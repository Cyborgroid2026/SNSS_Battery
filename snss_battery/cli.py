"""명령줄 인터페이스: python -m snss_battery <command> ..."""

from __future__ import annotations

import argparse
import sys

from .assembly import GrapheneLCDispersion, assess
from .bottle import BottleGelBattery, BottleSpec, GelFormation
from .electrolyte import SalineSolution
from .materials import MEMBRANES, format_audit
from .simulation import cycle_cc, max_power_point, suggest_limits


def _add_battery_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("생리식염수 결정 배터리")
    g.add_argument("--nacl", type=float, default=0.9, help="NaCl wt%% (기본 0.9 = 생리식염수)")
    g.add_argument("--temp", type=float, default=25.0, help="온도 °C")
    g.add_argument("--volume", type=float, default=500.0, help="식염수병 용량 mL")
    g.add_argument("--diameter", type=float, default=72.0, help="병 바깥지름 mm")
    g.add_argument("--go", type=float, default=5.0, help="GO 액정 농도 mg/mL")
    g.add_argument("--layer", type=float, default=0.5, help="인공세포 층 두께 mm")
    g.add_argument("--ratio", type=float, default=20.0, help="결정화 시 진한/묽은 세포 농도비")
    g.add_argument("--shrink", type=float, default=0.0, help="겔화 수축률 (0~0.5)")
    g.add_argument("--cem", default="go_lc", help="양이온 선택막")
    g.add_argument("--aem", default="go_pdda", help="음이온 선택막")
    g.add_argument("--surface-go", type=float, default=0.0, help="결정 표면 그래핀 mg/cm² (0 = 자동)")
    g.add_argument("--reactants", default="", help="함께 붓는 반응 화학물질 (메모)")
    g.add_argument("--age-days", type=float, default=0.0, help="결정화 후 보관 기간 (일)")
    f = p.add_argument_group("보로노이·프랙탈 구조")
    f.add_argument("--fractal-d", type=float, default=1.25, help="층 경계 프랙탈 차원 (1 = 평평, <2)")
    f.add_argument("--roughness", type=float, default=0.35, help="층 경계 RMS 거칠기 / 층 두께")
    f.add_argument("--correlation", type=float, default=0.85, help="이웃 층 경계가 함께 휘는 정도 0~1")
    f.add_argument("--seed-d", type=float, default=2.0, help="결정핵 분포 프랙탈 차원 (2 = 고름)")
    f.add_argument("--grains", type=float, default=3.0, help="층 두께당 결정핵 수")


def _build(a: argparse.Namespace) -> BottleGelBattery:
    bat = BottleGelBattery(
        BottleSpec(fill_volume_ml=a.volume, outer_diameter_mm=a.diameter),
        GelFormation(go_mg_per_ml=a.go, layer_thickness_mm=a.layer, concentration_ratio=a.ratio,
                     shrinkage=a.shrink, cation_membrane=a.cem, anion_membrane=a.aem,
                     surface_go_mg_cm2=a.surface_go, reactants=a.reactants,
                     interface_dimension=a.fractal_d, interface_roughness=a.roughness,
                     interface_correlation=a.correlation, seed_dimension=a.seed_d, grains_per_layer=a.grains),
        SalineSolution(a.nacl, a.temp),
    )
    bat.age(a.age_days)
    return bat


def cmd_materials(_: argparse.Namespace) -> None:
    print("[도메인 벽 — 결정화로 생기는 그래핀 액정막 (가정 파라미터)]")
    for m in MEMBRANES.values():
        sel = "양이온" if m.selectivity.value == "cation" else "음이온"
        print(f"  {m.key:<9}{m.name:<14} {sel} 선택 α0={m.permselectivity:.2f} "
              f"R={m.area_resistance_ohm_cm2:g} Ω·cm²  {m.note}")


def cmd_assembly(a: argparse.Namespace) -> None:
    d = GrapheneLCDispersion(a.go, a.flake, a.flake_thickness, a.ccc)
    print(assess(d, SalineSolution(a.nacl).molarity).describe())


def cmd_info(a: argparse.Namespace) -> None:
    from .cad import BottleDesign

    bat = _build(a)
    design = BottleDesign(bat)
    s = bat.stack
    _, p = max_power_point(s)
    print(bat.saline.describe())
    print(bat.describe())
    print(design.summary())
    print(f"프로브 연결 즉시: 개방전압 {s.open_circuit_voltage():.2f} V, 내부저항 {s.internal_resistance():.1f} Ω, "
          f"순간 최대 {p * 1000:.1f} mW, 용량 {s.capacity_mah:.2f} mAh (제한: {s.limiting_factor})")
    print(format_audit(design.audit()))


def cmd_cycle(a: argparse.Namespace) -> None:
    bat = _build(a)
    s = bat.stack
    i = a.current / 1000
    v_max, v_min = suggest_limits(s, i)
    v_max = a.vmax if a.vmax is not None else v_max
    v_min = a.vmin if a.vmin is not None else v_min
    print(bat.describe())
    print(f"프로브 연결 → 첫 방전 후 충방전: {a.current:g} mA, {v_min:g}–{v_max:g} V, {a.cycles}사이클")
    res = cycle_cc(s, i, v_max, v_min, a.cycles, a.dt, record_every=a.record_every, born_charged=True)
    print(res.summary())
    if a.csv:
        res.to_csv(a.csv)
        print(f"CSV 저장: {a.csv} ({len(res.points)}행)")


def cmd_fractal(a: argparse.Namespace) -> None:
    from .tessellation import analyze_battery, sweep_interface_dimension, sweep_roughness

    bat = _build(a)
    s = bat.stack
    print(bat.describe())
    print(f"이상적 층 모델: 개방전압 {s.open_circuit_voltage():.2f} V, 내부저항 {s.internal_resistance():.0f} Ω")
    print(analyze_battery(bat).describe())
    if a.sweep:
        base = bat.fractal_params(window_layers=24)
        args = (s, bat.formation.layer_thickness_mm, 2 * s.n_pairs, bat.gel_area_cm2 * 100, base)
        for title, rows, key in (("층 경계 프랙탈 차원 D", sweep_interface_dimension(*args), "interface_dimension"),
                                 ("층 경계 거칠기", sweep_roughness(*args), "roughness")):
            print(f"\n[{title} 스윕]  값 | 개방전압 V | 내부저항 Ω | 최대전력 mW | 내부누설 mA | 실측 D | 결함 %")
            for r in rows:
                print(f"  {getattr(r.params, key):5.2f} | {r.ocv_v:9.2f} | {r.resistance_ohm:9.0f} | "
                      f"{r.max_power_mw:10.1f} | {r.leak_current_ma:10.3f} | {r.fractal_dim_interfaces:6.2f} | "
                      f"{r.defect_fraction * 100:5.1f}")


def cmd_lighting(a: argparse.Namespace) -> None:
    from .metabolism import evaluate_lighting

    print(evaluate_lighting(_build(a), hours=a.hours).describe())


def cmd_crosscheck(_: argparse.Namespace) -> None:
    from .crosscheck import format_report, quantum_check, run_all

    print("같은 명세(spec/SPEC.md, spec/QUANTUM.md)를 Python · Rust · C# 로 각각 계산해 비교합니다…")
    print(format_report(run_all()))
    q = quantum_check()
    for lang, r in q["languages"].items():
        if "error" in r:
            print(f"[{lang}] 양자 모듈 실행 실패: {r['error']}")
        else:
            print(f"[{lang}] 양자 모듈 {'✔ 일치' if r['ok'] else '✘ 불일치'} — 항목 {r['n']}개, 최대 차이 {r['max_rel']:.1e}")


def cmd_tissue(a: argparse.Namespace) -> None:
    from .tissue import TissueRecipe, freezing, tissue_for

    rc = TissueRecipe()
    bat = rc.battery()
    print(tissue_for(bat).describe())
    f = freezing(bat.gel_height_mm, rc.plate_c)
    print(f"  방향성 동결 ({rc.plate_c:g} °C 판): 약 {f['hours']:.0f} h, 전선 {f['v_mid_um_s']:.1f} → {f['v_top_um_s']:.1f} µm/s, "
          f"세포 폭 추정 {f['cell_mid_um']:.0f}–{f['cell_top_um']:.0f} µm")
    print(f"[{rc.name}] 재료량 (RECIPE.md)")
    for group, items in rc.amounts():
        print(f"  [{group}]")
        for item, value, unit in items:
            print(f"    {item:<28} {value:9.2f} {unit}")
    from .process import describe, process

    print(describe(process(rc)))


def cmd_recipe(a: argparse.Namespace) -> None:
    from pathlib import Path

    from .drawing import pour_guide_sheet
    from .recipe import RECIPES

    for key in (["practice", "led"] if a.which == "all" else [a.which]):
        r = RECIPES[key]
        print(r.describe())
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        sh = pour_guide_sheet(r)
        sh.save_pdf(out / f"pour_guide_{key}.pdf")
        sh.to_dxf(out / f"pour_guide_{key}.dxf")
        print(f"  1:1 붓기 가이드: {out / f'pour_guide_{key}.pdf'}\n")


def cmd_chem(a: argparse.Namespace) -> None:
    from . import chem

    if a.rebuild:  # PHREEQC 로 표 다시 계산 (phreeqpython 필요 → .venv)
        chem.write_table()
        print(f"표 저장: {chem.TABLE}")
    print(chem.describe())


def cmd_fem(a: argparse.Namespace) -> None:
    from . import fem

    if not a.summary:
        fem.run(a.cell / 1000)
    print(fem.describe())


def cmd_elab(_: argparse.Namespace) -> None:
    from . import elab

    r = elab.push()
    print(f"eLabFTW: 템플릿 {r['template']}, 실험 {r['experiments']} → {r['url']}")


def cmd_pybamm(_: argparse.Namespace) -> None:
    from . import pybamm_cell

    r = pybamm_cell.write()
    print(pybamm_cell.describe(r))
    print(f"저장: {pybamm_cell.OUT}")


def cmd_quantum(_: argparse.Namespace) -> None:
    from .quantum import QuantumModule

    print(QuantumModule().describe())


def cmd_cadcheck(a: argparse.Namespace) -> None:
    from .cadcheck import format_report, run

    rep = run(a.out, a.ocp)
    for line in rep.get("generate_log", []):
        print(line)
    print(format_report(rep))


def cmd_cad(a: argparse.Namespace) -> None:
    from .cad import BottleDesign, BottleDesignParams
    from .drawing import export_all

    d = BottleDesign(_build(a), BottleDesignParams(cut_margin_mm=a.cut_margin))
    print(d.summary())
    for f in export_all(d, a.out):
        print(f"  {f}")


def cmd_web(a: argparse.Namespace) -> None:
    from .cad import BottleDesign
    from .web import build_site, serve

    bat = _build(a)
    index = build_site(bat, BottleDesign(bat), a.out, current_a=a.current / 1000)
    print(f"사이트 생성: {index}")
    if not a.no_serve:
        serve(a.out, a.port, a.host)


def cmd_static(a: argparse.Namespace) -> None:
    from .static_site import export_static

    index = export_static(a.src, a.out, a.zip)
    print(f"정적 사이트 생성: {index}  (더블클릭으로 열거나 폴더째 정적 호스팅에 올리면 됨)")


def cmd_gui(_: argparse.Namespace) -> None:
    from .gui import main as gui_main

    gui_main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="snss-battery", description="생리식염수 결정 배터리 시뮬레이터")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("materials", help="재료 목록").set_defaults(func=cmd_materials)
    sub.add_parser("gui", help="GUI 실행 (matplotlib 필요)").set_defaults(func=cmd_gui)

    p = sub.add_parser("assembly", help="GO 액정 + 식염수 결정화(막 형성) 판정")
    p.add_argument("--go", type=float, default=5.0, help="GO 농도 mg/mL")
    p.add_argument("--flake", type=float, default=10.0, help="판 크기 µm")
    p.add_argument("--flake-thickness", type=float, default=1.0, help="판 두께 nm")
    p.add_argument("--ccc", type=float, default=44.0, help="임계응집농도 mM")
    p.add_argument("--nacl", type=float, default=0.9, help="NaCl wt%%")
    p.set_defaults(func=cmd_assembly)

    p = sub.add_parser("info", help="배터리 사양 + 금속 검사")
    _add_battery_args(p)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("cycle", help="탄생 방전 + 충방전 사이클 시뮬레이션")
    _add_battery_args(p)
    p.add_argument("--current", type=float, default=0.1, help="충방전 전류 mA")
    p.add_argument("--vmax", type=float, help="충전 상한 V (기본: 자동 권장값)")
    p.add_argument("--vmin", type=float, help="방전 하한 V (기본: 자동 권장값)")
    p.add_argument("--cycles", type=int, default=2)
    p.add_argument("--dt", type=float, default=20.0, help="시간 스텝 s")
    p.add_argument("--record-every", type=int, default=6)
    p.add_argument("--csv", help="결과 CSV 경로")
    p.set_defaults(func=cmd_cycle)

    p = sub.add_parser("fractal", help="보로노이·프랙탈 도메인 네트워크 해석")
    _add_battery_args(p)
    p.add_argument("--sweep", action="store_true", help="프랙탈 차원·거칠기 스윕")
    p.set_defaults(func=cmd_fractal)

    p = sub.add_parser("lighting", help="대사(빛·연료·증발·반응물)로 LED·꼬마전구가 켜지는지 판정")
    _add_battery_args(p)
    p.add_argument("--hours", type=float, default=168.0, help="LED 연결 시간")
    p.set_defaults(func=cmd_lighting)

    sub.add_parser("crosscheck", help="Python · Rust · C# 독립 구현 교차 검증").set_defaults(func=cmd_crosscheck)
    p = sub.add_parser("tissue", help="통째 결정 · 인공세포 조직 (3D 보로노이 + 프랙탈 동결 전선, 층·극성 없음)")
    p.set_defaults(func=cmd_tissue)
    p = sub.add_parser("recipe", help="레시피 재료량 — 통째 결정 · 인공세포형 (RECIPE.md)")
    p.add_argument("--which", choices=["practice", "led", "all"], default="all")
    p.add_argument("--out", default="cad_out")
    p.set_defaults(func=cmd_tissue)  # 층 쌓기 레시피는 뺐음 — 통째 결정 레시피
    sub.add_parser("quantum", help="SNSS-QB 양자 모듈 (유기 미세공진기 Dicke 형) 계산").set_defaults(func=cmd_quantum)
    p = sub.add_parser("chem", help="용액 화학 — PHREEQC · pitzer.dat 활동도 · 어는점 · 막전위 보정")
    p.add_argument("--rebuild", action="store_true", help="PHREEQC 로 표를 다시 계산 (phreeqpython 필요)")
    p.set_defaults(func=cmd_chem)
    p = sub.add_parser("fem", help="FEniCSx(Docker) 로 방향성 동결 · 해동 열전달 + 상변화 — 레시피 조건 비교")
    p.add_argument("--cell", type=float, default=0.8, help="격자 크기 mm")
    p.add_argument("--summary", action="store_true", help="계산하지 않고 저장된 결과만 요약")
    p.set_defaults(func=cmd_fem)
    sub.add_parser("elab", help="eLabFTW(로컬 Docker) 에 공정 19단계를 실험 템플릿 · 실험으로 올림").set_defaults(func=cmd_elab)
    sub.add_parser("pybamm", help="PyBaMM 으로 인공세포 스택 충방전 (확산 + 활동도) · 기존 모델과 비교").set_defaults(func=cmd_pybamm)
    p = sub.add_parser("cadcheck", help="Rust(truck)·C# 로 STEP 생성 + OpenCascade 검증")
    p.add_argument("--out", default="cad_out/step")
    p.add_argument("--ocp", help="OpenCascade(OCP) 파이썬 패키지 경로 (pip --target 으로 설치한 경우)")
    p.set_defaults(func=cmd_cadcheck)

    p = sub.add_parser("cad", help="실물 설계 파일 (도면 DXF/PDF, 1:1 템플릿, STL, OpenSCAD)")
    _add_battery_args(p)
    p.add_argument("--out", default="cad_out", help="출력 폴더")
    p.add_argument("--cut-margin", type=float, default=5.0, help="겔 윗면 ~ 절단선 A mm")
    p.set_defaults(func=cmd_cad)

    p = sub.add_parser("web", help="웹 뷰어 생성 + 로컬 서버 (도면·3D·시뮬레이션)")
    _add_battery_args(p)
    p.add_argument("--out", default="web_out", help="사이트 폴더")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--current", type=float, default=0.1, help="충방전 전류 mA")
    p.add_argument("--no-serve", action="store_true", help="사이트만 만들고 서버는 띄우지 않음")
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("static", help="서버 없이 동작하는 정적 웹 사이트 (web 출력 → web_static)")
    p.add_argument("--src", default="web_out", help="web 명령이 만든 사이트 폴더")
    p.add_argument("--out", default="web_static", help="정적 사이트 폴더")
    p.add_argument("--zip", action="store_true", help="폴더를 zip 으로도 묶음")
    p.set_defaults(func=cmd_static)

    a = parser.parse_args(argv)
    try:
        a.func(a)
    except (ValueError, KeyError, OSError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
