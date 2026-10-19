//! SVG 렌더링 — 웹 뷰어용 그림 (matplotlib 대신 직접 디자인한 벡터 그래픽)

use crate::metab::{best_parallel, simulate, Bulb, Led, Load, Metabolism};
use crate::model::{build, Case};
use crate::quantum;
use crate::tess::{network, section, Params, BOTTOM, SIDE, TOP};
use std::fmt::Write as _;

const FONT: &str = "Pretendard, 'Noto Sans KR', NanumGothic, 'Apple SD Gothic Neo', sans-serif";
const INK: &str = "#14202b";
const MUTED: &str = "#6b7a89";
const GRID: &str = "#e6ebf0";
const DILUTE: &str = "#cfe6f7";
const CONC: &str = "#2f6db5";
const CEM: &str = "#f28c38";
const AEM: &str = "#23a06b";
const DEFECT: &str = "#e0344b";

fn head(w: f64, h: f64, title: &str, sub: &str) -> String {
    let mut s = String::new();
    let _ = write!(s, r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="{FONT}">
<defs><filter id="sh" x="-5%" y="-5%" width="110%" height="115%"><feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#0b2540" flood-opacity="0.12"/></filter></defs>
<rect x="8" y="8" width="{}" height="{}" rx="18" fill="#ffffff" filter="url(#sh)"/>
<text x="36" y="52" font-size="22" font-weight="700" fill="{INK}">{title}</text>
<text x="36" y="78" font-size="14" fill="{MUTED}">{sub}</text>
"##, w - 16.0, h - 16.0);
    s
}

fn default_case() -> Case {
    Case { bottle_ml: 500.0, bottle_d: 72.0, nacl: 0.9, temp: 25.0, go: 5.0, layer: 0.5, ratio: 20.0, shrink: 0.0, surface_go: 0.0 }
}

pub fn voronoi_svg(rough: f64, corr: f64, d: f64, ds: f64, seed: u64, title: &str) -> String {
    let bat = build(&default_case());
    let p = Params { d, roughness: rough, correlation: corr, ds, grains: 3.0, layers: 12, width: 12.0, seed };
    let sec = section(&bat, &p);
    let net = network(&bat, &sec);
    let (w, h) = (1200.0, 760.0);
    let (ox, oy, sc) = (40.0, 110.0, 1120.0 / sec.w);
    let (x, y) = (|v: f64| ox + v * sc, |v: f64| oy + (sec.h - v) * sc);
    let mut s = head(w, h, title, &format!(
        "결정핵 {}개의 보로노이 분할 · 층 경계 프랙탈 D={d:.2}, 거칠기 {rough:.2}t, 상관도 {corr:.2}, 결정핵 분포 D={ds:.2}", sec.seeds.len()));
    let _ = write!(s, r#"<clipPath id="win"><rect x="{ox}" y="{oy}" width="{}" height="{}" rx="10"/></clipPath><g clip-path="url(#win)">"#,
                   sec.w * sc, sec.h * sc);
    for (i, cell) in sec.cells.iter().enumerate() {
        let pts: Vec<String> = cell.poly.iter().map(|&(a, b, _)| format!("{:.1},{:.1}", x(a), y(b))).collect();
        let fill = if sec.layer[i] % 2 == 0 { DILUTE } else { CONC };
        let _ = write!(s, r##"<polygon points="{}" fill="{fill}" stroke="#ffffff" stroke-opacity="0.55" stroke-width="0.8"/>"##, pts.join(" "));
    }
    // 층 사이 벽 강조
    for (i, cell) in sec.cells.iter().enumerate() {
        let m = cell.poly.len();
        for k in 0..m {
            let (x0, z0, lab) = cell.poly[k];
            let (x1, z1, _) = cell.poly[(k + 1) % m];
            if lab < 0 || (lab as usize) <= i {
                continue;
            }
            let dl = (sec.layer[lab as usize] - sec.layer[i]).abs();
            if dl == 0 {
                continue;
            }
            let lo = sec.layer[i].min(sec.layer[lab as usize]);
            let (col, wid) = if dl >= 2 { (DEFECT, 4.0) } else if lo % 2 == 0 { (CEM, 2.6) } else { (AEM, 2.6) };
            let _ = write!(s, r#"<line x1="{:.1}" y1="{:.1}" x2="{:.1}" y2="{:.1}" stroke="{col}" stroke-width="{wid}" stroke-linecap="round"/>"#,
                           x(x0), y(z0), x(x1), y(z1));
        }
    }
    for &(a, b) in &sec.seeds {
        let _ = write!(s, r#"<circle cx="{:.1}" cy="{:.1}" r="1.3" fill="{INK}" fill-opacity="0.55"/>"#, x(a), y(b));
    }
    let _ = write!(s, "</g>");
    let _ = (BOTTOM, TOP, SIDE);
    // 스케일 막대 + 범례 + 수치
    let yb = oy + sec.h * sc + 34.0;
    let _ = write!(s, r#"<line x1="{ox}" y1="{yb}" x2="{}" y2="{yb}" stroke="{INK}" stroke-width="3"/><text x="{}" y="{}" font-size="13" fill="{INK}">1 mm</text>"#,
                   ox + sc, ox + sc + 10.0, yb + 5.0);
    let items = [(DILUTE, "묽은 도메인", false), (CONC, "진한 도메인", false), (CEM, "양이온 선택 벽", true),
                 (AEM, "음이온 선택 벽", true), (DEFECT, "결함 벽 (층 건너뜀 → 단락)", true)];
    let mut lx = ox + 160.0;
    for (col, label, line) in items {
        if line {
            let _ = write!(s, r#"<line x1="{lx}" y1="{}" x2="{}" y2="{}" stroke="{col}" stroke-width="4" stroke-linecap="round"/>"#, yb, lx + 22.0, yb);
        } else {
            let _ = write!(s, r#"<rect x="{lx}" y="{}" width="22" height="14" rx="4" fill="{col}"/>"#, yb - 7.0);
        }
        let _ = write!(s, r#"<text x="{}" y="{}" font-size="13" fill="{INK}">{label}</text>"#, lx + 30.0, yb + 5.0);
        lx += 30.0 + label.chars().count() as f64 * 13.5 + 26.0;
    }
    let _ = write!(s, r#"<text x="{ox}" y="{}" font-size="14" fill="{MUTED}">회로망 계산: 개방전압 {:.2} V · 내부저항 {:.0} Ω · 내부 누설 {:.3} mA · 결함 벽 {:.1} % · 평균 이웃 {:.2}</text>"#,
                   yb + 34.0, net.ocv, net.r, net.leak_ma, 100.0 * net.defect_len / (net.active_len + net.defect_len).max(1e-9), net.mean_nb);
    s.push_str("</svg>");
    s
}

fn log_y(v: f64, lo: f64, hi: f64, top: f64, bottom: f64) -> f64 {
    let t = (v.max(lo).ln() - lo.ln()) / (hi.ln() - lo.ln());
    bottom - t * (bottom - top)
}

pub fn led_week_svg() -> String {
    let bat = build(&default_case());
    let met = Metabolism::default();
    let run = simulate(&bat, &met, &Led, 168.0, 60.0, 1, 10);
    let (w, h) = (1200.0, 560.0);
    let (l, r, t, b) = (100.0, 1150.0, 120.0, 470.0);
    let (lo, hi) = (1e-6, 3e-2);
    let x = |hh: f64| l + hh / 168.0 * (r - l);
    let y = |i: f64| log_y(i, lo, hi, t, b);
    let off = run.first_off_h;
    let mut s = head(w, h, "LED (+470 Ω 보호 저항) 를 1주일 연결했을 때", &format!(
        "빛(낮 12시간) + 내장 연료가 결정 안에서 농도차를 다시 만듦 · {}",
        match off { Some(o) => format!("{o:.0}시간 뒤 처음 꺼짐 (연료 감소)"), None => "1주일 내내 켜짐".into() }));
    for d in 0..7 {
        let _ = write!(s, r##"<rect x="{:.1}" y="{t}" width="{:.1}" height="{}" fill="#fff6db"/>"##, x(d as f64 * 24.0), x(12.0) - x(0.0), b - t);
    }
    for (v, lab) in [(1e-6, "1 µA"), (1e-5, "10 µA"), (1e-4, "100 µA"), (1e-3, "1 mA"), (1e-2, "10 mA")] {
        let _ = write!(s, r#"<line x1="{l}" x2="{r}" y1="{0:.1}" y2="{0:.1}" stroke="{GRID}"/><text x="{1}" y="{2:.1}" font-size="13" fill="{MUTED}" text-anchor="end">{lab}</text>"#,
                       y(v), l - 10.0, y(v) + 4.0);
    }
    for d in 0..=7 {
        let _ = write!(s, r#"<text x="{:.1}" y="{}" font-size="13" fill="{MUTED}" text-anchor="middle">{}일</text>"#, x(d as f64 * 24.0), b + 24.0, d);
    }
    for (v, col, lab) in [(20e-6, "#b7791f", "희미하게 보임 20 µA"), (0.5e-3, "#2f855a", "또렷 0.5 mA")] {
        let _ = write!(s, r#"<line x1="{l}" x2="{r}" y1="{0:.1}" y2="{0:.1}" stroke="{col}" stroke-dasharray="6 5" stroke-width="1.5"/><text x="{1}" y="{2:.1}" font-size="13" fill="{col}" text-anchor="end">{lab}</text>"#,
                       y(v), r - 6.0, y(v) - 6.0);
    }
    let path: Vec<String> = run.trace.iter().map(|&(hh, i, _)| format!("{:.1},{:.1}", x(hh), y(i))).collect();
    let _ = write!(s, r#"<polyline points="{}" fill="none" stroke="{DEFECT}" stroke-width="2.6" stroke-linejoin="round"/>"#, path.join(" "));
    if let Some(o) = off {
        let _ = write!(s, r#"<line x1="{0:.1}" x2="{0:.1}" y1="{t}" y2="{b}" stroke="{INK}" stroke-dasharray="3 4"/><text x="{1:.1}" y="{2}" font-size="13" fill="{INK}">처음 꺼짐 {3:.0} h</text>"#,
                       x(o), x(o) + 6.0, t + 18.0, o);
    }
    let _ = write!(s, r##"<rect x="{l}" y="{}" width="16" height="12" fill="#fff6db" stroke="#e8d7a3"/><text x="{}" y="{}" font-size="13" fill="{MUTED}">빛 있는 시간</text><text x="{}" y="{}" font-size="13" fill="{MUTED}">LED 전류 (로그 눈금)</text>"##,
                   b + 40.0, l + 22.0, b + 50.0, l + 140.0, b + 50.0);
    s.push_str("</svg>");
    s
}

pub fn power_budget_svg() -> String {
    let mut bat = build(&default_case());
    let met = Metabolism::default();
    met.attach(&mut bat);
    let e_ion = bat.stack.n_pairs as f64 * bat.stack.pair_emf();
    let bars = [
        ("빛 (광합성형, 낮)", met.light_pump(&bat) * e_ion, CONC, "만듦"),
        ("내장 연료 (소화형, 시작)", met.fuel_pump(&bat) * e_ion, AEM, "만듦"),
        ("증발 (호흡형)", met.evap_emf(&bat).abs() * 1e-3, "#7aa6c9", "만듦"),
        ("LED 희미하게", 20e-6 * Led.voltage(20e-6), "#b7791f", "필요"),
        ("LED 또렷하게", 0.5e-3 * Led.voltage(0.5e-3), "#b7791f", "필요"),
        ("꼬마전구 붉게", 0.15 * 0.75, DEFECT, "필요"),
        ("꼬마전구 정격", 0.75, DEFECT, "필요"),
    ];
    let (w, h) = (1200.0, 560.0);
    let (l, r, t) = (300.0, 1120.0, 120.0);
    let (lo, hi): (f64, f64) = (1e-6, 1.0);
    let xs = |p: f64| l + (p.max(lo).ln() - lo.ln()) / (hi.ln() - lo.ln()) * (r - l);
    let mut s = head(w, h, "만드는 전력 vs 필요한 전력", "결정 안의 대사가 만드는 화학 전력과 각 부하가 요구하는 전력 (로그 눈금)");
    for (p, lab) in [(1e-6, "1 µW"), (1e-5, "10 µW"), (1e-4, "100 µW"), (1e-3, "1 mW"), (1e-2, "10 mW"), (1e-1, "100 mW"), (1.0, "1 W")] {
        let _ = write!(s, r#"<line x1="{0:.1}" x2="{0:.1}" y1="{t}" y2="{1}" stroke="{GRID}"/><text x="{0:.1}" y="{2}" font-size="13" fill="{MUTED}" text-anchor="middle">{lab}</text>"#,
                       xs(p), t + bars.len() as f64 * 52.0, t + bars.len() as f64 * 52.0 + 22.0);
    }
    for (k, (lab, p, col, kind)) in bars.iter().enumerate() {
        let yy = t + k as f64 * 52.0 + 10.0;
        let _ = write!(s, r#"<text x="{}" y="{:.1}" font-size="15" fill="{INK}" text-anchor="end">{lab}</text><text x="{}" y="{:.1}" font-size="12" fill="{MUTED}" text-anchor="end">{kind}</text>"#,
                       l - 16.0, yy + 18.0, l - 16.0, yy + 34.0);
        let _ = write!(s, r#"<rect x="{l}" y="{yy:.1}" width="{:.1}" height="30" rx="8" fill="{col}" fill-opacity="{}"/>"#,
                       (xs(*p) - l).max(4.0), if *kind == "만듦" { "0.9" } else { "0.35" });
        let txt = if *p >= 1e-3 { format!("{:.2} mW", p * 1e3) } else { format!("{:.1} µW", p * 1e6) };
        let _ = write!(s, r#"<text x="{:.1}" y="{:.1}" font-size="14" font-weight="600" fill="{INK}">{txt}</text>"#, xs(*p) + 10.0, yy + 21.0);
    }
    s.push_str("</svg>");
    s
}

pub fn bulb_svg() -> String {
    let bat = build(&default_case());
    let met = Metabolism::default();
    let (k, _) = best_parallel(&bat, &met, &Bulb);
    let run = simulate(&bat, &met, &Bulb, 0.5, 2.0, k, 3);
    let (w, h) = (1200.0, 520.0);
    let (l, r, t, b) = (100.0, 1150.0, 120.0, 430.0);
    let pmax = run.trace.iter().map(|&(_, i, _)| i * Bulb.voltage(i)).fold(0.0, f64::max).max(0.2);
    let x = |hh: f64| l + hh / 0.5 * (r - l);
    let y = |p: f64| b - p / pmax * (b - t);
    let off = run.first_off_h.map(|o| o * 60.0);
    let mut s = head(w, h, &format!("꼬마전구 (2.5 V 0.3 A) — 결정을 {k}조각 병렬로"), &format!(
        "결정화 때 저장된 농도차로만 빛남 · {}", match off { Some(m) => format!("약 {m:.1}분 뒤 꺼짐, 대사 전력으로는 지속 불가"), None => "30분 이상".into() }));
    for m in (0..=30).step_by(5) {
        let _ = write!(s, r#"<text x="{:.1}" y="{}" font-size="13" fill="{MUTED}" text-anchor="middle">{m}분</text>"#, x(m as f64 / 60.0), b + 24.0);
    }
    let glow = 0.15 * 0.75;
    let _ = write!(s, r#"<line x1="{l}" x2="{r}" y1="{0:.1}" y2="{0:.1}" stroke="{DEFECT}" stroke-dasharray="6 5"/><text x="{1}" y="{2:.1}" font-size="13" fill="{DEFECT}" text-anchor="end">붉게 빛나는 기준 {3:.0} mW</text>"#,
                   y(glow), r - 6.0, y(glow) - 6.0, glow * 1e3);
    let path: Vec<String> = run.trace.iter().map(|&(hh, i, _)| format!("{:.1},{:.1}", x(hh), y(i * Bulb.voltage(i)))).collect();
    let _ = write!(s, r##"<polyline points="{}" fill="none" stroke="#c05621" stroke-width="2.8"/><text x="{l}" y="{}" font-size="13" fill="{MUTED}">전구 전력 (최대 {:.0} mW)</text>"##,
                   path.join(" "), t - 10.0, pmax * 1e3);
    s.push_str("</svg>");
    s
}

pub fn quantum_svg() -> String {
    let (w, h) = (1200.0, 600.0);
    let mut s = head(w, h, "양자 모듈 — 분자가 많을수록 더 빨리 충전 (Tavis–Cummings)",
        "왼쪽: 저장 에너지 E/N (분자 N 개, 광자 N 개로 충전) · 오른쪽: 따로 충전할 때 대비 평균 전력 Γ — 집단 양자 이점");
    let (l, r, t, b) = (90.0, 600.0, 120.0, 500.0);
    let tmax = 1.8;
    let x = |v: f64| l + v / tmax * (r - l);
    let y = |v: f64| b - v * (b - t);
    for k in 0..=4 {
        let v = k as f64 / 4.0;
        let _ = write!(s, r#"<line x1="{l}" x2="{r}" y1="{0:.1}" y2="{0:.1}" stroke="{GRID}"/><text x="{1}" y="{2:.1}" font-size="13" fill="{MUTED}" text-anchor="end">{3:.2}</text>"#,
                       y(v), l - 8.0, y(v) + 4.0, v);
    }
    for k in 0..=6 {
        let v = k as f64 * 0.3;
        let _ = write!(s, r#"<text x="{:.1}" y="{}" font-size="13" fill="{MUTED}" text-anchor="middle">{v:.1}</text>"#, x(v), b + 22.0);
    }
    let _ = write!(s, r#"<text x="{}" y="{}" font-size="13" fill="{MUTED}" text-anchor="middle">시간 [1/g]</text>"#, (l + r) / 2.0, b + 44.0);
    let cols = ["#9aa7b4", "#7aa6c9", "#2f6db5", "#23a06b", "#f28c38"];
    for (c, n) in [1usize, 4, 16, 64, 128].iter().enumerate() {
        let tr = quantum::trace(*n, tmax, 300);
        let pts: Vec<String> = tr.iter().map(|&(tt, e)| format!("{:.1},{:.1}", x(tt), y(e))).collect();
        let _ = write!(s, r#"<polyline points="{}" fill="none" stroke="{}" stroke-width="2.4"/><text x="{}" y="{:.1}" font-size="13" fill="{}">N={n}</text>"#,
                       pts.join(" "), cols[c], r + 8.0, t + 20.0 + c as f64 * 20.0, cols[c]);
    }
    // 오른쪽: Γ vs N (로그-로그)
    let (rows, a) = quantum::scaling(&[1, 2, 4, 8, 16, 32, 64, 128]);
    let (l2, r2) = (720.0, 1150.0);
    let xn = |n: f64| l2 + n.ln() / 128f64.ln() * (r2 - l2);
    let gmax = 8.0f64;
    let yg = |g: f64| b - (g.ln() - 0.8f64.ln()) / (gmax.ln() - 0.8f64.ln()) * (b - t);
    for g in [1.0, 2.0, 4.0, 8.0] {
        let _ = write!(s, r#"<line x1="{l2}" x2="{r2}" y1="{0:.1}" y2="{0:.1}" stroke="{GRID}"/><text x="{1}" y="{2:.1}" font-size="13" fill="{MUTED}" text-anchor="end">×{g}</text>"#,
                       yg(g), l2 - 8.0, yg(g) + 4.0);
    }
    for n in [1.0, 4.0, 16.0, 64.0, 128.0] {
        let _ = write!(s, r#"<text x="{:.1}" y="{}" font-size="13" fill="{MUTED}" text-anchor="middle">{n}</text>"#, xn(n), b + 22.0);
    }
    let _ = write!(s, r#"<text x="{}" y="{}" font-size="13" fill="{MUTED}" text-anchor="middle">분자 수 N</text>"#, (l2 + r2) / 2.0, b + 44.0);
    let pts: Vec<String> = rows.iter().map(|q| format!("{:.1},{:.1}", xn(q.n as f64), yg(q.advantage))).collect();
    let _ = write!(s, r##"<polyline points="{}" fill="none" stroke="#7a5af8" stroke-width="2.6"/>"##, pts.join(" "));
    for q in &rows {
        let _ = write!(s, r##"<circle cx="{:.1}" cy="{:.1}" r="4.5" fill="#7a5af8"/>"##, xn(q.n as f64), yg(q.advantage));
    }
    let last = rows.last().unwrap();
    let _ = write!(s, r##"<text x="{l2}" y="{}" font-size="14" fill="{INK}">N={} 에서 병렬 대비 ×{:.2} · 충전 시간 ∝ N^-{:.3}</text>"##, t - 4.0, last.n, last.advantage, a);
    s.push_str("</svg>");
    s
}

pub fn qmodule_section_svg() -> String {
    let (w, h) = (1200.0, 520.0);
    let mut s = head(w, h, "양자 모듈 단면 (두께 과장 표시)", "용융 실리카 · SiO₂/Si₃N₄ 유전체 거울 8쌍 · 색소 활성층 · 8쌍 · 덮개 — 금속 없음 (Si 는 준금속)");
    let lam = 590.0;
    let (t1, t2, ta) = (lam / (4.0 * 1.46), lam / (4.0 * 2.0), lam / (2.0 * 1.49));
    let mut layers: Vec<(&str, f64, &str)> = Vec::new();
    for _ in 0..8 { layers.push(("SiO₂", t1, "#e8f1f8")); layers.push(("Si₃N₄", t2, "#9fb6c9")); }
    layers.push(("활성층 PMMA + 색소", ta, "#f28c38"));
    for _ in 0..8 { layers.push(("Si₃N₄", t2, "#9fb6c9")); layers.push(("SiO₂", t1, "#e8f1f8")); }
    let total: f64 = layers.iter().map(|q| q.1).sum();
    let (x0, x1, top, bottom) = (120.0, 760.0, 150.0, 420.0);
    let k = (bottom - top) / total;
    let _ = write!(s, r##"<rect x="{x0}" y="{bottom}" width="{}" height="40" fill="#dfe9f3"/><text x="{}" y="{}" font-size="13" fill="{MUTED}">용융 실리카 기판 1 mm</text>"##,
                   x1 - x0, x1 + 16.0, bottom + 24.0);
    let _ = write!(s, r##"<rect x="{x0}" y="{}" width="{}" height="30" fill="#dfe9f3"/><text x="{}" y="{}" font-size="13" fill="{MUTED}">덮개 용융 실리카 0.5 mm</text>"##,
                   top - 30.0, x1 - x0, x1 + 16.0, top - 10.0);
    let mut z = bottom;
    for (name, tk, col) in &layers {
        let hh = tk * k;
        z -= hh;
        let _ = write!(s, r#"<rect x="{x0}" y="{z:.2}" width="{}" height="{hh:.2}" fill="{col}"/>"#, x1 - x0);
        if name.starts_with("활성") {
            let _ = write!(s, r#"<text x="{}" y="{:.1}" font-size="15" font-weight="700" fill="{INK}">{name} {tk:.0} nm (λ/2n)</text>"#, x1 + 16.0, z + hh / 2.0 + 5.0);
        }
    }
    let _ = write!(s, r#"<text x="{}" y="{}" font-size="13" fill="{MUTED}">거울 SiO₂ {t1:.1} nm / Si₃N₄ {t2:.1} nm (λ/4n, λ = 590 nm)</text>"#, x1 + 16.0, bottom - 20.0);
    let _ = write!(s, r#"<text x="{}" y="{}" font-size="13" fill="{MUTED}">거울 8쌍</text>"#, x1 + 16.0, top + 30.0);
    let _ = write!(s, r#"<text x="{x0}" y="{}" font-size="13" fill="{MUTED}">지름 24 mm (기판·덮개 25 mm) · 빛으로 충전·방출 · STEP: qmodule_rust.step / qmodule_csharp.step</text>"#, bottom + 70.0);
    s.push_str("</svg>");
    s
}

pub fn render_all(dir: &str) {
    std::fs::create_dir_all(dir).expect("폴더 만들기");
    let files = [
        ("voronoi_default.svg", voronoi_svg(0.35, 0.85, 1.25, 2.0, 1, "결정 단면 — 보로노이 도메인과 프랙탈 층 경계")),
        ("voronoi_rough.svg", voronoi_svg(1.0, 0.0, 1.6, 2.0, 2, "거친 프랙탈 경계 — 결함 벽이 생기는 경우")),
        ("voronoi_clustered.svg", voronoi_svg(0.35, 0.85, 1.25, 1.6, 3, "뭉친 결정핵 (프랙탈 점집합)")),
        ("led_week.svg", led_week_svg()),
        ("power_budget.svg", power_budget_svg()),
        ("bulb.svg", bulb_svg()),
        ("quantum_charging.svg", quantum_svg()),
        ("qmodule_section.svg", qmodule_section_svg()),
    ];
    for (name, body) in files {
        std::fs::write(format!("{dir}/{name}"), body).expect("쓰기");
        println!("{dir}/{name}");
    }
}
