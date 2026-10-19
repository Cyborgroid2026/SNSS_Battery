//! 식염수 · 막 · 층 스택 · 병 (spec §2–4)

pub const FARADAY: f64 = 96485.33212;
pub const GAS: f64 = 8.314462618;

const TABLE: [(f64, f64); 13] = [
    (0.0, 0.0), (0.001, 0.1237), (0.01, 1.185), (0.05, 5.55), (0.1, 10.67), (0.154, 15.6), (0.5, 47.0),
    (1.0, 85.8), (2.0, 145.0), (3.0, 187.0), (4.0, 213.0), (5.0, 222.0), (6.1, 225.0),
];

pub fn conductivity(c: f64, t: f64) -> f64 {
    let c = c.max(0.0);
    let k25 = if c <= TABLE[0].0 {
        TABLE[0].1
    } else if c >= TABLE[12].0 {
        TABLE[12].1
    } else {
        let mut i = 1;
        while TABLE[i].0 < c {
            i += 1;
        }
        let (x0, y0) = TABLE[i - 1];
        let (x1, y1) = TABLE[i];
        y0 + (y1 - y0) * (c - x0) / (x1 - x0)
    };
    (k25 * 0.1 * (1.0 + 0.0212 * (t - 25.0))).max(5.5e-6)
}

pub fn molarity(wt: f64) -> f64 {
    let rho = 0.997 + 0.0071 * wt;
    (wt / 100.0 * rho * 1000.0 / 58.44).min(6.1)
}

pub fn thermal_voltage(t: f64) -> f64 {
    GAS * (t + 273.15) / FARADAY
}

#[derive(Clone, Copy)]
pub struct Membrane {
    pub alpha0: f64,
    pub half: f64,
    pub asr: f64, // Ω·cm²
    pub perm: f64,
    pub thick_um: f64,
}

impl Membrane {
    pub fn selectivity(&self, c: f64) -> f64 {
        self.alpha0 / (1.0 + c / self.half)
    }
}

pub const GO_LC: Membrane = Membrane { alpha0: 0.85, half: 0.30, asr: 5.0, perm: 2e-11, thick_um: 5.0 };
pub const GO_PDDA: Membrane = Membrane { alpha0: 0.80, half: 0.30, asr: 6.0, perm: 2e-11, thick_um: 8.0 };

#[derive(Clone)]
pub struct Stack {
    pub n_pairs: usize,
    pub temp: f64,
    pub c0: f64,
    pub area_cm2: f64,
    pub t_mm: f64,
    pub cem: Membrane,
    pub aem: Membrane,
    pub contact_mg: f64,
    pub x: f64,
    pub q: f64,
    pub faradaic: bool,
    pub contact_asr: f64,
    pub extra_emf: f64,
}

impl Stack {
    pub fn volume_l(&self) -> f64 {
        self.area_cm2 * self.t_mm * 100.0 * 1e-6
    }
    pub fn max_shift(&self) -> f64 {
        self.c0 - 0.002
    }
    pub fn c_a(&self) -> f64 {
        self.c0 - self.x
    }
    pub fn c_b(&self) -> f64 {
        self.c0 + self.x
    }
    pub fn eta(&self) -> f64 {
        0.5 * (self.cem.selectivity(self.c0) + self.aem.selectivity(self.c0))
    }
    pub fn capacitance(&self) -> f64 {
        self.contact_mg * 1e-3 * 150.0
    }
    pub fn capacity_c(&self) -> f64 {
        let ionic = self.max_shift() * self.volume_l() * FARADAY / self.eta();
        ionic.min(self.capacitance() * 0.6)
    }
    pub fn pair_emf(&self) -> f64 {
        let a = self.cem.selectivity(self.c0) + self.aem.selectivity(self.c0);
        a * thermal_voltage(self.temp) * (self.c_b() / self.c_a()).ln()
    }
    pub fn electrode_v(&self) -> f64 {
        if self.faradaic { 0.0 } else { self.q / self.capacitance() }
    }
    pub fn ocv(&self) -> f64 {
        self.n_pairs as f64 * self.pair_emf() + 2.0 * self.electrode_v() + self.extra_emf
    }
    pub fn pair_r(&self) -> f64 {
        let a_m2 = self.area_cm2 * 1e-4;
        let t_m = self.t_mm * 1e-3;
        (self.cem.asr + self.aem.asr) / self.area_cm2
            + t_m / (conductivity(self.c_a(), self.temp) * a_m2)
            + t_m / (conductivity(self.c_b(), self.temp) * a_m2)
    }
    pub fn r_int(&self) -> f64 {
        let mut r = self.n_pairs as f64 * self.pair_r() + 0.2;
        if self.faradaic {
            r += 2.0 * self.contact_asr / self.area_cm2;
        }
        r
    }
    pub fn step(&mut self, current: f64, dt: f64, pump: f64) {
        let v = self.volume_l();
        let mut dx = -self.eta() * current * dt / (FARADAY * v);
        dx += pump * dt / (FARADAY * v);
        let flux = (self.cem.perm + self.aem.perm) * self.area_cm2 * 1e-4 * (self.c_b() - self.c_a()) * 1000.0;
        dx -= flux * dt / v;
        let m = self.max_shift();
        self.x = (self.x + dx).max(-m).min(m);
        if !self.faradaic {
            self.q -= current * dt;
        }
    }
}

#[derive(Clone)]
pub struct Battery {
    pub stack: Stack,
    pub gel_d: f64,
    pub gel_h: f64,
    pub layer_mm: f64,
    pub go_mg: f64,
}

pub struct Case {
    pub bottle_ml: f64,
    pub bottle_d: f64,
    pub nacl: f64,
    pub temp: f64,
    pub go: f64,
    pub layer: f64,
    pub ratio: f64,
    pub shrink: f64,
    pub surface_go: f64,
}

pub fn build(c: &Case) -> Battery {
    let di = c.bottle_d - 1.6;
    let area_in = std::f64::consts::PI * (di / 20.0).powi(2);
    let fill_h = c.bottle_ml / area_in * 10.0;
    let gel_d = di * (1.0 - c.shrink);
    let gel_h = fill_h * (1.0 - c.shrink);
    let ag = std::f64::consts::PI * (gel_d / 20.0).powi(2);
    let pair = 2.0 * c.layer + (GO_LC.thick_um + GO_PDDA.thick_um) / 1000.0;
    let n = (gel_h / pair + 1e-9).floor() as usize; // spec §4: 딱 맞는 높이의 반올림 오차 보정
    let go_mg = c.go * c.bottle_ml;
    let surf = if c.surface_go > 0.0 { c.surface_go } else { go_mg / (2.0 * n as f64) / ag };
    let c0 = molarity(c.nacl);
    let mut s = Stack {
        n_pairs: n, temp: c.temp, c0, area_cm2: ag, t_mm: c.layer, cem: GO_LC, aem: GO_PDDA,
        contact_mg: surf * ag, x: 0.0, q: 0.0, faradaic: false, contact_asr: 0.0, extra_emf: 0.0,
    };
    s.x = (c0 * (c.ratio - 1.0) / (c.ratio + 1.0)).min(s.max_shift());
    Battery { stack: s, gel_d, gel_h, layer_mm: c.layer, go_mg }
}
