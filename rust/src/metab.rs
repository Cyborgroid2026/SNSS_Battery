//! 대사(에너지원) · 부하 · 시뮬레이션 (spec §6–8)

use crate::model::{thermal_voltage, Battery, FARADAY};
use std::f64::consts::PI;

const PLANCK: f64 = 6.62607015e-34;
const C_LIGHT: f64 = 2.99792458e8;
const E_CHARGE: f64 = 1.602176634e-19;

#[derive(Clone)]
pub struct Metabolism {
    pub irradiance: f64,
    pub wavelength: f64,
    pub qe: f64,
    pub penetration: f64,
    pub day_hours: f64,
    pub fuel_mm: f64,
    pub ions: f64,
    pub rate: f64,
    pub asr: f64,
    pub remaining: f64,
    pub evap_mm_h: f64,
    pub salt_d: f64,
}

impl Default for Metabolism {
    fn default() -> Self {
        Self { irradiance: 10.0, wavelength: 405.0, qe: 1e-3, penetration: 1.0, day_hours: 12.0,
               fuel_mm: 50.0, ions: 1.0, rate: 0.3, asr: 30.0, remaining: 1.0, evap_mm_h: 0.2, salt_d: 1.5e-9 }
    }
}

impl Metabolism {
    pub fn light_pump(&self, b: &Battery) -> f64 {
        let photon = PLANCK * C_LIGHT / (self.wavelength * 1e-9);
        let flux = self.irradiance * 1e-3 / photon;
        let area = PI * b.gel_d / 10.0 * self.penetration.min(b.gel_d / 2.0) / 10.0;
        E_CHARGE * flux * self.qe * area
    }
    pub fn lit(&self, t: f64) -> bool {
        (t / 3600.0) % 24.0 < self.day_hours
    }
    pub fn fuel_pump(&self, b: &Battery) -> f64 {
        if self.remaining <= 0.0 {
            return 0.0;
        }
        let mol0 = self.fuel_mm * 1e-3 * b.stack.volume_l();
        self.ions * FARADAY * self.rate / 86400.0 * mol0 * self.remaining
    }
    pub fn evap_emf(&self, b: &Battery) -> f64 {
        let s = &b.stack;
        let v = self.evap_mm_h * 1e-3 / 3600.0;
        let pe = v * b.gel_h * 1e-3 / self.salt_d;
        let ratio = pe.min(50.0).exp().min(6.1 / s.c0);
        0.5 * (s.cem.selectivity(s.c0) - s.aem.selectivity(s.c0)) * thermal_voltage(s.temp) * ratio.ln()
    }
    pub fn attach(&self, b: &mut Battery) {
        let e = self.evap_emf(b);
        b.stack.faradaic = true;
        b.stack.contact_asr = self.asr;
        b.stack.extra_emf = e;
    }
    pub fn pump(&self, b: &Battery, t: f64) -> f64 {
        (if self.lit(t) { self.light_pump(b) } else { 0.0 }) + self.fuel_pump(b)
    }
    pub fn consume(&mut self, dt: f64) {
        self.remaining *= (-self.rate * dt / 86400.0).exp();
    }
}

pub trait Load {
    fn voltage(&self, i: f64) -> f64;
    fn lit(&self, i: f64) -> bool;
}

pub struct Led;

impl Load for Led {
    fn voltage(&self, i: f64) -> f64 {
        let nvt: f64 = 2.0 * 0.025693;
        let is = 1e-3 / (1.85 / nvt).exp();
        nvt * (i.max(0.0) / is + 1.0).ln() + 470.0 * i
    }
    fn lit(&self, i: f64) -> bool {
        i >= 20e-6
    }
}

pub struct Bulb;

impl Bulb {
    pub fn resistance(&self, i: f64) -> f64 {
        let r_hot = 2.5 / 0.3;
        let mut r = r_hot * 0.1;
        for _ in 0..30 {
            let p = i * i * r;
            r = r_hot * (0.1 + 0.9 * (p / 0.75).min(1.5).powf(0.6));
        }
        r
    }
}

impl Load for Bulb {
    fn voltage(&self, i: f64) -> f64 {
        i * self.resistance(i)
    }
    fn lit(&self, i: f64) -> bool {
        i * self.voltage(i) >= 0.15 * 0.75
    }
}

pub fn operating(ocv: f64, r: f64, load: &dyn Load) -> f64 {
    if ocv <= 0.0 {
        return 0.0;
    }
    let (mut lo, mut hi) = (0.0, ocv / r);
    for _ in 0..100 {
        let mid = 0.5 * (lo + hi);
        if ocv - mid * r - load.voltage(mid) > 0.0 {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    0.5 * (lo + hi)
}

pub struct Run {
    pub first_off_h: Option<f64>,
    pub on_fraction: f64,
    pub last_i: f64,
    pub trace: Vec<(f64, f64, bool)>, // (h, I, 빛)
}

pub fn simulate(bat: &Battery, met: &Metabolism, load: &dyn Load, hours: f64, dt: f64, k: usize, trace_every: usize) -> Run {
    let mut b = bat.clone();
    let mut m = met.clone();
    m.attach(&mut b);
    let kf = k as f64;
    let steps = (hours * 3600.0 / dt) as usize;
    let (mut first, mut on, mut last) = (None, 0usize, 0.0);
    let mut trace = Vec::new();
    for n in 0..=steps {
        let t = n as f64 * dt;
        let i = operating(b.stack.ocv() / kf, b.stack.r_int() / (kf * kf), load);
        if load.lit(i) {
            on += 1;
        } else if first.is_none() {
            first = Some(t / 3600.0);
        }
        if trace_every > 0 && n % trace_every == 0 {
            trace.push((t / 3600.0, i, m.lit(t)));
        }
        let pump = m.pump(&b, t);
        b.stack.step(i / kf, dt, pump);
        m.consume(dt);
        last = i;
    }
    Run { first_off_h: first, on_fraction: on as f64 / (steps + 1) as f64, last_i: last, trace }
}

pub fn best_parallel(bat: &Battery, met: &Metabolism, load: &dyn Load) -> (usize, f64) {
    let mut b = bat.clone();
    met.attach(&mut b);
    let (mut best, mut best_p) = (1usize, -1.0f64);
    for k in 1..=64usize.min(b.stack.n_pairs) {
        let kf = k as f64;
        let i = operating(b.stack.ocv() / kf, b.stack.r_int() / (kf * kf), load);
        let p = i * load.voltage(i);
        if p > best_p {
            best = k;
            best_p = p;
        }
    }
    (best, best_p)
}
