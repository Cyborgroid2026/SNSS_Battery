//! snss — SNSS 생리식염수 결정 배터리 독립 구현 (Rust)
//!
//!   cargo run --release -- crosscheck ../spec/cases.json   # 기준 사례 계산 → JSON (Python 이 비교)
//!   cargo run --release -- recipe ../spec/cases.json       # 레시피 재료량 → JSON
//!   cargo run --release -- render <출력 폴더>               # SVG 그림 (보로노이 단면, LED 7일, 전력 수지)

mod json;
mod metab;
mod model;
mod quantum;
mod recipe;
mod rng;
mod svg;
mod tess;

use json::{esc, num, Json};
use metab::{best_parallel, operating, simulate, Bulb, Led, Load, Metabolism};
use model::{build, Case};
use tess::{network, section, Params};

fn case_from(j: &Json) -> (Case, Params) {
    let f = j.get("fractal").expect("fractal");
    (
        Case {
            bottle_ml: j.num("bottle_ml"), bottle_d: j.num("bottle_d_mm"), nacl: j.num("nacl_wt"), temp: j.num("temp_c"),
            go: j.num("go_mg_ml"), layer: j.num("layer_mm"), ratio: j.num("ratio"), shrink: j.num("shrink"),
            surface_go: j.num("surface_go"),
        },
        Params {
            d: f.num("D"), roughness: f.num("roughness"), correlation: f.num("correlation"), ds: f.num("Ds"),
            grains: f.num("grains"), layers: f.num("window_layers") as usize, width: f.num("window_mm"),
            seed: f.num("seed") as u64,
        },
    )
}

fn crosscheck(path: &str) {
    let spec = json::parse(&std::fs::read_to_string(path).expect("cases.json 읽기"));
    let cases = match spec.get("cases") {
        Some(Json::Arr(a)) => a.clone(),
        _ => panic!("cases 없음"),
    };
    let mut out = Vec::new();
    for c in &cases {
        let (case, prm) = case_from(c);
        let bat = build(&case);
        let s = &bat.stack;
        let sec = section(&bat, &prm);
        let net = network(&bat, &sec);
        let mut f: Vec<(&str, String)> = vec![
            ("n_pairs", s.n_pairs.to_string()), ("c0", num(s.c0)), ("ocv_v", num(s.ocv())),
            ("r_int_ohm", num(s.r_int())), ("capacity_c", num(s.capacity_c())), ("contact_f", num(s.capacitance())),
            ("n_cells", net.n_cells.to_string()), ("n_inner_ridges", net.n_inner.to_string()),
            ("v_oc_window", num(net.v_win)), ("r_window", num(net.r_win)), ("p_loss_window", num(net.p_loss)),
            ("active_length", num(net.active_len)), ("defect_length", num(net.defect_len)),
            ("mean_neighbors", num(net.mean_nb)), ("net_ocv_v", num(net.ocv)), ("net_r_ohm", num(net.r)),
            ("net_leak_ma", num(net.leak_ma)),
        ];
        if c.flag("lighting") {
            let met = Metabolism::default();
            let mut b2 = bat.clone();
            met.attach(&mut b2);
            f.push(("light_pump_a", num(met.light_pump(&b2))));
            f.push(("fuel_pump_a", num(met.fuel_pump(&b2))));
            f.push(("evap_emf_v", num(met.evap_emf(&b2))));
            let led = simulate(&bat, &met, &Led, 168.0, 60.0, 1, 0);
            f.push(("led_first_off_h", num(led.first_off_h.unwrap_or(-1.0))));
            f.push(("led_on_fraction", num(led.on_fraction)));
            f.push(("led_current_end_a", num(led.last_i)));
            let (k, _) = best_parallel(&bat, &met, &Bulb);
            f.push(("bulb_best_k", k.to_string()));
            let kf = k as f64;
            let i0 = operating(b2.stack.ocv() / kf, b2.stack.r_int() / (kf * kf), &Bulb);
            f.push(("bulb_peak_w", num(i0 * Bulb.voltage(i0))));
            let bulb = simulate(&bat, &met, &Bulb, 2.0, 2.0, k, 0);
            f.push(("bulb_glow_min", num(bulb.first_off_h.map(|h| h * 60.0).unwrap_or(-1.0))));
        }
        let body: Vec<String> = f.iter().map(|(k, v)| format!("{}: {}", esc(k), v)).collect();
        out.push(format!("{}: {{{}}}", esc(&c.str("name")), body.join(", ")));
    }
    println!("{{{}}}", out.join(",\n"));
}

fn recipes(path: &str) {
    let spec = json::parse(&std::fs::read_to_string(path).expect("cases.json 읽기"));
    let list = match spec.get("recipes") {
        Some(Json::Arr(a)) => a.clone(),
        _ => Vec::new(),
    };
    let out: Vec<String> = list
        .iter()
        .map(|j| {
            let body: Vec<String> = recipe::Recipe::from(j)
                .values()
                .iter()
                .map(|(k, v, int)| format!("{}: {}", esc(k), if *int { (*v as i64).to_string() } else { num(*v) }))
                .collect();
            format!("{}: {{{}}}", esc(&j.str("name")), body.join(", "))
        })
        .collect();
    println!("{{{}}}", out.join(",\n"));
}

fn quantum_json() {
    let (rows, a) = quantum::scaling(&[1, 2, 4, 8, 16, 32, 64, 128]);
    let body: Vec<String> = rows
        .iter()
        .map(|r| format!("{}: {{\"steps\": {}, \"tau\": {}, \"energy\": {}, \"ergotropy\": {}, \"advantage\": {}}}",
                         esc(&r.n.to_string()), r.steps, num(r.tau), num(r.energy), num(r.ergotropy), num(r.advantage)))
        .collect();
    println!("{{\"exponent\": {}, \"rows\": {{{}}}}}", num(a), body.join(", "));
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("crosscheck") => crosscheck(args.get(2).map(String::as_str).unwrap_or("../spec/cases.json")),
        Some("quantum") => quantum_json(),
        Some("recipe") => recipes(args.get(2).map(String::as_str).unwrap_or("../spec/cases.json")),
        Some("render") => svg::render_all(args.get(2).map(String::as_str).unwrap_or("svg_out")),
        _ => eprintln!("사용법: snss crosscheck <cases.json> | recipe <cases.json> | quantum | render <폴더>"),
    }
}
