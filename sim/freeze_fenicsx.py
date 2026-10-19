"""방향성 동결 · 해동 — FEniCSx (dolfinx) 유한요소, 2D 축대칭 열전달 + 상변화 (엔탈피법).

Docker 안에서 실행합니다 (`python3 -m snss_battery fem` 이 대신 실행):
    docker run --rm -v "$PWD":/work -w /work dolfinx/dolfinx:v0.9.0 python3 sim/freeze_fenicsx.py
결과: spec/fenicsx_freezing.json

영역 (r, z) [m]: 겔 | PE 병 벽·바닥 (+ 접촉액) | 병 안 윗공기 | 스티로폼 (옆·위).
아래 z=0 은 냉각판 (고정 온도), 바깥 옆·위는 공기와 대류 (h, T_amb).
겔 = 물 + 3 % PVA 로 봄. 어는점은 PHREEQC 로 계산한 생리식염수 값 (spec/phreeqc_nacl.json).
엔탈피 H(T) = ρc·T + ρL·φ(T),  φ = 액체 비율 (어는점 둘레 ±1 K 에서 매끄럽게) → 에너지 보존형 내연법.
"""

import json
import time
from pathlib import Path

import numpy as np
import ufl
from dolfinx import fem, mesh
from dolfinx.fem.petsc import NonlinearProblem
from dolfinx.nls.petsc import NewtonSolver
from mpi4py import MPI
from petsc4py import PETSc

ROOT = Path(__file__).resolve().parents[1]
CHEM = json.loads((ROOT / "spec" / "phreeqc_nacl.json").read_text())

# 병 · 겔 (snss_battery.bottle.BottleSpec 기본값, 500 mL)
R_GEL, H_GEL = 0.0352, 0.12845
T_PE = 0.0008  # 병 벽 · 바닥 두께
GAP = 0.0215  # 겔 윗면 ~ 어깨 (병 안 공기)
L_FUS = 334e3 * 0.917  # 부피당 녹음열 J/m³ ÷ ρ_물 (tissue.py 와 같은 ρL)
DT_PC = 1.0  # 상변화 폭 K (어는점 ± 이 값 안에서 녹음열이 나옴)


def melt_c():
    """PHREEQC 물 활동도 → 생리식염수 (0.154 mol/kg) 어는점."""
    m, aw = CHEM["molality"], CHEM["aw"]["0.0"]
    a = float(np.interp(np.log(0.154), np.log(m), aw))
    return 1 / (1 / 273.15 - 8.314462618 * np.log(a) / 6010.0) - 273.15


TM = melt_c()


def run(name, t_plate, t_amb, h_out, ins_side, ins_top, t0_gel, *, thaw=False, t_end_h=40.0, cell=0.0008, xdmf=None):
    r_out = R_GEL + T_PE + ins_side
    z_top = T_PE + H_GEL + GAP + ins_top
    nx, ny = max(4, round(r_out / cell)), max(4, round(z_top / cell))
    msh = mesh.create_rectangle(MPI.COMM_WORLD, [np.array([0.0, 0.0]), np.array([r_out, z_top])], [nx, ny], mesh.CellType.quadrilateral)
    x = ufl.SpatialCoordinate(msh)
    r, z = x[0], x[1]
    V = fem.functionspace(msh, ("Lagrange", 1))
    T, Tn, v = fem.Function(V), fem.Function(V), ufl.TestFunction(V)

    # 재료 (위치로 구분)
    gel = ufl.And(ufl.lt(r, R_GEL), ufl.And(ufl.gt(z, T_PE), ufl.lt(z, T_PE + H_GEL)))
    pe = ufl.Or(ufl.And(ufl.lt(r, R_GEL + T_PE), ufl.lt(z, T_PE)),
                ufl.And(ufl.And(ufl.ge(r, R_GEL), ufl.lt(r, R_GEL + T_PE)), ufl.lt(z, T_PE + H_GEL + GAP)))
    air = ufl.And(ufl.lt(r, R_GEL), ufl.And(ufl.ge(z, T_PE + H_GEL), ufl.lt(z, T_PE + H_GEL + GAP)))
    phi = lambda u: 0.5 * (1 + ufl.tanh((u - TM) / (DT_PC / 2)))  # 액체 비율
    k_gel = lambda u: 2.2 + (0.56 - 2.2) * phi(u)
    c_gel = lambda u: 1.0e6 * (2.05 + (4.18 - 2.05) * phi(u))  # ρc J/(m³K)
    sel = lambda a, b, c, d: ufl.conditional(gel, a, ufl.conditional(pe, b, ufl.conditional(air, c, d)))
    k = lambda u: sel(k_gel(u), 0.40, 0.026, 0.033)
    H = lambda u: sel(c_gel(u) * u + 1000 * L_FUS * phi(u), 950 * 1900 * u, 1.2 * 1000 * u, 30 * 1300 * u)

    dt = fem.Constant(msh, PETSc.ScalarType(30.0))
    # 경계: 아래 = 냉각판 (해동이면 수조 대류), 바깥 옆 · 위 = 공기 대류
    fdim = msh.topology.dim - 1
    side = mesh.locate_entities_boundary(msh, fdim, lambda p: np.isclose(p[0], r_out))
    top = mesh.locate_entities_boundary(msh, fdim, lambda p: np.isclose(p[1], z_top))
    bot = mesh.locate_entities_boundary(msh, fdim, lambda p: np.isclose(p[1], 0.0))
    facets = np.concatenate([side, top, bot])
    tags = np.concatenate([np.full(len(side), 1), np.full(len(top), 2), np.full(len(bot), 3)]).astype(np.int32)
    order = np.argsort(facets)
    mt = mesh.meshtags(msh, fdim, facets[order], tags[order])
    # 적분 차수 고정: tanh 같은 비다항식이면 F 와 J 의 차수 추정이 달라져 Newton 이 1차 수렴으로 떨어짐
    q = {"quadrature_degree": 4}
    dx = ufl.Measure("dx", domain=msh, metadata=q)
    ds = ufl.Measure("ds", domain=msh, subdomain_data=mt, metadata=q)
    F = (H(T) - H(Tn)) / dt * v * r * dx + k(T) * ufl.dot(ufl.grad(T), ufl.grad(v)) * r * dx
    if thaw:  # 수조: 옆 · 바닥 h_out, 위(병 안 공기 쪽)는 약한 대류
        F += h_out * (T - t_amb) * v * r * (ds(1) + ds(3)) + 5.0 * (T - t_amb) * v * r * ds(2)
        bcs = []
    else:
        F += h_out * (T - t_amb) * v * r * (ds(1) + ds(2))
        bcs = [fem.dirichletbc(PETSc.ScalarType(t_plate), fem.locate_dofs_topological(V, fdim, bot), V)]

    # 처음 온도: 겔 = t0_gel, 나머지 = 주변
    xs = V.tabulate_dof_coordinates()
    in_gel = (xs[:, 0] < R_GEL) & (xs[:, 1] > T_PE) & (xs[:, 1] < T_PE + H_GEL)
    Tn.x.array[:] = np.where(in_gel, t0_gel, t_amb if not thaw else t0_gel)
    T.x.array[:] = Tn.x.array

    problem = NonlinearProblem(F, T, bcs=bcs)
    solver = NewtonSolver(MPI.COMM_WORLD, problem)
    solver.convergence_criterion, solver.rtol, solver.atol, solver.max_it = "incremental", 1e-6, 1e-6, 40
    ksp = solver.krylov_solver
    ksp.setType("preonly"); ksp.getPC().setType("lu"); ksp.getPC().setFactorSolverType("mumps")

    gel_dofs = np.where(in_gel)[0]
    if xdmf:  # ParaView 용: 온도 · 얼음 비율 (겔만, 0 = 물 1 = 얼음) 을 시간별로 기록. 시간 단위는 h
        from dolfinx import io

        ice = fem.Function(V, name="ice_fraction")
        T.name = "temperature_C"
        ice_expr = fem.Expression(ufl.conditional(gel, 1 - phi(T), -0.0), V.element.interpolation_points())
        out_file = io.XDMFFile(msh.comm, str(xdmf), "w")
        out_file.write_mesh(msh)
        next_write = 0.0
    t_f = np.full(len(xs), np.nan)  # 얼음 전선(동결) / 다 녹음(해동) 시각
    t, t_end, steps, last = 0.0, t_end_h * 3600, 0, time.time()
    hist = []
    h = 5.0  # 시간 간격: 수렴하면 늘리고 (최대 300 s), 안 되면 반으로
    while t < t_end:
        dt.value = h
        try:
            _, ok = solver.solve(T)
        except RuntimeError:
            ok = False
        if not ok:
            T.x.array[:] = Tn.x.array
            h /= 2
            if h < 0.05:
                raise RuntimeError("Newton 미수렴 (시간 간격 0.05 s 미만)")
            continue
        t += h; steps += 1
        h = min(h * 1.3, 300.0)
        a = T.x.array
        hit = np.isnan(t_f) & ((a > TM + DT_PC) if thaw else (a < TM - DT_PC))
        t_f[hit] = t
        Tn.x.array[:] = a
        frac = np.mean(~np.isnan(t_f[gel_dofs]))
        if xdmf and t >= next_write:
            ice.interpolate(ice_expr)
            out_file.write_function(T, t / 3600); out_file.write_function(ice, t / 3600)
            next_write += 900.0  # 15분마다
        if steps % 20 == 0:
            hist.append([t / 3600, float(frac)])
        if frac >= 0.999:
            break
    if xdmf:
        out_file.close()
    tf = t_f[gel_dofs] / 3600
    g = xs[gel_dofs]

    def at(rr, zz):  # 가장 가까운 겔 절점의 시각 [h]
        i = np.argmin((g[:, 0] - rr) ** 2 + (g[:, 1] - zz) ** 2)
        return float(tf[i])

    zc = T_PE + H_GEL / 2
    out = {"name": name, "t_plate": t_plate, "t_amb": t_amb, "h_out": h_out, "ins_side_m": ins_side, "ins_top_m": ins_top,
           "melt_c": TM, "cells": nx * ny, "steps": steps, "wall_s": time.time() - last, "hist": hist,
           "done_fraction": float(np.mean(~np.isnan(tf))),
           "t_all_h": float(np.nanmax(tf)) if np.all(~np.isnan(tf)) else None,
           "t_top_center_h": at(0, T_PE + H_GEL - 0.002), "t_mid_center_h": at(0, zc), "t_mid_wall_h": at(R_GEL - 0.001, zc)}
    # 방향성: 같은 높이에서 벽 쪽이 가운데보다 먼저 얼면 옆에서 언 것 → (가운데 − 벽) / 가운데
    if not thaw:
        out["side_lead_mid"] = (out["t_mid_center_h"] - out["t_mid_wall_h"]) / out["t_mid_center_h"]
        zs = np.linspace(T_PE + 0.005, T_PE + H_GEL - 0.005, 12)
        out["profile"] = [[float((zz - T_PE) * 1000), at(0, zz), at(R_GEL / 2, zz), at(R_GEL - 0.001, zz)] for zz in zs]
    # 웹 그림용 동결 시각 격자 (r 12 × z 32)
    rs, zs = np.linspace(0, R_GEL - 0.001, 12), np.linspace(T_PE + 0.001, T_PE + H_GEL - 0.001, 32)
    out["grid"] = {"r_mm": (rs * 1000).round(2).tolist(), "z_mm": ((zs - T_PE) * 1000).round(2).tolist(),
                   "t_h": [[None if np.isnan(at(rr, zz)) else round(at(rr, zz), 3) for rr in rs] for zz in zs]}
    if not thaw:
        tg = np.array([[np.nan if v is None else v for v in row] for row in out["grid"]["t_h"]])
        out["bottom_up_fraction"] = float(np.mean(tg[1:] >= tg[:-1] - 0.02))
    print(f"{name}: {nx}×{ny} 격자, {steps} 단계, {out['wall_s']:.0f} s · 끝 {out['t_all_h']} h · 위 가운데 {out['t_top_center_h']:.1f} h", flush=True)
    return out


if __name__ == "__main__":
    import sys

    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    cell = float(args[0]) if args else 0.0008
    if "--xdmf" in sys.argv:  # ParaView 애니메이션만 (results/, JSON 은 그대로)
        (ROOT / "results").mkdir(exist_ok=True)
        run("A · 새 레시피", -20.0, 4.0, 8.0, 0.03, 0.03, 20.0, cell=cell, xdmf=ROOT / "results" / "freeze_A_new_recipe.xdmf")
        run("E · 저가 (냉동실 + 단열 8 cm)", -15.0, -20.0, 8.0, 0.08, 0.08, 20.0, cell=cell, xdmf=ROOT / "results" / "freeze_E_low_cost.xdmf")
        sys.exit(0)
    res = {"tool": "FEniCSx dolfinx 0.9 (Docker dolfinx/dolfinx:v0.9.0)", "melt_c": TM, "cases": [
        run("A · 새 레시피: 저온실 +4 °C, 냉각판 −20 °C, 단열 3 cm", -20.0, 4.0, 8.0, 0.03, 0.03, 20.0, cell=cell),
        run("B · 이전 레시피: 냉동실 −20 °C, 금속판, 옆 단열 2 cm (위 없음)", -20.0, -20.0, 8.0, 0.02, 0.0, 20.0, cell=cell),
        run("C · 상온 22 °C, 냉각판 −20 °C, 단열 3 cm", -20.0, 22.0, 8.0, 0.03, 0.03, 20.0, cell=cell),
        run("D · 저가: 냉동실 −20 °C, 금속판, 단열 8 cm 옆·위", -20.0, -20.0, 8.0, 0.08, 0.08, 20.0, cell=cell),
        # 쟁반은 냉각기가 아니라 냉동실 공기로만 식으므로, 얼음이 내놓는 열(약 3 W)에 몇 도 데워짐
        run("E · 저가 (현실): 냉동실 −20 °C, 쟁반이 데워져 −15 °C, 단열 8 cm 옆·위", -15.0, -20.0, 8.0, 0.08, 0.08, 20.0, cell=cell),
        run("해동 · 25 °C 항온수조 (어깨까지 담금)", 0.0, 25.0, 300.0, 0.0, 0.0, -20.0, thaw=True, t_end_h=12.0, cell=cell),
    ]}
    (ROOT / "spec" / "fenicsx_freezing.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
