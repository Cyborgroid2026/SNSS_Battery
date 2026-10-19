namespace Snss;

/// <summary>SplitMix64 — spec §1. Python·Rust 와 같은 수열.</summary>
public sealed class SplitMix64(ulong seed)
{
    private ulong _state = seed;

    public ulong NextU64()
    {
        unchecked
        {
            _state += 0x9E3779B97F4A7C15UL;
            ulong z = _state;
            z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
            z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
            return z ^ (z >> 31);
        }
    }

    public double U() => (NextU64() >> 11) * (1.0 / (1UL << 53));

    public double Uniform(double a, double b) => a + (b - a) * U();

    public int Poisson(double lam)
    {
        double limit = Math.Exp(-lam), p = 1.0;
        int k = 0;
        while (true)
        {
            p *= U();
            if (p <= limit) return k;
            k++;
        }
    }

    public static long RoundHalfUp(double v) => (long)Math.Floor(v + 0.5);
}
