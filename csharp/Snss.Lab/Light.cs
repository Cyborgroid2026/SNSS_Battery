namespace Snss;

/// <summary>빛 조각가 SC-2 — 잉크층 · 405/530 nm 층 노출 (spec/SPEC.md §11, spec/LIGHT.md). Python lightsculpt.py · Rust 와 같은 식.</summary>
public sealed record Light(double Go, double Pva, double Nacl, double EosinUm, double DepthMm, double Irr, double Green)
{
    // 고정 상수 (lightsculpt.Photo · Tank · Desktop 기본값)
    const double EpsGo = 15.0, ASbq = 1.5, Ec = 20.0, Overcure = 0.25;
    public const double ERed = 1000.0;
    const double EpsGo530 = 10.0, EpsEosin = 95000.0, EGraft = 300.0, GraftTarget = 0.8;
    const double CccGoNacl = 44.0, CccPerPva = 0.15, RhoWater = 997.05, NaclRhoPerMm = 0.0405;
    const double DNacl = 1.5e-9, KWater = 0.6, SalineMm = 154.0, TankM = 0.35, FillM = 0.33, WallU = 10.0;
    const double Reflect = 0.02, BuildMm = 110.0, ZMotorW = 3 * 0.35, InsulWmk = 0.035, InsulMm = 30.0, ExhaustK = 5.0;

    /// <summary>erfc — |x| &lt; 3 은 erf 급수, 그 밖은 연분수 (Lentz).</summary>
    public static double Erfc(double x)
    {
        if (x < 0) return 2.0 - Erfc(-x);
        if (x < 3.0)
        {
            double term = x, sum = x, n = 0;
            while (true)
            {
                n += 1;
                term *= -x * x / n;
                double add = term / (2 * n + 1);
                sum += add;
                if (Math.Abs(add) < 1e-17 * Math.Abs(sum)) break;
            }
            return 1.0 - 2.0 / Math.Sqrt(Math.PI) * sum;
        }
        const double tiny = 1e-300;
        double f = x, c = x, d = 0;
        for (int i = 1; i < 300; i++)
        {
            double a = i / 2.0;
            d = x + a * d; if (Math.Abs(d) < tiny) d = tiny;
            c = x + a / c; if (Math.Abs(c) < tiny) c = tiny;
            d = 1.0 / d;
            double delta = c * d;
            f *= delta;
            if (Math.Abs(delta - 1.0) < 1e-16) break;
        }
        return Math.Exp(-x * x) / Math.Sqrt(Math.PI) / f;
    }

    /// <summary>erfc 의 역함수 — 뉴턴.</summary>
    public static double ErfcInv(double y)
    {
        double x = 0;
        for (int i = 0; i < 100; i++)
        {
            double step = (Erfc(x) - y) / (2.0 / Math.Sqrt(Math.PI) * Math.Exp(-x * x));
            x += step;
            if (Math.Abs(step) < 1e-16 * Math.Max(Math.Abs(x), 1e-300)) break;
        }
        return x;
    }

    public double DpMm => 10.0 / (Math.Log(10) * (EpsGo * Go + ASbq * Pva));
    public double DpGreenMm => 10.0 / (Math.Log(10) * (EpsGo530 * Go + EpsEosin * EosinUm * 1e-6));
    public double EGraftTarget => EGraft * Math.Log(1.0 / (1.0 - GraftTarget));

    /// <summary>세포질 기둥 바로 아래 막 칸이 받는 누적량 / E_red (층 = x·Dp)</summary>
    public double MembraneLeak(double x)
    {
        double eMem = Ec * Math.Exp((1 + Overcure) * x);
        return Math.Exp(-x) + eMem * (1 - Math.Exp(-x)) / x / ERed;
    }

    /// <summary>0.5–4 를 351 칸 (numpy linspace 와 같은 i·step + start) 에서 첫 최솟값</summary>
    public double LayerRatio
    {
        get
        {
            double step = (4.0 - 0.5) / 350.0, bestV = double.PositiveInfinity, bestX = 0.5;
            for (int i = 0; i < 351; i++)
            {
                double x = i == 350 ? 4.0 : i * step + 0.5;
                double v = MembraneLeak(x);
                if (v < bestV) { bestV = v; bestX = x; }
            }
            return bestX;
        }
    }

    public double LayerMm => Math.Round(LayerRatio * DpMm * 1000.0, MidpointRounding.AwayFromZero) / 1000.0;
    public double ECure => Ec * Math.Exp((1 + Overcure) * LayerMm / DpMm);
    public double CccMm => CccGoNacl * (1 + CccPerPva * Pva);
    public double InkDensity => RhoWater + Go * (1 - RhoWater / 1800) + 10 * Pva * (1 - RhoWater / 1270) + NaclRhoPerMm * Nacl;

    public double InkLifeH
    {
        get
        {
            double frac = (0.8 * CccMm - Nacl) / (SalineMm - Nacl);
            double x = ErfcInv(2 * frac);
            double d = DepthMm / 1000;
            return Math.Pow(d / (2 * x), 2) / DNacl / 3600;
        }
    }

    public double SurfaceRiseK => Math.Max(Irr, Green) * 10 * (1 - Reflect) / (KWater / (DepthMm / 1000) + 10.0);

    public double HeatRiseK
    {
        get
        {
            double light = Irr * 10 * (1 - Reflect) * BuildMm * BuildMm / 1e6;
            double pc = InsulWmk / (InsulMm / 1000) * TankM * TankM * ExhaustK;
            double loss = WallU * (2 * (TankM + TankM) * FillM + TankM * TankM);
            return (light + ZMotorW + pc) / loss;
        }
    }

    public double BuildTimeH(double heightMm) => ERed * heightMm / (DpMm * Irr) / 3600;

    /// <summary>한 기둥 (아래 → 위): 노출 E · 누적 D. lightsculpt._columns 와 같은 위층부터의 풀이.</summary>
    public static (double[] E, double[] D) Columns(double[] floor, double[] target, double x)
    {
        double r = Math.Exp(-x), c = (1 - r) / x, q = 0;
        int n = floor.Length;
        var e = new double[n];
        var d = new double[n];
        for (int k = n - 1; k >= 0; k--)
        {
            double want = target[k] > 0 ? (target[k] - c * q) / c : 0.0;
            e[k] = Math.Max(floor[k], want);
            d[k] = c * (e[k] + q);
            q = r * (e[k] + q);
        }
        return (e, d);
    }

    /// <summary>기둥 글자 (P · N · M · 0) → 405 nm 와 530 nm 의 (E, D, G, Dg)</summary>
    public double[][] Column(string col)
    {
        double h = LayerMm, cure = ECure, eg = EGraftTarget;
        var floor = col.Select(m => m != '0' ? cure : 0.0).ToArray();
        var tgt = col.Select(m => m is 'P' or 'N' ? ERed : 0.0).ToArray();
        var gt = col.Select(m => m == 'P' ? eg : 0.0).ToArray();
        var (e, d) = Columns(floor, tgt, h / DpMm);
        var (g, dg) = Columns(new double[col.Length], gt, h / DpGreenMm);
        return [e, d, g, dg];
    }
}
