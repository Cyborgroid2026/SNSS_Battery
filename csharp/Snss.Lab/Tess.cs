namespace Snss;

/// <summary>보로노이 · 프랙탈 단면과 회로망 (spec §5). 보로노이는 반평면 절단으로 직접 구한다.</summary>
public sealed record FractalParams(double D, double Roughness, double Correlation, double Ds, double Grains,
                                   int Layers, double Width, ulong Seed);

public sealed class NetResult
{
    public int NCells, NInner;
    public double VWin, RWin, PLoss, ActiveLen, DefectLen, MeanNb, Ocv, R, LeakMa;
}

public static class Tess
{
    public const long Bottom = -1, Top = -2, Side = -3;

    public static List<(double X, double Z)> Seeds(FractalParams p, double w, double h, double sp, SplitMix64 rng)
    {
        var pts = new List<(double, double)>();
        if (p.Ds >= 1.999)
        {
            int nx = (int)Math.Max(2, SplitMix64.RoundHalfUp(w / sp));
            int nz = (int)Math.Max(2, SplitMix64.RoundHalfUp(h / sp));
            for (int j = 0; j < nz; j++)
                for (int i = 0; i < nx; i++)
                {
                    double x = (i + 0.5) * w / nx + rng.Uniform(-0.42, 0.42) * w / nx;
                    double z = (j + 0.5) * h / nz + rng.Uniform(-0.42, 0.42) * h / nz;
                    pts.Add((x, z));
                }
            return pts;
        }
        double m = Math.Pow(2, p.Ds), s0 = sp * 16.0;
        int n0 = (int)Math.Max(1, SplitMix64.RoundHalfUp(w * h / (s0 * s0)));
        for (int k = 0; k < n0; k++)
        {
            double x = rng.Uniform(0, 1) * w, z = rng.Uniform(0, 1) * h;
            pts.Add((x, z));
        }
        double half = s0 / 2.0;
        for (int level = 0; level < 4; level++)
        {
            var counts = pts.Select(_ => Math.Max(1, rng.Poisson(m))).ToArray();
            var next = new List<(double, double)>();
            for (int k = 0; k < pts.Count; k++)
                for (int c = 0; c < counts[k]; c++)
                {
                    double dx = rng.Uniform(-half, half), dz = rng.Uniform(-half, half);
                    next.Add((pts[k].Item1 + dx, pts[k].Item2 + dz));
                }
            pts = next;
            half /= 2.0;
        }
        var outp = new List<(double, double)>();
        var seen = new HashSet<(long, long)>();
        foreach (var (x0, z0) in pts)
        {
            double x = ((x0 % w) + w) % w;
            double z = Math.Abs(z0);
            if (z > h) z = 2 * h - z;
            z = Math.Min(Math.Max(z, h * 1e-4), h * (1 - 1e-4));
            var key = ((long)Math.Floor(x / (sp * 1e-3) + 0.5), (long)Math.Floor(z / (sp * 1e-3) + 0.5));
            if (seen.Add(key)) outp.Add((x, z));
        }
        return outp;
    }

    public sealed class Interfaces
    {
        private readonly double[] _amp, _freq, _common;
        private readonly double[][] _own;
        private readonly double _norm, _t, _rough, _wc, _wi;

        public Interfaces(FractalParams p, double w, double t, int n, double fine, SplitMix64 rng)
        {
            const double gamma = 1.7;
            int terms = (int)Math.Max(4, (long)Math.Floor(Math.Log(w / (fine / 2)) / Math.Log(gamma)) + 1);
            _amp = Enumerable.Range(0, terms).Select(k => Math.Pow(gamma, (p.D - 2) * k)).ToArray();
            _freq = Enumerable.Range(0, terms).Select(k => 2 * Math.PI * Math.Pow(gamma, k) / w).ToArray();
            _norm = Math.Sqrt(_amp.Sum(a => a * a) / 2);
            _own = new double[n][];
            for (int b = 0; b < n; b++)
            {
                _own[b] = new double[terms];
                for (int k = 0; k < terms; k++) _own[b][k] = rng.Uniform(0, 2 * Math.PI);
            }
            _common = new double[terms];
            for (int k = 0; k < terms; k++) _common[k] = rng.Uniform(0, 2 * Math.PI);
            _t = t; _rough = p.Roughness; _wc = Math.Sqrt(p.Correlation); _wi = Math.Sqrt(1 - p.Correlation);
        }

        public int Count => _own.Length;

        public double Height(int b, double x)
        {
            double baseH = (b + 1) * _t;
            if (_rough == 0) return baseH;
            double a = 0, o = 0;
            for (int k = 0; k < _amp.Length; k++)
            {
                a += _amp[k] * Math.Cos(_freq[k] * x + _common[k]);
                o += _amp[k] * Math.Cos(_freq[k] * x + _own[b][k]);
            }
            return baseH + _rough * _t * (_wc * a + _wi * o) / _norm;
        }
    }

    private static List<(double X, double Z, long Lab)> Clip(List<(double X, double Z, long Lab)> poly,
        (double X, double Z) pi, (double X, double Z) pj, long j)
    {
        double nx = pj.X - pi.X, nz = pj.Z - pi.Z, mx = 0.5 * (pi.X + pj.X), mz = 0.5 * (pi.Z + pj.Z);
        double Side(double x, double z) => (x - mx) * nx + (z - mz) * nz;
        var outp = new List<(double, double, long)>(poly.Count + 2);
        for (int k = 0; k < poly.Count; k++)
        {
            var (x0, z0, lab) = poly[k];
            var (x1, z1, _) = poly[(k + 1) % poly.Count];
            double s0 = Side(x0, z0), s1 = Side(x1, z1);
            bool in0 = s0 <= 0, in1 = s1 <= 0;
            if (in0) outp.Add((x0, z0, lab));
            if (in0 != in1)
            {
                double r = s0 / (s0 - s1);
                outp.Add((x0 + r * (x1 - x0), z0 + r * (z1 - z0), in0 ? j : lab));
            }
        }
        return outp;
    }

    public sealed class Section
    {
        public double W, H, T;
        public required List<(double X, double Z)> Seeds;
        public required long[] Layer;
        public required List<List<(double X, double Z, long Lab)>> Cells;
    }

    public static Section Build(Battery bat, FractalParams p)
    {
        double t = bat.LayerMm, w = p.Width, h = p.Layers * t, sp = t / p.Grains;
        var rng = new SplitMix64(p.Seed);
        var pts = Seeds(p, w, h, sp, rng);
        var ifc = new Interfaces(p, w, t, p.Layers - 1, sp, rng);
        var layer = pts.Select(q => (long)Enumerable.Range(0, ifc.Count).Count(b => q.Z > ifc.Height(b, q.X))).ToArray();
        double bs = Math.Max(Math.Max(w, h) / Math.Sqrt(pts.Count) * 1.5, 1e-6);
        long bx = (long)Math.Ceiling(w / bs), bz = (long)Math.Ceiling(h / bs);
        var buckets = new List<int>[bx * bz];
        for (int k = 0; k < buckets.Length; k++) buckets[k] = [];
        for (int i = 0; i < pts.Count; i++)
        {
            long cx = Math.Min((long)(pts[i].X / bs), bx - 1), cz = Math.Min((long)(pts[i].Z / bs), bz - 1);
            buckets[cz * bx + cx].Add(i);
        }
        var cells = new List<List<(double, double, long)>>(pts.Count);
        for (int i = 0; i < pts.Count; i++)
        {
            var pi = pts[i];
            var poly = new List<(double X, double Z, long Lab)> { (0, 0, Bottom), (w, 0, Side), (w, h, Top), (0, h, Side) };
            long cx = Math.Min((long)(pi.X / bs), bx - 1), cz = Math.Min((long)(pi.Z / bs), bz - 1);
            for (long ring = 0; ; ring++)
            {
                for (long dz = -ring; dz <= ring; dz++)
                    for (long dx = -ring; dx <= ring; dx++)
                    {
                        if (Math.Abs(dx) != ring && Math.Abs(dz) != ring) continue;
                        long gx = cx + dx, gz = cz + dz;
                        if (gx < 0 || gz < 0 || gx >= bx || gz >= bz) continue;
                        foreach (int j in buckets[gz * bx + gx])
                            if (j != i) poly = Clip(poly, pi, pts[j], j);
                    }
                double rmax = poly.Max(v => Math.Sqrt((v.X - pi.X) * (v.X - pi.X) + (v.Z - pi.Z) * (v.Z - pi.Z)));
                if (ring * bs >= 2 * rmax + bs || ring > Math.Max(bx, bz)) break;
            }
            cells.Add(poly);
        }
        return new Section { W = w, H = h, T = t, Seeds = pts, Layer = layer, Cells = cells };
    }

    private static double[] Cg(double[] diag, List<(int I, int J, double G)> offd, double[] b)
    {
        int n = b.Length;
        var x = new double[n];
        var r = (double[])b.Clone();
        var z = new double[n];
        for (int k = 0; k < n; k++) z[k] = r[k] / diag[k];
        var p = (double[])z.Clone();
        var ap = new double[n];
        double rz = 0;
        for (int k = 0; k < n; k++) rz += r[k] * z[k];
        double bnorm = Math.Max(Math.Sqrt(b.Sum(v => v * v)), 1e-300);
        for (int it = 0; it < 20 * n + 100; it++)
        {
            for (int k = 0; k < n; k++) ap[k] = diag[k] * p[k];
            foreach (var (i, j, g) in offd) { ap[i] -= g * p[j]; ap[j] -= g * p[i]; }
            double pap = 0;
            for (int k = 0; k < n; k++) pap += p[k] * ap[k];
            double alpha = rz / pap;
            double rr = 0;
            for (int k = 0; k < n; k++) { x[k] += alpha * p[k]; r[k] -= alpha * ap[k]; rr += r[k] * r[k]; }
            if (Math.Sqrt(rr) / bnorm < 1e-14) break;
            double rz2 = 0;
            for (int k = 0; k < n; k++) { z[k] = r[k] / diag[k]; rz2 += r[k] * z[k]; }
            double beta = rz2 / rz;
            rz = rz2;
            for (int k = 0; k < n; k++) p[k] = z[k] + beta * p[k];
        }
        return x;
    }

    public static NetResult Network(Battery bat, Section sec)
    {
        var s = bat.Stack;
        int n = sec.Seeds.Count;
        double vt = Saline.ThermalVoltage(s.Temp);
        double ratio = s.X > 0 ? Math.Log(s.CB / s.CA) : 0.0;
        double eC = s.Cem.Selectivity(s.C0) * vt * ratio, eA = s.Aem.Selectivity(s.C0) * vt * ratio;
        double rC = s.Cem.Asr * 100.0, rA = s.Aem.Asr * 100.0;
        double sigA = Saline.Conductivity(s.CA, s.Temp) / 1000.0, sigB = Saline.Conductivity(s.CB, s.Temp) / 1000.0;
        double Sig(int i) => sec.Layer[i] % 2 == 0 ? sigA : sigB;
        var edges = new List<(int I, int J, double G, double E)>();
        double active = 0, defect = 0;
        var nb = new int[n];
        var bottom = new List<(int, double)>();
        var top = new List<(int, double)>();
        for (int i = 0; i < n; i++)
        {
            var poly = sec.Cells[i];
            for (int k = 0; k < poly.Count; k++)
            {
                var (x0, z0, lab) = poly[k];
                var (x1, z1, _) = poly[(k + 1) % poly.Count];
                double len = Math.Sqrt((x1 - x0) * (x1 - x0) + (z1 - z0) * (z1 - z0));
                if (lab == Bottom || lab == Top)
                {
                    double dist = lab == Bottom ? sec.Seeds[i].Z : sec.H - sec.Seeds[i].Z;
                    double gc = 1.0 / (Math.Max(dist, 1e-3) / (Sig(i) * Math.Max(len, 1e-9)) + 1e-3);
                    (lab == Bottom ? bottom : top).Add((i, gc));
                    continue;
                }
                if (lab < 0 || lab <= i || len <= 1e-9) continue;
                int j = (int)lab;
                double dX = sec.Seeds[i].X - sec.Seeds[j].X, dZ = sec.Seeds[i].Z - sec.Seeds[j].Z;
                double d = Math.Sqrt(dX * dX + dZ * dZ);
                long dl = sec.Layer[j] - sec.Layer[i];
                bool isC = Math.Min(sec.Layer[i], sec.Layer[j]) % 2 == 0;
                bool act = Math.Abs(dl) == 1;
                double rWall = act ? (isC ? rC : rA) : (rC + rA) / 2.0;
                double r = rWall / len + d / 2.0 / (Sig(i) * len) + d / 2.0 / (Sig(j) * len);
                double e = act ? Math.Sign(dl) * (isC ? eC : eA) : 0.0;
                if (act) active += len;
                if (Math.Abs(dl) >= 2) defect += len;
                nb[i]++; nb[j]++;
                edges.Add((i, j, 1.0 / r, e));
            }
        }
        var diag = new double[n + 1];
        var offd = new List<(int, int, double)>();
        foreach (var (i, j, g, _) in edges) { diag[i] += g; diag[j] += g; offd.Add((i, j, g)); }
        foreach (var (i, g) in bottom) diag[i] += g;
        foreach (var (i, g) in top) { diag[i] += g; diag[n] += g; offd.Add((i, n, g)); }
        var b = new double[n + 1];
        foreach (var (i, j, g, e) in edges) { b[i] -= g * e; b[j] += g * e; }
        var phi = Cg(diag, offd, b);
        var b1 = new double[n + 1];
        b1[n] = 1.0;
        double rWin = Cg(diag, offd, b1)[n], vWin = phi[n];
        double pLoss = edges.Sum(q => q.G * Math.Pow(phi[q.I] + q.E - phi[q.J], 2));
        double t = sec.T;
        var interior = Enumerable.Range(0, n).Where(i =>
        {
            var (x, z) = sec.Seeds[i];
            return x > 2 * t && x < sec.W - 2 * t && z > 2 * t && z < sec.H - 2 * t;
        }).ToList();
        double meanNb = interior.Count == 0 ? nb.Average() : interior.Average(i => (double)nb[i]);
        double l = Math.Round(sec.H / t), nTot = 2.0 * s.NPairs, depth = sec.W / (s.AreaCm2 * 100.0);
        double ocv = vWin * nTot / (l - 1.0), rDev = rWin * (nTot / l) * depth, pDev = pLoss * (nTot / l) / depth;
        return new NetResult
        {
            NCells = n, NInner = edges.Count, VWin = vWin, RWin = rWin, PLoss = pLoss, ActiveLen = active,
            DefectLen = defect, MeanNb = meanNb, Ocv = ocv, R = rDev, LeakMa = ocv > 0 ? pDev / ocv * 1000.0 : 0.0,
        };
    }
}
