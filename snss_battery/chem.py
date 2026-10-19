"""NaCl 수용액 화학 — PHREEQC (USGS) + Pitzer 데이터베이스.

진한 소금물(1–5 mol/kg)은 이상 용액에서 많이 벗어나므로, 막전위·어는점을 농도 대신 활동도로 계산합니다.
- 표 만들기: `python -m snss_battery chem` (phreeqpython 필요 → `.venv`) → spec/phreeqc_nacl.json
- 표 쓰기: 이 모듈의 함수들 (표만 있으면 phreeqpython 없이 동작)

어는점: 얼음과 평형인 용액은 ln a_w = −(ΔH_fus/R)(1/T_f − 1/T_0) 를 만족합니다 (ΔH_fus 온도 의존 무시 — 공정점 근처에서 약 1 K 오차).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from .constants import GAS_CONSTANT, thermal_voltage

TABLE = Path(__file__).resolve().parents[1] / "spec" / "phreeqc_nacl.json"
H_FUS = 6010.0  # 얼음 녹음열 J/mol
T0 = 273.15
GRID = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.154, 0.2, 0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 1.63,
        2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]


def build_table(temps_c: tuple[float, ...] = (0.0, 25.0)) -> dict:
    """PHREEQC(pitzer.dat)로 γ±·a_w 표를 계산 (phreeqpython 필요)."""
    from phreeqpython import PhreeqPython

    pp = PhreeqPython(database="pitzer.dat")
    out = {"source": "PHREEQC (phreeqpython) · pitzer.dat", "molality": GRID, "temps_c": list(temps_c), "gamma": {}, "aw": {}, "halite_si": {}}
    for tc in temps_c:
        g, a, si = [], [], []
        for m in GRID:
            pp.ip.run_string(f"""SOLUTION 1
 temp {tc}
 units mol/kgw
 Na {m}
 Cl {m}
SELECTED_OUTPUT
 -reset false
USER_PUNCH
 -headings aw gamma si
 10 PUNCH ACT("H2O"), (ACT("Na+")*ACT("Cl-"))^0.5/TOT("Na"), SI("Halite")
END""")
            row = pp.ip.get_selected_output_array()[1]
            a.append(row[0]); g.append(row[1]); si.append(row[2])
        out["gamma"][str(tc)], out["aw"][str(tc)], out["halite_si"][str(tc)] = g, a, si
    return out


def write_table(path: Path = TABLE) -> dict:
    t = build_table()
    path.write_text(json.dumps(t, indent=1), encoding="utf-8")
    return t


@lru_cache(maxsize=1)
def table() -> dict:
    return json.loads(TABLE.read_text(encoding="utf-8"))


def _interp(xs: list[float], ys: list[float], x: float) -> float:
    """로그 농도에 대해 선형 보간 (범위 밖은 끝값)."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lx = math.log(x)
    for k in range(1, len(xs)):
        if x <= xs[k]:
            u = (lx - math.log(xs[k - 1])) / (math.log(xs[k]) - math.log(xs[k - 1]))
            return ys[k - 1] + u * (ys[k] - ys[k - 1])
    return ys[-1]


def gamma(m: float, temp_c: float = 25.0) -> float:
    """NaCl 평균 활동도계수 γ± (0 °C 와 25 °C 표 사이 선형 보간)."""
    t = table()
    g0, g25 = (_interp(t["molality"], t["gamma"][k], m) for k in ("0.0", "25.0"))
    u = min(max(temp_c / 25.0, 0.0), 1.0)
    return g0 + u * (g25 - g0)


def water_activity(m: float, temp_c: float = 0.0) -> float:
    t = table()
    a0, a25 = (_interp(t["molality"], t["aw"][k], m) for k in ("0.0", "25.0"))
    u = min(max(temp_c / 25.0, 0.0), 1.0)
    return a0 + u * (a25 - a0)


def freezing_point_c(m: float) -> float:
    """얼음과 평형인 온도 [°C]."""
    aw = water_activity(m, 0.0)
    return 1 / (1 / T0 - GAS_CONSTANT * math.log(aw) / H_FUS) - T0


def brine_at(temp_c: float) -> float:
    """온도 temp_c 에서 얼음과 공존하는 소금물 농도 [mol/kg] (이분법). 공정점보다 차가우면 공정 조성."""
    lo, hi = 1e-4, 6.0
    if freezing_point_c(hi) > temp_c:
        return hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if freezing_point_c(mid) > temp_c else (lo, mid)
    return 0.5 * (lo + hi)


def membrane_potential(c_hi: float, c_lo: float, alpha: float, temp_c: float = 25.0) -> tuple[float, float]:
    """선택도 α 막의 확산 전위 [V]: (이상 용액, 활동도) — 농도는 mol/kg ≈ mol/L 로 봄."""
    vt = thermal_voltage(temp_c)
    ideal = alpha * vt * math.log(c_hi / c_lo)
    real = alpha * vt * math.log(gamma(c_hi, temp_c) * c_hi / (gamma(c_lo, temp_c) * c_lo))
    return ideal, real


def report() -> dict:
    """프로젝트에 쓰이는 값: 식염수 어는점, 내강/소금물 막전위 보정, 냉각판 온도의 공존 소금물."""
    from .tissue import WALL_ALPHA, TissueRecipe, tissue_for

    tr = tissue_for(TissueRecipe().battery())
    c_lo, c_hi = float(tr.c_lumen[1]), float(tr.c_brine)
    ideal, real = membrane_potential(c_hi, c_lo, WALL_ALPHA)
    return {
        "saline_freezing_c": freezing_point_c(0.154),
        "brine_freezing_c": freezing_point_c(c_hi),
        "eutectic_m": brine_at(-21.1),
        "brine_at_minus5_m": brine_at(-5.0), "brine_at_minus10_m": brine_at(-10.0),
        "c_lumen_m": c_lo, "c_brine_m": c_hi, "gamma_lumen": gamma(c_lo), "gamma_brine": gamma(c_hi),
        "wall_mv_ideal": 1000 * ideal, "wall_mv_activity": 1000 * real,
    }


def describe() -> str:
    r = report()
    return "\n".join([
        "용액 화학 — PHREEQC · pitzer.dat (spec/phreeqc_nacl.json)",
        f"  생리식염수 0.154 mol/kg 어는점 {r['saline_freezing_c']:.2f} °C (모델 동결 온도 −0.6 °C 와 비교)",
        f"  막 사이 소금물 {r['c_brine_m']:.2f} mol/kg: γ± {r['gamma_brine']:.3f}, 어는점 {r['brine_freezing_c']:.1f} °C",
        f"  내강 {1000 * r['c_lumen_m']:.1f} mmol/kg: γ± {r['gamma_lumen']:.3f}",
        f"  막 하나의 확산 전위: 이상 용액 {r['wall_mv_ideal']:.1f} mV → 활동도 {r['wall_mv_activity']:.1f} mV",
        f"  얼음과 공존하는 소금물: −5 °C {r['brine_at_minus5_m']:.2f} · −10 °C {r['brine_at_minus10_m']:.2f} · 공정점(−21.1 °C) {r['eutectic_m']:.2f} mol/kg (문헌 5.2)",
    ])
