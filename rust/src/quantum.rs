//! SNSS-QB 양자 모듈 — Tavis–Cummings 충전 (spec/QUANTUM.md §1–2). Python·C# 와 같은 RK4.

pub struct Charge {
    pub n: usize,
    pub steps: usize,
    pub tau: f64,
    pub energy: f64,
    pub ergotropy: f64,
    pub advantage: f64,
}

pub fn charge(n: usize) -> Charge {
    let off: Vec<f64> = (0..n).map(|k| (n - k) as f64 * ((k + 1) as f64).sqrt()).collect();
    let norm = (0..=n)
        .map(|k| (if k > 0 { off[k - 1] } else { 0.0 }) + (if k < n { off[k] } else { 0.0 }))
        .fold(f64::MIN, f64::max);
    let dt = 0.02 / norm;
    let deriv = |r: &[f64], i: &[f64]| -> (Vec<f64>, Vec<f64>) {
        let mut dr = vec![0.0; n + 1];
        let mut di = vec![0.0; n + 1];
        for k in 0..=n {
            let (mut hr, mut hi) = (0.0, 0.0);
            if k > 0 {
                hr += off[k - 1] * r[k - 1];
                hi += off[k - 1] * i[k - 1];
            }
            if k < n {
                hr += off[k] * r[k + 1];
                hi += off[k] * i[k + 1];
            }
            dr[k] = hi;
            di[k] = -hr;
        }
        (dr, di)
    };
    let energy = |r: &[f64], i: &[f64]| (0..=n).map(|k| k as f64 * (r[k] * r[k] + i[k] * i[k])).sum::<f64>();
    let mut re = vec![0.0; n + 1];
    let mut im = vec![0.0; n + 1];
    re[0] = 1.0;
    let mut prev = energy(&re, &im);
    let mut step = 0usize;
    let axpy = |a: &[f64], b: &[f64], s: f64| -> Vec<f64> { a.iter().zip(b).map(|(x, y)| x + s * y).collect() };
    loop {
        let (k1r, k1i) = deriv(&re, &im);
        let (k2r, k2i) = deriv(&axpy(&re, &k1r, 0.5 * dt), &axpy(&im, &k1i, 0.5 * dt));
        let (k3r, k3i) = deriv(&axpy(&re, &k2r, 0.5 * dt), &axpy(&im, &k2i, 0.5 * dt));
        let (k4r, k4i) = deriv(&axpy(&re, &k3r, dt), &axpy(&im, &k3i, dt));
        let nr: Vec<f64> = (0..=n).map(|k| re[k] + dt / 6.0 * (k1r[k] + 2.0 * k2r[k] + 2.0 * k3r[k] + k4r[k])).collect();
        let ni: Vec<f64> = (0..=n).map(|k| im[k] + dt / 6.0 * (k1i[k] + 2.0 * k2i[k] + 2.0 * k3i[k] + k4i[k])).collect();
        let e = energy(&nr, &ni);
        if e < prev && step > 0 {
            break;
        }
        re = nr;
        im = ni;
        prev = e;
        step += 1;
    }
    let tau = step as f64 * dt;
    let pmax = (0..=n).map(|k| re[k] * re[k] + im[k] * im[k]).fold(0.0, f64::max);
    let power = prev / tau;
    Charge { n, steps: step, tau, energy: prev, ergotropy: prev - (1.0 - pmax),
             advantage: power / (n as f64 / (std::f64::consts::PI / 2.0)) }
}

pub fn scaling(ns: &[usize]) -> (Vec<Charge>, f64) {
    let rows: Vec<Charge> = ns.iter().map(|&n| charge(n)).collect();
    let xs: Vec<f64> = rows.iter().map(|r| (r.n as f64).ln()).collect();
    let ys: Vec<f64> = rows.iter().map(|r| r.tau.ln()).collect();
    let mx = xs.iter().sum::<f64>() / xs.len() as f64;
    let my = ys.iter().sum::<f64>() / ys.len() as f64;
    let slope = xs.iter().zip(&ys).map(|(x, y)| (x - mx) * (y - my)).sum::<f64>()
        / xs.iter().map(|x| (x - mx).powi(2)).sum::<f64>();
    (rows, -slope)
}

/// 충전 곡선 E(t)/N — t 는 1/g 단위, t_max 까지 같은 RK4 로 (그림용)
pub fn trace(n: usize, t_max: f64, samples: usize) -> Vec<(f64, f64)> {
    let off: Vec<f64> = (0..n).map(|k| (n - k) as f64 * ((k + 1) as f64).sqrt()).collect();
    let norm = (0..=n)
        .map(|k| (if k > 0 { off[k - 1] } else { 0.0 }) + (if k < n { off[k] } else { 0.0 }))
        .fold(f64::MIN, f64::max);
    let dt = 0.02 / norm;
    let h = |r: &[f64], i: &[f64]| -> (Vec<f64>, Vec<f64>) {
        let mut dr = vec![0.0; n + 1];
        let mut di = vec![0.0; n + 1];
        for k in 0..=n {
            let (mut hr, mut hi) = (0.0, 0.0);
            if k > 0 { hr += off[k - 1] * r[k - 1]; hi += off[k - 1] * i[k - 1]; }
            if k < n { hr += off[k] * r[k + 1]; hi += off[k] * i[k + 1]; }
            dr[k] = hi;
            di[k] = -hr;
        }
        (dr, di)
    };
    let axpy = |a: &[f64], b: &[f64], s: f64| -> Vec<f64> { a.iter().zip(b).map(|(x, y)| x + s * y).collect() };
    let mut re = vec![0.0; n + 1];
    let mut im = vec![0.0; n + 1];
    re[0] = 1.0;
    let steps = (t_max / dt).ceil() as usize;
    let every = (steps / samples).max(1);
    let mut out = Vec::new();
    for s in 0..=steps {
        if s % every == 0 {
            let e: f64 = (0..=n).map(|k| k as f64 * (re[k] * re[k] + im[k] * im[k])).sum();
            out.push((s as f64 * dt, e / n as f64));
        }
        let (k1r, k1i) = h(&re, &im);
        let (k2r, k2i) = h(&axpy(&re, &k1r, 0.5 * dt), &axpy(&im, &k1i, 0.5 * dt));
        let (k3r, k3i) = h(&axpy(&re, &k2r, 0.5 * dt), &axpy(&im, &k2i, 0.5 * dt));
        let (k4r, k4i) = h(&axpy(&re, &k3r, dt), &axpy(&im, &k3i, dt));
        for k in 0..=n {
            re[k] += dt / 6.0 * (k1r[k] + 2.0 * k2r[k] + 2.0 * k3r[k] + k4r[k]);
            im[k] += dt / 6.0 * (k1i[k] + 2.0 * k2i[k] + 2.0 * k3i[k] + k4i[k]);
        }
    }
    out
}
