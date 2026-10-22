"""교차 검증: 같은 명세(spec/SPEC.md)를 Python · Rust · C# 가 각각 계산해 결과를 비교한다.

    python -m snss_battery crosscheck
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
from pathlib import Path

from .bottle import BottleGelBattery, BottleSpec, GelFormation
from .electrolyte import SalineSolution
from .metabolism import LED, IncandescentBulb, Metabolism, best_parallel, operating_current
from .tessellation import FractalVoronoiParams, analyze

ROOT = Path(__file__).resolve().parent.parent
SPEC_CASES = ROOT / "spec" / "cases.json"

INT_KEYS = {"n_pairs", "n_cells", "n_inner_ridges", "bulb_best_k", "steps"}
SIM_KEYS = {"led_on_fraction", "led_current_end_a", "bulb_peak_w", "led_first_off_h", "bulb_glow_min"}


def build(case: dict) -> BottleGelBattery:
    if case["bottle_ml"] > 520 and case["bottle_d_mm"] < 80:
        raise ValueError("사례의 병 치수가 맞지 않습니다.")
    body = 150.0 if case["bottle_ml"] <= 600 else 200.0
    return BottleGelBattery(
        BottleSpec(fill_volume_ml=case["bottle_ml"], outer_diameter_mm=case["bottle_d_mm"], body_height_mm=body),
        GelFormation(go_mg_per_ml=case["go_mg_ml"], layer_thickness_mm=case["layer_mm"],
                     concentration_ratio=case["ratio"], shrinkage=case["shrink"],
                     surface_go_mg_cm2=case["surface_go"]),
        SalineSolution(case["nacl_wt"], case["temp_c"]),
    )


def _first_off_and_fraction(bat, met, load, hours, dt, k):
    bat, met = copy.deepcopy(bat), copy.deepcopy(met)
    met.attach(bat)
    s = bat.stack
    steps = int(hours * 3600 / dt)
    first_off, on, i = None, 0, 0.0
    for n in range(steps + 1):
        t = n * dt
        i = operating_current(s.open_circuit_voltage() / k, s.internal_resistance() / k ** 2, load)
        if load.lit(i):
            on += 1
        elif first_off is None:
            first_off = t / 3600
        s.step(i / k, dt, met.pump_a(bat, t))
        met.consume(dt)
    return first_off, on / (steps + 1), i


def python_results(case: dict) -> dict:
    bat = build(case)
    s = bat.stack
    f = case["fractal"]
    prm = FractalVoronoiParams(f["D"], f["roughness"], f["correlation"], f["Ds"], f["grains"],
                               f["window_layers"], f["window_mm"], f["seed"])
    net = analyze(s, case["layer_mm"], 2 * s.n_pairs, bat.gel_area_cm2 * 100, prm, keep_geometry=False)
    raw = net.raw
    out = {
        "n_pairs": s.n_pairs, "c0": s.c0, "ocv_v": s.open_circuit_voltage(), "r_int_ohm": s.internal_resistance(),
        "capacity_c": s.capacity_c, "contact_f": s.electrode_capacitance_f,
        "n_cells": raw["n_cells"], "n_inner_ridges": raw["n_inner_ridges"], "v_oc_window": raw["v_oc_window"],
        "r_window": raw["r_window"], "p_loss_window": raw["p_loss_window"], "active_length": raw["active_length"],
        "defect_length": raw["defect_length"], "mean_neighbors": raw["mean_neighbors"],
        "net_ocv_v": net.ocv_v, "net_r_ohm": net.resistance_ohm, "net_leak_ma": net.leak_current_ma,
    }
    if case.get("lighting"):
        met = Metabolism()
        b2 = copy.deepcopy(bat)
        met.attach(b2)
        out["light_pump_a"] = met.light.pump_a(b2)
        out["fuel_pump_a"] = met.fuel.pump_a(b2)
        out["evap_emf_v"] = met.evaporation.emf_v(b2)
        off, frac, i_end = _first_off_and_fraction(bat, met, LED(), 168.0, 60.0, 1)
        out["led_first_off_h"] = -1.0 if off is None else off
        out["led_on_fraction"] = frac
        out["led_current_end_a"] = i_end
        bulb = IncandescentBulb()
        k = best_parallel(bat, met, bulb)
        out["bulb_best_k"] = k
        m3 = copy.deepcopy(met)
        b3 = copy.deepcopy(bat)
        m3.attach(b3)
        i0 = operating_current(b3.stack.open_circuit_voltage() / k, b3.stack.internal_resistance() / k ** 2, bulb)
        out["bulb_peak_w"] = i0 * bulb.voltage(i0)
        off_b, _, _ = _first_off_and_fraction(bat, met, bulb, 2.0, 2.0, k)
        out["bulb_glow_min"] = -1.0 if off_b is None else off_b * 60
    return out


def recipe_python(spec: dict) -> dict:
    """레시피 재료량 + 결정 예측 (spec/SPEC.md §10)."""
    from .recipe import Recipe

    r = Recipe(**spec)
    p = r.predict()
    return {"c_dilute_m": r.c_dilute_m, "c_conc_m": r.c_conc_m, "ratio": r.ratio, "area_cm2": r.area_cm2,
            "layer_ml": r.layer_ml, "mix_ml": r.mix_ml, "height_mm": r.height_mm, "steps": r.steps(),
            **r.quantities(), "n_pairs": p["pairs"], "ocv_v": p["ocv_v"], "r_int_ohm": p["r_ohm"],
            "led_ma": p["led_ma"]}


def _run(cmd: list[str], cwd: Path, timeout: int = 900) -> dict:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} 실패:\n{p.stderr[-2000:]}")
    return json.loads(p.stdout)


def external_results(lang: str) -> dict:
    cases = str(SPEC_CASES)
    if lang == "rust":
        if not shutil.which("cargo"):
            raise RuntimeError("cargo 없음")
        return _run(["cargo", "run", "--release", "--quiet", "--", "crosscheck", cases], ROOT / "rust")
    if lang == "csharp":
        if not shutil.which("dotnet"):
            raise RuntimeError("dotnet 없음")
        return _run(["dotnet", "run", "-c", "Release", "--project", "Snss.Lab", "--", "crosscheck", cases],
                    ROOT / "csharp")
    raise ValueError(lang)


def recipe_external(lang: str) -> dict:
    cases = str(SPEC_CASES)
    if lang == "rust":
        return _run(["cargo", "run", "--release", "--quiet", "--", "recipe", cases], ROOT / "rust")
    return _run(["dotnet", "run", "-c", "Release", "--project", "Snss.Lab", "--", "recipe", cases], ROOT / "csharp")


def _tol(key: str) -> float:
    if key in INT_KEYS:
        return 0.0
    if key in SIM_KEYS:
        return 1e-4
    return 1e-6


def compare(ref: dict, other: dict) -> list[dict]:
    rows = []
    for key, a in ref.items():
        b = other.get(key)
        if b is None:
            rows.append({"key": key, "ref": a, "other": None, "rel": math.inf, "ok": False})
            continue
        if key == "led_first_off_h" or key == "bulb_glow_min":
            step = (60.0 / 3600) if key == "led_first_off_h" else (2.0 / 60)
            ok = abs(a - b) <= step + 1e-9
            rel = abs(a - b)
        else:
            rel = abs(a - b) / max(abs(a), 1e-12) if a != b else 0.0
            ok = rel <= _tol(key) or abs(a - b) < 1e-12
        rows.append({"key": key, "ref": a, "other": b, "rel": rel, "ok": ok})
    return rows


def run_all(langs=("rust", "csharp")) -> dict:
    spec = json.loads(SPEC_CASES.read_text(encoding="utf-8"))
    py = {c["name"]: python_results(c) for c in spec["cases"]}
    rpy = {r["name"]: recipe_python(r) for r in spec.get("recipes", [])}
    report = {"python": py, "recipes": rpy, "languages": {}}
    for lang in langs:
        try:
            ext = external_results(lang)
        except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            report["languages"][lang] = {"error": str(e)}
            continue
        per_case = {}
        for name, ref in py.items():
            rows = compare(ref, ext.get(name, {}))
            per_case[name] = {"rows": rows, "ok": all(r["ok"] for r in rows)}
        try:  # 레시피 재료량 (§10) — 계산식이 닫힌 꼴이라 상대 1e-9
            rext = recipe_external(lang) if rpy else {}
            for name, ref in rpy.items():
                rows = compare(ref, rext.get(name, {}))
                for x in rows:
                    x["ok"] = x["ok"] and (x["key"] in INT_KEYS and x["rel"] == 0 or x["rel"] <= 1e-9)
                per_case[f"레시피: {name}"] = {"rows": rows, "ok": all(x["ok"] for x in rows)}
        except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            per_case["레시피"] = {"rows": [{"key": "실행", "ref": 0, "other": None, "rel": math.inf, "ok": False}],
                                "ok": False, "error": str(e)}
        report["languages"][lang] = {"cases": per_case, "ok": all(c["ok"] for c in per_case.values()),
                                     "results": ext}
    return report


def format_report(report: dict) -> str:
    out = []
    for lang, r in report["languages"].items():
        if "error" in r:
            out.append(f"[{lang}] 실행 실패: {r['error']}")
            continue
        out.append(f"[{lang}] {'✔ 모든 값 일치' if r['ok'] else '✘ 불일치 있음'}")
        for name, c in r["cases"].items():
            worst = max((x["rel"] for x in c["rows"] if math.isfinite(x["rel"])), default=0.0)
            bad = [x["key"] for x in c["rows"] if not x["ok"]]
            out.append(f"  {name:<22} {'✔' if c['ok'] else '✘'} 항목 {len(c['rows'])}개, 최대 차이 {worst:.2e}"
                       + (f"  불일치: {', '.join(bad)}" if bad else ""))
    return "\n".join(out)


# ---------- 양자 모듈 (spec/QUANTUM.md) ----------
def quantum_python() -> dict:
    from .quantum import scaling

    rows, a = scaling()
    return {"exponent": a, "rows": {str(r.n): {"steps": r.steps, "tau": r.tau, "energy": r.energy,
                                               "ergotropy": r.ergotropy, "advantage": r.advantage} for r in rows}}


def quantum_external(lang: str) -> dict:
    if lang == "rust":
        return _run(["cargo", "run", "--release", "--quiet", "--", "quantum"], ROOT / "rust")
    return _run(["dotnet", "run", "-c", "Release", "--project", "Snss.Lab", "--", "quantum"], ROOT / "csharp")


def quantum_check(langs=("rust", "csharp")) -> dict:
    ref = quantum_python()
    out = {"python": ref, "languages": {}}
    for lang in langs:
        try:
            ext = quantum_external(lang)
        except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            out["languages"][lang] = {"error": str(e)}
            continue
        worst, ok = 0.0, True
        pairs = [("exponent", ref["exponent"], ext.get("exponent"))]
        for n, r in ref["rows"].items():
            for k, v in r.items():
                pairs.append((f"N={n} {k}", v, ext.get("rows", {}).get(n, {}).get(k)))
        bad = []
        for name, a, b in pairs:
            if b is None:
                ok = False
                bad.append(name)
                continue
            rel = abs(a - b) / max(abs(a), 1e-300) if a != b else 0.0
            worst = max(worst, rel)
            limit = 0.0 if name.endswith("steps") else 1e-9
            if rel > limit:
                ok = False
                bad.append(name)
        out["languages"][lang] = {"ok": ok, "n": len(pairs), "max_rel": worst, "bad": bad}
    return out


# ---------- 빛 조각가 SC-2 (spec/SPEC.md §11, spec/LIGHT.md) ----------
LIGHT_CASES = ROOT / "spec" / "light_cases.json"
LIGHT_COLUMN_TOL = 1e-6  # lightsculpt._columns 는 E · D 를 float32 로 담음
LIGHT_TOL = 1e-9


def light_python(case: dict) -> dict:
    """lightsculpt.py 그대로 — 닫힌 꼴 값 + 짧은 기둥 노출 풀이 (405 nm · 530 nm)."""
    import numpy as np

    from .lightsculpt import Ink, LightSculptorSpec, Projector, _columns, build_time_estimate_h

    spec = LightSculptorSpec(ink=Ink(go_mg_ml=case["go_mg_ml"], pva_wt=case["pva_wt"], nacl_mm=case["nacl_mm"],
                                     eosin_um=case["eosin_um"], depth_mm=case["depth_mm"]),
                             projector=Projector(irradiance_mw_cm2=case["irradiance"], green_mw_cm2=case["green"]))
    x = spec.layer_ratio()
    out = {"dp_mm": spec.dp_mm(), "dp_green_mm": spec.dp_green_mm(), "layer_ratio": x, "layer_mm": spec.layer_mm,
           "membrane_leak": spec._membrane_leak(x), "e_cure": spec.e_cure(), "e_graft_target": spec.e_graft_target(),
           "ccc_mm": spec.ccc_mm(), "ink_density": spec.ink_density(), "ink_life_h": spec.ink_life_h(),
           "surface_rise_k": spec.surface_rise_k(), "heat_rise_k": spec.heat_rise_k(),
           "build_time_h": build_time_estimate_h(spec, case["height_mm"])}
    h = spec.layer_mm
    for c, col in enumerate(case["columns"]):
        m = np.array([" PNM".index(ch) if ch != "0" else 0 for ch in col])[None, None, :]
        inside, cyto, pos = m != 0, (m == 1) | (m == 2), m == 1
        E, D = _columns(np.where(inside, spec.e_cure(), 0.0), np.where(cyto, spec.photo.e_red_mj_cm2, 0.0), h / spec.dp_mm())
        G, Dg = _columns(np.zeros(m.shape), np.where(pos, spec.e_graft_target(), 0.0), h / spec.dp_green_mm())
        for key, arr in (("E405", E), ("D405", D), ("E530", G), ("D530", Dg)):
            for k, v in enumerate(arr[0, 0]):
                out[f"col{c}.{key}.{k}"] = float(v)
    return out


def light_external(lang: str) -> dict:
    if lang == "rust":
        return _run(["cargo", "run", "--release", "--quiet", "--", "light", str(LIGHT_CASES)], ROOT / "rust")
    return _run(["dotnet", "run", "-c", "Release", "--project", "Snss.Lab", "--", "light", str(LIGHT_CASES)], ROOT / "csharp")


def light_check(langs=("rust", "csharp")) -> dict:
    cases = json.loads(LIGHT_CASES.read_text(encoding="utf-8"))["cases"]
    ref = {c["name"]: light_python(c) for c in cases}
    out = {"python": ref, "languages": {}}
    for lang in langs:
        try:
            ext = light_external(lang)
        except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            out["languages"][lang] = {"error": str(e)}
            continue
        worst, bad, n = {}, [], 0
        for name, r in ref.items():
            for k, a in r.items():
                n += 1
                b = ext.get(name, {}).get(k)
                if b is None:
                    bad.append(f"{name}: {k}")
                    continue
                rel = abs(a - b) / max(abs(a), 1e-300) if a != b else 0.0
                group = k.split(".")[1] if k.startswith("col") else k
                worst[group] = max(worst.get(group, 0.0), rel)
                if rel > (LIGHT_COLUMN_TOL if k.startswith("col") else LIGHT_TOL):
                    bad.append(f"{name}: {k}")
        out["languages"][lang] = {"ok": not bad, "n": n, "max_rel": worst, "bad": bad}
    return out
