"""전기 도핑 (사후) — 빛으로 못 하는 n 도핑을 존재 자신의 배선으로 (명세: spec/LIGHT.md §10).

빛 조각가는 p 세포만 빛(530 nm)으로 도핑한다. n 도펀트 PEI 는 양이온 고분자라 잉크에 넣으면 GO 를 엉기게 한다.
그래서 다 빚은 뒤 받침째 꺼내 **작은 도핑 통**(멸균생리식염수 1 L + PEI)에 담그고, 발 단자로 두 망에 전위를 건다:

- 오른발(− 망, 간극연접으로 이어진 n 세포들) −0.6 V, 왼발(+ 망) +0.2 V (흑연 기준 전극 대비, 탄소의 안전 전압창 안).
- PEI 는 양이온 → 음으로 대전된 − 망 rGO 면에 붙고, + 망에서는 밀려남. 붙는 몫 f(E) = 1 / (1 + e^((E − E½)/w)) (가정).
- 단자에 이어지지 않은 세포(잠든 세포)는 전위가 걸리지 않음 → 개방 전위 0 V 의 몫만.
- PEI 가 몸 속으로 스며드는 것은 확산: 겉에서 깊이 d 인 세포의 몫 erfc(d / 2√(Dt)) — 속 깊은 세포는 덜 도핑된다 (이 방법의 한계).
- 세포마다 PEI 전자 밀도 n = n_max · f(E) · erfc(…) 에서, 빛으로 붙은 NBD 정공을 뺀 값이 순 도핑.
  양자층 셀 계산(qcap)은 세포 평균 도핑 하나로 어림한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from scipy import ndimage
from scipy.special import erfc

from .sculpt import BodyModel, body_signs


@dataclass
class ElectroDope:
    bath: str = "도핑 통: 멸균생리식염수 1 L + 분지형 PEI 0.1 wt% · 흑연 시트 상대 전극 · 연필심 기준 전극 (유리 비커)"
    e_neg_v: float = -0.6  # 오른발 (− 망)
    e_pos_v: float = 0.2  # 왼발 (+ 망)
    e_oc_v: float = 0.0  # 단자에 안 이어진 세포
    e_half_v: float = -0.2  # PEI 가 절반 붙는 전위 (가정)
    width_v: float = 0.08  # 전위 민감도 (가정)
    n_max: float = 5.0  # 다 붙었을 때 전자 밀도 10¹² cm⁻² (SC-1 n 세포와 같음, 가정)
    d_m2_s: float = 5e-11  # PEI (25 kDa) 가 젤 속으로 스미는 확산 계수 (가정)
    hours: float = 24.0

    def frac(self, e_v: float) -> float:
        return 1 / (1 + math.exp((e_v - self.e_half_v) / self.width_v))


def cell_depth_mm(piece) -> np.ndarray:
    """세포마다 겉(몸 밖)에서의 평균 깊이 (mm, 완성 크기). 순서 = body_signs 의 cells.ids."""
    s = 1 / piece.scale
    px, pz = piece.pitch[0] * s, piece.pitch[1] * s
    inside = piece.material != 0
    pad = np.pad(inside, 1)
    d = ndimage.distance_transform_edt(pad, sampling=(px, px, pz))[1:-1, 1:-1, 1:-1]
    d = np.where(inside, d, 0.0)  # 발바닥도 겉으로 셈 (받침 패드 둘레로 스밈 — 낙관적)
    ids = np.unique(piece.cell[piece.cell >= 0])
    remap = np.full(int(piece.cell.max()) + 1, -1)
    remap[ids] = np.arange(len(ids))
    c = np.where(piece.cell >= 0, remap[np.maximum(piece.cell, 0)], -1)
    m = c >= 0
    tot = np.bincount(c[m], weights=d[m], minlength=len(ids))
    cnt = np.bincount(c[m], minlength=len(ids))
    return tot / np.maximum(cnt, 1)


def electro_dope(job: dict, ed: ElectroDope | None = None) -> dict:
    """빛 작업(light_job) 결과에 사후 전기 도핑을 더함 → 세포별 도핑 · 새 생명 신호."""
    ed = ed or ElectroDope()
    spec, p, pr = job["spec"], job["piece"], job["prediction"]
    cells = pr["cells"]
    typ = np.array(cells["type"])
    connected = np.array([w is not None for w in cells["wake_s"]])
    depth = cell_depth_mm(p)
    reach = erfc(depth / 1000 / (2 * math.sqrt(ed.d_m2_s * ed.hours * 3600)))
    e_cell = np.where(~connected, ed.e_oc_v, np.where(typ < 0, ed.e_neg_v, ed.e_pos_v))
    f_e = np.array([ed.frac(e) for e in e_cell])
    pei = ed.n_max * f_e * reach
    p_light, n_light = p.carriers  # 빛 도핑 (NBD 정공): p 세포 · n 세포 평균
    net_neg = pei[typ < 0] - n_light  # + 면 n형
    net_pos = p_light - pei[typ > 0]  # + 면 p형
    w_neg = np.array(cells["cap_f"])[typ < 0] + 1e-30  # 용량 가중 평균 (도핑이 셈하는 면적)
    w_pos = np.array(cells["cap_f"])[typ > 0] + 1e-30
    n_eff = float(np.average(net_neg, weights=w_neg))
    p_eff = float(np.average(net_pos, weights=w_pos))
    doped = replace(p, carriers=(round(max(p_eff, 0.0), 3), round(abs(n_eff), 3)))
    bm = BodyModel(go_in_cell_mg_ml=spec.ink.go_mg_ml, neg_dopant="PEI" if n_eff > 0 else "NBD")
    new = body_signs(doped, spec.design_spec(), bm)
    # − 망 세포 90 % 가 절반 이상 도핑되려면: 90 번째 깊이에서 f(E)·erfc(d/2√Dt) = 0.5
    from scipy.special import erfcinv

    d90 = float(np.percentile(depth[(typ < 0) & connected], 90)) / 1000
    f_neg = ed.frac(ed.e_neg_v)
    t90_h = (d90 / (2 * erfcinv(0.5 / f_neg))) ** 2 / ed.d_m2_s / 3600 if f_neg > 0.5 else float("inf")
    return {"ed": ed, "piece": doped, "prediction": new, "before_energy_j": pr["energy_j"],
            "n_eff": n_eff, "p_eff": p_eff, "neg_doped_half": float((net_neg > ed.n_max * 0.5).mean()),
            "pos_compensated": float((pei[typ > 0] > 0.5).mean()), "depth_mm_max": float(depth.max()),
            "reach_mm": 2 * math.sqrt(ed.d_m2_s * ed.hours * 3600) * 1000, "t90_h": t90_h,
            "unconnected": int((~connected).sum())}


def describe_edope(r: dict) -> str:
    ed, pr = r["ed"], r["prediction"]
    return "\n".join([
        f"[사후 전기 도핑 — n 세포] {ed.bath}",
        f"  오른발(− 망) {ed.e_neg_v:+.1f} V · 왼발(+ 망) {ed.e_pos_v:+.1f} V (흑연 기준) · {ed.hours:g} h — PEI 붙는 몫 "
        f"− 망 {ed.frac(ed.e_neg_v) * 100:.0f} % · + 망 {ed.frac(ed.e_pos_v) * 100:.1f} % · 안 이어진 세포 {ed.frac(ed.e_oc_v) * 100:.0f} %",
        f"  스미는 깊이 2√(Dt) {r['reach_mm']:.1f} mm (몸 속 가장 깊은 세포 {r['depth_mm_max']:.1f} mm) — "
        f"− 망 세포 90 % 가 절반 이상 붙으려면 약 {r['t90_h']:.0f} h",
        f"  n 세포 절반 이상 도핑 {r['neg_doped_half'] * 100:.0f} % · 평균 순 도핑 n {r['n_eff']:+.2f} · p {r['p_eff']:+.2f} ×10¹² cm⁻² "
        f"· p 세포가 PEI 로 깎인 비율 {r['pos_compensated'] * 100:.0f} %",
        f"  에너지 {r['before_energy_j']:.3f} J → {pr['energy_j']:.3f} J (×{pr['energy_j'] / max(r['before_energy_j'], 1e-12):.2f}) · "
        f"페르미 준위 p {pr['ef_pos_mev']:+.0f} / n {pr['ef_neg_mev']:+.0f} meV",
    ])
