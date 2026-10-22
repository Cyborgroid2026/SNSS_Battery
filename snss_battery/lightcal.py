"""빛 상수 보정 — 시험편(사다리) 세 장으로 SC-2 의 가정값을 실측값으로 바꿈 (명세: spec/LIGHT.md §8).

멀티미터 · 버니어 캘리퍼스 · 흑연 기준 전극만으로 잴 수 있게 짰다.

A. 굳힘 사다리 (405 nm): 정사각형마다 노출 E_i 를 달리 → 꺼내서 굳은 두께 Cd_i (캘리퍼스 · 현미경).
   SLA 작업 곡선 Cd = Dp·ln(E/Ec) — Cd 를 ln E 에 직선 맞춤 → 기울기 Dp, 절편 → Ec.
   Dp 에서 GO 흡광계수: ε_GO = (1/(ln10·Dp) − a_SbQ·PVA%) / c_GO.
B. 광환원 사다리 (405 nm): 얇게 굳힌 뒤 노출을 더 줌 → 정사각형 양 끝 흑연 패드로 2단자 저항 R_i.
   log10 σ(D) = a + b·(1 − e^(−D/τ)) 맞춤 (σ ∝ 1/R) → E_red = 로그 상승 90 % 노출 = τ·ln10,
   θ = 막 한도(로그 상승 50 %) 노출 / E_red = ln 2 / ln 10 = 0.30 — 막이 세포질보다 전도도 자릿수 절반(6 자릿수면 3 자릿수) 이상
   낮게 남으면 전자를 막는다고 봄. θ 는 맞춤값이 아니라 이 기준의 정의 (mem_frac 로 바꿈).
C. 초록 접목 사다리 (530 nm): E_red 로 다 환원한 뒤 초록 노출 → 배지 속 개방 전위를 도핑 안 한 정사각형 기준으로 잼 ΔV_i.
   ΔV(D) = ΔV_max·(1 − e^(−D/E_g)) 맞춤 → E_g. ΔV_max ≈ 페르미 준위 이동 → 정공 밀도 n = (eΔV_max/ħv_F)²/π.

D. 전기 도핑 사다리 (사후, PEI 도핑 통): 다 환원한 칸마다 다른 전위 E_i 로 잡고 (흑연 기준, 다채널 · 저항 분압) 24 h →
   씻은 뒤 배지 속 개방 전위 차 ΔV_i (n형이면 +). ΔV = ΔV_max / (1 + e^((E − E½)/w)) 맞춤 → E½ · w, ΔV_max → n_max.
   (얇은 칸이라 확산은 다 됨 — 확산 계수는 따로, 두꺼운 덩어리를 잘라 단면으로)

E. 주입량 사다리 (T1 유리 피펫): 다 환원한 칸(8 mm)마다 PEI:GO 질량비 r_i 만큼 PEI 1 % 를 가운데 주입 → 24 h 뒤 흑연 탐침(T5)으로 ΔV.
   ΔV → 전자 밀도 n = (eΔV/ħv_F)²/π, n = n_max·(1 − e^(−r·ln10/r_sat)) 맞춤 → r_sat (90 % 붙는 비) · n_max.
F. 막 너머 샘: 막(굳힘만) 한 줄을 사이에 둔 두 칸 중 하나에만 주입 → 두 칸의 ΔV. 샘 = n_이웃/n_주입 = (ΔV_이웃/ΔV_주입)².

결과는 sculpt_out/light_cal.json 에 쓰고, `LightSculptorSpec.calibrated(path)` · `light --cal` 이 읽는다.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from .lightsculpt import LightSculptorSpec, Photo

SQUARE_MM = 8.0  # 사다리 한 칸
GAP_MM = 3.0
COLS = 6


def ladders(spec: LightSculptorSpec | None = None) -> dict:
    """세 사다리의 노출량 (mJ/cm²) — 지금 가정값을 가운데 두고 넓게 (등비)."""
    spec = spec or LightSculptorSpec()
    ph = spec.photo
    return {
        "A": list(np.round(np.geomspace(ph.ec_mj_cm2 * 1.5, ph.ec_mj_cm2 * 60, 12), 1)),
        "B": list(np.round(np.geomspace(ph.e_red_mj_cm2 * 0.05, ph.e_red_mj_cm2 * 4, 12), 0)),
        "C": list(np.round(np.geomspace(ph.e_graft_mj_cm2 * 0.1, ph.e_graft_mj_cm2 * 6, 12), 0)),
    }


EDOPE_V = [round(float(v), 2) for v in np.linspace(-0.8, 0.4, 12)]  # 사다리 D 의 칸 전위 (V, 흑연 기준)
INJ_RATIO = [round(float(v), 3) for v in np.geomspace(0.02, 1.5, 10)]  # 사다리 E 의 PEI:GO 질량비
LEAK_PAIRS = 2  # 시험 F 의 칸 짝


def _n_from_mv(dv_mv):
    from .qcap import E, HBAR, V_F

    return (np.abs(np.asarray(dv_mv, float)) / 1000 * E / (HBAR * V_F)) ** 2 / math.pi / 1e16


def _mv_from_n(n):
    from .qcap import E, HBAR, V_F

    return HBAR * V_F * math.sqrt(math.pi * max(n, 0.0) * 1e16) / E * 1000


def inject_coupon(spec: LightSculptorSpec | None = None, ts=None, px_mm: float = 0.05) -> dict:
    """시험 E · F 의 빛 그림 (다 환원한 칸 + F 짝 사이 막) 과 T1 주입 자리 (가운데 = 좌표 0)."""
    from .lighttools import ToolSpec

    spec = spec or LightSculptorSpec()
    ts = ts or ToolSpec()
    pitch = SQUARE_MM + GAP_MM
    e_cyto, e_mem = spec.photo.e_red_mj_cm2 * 1.5, spec.e_cure()
    cd = spec.layer_mm * (1 + spec.photo.overcure)  # 한 번 노출로 굳는 두께
    go_mg = SQUARE_MM ** 2 * cd / 1000 * spec.ink.go_mg_ml  # 칸 하나의 GO (mg)
    squares = [("E", i + 1, r) for i, r in enumerate(INJ_RATIO)]
    w_mm, h_mm = COLS * pitch + GAP_MM, 4 * pitch + GAP_MM
    img = np.zeros((int(round(h_mm / px_mm)), int(round(w_mm / px_mm))), dtype=np.float32)
    s = int(round(SQUARE_MM / px_mm))
    targets = []

    def put(r, c, x_off=0.0):
        y0, x0 = int(round((GAP_MM + r * pitch) / px_mm)), int(round((GAP_MM + c * pitch + x_off) / px_mm))
        img[y0:y0 + s, x0:x0 + s] = 1.0
        return (GAP_MM + c * pitch + x_off + SQUARE_MM / 2 - w_mm / 2, GAP_MM + r * pitch + SQUARE_MM / 2 - h_mm / 2)

    for n, (t, i, r) in enumerate(squares):
        x, y = put(*divmod(n, COLS))
        targets.append((t, i, x, y, r * go_mg / (ts.inj.pei_wt * 10) * 1000))  # µL = mg / (mg/mL) × 1000
    for j in range(LEAK_PAIRS):  # F: 두 칸을 막 한 줄(0.41 mm)로 붙여 놓음
        r_row, c0 = 2 + j, 0
        xa, y = put(r_row, c0)
        put(r_row, c0, SQUARE_MM + 0.41)
        y0 = int(round((GAP_MM + r_row * pitch) / px_mm))
        xm = int(round((GAP_MM + c0 * pitch + SQUARE_MM) / px_mm))
        img[y0:y0 + s, xm:xm + int(round(0.41 / px_mm))] = e_mem / e_cyto
        targets.append(("F", 2 * j + 1, xa, y, ts.inj.pei_go_saturate * go_mg / (ts.inj.pei_wt * 10) * 1000))
    return {"gray": img, "seconds": e_cyto / spec.projector.irradiance_mw_cm2, "targets": targets, "thick_mm": cd}


def coupon_frames(spec: LightSculptorSpec | None = None, px_mm: float = 0.05) -> dict:
    """사다리 노출 그림 — 칸마다 밝기는 같고 칸마다 켜 두는 시간이 다름 → 회색조(시간 비례) 한 장 + 시간."""
    spec = spec or LightSculptorSpec()
    out = {}
    pitch = SQUARE_MM + GAP_MM
    n = int(round((COLS * pitch + GAP_MM) / px_mm))
    for key, doses in ladders(spec).items():
        rows = math.ceil(len(doses) / COLS)
        img = np.zeros((int(round((rows * pitch + GAP_MM) / px_mm)), n), dtype=np.float32)
        d_max = max(doses)
        for i, d in enumerate(doses):
            r, c = divmod(i, COLS)
            y0, x0 = int(round((GAP_MM + r * pitch) / px_mm)), int(round((GAP_MM + c * pitch) / px_mm))
            s = int(round(SQUARE_MM / px_mm))
            img[y0:y0 + s, x0:x0 + s] = d / d_max
        irr = spec.projector.green_mw_cm2 if key == "C" else spec.projector.irradiance_mw_cm2
        out[key] = {"gray": img, "seconds": d_max / irr, "doses": doses,
                    "pre": {"A": "없음 — 첫 층 그대로", "B": f"모든 칸 먼저 굳힘 {spec.e_cure():.0f} mJ/cm²",
                            "C": f"모든 칸 먼저 405 nm {spec.photo.e_red_mj_cm2 * 1.5:.0f} mJ/cm² (다 환원)"}[key]}
    return out


def write_coupon(folder: str | Path, spec: LightSculptorSpec | None = None) -> Path:
    """보정 시험편 묶음: 사다리 그림 PNG 3장 · 측정 기록표 CSV · 순서 안내."""
    from PIL import Image

    spec = spec or LightSculptorSpec()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fr = coupon_frames(spec)
    what = {"A": ("굳은 두께", "mm"), "B": ("2단자 저항", "ohm"), "C": ("개방 전위 차 (기준: 도핑 안 한 칸)", "mV")}
    rows = ["시험,칸,노출_mJ_cm2,측정값,단위,메모"]
    guide = [f"[SC-2 빛 상수 보정 — 시험편 3장] 칸 {SQUARE_MM:g} mm · 간격 {GAP_MM:g} mm · 프로젝터 픽셀 0.05 mm"]
    for key, f in fr.items():
        Image.fromarray(np.round(f["gray"] * 255).astype(np.uint8)[::-1]).save(folder / f"coupon_{key}.png")
        lab, unit = what[key]
        for i, d in enumerate(f["doses"]):
            rows.append(f"{key},{i + 1},{d:g},,{unit},")
        color = "530 nm" if key == "C" else "405 nm"
        guide.append(f"  {key}. {lab} — 먼저: {f['pre']} → coupon_{key}.png 를 {color} 로 {f['seconds']:.0f} s "
                     f"(회색조 = 켜 두는 시간 비례) · 노출 {f['doses'][0]:g}–{f['doses'][-1]:g} mJ/cm²")
    for i, v in enumerate(EDOPE_V):  # 전기 도핑: 노출 칸에 전위(V)를 적음
        rows.append(f"D,{i + 1},{v:g},,mV,전위 V")
    guide.append(f"  D. 전기 도핑 (사후) — 다 환원한 칸 12개를 도핑 통(배지 + PEI 0.1 %)에서 {EDOPE_V[0]:g}…{EDOPE_V[-1]:g} V 로 24 h → 개방 전위 차 (mV)")
    ic = inject_coupon(spec)
    Image.fromarray(np.round(ic["gray"] * 255).astype(np.uint8)[::-1]).save(folder / "coupon_EF.png")
    from .lighttools import _tool_footer, _tool_header, ToolSpec

    ts = ToolSpec()
    g = _tool_header("시험 E · F — 주입량 사다리 · 막 너머 샘", ic["thick_mm"], ts) + ["TOOL_PICK T=T1  ; 유리 미세 피펫", "PRIME T=T1 UL=2"]
    for t, i, x, y, ul in ic["targets"]:
        g += [f"; {t}{i}", f"G0 X{x:.2f} Y{y:.2f} Z{ic['thick_mm'] + 3:.2f}", f"G1 Z{ic['thick_mm'] / 2:.2f} F120",
              f"INJECT UL={ul:.3f} RATE={ts.head.inj_flow_ul_s:g}", f"G1 Z{ic['thick_mm'] + 3:.2f} F120"]
    (folder / "coupon_EF_inject.gcode").write_text("\n".join(g + _tool_footer()) + "\n", encoding="utf-8")
    for i, r in enumerate(INJ_RATIO):
        rows.append(f"E,{i + 1},{r:g},,mV,PEI:GO 질량비")
    for j in range(LEAK_PAIRS):
        rows += [f"F,{2 * j + 1},1,,mV,주입한 칸", f"F,{2 * j + 2},0,,mV,막 너머 이웃 칸"]
    guide.append(f"  E · F. 주입 — coupon_EF.png 를 405 nm 로 {ic['seconds']:.0f} s (다 환원 · F 짝 사이는 막) → 받침째 도구 면으로 → "
                 f"coupon_EF_inject.gcode (T1, PEI 1 %) → 24 h → T5 흑연 탐침으로 칸마다 개방 전위 차 (mV, 도핑 안 한 칸 기준)")
    guide += ["  측정 → measurements.csv 의 '측정값' 칸을 채우고: python -m snss_battery light-cal fit measurements.csv",
              "  B: 칸 양 끝에 흑연 시트 패드를 대고 멀티미터 저항 (배지에서 꺼내 표면 물기만 닦고, 같은 간격으로)",
              "  C: 배지 속에서 흑연 기준 전극 ↔ 칸 사이 개방 전위 (도핑 안 한 칸과의 차, mV) — 30 초 안정 뒤"]
    (folder / "measurements.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (folder / "README.txt").write_text("\n".join(guide) + "\n", encoding="utf-8")
    return folder


# ---------- 맞춤 ----------
def fit_working_curve(dose: np.ndarray, cd_mm: np.ndarray) -> dict:
    """Cd = Dp·ln(E/Ec): 굳은 칸(Cd > 0)만, 최소제곱 직선."""
    m = cd_mm > 0
    if m.sum() < 3:
        raise ValueError("굳은 칸이 3개보다 적어 작업 곡선을 맞출 수 없습니다.")
    x, y = np.log(dose[m]), cd_mm[m]
    dp, b = np.polyfit(x, y, 1)
    ec = math.exp(-b / dp)
    r = y - (dp * x + b)
    return {"dp_mm": float(dp), "ec_mj_cm2": float(ec), "rms_mm": float(np.sqrt(np.mean(r ** 2))), "n": int(m.sum())}


def _fit_saturating(dose: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float]:
    """y = a + b·(1 − e^(−D/τ)): τ 를 로그 격자로 훑고 a, b 는 선형 최소제곱."""
    best = None
    for tau in np.geomspace(dose.min() * 0.05, dose.max() * 5, 4000):
        A = np.stack([np.ones_like(dose), 1 - np.exp(-dose / tau)], 1)
        (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
        res = float(np.sum((A @ np.array([a, b]) - y) ** 2))
        if best is None or res < best[3]:
            best = (float(a), float(b), float(tau), res)
    return best


def fit_reduction(dose: np.ndarray, r_ohm: np.ndarray, mem_frac: float = 0.5) -> dict:
    a, b, tau, res = _fit_saturating(dose, np.log10(1 / r_ohm))
    e_red = tau * math.log(10)  # 로그 상승 90 %
    e_mem = tau * math.log(1 / (1 - mem_frac))
    return {"e_red_mj_cm2": e_red, "theta_mem": e_mem / e_red, "decades": b, "tau_mj_cm2": tau,
            "rms_decades": math.sqrt(res / len(dose))}


def fit_graft(dose: np.ndarray, dv_mv: np.ndarray) -> dict:
    from .qcap import E, HBAR, V_F

    a, b, tau, res = _fit_saturating(dose, dv_mv)
    ef = abs(a + b) / 1000  # V ≈ eV
    n = (ef * E / (HBAR * V_F)) ** 2 / math.pi / 1e16  # 10¹² cm⁻²
    return {"e_graft_mj_cm2": tau, "dv_max_mv": a + b, "n_graft_max": n, "rms_mv": math.sqrt(res / len(dose))}


def fit_edope(e_v: np.ndarray, dv_mv: np.ndarray) -> dict:
    """ΔV = ΔV_max / (1 + e^((E − E½)/w)): E½ · w 격자, ΔV_max 선형."""
    from .qcap import E, HBAR, V_F

    best = None
    for eh in np.linspace(-0.8, 0.4, 241):
        for w in np.geomspace(0.01, 0.5, 120):
            g = 1 / (1 + np.exp((e_v - eh) / w))
            amp = float(g @ dv_mv / max(g @ g, 1e-12))
            res = float(np.sum((amp * g - dv_mv) ** 2))
            if best is None or res < best[3]:
                best = (float(eh), float(w), amp, res)
    eh, w, amp, res = best
    n = (abs(amp) / 1000 * E / (HBAR * V_F)) ** 2 / math.pi / 1e16
    return {"e_half_v": eh, "width_v": w, "dv_max_mv": amp, "n_max": n, "rms_mv": math.sqrt(res / len(e_v))}


def fit_calibration(csv_path: str | Path, spec: LightSculptorSpec | None = None) -> dict:
    spec = spec or LightSculptorSpec()
    data: dict[str, list[tuple[float, float]]] = {"A": [], "B": [], "C": [], "D": [], "E": [], "F": []}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = (row.get("측정값") or "").strip()
            if v and row["시험"] in data:
                data[row["시험"]].append((float(row["노출_mJ_cm2"]), float(v)))
    out: dict = {"source": str(csv_path), "fits": {}, "photo": {}}
    ph, ink = spec.photo, spec.ink
    if len(data["A"]) >= 3:
        d, y = np.array(data["A"]).T
        fa = fit_working_curve(d, y)
        out["fits"]["A"] = fa
        out["photo"]["ec_mj_cm2"] = fa["ec_mj_cm2"]
        eps = (10 / (math.log(10) * fa["dp_mm"]) - ph.a_sbq * ink.pva_wt) / ink.go_mg_ml
        out["photo"]["eps_go"] = eps
    if len(data["B"]) >= 4:
        d, y = np.array(data["B"]).T
        fb = fit_reduction(d, y)
        out["fits"]["B"] = fb
        out["photo"]["e_red_mj_cm2"] = fb["e_red_mj_cm2"]
        out["photo"]["theta_mem"] = fb["theta_mem"]
    if len(data["C"]) >= 4:
        d, y = np.array(data["C"]).T
        fc = fit_graft(d, y)
        out["fits"]["C"] = fc
        out["photo"]["e_graft_mj_cm2"] = fc["e_graft_mj_cm2"]
        out["photo"]["n_graft_max"] = fc["n_graft_max"]
    if len(data["D"]) >= 5:
        e, y = np.array(data["D"]).T
        fd = fit_edope(e, y)
        out["fits"]["D"] = fd
        out["edope"] = {k: fd[k] for k in ("e_half_v", "width_v", "n_max")}
    if len(data["E"]) >= 4:
        r, y = np.array(data["E"]).T
        n = _n_from_mv(y)
        a, b, tau, res = _fit_saturating(r, n)
        out["fits"]["E"] = {"r_sat": tau * math.log(10), "n_max": a + b, "rms_n": math.sqrt(res / len(r))}
        out.setdefault("inject", {}).update({"pei_go_saturate": tau * math.log(10), "n_max": a + b})
    if len(data["F"]) >= 2:
        pairs = [(data["F"][i][1], data["F"][i + 1][1]) for i in range(0, len(data["F"]) - 1, 2)
                 if data["F"][i][0] == 1 and data["F"][i + 1][0] == 0]
        if pairs:
            leak = float(np.mean([(nb / inj) ** 2 for inj, nb in pairs if inj]))
            out["fits"]["F"] = {"leak": leak, "pairs": len(pairs)}
            out.setdefault("inject", {})["leak"] = leak
    if not out["photo"] and "edope" not in out and "inject" not in out:
        raise ValueError("측정값이 채워진 시험이 없습니다 (measurements.csv 의 '측정값' 칸).")
    return out


def calibrated_spec(cal: dict | str | Path, spec: LightSculptorSpec | None = None) -> LightSculptorSpec:
    if not isinstance(cal, dict):
        cal = json.loads(Path(cal).read_text(encoding="utf-8"))
    spec = spec or LightSculptorSpec()
    keys = {k: float(v) for k, v in cal.get("photo", {}).items() if k in asdict(spec.photo)}
    return replace(spec, photo=replace(spec.photo, **keys))


def calibrated_edope(cal: dict | str | Path, ed=None):
    """전기 도핑 상수 (사다리 D) 를 ElectroDope 에."""
    from .electrodope import ElectroDope

    if not isinstance(cal, dict):
        cal = json.loads(Path(cal).read_text(encoding="utf-8"))
    ed = ed or ElectroDope()
    return replace(ed, **{k: float(v) for k, v in cal.get("edope", {}).items()})


def calibrated_toolspec(cal: dict | str | Path, ts=None):
    """주입 상수 (시험 E · F) 를 ToolSpec 에."""
    from .lighttools import ToolSpec

    if not isinstance(cal, dict):
        cal = json.loads(Path(cal).read_text(encoding="utf-8"))
    ts = ts or ToolSpec()
    return replace(ts, inj=replace(ts.inj, **{k: float(v) for k, v in cal.get("inject", {}).items()}))


def describe_calibration(cal: dict, spec: LightSculptorSpec | None = None) -> str:
    spec = spec or LightSculptorSpec()
    base = asdict(Photo())
    lines = [f"[빛 상수 보정 — {cal['source']}]"]
    f = cal["fits"]
    if "A" in f:
        lines.append(f"  A 굳힘: Dp {f['A']['dp_mm']:.3f} mm · Ec {f['A']['ec_mj_cm2']:.1f} mJ/cm² (칸 {f['A']['n']}개, 잔차 {f['A']['rms_mm'] * 1000:.0f} µm)")
    if "B" in f:
        lines.append(f"  B 광환원: E_red {f['B']['e_red_mj_cm2']:.0f} mJ/cm² · 전도도 {f['B']['decades']:.1f} 자릿수 상승 · θ {f['B']['theta_mem']:.3f}")
    if "C" in f:
        lines.append(f"  C 초록 접목: E_g {f['C']['e_graft_mj_cm2']:.0f} mJ/cm² · ΔV {f['C']['dv_max_mv']:.0f} mV → 정공 {f['C']['n_graft_max']:.1f}×10¹² cm⁻²")
    if "D" in f:
        lines.append(f"  D 전기 도핑: E½ {f['D']['e_half_v']:+.2f} V · w {f['D']['width_v']:.3f} V · ΔV {f['D']['dv_max_mv']:.0f} mV → 전자 {f['D']['n_max']:.1f}×10¹² cm⁻²")
    if "E" in f:
        lines.append(f"  E 주입량: PEI:GO {f['E']['r_sat']:.2f} 에서 90 % · 전자 {f['E']['n_max']:.1f}×10¹² cm⁻²")
    if "F" in f:
        lines.append(f"  F 막 너머 샘: {f['F']['leak'] * 100:.1f} % (짝 {f['F']['pairs']}개)")
    lines.append("  바뀐 상수: " + " · ".join(f"{k} {base[k]:g} → {v:.4g}" for k, v in cal.get("photo", {}).items()))
    new = calibrated_spec(cal, spec)
    bad = new.check()
    lines.append(f"  보정 뒤: 층 {new.layer_mm} mm · 막 새는 빛 {new._membrane_leak(new.layer_ratio()):.2f}·E_red · 설계 점검 " +
                 ("통과" if not bad else "; ".join(bad)))
    return "\n".join(lines)


def synthetic_measurements(path: str | Path, truth: Photo, spec: LightSculptorSpec | None = None, noise: float = 0.03,
                           seed: int = 1) -> Path:
    """가상 측정 (시험 · 연습용): 참값 상수로 사다리 측정값을 만들고 잡음을 섞음."""
    from .qcap import E, HBAR, V_F

    spec = spec or LightSculptorSpec()
    rng = np.random.default_rng(seed)
    t_spec = replace(spec, photo=truth)
    dp = t_spec.dp_mm()
    lad = ladders(spec)
    rows = ["시험,칸,노출_mJ_cm2,측정값,단위,메모"]
    for i, d in enumerate(lad["A"]):
        cd = max(0.0, dp * math.log(d / truth.ec_mj_cm2)) * (1 + noise * rng.standard_normal())
        rows.append(f"A,{i + 1},{d:g},{cd:.4f},mm,")
    tau = truth.e_red_mj_cm2 / math.log(10)
    for i, d in enumerate(lad["B"]):
        logs = -6 + 6 * (1 - math.exp(-d / tau)) + noise * rng.standard_normal()
        rows.append(f"B,{i + 1},{d:g},{10 ** -logs:.6g},ohm,")
    ef = HBAR * V_F * math.sqrt(math.pi * truth.n_graft_max * 1e16) / E * 1000  # mV
    for i, d in enumerate(lad["C"]):
        dv = ef * (1 - math.exp(-d / truth.e_graft_mj_cm2)) * (1 + noise * rng.standard_normal())
        rows.append(f"C,{i + 1},{d:g},{dv:.2f},mV,")
    from .electrodope import ElectroDope

    ed = ElectroDope()
    ef_n = HBAR * V_F * math.sqrt(math.pi * ed.n_max * 1e16) / E * 1000
    for i, v in enumerate(EDOPE_V):
        dv = ef_n * ed.frac(v) * (1 + noise * rng.standard_normal())
        rows.append(f"D,{i + 1},{v:g},{dv:.2f},mV,전위 V")
    from .lighttools import Injection

    inj = Injection()
    for i, r in enumerate(INJ_RATIO):
        n = inj.n_max * (1 - math.exp(-r * math.log(10) / inj.pei_go_saturate))
        rows.append(f"E,{i + 1},{r:g},{_mv_from_n(n) * (1 + noise * rng.standard_normal()):.2f},mV,PEI:GO 질량비")
    for j in range(LEAK_PAIRS):
        n_inj = inj.n_max * (1 - math.exp(-math.log(10)))
        rows += [f"F,{2 * j + 1},1,{_mv_from_n(n_inj):.2f},mV,주입한 칸",
                 f"F,{2 * j + 2},0,{_mv_from_n(n_inj * inj.leak) * (1 + noise * rng.standard_normal()):.2f},mV,막 너머 이웃 칸"]
    Path(path).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return Path(path)
