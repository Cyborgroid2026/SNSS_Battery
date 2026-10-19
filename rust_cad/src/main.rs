//! snss-cad — truck B-rep 커널로 SNSS 형상을 만들고 STEP (ISO 10303-21, AP214) 으로 내보냄.
//!
//!   cargo run --release -- <출력 폴더>
//!     qmodule_rust.step       양자 모듈 (spec/QUANTUM.md §4) 35개 층 고체
//!     crystal_block_rust.step 생리식염수 결정 블록 — 도메인 층 252개 + 막 252장 (spec/SPEC.md §4)

use truck_modeling::*;
use truck_stepio::out;

/// z0 에서 높이 h 인 원기둥 고체 (반지름 r, 축 = Z)
fn disc(r: f64, z0: f64, h: f64) -> Solid {
    let v = builder::vertex(Point3::new(r, 0.0, z0));
    let circle = builder::rsweep(&v, Point3::new(0.0, 0.0, z0), Vector3::unit_z(), Rad(7.0));
    let face = builder::try_attach_plane(&[circle]).expect("평면 붙이기");
    builder::tsweep(&face, Vector3::new(0.0, 0.0, h))
}

/// (이름, 지름, 두께) — 아래에서 위로. spec/QUANTUM.md §4
fn qmodule_layers() -> Vec<(String, f64, f64)> {
    let lam = 590.0;
    let t_sio2 = lam / (4.0 * 1.46) * 1e-6;
    let t_sin = lam / (4.0 * 2.00) * 1e-6;
    let t_act = lam / (2.0 * 1.49) * 1e-6;
    let mut v = vec![("substrate SiO2".to_string(), 25.0, 1.0)];
    for k in 1..=8 {
        v.push((format!("bottom DBR SiO2 {k}"), 24.0, t_sio2));
        v.push((format!("bottom DBR Si3N4 {k}"), 24.0, t_sin));
    }
    v.push(("active PMMA+PDI dye".into(), 24.0, t_act));
    for k in 1..=8 {
        v.push((format!("top DBR Si3N4 {k}"), 24.0, t_sin));
        v.push((format!("top DBR SiO2 {k}"), 24.0, t_sio2));
    }
    v.push(("cover SiO2".into(), 25.0, 0.5));
    v
}

/// 결정 블록: 기본 배합 (500 mL 병, 층 0.5 mm, 막 5/8 µm). spec/SPEC.md §4
fn crystal_layers() -> Vec<(String, f64, f64)> {
    let di = 72.0 - 1.6;
    let fill_h = 500.0 / (std::f64::consts::PI * (di / 20.0f64).powi(2)) * 10.0;
    let pair = 2.0 * 0.5 + (5.0 + 8.0) / 1000.0;
    let n = (fill_h / pair).floor() as usize;
    let mut v = Vec::new();
    for k in 1..=n {
        v.push((format!("A{k} dilute domain layer"), di, 0.5));
        v.push((format!("CEM{k} GO-LC wall"), di, 0.005));
        v.push((format!("B{k} concentrated domain layer"), di, 0.5));
        v.push((format!("AEM{k} GO/PDDA wall"), di, 0.008));
    }
    v
}

fn build(layers: &[(String, f64, f64)]) -> (Vec<Solid>, f64) {
    let mut z = 0.0;
    let mut vol = 0.0;
    let mut solids = Vec::new();
    for (_, d, t) in layers {
        solids.push(disc(d / 2.0, z, *t));
        vol += std::f64::consts::PI * (d / 2.0).powi(2) * t;
        z += t;
    }
    (solids, vol)
}

fn write(path: &str, layers: &[(String, f64, f64)]) {
    let (solids, vol) = build(layers);
    let compressed: Vec<_> = solids.iter().map(|s| s.compress()).collect();
    let models: out::StepModels<_, _, _> = compressed.iter().collect();
    let step = out::CompleteStepDisplay::new(
        models,
        out::StepHeaderDescriptor {
            file_name: path.rsplit('/').next().unwrap_or(path).to_string(),
            organization_system: "SNSS snss-cad (truck)".into(),
            ..Default::default()
        },
    )
    .to_string()
    // truck 0.3 은 FILE_NAME 의 작성자·조직을 (('')) 로 써서 OpenCascade 가 헤더 경고를 냄 → 표준 형식 ('') 로 고침
    .replacen("(('')), ((''))", "(''), ('')", 1);
    std::fs::write(path, step).expect("STEP 쓰기");
    println!("{path}\t고체 {}\t해석 부피 {vol:.9} mm³", solids.len());
}

fn main() {
    let dir = std::env::args().nth(1).unwrap_or_else(|| "cad_out".into());
    std::fs::create_dir_all(&dir).expect("폴더");
    write(&format!("{dir}/qmodule_rust.step"), &qmodule_layers());
    write(&format!("{dir}/crystal_block_rust.step"), &crystal_layers());
}
