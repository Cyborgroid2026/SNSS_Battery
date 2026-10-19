//! 보로노이 · 프랙탈 단면과 회로망 (spec §5). 보로노이는 반평면 절단(Sutherland–Hodgman)으로 직접 구한다.

use crate::model::{conductivity, thermal_voltage, Battery, FARADAY};
use crate::rng::{round_half_up, SplitMix64};
use std::f64::consts::PI;

pub struct Params {
    pub d: f64,
    pub roughness: f64,
    pub correlation: f64,
    pub ds: f64,
    pub grains: f64,
    pub layers: usize,
    pub width: f64,
    pub seed: u64,
}

pub const BOTTOM: i64 = -1;
pub const TOP: i64 = -2;
pub const SIDE: i64 = -3;

pub struct Cell {
    pub poly: Vec<(f64, f64, i64)>, // 꼭짓점 + (이 꼭짓점→다음 꼭짓점) 변의 이웃 번호
}

pub struct Section {
    pub w: f64,
    pub h: f64,
    pub t: f64,
    pub seeds: Vec<(f64, f64)>,
    pub layer: Vec<i64>,
    pub cells: Vec<Cell>,
}

pub fn seeds(p: &Params, w: f64, h: f64, sp: f64, rng: &mut SplitMix64) -> Vec<(f64, f64)> {
    let mut pts = Vec::new();
    if p.ds >= 1.999 {
        let nx = round_half_up(w / sp).max(2) as usize;
        let nz = round_half_up(h / sp).max(2) as usize;
        for j in 0..nz {
            for i in 0..nx {
                let x = (i as f64 + 0.5) * w / nx as f64 + rng.uniform(-0.42, 0.42) * w / nx as f64;
                let z = (j as f64 + 0.5) * h / nz as f64 + rng.uniform(-0.42, 0.42) * h / nz as f64;
                pts.push((x, z));
            }
        }
        return pts;
    }
    let m = 2f64.powf(p.ds);
    let s0 = sp * 16.0;
    let n0 = round_half_up(w * h / (s0 * s0)).max(1) as usize;
    for _ in 0..n0 {
        let x = rng.uniform(0.0, 1.0) * w;
        let z = rng.uniform(0.0, 1.0) * h;
        pts.push((x, z));
    }
    let mut half = s0 / 2.0;
    for _ in 0..4 {
        let counts: Vec<u32> = (0..pts.len()).map(|_| rng.poisson(m).max(1)).collect();
        let mut next = Vec::new();
        for (k, &(px, pz)) in pts.iter().enumerate() {
            for _ in 0..counts[k] {
                let dx = rng.uniform(-half, half);
                let dz = rng.uniform(-half, half);
                next.push((px + dx, pz + dz));
            }
        }
        pts = next;
        half /= 2.0;
    }
    let mut out = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for (x, z) in pts {
        let x = x.rem_euclid(w);
        let mut z = z.abs();
        if z > h {
            z = 2.0 * h - z;
        }
        let z = z.max(h * 1e-4).min(h * (1.0 - 1e-4));
        let key = ((x / (sp * 1e-3) + 0.5).floor() as i64, (z / (sp * 1e-3) + 0.5).floor() as i64);
        if seen.insert(key) {
            out.push((x, z));
        }
    }
    out
}

pub struct Interfaces {
    amp: Vec<f64>,
    freq: Vec<f64>,
    common: Vec<f64>,
    own: Vec<Vec<f64>>,
    norm: f64,
    t: f64,
    rough: f64,
    wc: f64,
    wi: f64,
}

impl Interfaces {
    pub fn new(p: &Params, w: f64, t: f64, n: usize, fine: f64, rng: &mut SplitMix64) -> Self {
        let gamma: f64 = 1.7;
        let terms = (((w / (fine / 2.0)).ln() / gamma.ln()).floor() as i64 + 1).max(4) as usize;
        let amp: Vec<f64> = (0..terms).map(|k| gamma.powf((p.d - 2.0) * k as f64)).collect();
        let freq: Vec<f64> = (0..terms).map(|k| 2.0 * PI * gamma.powi(k as i32) / w).collect();
        let norm = (amp.iter().map(|a| a * a).sum::<f64>() / 2.0).sqrt();
        let own: Vec<Vec<f64>> = (0..n).map(|_| (0..terms).map(|_| rng.uniform(0.0, 2.0 * PI)).collect()).collect();
        let common: Vec<f64> = (0..terms).map(|_| rng.uniform(0.0, 2.0 * PI)).collect();
        Self { amp, freq, common, own, norm, t, rough: p.roughness,
               wc: p.correlation.sqrt(), wi: (1.0 - p.correlation).sqrt() }
    }
    pub fn height(&self, b: usize, x: f64) -> f64 {
        let base = (b + 1) as f64 * self.t;
        if self.rough == 0.0 {
            return base;
        }
        let (mut a, mut o) = (0.0, 0.0);
        for k in 0..self.amp.len() {
            a += self.amp[k] * (self.freq[k] * x + self.common[k]).cos();
            o += self.amp[k] * (self.freq[k] * x + self.own[b][k]).cos();
        }
        base + self.rough * self.t * (self.wc * a + self.wi * o) / self.norm
    }
    pub fn count(&self) -> usize {
        self.own.len()
    }
}

fn clip(poly: &[(f64, f64, i64)], pi: (f64, f64), pj: (f64, f64), j: i64) -> Vec<(f64, f64, i64)> {
    let (nx, nz) = (pj.0 - pi.0, pj.1 - pi.1);
    let (mx, mz) = (0.5 * (pi.0 + pj.0), 0.5 * (pi.1 + pj.1));
    let side = |x: f64, z: f64| (x - mx) * nx + (z - mz) * nz; // ≤ 0 이면 i 쪽
    let n = poly.len();
    let mut out = Vec::with_capacity(n + 2);
    for k in 0..n {
        let (x0, z0, lab) = poly[k];
        let (x1, z1, _) = poly[(k + 1) % n];
        let (s0, s1) = (side(x0, z0), side(x1, z1));
        let (in0, in1) = (s0 <= 0.0, s1 <= 0.0);
        if in0 {
            out.push((x0, z0, lab));
        }
        if in0 != in1 {
            let r = s0 / (s0 - s1);
            let (ix, iz) = (x0 + r * (x1 - x0), z0 + r * (z1 - z0));
            out.push((ix, iz, if in0 { j } else { lab }));
        }
    }
    out
}

pub fn section(bat: &Battery, p: &Params) -> Section {
    let t = bat.layer_mm;
    let (w, h) = (p.width, p.layers as f64 * t);
    let sp = t / p.grains;
    let mut rng = SplitMix64::new(p.seed);
    let pts = seeds(p, w, h, sp, &mut rng);
    let ifc = Interfaces::new(p, w, t, p.layers - 1, sp, &mut rng);
    let layer: Vec<i64> = pts
        .iter()
        .map(|&(x, z)| (0..ifc.count()).filter(|&b| z > ifc.height(b, x)).count() as i64)
        .collect();
    // 격자 버킷
    let bs = (w.max(h) / (pts.len() as f64).sqrt() * 1.5).max(1e-6);
    let (bx, bz) = ((w / bs).ceil() as i64, (h / bs).ceil() as i64);
    let mut buckets = vec![Vec::new(); (bx * bz) as usize];
    for (i, &(x, z)) in pts.iter().enumerate() {
        let cx = ((x / bs) as i64).min(bx - 1);
        let cz = ((z / bs) as i64).min(bz - 1);
        buckets[(cz * bx + cx) as usize].push(i);
    }
    let mut cells = Vec::with_capacity(pts.len());
    for (i, &pi) in pts.iter().enumerate() {
        let mut poly = vec![(0.0, 0.0, BOTTOM), (w, 0.0, SIDE), (w, h, TOP), (0.0, h, SIDE)];
        let cx = ((pi.0 / bs) as i64).min(bx - 1);
        let cz = ((pi.1 / bs) as i64).min(bz - 1);
        let mut ring = 0i64;
        loop {
            for dz in -ring..=ring {
                for dx in -ring..=ring {
                    if dx.abs() != ring && dz.abs() != ring {
                        continue;
                    }
                    let (gx, gz) = (cx + dx, cz + dz);
                    if gx < 0 || gz < 0 || gx >= bx || gz >= bz {
                        continue;
                    }
                    for &j in &buckets[(gz * bx + gx) as usize] {
                        if j != i {
                            poly = clip(&poly, pi, pts[j], j as i64);
                        }
                    }
                }
            }
            let rmax = poly.iter().map(|&(x, z, _)| ((x - pi.0).powi(2) + (z - pi.1).powi(2)).sqrt()).fold(0.0, f64::max);
            if (ring as f64) * bs >= 2.0 * rmax + bs || ring > bx.max(bz) {
                break;
            }
            ring += 1;
        }
        cells.push(Cell { poly });
    }
    Section { w, h, t, seeds: pts, layer, cells }
}

pub struct NetResult {
    pub n_cells: usize,
    pub n_inner: usize,
    pub v_win: f64,
    pub r_win: f64,
    pub p_loss: f64,
    pub active_len: f64,
    pub defect_len: f64,
    pub mean_nb: f64,
    pub ocv: f64,
    pub r: f64,
    pub leak_ma: f64,
}

struct Edge {
    i: usize,
    j: usize,
    g: f64,
    e: f64,
}

fn cg(diag: &[f64], edges: &[(usize, usize, f64)], b: &[f64]) -> Vec<f64> {
    let n = b.len();
    let matvec = |x: &[f64], y: &mut [f64]| {
        for k in 0..n {
            y[k] = diag[k] * x[k];
        }
        for &(i, j, g) in edges {
            y[i] -= g * x[j];
            y[j] -= g * x[i];
        }
    };
    let mut x = vec![0.0; n];
    let mut r = b.to_vec();
    let mut z: Vec<f64> = r.iter().zip(diag).map(|(a, d)| a / d).collect();
    let mut p = z.clone();
    let mut rz: f64 = r.iter().zip(&z).map(|(a, b)| a * b).sum();
    let bnorm = b.iter().map(|v| v * v).sum::<f64>().sqrt().max(1e-300);
    let mut ap = vec![0.0; n];
    for _ in 0..20 * n + 100 {
        matvec(&p, &mut ap);
        let alpha = rz / p.iter().zip(&ap).map(|(a, b)| a * b).sum::<f64>();
        for k in 0..n {
            x[k] += alpha * p[k];
            r[k] -= alpha * ap[k];
        }
        if r.iter().map(|v| v * v).sum::<f64>().sqrt() / bnorm < 1e-14 {
            break;
        }
        for k in 0..n {
            z[k] = r[k] / diag[k];
        }
        let rz2: f64 = r.iter().zip(&z).map(|(a, b)| a * b).sum();
        let beta = rz2 / rz;
        rz = rz2;
        for k in 0..n {
            p[k] = z[k] + beta * p[k];
        }
    }
    x
}

pub fn network(bat: &Battery, sec: &Section) -> NetResult {
    let s = &bat.stack;
    let n = sec.seeds.len();
    let vt = thermal_voltage(s.temp);
    let ratio = if s.x > 0.0 { (s.c_b() / s.c_a()).ln() } else { 0.0 };
    let (ac, aa) = (s.cem.selectivity(s.c0), s.aem.selectivity(s.c0));
    let (e_c, e_a) = (ac * vt * ratio, aa * vt * ratio);
    let (r_c, r_a) = (s.cem.asr * 100.0, s.aem.asr * 100.0);
    let sig_a = conductivity(s.c_a(), s.temp) / 1000.0;
    let sig_b = conductivity(s.c_b(), s.temp) / 1000.0;
    let sig = |i: usize| if sec.layer[i] % 2 == 0 { sig_a } else { sig_b };
    let mut edges = Vec::new();
    let mut active_len = 0.0;
    let mut defect_len = 0.0;
    let mut nb = vec![0usize; n];
    let mut bottom = Vec::new();
    let mut top = Vec::new();
    for (i, cell) in sec.cells.iter().enumerate() {
        let m = cell.poly.len();
        for k in 0..m {
            let (x0, z0, lab) = cell.poly[k];
            let (x1, z1, _) = cell.poly[(k + 1) % m];
            let len = ((x1 - x0).powi(2) + (z1 - z0).powi(2)).sqrt();
            if lab == BOTTOM || lab == TOP {
                let dist = if lab == BOTTOM { sec.seeds[i].1 } else { sec.h - sec.seeds[i].1 };
                let gc = 1.0 / (dist.max(1e-3) / (sig(i) * len.max(1e-9)) + 1e-3);
                if lab == BOTTOM { bottom.push((i, gc)) } else { top.push((i, gc)) }
                continue;
            }
            if lab < 0 || (lab as usize) <= i || len <= 1e-9 {
                continue;
            }
            let j = lab as usize;
            let d = ((sec.seeds[i].0 - sec.seeds[j].0).powi(2) + (sec.seeds[i].1 - sec.seeds[j].1).powi(2)).sqrt();
            let dl = sec.layer[j] - sec.layer[i];
            let lo = sec.layer[i].min(sec.layer[j]);
            let is_c = lo % 2 == 0;
            let active = dl.abs() == 1;
            let r_wall = if active { if is_c { r_c } else { r_a } } else { (r_c + r_a) / 2.0 };
            let r = r_wall / len + d / 2.0 / (sig(i) * len) + d / 2.0 / (sig(j) * len);
            let e = if active { dl.signum() as f64 * if is_c { e_c } else { e_a } } else { 0.0 };
            if active {
                active_len += len;
            }
            if dl.abs() >= 2 {
                defect_len += len;
            }
            nb[i] += 1;
            nb[j] += 1;
            edges.push(Edge { i, j, g: 1.0 / r, e });
        }
    }
    let total = n + 1;
    let mut diag = vec![0.0; total];
    let mut offd = Vec::new();
    for e in &edges {
        diag[e.i] += e.g;
        diag[e.j] += e.g;
        offd.push((e.i, e.j, e.g));
    }
    for &(i, g) in &bottom {
        diag[i] += g;
    }
    for &(i, g) in &top {
        diag[i] += g;
        diag[n] += g;
        offd.push((i, n, g));
    }
    let mut b = vec![0.0; total];
    for e in &edges {
        b[e.i] -= e.g * e.e;
        b[e.j] += e.g * e.e;
    }
    let phi = cg(&diag, &offd, &b);
    let mut b1 = vec![0.0; total];
    b1[n] = 1.0;
    let r_win = cg(&diag, &offd, &b1)[n];
    let v_win = phi[n];
    let p_loss: f64 = edges.iter().map(|e| e.g * (phi[e.i] + e.e - phi[e.j]).powi(2)).sum();
    let t = sec.t;
    let interior: Vec<usize> = (0..n)
        .filter(|&i| {
            let (x, z) = sec.seeds[i];
            x > 2.0 * t && x < sec.w - 2.0 * t && z > 2.0 * t && z < sec.h - 2.0 * t
        })
        .collect();
    let mean_nb = if interior.is_empty() {
        nb.iter().sum::<usize>() as f64 / n as f64
    } else {
        interior.iter().map(|&i| nb[i]).sum::<usize>() as f64 / interior.len() as f64
    };
    let l = (sec.h / t).round();
    let n_tot = 2.0 * s.n_pairs as f64;
    let depth = sec.w / (s.area_cm2 * 100.0);
    let ocv = v_win * n_tot / (l - 1.0);
    let r = r_win * (n_tot / l) * depth;
    let p_dev = p_loss * (n_tot / l) / depth;
    let leak_ma = if ocv > 0.0 { p_dev / ocv * 1000.0 } else { 0.0 };
    let _ = FARADAY;
    NetResult { n_cells: n, n_inner: edges.len(), v_win, r_win, p_loss, active_len, defect_len, mean_nb, ocv, r, leak_ma }
}
