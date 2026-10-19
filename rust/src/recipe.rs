//! 레시피 재료량 + 결정 예측 (spec §10, Python snss_battery/recipe.py 와 독립 구현)

use crate::json::Json;
use crate::metab::{operating, Led};
use crate::model::{build, Case};
use std::f64::consts::PI;

const NACL_MW: f64 = 58.44;
const SALINE_M: f64 = 0.1545;
const GO_DISP: f64 = 4.0;

pub struct Recipe {
    pub pairs: f64,
    pub layer: f64,
    pub dilution: f64,
    pub inner_d: f64,
    pub go: f64,
    pub wall: f64,
    pub aem_go: f64,
    pub pdda: f64,
    pub spare: f64,
}

impl Recipe {
    pub fn from(j: &Json) -> Self {
        Recipe {
            pairs: j.num("pairs"), layer: j.num("layer_mm"), dilution: j.num("dilution"),
            inner_d: j.num("bottle_inner_mm"), go: j.num("go_layer_mg_ml"), wall: j.num("wall_ml"),
            aem_go: j.num("aem_go_mg_ml"), pdda: j.num("aem_pdda_wt"), spare: j.num("spare"),
        }
    }

    /// (키, 값, 정수 여부) — Python 과 같은 순서·이름
    pub fn values(&self) -> Vec<(&'static str, f64, bool)> {
        let ca = SALINE_M / self.dilution;
        let cb = 2.0 * SALINE_M - ca;
        let area = PI * (self.inner_d / 20.0).powi(2);
        let layer_ml = area * self.layer / 10.0;
        let mix = layer_ml * self.pairs * self.spare;
        let height = self.pairs * (2.0 * self.layer + 0.013);
        let half = mix / 2.0;
        let stock = 2.0 * half;
        let pva = stock * 0.10;
        let go_stock = stock * (2.0 * self.go) / GO_DISP;
        let saline_a = half * (2.0 * ca) / SALINE_M;
        let nacl = (2.0 * cb - SALINE_M) * half / 1000.0 * NACL_MW;
        let walls = self.pairs * self.wall * self.spare;
        let cem_go = walls * 0.9;
        let aem_go = walls * self.aem_go / GO_DISP;
        let pdda = walls * self.pdda / 20.0;

        let bat = build(&Case {
            bottle_ml: area * height / 10.0, bottle_d: self.inner_d + 1.6, nacl: 0.9, temp: 25.0, go: self.go,
            layer: self.layer, ratio: cb / ca, shrink: 0.0, surface_go: 0.0,
        });
        let s = &bat.stack;
        let i = operating(s.ocv(), s.r_int(), &Led);
        vec![
            ("c_dilute_m", ca, false), ("c_conc_m", cb, false), ("ratio", cb / ca, false), ("area_cm2", area, false),
            ("layer_ml", layer_ml, false), ("mix_ml", mix, false), ("height_mm", height, false),
            ("steps", 4.0 * self.pairs, true), ("half_ml", half, false), ("stock_ml", stock, false), ("pva_g", pva, false),
            ("go_stock_ml", go_stock, false), ("water_stock_ml", stock - pva - go_stock, false),
            ("saline_a_ml", saline_a, false), ("water_a_ml", half - saline_a, false), ("extra_nacl_g", nacl, false),
            ("wall_ml", walls, false), ("cem_go_ml", cem_go, false), ("cem_pva_ml", walls - cem_go, false),
            ("aem_go_ml", aem_go, false), ("pdda_ml", pdda, false), ("aem_water_ml", walls - aem_go - pdda, false),
            ("buy_saline_ml", saline_a + half, false), ("buy_go_ml", go_stock + cem_go + aem_go, false),
            ("buy_pva_g", pva + (walls - cem_go) * 0.10, false), ("n_pairs", s.n_pairs as f64, true),
            ("ocv_v", s.ocv(), false), ("r_int_ohm", s.r_int(), false), ("led_ma", i * 1000.0, false),
        ]
    }
}
