"""웹 뷰어: 결정화 과정 애니메이션 · 도면 · 3D · 시뮬레이션 · 실험 기록을 로컬 서버로 띄움.

    python -m snss_battery web --port 8765
    → http://127.0.0.1:8765/  (VS Code: "Browser: Open Integrated Browser" / Simple Browser)

실험 기록은 서버가 experiments/log.jsonl 에 저장한다 (사이트 폴더의 상위 폴더 기준).
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import shutil
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from matplotlib.figure import Figure

from .assembly import PHASE_LABELS, GrapheneLCDispersion, assess
from .bottle import BottleGelBattery
from .cad import BottleDesign
from .drawing import cut_sheet, export_all, setup_fonts
from .materials import format_audit
from .plots import plot_assembly, plot_cycles, plot_structure
from .simulation import cycle_cc, max_power_point, suggest_limits

VENDOR = Path(__file__).parent / "vendor"
WEBUI = Path(__file__).parent / "webui"
EXPERIMENT_FIELDS = ("elapsed_h", "temp_c", "saline_ml", "go_g", "reactants", "state", "voltage_v",
                     "current_ma", "note", "sample", "height_mm", "probe", "polarity", "phase", "load", "lit", "recipe")
_TEXT_FIELDS = {"reactants", "state", "note", "sample", "probe", "polarity", "phase", "load", "lit", "recipe"}
ROOT = Path(__file__).resolve().parent.parent
LAB_DLL = ROOT / "csharp" / "Snss.Lab" / "bin" / "Release" / "net10.0" / "Snss.Lab.dll"
RUST_BIN = ROOT / "rust" / "target" / "release" / "snss"


def _save(fig_fn, path: Path, size=(10, 5.5), dpi=130) -> None:
    fig = Figure(figsize=size, layout="constrained")
    fig_fn(fig)
    fig.savefig(path, dpi=dpi)


def _flat(tris) -> list[float]:
    return [round(c, 3) for t in tris for v in t for c in v]


def _model_json(d: BottleDesign) -> dict:
    b = d.battery.bottle
    return {
        "bottle": [{"name": s.name, "kind": s.kind, "positions": _flat(s.triangles)} for s in d.bottle_solids()],
        "probes": [{"name": s.name, "positions": _flat(s.triangles)} for s in d.solids()[1:]],
        "gel": {"r": d.gel_radius, "h": d.block_height, "z": d.gel_bottom_z,
                "bands": [[round(z0, 4), round(z1, 4), k] for z0, z1, k in d.layer_bands()]},
        "height": b.total_height_mm,
        "radius": b.outer_diameter_mm / 2,
    }


def build_site(
    battery: BottleGelBattery,
    design: BottleDesign,
    folder: str | Path,
    dispersion: GrapheneLCDispersion | None = None,
    current_a: float = 1e-4,
    n_cycles: int = 2,
    dt_s: float = 10.0,
) -> Path:
    folder = Path(folder)
    (folder / "img").mkdir(parents=True, exist_ok=True)
    setup_fonts()
    stack, b = battery.stack, battery.bottle
    disp = dispersion or GrapheneLCDispersion(go_mg_per_ml=battery.formation.go_mg_per_ml)
    files = export_all(design, folder / "cad")
    cut_sheet(design).save_pdf(folder / "cad" / "template_1to1.png", dpi=110)
    shutil.copytree(VENDOR, folder / "vendor", dirs_exist_ok=True)
    shutil.copytree(WEBUI, folder / "ui", dirs_exist_ok=True)

    rep = assess(disp, stack.saline.molarity)
    _save(lambda f: plot_assembly(f, disp, stack.saline.molarity * 1000), folder / "img" / "assembly_phase.png")
    _save(lambda f: plot_structure(f, stack), folder / "img" / "structure.png", size=(11, 4.2))
    v_max, v_min = suggest_limits(stack, current_a)
    sim = copy.deepcopy(stack)
    res = cycle_cc(sim, current_a, v_max, v_min, n_cycles, dt_s, record_every=4, born_charged=True)
    _save(lambda f: plot_cycles(f, res, v_max, v_min), folder / "img" / "cycles.png", size=(10, 7))
    _, p_mpp = max_power_point(stack)
    born = next((c for c in res.cycles if c.born), None)
    fractal = _fractal_assets(battery, folder / "img")
    svgs = _rust_svgs(folder / "svg")
    cross = _crosscheck_summary()
    from .metabolism import evaluate_lighting

    lighting = evaluate_lighting(battery)
    quantum = _quantum_assets(folder / "cad" / "step")
    recipes = _recipe_assets(folder / "cad")
    sculptor = _sculptor_assets(folder)
    light = _light_assets(folder)

    data = {
        "title": "SNSS 생리식염수 결정 배터리",
        "ocv": round(stack.open_circuit_voltage(), 3),
        "fractal": fractal,
        "svgs": svgs,
        "crosscheck": cross,
        "quantum": quantum,
        "sculptor": sculptor,
        "light": light,
        "recipes": recipes,
        "samples": _samples(battery, folder),
        "tools": _standard_tools(folder),
        "lighting": {"text": lighting.describe(), "budget_mw": {k: v * 1000 for k, v in lighting.budget_w.items()},
                     "led_off_h": lighting.led.first_off_h(), "bulb_k": lighting.bulb.parallel,
                     "bulb_peak_mw": lighting.bulb.peak_power_w() * 1000},
        "n_layers": 2 * stack.n_pairs,
        "conc": [round(stack.c_dilute * 1000, 1), round(stack.c_concentrated * 1000, 1)],
        "go_g": round(battery.go_mass_g, 2),
        "bottle": {"d": b.outer_diameter_mm, "wall": b.wall_mm, "body": b.body_height_mm,
                   "shoulder": b.shoulder_height_mm, "neck_d": b.neck_diameter_mm, "neck_h": b.neck_height_mm,
                   "cap_d": b.cap_diameter_mm, "cap_h": b.cap_height_mm, "fill": b.fill_height_mm,
                   "volume": b.fill_volume_ml, "cut": design.cut_z},
        "cards": [
            ("재료", f"약국 생리식염수 {b.fill_volume_ml:g} mL + 그래핀 폴리머 액정 {battery.go_mass_g:.2f} g + 반응 화학물"),
            ("결정 블록", f"Ø{battery.gel_diameter_mm:.1f} × {design.block_height:.1f} mm, 약 {design.mass_g():.0f} g"),
            ("세포형 도메인", f"{2 * stack.n_pairs}층 (결정화로 저절로 생김)"),
            ("개방전압 (프로브로 바로 측정)", f"{stack.open_circuit_voltage():.2f} V"),
            ("내부저항", f"{stack.internal_resistance():.0f} Ω"),
            ("뽑을 수 있는 전기 (첫 방전)", f"{born.discharge_mah:.3f} mAh" if born else "-"),
            ("제한 요인", stack.limiting_factor),
            ("보관 수명 (1/e)", f"약 {battery.shelf_time_constant_days:.0f}일"),
            ("막 형성 판정", PHASE_LABELS[rep.phase]),
            ("순간 최대 전력", f"{p_mpp * 1000:.0f} mW (아주 짧게)"),
            ("보로노이·프랙탈 회로망 개방전압", f"{fractal['ocv']:.2f} V (결함 반영)"),
            ("결함 단락 내부 누설", f"{fractal['leak_ma']:.3f} mA"),
        ],
        "audit_ok": all(a.ok for a in design.audit()),
        "summary": "\n".join([stack.saline.describe(), rep.describe(), battery.describe(), design.summary(),
                              format_audit(design.audit())]),
        "cycle_text": f"프로브 연결 후 {current_a * 1000:g} mA 방전 → 재충전 {n_cycles}회 ({v_min:g}–{v_max:g} V)\n"
                      + res.summary(),
        "cycles": [{"cycle": "탄생" if c.born else c.cycle, "charge": "-" if c.born else round(c.charge_mah, 3),
                    "discharge": round(c.discharge_mah, 3),
                    "ce": "-" if c.born else f"{c.coulombic_efficiency * 100:.1f}%",
                    "ee": "-" if c.born else f"{c.energy_efficiency * 100:.1f}%"} for c in res.cycles],
        "bom": [{"no": x.no, "name": x.name, "material": x.material, "qty": x.qty, "spec": x.spec,
                 "keep": x.in_battery} for x in design.bom()],
        "files": [str(f.relative_to(folder)) for f in files] + ["cad/template_1to1.png"],
    }
    (folder / "model.json").write_text(json.dumps(_model_json(design), ensure_ascii=False), encoding="utf-8")
    html = _TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    (folder / "index.html").write_text(html, encoding="utf-8")
    return folder / "index.html"


def _tissue_sample(folder: Path) -> dict:
    """통째 결정 · 인공세포 조직: 3D 보로노이 세포 + 프랙탈 동결 전선 (층·극성 없음) → model_tissue.json."""
    from .process import process, summary
    from .tissue import TissueRecipe, freezing, tissue_for

    rc = TissueRecipe()
    steps = process(rc)
    bat = rc.battery()
    tr = tissue_for(bat)
    d = BottleDesign(bat)
    f, c = tr.full, tr.continuity
    out = {
        "key": "tissue", "name": "통째 결정 · 인공세포 조직", "tissue": True,
        "note": "식염수병 안 식염수에서 바로 얼음 결정이 자라 세포가 되고, GO·PVA 가 결정 경계로 밀려나 막이 됨. "
                "층·극성 없음 — 세포는 비어 있고, 묽은 내강과 막 사이 진한 소금물의 농도차로 에너지만 담김.",
        "gel_r": d.gel_radius, "gel_z": d.gel_bottom_z, "block_h": d.block_height, "cut_z": d.cut_z, "mass_g": d.mass_g(),
        "fill_ml": bat.bottle.fill_volume_ml, "go_g": bat.go_mass_g, "layer_mm": 0, "pairs": 0,
        "ocv": f["ocv_v"], "gradient_bound_v": f["gradient_bound_v"], "r_ohm": f["r_ohm"], "led_ma": 0.0, "led": "꺼짐 (전압 거의 0)",
        "led_level": 0, "n_cells": f["n_cells"], "energy_j": f["energy_j"], "c_lumen_mM": 1000 * tr.c_lumen[1],
        "c_brine_m": tr.c_brine, "wall_mv": tr.wall_mv, "spacing_um": tr.params.cell_um, "film_um": tr.params.film_um,
        "e_cell_j": c["e_cell_mean"], "k_eff": c["k_eff"], "d_front": c["d_front"], "d_set": c["d_set"], "front_um": c["front_um"],
        "c_bottom_mM": f["c_bottom_mM"], "c_top_mM": f["c_top_mM"], "n_veins": len(tr.veins),
        "freezing": freezing(bat.gel_height_mm, rc.plate_c), "describe": tr.describe(),
        "amounts": rc.amounts(), "freeze_thaw": rc.freeze_thaw, "plate_c": rc.plate_c, "shelf_days": bat.shelf_time_constant_days,
        "process": [x.to_json() for x in steps], "process_summary": summary(steps),
    }
    r6 = lambda v: round(float(v), 5)
    cells = [{"c": round(x.conc_m * 1000, 3), "v": r6(x.volume_mm3), "fv": r6(x.film_mm3), "e": x.energy_j, "t": round(x.freeze_h, 3),
              "s": [r6(q) for q in x.seed], "f": [int(i) for i in x.faces]} for x in tr.cells]
    faces = [{"a": int(x.a), "b": int(x.b), "A": r6(x.area_mm2), "p": [r6(v) for v in x.poly.ravel()]} for x in tr.faces]
    model = {"W": tr.params.window_mm, "H": tr.params.height_mm, "spacing": tr.params.cell_um / 1000, "film_um": tr.params.film_um,
             "c_brine": tr.c_brine, "wall_mv": tr.wall_mv, "cells": cells, "faces": faces, "n_veins": len(tr.veins)}
    (folder / "model_tissue.json").write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out


def _standard_tools(folder: Path) -> dict:
    """'표준 도구' 탭: PHREEQC · PyBaMM · FEniCSx(ParaView 프레임) · eLabFTW 결과를 모음. 없는 것은 빠짐."""
    from . import chem

    spec = ROOT / "spec"
    load = lambda name: json.loads((spec / name).read_text(encoding="utf-8")) if (spec / name).exists() else None
    out: dict = {}
    try:
        m = [x for x in chem.table()["molality"] if x <= 5.5]
        out["phreeqc"] = {"m": m, "gamma25": [chem.gamma(x, 25) for x in m], "gamma0": [chem.gamma(x, 0) for x in m],
                          "tf": [chem.freezing_point_c(x) for x in m], "report": chem.report()}
    except (OSError, KeyError, ValueError):
        pass
    if (val := load("pybamm_validation.json")):
        val.pop("curves", None)
        out["pybamm"] = {"validation": val, "view": load("pybamm_view.json")}
    if (fem := load("fenicsx_freezing.json")):
        out["fem"] = fem
        frames = ROOT / "results" / "frames"
        if (frames / "frames.json").exists():  # ParaView 프레임 (./tools.sh fem-movie)
            shutil.copytree(frames, folder / "frames", dirs_exist_ok=True)
            out["frames"] = json.loads((frames / "frames.json").read_text())
    out["elab_url"] = "http://localhost:3148"
    return out


def _samples(battery: BottleGelBattery, folder: Path | None = None) -> list[dict]:
    """층·극성 없는 통째 결정 하나만 (층 쌓기 시료는 뺐음)."""
    return [_tissue_sample(folder)] if folder is not None else []


def _rust_svgs(out: Path) -> list[str]:
    """Rust 렌더러로 SVG 그림 생성 (없으면 빌드 시도, 실패하면 빈 목록)."""
    import shutil
    import subprocess

    if not RUST_BIN.exists() and shutil.which("cargo"):
        subprocess.run(["cargo", "build", "--release", "--quiet"], cwd=ROOT / "rust", timeout=600)
    if not RUST_BIN.exists():
        return []
    p = subprocess.run([str(RUST_BIN), "render", str(out)], capture_output=True, text=True, timeout=120)
    return [Path(line).name for line in p.stdout.split()] if p.returncode == 0 else []


def _recipe_assets(out: Path) -> list[dict]:
    from .drawing import pour_guide_sheet
    from .recipe import RECIPES

    items = []
    for key, r in RECIPES.items():
        sh = pour_guide_sheet(r)
        sh.save_pdf(out / f"pour_guide_{key}.pdf")
        sh.to_dxf(out / f"pour_guide_{key}.dxf")
        p = r.predict()
        items.append({"key": key, "name": r.name, "pairs": r.pairs, "layer_mm": r.layer_mm, "layer_ml": r.layer_ml,
                      "height_mm": r.height_mm, "steps": r.steps(), "c_a": r.c_dilute_m * 1000, "c_b": r.c_conc_m * 1000,
                      "ratio": r.ratio, "amounts": r.amounts(), "predict": p})
    return items


def _sculptor_assets(folder: Path) -> dict:
    """'조각가 · 존재' 탭: SC-1 기계 · 펜 끝 레시피 · 양자층 · 존재 설계와 생명 신호 · 3D 보기용 메시 · Blender 렌더."""
    import numpy as np

    from . import sculpt as S
    from .printer import SculptorSpec, bom, klipper_cfg
    from .qcap import QuantumCell, QuantumElectrode, doping_sweep

    out = folder / "sculpt"
    out.mkdir(parents=True, exist_ok=True)
    spec = SculptorSpec()
    cp = S.CellParams()
    piece = S.design("being", 0.0, cp, spec, "being")
    job = S.job_new(piece, spec)
    res = S.write_job(job, spec, out, meshes=False)
    pr = res["predictions"][0]
    (out / "bom.csv").write_text("구분,품목,수량,사양,구입처\n" + "\n".join(f"{b.group},{b.part},{b.qty},\"{b.spec}\",{b.where}" for b in bom(spec)) + "\n",
                                 encoding="utf-8")
    # 3D 보기: 거칠게 (칸 3개씩) — 세포 경계가 보일 만큼
    ms = S.piece_meshes(piece, 3, pr["cells"])
    view = {"bounds": [float(piece.height_mm)]}
    for role, (v, t, w) in ms.items():
        view[role] = {"v": np.round(v, 1).ravel().tolist(), "f": t.ravel().tolist(),
                      "w": (np.round(np.nan_to_num(w, nan=-1), 1).tolist() if w is not None else None)}
    (out / "being_view.json").write_text(json.dumps(view, separators=(",", ":")), encoding="utf-8")
    # 그림: 양자층 · 깨어남 · 단면
    cell = QuantumCell(QuantumElectrode("NBD", cp.carrier_pos), QuantumElectrode("PEI", cp.carrier_neg))
    sweep = doping_sweep()

    def fig_quantum(fig):
        ax1, ax2 = fig.subplots(1, 2)
        e = np.linspace(-0.6, 0.6, 400)
        for el, lab, col in ((QuantumElectrode("", 0.0), "도핑 없음", "#9aa7b4"), (cell.positive, "p형 (NBD)", "#e0344b"),
                             (cell.negative, "n형 (PEI)", "#2f6db5")):
            ax1.plot(e, el.c_total(e) * 100, color=col, label=lab)
        ax1.axhline(cell.positive.c_edl * 100, color="#5d6673", ls="--", lw=1, label="전기이중층 한계")
        ax1.set_xlabel("전극 전위 E (V, 영전하 기준)")
        ax1.set_ylabel("면적당 용량 µF/cm²")
        ax1.set_title("양자 커패시턴스가 깎는 용량: 1/C = 1/C_Q + 1/C_EDL")
        ax1.legend(fontsize=8)
        x = [r["carrier_1e12"] for r in sweep]
        ax2.plot(x, [r["sym_c"] for r in sweep], "o-", color="#9aa7b4", label="같은 n형 두 전극")
        ax2.plot(x, [r["asym_c"] for r in sweep], "o-", color="#7a5af8", label="양극 p형 · 음극 n형")
        ax2.set_xlabel("도핑 전하 밀도 (10¹² cm⁻²)")
        ax2.set_ylabel("셀 평균 용량 µF/cm²")
        ax2.set_title("세포 유형마다 도핑을 다르게 — p·n 이 이김")
        ax2.legend(fontsize=8)
        ax2.grid(True)

    def fig_wake(fig):
        ax1, ax2 = fig.subplots(1, 2)
        t = np.array(pr["series"]["t_s"]) / 60
        ax1.semilogx(t, np.array(pr["series"]["energy_j"]) * 1000, color="#23a06b")
        from matplotlib.ticker import FuncFormatter

        ax1.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))  # 10^-1 수식 눈금은 한글 글꼴에 − 가 없어 경고
        ax1.set_xlabel("발에 0.8 V 를 건 뒤 (분)")
        ax1.set_ylabel("몸에 쌓인 에너지 mJ")
        ax1.set_title("충전 = 깨어남")
        ax1.grid(True)
        w = np.array([x for x in pr["cells"]["wake_s"] if x is not None]) / 60
        z = np.array([c[2] for c, x in zip(pr["cells"]["center_mm"], pr["cells"]["wake_s"]) if x is not None])
        typ = np.array([ty for ty, x in zip(pr["cells"]["type"], pr["cells"]["wake_s"]) if x is not None])
        ax2.scatter(w[typ > 0], z[typ > 0], s=5, color="#e0344b", label="p 세포")
        ax2.scatter(w[typ < 0], z[typ < 0], s=5, color="#2f6db5", label="n 세포")
        ax2.set_xlabel("깨어나는 시간 (분, 63 %)")
        ax2.set_ylabel("세포 높이 mm")
        ax2.set_title(f"세포 {pr['n_cells']}개 — 발에서 머리로")
        ax2.legend(fontsize=8)

    from matplotlib.colors import ListedColormap

    cmap = ListedColormap(["#ffffff", "#e0344b", "#2f6db5", "#b9c3ce"])
    mat = piece.material

    def fig_slices(fig):
        axs = fig.subplots(1, 4, gridspec_kw={"width_ratios": [1, 1, 1, 1.25]})
        nz = mat.shape[2]
        for ax, (k, lab) in zip(axs[:3], ((1, "발바닥 (단자)"), (int(nz * 0.5), "몸통"), (int(nz * 0.83), "머리"))):
            ax.imshow(mat[:, :, k].T, origin="lower", cmap=cmap, vmin=0, vmax=3, interpolation="nearest")
            ax.set_title(f"{lab} · 층 {k}", fontsize=9)
            ax.axis("off")
        j = mat.shape[1] // 2
        axs[3].imshow(mat[:, j, :].T, origin="lower", cmap=cmap, vmin=0, vmax=3, interpolation="nearest",
                      aspect=spec.layer_mm / spec.line_mm)
        axs[3].set_title("세로 단면", fontsize=9)
        axs[3].axis("off")

    _save(fig_quantum, out / "quantum.png", size=(11, 4.2))
    _save(fig_wake, out / "wake.png", size=(11, 4.2))
    _save(fig_slices, out / "slices.png", size=(11, 4.0))
    # Blender 렌더 (./tools.sh blender 로 만든 것이 있으면)
    renders = []
    jobs = sorted(f.parent for f in (ROOT / "sculpt_out" / "jobs").glob("*/blender/sculptor.png"))
    if jobs:
        src = jobs[-1]
        for n in ("sculptor.png", "wake_0.png", "wake_1.png", "wake_2.png", "being.mp4"):
            if (src / n).exists():
                shutil.copy2(src / n, out / f"blender_{n}")
                renders.append(f"sculpt/blender_{n}")
    recipes = []
    for r in spec.recipes.values():
        g = spec.gel_check(r)
        recipes.append({"name": r.name, "go": r.go, "snss": r.snss, "pva": r.pva, "variant": r.go_variant, "light": r.light,
                        "color": r.color, "go_mg": g["go_mg_ml"], "nacl": g["nacl_mm"], "ccc": g["ccc_mm"],
                        "pva_wt": g["pva_wt"], "ok": g["ok"], "yield": g["yield_pa"]})
    # 출력 부품 (부모 프린터) · 시중 구매 · 호환 단자 — STL 은 무거워 웹에 넣지 않음 (./tools.sh parts)
    from .interfaces import ports_table
    from .parts import PARENT_BED_MM, printed_parts

    parts = []
    for part in printed_parts():
        parts.append({"name": part.name, "qty": part.qty, "material": part.material, "role": part.role,
                      "size": [round(x, 1) for x in part.size], "fits": part.fits()})
    parts_png = ROOT / "sculpt_out" / "parts" / "parts.png"
    if parts_png.exists():
        shutil.copy2(parts_png, out / "parts.png")
    t = res["time"]
    return {
        "parts": parts, "parent_bed": PARENT_BED_MM, "parts_png": "sculpt/parts.png" if parts_png.exists() else None,
        "buy": [{"group": b.group, "part": b.part, "qty": b.qty, "spec": b.spec, "where": b.where} for b in bom(spec)],
        "ports": ports_table(),
        "machine": spec.describe(), "check": spec.check(), "recipes": recipes,
        "feeds": [{"name": f.name, "stock": f.stock} for f in spec.feeds],
        "prediction": {k: v for k, v in pr.items() if k not in ("cells", "series")},
        "prediction_text": S.describe_prediction(pr),
        "job": {"work_h": t["work_s"] / 3600, "wait_h": t["wait_s"] / 3600, "switches": t["switches"], "saline_ml": t["saline_ml"], "nacl_after": t["medium"]["nacl_after_mm"],
                "ops": [o.note for o in job.ops]},
        "files": ["sculpt/job.gcode", "sculpt/printer.cfg", "sculpt/bom.csv", "sculpt/being.npz"],
        "renders": renders, "cell_mm": cp.cell_mm,
        "qcap_text": cell.describe(),
    }


def _light_assets(folder: Path) -> dict:
    """'빛 조각가 · 콘솔' 탭: SC-2 명세 · 공간 배치 · 층별 빛 그림(압축) · 존재 3D · Blender 렌더 · 어림 계산용 상수."""
    import base64
    import gzip

    import numpy as np

    from .layout import make_light_layout
    from .lightsculpt import LightSculptorSpec, describe_job, light_job
    from .sculpt import piece_meshes

    out = folder / "light"
    out.mkdir(parents=True, exist_ok=True)
    spec = LightSculptorSpec()
    cal_file = ROOT / "sculpt_out" / "light_cal.json"  # 시험편으로 잰 빛 상수가 있으면 그것으로
    if cal_file.exists():
        from .lightcal import calibrated_spec

        spec = calibrated_spec(cal_file, spec)
    job = light_job("being", 0.0, spec, name="being")
    p, pl, pr = job["piece"], job["plan"], job["prediction"]
    E, G = pl["E"], pl["G"]
    e_max, g_max = float(E.max()) or 1.0, float(G.max()) or 1.0
    q = lambda a, m: np.round(a / m * 255).astype(np.uint8)  # noqa: E731
    vox = np.stack([p.material.astype(np.uint8), q(E, e_max), q(G, g_max)], -1).transpose(2, 1, 0, 3)  # (층, y, x, 3)
    nz, ny, nx, _ = vox.shape
    blob = {"nx": nx, "ny": ny, "nz": nz, "pitch": list(p.pitch), "offset": list(p.offset), "e_max": e_max, "g_max": g_max,
            "layer_s": [round(float(t), 1) for t in pl["layer_s"]],
            "gz": base64.b64encode(gzip.compress(vox.tobytes(), 9)).decode()}
    (out / "exposure.js").write_text("window.SNSS_LIGHT = " + json.dumps(blob, separators=(",", ":")) + ";\n", encoding="utf-8")
    view = {"height": float(p.height_mm)}
    for role, (v, t, _) in piece_meshes(p, 3, None).items():
        view[role] = {"v": np.round(v, 1).ravel().tolist(), "f": t.ravel().tolist()}
    (out / "being.js").write_text("window.SNSS_LIGHT_BEING = " + json.dumps(view, separators=(",", ":")) + ";\n", encoding="utf-8")
    renders = []
    jobs = sorted(f.parent for f in (ROOT / "sculpt_out" / "light_jobs").glob("*/blender/light_scene.png"))
    if jobs:
        for n in ("light_scene.png", "light_surface.png", "light_cycle.mp4"):
            if (jobs[-1] / n).exists():
                shutil.copy2(jobs[-1] / n, out / f"blender_{n}")
                renders.append(f"light/blender_{n}")
    lay = make_light_layout(spec)
    ph, ink, pj, tk = spec.photo, spec.ink, spec.projector, spec.tank
    from .electrodope import ElectroDope, describe_edope, electro_dope

    ed0 = ElectroDope(hours=24)
    if cal_file.exists():
        from .lightcal import calibrated_edope

        ed0 = calibrated_edope(cal_file, ed0)
    edope = electro_dope(job, ed0)
    from .lighttools import describe_tools, plan_tools

    if cal_file.exists():
        from .lightcal import calibrated_toolspec

        tools = plan_tools(job, calibrated_toolspec(cal_file))
    else:
        tools = plan_tools(job)
    eit = None
    try:  # 배지 속 전극 감지 — 약 20 s
        from .eit import eit_report

        er = eit_report(job, out_dir=out / "eit")
        eit = {"text": er["text"], "figure": "light/eit/eit.png" if er.get("figure") else None}
    except Exception as e:  # noqa: BLE001 — 웹은 EIT 없이도 만들어져야 함
        eit = {"text": f"EIT 계산 실패: {e}", "figure": None}
    from .lightrun import plan_schedule

    sch = plan_schedule(job, tools)
    start_h = [None] * pl["E"].shape[2]
    marks = []
    for r in sch["rows"]:
        start_h[r["k"]] = round(r["start_s"] / 3600, 3)
        if r["swap_ink"] or r["tool_before"]:
            marks.append({"k": r["k"], "swap": r["swap_ink"], "tool": r["tool_before"]["cells"] if r["tool_before"] else 0})
    return {
        "eit": eit,
        "timeline": {"start_h": start_h, "marks": marks, "total_h": sch["total_s"] / 3600,
                     "after_cells": sum(x["cells"] for x in sch["finals"])},
        "machine": spec.describe(), "layout": lay.describe(), "job_text": describe_job(job) + "\n\n" + describe_tools(tools) + "\n\n" + describe_edope(edope),
        "tools": [{"key": t.key, "name": t.name, "tip": t.tip, "use": t.use} for t in tools["ts"].tools],
        "inject": {"cells": tools["n_inject"], "phases": len(tools["phases"]), "hours": tools["tool_h"],
                   "energy_j": tools["prediction"]["energy_j"], "max_h": tools["max_height_mm"], "tip_z": tools["ts"].head.tip_z},
        "check": spec.check(), "edope_energy_j": edope["prediction"]["energy_j"], "edope_hours": ed0.hours,
        "edope_t90_h": edope["t90_h"],
        "calibrated": cal_file.exists(),
        "renders": renders, "fill_mm": tk.fill_mm, "gz": lay.gz, "well_mm": ink.well_mm, "ink_depth_mm": ink.depth_mm,
        "tank_mm": tk.inner_mm[0], "height_mm": p.height_mm, "n_cells": p.n_cells(), "layers": pl["layers"],
        "layer_mm": spec.layer_mm, "dp_mm": spec.dp_mm(), "dp_green_mm": spec.dp_green_mm(),
        "expose_h": pl["expose_s"] / 3600, "cure_h": spec.cure_h, "ink_life_h": spec.ink_life_h(),
        "cyto_reduced": pl["cyto_reduced"], "mem_leaky": pl["mem_leaky"], "p_graft": pl["p_graft"], "n_graft": pl["n_graft"],
        "energy_j": pr["energy_j"], "undoped_energy_j": job["undoped_energy_j"], "surface_k": spec.surface_rise_k(), "bath_k": spec.heat_rise_k(),
        "ink_density": spec.ink_density(), "bath_density": tk.density, "ccc_mm": spec.ccc_mm(),
        # 어림 계산 (lightsculpt 와 같은 식) 에 쓰는 상수
        "k": {"eps_go": ph.eps_go, "a_sbq": ph.a_sbq, "ec": ph.ec_mj_cm2, "e_red": ph.e_red_mj_cm2, "theta": ph.theta_mem,
              "overcure": ph.overcure, "eps_go_530": ph.eps_go_530, "eps_eosin": ph.eps_eosin, "eosin_um": ink.eosin_um,
              "e_graft_target": spec.e_graft_target(), "pva_wt": ink.pva_wt, "nacl_mm": ink.nacl_mm, "nbd_mm": ink.nbd_mm,
              "go_mg_ml": ink.go_mg_ml, "irr": pj.irradiance_mw_cm2, "irr_g": pj.green_mw_cm2, "reflect": pj.reflect,
              "recoat_s": spec.recoat_s, "rho_water": 997.05, "loss_w_k": tk.heat_loss_w_k},
    }


def _quantum_assets(step_dir: Path) -> dict:
    """양자 모듈 계산(Python) + Rust·C# 교차 검증 + STEP 생성 + OpenCascade 검증 기록."""
    from .cadcheck import generate, last_record, validate
    from .crosscheck import quantum_check
    from .quantum import QuantumModule

    qm = QuantumModule()
    r = qm.report()
    qc = quantum_check()
    generate(step_dir)
    import os

    v = validate(step_dir, os.environ.get("SNSS_OCP_PATH"))
    if "error" in v:
        v = {**(last_record() or {}), "note": v["error"] + " — 아래는 마지막 검증 기록"}
    return {
        "text": qm.describe(),
        "rows": [{"n": x.n, "tau": x.tau, "e": x.energy / x.n, "w": x.ergotropy / x.n, "adv": x.advantage} for x in r["rows"]],
        "exponent": r["exponent"], "charge_fs": r["charge_fs"], "t2_fs": r["t2_fs"], "cavity_fs": r["cavity_fs"],
        "quantum_ok": r["quantum_ok"], "energy_mj": r["max_energy_j"] * 1e3, "lifetime_ns": r["lifetime_ns"],
        "cross": {k: {kk: vv for kk, vv in val.items() if kk != "bad"} | {"bad": val.get("bad", [])}
                  for k, val in qc["languages"].items()},
        "cad": v,
        "steps": sorted(p.name for p in step_dir.glob("*.step")),
    }


def _crosscheck_summary() -> dict:
    from .crosscheck import run_all

    rep = run_all()
    out = {"cases": [], "languages": {}}
    for lang, r in rep["languages"].items():
        if "error" in r:
            out["languages"][lang] = {"error": r["error"][:300]}
            continue
        out["languages"][lang] = {"ok": r["ok"], "cases": {
            name: {"ok": c["ok"], "n": len(c["rows"]),
                   "max_rel": max((x["rel"] for x in c["rows"] if x["rel"] != float("inf")), default=0.0),
                   "bad": [x["key"] for x in c["rows"] if not x["ok"]]}
            for name, c in r["cases"].items()}}
    first = next(iter(rep["python"].values()))
    out["sample"] = {k: first[k] for k in ("ocv_v", "r_int_ohm", "n_cells", "n_inner_ridges", "v_oc_window",
                                           "led_first_off_h", "bulb_best_k", "bulb_glow_min")}
    out["sample_langs"] = {lang: {k: r.get("results", {}).get(next(iter(rep["python"])), {}).get(k)
                                  for k in out["sample"]} for lang, r in rep["languages"].items()}
    return out


def _fractal_assets(battery, img_dir: Path) -> dict:
    """보로노이·프랙탈 회로망 계산 + 그림 (현재 배합, 스윕, D×거칠기 지도)."""
    from .plots import (plot_box_counting, plot_fractal_map, plot_fractal_sweeps, plot_voronoi_section,
                        plot_voronoi_stats)
    from .tessellation import FractalVoronoiParams, analyze, analyze_battery, sweep_interface_dimension, sweep_roughness

    s = battery.stack
    t, n_tot, area = battery.formation.layer_thickness_mm, 2 * s.n_pairs, battery.gel_area_cm2 * 100
    res = analyze_battery(battery)
    base = battery.fractal_params(window_layers=24)
    by_d = sweep_interface_dimension(s, t, n_tot, area, base)
    by_r = sweep_roughness(s, t, n_tot, area, base)
    dims, roughs = [1.0, 1.2, 1.4, 1.6, 1.8], [0.0, 0.3, 0.6, 0.9, 1.2]
    corr = battery.formation.interface_correlation
    grid = [[analyze(s, t, n_tot, area, FractalVoronoiParams(d if r > 0 else 1.0, r, corr, 2.0,
                                                             battery.formation.grains_per_layer, 16, 6.0),
                     keep_geometry=False) for d in dims] for r in roughs]
    _save(lambda f: plot_voronoi_section(f, res), img_dir / "voronoi_section.png", size=(11, 6))
    _save(lambda f: plot_fractal_map(f, grid, dims, roughs), img_dir / "fractal_map.png", size=(9, 5))
    _save(lambda f: plot_fractal_sweeps(f, by_d, by_r), img_dir / "fractal_sweeps.png", size=(12, 4.6))
    _save(lambda f: plot_box_counting(f, res), img_dir / "box_counting.png", size=(6.5, 4.8))
    _save(lambda f: plot_voronoi_stats(f, res), img_dir / "voronoi_stats.png", size=(9, 4.2))
    p = res.params
    return {
        "params": {"interface_dimension": p.interface_dimension, "roughness": p.roughness,
                   "correlation": p.correlation, "seed_dimension": p.seed_dimension,
                   "grains_per_layer": p.grains_per_layer},
        "layer_mm": t, "ocv": res.ocv_v, "leak_ma": res.leak_current_ma, "text": res.describe(),
        "map": {"dims": dims, "roughs": roughs, "correlation": corr,
                "V": [[round(r.ocv_v, 3) for r in row] for row in grid],
                "P": [[round(max(r.max_power_mw - r.leak_current_ma * r.ocv_v, 0), 2) for r in row] for row in grid]},
    }


# ---------- 서버 ----------
def _make_handler(site: Path, log_path: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(site), **kwargs)

        def log_message(self, fmt, *args) -> None:  # 접속 로그 생략
            pass

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            route = self.path.split("?")[0]
            if route == "/api/experiments":
                self._json(200, read_experiments(log_path))
            elif route == "/api/verdict":
                self._json(200, verdict(log_path))
            elif route == "/api/lightcal":
                self._json(200, lightcal_state())
            else:
                super().do_GET()

        def do_POST(self) -> None:
            if self.path == "/api/lightcal":
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    if n > 100_000:
                        raise ValueError("요청이 너무 큽니다.")
                    self._json(200, lightcal_fit(json.loads(self.rfile.read(n) or b"{}")))
                except (ValueError, KeyError, json.JSONDecodeError) as e:
                    self._json(400, {"error": str(e)})
                return
            if self.path != "/api/experiments":
                self._json(404, {"error": "not found"})
                return
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n > 100_000:
                    raise ValueError("요청이 너무 큽니다.")
                rec = add_experiment(log_path, json.loads(self.rfile.read(n) or b"{}"))
            except (ValueError, json.JSONDecodeError) as e:
                self._json(400, {"error": str(e)})
                return
            self._json(201, rec)

        def do_DELETE(self) -> None:
            prefix = "/api/experiments/"
            if not self.path.startswith(prefix):
                self._json(404, {"error": "not found"})
                return
            ok = delete_experiment(log_path, self.path[len(prefix):])
            self._json(200 if ok else 404, {"deleted": ok})

    return Handler


LIGHT_CAL_DIR = ROOT / "sculpt_out" / "light_cal"


def lightcal_state() -> dict:
    """콘솔의 시험편 측정표: 사다리 노출(전위) · 지금까지 적은 측정값 · 보정 결과."""
    import csv

    from .lightcal import EDOPE_V, INJ_RATIO, LEAK_PAIRS, ladders

    lad = ladders()
    rows = [{"test": t, "i": i + 1, "x": float(x), "value": ""} for t in "ABC" for i, x in enumerate(lad[t])]
    rows += [{"test": "D", "i": i + 1, "x": float(v), "value": ""} for i, v in enumerate(EDOPE_V)]
    rows += [{"test": "E", "i": i + 1, "x": float(r), "value": ""} for i, r in enumerate(INJ_RATIO)]
    rows += [{"test": "F", "i": i + 1, "x": float(1 - i % 2), "value": ""} for i in range(2 * LEAK_PAIRS)]
    meas = LIGHT_CAL_DIR / "measurements.csv"
    if meas.exists():
        with open(meas, encoding="utf-8") as f:
            have = {(r["시험"], int(r["칸"])): (r.get("측정값") or "").strip() for r in csv.DictReader(f)}
        for r in rows:
            r["value"] = have.get((r["test"], r["i"]), "")
    cal = ROOT / "sculpt_out" / "light_cal.json"
    out = {"rows": rows, "calibrated": cal.exists()}
    if cal.exists():
        from .lightcal import describe_calibration

        out["text"] = describe_calibration(json.loads(cal.read_text(encoding="utf-8")))
    return out


def lightcal_fit(body: dict) -> dict:
    """측정표 저장 → 맞춤 → sculpt_out/light_cal.json (웹 콘솔을 다시 만들면 보정값으로)."""
    from .lightcal import describe_calibration, fit_calibration

    unit = {"A": "mm", "B": "ohm", "C": "mV", "D": "mV", "E": "mV", "F": "mV"}
    lines = ["시험,칸,노출_mJ_cm2,측정값,단위,메모"]
    for r in body["rows"]:
        t = str(r["test"])
        if t not in unit:
            raise ValueError(f"시험 이름이 이상합니다: {t}")
        v = str(r.get("value", "")).strip()
        if v:
            float(v)  # 숫자인지
        memo = {"D": "전위 V", "E": "PEI:GO 질량비", "F": "주입한 칸" if float(r["x"]) else "막 너머 이웃 칸"}.get(t, "")
        lines.append(f"{t},{int(r['i'])},{float(r['x']):g},{v},{unit[t]},{memo}")
    LIGHT_CAL_DIR.mkdir(parents=True, exist_ok=True)
    demo = bool(body.get("demo"))  # 연습값은 진짜 보정값으로 저장하지 않음
    meas = LIGHT_CAL_DIR / ("demo_measurements.csv" if demo else "measurements.csv")
    meas.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cal = fit_calibration(meas)
    if demo:
        return {"text": describe_calibration(cal) + "\n(연습값 — light_cal.json 에 저장하지 않음)", "calibrated": False}
    (ROOT / "sculpt_out" / "light_cal.json").write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"text": describe_calibration(cal) + "\n저장: sculpt_out/light_cal.json — 웹을 다시 만들면(./tools.sh web) 콘솔이 보정값으로 계산",
            "calibrated": True}


def verdict(log_path: Path) -> dict:
    """C# 판정기(Snss.Lab verify)로 실험 기록을 사전 등록 가설에 따라 판정."""
    import shutil
    import subprocess

    if not LAB_DLL.exists() or not shutil.which("dotnet"):
        return {"error": "C# 판정기가 빌드되지 않았습니다: cd csharp && dotnet build Snss.Lab -c Release"}
    try:
        p = subprocess.run(["dotnet", str(LAB_DLL), "verify", str(log_path)], capture_output=True, text=True, timeout=60)
        return json.loads(p.stdout) if p.returncode == 0 else {"error": p.stderr[-500:]}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"error": str(e)}


def read_experiments(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    out = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def add_experiment(log_path: Path, data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 필요합니다.")
    rec = {"id": uuid.uuid4().hex[:12], "created": _dt.datetime.now().isoformat(timespec="seconds")}
    for k in EXPERIMENT_FIELDS:
        v = data.get(k, "")
        if k in _TEXT_FIELDS:
            rec[k] = str(v)[:500]
        elif v in ("", None):
            rec[k] = None
        else:
            try:
                rec[k] = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k} 값은 숫자여야 합니다: {v!r}") from None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def delete_experiment(log_path: Path, rec_id: str) -> bool:
    recs = read_experiments(log_path)
    keep = [r for r in recs if r.get("id") != rec_id]
    if len(keep) == len(recs):
        return False
    log_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), encoding="utf-8")
    return True


def _is_snss_server(host: str, port: int) -> bool:
    from urllib.request import urlopen

    try:
        with urlopen(f"http://{host}:{port}/", timeout=2) as r:
            return "SNSS" in r.read(4096).decode("utf-8", "ignore")
    except OSError:
        return False


def serve(folder: str | Path, port: int = 8765, host: str = "127.0.0.1", tries: int = 10,
          log_path: str | Path | None = None) -> None:
    """포트가 사용 중이면 다음 포트를 시도. Ctrl+C 로 종료."""
    import errno

    site = Path(folder).resolve()
    log = Path(log_path) if log_path else site.parent / "experiments" / "log.jsonl"
    handler = _make_handler(site, log)
    for p in range(port, port + tries):
        try:
            httpd = ThreadingHTTPServer((host, p), handler)
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
            note = "이미 실행 중인 SNSS 뷰어" if _is_snss_server(host, p) else "다른 프로그램"
            print(f"포트 {p} 사용 중 ({note}: http://{host}:{p}/) → 다음 포트 시도", flush=True)
            continue
        with httpd:
            print(f"SNSS 웹 뷰어: http://{host}:{p}/  (종료: Ctrl+C)", flush=True)
            print(f"실험 기록 파일: {log}", flush=True)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n서버 종료")
        return
    raise OSError(f"포트 {port}~{port + tries - 1}이 모두 사용 중입니다. --port 로 다른 포트를 지정하세요.")


_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SNSS 결정 배터리</title>
<style>
:root {
  --bg: #f6f7f9; --panel: #ffffff; --ink: #1b1f24; --muted: #5d6673; --line: #dfe3e8;
  --accent: #1d5fa8; --accent-soft: #e6eef8; --ok: #2f8a4f; --bad: #b3261e;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg: #15181c; --panel: #1e2227; --ink: #e8ebef; --muted: #9aa4b1; --line: #313740;
          --accent: #7fb2e5; --accent-soft: #23303f; --ok: #6cc08b; --bad: #f2867e; }
}
:root[data-theme="dark"] { --bg: #15181c; --panel: #1e2227; --ink: #e8ebef; --muted: #9aa4b1; --line: #313740;
          --accent: #7fb2e5; --accent-soft: #23303f; --ok: #6cc08b; --bad: #f2867e; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 14px/1.55 "NanumGothic", "Noto Sans KR", "Malgun Gothic", system-ui, sans-serif; }
header { padding: 18px 24px 0; }
h1 { margin: 0 0 4px; font-size: 22px; }
.sub { color: var(--muted); margin: 0 0 14px; }
nav { display: flex; gap: 4px; flex-wrap: wrap; padding: 0 24px; border-bottom: 1px solid var(--line); }
nav button { border: 0; background: none; color: var(--muted); padding: 10px 14px; font: inherit;
             cursor: pointer; border-bottom: 2px solid transparent; }
nav button.on { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
main { padding: 20px 24px 40px; }
section { display: none; } section.on { display: block; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; margin-bottom: 18px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.sc-view { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 12px; margin-bottom: 18px; }
.sc-stage { position: relative; min-height: 460px; background: radial-gradient(circle at 50% 40%, #2a3340, #0f1318); border-radius: 10px; overflow: hidden; }
.sc-stage canvas { display: block; width: 100%; height: 100%; }
.sc-msg { position: absolute; inset: 0; display: grid; place-items: center; color: #c9d2dc; }
.sc-side { display: flex; flex-direction: column; gap: 10px; }
.sc-side input[type=range] { width: 100%; } .sc-side label { display: block; margin: 2px 0; }
.sc-val { color: var(--muted); font-size: 12px; margin: 2px 0 6px; font-variant-numeric: tabular-nums; }
@media (max-width: 760px) { .sc-view { grid-template-columns: 1fr; } }
.lc-view { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr) 230px; gap: 12px; margin-bottom: 18px; }
.lc-frame { display: flex; flex-direction: column; gap: 6px; }
.lc-frame canvas { width: 100%; aspect-ratio: 640 / 400; background: #000; border-radius: 10px; image-rendering: pixelated; cursor: crosshair; }
.lc-frame canvas:focus { outline: 2px solid var(--accent); }
.lc-head { display: flex; gap: 8px; align-items: baseline; }
.lc-stage { min-height: 420px; }
.lc-marks { position: relative; height: 10px; margin: 0 8px 4px; }
.lc-marks span { position: absolute; top: 0; width: 4px; height: 10px; margin-left: -2px; border-radius: 2px; background: var(--muted); }
.lc-marks span.tool { background: #2f9e5a; } .lc-marks span.swap { background: #c47f17; } .lc-marks span.swap.tool { background: linear-gradient(#c47f17, #2f9e5a); }
.lc-whatif { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 6px 16px; margin-bottom: 10px; }
.lc-whatif label { color: var(--muted); font-size: 13px; } .lc-whatif input { width: 100%; }
@media (max-width: 1000px) { .lc-view { grid-template-columns: 1fr; } }
.lc-cal { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; margin: 8px 0; }
.lc-cal table { width: 100%; } .lc-cal input { width: 90px; font: inherit; }
.card .k { color: var(--muted); font-size: 12px; } .card .v { font-size: 15px; font-weight: 600; margin-top: 2px; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-weight: 600; }
.badge.ok { background: color-mix(in srgb, var(--ok) 18%, transparent); color: var(--ok); }
.badge.bad { background: color-mix(in srgb, var(--bad) 18%, transparent); color: var(--bad); }
pre { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px;
      overflow-x: auto; font: 12.5px/1.5 "NanumGothicCoding", ui-monospace, monospace; }
.sheet { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 6px; margin-bottom: 16px; }
.sheet img { width: 100%; display: block; }
img.fig { max-width: 100%; background: #fff; border-radius: 10px; border: 1px solid var(--line); margin: 6px 0 16px; }
table { border-collapse: collapse; width: 100%; background: var(--panel); border-radius: 10px; overflow: hidden; margin-bottom: 12px; }
th, td { border-bottom: 1px solid var(--line); padding: 7px 10px; text-align: left; vertical-align: top; }
th { background: var(--accent-soft); font-weight: 600; }
td.n { text-align: right; font-variant-numeric: tabular-nums; }
tr.gone td { color: var(--muted); }
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 0 0 10px; }
.row label { color: var(--muted); }
button, input, select, textarea { font: inherit; }
button.primary { background: var(--accent); color: var(--panel); border: 0; border-radius: 8px; padding: 7px 14px; cursor: pointer; font-weight: 600; }
button.ghost { background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: 8px; padding: 6px 12px; cursor: pointer; }
a { color: var(--accent); }
h2 { font-size: 16px; margin: 18px 0 8px; }
/* 결정화 과정 */
.proc { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; }
@media (max-width: 900px) { .proc { grid-template-columns: 1fr; } }
.stagebox { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
#proc { display: block; width: 100%; height: 600px; background: #fbfcfd; }
.ctl { display: flex; gap: 10px; align-items: center; padding: 10px 12px; border-top: 1px solid var(--line); flex-wrap: wrap; }
.ctl input[type=range] { flex: 1; min-width: 180px; }
aside .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; }
.stages { list-style: none; margin: 0; padding: 0; }
.stages li { padding: 7px 8px; border-radius: 8px; color: var(--muted); cursor: pointer; }
.stages li.on { background: var(--accent-soft); color: var(--ink); font-weight: 600; }
.stages li small { display: block; font-weight: 400; color: var(--muted); }
.metric { display: flex; justify-content: space-between; padding: 3px 0; }
.metric b { font-variant-numeric: tabular-nums; }
/* 3D */
#viewer { position: relative; height: min(72vh, 720px); background: var(--panel); border: 1px solid var(--line);
          border-radius: 10px; overflow: hidden; }
#viewer canvas { display: block; }
#legend { position: absolute; left: 12px; top: 12px; background: color-mix(in srgb, var(--panel) 88%, transparent);
          border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; font-size: 12px; }
#legend div { display: flex; align-items: center; gap: 6px; }
#legend i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; border: 1px solid #0003; }
#msg { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); }
/* 실험 기록 */
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px 14px; background: var(--panel);
        border: 1px solid var(--line); border-radius: 10px; padding: 14px; margin-bottom: 14px; }
.form label { display: flex; flex-direction: column; gap: 3px; color: var(--muted); font-size: 12px; }
.form input, .form select, .form textarea { color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; }
.form .wide { grid-column: 1 / -1; }
#chart { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; width: 100%; height: auto; aspect-ratio: 900 / 280; display: block; margin-bottom: 14px; }
#logMsg { color: var(--muted); }
</style>
<link rel="stylesheet" href="ui/ui.css">
</head>
<body>
<header class="app">
  <svg class="logo" viewBox="0 0 40 40" aria-hidden="true">
    <rect x="9" y="3" width="22" height="34" rx="6" fill="#dfe9f3" opacity=".25" stroke="#9fc7ff" stroke-width="1.5"/>
    <rect x="15" y="0.8" width="10" height="4" rx="1.5" fill="#3b7dd8"/>
    <rect x="11.5" y="14" width="17" height="3" fill="#9cc9e4"/><rect x="11.5" y="17" width="17" height="0.9" fill="#e8833a"/>
    <rect x="11.5" y="17.9" width="17" height="3" fill="#2c6fb0"/><rect x="11.5" y="20.9" width="17" height="0.9" fill="#3a9a5b"/>
    <rect x="11.5" y="21.8" width="17" height="3" fill="#9cc9e4"/><rect x="11.5" y="24.8" width="17" height="0.9" fill="#e8833a"/>
    <rect x="11.5" y="25.7" width="17" height="3" fill="#2c6fb0"/><rect x="11.5" y="28.7" width="17" height="0.9" fill="#3a9a5b"/>
    <rect x="11.5" y="29.6" width="17" height="5" rx="2" fill="#9cc9e4"/>
  </svg>
  <div>
    <h1 id="title"></h1>
    <p class="sub">약국 생리식염수 통에서 그래핀 폴리머 액정 + 반응 화학물질로 결정화 → 결정 자체가 전지 · 별도 전극·부품·금속 없음 · <span id="audit"></span></p>
  </div>
</header>
<nav id="tabs"></nav>
<main>
  <section data-id="console" data-tab="빛 조각가 · 콘솔">
    <p class="sub"><b>SNSS 빛 조각가 SC-2</b> — 펜이 없습니다. <b>배양조 속 멸균생리식염수가 곧 모니터</b>이고, 수조 아래 데스크톱이 설계를 층마다
      빛 그림으로 바꿔 수조 위 두 색 프로젝터로 비춥니다. 배지 위에 뜬 잉크층(염 10 mM · GO · 감광 PVA · NBD · 에오신 Y)에서
      <b style="color:#8a4dff">405 nm</b> 가 닿은 곳이 굳고(세게 받으면 rGO 세포질), <b style="color:#2f9e5a">530 nm</b> 가 닿은 곳만 p 도핑 —
      받침이 한 층 내려가면 그 층이 멸균생리식염수에 닿아 엉기며 고정됩니다. 조작은 방수 키보드 · 마우스로 (아래 단축키).</p>
    <div class="cards" id="lcCards"></div>
    <div class="lc-view">
      <div class="lc-frame">
        <div class="lc-head"><b>프로젝터 화면</b> <span id="lcLayerV" class="sc-val"></span></div>
        <canvas id="lcFrame" width="640" height="400" tabindex="0" aria-label="층 빛 그림"></canvas>
        <div class="sc-val" id="lcHover">칸에 마우스를 올리면 노출량 · 재료</div>
      </div>
      <div class="sc-stage lc-stage" id="lcTank"><div class="sc-msg" id="lcMsg">3D 불러오는 중…</div></div>
      <aside class="sc-side">
        <div class="lab-card"><h3>층</h3>
          <input type="range" id="lcLayer" min="0" max="1" value="0">
          <div class="sc-val" id="lcTimeV"></div>
          <button class="primary" id="lcPlay" type="button">▶ 빚기 재생 (Space)</button></div>
        <div class="lab-card"><h3>빛 (1 · 2 · 3)</h3>
          <label><input type="radio" name="lcCh" value="both" checked> 둘 다</label>
          <label><input type="radio" name="lcCh" value="v"> 405 nm 굳힘 · 광환원</label>
          <label><input type="radio" name="lcCh" value="g"> 530 nm p 도핑</label></div>
        <div class="lab-card"><h3>방수 키보드 · 마우스</h3>
          <div class="sc-val">← → 한 층 · ↑ ↓ 열 층 · Home End 처음 · 끝<br>Space 재생 · 1 2 3 빛 · R 시점<br>
            화면 위 휠 = 층 · 클릭 = 칸 고정 · 3D 끌기 = 돌려 보기</div></div>
      </aside>
    </div>
    <h2>조각 도구 — 물속 갠트리 (빛을 쬘 때는 뒤쪽에 주차)</h2>
    <p class="sub">빛이 몸을 빚고, 주사기가 빛이 못 하는 것을 합니다 — 허공 획 · 덧붙이기(SC-1 레시피, 멸균생리식염수 속 도구 면에서 굳음),
      n 세포마다 PEI 주입, 깎기 · 떼기 · 붙이기 · 재기. 물속 도구에 금속 없음 (유리 미세 피펫 · PEEK). 명령: <code>light-tool add|carve|detach|draw|attach</code></p>
    <table id="lcTools"></table>
    <h2>데스크톱 어림 — 잉크 · 빛을 바꾸면</h2>
    <p class="sub">lightsculpt.py 와 같은 식으로 바로 어림합니다 (층 그림 전체는 <code>python -m snss_battery light being --go … --irradiance …</code>).</p>
    <div class="lc-whatif">
      <label>잉크 GO <input type="range" id="wGo" min="0.5" max="5" step="0.1"> <span id="wGoV"></span></label>
      <label>405 nm 세기 <input type="range" id="wI" min="2" max="20" step="0.5"> <span id="wIV"></span></label>
      <label>530 nm 세기 <input type="range" id="wIg" min="2" max="20" step="0.5"> <span id="wIgV"></span></label>
      <label>감광 PVA <input type="range" id="wPva" min="0.2" max="5" step="0.1"> <span id="wPvaV"></span></label>
    </div>
    <table id="lcWhatIf"></table>
    <h2>시험편 측정 → 빛 상수 보정</h2>
    <p class="sub">보정 시험편(<code>./tools.sh light-cal</code>)을 재서 측정값을 적고 <b>맞추기</b> — A 굳은 두께 mm · B 2단자 저항 Ω ·
      C 개방 전위 차 mV · D 전기 도핑 개방 전위 차 mV. 빈 칸은 건너뜀 (A 3칸 · B C 4칸 · D 5칸 이상이면 그 시험을 맞춤). 서버(./tools.sh web)에서만 저장됩니다.</p>
    <div class="row"><button class="primary" id="lcCalFit" type="button">맞추기 · 저장</button>
      <button id="lcCalDemo" type="button">연습값 채우기 (참값을 아는 가상 측정)</button></div>
    <div class="lc-cal" id="lcCal"></div>
    <pre id="lcCalText"></pre>
    <h2>배지 속 전극 감지 (EIT) — 빚는 동안 전기장으로 봄</h2>
    <p class="sub">흑연 전극 32개 (잉크 우물 테 아래 한 줄 + 받침 가장자리 한 줄, 도구 갠트리와 안 부딪힘) · 교류 10 kHz 20 mV ·
      갠트리가 주차했을 때만. 자람은 한 층마다 보이고, 덧굳은 덩어리는 16 mm 부터 (10층 평균이면 11 mm). 명령: <code>./tools.sh light-eit</code></p>
    <div id="lcEit"></div>
    <div id="lcRenders"></div>
    <h2>기계 · 공간 배치 · 이 작업</h2>
    <pre id="lcText"></pre>
  </section>
  <section data-id="sculptor" data-tab="조각가 · 존재">
    <p class="sub"><b>SNSS 조각가 SC-1</b> — 3D 펜을 단 상온 3D 프린터. GO · SNSS(멸균생리식염수) · PVA 가 따로 펜에 들어가
      펜 끝에서 처음 만나 하나가 되고, 그 젤로 <b>양자 인공세포</b>가 모인 존재를 빚습니다. <b>수중 환경</b> — 기계까지 통째로 멸균생리식염수(배지) 배양조에 잠겨
      세포 배양하듯 결정체를 키웁니다 (젖는 쪽은 비금속, 모터 · 전자는 방수 통). 잉크는 배지에 닿으며 굳고 거의 떠 있듯 버티며, 다 자라면 받침째 꺼냅니다. 층을 더하고, 깎고, 떼고, 다시 붙일 수 있습니다 (전부 상온).</p>
    <div class="cards" id="scCards"></div>
    <div class="sc-view">
      <div class="sc-stage" id="scView"><div class="sc-msg" id="scMsg">3D 불러오는 중…</div></div>
      <aside class="sc-side">
        <div class="lab-card"><h3>깨어남</h3>
          <input type="range" id="scTime" min="0" max="1000" value="1000"><div class="sc-val" id="scTimeV"></div>
          <button class="primary" id="scWake" type="button">▶ 발에 0.8 V — 깨우기</button></div>
        <div class="lab-card"><h3>빚기 (아래에서 위로)</h3>
          <input type="range" id="scHeight" min="0" max="1000" value="1000"><div class="sc-val" id="scHeightV"></div>
          <button id="scBuild" type="button">▶ 쌓기 재생</button></div>
        <div class="lab-card"><h3>보기</h3>
          <label><input type="checkbox" id="scSkin" checked> 막 · 피부</label>
          <label><input type="checkbox" id="scPos" checked> p 세포 (+)</label>
          <label><input type="checkbox" id="scNeg" checked> n 세포 (−)</label></div>
      </aside>
    </div>
    <h2>펜 끝 — 세 원료가 하나가 되는 비율</h2>
    <table id="scRecipes"></table>
    <h2>양자층 — 그래핀 양자 커패시턴스와 세포별 도핑</h2>
    <img class="fig" src="sculpt/quantum.png" alt="양자층">
    <h2>생명 신호 — 세포 단위 두 회로망 (전자 + 전해질)</h2>
    <img class="fig" src="sculpt/wake.png" alt="깨어남">
    <h2>출력 단면 — 세포질 (p 빨강 · n 파랑) · 막 · 피부</h2>
    <img class="fig" src="sculpt/slices.png" alt="단면">
    <div id="scRenders"></div>
    <h2>바깥 연결 — 아날로그 · 디지털 · 양자 공학기기 호환</h2>
    <p class="sub">존재의 발 단자는 BNC 로 오실로스코프·멀티미터·포텐시오스탯에, 조각가 자체는 SCPI(TCP 5025)로 계측기처럼,
      양자 계측기와는 10 MHz/1 PPS 시간 동기 · 층 트리거 · 양자 난수(세포 씨앗) · C–V 되먹임(페르미 준위 역산)으로 이어집니다.</p>
    <table id="scPorts"></table>
    <h2>만드는 법 — 부품은 3D 프린터로, 원료는 시중에서</h2>
    <div id="scPartsImg"></div>
    <table id="scParts"></table>
    <h3>시중에서 사는 것</h3>
    <table id="scBuy"></table>
    <h2>작업 · 파일</h2>
    <table id="scJob"></table>
    <pre id="scText"></pre>
  </section>
  <section data-id="lab" data-tab="실험대">
    <div class="lab">
      <div class="lab-bar">
        <span class="samplebar">시료 <select id="labSample"></select></span>
        <button class="primary" id="labPlay" type="button">▶ 재생</button>
        <button id="labPrev" type="button" title="이전 단계">◀</button><button id="labNext" type="button" title="다음 단계">▶</button>
        <label>속도 <select id="labSpeed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></label>
        <div class="prog" id="labProg" title="눌러서 이동"><i id="labBar"></i></div>
        <span class="clock" id="labClock"></span>
      </div>
      <div class="lab-body">
        <div class="lab-stage"><canvas id="labC"></canvas></div>
        <aside class="lab-side">
          <div class="lab-card"><h3>계기</h3><div class="lcd" id="labLcd"></div></div>
          <div class="lab-card"><h3>실험 노트 — 이 단계의 양</h3><div class="notebook" id="labNote"></div></div>
          <div class="lab-card"><h3>절차 (RECIPE.md)</h3><ol class="lab-steps" id="labSteps"></ol></div>
        </aside>
      </div>
    </div>
    <p class="note-line" id="labSampleNote"></p>
    <p class="note-line">가상 실험입니다. 양은 레시피 계산기(Python·Rust·C# 교차 검증)의 값이고, 전압·전류는 모델 예측입니다. 실제 결과는 '실험 기록'에 남겨 사전 등록 가설(H1~H7)로 판정하세요.</p>
  </section>
  <section data-id="cad" data-tab="CAD 작업대">
    <div class="wb">
      <div class="wb-bar">
        <span class="samplebar"><span class="lbl">시료</span><select id="wbSample"></select></span>
        <span class="sep"></span><span class="lbl">시점</span>
        <button class="tb on" data-view="iso" title="등각"><svg viewBox="0 0 24 24"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/></svg>등각</button>
        <button class="tb" data-view="front" title="정면"><svg viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14"/></svg>정면</button>
        <button class="tb" data-view="top" title="윗면"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="1.5"/></svg>윗면</button>
        <button class="tb" data-view="right" title="우측"><svg viewBox="0 0 24 24"><path d="M7 4h10v16H7z"/><path d="M17 4l3 2v16l-3-2"/></svg>우측</button>
        <button class="tb" id="wbFit" title="맞춤"><svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>맞춤</button>
        <span class="sep"></span>
        <button class="tb on" data-proj="persp" title="원근 투영">원근</button><button class="tb" data-proj="ortho" title="직교 투영">직교</button>
        <span class="sep"></span><span class="lbl">표시</span>
        <button class="tb" data-mode="shade" title="음영">음영</button>
        <button class="tb on" data-mode="edges" title="음영 + 모서리">모서리</button>
        <button class="tb" data-mode="wire" title="와이어프레임">와이어</button>
        <span class="sep"></span>
        <button class="tb" id="wbSection" title="단면 (XZ 평면)"><svg viewBox="0 0 24 24"><path d="M4 12h16"/><path d="M7 5h10v14H7z" stroke-dasharray="2 2"/></svg>단면</button>
        <button class="tb on" id="wbDims" title="치수"><svg viewBox="0 0 24 24"><path d="M4 8v8M20 8v8M4 12h16M7 9l-3 3 3 3M17 9l3 3-3 3"/></svg>치수</button>
        <button class="tb on" id="wbGrid" title="격자"><svg viewBox="0 0 24 24"><path d="M4 4h16v16H4zM4 9.3h16M4 14.6h16M9.3 4v16M14.6 4v16"/></svg>격자</button>
        <span class="sep"></span><span class="lbl">내보내기</span>
        <button class="tb" id="wbSTL" title="결정 블록 STL (mm)"><svg viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>STL</button>
        <button class="tb" id="wbPNG" title="화면 PNG"><svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="13" rx="2"/><circle cx="12" cy="12.5" r="3.5"/><path d="M8 6l1.5-2h5L16 6"/></svg>PNG</button>
      </div>
      <div class="wb-body">
        <aside class="wb-tree"><div class="wb-h">모델 트리</div><ul id="wbTree"></ul></aside>
        <div class="wb-view" id="wbView">
          <div class="ovl" id="wbMsg">3D 모델 불러오는 중…</div>
          <div class="wb-title" id="wbTitle"></div>
          <div class="ovl" id="wbTip"></div>
          <div class="ovl wb-corner"><div class="lab-card" id="wbMeter" style="display:none;background:#10181a;border-color:#000;color:#9cf0c5;text-align:right;padding:6px 10px">
          </div></div>
        </div>
        <aside class="wb-prop"><div class="wb-h">속성</div><table id="wbProps"></table><div class="wb-h">시료 예측 (모델)</div><table id="wbPred"></table>
          <div class="wb-h">조작</div><div style="padding:8px 10px;color:#8c99a8;font-size:12px;line-height:1.6">왼쪽 드래그 회전 · 휠 확대 · 오른쪽 드래그 이동<br>층·벽·병·프로브를 눌러 선택 → 속성 표시<br>모델 트리 ◉ 로 보이기/숨기기</div></aside>
      </div>
      <div class="wb-tl">
        <label>과정 <input type="range" id="wbProc" min="0" max="200" value="0"></label><span class="stage" id="wbStage"></span>
        <label>분해도 <input type="range" id="wbExp" min="0" max="100" value="0"></label>
        <label>단면 위치 <input type="range" id="wbSecPos" min="-35" max="35" step="0.1" value="0"></label>
      </div>
      <div class="wb-status" id="wbStatus"></div>
    </div>
    <p class="note-line">결정 표면 무늬는 같은 보로노이 규칙으로 세포 크기만 ×12 확대해 그린 것이고, 상세도 A 는 실제 계산한 세포(1.34 × 1.34 × 3 mm)입니다. 층·극성은 없습니다. 2D 도면은 '실물 도면' 탭에 있습니다.</p>
  </section>
  <section data-id="process" data-tab="결정화 과정">
    <p class="sub">병 속 식염수에서 결정이 바로 생겨 세포가 되는 과정의 <b>2D 단면</b> 모식도입니다 (보로노이 결정핵 + 프랙탈 동결 전선, 층·극성 없음).
      같은 규칙으로 만든 <b>3D 인공세포 조직</b>은 <a href="#cad">CAD 작업대</a>, 실제 절차(방향성 동결)는 <a href="#lab">실험대</a>에서 볼 수 있습니다.</p>
    <div class="proc">
      <div class="stagebox">
        <canvas id="proc"></canvas>
        <div class="ctl">
          <button class="primary" id="play">▶ 재생</button>
          <input type="range" id="t" min="0" max="1000" value="0">
          <label>속도 <select id="speed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label>
        </div>
      </div>
      <aside>
        <div class="panel"><ul class="stages" id="stages"></ul></div>
        <div class="panel" id="metrics"></div>
        <div class="panel sub" style="margin:0">표시는 이해를 위한 2D 단면 모식도입니다 (세포 크기 확대). 층·극성은 없고, 모든 세포가 같은 종류입니다.<span id="dispRows" hidden></span><span id="realRows" hidden></span>
          실제 걸리는 시간은 실험으로 측정해 '실험 기록'에 남겨 주세요.</div>
      </aside>
    </div>
  </section>
  <section data-id="fractal" data-tab="보로노이·프랙탈">
    <p class="note-line" style="margin:0 0 10px;padding:6px 10px;border-left:3px solid #e07a1f;background:var(--accent-soft)"><b>비교용 · 이전 층 모델</b> — 이 탭은 묽은/진한 층이 번갈아 쌓인다고 가정했던 이전 모델의 해석입니다. 지금 구조(통째 결정 · 층·극성 없는 인공세포)는 <a href="#cad">CAD 작업대</a>와 <a href="#lab">실험대</a>에 있습니다.</p>
    <p class="sub">결정화 = 결정핵에서 자란 도메인들이 만나는 곳이 벽 → <b>보로노이 분할</b>. 묽은/진한 층의 경계는 <b>프랙탈 곡선</b>,
      결정핵 분포는 <b>프랙탈 점집합</b>. 아래 단면은 슬라이더에 따라 바로 다시 계산됩니다.</p>
    <div class="proc">
      <div class="stagebox">
        <canvas id="vx" style="display:block;width:100%;height:440px;background:#fbfcfd"></canvas>
        <div class="ctl" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px 16px">
          <label>층 경계 프랙탈 차원 D <b id="vD"></b><input type="range" id="sD" min="1" max="1.9" step="0.05"></label>
          <label>층 경계 거칠기 (×층 두께) <b id="vR"></b><input type="range" id="sR" min="0" max="1.5" step="0.05"></label>
          <label>층 경계 상관도 <b id="vC"></b><input type="range" id="sC" min="0" max="1" step="0.05"></label>
          <label>결정핵 분포 프랙탈 차원 <b id="vS"></b><input type="range" id="sS" min="1.2" max="2" step="0.05"></label>
          <label>층 두께당 결정핵 수 <b id="vG"></b><input type="range" id="sG" min="1.5" max="6" step="0.5"></label>
          <label><span>새 무작위 배치</span><button class="ghost" id="reseed" type="button">다시 뿌리기</button></label>
        </div>
      </div>
      <aside>
        <div class="panel" id="vMetrics"></div>
        <div class="panel sub" style="margin:0">전압·전력은 Python 보로노이 회로망 계산(상관도 <b id="mapCorr"></b>, 결정핵 고른 분포 기준)을
          D × 거칠기 지도로 미리 구해 보간한 값입니다. 정확한 값은 <code>python3 -m snss_battery fractal</code>.</div>
      </aside>
    </div>
    <h2>회로망 계산 결과 (현재 배합)</h2>
    <pre id="vText"></pre>
    <div id="vorSvgs"></div>
    <img class="fig" src="img/fractal_map.png" alt="출력 지도">
    <img class="fig" src="img/fractal_sweeps.png" alt="스윕">
    <div class="row" style="align-items:flex-start">
      <img class="fig" src="img/box_counting.png" alt="박스 카운팅" style="max-width:48%">
      <img class="fig" src="img/voronoi_stats.png" alt="보로노이 통계" style="max-width:48%">
    </div>
    <h2>실험 사진 프랙탈 분석</h2>
    <p class="sub">결정 단면(또는 표면) 사진을 올리면 도메인 벽(어두운 선)을 골라 박스 카운팅으로 프랙탈 차원을 잽니다. 사진은 이 브라우저 안에서만 처리됩니다.</p>
    <div class="row">
      <input type="file" id="photo" accept="image/*">
      <button class="ghost" type="button" id="demoPhoto">예시: 모델 단면 그림으로 시험</button>
      <label>문턱값 <input type="range" id="thr" min="0" max="255" value="110"></label>
      <label><input type="checkbox" id="inv"> 밝은 선이 벽</label>
      <b id="photoD"></b>
    </div>
    <div class="row" style="align-items:flex-start">
      <canvas id="photoC" style="max-width:48%;border:1px solid var(--line);border-radius:10px;background:#fff"></canvas>
      <svg id="photoPlot" viewBox="0 0 420 300" style="max-width:48%;width:420px;background:var(--panel);border:1px solid var(--line);border-radius:10px"></svg>
    </div>
  </section>
  <section data-id="light" data-tab="전구·대사">
    <p class="note-line" style="margin:0 0 10px;padding:6px 10px;border-left:3px solid #e07a1f;background:var(--accent-soft)"><b>비교용 · 이전 층 모델</b> — 이 탭은 묽은/진한 층이 번갈아 쌓인다고 가정했던 이전 모델의 해석입니다. 지금 구조(통째 결정 · 층·극성 없는 인공세포)는 <a href="#cad">CAD 작업대</a>와 <a href="#lab">실험대</a>에 있습니다.</p>
    <p class="sub">생명체처럼 안에서 에너지를 만드는 방법(먹이) — <b>빛</b>(광합성형), <b>내장 연료</b>(소화형), <b>증발</b>(호흡형), <b>레시피 반응물</b>.
      에너지는 무에서 생기지 않으므로, 만드는 전력과 부하가 요구하는 전력을 같은 눈금으로 비교합니다. 그림은 Rust 렌더러가 그립니다.</p>
    <div id="lightSvgs"></div>
    <pre id="lightText"></pre>
  </section>
  <section data-id="recipe" data-tab="레시피">
    <p class="sub">통째 결정 — 약국 식염수병 안 식염수에 PVA · GO 를 섞고, 병을 그릇으로 삼아 냉각판 위에서 아래부터 위로 얼립니다. 얼음 결정이 세포가 되고 GO·PVA 가 막이 됩니다.
      층도 극성도 없습니다. 자세한 설명·근거 문헌·위험 요소: <code>RECIPE.md</code>. 수치는 모델 예측입니다.</p>
    <div id="recipeCards"></div>
    <h2>공정 — 수작업 / 기계작업 (실험실 장비)</h2>
    <p class="note-line" id="recipeSum"></p>
    <table id="recipeSteps"></table>
    <h2>대조군 — 함께 만들 것</h2>
    <table id="recipeCtrl"></table>
  </section>
  <section data-id="quantum" data-tab="양자 모듈">
    <p class="sub"><b>생리식염수 결정 자체는 양자 배터리가 될 수 없습니다</b> (상온 물속 이온의 결맞음은 펨토초 안에 사라짐).
      그래서 금속·생물 요소 없이 만들 수 있는 <b>진짜 양자 배터리를 별도 모듈</b>로 설계했습니다: 유기 색소 분자를 유전체 거울 미세공진기에 넣은
      Dicke 형 (Quach 외, Science Advances 2022 에서 집단 초흡수 실증). 계산은 Python·Rust·C# 3중 구현, 형상은 Rust(truck B-rep 커널)·C#(STEP 작성기)로
      만들고 OpenCascade 로 검증했습니다.</p>
    <div class="cards" id="qCards"></div>
    <div id="qSvgs"></div>
    <h2>충전 시뮬레이션 (Tavis–Cummings, 광자 N 개 → 분자 N 개)</h2>
    <table id="qTable"></table>
    <h2>계산 교차 검증</h2>
    <table id="qCross"></table>
    <h2>CAD — STEP (ISO 10303-21, AP214) · OpenCascade 검증</h2>
    <p class="sub" id="qCadNote"></p>
    <table id="qCad"></table>
    <p class="sub">STEP 파일은 FreeCAD · Fusion 360 · SolidWorks · Onshape · CATIA 등 어떤 CAD 에서도 열립니다.
      나노미터 층이 있으므로 CAD 에서 확대해서 보세요. 결정 블록 STEP 은 도메인 층 252개 + 벽 252장(고체 504개)입니다.</p>
    <pre id="qText"></pre>
  </section>
  <section data-id="tools" data-tab="표준 도구">
    <p class="sub">분야마다 표준으로 쓰이는 공개 도구로 다시 계산한 결과입니다. 다시 계산: <code>./tools.sh all</code> · 애니메이션: <code>./tools.sh fem-movie</code>.</p>
    <div id="toolsBody"></div>
  </section>
  <section data-id="verify" data-tab="검증">
    <h2>① 계산 재현성 — Python · Rust · C# 독립 구현 비교</h2>
    <p class="sub">같은 명세(<code>spec/SPEC.md</code>)를 세 언어로 따로 구현했습니다. 같은 난수(SplitMix64)·같은 입력에서 같은 숫자가 나오면
      결과가 특정 언어나 라이브러리의 산물이 아니라는 뜻입니다. (보로노이: Python 은 Qhull, Rust·C# 는 직접 짠 반평면 절단)</p>
    <table id="crossTable"></table>
    <table id="crossSample"></table>
    <h2>② 실험 판정 — 사전 등록 가설 (C# 판정기)</h2>
    <p class="sub">계산이 맞아도 실제 전기가 나오는지는 실험만이 증명합니다. '실험 기록'에 측정값을 넣으면 아래 가설이 자동 판정됩니다.
      판정 기준은 측정 전에 정해 두었습니다 (<code>EXPERIMENT_PROTOCOL.md</code>).</p>
    <div class="row"><button class="ghost" id="reVerdict" type="button">다시 판정</button><span id="verdictMsg" class="sub"></span></div>
    <table id="verdictTable"></table>
  </section>
  <section data-id="overview" data-tab="개요">
    <h2>시료 — 모델 예측</h2>
    <table id="sampleTable"></table>
    <h2>인공세포 조직 요약</h2>
    <pre id="tissueText"></pre>
    <h2>이전 층 모델 (비교용)</h2>
    <p class="sub">아래 카드와 상세 요약은 이전의 층 모델(묽은/진한 층이 번갈아 쌓인다고 가정) 기준입니다.</p>
    <div class="cards" id="cards"></div>
    <h2>상세 요약</h2>
    <pre id="summary"></pre>
  </section>
  <section data-id="drawing" data-tab="실물 도면">
    <div class="row"><a href="cad/assembly_drawing.pdf" target="_blank">도면 PDF</a>
      <a href="cad/assembly_drawing.dxf" download>도면 DXF</a>
      <a href="cad/template_1to1.pdf" target="_blank">1:1 절단 가이드 PDF (100 % 인쇄)</a></div>
    <div class="sheet"><img src="cad/assembly_drawing.png" alt="도면"></div>
    <h2>1:1 절단 가이드 띠 — 병에 감아 절단선 표시</h2>
    <div class="sheet"><img src="cad/template_1to1.png" alt="템플릿"></div>
  </section>
  <section data-id="sim" data-tab="시뮬레이션">
    <p class="note-line" style="margin:0 0 10px;padding:6px 10px;border-left:3px solid #e07a1f;background:var(--accent-soft)"><b>비교용 · 이전 층 모델</b> — 이 탭은 묽은/진한 층이 번갈아 쌓인다고 가정했던 이전 모델의 해석입니다. 지금 구조(통째 결정 · 층·극성 없는 인공세포)는 <a href="#cad">CAD 작업대</a>와 <a href="#lab">실험대</a>에 있습니다.</p>
    <h2>세포형 도메인 구조 (결정화 직후)</h2><img class="fig" src="img/structure.png" alt="구조">
    <h2>프로브 연결 → 방전 → 재충전</h2><img class="fig" src="img/cycles.png" alt="사이클">
    <table id="cycleTable"></table>
    <pre id="cycleText"></pre>
    <h2>결정화 (막 형성) 상태도</h2><img class="fig" src="img/assembly_phase.png" alt="상태도">
  </section>
  <section data-id="log" data-tab="실험 기록">
    <form class="form" id="expForm">
      <label>결정화 시작 후 경과 [h]<input name="elapsed_h" type="number" step="any" required></label>
      <label>온도 [°C]<input name="temp_c" type="number" step="any"></label>
      <label>식염수 [mL]<input name="saline_ml" type="number" step="any"></label>
      <label>그래핀 폴리머 액정 [g]<input name="go_g" type="number" step="any"></label>
      <label>상태<select name="state"><option>액체</option><option>일부 결정</option><option>완전 결정</option><option>절단 후</option></select></label>
      <label>레시피<select name="recipe"><option>통째 결정 · 인공세포 조직</option><option>기타</option></select></label>
      <label>시료<select name="sample"><option>본 시료</option><option>대조군 A: 방향 없이 빨리 얼림</option><option>대조군 B: 식염수 + PVA 만</option><option>대조군 C: 얼리지 않음</option></select></label>
      <label>단계<select name="phase"><option>결정화 직후</option><option>절단 후</option><option>방전 후</option><option>재충전 후</option><option>보관 중</option></select></label>
      <label>측정한 결정 높이 [mm]<input name="height_mm" type="number" step="any"></label>
      <label>프로브<select name="probe"><option>흑연 막대</option><option>금속 프로브</option></select></label>
      <label>극성<select name="polarity"><option>정</option><option>역</option></select></label>
      <label>부하<select name="load"><option>없음(개방)</option><option>LED</option><option>꼬마전구</option></select></label>
      <label>점등<select name="lit"><option>-</option><option>켜짐</option><option>희미</option><option>꺼짐</option></select></label>
      <label>측정 전압 [V]<input name="voltage_v" type="number" step="any"></label>
      <label>측정 전류 [mA]<input name="current_ma" type="number" step="any"></label>
      <label class="wide">반응 화학물질 (종류·양)<input name="reactants" type="text"></label>
      <label class="wide">관찰 메모<textarea name="note" rows="2"></textarea></label>
      <div class="wide row" style="margin:0"><button class="primary" type="submit">기록 추가</button>
        <button class="ghost" type="button" id="csv">CSV 받기</button><span id="logMsg"></span></div>
    </form>
    <svg id="chart" viewBox="0 0 900 280"></svg>
    <table id="expTable"></table>
  </section>
  <section data-id="bom" data-tab="재료표"><table id="bom"></table></section>
  <section data-id="files" data-tab="파일"><table id="files"></table></section>
</main>
<script>
// ---------- 보로노이·프랙탈 공용 (Python tessellation.py 와 같은 생성 규칙) ----------
const FR = (() => {
  const rng = (seed) => { let s = seed >>> 0 || 1; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; };
  // Weierstrass–Mandelbrot 층 경계: k번째 경계 높이 h_k(x)
  function interfaces({ W, t, n, D, rough, corr, fine }, r) {
    const gamma = 1.7, terms = Math.max(4, Math.floor(Math.log(W / (fine / 2)) / Math.log(gamma)) + 1);
    const amp = [], freq = [], common = [];
    let norm = 0;
    for (let k = 0; k < terms; k++) { amp.push(Math.pow(gamma, (D - 2) * k)); freq.push(2 * Math.PI * Math.pow(gamma, k) / W); common.push(r() * 6.2832); norm += amp[k] * amp[k]; }
    norm = Math.sqrt(norm / 2);
    const own = Array.from({ length: n }, () => Array.from({ length: terms }, () => r() * 6.2832));
    const wc = Math.sqrt(corr), wi = Math.sqrt(1 - corr);
    return (k, x) => {
      if (rough === 0) return (k + 1) * t;
      let a = 0, b = 0;
      for (let q = 0; q < terms; q++) { a += amp[q] * Math.cos(freq[q] * x + common[q]); b += amp[q] * Math.cos(freq[q] * x + own[k][q]); }
      return (k + 1) * t + rough * t * (wc * a + wi * b) / norm;
    };
  }
  // 결정핵: 고른 분포(흔들린 격자) 또는 Soneira–Peebles 프랙탈 뭉침
  function seeds({ W, H, spacing, Ds }, r) {
    const pts = [];
    if (Ds >= 1.999) {
      const nx = Math.max(2, Math.round(W / spacing)), nz = Math.max(2, Math.round(H / spacing));
      for (let j = 0; j < nz; j++) for (let i = 0; i < nx; i++)
        pts.push([(i + 0.5 + (r() - 0.5) * 0.84) * W / nx, (j + 0.5 + (r() - 0.5) * 0.84) * H / nz]);
      return pts;
    }
    const levels = 4, m = Math.pow(2, Ds), s0 = spacing * 16;
    let cur = Array.from({ length: Math.max(1, Math.round(W * H / (s0 * s0))) }, () => [r() * W, r() * H]);
    let half = s0 / 2;
    for (let l = 0; l < levels; l++) {
      const next = [];
      for (const [x, z] of cur) {
        const c = Math.max(1, Math.floor(m) + (r() < m - Math.floor(m) ? 1 : 0));
        for (let q = 0; q < c; q++) next.push([x + (r() * 2 - 1) * half, z + (r() * 2 - 1) * half]);
      }
      cur = next; half /= 2;
    }
    return cur.map(([x, z]) => { x = ((x % W) + W) % W; z = Math.abs(z); if (z > H) z = 2 * H - z; return [x, Math.min(Math.max(z, H * 1e-4), H * 0.9999)]; });
  }
  function layerOf(x, z, h, n, t) {
    let k0 = Math.max(0, Math.floor(z / t) - 4), L = k0;
    for (let k = k0; k < n; k++) { const hz = h(k, x); if (z > hz) L = k + 1; else if (hz > z + 4 * t) break; }
    return L;
  }
  // 픽셀 격자 보로노이 (버킷 탐색)
  function raster(pts, W, H, gw, gh) {
    const bs = Math.max(W, H) / Math.sqrt(pts.length) * 1.5, bx = Math.ceil(W / bs), bz = Math.ceil(H / bs);
    const buckets = Array.from({ length: bx * bz }, () => []);
    pts.forEach(([x, z], i) => buckets[Math.min(bz - 1, Math.floor(z / bs)) * bx + Math.min(bx - 1, Math.floor(x / bs))].push(i));
    const owner = new Int32Array(gw * gh);
    for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
      const x = (i + 0.5) * W / gw, z = (j + 0.5) * H / gh;
      const cx = Math.floor(x / bs), cz = Math.floor(z / bs);
      let best = 1e18, who = 0;
      for (let rad = 1; rad <= 6; rad++) {
        for (let dz = -rad; dz <= rad; dz++) for (let dx = -rad; dx <= rad; dx++) {
          const X = cx + dx, Z = cz + dz;
          if (X < 0 || Z < 0 || X >= bx || Z >= bz) continue;
          for (const q of buckets[Z * bx + X]) { const ex = pts[q][0] - x, ez = pts[q][1] - z, d = ex * ex + ez * ez; if (d < best) { best = d; who = q; } }
        }
        if (best < (rad * bs) * (rad * bs)) break;
      }
      owner[j * gw + i] = who;
    }
    return owner;
  }
  // 박스 카운팅: 이진 격자에서 크기 2^k 상자
  function boxCount(mask, gw, gh) {
    const out = [];
    for (let s = 1; s <= Math.min(gw, gh) / 4; s *= 2) {
      let n = 0;
      for (let j = 0; j < gh; j += s) for (let i = 0; i < gw; i += s) {
        let hit = false;
        for (let b = j; b < Math.min(j + s, gh) && !hit; b++) for (let a = i; a < Math.min(i + s, gw); a++) if (mask[b * gw + a]) { hit = true; break; }
        if (hit) n++;
      }
      out.push([s, n]);
    }
    const pts = out.filter(([, n]) => n > 0).map(([s, n]) => [Math.log(1 / s), Math.log(n)]);
    if (pts.length < 2) return { D: NaN, pts: out };
    const mx = pts.reduce((a, p) => a + p[0], 0) / pts.length, my = pts.reduce((a, p) => a + p[1], 0) / pts.length;
    const D = pts.reduce((a, p) => a + (p[0] - mx) * (p[1] - my), 0) / pts.reduce((a, p) => a + (p[0] - mx) ** 2, 0);
    return { D, pts: out };
  }
  return { rng, interfaces, seeds, layerOf, raster, boxCount };
})();
</script>
<script>
const DATA = __DATA__;
window.DATA = DATA;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
$("#title").textContent = DATA.title;
$("#audit").innerHTML = DATA.audit_ok ? '<span class="badge ok">재질 검사 통과 ✔</span>' : '<span class="badge bad">금속 포함 ✘</span>';
$("#cards").innerHTML = DATA.cards.map(([k, v]) => `<div class="card"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
$("#summary").textContent = DATA.summary;
$("#tissueText").textContent = ((DATA.samples || []).find((x) => x.tissue) || {}).describe || "";
$("#sampleTable").innerHTML = "<tr><th>시료</th><th>구조</th><th>결정</th><th>내강 / 막 사이 소금물</th><th>저장 에너지</th><th>윗면–아랫면 전압</th><th>설명</th></tr>" +
  (DATA.samples || []).map((s) => `<tr><td><b>${esc(s.name)}</b></td><td>3D 보로노이 세포 약 ${(s.n_cells / 1e6).toFixed(0)}백만 개 · 층·극성 없음</td>
    <td class="n">Ø${(2 * s.gel_r).toFixed(1)} × ${s.block_h.toFixed(1)} mm</td><td class="n">${s.c_lumen_mM.toFixed(1)} mM / ${s.c_brine_m.toFixed(2)} M</td>
    <td class="n">${s.energy_j.toFixed(0)} J</td><td class="n">${(1000 * s.ocv).toFixed(1)} mV (≈ 0)</td><td>${esc(s.note)}</td></tr>`).join("");
$("#cycleText").textContent = DATA.cycle_text;
$("#cycleTable").innerHTML = "<tr><th>사이클</th><th>충전 mAh</th><th>방전 mAh</th><th>쿨롱효율</th><th>에너지효율</th></tr>" +
  DATA.cycles.map((c) => `<tr><td>${c.cycle}</td><td class="n">${c.charge}</td><td class="n">${c.discharge}</td><td class="n">${c.ce}</td><td class="n">${c.ee}</td></tr>`).join("");
$("#bom").innerHTML = "<tr><th>번호</th><th>품명</th><th>재질</th><th>수량</th><th>규격</th></tr>" +
  DATA.bom.map((b) => `<tr class="${b.keep ? "" : "gone"}"><td class="n">${b.no}</td><td>${esc(b.name)}</td><td>${esc(b.material)}</td><td>${esc(b.qty)}</td><td>${esc(b.spec)}</td></tr>`).join("");
$("#files").innerHTML = "<tr><th>파일</th><th></th></tr>" +
  DATA.files.map((f) => `<tr><td>${esc(f)}</td><td><a href="${esc(f)}" download>받기</a></td></tr>`).join("");

// ---------- 탭 ----------
const sections = [...document.querySelectorAll("section")];
const nav = $("#tabs");
const tabHooks = {};
function show(name) {
  sections.forEach((s) => s.classList.toggle("on", s.dataset.tab === name));
  nav.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  try { localStorage.setItem("snss-tab", name); } catch (e) {}
  const sec = sections.find((s) => s.dataset.tab === name);
  if (sec) { history.replaceState(null, "", location.search + "#" + sec.dataset.id); (tabHooks[sec.dataset.id] || (() => {}))(); }
}
const GROUPS = [["조각가", ["console", "sculptor"]], ["작업", ["lab", "cad", "process", "recipe"]], ["검증", ["tools", "verify", "log"]],
                ["자료", ["overview", "drawing", "bom", "files", "quantum"]], ["비교 · 층 모델", ["fractal", "light", "sim"]]];
const ICONS = { console: "◉", sculptor: "✒", lab: "⚗", cad: "⬡", process: "❄", recipe: "☰", fractal: "⬢", light: "💡", sim: "∿", quantum: "⚛",
                tools: "▶", verify: "✓", log: "✎", overview: "◎", drawing: "📐", bom: "▤", files: "⇩" };
const NEW = new Set(["console"]);
const grouped = new Set(GROUPS.flatMap(([, ids]) => ids));
for (const [label, ids] of [...GROUPS, ["기타", sections.map((s) => s.dataset.id).filter((id) => !grouped.has(id))]]) {
  const secs = ids.map((id) => sections.find((s) => s.dataset.id === id)).filter(Boolean);
  if (!secs.length) continue;
  const g = document.createElement("div");
  g.className = "grp";
  g.innerHTML = `<span>${label}</span>`;
  for (const s of secs) {
    const b = document.createElement("button");
    b.dataset.tab = s.dataset.tab;
    b.innerHTML = `<i>${ICONS[s.dataset.id] || "•"}</i>${esc(s.dataset.tab)}`;
    if (NEW.has(s.dataset.id)) b.classList.add("new");
    b.onclick = () => show(s.dataset.tab);
    g.appendChild(b);
  }
  nav.appendChild(g);
}
const ALIAS = { "#3d": "#cad" };
const fromHashSec = () => sections.find((x) => "#" + x.dataset.id === (ALIAS[location.hash] || location.hash));
window.addEventListener("hashchange", () => {
  const s = fromHashSec();
  if (s) show(s.dataset.tab);
});

// ---------- 결정화 과정 애니메이션 (2D 캔버스) ----------
try { (function process() {
  const B = DATA.bottle;
  const cv = $("#proc"), ctx = cv.getContext("2d");
  const ri = B.d / 2 - B.wall, ro = B.d / 2;
  const total = B.body + B.shoulder + B.neck_h + B.cap_h;
  const ROWS = 8;
  $("#dispRows").textContent = ROWS; $("#realRows").textContent = DATA.n_layers;

  // 결정 성장 격자 (병 안 식염수 영역): 결정핵 = 보로노이 씨앗, 층 번호 = 프랙탈 경계 아래/위
  const F = DATA.fractal.params;
  const GW = 150, cell = (2 * ri) / GW, GH = Math.round(B.fill / cell);
  const tD = B.fill / ROWS;
  const r0 = FR.rng(7), rnd = r0;
  const raw = FR.seeds({ W: 2 * ri, H: B.fill, spacing: tD / F.grains_per_layer, Ds: F.seed_dimension }, r0);
  const hD = FR.interfaces({ W: 2 * ri, t: tD, n: ROWS - 1, D: F.interface_dimension, rough: F.roughness,
                             corr: F.correlation, fine: tD / F.grains_per_layer }, r0);
  const seeds = raw.map(([x, z]) => ({ x: x - ri, z, layer: FR.layerOf(x, z, hD, ROWS - 1, tD),
                                       tn: (z / B.fill) * 0.62 + rnd() * 0.1 - 0.06 * Math.pow(Math.abs(x - ri) / ri, 4),
                                       shade: 0.92 + rnd() * 0.16, ang: (rnd() - 0.5) * 0.35 }));
  // 영역 = 가장 가까운 결정핵 (보로노이), 굳는 시각 = 그 결정핵의 핵생성 시각 + 거리 / 성장 속도
  const owner = FR.raster(seeds.map((q) => [q.x + ri, q.z]), 2 * ri, B.fill, GW, GH);
  const arrive = new Float32Array(GW * GH);
  let amax = 0;
  for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) {
    const g = j * GW + i, q = seeds[owner[g]];
    const dx = -ri + (i + 0.5) * cell - q.x, dz = (j + 0.5) * cell - q.z;
    arrive[g] = q.tn + Math.sqrt(dx * dx + dz * dz) / (ri * 3.2);
    amax = Math.max(amax, arrive[g]);
  }
  for (let k = 0; k < arrive.length; k++) arrive[k] /= amax;
  const img = new ImageData(GW, GH);
  const off = document.createElement("canvas"); off.width = GW; off.height = GH;
  const offx = off.getContext("2d");

  // 붓는 입자: 그래핀 액정(진갈색) + 반응 화학물(호박색)
  const parts = [];
  for (let k = 0; k < 520; k++) parts.push({ go: k % 10 < 7, tx: (rnd() * 2 - 1) * ri * 0.95, tz: rnd() * B.fill,
                                             d: rnd() * 0.5, sw: rnd() * 6.28, sx: (rnd() - 0.5) * 3 });

  const STAGES = [
    [0.00, "식염수병 개봉", "약국에서 산 0.9 % 생리식염수 500 mL"],
    [0.10, "그래핀 폴리머 액정 + PVA 붓기", "진갈색 = 그래핀 액정, 호박색 = PVA 용액 (병 그대로, 한 번에)"],
    [0.32, "섞이며 퍼짐", "GO 와 PVA 가 식염수에 고르게 퍼짐 (층 없음)"],
    [0.40, "얼음 결정핵 → 아래부터 위로", "얼음 결정 하나 = 세포 하나, GO·PVA 는 경계로 밀려나 막이 됨 (보로노이)"],
    [0.86, "결정화 완료", "녹으면 묽은 내강 + 막 사이 진한 소금물 = 에너지가 담긴 빈 인공세포"],
    [0.90, "병 절단 · 프로브로 측정", "결정 윗면(+)·아래면(-)에 멀티미터 프로브"],
  ];
  $("#stages").innerHTML = STAGES.map((s, i) => `<li data-i="${i}">${esc(s[1])}<small>${esc(s[2])}</small></li>`).join("");
  [...$("#stages").children].forEach((li) => li.onclick = () => { setT(STAGES[+li.dataset.i][0] + 0.001); });

  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const ease = (v) => v * v * (3 - 2 * v);
  let W = 0, H = 0, k = 1, ox = 0, oy = 0;
  function layout() {
    const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    W = r.width; H = r.height;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    k = Math.min((H - 50) / (total + 55), (W * 0.55) / (B.d + 30));
    ox = W * 0.33; oy = H - 26;
  }
  const X = (x) => ox + x * k, Y = (z) => oy - z * k;

  function bottlePath(lift) {
    const rn = B.neck_d / 2, zs = B.body, zn = B.body + B.shoulder, zt = zn + B.neck_h;
    const p = new Path2D();
    p.moveTo(X(-ro), Y(0)); p.lineTo(X(ro), Y(0)); p.lineTo(X(ro), Y(zs));
    p.bezierCurveTo(X(ro), Y(zs + B.shoulder * 0.7), X(rn + 6), Y(zn - 3), X(rn), Y(zn));
    p.lineTo(X(rn), Y(zt)); p.lineTo(X(-rn), Y(zt)); p.lineTo(X(-rn), Y(zn));
    p.bezierCurveTo(X(-rn - 6), Y(zn - 3), X(-ro), Y(zs + B.shoulder * 0.7), X(-ro), Y(zs));
    p.closePath();
    return p;
  }
  function drawCap(x, z) {
    ctx.fillStyle = "#3b7dd8"; ctx.strokeStyle = "#1f4f94"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.roundRect(X(x - B.cap_d / 2), Y(z + B.cap_h), B.cap_d * k, B.cap_h * k, Math.max(1, k));
    ctx.fill(); ctx.stroke();
    for (let g = 1; g < 6; g++) { ctx.beginPath(); ctx.moveTo(X(x - B.cap_d / 2 + g * B.cap_d / 6), Y(z + B.cap_h * 0.15)); ctx.lineTo(X(x - B.cap_d / 2 + g * B.cap_d / 6), Y(z + B.cap_h * 0.85)); ctx.strokeStyle = "#ffffff40"; ctx.stroke(); }
  }

  function render(t) {
    if (W < 50 || H < 50 || k <= 0) return;  // 탭이 숨겨져 크기가 없을 때
    ctx.clearRect(0, 0, W, H);
    const zt = B.body + B.shoulder + B.neck_h;
    const pour = clamp((t - 0.10) / 0.22), mix = clamp((t - 0.18) / 0.22);
    const T = clamp((t - 0.40) / 0.46), cut = clamp((t - 0.88) / 0.12);
    // 받침
    ctx.fillStyle = "#e9edf2"; ctx.fillRect(0, oy, W, H - oy);
    // 내용물 (식염수 → 혼합 → 결정)
    const GO = [92, 70, 52], SAL = [222, 236, 245];
    const liq = SAL.map((c, i) => Math.round(c + (GO[i] - c) * 0.55 * mix));
    const d = img.data;
    let crystallized = 0;
    for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) {
      const g = j * GW + i, p = ((GH - 1 - j) * GW + i) * 4;
      const a = arrive[g];
      let c;
      if (T > 0 && a <= T) {
        crystallized++;
        const s = seeds[owner[g]];
        c = [191, 227, 245].map((v) => v * s.shade); // 모든 세포 같은 종류 (묽은 내강)
        if (T - a < 0.025 && T < 1) c = c.map((v) => v + 60);
        const right = i < GW - 1 ? owner[g + 1] : owner[g], up = j < GH - 1 ? owner[g + GW] : owner[g];
        const rr = i < GW - 1 && arrive[g + 1] <= T, uu = j < GH - 1 && arrive[g + GW] <= T;
        const nbr = rr && right !== owner[g] ? right : uu && up !== owner[g] ? up : -1;
        if (nbr >= 0) c = [201, 138, 58]; // 막 + 막 사이 진한 소금물 (모두 같은 막)
      } else c = liq;
      d[p] = c[0]; d[p + 1] = c[1]; d[p + 2] = c[2]; d[p + 3] = 255;
    }
    offx.putImageData(img, 0, 0);
    ctx.save();
    ctx.imageSmoothingEnabled = true;
    const raise = 34 * ease(cut);  // 꺼낸 결정을 들어 올려 아래면이 보이게
    ctx.drawImage(off, X(-ri), Y(B.wall + B.fill + raise), 2 * ri * k, B.fill * k);
    // 액정 방향(정렬) 표시
    if (false) {
      ctx.strokeStyle = "#ffffff70"; ctx.lineWidth = 1;
      for (const s of seeds) {
        const a = s.tn / amax * 1.0;
        if (a > T) continue;
        const cx = X(s.x), cz = Y(B.wall + s.z + raise), L = Math.min(9, 2 * ri * k / 14);
        ctx.beginPath(); ctx.moveTo(cx - L * Math.cos(s.ang), cz - L * Math.sin(s.ang));
        ctx.lineTo(cx + L * Math.cos(s.ang), cz + L * Math.sin(s.ang)); ctx.stroke();
      }
    }
    ctx.restore();
    // 붓는 입자
    if (pour > 0 && mix < 1) {
      for (const q of parts) {
        const u = clamp((pour - q.d * 0.6) / 0.45);
        if (u <= 0) continue;
        const fall = ease(clamp(u * 1.6));
        const spread = ease(clamp((u - 0.35) / 0.65));
        const x = q.sx * (1 - spread) + q.tx * spread + Math.sin(q.sw + u * 7) * 3 * spread;
        const z = (zt + 30) * (1 - fall) + (B.wall + q.tz) * fall;
        ctx.globalAlpha = (1 - mix) * 0.85;
        ctx.fillStyle = q.go ? "#3d2b1f" : "#d39b2a";
        ctx.beginPath(); ctx.arc(X(x), Y(z), q.go ? 1.6 : 1.3, 0, 6.29); ctx.fill();
      }
      ctx.globalAlpha = 1;
    }
    // 병 (절단 단계에서 위는 들리고 아래는 사라짐)
    ctx.save();
    const lift = 45 * ease(cut);
    const raise2 = 34 * ease(cut);
    const bp = bottlePath();
    ctx.lineWidth = 1.6;
    // 아래 컵
    ctx.save(); ctx.beginPath(); ctx.rect(0, Y(B.cut), W, H); ctx.clip();
    ctx.globalAlpha = 1 - ease(cut);
    ctx.fillStyle = "#cfe3f218"; ctx.fill(bp); ctx.strokeStyle = "#7d97ad"; ctx.stroke(bp);
    ctx.restore();
    // 위쪽 (들어 올림)
    ctx.save(); ctx.translate(0, -lift * k); ctx.beginPath(); ctx.rect(0, 0, W, Y(B.cut)); ctx.clip();
    ctx.globalAlpha = 1 - 0.9 * ease(cut);
    ctx.fillStyle = "#cfe3f218"; ctx.fill(bp); ctx.strokeStyle = "#7d97ad"; ctx.stroke(bp);
    ctx.restore();
    ctx.restore();
    // 뚜껑: 붓는 동안 옆에 벗어 둠
    const capOff = t >= 0.06 && t < 0.36;
    if (capOff) drawCap(ro + 30, 0); else drawCap(0, zt + (cut > 0 ? lift : 0));
    // 붓는 줄기
    if (pour > 0 && pour < 0.85) {
      ctx.strokeStyle = "#3d2b1fcc"; ctx.lineWidth = Math.max(2, 3 * k / 2);
      ctx.beginPath(); ctx.moveTo(X(-2), Y(zt + 55)); ctx.quadraticCurveTo(X(-1), Y(zt + 20), X(0), Y(B.wall + B.fill)); ctx.stroke();
      ctx.fillStyle = "#555"; ctx.font = "12px sans-serif"; ctx.textAlign = "center";
      ctx.fillText("그래핀 폴리머 액정 + PVA", X(0), Y(zt + 58));
    }
    // 절단선
    if (t > 0.84) {
      ctx.setLineDash([8, 4, 2, 4]); ctx.strokeStyle = "#c0392b"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(X(-ro - 10), Y(B.cut)); ctx.lineTo(X(ro + 10), Y(B.cut)); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = "#c0392b"; ctx.font = "12px sans-serif"; ctx.textAlign = "left"; ctx.fillText("절단선 A", X(ro + 12), Y(B.cut) + 4);
    }
    // 프로브 + 멀티미터
    const probe = clamp((cut - 0.45) / 0.4);
    if (probe > 0) {
      const top = Y(B.wall + B.fill + raise2), bot = Y(B.wall + raise2);
      const mx = X(ro + 55), my = (top + bot) / 2;
      ctx.lineWidth = 2;
      for (const [yy, col, sgn] of [[top, "#c0392b", -1], [bot, "#222", 1]]) {
        const len = 30 * (1 - ease(probe)) + 4;
        ctx.strokeStyle = col; ctx.beginPath();
        ctx.moveTo(X(0), yy + sgn * len); ctx.lineTo(X(0), yy + sgn * (len + 18));
        ctx.lineTo(mx, yy + sgn * (len + 18)); ctx.lineTo(mx, my + sgn * 30); ctx.stroke();
        ctx.fillStyle = col; ctx.beginPath(); ctx.arc(X(0), yy + sgn * len, 3, 0, 6.29); ctx.fill();
      }
      ctx.fillStyle = "#20262d"; ctx.beginPath(); ctx.roundRect(mx - 62, my - 30, 124, 60, 8); ctx.fill();
      ctx.fillStyle = "#b8f5c8"; ctx.font = "bold 20px monospace"; ctx.textAlign = "center";
      const TIS = (DATA.samples || [])[0] || { ocv: 0 };
      const v = TIS.ocv * clamp((probe - 0.6) / 0.4);
      ctx.fillText((1000 * v).toFixed(1) + " mV", mx, my + 7);
      ctx.fillStyle = "#9aa4b1"; ctx.font = "11px sans-serif"; ctx.fillText("멀티미터 (측정 장비)", mx, my + 46);
      ctx.font = "12px sans-serif"; ctx.textAlign = "right";
      ctx.fillStyle = "#c0392b"; ctx.fillText("(+) 윗면", X(-ri) - 6, top + 4);
      ctx.fillStyle = "#222"; ctx.fillText("(-) 아래면", X(-ri) - 6, bot + 4);
    }
    // 오른쪽 위 층 설명
    if (T > 0.2) {
      const lx = X(ro + 14), ly = Y(B.wall + B.fill * 0.75);
      ctx.font = "12px sans-serif"; ctx.textAlign = "left";
      [["#bfe3f5", `인공세포 (묽은 내강 ≈ ${((DATA.samples || [])[0] || {}).c_lumen_mM?.toFixed(1)} mM)`], ["#c98a3a", `막 + 막 사이 소금물 ≈ ${((DATA.samples || [])[0] || {}).c_brine_m?.toFixed(2)} M`]]
        .forEach(([c, s], i) => { if (probe > 0) return; ctx.fillStyle = c; ctx.fillRect(lx, ly + i * 18, 12, 12); ctx.fillStyle = "#333"; ctx.fillText(s, lx + 18, ly + i * 18 + 10); });
    }
    // 측정값 패널
    const frac = crystallized / (GW * GH);
    let rowsDone = 0;
    for (let r = 0; r < ROWS; r++) { const zr = Math.min(GH - 1, Math.round(((r + 1) / ROWS) * GH) - 1); let ok = true; for (let i = 0; i < GW; i += 5) if (arrive[zr * GW + i] > T || T <= 0) { ok = false; break; } if (ok) rowsDone++; }
    const stage = STAGES.reduce((acc, s, i) => (t >= s[0] ? i : acc), 0);
    [...$("#stages").children].forEach((li, i) => li.classList.toggle("on", i === stage));
    $("#metrics").innerHTML = [
      ["진행", `${Math.round(t * 100)} %`],
      ["결정화된 부분", `${Math.round(frac * 100)} %`],
      ["담긴 에너지", `${((((DATA.samples || [])[0] || {}).energy_j || 0) * frac).toFixed(0)} J`],
      ["윗면–아랫면 전압", probe > 0 ? `${(1000 * (((DATA.samples || [])[0] || {}).ocv || 0)).toFixed(1)} mV (≈ 0)` : "-"],
    ].map(([a, b]) => `<div class="metric"><span>${a}</span><b>${b}</b></div>`).join("");
  }

  let t = 0, playing = false, last = 0;
  const slider = $("#t");
  function setT(v) { t = clamp(v); slider.value = Math.round(t * 1000); render(t); }
  slider.oninput = () => { playing = false; $("#play").textContent = "▶ 재생"; setT(slider.value / 1000); };
  $("#play").onclick = () => { playing = !playing; if (playing && t >= 1) t = 0; $("#play").textContent = playing ? "❚❚ 정지" : "▶ 재생"; last = performance.now(); requestAnimationFrame(loop); };
  function loop(now) {
    if (!playing) return;
    t += ((now - last) / 1000) * (+$("#speed").value) / 18; last = now;
    if (t >= 1) { t = 1; playing = false; $("#play").textContent = "▶ 다시"; }
    setT(t);
    if (playing) requestAnimationFrame(loop);
  }
  const q = new URLSearchParams(location.search).get("t");
  new ResizeObserver(() => { layout(); render(t); }).observe(cv);
  layout(); setT(q !== null ? +q : 0);
  tabHooks.process = () => { layout(); render(t); };
})(); } catch (e) { console.error(e); $("#metrics").textContent = "애니메이션 오류: " + e.message; }

// ---------- 보로노이·프랙탈 탐색기 ----------
(function explorer() {
  const F = DATA.fractal;
  const cv = $("#vx"), ctx = cv.getContext("2d");
  const t = F.layer_mm, NL = 8, W = 8, H = NL * t;
  const sl = { D: $("#sD"), R: $("#sR"), C: $("#sC"), S: $("#sS"), G: $("#sG") };
  sl.D.value = F.params.interface_dimension; sl.R.value = F.params.roughness; sl.C.value = F.params.correlation;
  sl.S.value = F.params.seed_dimension; sl.G.value = F.params.grains_per_layer;
  $("#mapCorr").textContent = F.map.correlation; $("#vText").textContent = F.text;
  let seedNo = 1;
  function interp(D, R) {
    const { dims, roughs, V, P } = F.map;
    const f = (arr, v) => { let i = 0; while (i < arr.length - 2 && v > arr[i + 1]) i++; return [i, Math.min(1, Math.max(0, (v - arr[i]) / (arr[i + 1] - arr[i])))]; };
    const [i, u] = f(dims, D), [j, w] = f(roughs, R);
    const bl = (M) => (1 - u) * (1 - w) * M[j][i] + u * (1 - w) * M[j][i + 1] + (1 - u) * w * M[j + 1][i] + u * w * M[j + 1][i + 1];
    return [bl(V), bl(P)];
  }
  function draw() {
    const D = +sl.D.value, R = +sl.R.value, C = +sl.C.value, S = +sl.S.value, G = +sl.G.value;
    $("#vD").textContent = D.toFixed(2); $("#vR").textContent = R.toFixed(2); $("#vC").textContent = C.toFixed(2);
    $("#vS").textContent = S.toFixed(2); $("#vG").textContent = G.toFixed(1);
    const r = FR.rng(seedNo * 97 + 13);
    const pts = FR.seeds({ W, H, spacing: t / G, Ds: S }, r);
    const h = FR.interfaces({ W, t, n: NL - 1, D, rough: R, corr: C, fine: t / G }, r);
    const lay = pts.map(([x, z]) => FR.layerOf(x, z, h, NL - 1, t));
    const rect = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (rect.width < 20) return;  // 탭이 숨겨져 크기가 없을 때
    const gw = Math.min(900, Math.round(rect.width)), gh = Math.round(gw * H / W);
    cv.style.height = Math.round(rect.width * H / W) + "px";
    const owner = FR.raster(pts, W, H, gw, gh);
    const img = new ImageData(gw, gh), d = img.data;
    const iface = new Uint8Array(gw * gh);
    let nAct = 0, nDef = 0;
    const mid = Math.floor(NL / 2) - 1;
    for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
      const g = j * gw + i, o = owner[g], p = ((gh - 1 - j) * gw + i) * 4;
      let c = lay[o] % 2 ? [38, 104, 168] : [150, 196, 222];
      const nb = [i < gw - 1 ? owner[g + 1] : o, j < gh - 1 ? owner[g + gw] : o].find((q) => q !== o);
      if (nb !== undefined) {
        const dl = Math.abs(lay[nb] - lay[o]), lo = Math.min(lay[nb], lay[o]);
        if (dl === 0) c = [70, 82, 96];
        else if (dl === 1) { c = lo % 2 === 0 ? [232, 131, 58] : [58, 154, 91]; nAct++; if (lo === mid) iface[g] = 1; }
        else { c = [209, 38, 59]; nDef++; }
      }
      d[p] = c[0]; d[p + 1] = c[1]; d[p + 2] = c[2]; d[p + 3] = 255;
    }
    cv.width = gw; cv.height = gh;
    ctx.putImageData(img, 0, 0);
    ctx.fillStyle = "#111";
    const sx = gw / W, sz = gh / H;
    if (pts.length < 4000) for (const [x, z] of pts) ctx.fillRect(x * sx - 0.6, (H - z) * sz - 0.6, 1.3, 1.3);
    const bc = FR.boxCount(iface, gw, gh);
    const [V, P] = interp(Math.max(1, D), R);
    $("#vMetrics").innerHTML = [
      ["보로노이 도메인", `${pts.length}개 (창 ${W}×${H.toFixed(1)} mm)`],
      ["층 경계 하나 실측 D (박스 카운팅)", isNaN(bc.D) ? "-" : bc.D.toFixed(2)],
      ["결함 벽 비율", `${(100 * nDef / Math.max(1, nAct + nDef)).toFixed(1)} %`],
      ["예측 개방전압 (지도 보간)", `${V.toFixed(2)} V`],
      ["예측 유효 출력 (지도 보간)", `${P.toFixed(0)} mW`],
    ].map(([a, b]) => `<div class="metric"><span>${a}</span><b>${b}</b></div>`).join("") +
      '<div class="sub" style="margin-top:6px">주황 = 양이온 선택 벽, 초록 = 음이온 선택 벽, 회색 = 같은 층 벽, 빨강 = 층을 건너뛴 결함 벽(단락)</div>';
  }
  let pending = 0;
  const schedule = () => { cancelAnimationFrame(pending); pending = requestAnimationFrame(draw); };
  Object.values(sl).forEach((e) => e.oninput = schedule);
  $("#reseed").onclick = () => { seedNo++; schedule(); };
  tabHooks.fractal = schedule;
  new ResizeObserver(schedule).observe(cv.parentElement);

  // ----- 사진 분석 -----
  const pc = $("#photoC"), px = pc.getContext("2d", { willReadFrequently: true });
  let gray = null, gw = 0, gh = 0;
  function analyzePhoto() {
    if (!gray) return;
    const thr = +$("#thr").value, inv = $("#inv").checked;
    const mask = new Uint8Array(gw * gh), out = px.createImageData(gw, gh);
    for (let k = 0; k < gw * gh; k++) {
      const on = inv ? gray[k] > thr : gray[k] < thr;
      mask[k] = on ? 1 : 0;
      const v = on ? 20 : 245;
      out.data[4 * k] = on ? 209 : v; out.data[4 * k + 1] = on ? 38 : v; out.data[4 * k + 2] = on ? 59 : v; out.data[4 * k + 3] = 255;
    }
    px.putImageData(out, 0, 0);
    const bc = FR.boxCount(mask, gw, gh);
    $("#photoD").textContent = isNaN(bc.D) ? "벽 픽셀이 없음 — 문턱값 조정" : `사진의 벽 프랙탈 차원 D ≈ ${bc.D.toFixed(2)} (모델 설정 ${DATA.fractal.params.interface_dimension})`;
    const pts = bc.pts.filter(([, n]) => n > 0).map(([sz, n]) => [Math.log10(1 / sz), Math.log10(n)]);
    if (pts.length < 2) { $("#photoPlot").innerHTML = ""; return; }
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const X = (v) => 50 + (v - x0) / (x1 - x0 || 1) * 340, Y = (v) => 260 - (v - y0) / (y1 - y0 || 1) * 220;
    $("#photoPlot").innerHTML = `<text x="210" y="292" text-anchor="middle" font-size="12" fill="currentColor">log10(1/상자 크기)</text>
      <text x="14" y="150" transform="rotate(-90 14 150)" text-anchor="middle" font-size="12" fill="currentColor">log10 N</text>
      <polyline fill="none" stroke="#d1263b" stroke-width="2" points="${pts.map((p) => X(p[0]) + "," + Y(p[1])).join(" ")}"/>
      ${pts.map((p) => `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="4" fill="#d1263b"/>`).join("")}
      <text x="60" y="30" font-size="13" fill="currentColor">기울기 D = ${bc.D.toFixed(2)}</text>`;
  }
  function loadPhoto(src, revoke) {
    const im = new Image();
    im.onload = () => {
      const k = Math.min(1, 512 / Math.max(im.width, im.height));
      gw = Math.round(im.width * k); gh = Math.round(im.height * k);
      pc.width = gw; pc.height = gh;
      px.drawImage(im, 0, 0, gw, gh);
      const raw = px.getImageData(0, 0, gw, gh).data;
      gray = new Float32Array(gw * gh);
      for (let q = 0; q < gw * gh; q++) gray[q] = 0.299 * raw[4 * q] + 0.587 * raw[4 * q + 1] + 0.114 * raw[4 * q + 2];
      analyzePhoto();
      if (revoke) URL.revokeObjectURL(im.src);
    };
    im.src = src;
  }
  $("#photo").onchange = (ev) => { const f = ev.target.files[0]; if (f) loadPhoto(URL.createObjectURL(f), true); };
  $("#demoPhoto").onclick = () => { $("#thr").value = 90; loadPhoto("img/voronoi_section.png", false); };
  if (new URLSearchParams(location.search).has("demo")) $("#demoPhoto").click();
  $("#thr").oninput = analyzePhoto;
  $("#inv").onchange = analyzePhoto;
})();

// ---------- 전구·대사 / 검증 ----------
(function verifyAndLight() {
  const svg = (name, alt) => DATA.svgs.includes(name) ? `<img class="fig" src="svg/${name}" alt="${esc(alt)}" style="background:none;border:0">` : "";
  $("#lightSvgs").innerHTML = svg("power_budget.svg", "전력 수지") + svg("led_week.svg", "LED 1주일") + svg("bulb.svg", "꼬마전구");
  $("#vorSvgs").innerHTML = svg("voronoi_default.svg", "보로노이 단면") + svg("voronoi_rough.svg", "거친 경계") + svg("voronoi_clustered.svg", "뭉친 결정핵")
    || '<img class="fig" src="img/voronoi_section.png" alt="보로노이 단면">';
  $("#lightText").textContent = DATA.lighting.text;
  const C = DATA.crosscheck;
  const langs = Object.keys(C.languages);
  const caseNames = langs.length && C.languages[langs[0]].cases ? Object.keys(C.languages[langs[0]].cases) : [];
  $("#crossTable").innerHTML = "<tr><th>기준 사례</th>" + langs.map((l) => `<th>${l === "csharp" ? "C#" : l === "rust" ? "Rust" : l} vs Python</th>`).join("") + "</tr>" +
    caseNames.map((n) => `<tr><td>${esc(n)}</td>` + langs.map((l) => {
      const r = C.languages[l];
      if (r.error) return `<td><span class="badge bad">실행 실패</span> ${esc(r.error)}</td>`;
      const c = r.cases[n];
      return `<td>${c.ok ? '<span class="badge ok">✔ 일치</span>' : '<span class="badge bad">✘ 불일치</span>'} 항목 ${c.n}개 · 최대 상대차 ${c.max_rel.toExponential(1)}${c.bad.length ? " · " + esc(c.bad.join(", ")) : ""}</td>`;
    }).join("") + "</tr>").join("");
  const keys = Object.keys(C.sample || {});
  $("#crossSample").innerHTML = "<tr><th>값 (기본 배합)</th><th>Python</th>" + langs.map((l) => `<th>${l === "csharp" ? "C#" : "Rust"}</th>`).join("") + "</tr>" +
    keys.map((k) => `<tr><td>${esc(k)}</td><td class="n">${esc(C.sample[k])}</td>` + langs.map((l) => `<td class="n">${esc((C.sample_langs[l] || {})[k])}</td>`).join("") + "</tr>").join("");
  // 서버(C# 판정기)가 없을 때 쓰는 같은 규칙의 브라우저 판정 — csharp/Snss.Lab/Lab.cs Judge 와 동일
  function judge(raw, modelOcv) {
    const MAIN = "본 시료";
    const num = (v) => (typeof v === "number" && isFinite(v) ? v : null);
    const str = (v, d) => (typeof v === "string" && v.length ? v : d);
    const m = raw.map((r) => ({ elapsed: num(r.elapsed_h), sample: str(r.sample, MAIN), height: num(r.height_mm),
      probe: str(r.probe, "미기록"), polarity: str(r.polarity, "정"), phase: str(r.phase, "결정화 직후"),
      load: str(r.load, "없음(개방)"), lit: str(r.lit, "-"), v: num(r.voltage_v) }));
    const avg = (a) => a.reduce((s, x) => s + x, 0) / a.length;
    const v = [], add = (id, title, status, detail) => v.push({ id, title, status, detail });
    const open = m.filter((x) => x.load.startsWith("없음") && x.v !== null && x.polarity === "정");
    const main = open.filter((x) => x.sample === MAIN && (x.phase === "결정화 직후" || x.phase === "절단 후"));
    const ctrl = open.filter((x) => x.sample.startsWith("대조군"));
    let t = "정렬된 결정이 대조군보다 확실히 높은 전압";
    if (!main.length || !ctrl.length)
      add("H1", t, "데이터 부족", `본 시료 ${main.length}건, 대조군 ${ctrl.length}건 — 둘 다 필요 (대조군 A 농도차 없음 · B 한 통에 섞음 · C 식염수만)`);
    else {
      const vm = avg(main.map((x) => Math.abs(x.v))), vc = avg(ctrl.map((x) => Math.abs(x.v)));
      add("H1", t, vm >= 0.3 && vm >= 10 * Math.max(vc, 1e-6) ? "충족" : "불충족",
        `본 시료 평균 ${vm.toFixed(3)} V, 대조군 평균 ${vc.toFixed(3)} V (기준: ≥0.3 V 이고 대조군의 10배 이상, 모델 ${modelOcv.toFixed(2)} V)`);
    }
    t = "전압이 결정 높이에 비례 (층이 직렬로 쌓였다는 증거)";
    const withH = main.filter((x) => x.height > 0), hs = [...new Set(withH.map((x) => x.height))];
    if (hs.length < 2 || Math.max(...hs) / Math.min(...hs) < 1.5)
      add("H2", t, "데이터 부족", "높이가 1.5배 이상 다른 조각 2개 이상 필요 (예: 통째 측정 후 절반으로 잘라 측정)");
    else {
      const per = withH.map((x) => Math.abs(x.v) / x.height);
      const spread = Math.max(...per) / Math.max(Math.min(...per), 1e-12);
      add("H2", t, spread <= 1.25 / 0.75 ? "충족" : "불충족",
        `높이당 전압 평균 ${(avg(per) * 1000).toFixed(1)} mV/mm, 최대/최소 ${spread.toFixed(2)} (기준 ≤ 1.67, 모델 ${(modelOcv / 127.6 * 1000).toFixed(1)} mV/mm)`);
    }
    t = "프로브를 바꾸면 부호만 반대 (접촉 전위가 아닌 내부 전압)";
    const pairs = m.filter((x) => x.polarity === "역" && x.v !== null && x.load.startsWith("없음")).map((r) => {
      const c = open.filter((o) => o.sample === r.sample && o.elapsed !== null && r.elapsed !== null && Math.abs(o.elapsed - r.elapsed) <= 0.5)
        .sort((a, b) => Math.abs(a.elapsed - r.elapsed) - Math.abs(b.elapsed - r.elapsed));
      return c.length ? [r, c[0]] : null;
    }).filter(Boolean);
    if (!pairs.length) add("H3", t, "데이터 부족", "같은 시료를 30분 안에 정·역 극성으로 각각 측정한 기록 필요");
    else {
      const worst = Math.max(...pairs.map(([r, f]) => Math.abs(r.v + f.v) / Math.max(Math.abs(f.v), 1e-9)));
      add("H3", t, worst <= 0.15 ? "충족" : "불충족", `${pairs.length}쌍, |V정 + V역| / |V정| 최대 ${(worst * 100).toFixed(0)} % (기준 ≤ 15 %)`);
    }
    t = "방전 후 낮아진 전압이 재충전으로 회복 (2차 전지)";
    const pAvg = (ph) => { const a = open.filter((x) => x.sample === MAIN && x.phase === ph).map((x) => x.v); return a.length ? avg(a) : null; };
    const v0 = pAvg("결정화 직후") ?? pAvg("절단 후"), v1 = pAvg("방전 후"), v2 = pAvg("재충전 후");
    if (v0 === null || v1 === null || v2 === null) add("H4", t, "데이터 부족", "결정화 직후 · 방전 후 · 재충전 후 측정 필요");
    else {
      const drop = v0 - v1, rec = v2 - v1;
      add("H4", t, drop > 0 && rec >= 0.5 * drop ? "충족" : "불충족",
        `${v0.toFixed(3)} → 방전 후 ${v1.toFixed(3)} → 재충전 후 ${v2.toFixed(3)} V (기준: 떨어진 만큼의 50 % 이상 회복)`);
    }
    [["H5", "LED", "LED 가 켜짐", "모델: LED+470 Ω, 처음 약 14 mA 로 밝다가 연료+빛으로 약 93시간 희미하게 유지"],
     ["H6", "꼬마전구", "꼬마전구가 빛남", "모델: 6조각 병렬 시 처음 약 6분만 붉게 빛남, 지속 불가"]].forEach(([id, load, title, model]) => {
      const rec = m.filter((x) => x.load === load), lit = rec.filter((x) => x.lit === "켜짐" || x.lit === "희미").length;
      if (!rec.length) add(id, title, "데이터 부족", `${load} 연결 기록 없음. ${model}`);
      else add(id, title, lit ? "충족" : "불충족", `${rec.length}건 중 점등 ${lit}건. ${model}`);
    });
    t = "보관 중 전압 감쇠 시간 (모델 약 72일)";
    const shelf = open.filter((x) => x.sample === MAIN && x.elapsed !== null && x.v > 0 && (x.phase === "보관 중" || x.phase === "절단 후"))
      .sort((a, b) => a.elapsed - b.elapsed);
    if (shelf.length < 3 || shelf[shelf.length - 1].elapsed - shelf[0].elapsed < 24)
      add("H7", t, "데이터 부족", "하루 이상 간격으로 3번 이상 개방전압 측정 필요");
    else {
      const mx = avg(shelf.map((x) => x.elapsed)), my = avg(shelf.map((x) => Math.log(x.v)));
      const slope = shelf.reduce((s, x) => s + (x.elapsed - mx) * (Math.log(x.v) - my), 0) / shelf.reduce((s, x) => s + (x.elapsed - mx) ** 2, 0);
      const tau = slope < 0 ? -1 / slope / 24 : Infinity;
      add("H7", t, tau >= 24 && tau <= 216 ? "충족" : "불충족", `측정 시상수 ${isFinite(tau) ? tau.toFixed(1) + "일" : "감쇠 없음"} (기준: 모델의 1/3~3배)`);
    }
    if (m.some((x) => x.probe.includes("금속")))
      add("주의", "금속 프로브 사용 기록 있음", "확인 필요",
        "금속 프로브는 식염수와 닿으면 접촉 전위(수십~수백 mV)로 가짜 전압을 만들 수 있음 → 흑연 막대 2개 사용 권장, 대조군과 반드시 비교");
    return v;
  }
  async function loadVerdict() {
    let j = null;
    try {
      if (location.protocol === "file:") throw new Error("서버 없음");
      const r = await fetch("api/verdict", { cache: "no-store" });
      j = await r.json();
      if (j.error) throw new Error(j.error);
    } catch (e) {
      const ocv = (DATA.crosscheck && DATA.crosscheck.sample && DATA.crosscheck.sample.ocv_v) || DATA.ocv;
      j = { log: "이 브라우저 (서버 없이 같은 규칙으로 판정)", model_ocv_v: ocv, verdicts: judge(window.__expRows || [], ocv) };
    }
    $("#verdictMsg").textContent = `기록 ${j.log} · 모델 예측 개방전압 ${j.model_ocv_v.toFixed(2)} V`;
    const cls = (s) => s === "충족" ? "ok" : s === "불충족" ? "bad" : "";
    $("#verdictTable").innerHTML = "<tr><th>가설</th><th>내용</th><th>판정</th><th>근거</th></tr>" +
      j.verdicts.map((v) => `<tr><td>${esc(v.id)}</td><td>${esc(v.title)}</td><td><span class="badge ${cls(v.status)}">${esc(v.status)}</span></td><td>${esc(v.detail)}</td></tr>`).join("");
  }
  window.__loadVerdict = loadVerdict;
  $("#reVerdict").onclick = loadVerdict;
  tabHooks.verify = loadVerdict;
})();

// ---------- 레시피 (통째 결정 · 인공세포형) ----------
(function recipeTab() {
  const r = (DATA.samples || []).find((x) => x.tissue);
  if (!r) return;
  const F = r.freezing;
  $("#recipeCards").innerHTML = `
    <h2>${esc(r.name)} — 500 mL 병 하나, 붓기 한 번</h2>
    <div class="cards">
      <div class="card"><div class="k">결정 (= 인공세포 조직)</div><div class="v">Ø${(2 * r.gel_r).toFixed(1)} × ${r.block_h.toFixed(0)} mm · 세포 약 ${(r.n_cells / 1e6).toFixed(0)}백만 개</div></div>
      <div class="card"><div class="k">방향성 동결</div><div class="v">${r.plate_c} °C 판 · 약 ${F.hours.toFixed(0)} h · 전선 ${F.v_mid_um_s.toFixed(1)}→${F.v_top_um_s.toFixed(1)} µm/s</div></div>
      <div class="card"><div class="k">세포 폭 (동결 추정 / 모델)</div><div class="v">${F.cell_mid_um.toFixed(0)}–${F.cell_top_um.toFixed(0)} µm / ${r.spacing_um.toFixed(0)} µm</div></div>
      <div class="card"><div class="k">내강 / 막 사이 소금물</div><div class="v">${r.c_lumen_mM.toFixed(1)} mM / ${r.c_brine_m.toFixed(2)} M</div></div>
      <div class="card"><div class="k">저장 화학 에너지</div><div class="v">${r.energy_j.toFixed(0)} J (세포 하나 ${(r.e_cell_j * 1e6).toFixed(1)} µJ)</div></div>
      <div class="card"><div class="k">윗면–아랫면 전압</div><div class="v">${(1000 * r.ocv).toFixed(1)} mV — 사실상 0 (층·극성 없음)</div></div>
    </div>
    <table>${r.amounts.map(([g, items]) => `<tr><th colspan="3">${esc(g)}</th></tr>` + items.map(([n, v, u]) => `<tr><td>${esc(n)}</td><td class="n">${v.toFixed(2)}</td><td>${esc(u)}</td></tr>`).join("")).join("")}</table>`;
  const P = r.process_summary, dur = (h) => (h >= 1 ? `${h.toFixed(1)} h` : `${Math.round(h * 60)} 분`);
  $("#recipeSum").textContent = `전체 약 ${P.hours.toFixed(0)} h (${P.days.toFixed(1)} 일) · 손이 드는 시간 약 ${P.hands_h.toFixed(1)} h · `
    + `수작업 ${P.hand_steps}단계 / 기계작업 ${P.machine_steps}단계. 기계작업 동안 사람은 확인만 합니다.`;
  $("#recipeSteps").innerHTML = "<tr><th>#</th><th>단계</th><th>구분</th><th>손</th><th>걸림</th><th>장비</th><th>할 일</th><th>넘어가는 조건</th></tr>"
    + r.process.map((x, k) => `<tr><td>${k + 1}</td><td><b>${esc(x.title)}</b></td><td><span class="mode ${x.mode}">${esc(x.mode_ko)}</span></td>`
      + `<td class="n">${x.hands_min.toFixed(0)} 분</td><td class="n">${dur(x.hours)}</td><td>${esc(x.equipment.join(" · "))}</td><td>${esc(x.action)}</td><td>${esc(x.check)}</td></tr>`).join("");
  $("#recipeCtrl").innerHTML = "<tr><th>시료</th><th>만드는 법</th><th>보려는 것</th></tr>" + [
    ["대조군 A: 방향 없이 빨리 얼림", "같은 병을 냉동실에 그냥 넣음 (단열·금속판 없음)", "세포가 작고 고름 · 위아래 차이 없음"],
    ["대조군 B: 식염수 + PVA 만", "GO 없이 같은 동결", "막(GO)이 없으면 소금물이 갇히지 않음 → 대비 약함"],
    ["대조군 C: 얼리지 않음", "같은 배합을 상온에 둠", "세포·막이 생기지 않음"],
  ].map((x) => `<tr>${x.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("");
})();

// ---------- 양자 모듈 ----------
(function quantumTab() {
  const Q = DATA.quantum;
  if (!Q) return;
  $("#qCards").innerHTML = [
    ["집단 이점 (N=128)", `병렬 대비 평균 전력 ×${Q.rows[Q.rows.length - 1].adv.toFixed(2)}`],
    ["충전 시간 축척", `∝ N^-${Q.exponent.toFixed(3)}`],
    ["실제 소자 충전 시간", `${Q.charge_fs.toFixed(1)} fs (ħΩ_R 0.1 eV 가정)`],
    ["결맞음 조건", `${Q.quantum_ok ? "유효" : "깨짐"} · 분자 ${Q.t2_fs} fs, 광자 ${Q.cavity_fs.toFixed(1)} fs`],
    ["최대 저장 에너지", `${Q.energy_mj.toFixed(3)} mJ`],
    ["저장 수명", `약 ${Q.lifetime_ns} ns — 전구 점등 불가`],
  ].map(([k, v]) => `<div class="card"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
  const svg = (n) => DATA.svgs.includes(n) ? `<img class="fig" src="svg/${n}" style="background:none;border:0">` : "";
  $("#qSvgs").innerHTML = svg("quantum_charging.svg") + svg("qmodule_section.svg");
  $("#qTable").innerHTML = "<tr><th>분자 수 N</th><th>충전 시간 τ (1/g)</th><th>저장 E/N</th><th>에르고트로피/N</th><th>병렬 대비 전력 Γ</th></tr>" +
    Q.rows.map((r) => `<tr><td class="n">${r.n}</td><td class="n">${r.tau.toFixed(5)}</td><td class="n">${r.e.toFixed(4)}</td><td class="n">${r.w.toFixed(4)}</td><td class="n">×${r.adv.toFixed(3)}</td></tr>`).join("");
  $("#qCross").innerHTML = "<tr><th>구현</th><th>판정</th><th>비교 항목</th><th>최대 상대차</th></tr>" +
    Object.entries(Q.cross).map(([l, r]) => `<tr><td>${l === "csharp" ? "C#" : "Rust"} vs Python</td><td>${r.error ? '<span class="badge bad">실행 실패</span>' : r.ok ? '<span class="badge ok">✔ 일치</span>' : '<span class="badge bad">✘</span>'}</td><td class="n">${r.n ?? "-"}</td><td class="n">${r.max_rel !== undefined ? r.max_rel.toExponential(1) : esc(r.error)}</td></tr>`).join("");
  const C = Q.cad || {};
  $("#qCadNote").textContent = (C.tool ? `${C.tool} · ${C.date}` : "") + (C.note ? " · " + C.note : "");
  $("#qCad").innerHTML = "<tr><th>파일</th><th>만든 곳</th><th>고체</th><th>B-rep 유효</th><th>면/고체</th><th>부피 mm³ (해석값)</th><th>층별 최대 오차</th><th></th></tr>" +
    Object.entries(C.files || {}).map(([f, r]) => `<tr><td>${esc(f)}</td><td>${f.includes("rust") ? "Rust · truck 커널" : "C# · StepWriter"}</td><td class="n">${r.solids}/${r.expected}</td><td>${r.valid === r.solids ? '<span class="badge ok">✔ ' + r.valid + "</span>" : r.valid}</td><td class="n">${r.faces_per_solid.join(",")}</td><td class="n">${r.volume_mm3.toFixed(6)} (${r.analytic_mm3.toFixed(6)})</td><td class="n">${r.max_layer_rel_err.toExponential(1)}</td><td>${Q.steps.includes(f) ? `<a href="cad/step/${esc(f)}" download>STEP 받기</a>` : ""}</td></tr>`).join("");
  $("#qText").textContent = Q.text;
})();

// ---------- 실험 기록 ----------
(function experiments() {
  const LS = "snss-experiments";
  let useServer = true, rows = [];
  const local = () => { try { return JSON.parse(localStorage.getItem(LS) || "[]"); } catch (e) { return []; } };
  async function load() {
    try {
      if (location.protocol === "file:") throw new Error("서버 없음");
      const r = await fetch("api/experiments", { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      rows = await r.json(); useServer = true;
      $("#logMsg").textContent = "서버의 experiments/log.jsonl 에 저장됩니다.";
    } catch (e) {
      rows = local(); useServer = false;
      $("#logMsg").textContent = "서버 저장소에 연결하지 못해 이 브라우저에만 저장합니다.";
    }
    draw();
  }
  function draw() {
    rows.sort((a, b) => (a.elapsed_h ?? 0) - (b.elapsed_h ?? 0));
    window.__expRows = rows;
    $("#expTable").innerHTML = "<tr><th>경과 h</th><th>레시피</th><th>시료</th><th>단계</th><th>높이</th><th>극성</th><th>부하/점등</th><th>전압 V</th><th>전류 mA</th><th>프로브</th><th>메모</th><th></th></tr>" +
      rows.map((r) => `<tr><td class="n">${esc(r.elapsed_h)}</td><td>${esc(r.recipe)}</td><td>${esc(r.sample)}</td><td>${esc(r.phase)}</td><td class="n">${esc(r.height_mm)}</td><td>${esc(r.polarity)}</td><td>${esc(r.load)} ${esc(r.lit)}</td><td class="n">${esc(r.voltage_v)}</td><td class="n">${esc(r.current_ma)}</td><td>${esc(r.probe)}</td><td>${esc(r.note)}</td><td><button class="ghost" data-del="${esc(r.id)}">삭제</button></td></tr>`).join("");
    if (window.__loadVerdict) window.__loadVerdict();
    [...document.querySelectorAll("[data-del]")].forEach((b) => b.onclick = () => remove(b.dataset.del));
    chart();
  }
  function chart() {
    const svg = $("#chart"), Wd = 900, Hd = 280, L = 54, R = 16, T = 16, Bm = 36;
    const pts = rows.filter((r) => r.voltage_v != null && r.elapsed_h != null);
    const xmax = Math.max(1, ...pts.map((p) => p.elapsed_h)) * 1.05;
    const recs = (DATA.samples || []).filter((s) => s.recipe || s.tissue);
    const used = new Set(rows.map((r) => r.recipe).filter(Boolean));
    const lines = recs.filter((s) => !used.size || used.has(s.name));
    const ymax = Math.max(...lines.map((s) => s.ocv * 1.25), ...pts.map((p) => p.voltage_v), 0.1);
    const sx = (x) => L + (x / xmax) * (Wd - L - R), sy = (y) => Hd - Bm - (y / ymax) * (Hd - T - Bm);
    let g = "";
    for (let i = 0; i <= 4; i++) { const y = ymax * i / 4; g += `<line x1="${L}" x2="${Wd - R}" y1="${sy(y)}" y2="${sy(y)}" stroke="currentColor" stroke-opacity=".12"/><text x="${L - 6}" y="${sy(y) + 4}" text-anchor="end" font-size="11" fill="currentColor" fill-opacity=".6">${y.toFixed(1)}</text>`; }
    for (let i = 0; i <= 5; i++) { const x = xmax * i / 5; g += `<text x="${sx(x)}" y="${Hd - Bm + 16}" text-anchor="middle" font-size="11" fill="currentColor" fill-opacity=".6">${x.toFixed(1)}</text>`; }
    g += `<text x="${(L + Wd) / 2}" y="${Hd - 6}" text-anchor="middle" font-size="12" fill="currentColor" fill-opacity=".7">결정화 시작 후 경과 [h]</text>`;
    g += `<text x="14" y="${Hd / 2}" transform="rotate(-90 14 ${Hd / 2})" text-anchor="middle" font-size="12" fill="currentColor" fill-opacity=".7">전압 [V]</text>`;
    const LC = ["#1d5fa8", "#2f8a4f", "#8e44ad"];
    lines.forEach((s, k) => {
      g += `<line x1="${L}" x2="${Wd - R}" y1="${sy(s.ocv)}" y2="${sy(s.ocv)}" stroke="${LC[k % 3]}" stroke-dasharray="6 4" stroke-width="1.5"/>`;
      g += `<text x="${Wd - R - 4}" y="${sy(s.ocv) - 6}" text-anchor="end" font-size="12" fill="${LC[k % 3]}">${esc(s.name)} 예측 ${(1000 * s.ocv).toFixed(1)} mV</text>`;
    });
    g += `<line x1="${L}" x2="${Wd - R}" y1="${sy(0.05)}" y2="${sy(0.05)}" stroke="#b3261e" stroke-opacity=".5" stroke-dasharray="2 4"/><text x="${L + 6}" y="${sy(0.05) - 5}" font-size="11" fill="#b3261e" fill-opacity=".8">E2 기준 50 mV (대칭이면 이보다 작음)</text>`;
    if (pts.length > 1) g += `<polyline fill="none" stroke="#d1495b" stroke-width="2" points="${pts.map((p) => `${sx(p.elapsed_h)},${sy(p.voltage_v)}`).join(" ")}"/>`;
    g += pts.map((p) => `<circle cx="${sx(p.elapsed_h)}" cy="${sy(p.voltage_v)}" r="4" fill="#d1495b"><title>${p.elapsed_h} h · ${p.voltage_v} V · ${esc(p.state)}</title></circle>`).join("");
    if (!pts.length) g += `<text x="${(L + Wd) / 2}" y="${Hd / 2}" text-anchor="middle" font-size="13" fill="currentColor" fill-opacity=".55">측정 전압을 기록하면 여기 모델 예측과 함께 표시됩니다</text>`;
    svg.innerHTML = g;
  }
  async function remove(id) {
    if (useServer) { await fetch("api/experiments/" + encodeURIComponent(id), { method: "DELETE" }); return load(); }
    const keep = local().filter((r) => r.id !== id);
    try { localStorage.setItem(LS, JSON.stringify(keep)); } catch (e) {}
    rows = keep; draw();
  }
  $("#expForm").onsubmit = async (ev) => {
    ev.preventDefault();
    const rec = Object.fromEntries(new FormData(ev.target).entries());
    if (useServer) {
      const r = await fetch("api/experiments", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(rec) });
      if (!r.ok) { $("#logMsg").textContent = "저장 실패: " + ((await r.json()).error || r.status); return; }
    } else {
      const num = (v) => (v === "" ? null : +v);
      const all = local();
      all.push({ id: Math.random().toString(16).slice(2, 14), created: new Date().toISOString(), ...rec,
                 elapsed_h: num(rec.elapsed_h), temp_c: num(rec.temp_c), saline_ml: num(rec.saline_ml), go_g: num(rec.go_g),
                 voltage_v: num(rec.voltage_v), current_ma: num(rec.current_ma) });
      try { localStorage.setItem(LS, JSON.stringify(all)); } catch (e) {}
    }
    ev.target.reset();
    defaults();
    load();
  };
  $("#csv").onclick = () => {
    const cols = ["created", "elapsed_h", "recipe", "sample", "phase", "height_mm", "probe", "polarity", "load", "lit", "temp_c", "saline_ml", "go_g", "reactants", "state", "voltage_v", "current_ma", "note"];
    const csv = "﻿" + cols.join(",") + "\n" + rows.map((r) => cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "snss_experiments.csv"; a.click();
  };
  // 고른 레시피의 구매량으로 식염수·GO 기본값 (GO g = 분산액 mL × 4 mg/mL)
  function defaults() {
    const f = $("#expForm"), r = (DATA.samples || []).find((x) => x.name === f.recipe.value);
    f.saline_ml.value = r && r.q ? r.q.buy_saline_ml.toFixed(0) : r ? r.fill_ml.toFixed(0) : DATA.bottle.volume;
    f.go_g.value = r && r.q ? (r.q.buy_go_ml * 4 / 1000).toFixed(2) : r ? r.go_g.toFixed(2) : DATA.go_g;
  }
  $("#expForm").recipe.onchange = defaults;
  defaults();
  load();
})();

let saved = null;
try { saved = localStorage.getItem("snss-tab"); } catch (e) {}
const fromHash = fromHashSec();
show(fromHash ? fromHash.dataset.tab : sections.some((s) => s.dataset.tab === saved) ? saved : "빛 조각가 · 콘솔");
</script>
<script src="ui/lab.js"></script>
<script src="ui/tools.js"></script>
<script type="importmap">
{ "imports": { "three": "./vendor/three/three.module.js", "three/addons/": "./vendor/three/" } }
</script>
<script type="module" src="ui/workbench.js"></script>
<script type="module" src="ui/sculptor.js"></script>
<script src="light/exposure.js"></script>
<script src="light/being.js"></script>
<script type="module" src="ui/light.js"></script>
</body>
</html>
"""
