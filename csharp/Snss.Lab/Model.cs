namespace Snss;

/// <summary>식염수 · 막 · 층 스택 · 병 (spec §2–4)</summary>
public static class Saline
{
    public const double Faraday = 96485.33212;
    public const double Gas = 8.314462618;

    private static readonly (double C, double K)[] Table =
    [
        (0.0, 0.0), (0.001, 0.1237), (0.01, 1.185), (0.05, 5.55), (0.1, 10.67), (0.154, 15.6), (0.5, 47.0),
        (1.0, 85.8), (2.0, 145.0), (3.0, 187.0), (4.0, 213.0), (5.0, 222.0), (6.1, 225.0),
    ];

    public static double Conductivity(double c, double t)
    {
        c = Math.Max(c, 0.0);
        double k25;
        if (c <= Table[0].C) k25 = Table[0].K;
        else if (c >= Table[^1].C) k25 = Table[^1].K;
        else
        {
            int i = 1;
            while (Table[i].C < c) i++;
            var (x0, y0) = Table[i - 1];
            var (x1, y1) = Table[i];
            k25 = y0 + (y1 - y0) * (c - x0) / (x1 - x0);
        }
        return Math.Max(k25 * 0.1 * (1.0 + 0.0212 * (t - 25.0)), 5.5e-6);
    }

    public static double Molarity(double wt) => Math.Min(wt / 100.0 * (0.997 + 0.0071 * wt) * 1000.0 / 58.44, 6.1);

    public static double ThermalVoltage(double t) => Gas * (t + 273.15) / Faraday;
}

public readonly record struct Membrane(double Alpha0, double Half, double Asr, double Perm, double ThickUm)
{
    public double Selectivity(double c) => Alpha0 / (1.0 + c / Half);
    public static readonly Membrane GoLc = new(0.85, 0.30, 5.0, 2e-11, 5.0);
    public static readonly Membrane GoPdda = new(0.80, 0.30, 6.0, 2e-11, 8.0);
}

public sealed class Stack
{
    public int NPairs;
    public double Temp, C0, AreaCm2, TMm, ContactMg, X, Q, ContactAsr, ExtraEmf;
    public Membrane Cem = Membrane.GoLc, Aem = Membrane.GoPdda;
    public bool Faradaic;

    public Stack Clone() => (Stack)MemberwiseClone();
    public double VolumeL => AreaCm2 * TMm * 100.0 * 1e-6;
    public double MaxShift => C0 - 0.002;
    public double CA => C0 - X;
    public double CB => C0 + X;
    public double Eta => 0.5 * (Cem.Selectivity(C0) + Aem.Selectivity(C0));
    public double Capacitance => ContactMg * 1e-3 * 150.0;
    public double CapacityC => Math.Min(MaxShift * VolumeL * Saline.Faraday / Eta, Capacitance * 0.6);

    public double PairEmf =>
        (Cem.Selectivity(C0) + Aem.Selectivity(C0)) * Saline.ThermalVoltage(Temp) * Math.Log(CB / CA);

    public double ElectrodeV => Faradaic ? 0.0 : Q / Capacitance;
    public double Ocv => NPairs * PairEmf + 2.0 * ElectrodeV + ExtraEmf;

    public double PairR
    {
        get
        {
            double a = AreaCm2 * 1e-4, t = TMm * 1e-3;
            return (Cem.Asr + Aem.Asr) / AreaCm2 + t / (Saline.Conductivity(CA, Temp) * a)
                   + t / (Saline.Conductivity(CB, Temp) * a);
        }
    }

    public double RInt => NPairs * PairR + 0.2 + (Faradaic ? 2.0 * ContactAsr / AreaCm2 : 0.0);

    public void Step(double current, double dt, double pump)
    {
        double v = VolumeL;
        double dx = -Eta * current * dt / (Saline.Faraday * v);
        dx += pump * dt / (Saline.Faraday * v);
        double flux = (Cem.Perm + Aem.Perm) * AreaCm2 * 1e-4 * (CB - CA) * 1000.0;
        dx -= flux * dt / v;
        X = Math.Min(Math.Max(X + dx, -MaxShift), MaxShift);
        if (!Faradaic) Q -= current * dt;
    }
}

public sealed class Battery
{
    public required Stack Stack;
    public double GelD, GelH, LayerMm;
    public Battery Clone() => new() { Stack = Stack.Clone(), GelD = GelD, GelH = GelH, LayerMm = LayerMm };
}

public sealed record Case(double BottleMl, double BottleD, double Nacl, double Temp, double Go, double Layer,
                          double Ratio, double Shrink, double SurfaceGo)
{
    public Battery Build()
    {
        double di = BottleD - 1.6;
        double areaIn = Math.PI * Math.Pow(di / 20.0, 2);
        double fillH = BottleMl / areaIn * 10.0;
        double gelD = di * (1.0 - Shrink), gelH = fillH * (1.0 - Shrink);
        double ag = Math.PI * Math.Pow(gelD / 20.0, 2);
        double pair = 2.0 * Layer + (Membrane.GoLc.ThickUm + Membrane.GoPdda.ThickUm) / 1000.0;
        int n = (int)Math.Floor(gelH / pair + 1e-9);
        double goMg = Go * BottleMl;
        double surf = SurfaceGo > 0 ? SurfaceGo : goMg / (2.0 * n) / ag;
        double c0 = Saline.Molarity(Nacl);
        var s = new Stack { NPairs = n, Temp = Temp, C0 = c0, AreaCm2 = ag, TMm = Layer, ContactMg = surf * ag };
        s.X = Math.Min(c0 * (Ratio - 1.0) / (Ratio + 1.0), s.MaxShift);
        return new Battery { Stack = s, GelD = gelD, GelH = gelH, LayerMm = Layer };
    }
}
