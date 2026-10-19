namespace Snss;

/// <summary>SNSS-QB 양자 모듈 — Tavis–Cummings 충전 (spec/QUANTUM.md §1–2). Python·Rust 와 같은 RK4.</summary>
public sealed record ChargeResult(int N, int Steps, double Tau, double Energy, double Ergotropy, double Advantage);

public static class Quantum
{
    public static ChargeResult Charge(int n)
    {
        var off = new double[n];
        for (int k = 0; k < n; k++) off[k] = (n - k) * Math.Sqrt(k + 1);
        double norm = double.MinValue;
        for (int k = 0; k <= n; k++) norm = Math.Max(norm, (k > 0 ? off[k - 1] : 0) + (k < n ? off[k] : 0));
        double dt = 0.02 / norm;

        (double[], double[]) Deriv(double[] r, double[] i)
        {
            var dr = new double[n + 1];
            var di = new double[n + 1];
            for (int k = 0; k <= n; k++)
            {
                double hr = 0, hi = 0;
                if (k > 0) { hr += off[k - 1] * r[k - 1]; hi += off[k - 1] * i[k - 1]; }
                if (k < n) { hr += off[k] * r[k + 1]; hi += off[k] * i[k + 1]; }
                dr[k] = hi;
                di[k] = -hr;
            }
            return (dr, di);
        }
        double Energy(double[] r, double[] i)
        {
            double e = 0;
            for (int k = 0; k <= n; k++) e += k * (r[k] * r[k] + i[k] * i[k]);
            return e;
        }
        double[] Axpy(double[] a, double[] b, double s) => a.Select((x, k) => x + s * b[k]).ToArray();

        var re = new double[n + 1];
        var im = new double[n + 1];
        re[0] = 1.0;
        double prev = Energy(re, im);
        int step = 0;
        while (true)
        {
            var (k1r, k1i) = Deriv(re, im);
            var (k2r, k2i) = Deriv(Axpy(re, k1r, 0.5 * dt), Axpy(im, k1i, 0.5 * dt));
            var (k3r, k3i) = Deriv(Axpy(re, k2r, 0.5 * dt), Axpy(im, k2i, 0.5 * dt));
            var (k4r, k4i) = Deriv(Axpy(re, k3r, dt), Axpy(im, k3i, dt));
            var nr = new double[n + 1];
            var ni = new double[n + 1];
            for (int k = 0; k <= n; k++)
            {
                nr[k] = re[k] + dt / 6.0 * (k1r[k] + 2.0 * k2r[k] + 2.0 * k3r[k] + k4r[k]);
                ni[k] = im[k] + dt / 6.0 * (k1i[k] + 2.0 * k2i[k] + 2.0 * k3i[k] + k4i[k]);
            }
            double e = Energy(nr, ni);
            if (e < prev && step > 0) break;
            re = nr; im = ni; prev = e; step++;
        }
        double tau = step * dt, pmax = 0;
        for (int k = 0; k <= n; k++) pmax = Math.Max(pmax, re[k] * re[k] + im[k] * im[k]);
        double power = prev / tau;
        return new ChargeResult(n, step, tau, prev, prev - (1.0 - pmax), power / (n / (Math.PI / 2.0)));
    }

    public static (List<ChargeResult> Rows, double Exponent) Scaling(int[] ns)
    {
        var rows = ns.Select(Charge).ToList();
        var xs = rows.Select(r => Math.Log(r.N)).ToArray();
        var ys = rows.Select(r => Math.Log(r.Tau)).ToArray();
        double mx = xs.Average(), my = ys.Average();
        double slope = xs.Zip(ys, (x, y) => (x - mx) * (y - my)).Sum() / xs.Sum(x => (x - mx) * (x - mx));
        return (rows, -slope);
    }
}
