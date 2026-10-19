"""PyBaMM 으로 푼 인공세포 스택 (농도차 전지).

artificial_cell.ArtificialCellStack 과 같은 전지를 PyBaMM(오픈소스 배터리 모델링 프레임워크)의 PDE·이산화·솔버로 풉니다.
기존 모델은 세포 안 농도가 고르다고 보지만, 여기서는 두 가지를 더 넣습니다.

- 확산: 묽은 세포 A 와 진한 세포 B 의 두께 방향 농도 분포 (막 양쪽 대칭 → 반 두께 영역, x=0 이 막).
  막 표면 농도가 안쪽과 달라지는 농도 분극이 전압에 들어갑니다.
- 활동도: 막전위를 농도 대신 PHREEQC(pitzer.dat) 활동도로 계산합니다 (chem.py 표).

막 한 장(면)을 지나는 염 흐름 [mol/m²/s] (A → B):
    J = −η·I / (2·F·A_m) − P·(c_B,s − c_A,s),    P = (P_CEM + P_AEM) / 2   (I > 0 방전)
A:  ∂c/∂t = D ∂²c/∂x²,  D ∂c/∂x|₀ = J,  ∂c/∂x|_{L/2} = 0      B: 부호 반대
V = N·α·V_T·ln(a_B,s / a_A,s) + 2q/C_dl − I·R,    dq/dt = −I
R = N·(R_막 + ∫ dx/(σ(c_A)·A_m) + ∫ dx/(σ(c_B)·A_m)) + 2·R_집전체

`python -m snss_battery pybamm` (pybamm 필요 → `.venv`) → spec/pybamm_validation.json
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .artificial_cell import ArtificialCellStack
from .constants import FARADAY, thermal_voltage
from .electrolyte import _CONDUCTIVITY_TABLE_25C, _TEMP_COEFF

D_SALT = 1.5e-9  # 물속 NaCl 확산계수 m²/s (겔 안은 조금 작음)
OUT = Path(__file__).resolve().parents[1] / "spec" / "pybamm_validation.json"


@dataclass
class Physics:
    diffusion_m2_s: float = D_SALT
    activity: bool = True
    points: int = 16  # 반 두께 영역 격자 수

    @classmethod
    def lumped(cls) -> "Physics":
        """기존 모델과 같은 가정 (농도 고름 · 이상 용액) — 검증용."""
        return cls(diffusion_m2_s=1e-5, activity=False, points=6)


def build(stack: ArtificialCellStack, ph: Physics, v_min: float, v_max: float):
    import pybamm

    from . import chem

    g, s = stack.geometry, stack
    A, half, n = g.area_m2, g.thickness_m / 2, s.n_pairs
    eta, alpha = s.current_efficiency, s.cem.selectivity_at(s.c0) + s.aem.selectivity_at(s.c0)
    perm = 0.5 * (s.cem.salt_permeability_m_s + s.aem.salt_permeability_m_s)
    vt, c_dl = thermal_voltage(s.saline.temperature_c), s.electrode_capacitance_f
    r_fixed = n * (s.cem.area_resistance_ohm_cm2 + s.aem.area_resistance_ohm_cm2) / g.membrane_area_cm2 + 2 * s.collector.resistance_ohm
    tc = s.saline.temperature_c

    m = pybamm.BaseModel(name="SNSS 인공세포 스택 (농도차 전지)")
    xa = pybamm.SpatialVariable("x_A", domain="dilute", coord_sys="cartesian")
    xb = pybamm.SpatialVariable("x_B", domain="conc", coord_sys="cartesian")
    ca = pybamm.Variable("c_A [mol.m-3]", domain="dilute")
    cb = pybamm.Variable("c_B [mol.m-3]", domain="conc")
    q = pybamm.Variable("q [C]")
    I = pybamm.InputParameter("I [A]")  # + 방전, − 충전
    dis = pybamm.InputParameter("discharge")  # 1 방전 · 0 충전 (멈춤 조건)
    cas, cbs = pybamm.boundary_value(ca, "left"), pybamm.boundary_value(cb, "left")
    J = -eta * I / (2 * FARADAY * A) - perm * (cbs - cas)  # 충전(I<0)이면 A→B, 방전이면 B→A
    D = ph.diffusion_m2_s
    m.rhs = {ca: pybamm.div(D * pybamm.grad(ca)), cb: pybamm.div(D * pybamm.grad(cb)), q: -I}
    m.boundary_conditions = {ca: {"left": (J / D, "Neumann"), "right": (pybamm.Scalar(0), "Neumann")},
                             cb: {"left": (-J / D, "Neumann"), "right": (pybamm.Scalar(0), "Neumann")}}
    c_a0, c_b0 = 1000 * s.c_dilute, 1000 * s.c_concentrated
    m.initial_conditions = {ca: pybamm.Scalar(c_a0), cb: pybamm.Scalar(c_b0), q: pybamm.Scalar(s.q)}

    if ph.activity:
        t = chem.table()
        mol = np.array(t["molality"])
        ln_g = np.log([chem.gamma(x, tc) for x in mol])
        lg = lambda c: pybamm.Interpolant(np.log(mol), ln_g, pybamm.log(c / 1000), interpolator="linear", extrapolate=True)
        emf = n * alpha * vt * (pybamm.log(cbs / cas) + lg(cbs) - lg(cas))
    else:
        emf = n * alpha * vt * pybamm.log(cbs / cas)
    kx = np.array([k for k, _ in _CONDUCTIVITY_TABLE_25C]) * 1000  # mol/m³
    ky = np.array([v for _, v in _CONDUCTIVITY_TABLE_25C]) * 0.1 * (1 + _TEMP_COEFF * (tc - 25))  # S/m
    sigma = lambda c: pybamm.Interpolant(kx, ky, c, interpolator="linear", extrapolate=True)
    # 세포 하나 = 반 두께 영역 2개 (직렬)
    r_cells = n * 2 * (pybamm.Integral(1 / sigma(ca), xa) + pybamm.Integral(1 / sigma(cb), xb)) / A
    ocv = emf + 2 * q / c_dl
    V = ocv - I * (r_fixed + r_cells)
    m.variables = {"c_A [mol.m-3]": ca, "c_B [mol.m-3]": cb, "c_A,s [mol.m-3]": cas, "c_B,s [mol.m-3]": cbs,
                   # 영역 평균 (x_average 는 사용자 정의 영역에서 스칼라가 아니라 분포로 남음)
                   "c_A mean [mol.m-3]": pybamm.Integral(ca, xa) / half, "c_B mean [mol.m-3]": pybamm.Integral(cb, xb) / half,
                   "q [C]": q, "OCV [V]": ocv, "Voltage [V]": V, "R [Ohm]": r_fixed + r_cells,
                   "Electrode voltage [V]": q / c_dl}
    m.events = [pybamm.Event("전압 한계", dis * (V - v_min) + (1 - dis) * (v_max - V)),
                pybamm.Event("묽은 세포 염 바닥", cas - 1000 * s.min_molarity),
                # 방전은 q 가 줄고 충전은 q 가 늘어남 — 진행 방향의 한계만 봄
                pybamm.Event("전극 전압 한계", s.electrode.safe_voltage_v + (2 * dis - 1) * q / c_dl)]
    geometry = {"dilute": {xa: {"min": pybamm.Scalar(0), "max": pybamm.Scalar(half)}},
                "conc": {xb: {"min": pybamm.Scalar(0), "max": pybamm.Scalar(half)}}}
    mesh = pybamm.Mesh(pybamm.Geometry(geometry), {"dilute": pybamm.Uniform1DSubMesh, "conc": pybamm.Uniform1DSubMesh},
                       {xa: ph.points, xb: ph.points})
    disc = pybamm.Discretisation(mesh, {"dilute": pybamm.FiniteVolume(), "conc": pybamm.FiniteVolume()})
    disc.process_model(m)
    return m


def cycle(stack: ArtificialCellStack, current_a: float, v_max: float, v_min: float, n_cycles: int = 3,
          ph: Physics | None = None, born_charged: bool = True, max_phase_s: float = 7 * 86400) -> dict:
    """정전류 방전(태어난 상태) → [충전 → 방전] × n. cycle_cc 와 같은 순서·멈춤 조건."""
    import pybamm

    ph = ph or Physics()
    model = build(stack, ph, v_min, v_max)
    solver = pybamm.IDAKLUSolver(rtol=1e-8, atol=1e-10)
    phases = ([(0, "discharge")] if born_charged else []) + [(c, p) for c in range(1, n_cycles + 1) for p in ("charge", "discharge")]
    out, sol, t0 = [], None, 0.0
    for c, p in phases:
        i = current_a if p == "discharge" else -current_a
        if sol is not None:
            model.set_initial_conditions_from(sol)  # 앞 단계 끝 상태에서 이어서
        t = np.linspace(0, max_phase_s, 4000)
        sol = solver.solve(model, t, inputs={"I [A]": i, "discharge": 1.0 if p == "discharge" else 0.0})
        ts, V = sol.t, np.ravel(sol["Voltage [V]"].entries)
        dt = np.diff(ts)
        ah = current_a * (ts[-1] - ts[0]) / 3600
        wh = float(np.sum(0.5 * (np.abs(V[1:]) + np.abs(V[:-1])) * dt)) * current_a / 3600
        out.append({"cycle": c, "phase": p, "mah": 1000 * ah, "wh": wh, "end": sol.termination, "t0_h": t0 / 3600,
                    "t_h": (ts - ts[0] + t0).tolist()[::max(1, len(ts) // 200)], "v": V.tolist()[::max(1, len(ts) // 200)],
                    "c_a_s": float(np.ravel(sol["c_A,s [mol.m-3]"].entries)[-1]),
                    "c_a_mean": float(np.ravel(sol["c_A mean [mol.m-3]"].entries)[-1])})
        t0 += ts[-1] - ts[0]
    return {"phases": out}


def _summ(res: dict) -> list[dict]:
    rows = []
    by = {(x["cycle"], x["phase"]): x for x in res["phases"]}
    for c in sorted({x["cycle"] for x in res["phases"]}):
        ch, di = by.get((c, "charge")), by[(c, "discharge")]
        rows.append({"cycle": c, "charge_mah": ch["mah"] if ch else 0.0, "discharge_mah": di["mah"],
                     "charge_wh": ch["wh"] if ch else 0.0, "discharge_wh": di["wh"]})
    return rows


def validate(current_ma: float = 0.1, n_cycles: int = 2) -> dict:
    """같은 전지를 기존 모델(cycle_cc) · PyBaMM(같은 가정) · PyBaMM(확산+활동도)로 풀어 비교."""
    from .bottle import BottleGelBattery
    from .simulation import cycle_cc, suggest_limits

    i = current_ma / 1000
    ref_bat = BottleGelBattery()
    v_max, v_min = suggest_limits(ref_bat.stack, i)
    ref = cycle_cc(ref_bat.stack, i, v_max, v_min, n_cycles, dt_s=2.0, born_charged=True)
    ref_rows = [{"cycle": c.cycle, "charge_mah": c.charge_mah, "discharge_mah": c.discharge_mah,
                 "charge_wh": c.charge_wh, "discharge_wh": c.discharge_wh} for c in ref.cycles]
    lump = cycle(BottleGelBattery().stack, i, v_max, v_min, n_cycles, Physics.lumped())
    full = cycle(BottleGelBattery().stack, i, v_max, v_min, n_cycles, Physics())
    st = BottleGelBattery().stack
    # 농도 분극: 높은 전류에서 막 표면 농도가 안쪽보다 얼마나 낮아지나 (확산 시간 L²/4D)
    hi = []
    for ma in (1.0, 10.0, 40.0):
        r = cycle(BottleGelBattery().stack, ma / 1000, v_max, 0.0, 0, Physics(), max_phase_s=600)
        d = r["phases"][0]
        hi.append({"ma": ma, "c_a_surface": d["c_a_s"], "c_a_mean": d["c_a_mean"], "v_end": d["v"][-1], "end": d["end"]})
    return {"current_ma": current_ma, "v_max": v_max, "v_min": v_min, "n_pairs": st.n_pairs,
            "diffusion_time_s": (st.geometry.thickness_m / 2) ** 2 / D_SALT,
            "reference": ref_rows, "pybamm_lumped": _summ(lump), "pybamm_full": _summ(full),
            "ocv0": {"reference": st.open_circuit_voltage(), "full": full["phases"][0]["v"][0]},
            "curves": {"lumped": lump["phases"], "full": [dict(x, t_h=x["t_h"], v=x["v"]) for x in full["phases"]]},
            "polarization": hi}


def describe(r: dict) -> str:
    lines = [f"PyBaMM 인공세포 스택 — {r['n_pairs']}쌍, {r['current_ma']:g} mA, {r['v_min']:.2f}–{r['v_max']:.2f} V",
             f"  세포 반 두께 확산 시간 {r['diffusion_time_s']:.0f} s",
             "  사이클   방전 mAh: 기존 모델 / PyBaMM 같은 가정 / PyBaMM 확산+활동도   방전 mWh"]
    for a, b, c in zip(r["reference"], r["pybamm_lumped"], r["pybamm_full"]):
        lines.append(f"  {a['cycle']:>4}   {a['discharge_mah']:.4f} / {b['discharge_mah']:.4f} / {c['discharge_mah']:.4f}"
                     f"   {1000 * a['discharge_wh']:.3f} / {1000 * b['discharge_wh']:.3f} / {1000 * c['discharge_wh']:.3f}")
    lines.append("  농도 분극 (10분 방전 뒤 묽은 세포 막 표면 / 평균):")
    for p in r["polarization"]:
        lines.append(f"    {p['ma']:>5g} mA: {p['c_a_surface']:.1f} / {p['c_a_mean']:.1f} mol/m³, 전압 {p['v_end']:.2f} V ({p['end']})")
    return "\n".join(lines)


def write(path: Path = OUT) -> dict:
    r = validate()
    slim = {k: v for k, v in r.items() if k != "curves"}
    slim["curves"] = {k: [{"cycle": x["cycle"], "phase": x["phase"], "t_h": x["t_h"], "v": x["v"]} for x in v] for k, v in r["curves"].items()}
    path.write_text(json.dumps(slim, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return r


def view(current_ma: float = 0.1, n_cycles: int = 1) -> None:
    """PyBaMM 공식 그래프 창 (dynamic_plot): 시간 슬라이더로 전압 · 세포 안 농도 분포를 봄. 확산 + 활동도 모델."""
    import pybamm

    from .bottle import BottleGelBattery
    from .simulation import suggest_limits

    st = BottleGelBattery().stack
    i = current_ma / 1000
    v_max, v_min = suggest_limits(st, i)
    model = build(st, Physics(), v_min, v_max)
    solver = pybamm.IDAKLUSolver(rtol=1e-8, atol=1e-10)
    phases = [(0, "discharge")] + [(c, p) for c in range(1, n_cycles + 1) for p in ("charge", "discharge")]
    sols, sol = [], None
    for _, p in phases:
        if sol is not None:
            model.set_initial_conditions_from(sol)
        t0 = sol.t[-1] if sol is not None else 0.0  # 앞 단계 끝 시각에서 이어서 (시간축 하나로 붙이려고)
        sol = solver.solve(model, np.linspace(t0, t0 + 7 * 86400, 2000),
                           inputs={"I [A]": i if p == "discharge" else -i, "discharge": 1.0 if p == "discharge" else 0.0})
        sols.append(sol)
    total = sols[0]
    for s in sols[1:]:
        total = total + s  # 단계를 이어 붙임
    pybamm.dynamic_plot(total, [["Voltage [V]", "OCV [V]"], "Electrode voltage [V]",
                                "c_A [mol.m-3]", "c_B [mol.m-3]", ["c_A,s [mol.m-3]", "c_A mean [mol.m-3]"]],
                        time_unit="hours")
