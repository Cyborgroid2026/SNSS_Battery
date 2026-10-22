//! 빛 조각가 SC-2 — 잉크층 · 405/530 nm 층 노출 (spec/SPEC.md §11, spec/LIGHT.md). Python lightsculpt.py · C# 와 같은 식.

// 고정 상수 (lightsculpt.Photo · Tank · Desktop 기본값)
const EPS_GO: f64 = 15.0; // GO 405 nm 질량 흡광계수 mL·mg⁻¹·cm⁻¹ (상용로그)
const A_SBQ: f64 = 1.5; // 감광 PVA 1 wt% 당 흡광도 /cm
const EC: f64 = 20.0; // 가교 문턱 mJ/cm²
pub const E_RED: f64 = 1000.0; // GO → rGO 누적 노출 mJ/cm²
const OVERCURE: f64 = 0.25;
const EPS_GO_530: f64 = 10.0;
const EPS_EOSIN: f64 = 95000.0; // M⁻¹cm⁻¹
const E_GRAFT: f64 = 300.0;
const GRAFT_TARGET: f64 = 0.8;
const CCC_GO_NACL: f64 = 44.0; // assembly.PURE_GO_NACL_CCC_MM
const CCC_PER_PVA: f64 = 0.15;
const RHO_WATER: f64 = 997.05;
const NACL_RHO_PER_MM: f64 = 0.0405;
const D_NACL: f64 = 1.5e-9;
const K_WATER: f64 = 0.6;
const SALINE_MM: f64 = 154.0;
const TANK_M: f64 = 0.35; // 배양조 안 한 변
const FILL_M: f64 = 0.33;
const WALL_U: f64 = 10.0;
const REFLECT: f64 = 0.02;
const BUILD_MM: f64 = 110.0;
const Z_MOTOR_W: f64 = 3.0 * 0.35;
const INSUL_W_MK: f64 = 0.035;
const INSUL_MM: f64 = 30.0;
const EXHAUST_K: f64 = 5.0;

pub struct Light {
    pub go: f64,
    pub pva: f64,
    pub nacl: f64,
    pub eosin_um: f64,
    pub depth_mm: f64,
    pub irr: f64,
    pub green: f64,
}

/// erfc — |x| < 3 은 erf 급수, 그 밖은 연분수 (Lentz). 둘 다 상대 1e-15 안팎.
pub fn erfc(x: f64) -> f64 {
    if x < 0.0 {
        return 2.0 - erfc(-x);
    }
    if x < 3.0 {
        // erf = 2/√π Σ (−1)ⁿ x^(2n+1) / (n! (2n+1))
        let (mut term, mut sum, mut n) = (x, x, 0.0);
        loop {
            n += 1.0;
            term *= -x * x / n;
            let add = term / (2.0 * n + 1.0);
            sum += add;
            if add.abs() <= 1e-17 * sum.abs() {
                break;
            }
        }
        return 1.0 - 2.0 / std::f64::consts::PI.sqrt() * sum;
    }
    // erfc = e^(−x²)/√π · 1/(x + 1/2/(x + 1/(x + 3/2/(x + …))))
    let tiny = 1e-300;
    let mut f = x;
    let (mut c, mut d) = (x, 0.0);
    for i in 1..300 {
        let a = i as f64 / 2.0;
        d = x + a * d;
        d = if d.abs() < tiny { tiny } else { d };
        c = x + a / c;
        c = if c.abs() < tiny { tiny } else { c };
        d = 1.0 / d;
        let delta = c * d;
        f *= delta;
        if (delta - 1.0).abs() < 1e-16 {
            break;
        }
    }
    (-x * x).exp() / std::f64::consts::PI.sqrt() / f
}

/// erfc 의 역함수 — 뉴턴 (도함수 −2/√π e^(−x²)).
pub fn erfcinv(y: f64) -> f64 {
    let mut x = 0.0;
    for _ in 0..100 {
        let step = (erfc(x) - y) / (2.0 / std::f64::consts::PI.sqrt() * (-x * x).exp());
        x += step;
        if step.abs() < 1e-16 * x.abs().max(1e-300) {
            break;
        }
    }
    x
}

impl Light {
    pub fn dp_mm(&self) -> f64 {
        10.0 / (std::f64::consts::LN_10 * (EPS_GO * self.go + A_SBQ * self.pva))
    }
    pub fn dp_green_mm(&self) -> f64 {
        10.0 / (std::f64::consts::LN_10 * (EPS_GO_530 * self.go + EPS_EOSIN * self.eosin_um * 1e-6))
    }
    pub fn e_graft_target(&self) -> f64 {
        E_GRAFT * (1.0 / (1.0 - GRAFT_TARGET)).ln()
    }
    /// 세포질 기둥 바로 아래 막 칸이 받는 누적량 / E_red (층 = x·Dp)
    pub fn membrane_leak(&self, x: f64) -> f64 {
        let e_mem = EC * ((1.0 + OVERCURE) * x).exp();
        (-x).exp() + e_mem * (1.0 - (-x).exp()) / x / E_RED
    }
    /// 0.5–4 를 351 칸 (numpy linspace 와 같은 i·step + start) 에서 첫 최솟값
    pub fn layer_ratio(&self) -> f64 {
        let step = (4.0 - 0.5) / 350.0;
        let mut best = (f64::INFINITY, 0.5);
        for i in 0..351 {
            let x = if i == 350 { 4.0 } else { i as f64 * step + 0.5 };
            let v = self.membrane_leak(x);
            if v < best.0 {
                best = (v, x);
            }
        }
        best.1
    }
    pub fn layer_mm(&self) -> f64 {
        (self.layer_ratio() * self.dp_mm() * 1000.0).round() / 1000.0
    }
    pub fn e_cure(&self) -> f64 {
        EC * ((1.0 + OVERCURE) * self.layer_mm() / self.dp_mm()).exp()
    }
    pub fn ccc_mm(&self) -> f64 {
        CCC_GO_NACL * (1.0 + CCC_PER_PVA * self.pva)
    }
    pub fn ink_density(&self) -> f64 {
        RHO_WATER + self.go * (1.0 - RHO_WATER / 1800.0) + 10.0 * self.pva * (1.0 - RHO_WATER / 1270.0) + NACL_RHO_PER_MM * self.nacl
    }
    pub fn ink_life_h(&self) -> f64 {
        let frac = (0.8 * self.ccc_mm() - self.nacl) / (SALINE_MM - self.nacl);
        let x = erfcinv(2.0 * frac);
        let d = self.depth_mm / 1000.0;
        (d / (2.0 * x)).powi(2) / D_NACL / 3600.0
    }
    pub fn surface_rise_k(&self) -> f64 {
        let q = self.irr.max(self.green) * 10.0 * (1.0 - REFLECT);
        q / (K_WATER / (self.depth_mm / 1000.0) + 10.0)
    }
    pub fn heat_rise_k(&self) -> f64 {
        let light = self.irr * 10.0 * (1.0 - REFLECT) * BUILD_MM * BUILD_MM / 1e6;
        let pc = INSUL_W_MK / (INSUL_MM / 1000.0) * TANK_M * TANK_M * EXHAUST_K;
        let loss = WALL_U * (2.0 * (TANK_M + TANK_M) * FILL_M + TANK_M * TANK_M);
        (light + Z_MOTOR_W + pc) / loss
    }
    pub fn build_time_h(&self, height_mm: f64) -> f64 {
        E_RED * height_mm / (self.dp_mm() * self.irr) / 3600.0
    }
    /// 한 기둥 (아래 → 위): 노출 E · 누적 D. lightsculpt._columns 와 같은 위층부터의 풀이.
    pub fn columns(floor: &[f64], target: &[f64], x: f64) -> (Vec<f64>, Vec<f64>) {
        let r = (-x).exp();
        let c = (1.0 - r) / x;
        let n = floor.len();
        let (mut e, mut d) = (vec![0.0; n], vec![0.0; n]);
        let mut q = 0.0;
        for k in (0..n).rev() {
            let want = if target[k] > 0.0 { (target[k] - c * q) / c } else { 0.0 };
            e[k] = floor[k].max(want);
            d[k] = c * (e[k] + q);
            q = r * (e[k] + q);
        }
        (e, d)
    }
    /// 기둥 글자 (P · N · M · 0) → 405 nm 와 530 nm 의 (E, D, G, Dg)
    pub fn column(&self, col: &str) -> [Vec<f64>; 4] {
        let ch: Vec<char> = col.chars().collect();
        let h = self.layer_mm();
        let (cure, eg) = (self.e_cure(), self.e_graft_target());
        let floor: Vec<f64> = ch.iter().map(|&m| if m != '0' { cure } else { 0.0 }).collect();
        let tgt: Vec<f64> = ch.iter().map(|&m| if m == 'P' || m == 'N' { E_RED } else { 0.0 }).collect();
        let zero = vec![0.0; ch.len()];
        let gt: Vec<f64> = ch.iter().map(|&m| if m == 'P' { eg } else { 0.0 }).collect();
        let (e, d) = Self::columns(&floor, &tgt, h / self.dp_mm());
        let (g, dg) = Self::columns(&zero, &gt, h / self.dp_green_mm());
        [e, d, g, dg]
    }
}
