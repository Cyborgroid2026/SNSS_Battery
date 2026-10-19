using System.Globalization;
using System.Text;

namespace Snss;

/// <summary>
/// 동축 원기둥 적층을 정확한 B-rep (평면 2 + 원통면 1, 원 2 + 이음선 1) 으로 STEP AP214 (ISO 10303-21) 에 직접 쓴다.
/// 외부 CAD 라이브러리 없이 표준 엔티티만 사용 — OpenCascade 등 어떤 CAD 에서도 열린다.
/// </summary>
public sealed class StepWriter
{
    private readonly StringBuilder _data = new();
    private int _id;

    private static string F(double v) => v.ToString("0.0###############E+00", CultureInfo.InvariantCulture);

    /// <summary>STEP 문자열: ASCII 밖 문자는 \X2\…\X0\ (UTF-16 16진수)</summary>
    private static string S(string s)
    {
        var sb = new StringBuilder("'");
        foreach (char c in s)
        {
            if (c == '\'') sb.Append("''");
            else if (c < 128) sb.Append(c);
            else sb.Append($"\\X2\\{(int)c:X4}\\X0\\");
        }
        return sb.Append('\'').ToString();
    }

    private int Add(string entity)
    {
        _id++;
        _data.Append('#').Append(_id).Append(" = ").Append(entity).Append(";\n");
        return _id;
    }

    private int Point(double x, double y, double z) => Add($"CARTESIAN_POINT('', ({F(x)}, {F(y)}, {F(z)}))");
    private int Dir(double x, double y, double z) => Add($"DIRECTION('', ({F(x)}, {F(y)}, {F(z)}))");

    private int Axis(double z)
    {
        int o = Point(0, 0, z), ax = Dir(0, 0, 1), rf = Dir(1, 0, 0);
        return Add($"AXIS2_PLACEMENT_3D('', #{o}, #{ax}, #{rf})");
    }

    /// <summary>반지름 r, z0~z1 원기둥 하나 → MANIFOLD_SOLID_BREP 번호</summary>
    public int Cylinder(string name, double r, double z0, double z1)
    {
        int pb = Point(r, 0, z0), pt = Point(r, 0, z1);
        int vb = Add($"VERTEX_POINT('', #{pb})"), vt = Add($"VERTEX_POINT('', #{pt})");
        int cb = Add($"CIRCLE('', #{Axis(z0)}, {F(r)})"), ct = Add($"CIRCLE('', #{Axis(z1)}, {F(r)})");
        int lineDir = Dir(0, 0, 1);
        int vec = Add($"VECTOR('', #{lineDir}, {F(z1 - z0)})");
        int line = Add($"LINE('', #{Point(r, 0, z0)}, #{vec})");
        int eb = Add($"EDGE_CURVE('', #{vb}, #{vb}, #{cb}, .T.)");
        int et = Add($"EDGE_CURVE('', #{vt}, #{vt}, #{ct}, .T.)");
        int es = Add($"EDGE_CURVE('', #{vb}, #{vt}, #{line}, .T.)");
        int Oe(int e, bool fwd) => Add($"ORIENTED_EDGE('', *, *, #{e}, {(fwd ? ".T." : ".F.")})");
        int Face(int[] edges, int surface, bool sense)
        {
            int loop = Add($"EDGE_LOOP('', ({string.Join(", ", edges.Select(e => "#" + e))}))");
            int bound = Add($"FACE_OUTER_BOUND('', #{loop}, .T.)");
            return Add($"ADVANCED_FACE('', (#{bound}), #{surface}, {(sense ? ".T." : ".F.")})");
        }
        // 아래면: 법선 −Z (평면 +Z, sense .F.), 위에서 보면 시계 방향
        int bottom = Face([Oe(eb, false)], Add($"PLANE('', #{Axis(z0)})"), false);
        int top = Face([Oe(et, true)], Add($"PLANE('', #{Axis(z1)})"), true);
        // 옆면: (각도 u, 높이 v) 에서 반시계 — 아래 원 → 이음선 ↑ → 위 원(역) → 이음선 ↓
        int cyl = Add($"CYLINDRICAL_SURFACE('', #{Axis(z0)}, {F(r)})");
        int side = Face([Oe(eb, true), Oe(es, true), Oe(et, false), Oe(es, false)], cyl, true);
        int shell = Add($"CLOSED_SHELL('', (#{bottom}, #{top}, #{side}))");
        return Add($"MANIFOLD_SOLID_BREP({S(name)}, #{shell})");
    }

    /// <summary>적층 (이름, 지름, 두께) 을 아래에서 위로 쌓아 STEP 파일로. 해석 부피 반환.</summary>
    public static double Write(string path, IEnumerable<(string Name, double D, double T)> layers, string product)
    {
        var w = new StepWriter();
        // 제품·단위 정의 (AP214)
        int appCtx = w.Add("APPLICATION_CONTEXT('core data for automotive mechanical design processes')");
        w.Add($"APPLICATION_PROTOCOL_DEFINITION('international standard', 'automotive_design', 2000, #{appCtx})");
        int prodCtx = w.Add($"PRODUCT_CONTEXT('', #{appCtx}, 'mechanical')");
        int prod = w.Add($"PRODUCT({S(product)}, {S(product)}, '', (#{prodCtx}))");
        int form = w.Add($"PRODUCT_DEFINITION_FORMATION('', '', #{prod})");
        int defCtx = w.Add($"PRODUCT_DEFINITION_CONTEXT('part definition', #{appCtx}, 'design')");
        int pdef = w.Add($"PRODUCT_DEFINITION('design', '', #{form}, #{defCtx})");
        int pds = w.Add($"PRODUCT_DEFINITION_SHAPE('', '', #{pdef})");
        int mm = w.Add("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )");
        int rad = w.Add("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )");
        int sr = w.Add("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )");
        int unc = w.Add($"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07), #{mm}, 'distance_accuracy_value', 'confusion accuracy')");
        int ctx = w.Add("( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#" + unc +
                        ")) GLOBAL_UNIT_ASSIGNED_CONTEXT((#" + mm + ", #" + rad + ", #" + sr +
                        ")) REPRESENTATION_CONTEXT('', '3D') )");
        var solids = new List<int>();
        double z = 0, vol = 0;
        foreach (var (name, d, t) in layers)
        {
            solids.Add(w.Cylinder(name, d / 2, z, z + t));
            vol += Math.PI * (d / 2) * (d / 2) * t;
            z += t;
        }
        int rep = w.Add($"ADVANCED_BREP_SHAPE_REPRESENTATION({S(product)}, ({string.Join(", ", solids.Select(s => "#" + s))}), #{ctx})");
        w.Add($"SHAPE_DEFINITION_REPRESENTATION(#{pds}, #{rep})");
        var file = new StringBuilder();
        file.Append("ISO-10303-21;\nHEADER;\n");
        file.Append("FILE_DESCRIPTION(('SNSS ").Append(product).Append(" - C# StepWriter'), '2;1');\n");
        file.Append($"FILE_NAME('{Path.GetFileName(path)}', '{DateTime.UtcNow:yyyy-MM-ddTHH:mm:ss}', (''), (''), 'Snss.Lab StepWriter', 'C#', '');\n");
        file.Append("FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\nENDSEC;\nDATA;\n");
        file.Append(w._data).Append("ENDSEC;\nEND-ISO-10303-21;\n");
        File.WriteAllText(path, file.ToString(), new UTF8Encoding(false));
        return vol;
    }

    // ---------- 형상 정의 (spec/QUANTUM.md §4, spec/SPEC.md §4) ----------
    public static List<(string, double, double)> QModuleLayers()
    {
        const double lam = 590.0;
        double tSio2 = lam / (4 * 1.46) * 1e-6, tSin = lam / (4 * 2.00) * 1e-6, tAct = lam / (2 * 1.49) * 1e-6;
        var v = new List<(string, double, double)> { ("기판 SiO2", 25.0, 1.0) };
        for (int k = 1; k <= 8; k++) { v.Add(($"아래 거울 SiO2 {k}", 24.0, tSio2)); v.Add(($"아래 거울 Si3N4 {k}", 24.0, tSin)); }
        v.Add(("활성층 PMMA+PDI 색소", 24.0, tAct));
        for (int k = 1; k <= 8; k++) { v.Add(($"위 거울 Si3N4 {k}", 24.0, tSin)); v.Add(($"위 거울 SiO2 {k}", 24.0, tSio2)); }
        v.Add(("덮개 SiO2", 25.0, 0.5));
        return v;
    }

    public static List<(string, double, double)> CrystalLayers()
    {
        double di = 72.0 - 1.6;
        double fillH = 500.0 / (Math.PI * Math.Pow(di / 20.0, 2)) * 10.0;
        int n = (int)Math.Floor(fillH / (2 * 0.5 + 0.013));
        var v = new List<(string, double, double)>();
        for (int k = 1; k <= n; k++)
        {
            v.Add(($"A{k} 묽은 도메인층", di, 0.5));
            v.Add(($"CEM{k} GO 액정 벽", di, 0.005));
            v.Add(($"B{k} 진한 도메인층", di, 0.5));
            v.Add(($"AEM{k} GO/PDDA 벽", di, 0.008));
        }
        return v;
    }
}
