namespace Snss;

/// <summary>대사(에너지원) · 부하 · 시뮬레이션 (spec §6–8)</summary>
public sealed class Metabolism
{
    public double Irradiance = 10.0, Wavelength = 405.0, Qe = 1e-3, Penetration = 1.0, DayHours = 12.0;
    public double FuelMm = 50.0, Ions = 1.0, Rate = 0.3, Asr = 30.0, Remaining = 1.0, EvapMmH = 0.2, SaltD = 1.5e-9;

    public Metabolism Clone() => (Metabolism)MemberwiseClone();

    public double LightPump(Battery b)
    {
        double photon = 6.62607015e-34 * 2.99792458e8 / (Wavelength * 1e-9);
        double flux = Irradiance * 1e-3 / photon;
        double area = Math.PI * b.GelD / 10.0 * Math.Min(Penetration, b.GelD / 2.0) / 10.0;
        return 1.602176634e-19 * flux * Qe * area;
    }

    public bool Lit(double t) => t / 3600.0 % 24.0 < DayHours;

    public double FuelPump(Battery b) =>
        Remaining <= 0 ? 0 : Ions * Saline.Faraday * Rate / 86400.0 * (FuelMm * 1e-3 * b.Stack.VolumeL) * Remaining;

    public double EvapEmf(Battery b)
    {
        var s = b.Stack;
        double v = EvapMmH * 1e-3 / 3600.0, pe = v * b.GelH * 1e-3 / SaltD;
        double ratio = Math.Min(Math.Exp(Math.Min(pe, 50.0)), 6.1 / s.C0);
        return 0.5 * (s.Cem.Selectivity(s.C0) - s.Aem.Selectivity(s.C0)) * Saline.ThermalVoltage(s.Temp) * Math.Log(ratio);
    }

    public void Attach(Battery b)
    {
        double e = EvapEmf(b);
        b.Stack.Faradaic = true;
        b.Stack.ContactAsr = Asr;
        b.Stack.ExtraEmf = e;
    }

    public double Pump(Battery b, double t) => (Lit(t) ? LightPump(b) : 0.0) + FuelPump(b);
    public void Consume(double dt) => Remaining *= Math.Exp(-Rate * dt / 86400.0);
}

public interface ILoad
{
    double Voltage(double i);
    bool IsLit(double i);
}

public sealed class Led : ILoad
{
    public double Voltage(double i)
    {
        const double nvt = 2.0 * 0.025693;
        double iS = 1e-3 / Math.Exp(1.85 / nvt);
        return nvt * Math.Log(Math.Max(i, 0.0) / iS + 1.0) + 470.0 * i;
    }
    public bool IsLit(double i) => i >= 20e-6;
}

public sealed class Bulb : ILoad
{
    public static double Resistance(double i)
    {
        const double rHot = 2.5 / 0.3;
        double r = rHot * 0.1;
        for (int k = 0; k < 30; k++)
        {
            double p = i * i * r;
            r = rHot * (0.1 + 0.9 * Math.Pow(Math.Min(p / 0.75, 1.5), 0.6));
        }
        return r;
    }
    public double Voltage(double i) => i * Resistance(i);
    public bool IsLit(double i) => i * Voltage(i) >= 0.15 * 0.75;
}

public sealed record RunResult(double? FirstOffH, double OnFraction, double LastI);

public static class Sim
{
    public static double Operating(double ocv, double r, ILoad load)
    {
        if (ocv <= 0) return 0;
        double lo = 0, hi = ocv / r;
        for (int k = 0; k < 100; k++)
        {
            double mid = 0.5 * (lo + hi);
            if (ocv - mid * r - load.Voltage(mid) > 0) lo = mid; else hi = mid;
        }
        return 0.5 * (lo + hi);
    }

    public static RunResult Simulate(Battery bat, Metabolism met, ILoad load, double hours, double dt, int k,
                                     List<(double H, double I, bool Light)>? trace = null, int every = 10)
    {
        var b = bat.Clone();
        var m = met.Clone();
        m.Attach(b);
        int steps = (int)(hours * 3600.0 / dt);
        double? first = null;
        int on = 0;
        double last = 0;
        for (int n = 0; n <= steps; n++)
        {
            double t = n * dt;
            double i = Operating(b.Stack.Ocv / k, b.Stack.RInt / ((double)k * k), load);
            if (load.IsLit(i)) on++;
            else first ??= t / 3600.0;
            if (trace != null && n % every == 0) trace.Add((t / 3600.0, i, m.Lit(t)));
            double pump = m.Pump(b, t);
            b.Stack.Step(i / k, dt, pump);
            m.Consume(dt);
            last = i;
        }
        return new RunResult(first, on / (double)(steps + 1), last);
    }

    public static (int K, double P) BestParallel(Battery bat, Metabolism met, ILoad load)
    {
        var b = bat.Clone();
        met.Attach(b);
        int best = 1;
        double bestP = -1;
        for (int k = 1; k <= Math.Min(64, b.Stack.NPairs); k++)
        {
            double i = Operating(b.Stack.Ocv / k, b.Stack.RInt / ((double)k * k), load);
            double p = i * load.Voltage(i);
            if (p > bestP) { best = k; bestP = p; }
        }
        return (best, bestP);
    }
}
