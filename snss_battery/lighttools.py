"""빛 조각가 SC-2 의 조각 도구 — 물속 갠트리 + 주사기 · 조각 도구 (명세: spec/LIGHT.md §11).

빛이 몸(보로노이 세포)을 층층이 빚고, 주사기와 도구가 빛이 못 하는 것을 한다:
- T0 쌓기 주사기: SC-1 펜과 같은 세 원료(GO · SNSS · PVA) 혼합 → 허공 획 · 덧붙이기 · 메우기 (멸균생리식염수 154 mM 속에서
  잉크 자체의 염으로 굳음 — SC-1 레시피 그대로). 빛은 아래가 빈 돌출부를 못 만들지만 주사기는 허공에 그린다.
- T1 주입 주사기: n 세포마다 PEI 를 직접 넣음 → n 도핑이 세포 반지름(≈1.5 mm)만 스미면 됨 (몸 통째 담그면 6 일 → 약 1 시간).
- T2 흡입 주사기: 깎기 (SC-1 흡입과 같음). T3 나일론 줄 칼: 떼기. T4 누름판: 붙이기. T5 흑연 탐침: 세포 전위 · 저항 재기.

두 작업면:
- 빛 면 = 배지 수면 (잉크층). 빛을 쬘 때 갠트리는 뒤쪽에 주차 — 받침 기둥 · 빛길에서 비킴.
- 도구 면 = 도구 끝 높이 (멸균생리식염수 속). 받침이 작업물을 이 높이로 내려 도구가 위에서 일함 (SC-1 환경 그대로).
  그래서 도구 작업은 작업물이 '도구 높이 한도' 아래일 때만 (너트 판이 Z 모터 방수 통에 닿지 않게).

물속 금속 없음: 주사기 바늘은 스테인리스 대신 **당겨 뽑은 유리 미세 피펫**(붕규산) · **PEEK 관**.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .lightsculpt import LightSculptorSpec
from .sculpt import NEG, POS, BodyModel, body_signs


@dataclass(frozen=True)
class Tool:
    key: str
    name: str
    tip: str
    use: str
    elements: frozenset  # 젖는 쪽 원소 (금속 점검)


TOOLS: tuple[Tool, ...] = (
    Tool("T0", "쌓기 주사기 (세 원료 혼합)", "PEEK 노즐 Ø0.41 (22G 상당) + 나선 혼합기",
         "허공 획 · 덧붙이기 · 메우기 — SC-1 레시피 (p · n · 막), 잉크 자체 염으로 굳음", frozenset({"C", "H", "O"})),
    Tool("T1", "주입 주사기", "당겨 뽑은 유리 미세 피펫 (붕규산, 끝 Ø0.1 mm, 길이 30 mm)",
         "n 세포마다 PEI 1 % 주입 (n 도핑) · 잉크 · 수리액", frozenset({"Si", "O", "B", "Na"})),
    Tool("T2", "흡입 주사기 (깎기)", "PEEK 관 Ø1.0 · 역방향 흡입 + 전단", "깎기 · 떼어 낸 조각 회수", frozenset({"C", "H", "O"})),
    Tool("T3", "나일론 줄 칼 (떼기)", "나일론 낚싯줄 0.2 mm 를 PETG 활에 팽팽히", "높이 z 에서 가름 (그다음 T2 로 틈 정리)",
         frozenset({"C", "H", "O", "N"})),
    Tool("T4", "누름판 (붙이기)", "PETG 판 20×20 + 실리콘 패드", "올린 조각을 눌러 30 분 아묾", frozenset({"C", "H", "O", "Si"})),
    Tool("T5", "흑연 탐침 (재기)", "연필심 0.3 mm 2개 · 간격 1 mm (실리콘 피복)", "세포 개방 전위 · 2단자 저항 → 도핑 · 막 확인",
         frozenset({"C", "Si", "O", "H"})),
)


@dataclass
class ToolHead:
    """물속 CoreXY (SC-1 과 같은 탄소섬유 · PETG · 나일론) + 자석 키네마틱 도구 교환 + 도구 걸이."""

    gz: float = 304.0  # 갠트리 높이 — X 빔 위 끝이 잉크 우물 테 아래 (테는 잉크층 밑 2 mm 까지만)
    tool_len: float = 85.0  # 마운트 15 + 몸체 40 + 피펫/노즐 30
    carriage_drop: float = 21.0
    park: tuple[float, float] = (0.0, 105.0)  # 뒤쪽 가운데 (받침 기둥 · 손 통로 밖)
    travel_mm_s: float = 40.0
    z_mm_s: float = 3.0  # 받침 오르내림 (나일론 나사봉)
    change_s: float = 20.0  # 도구 바꾸기 (걸이에 걸고 집기)
    pumps: tuple[str, ...] = ("GO", "SNSS", "PVA", "PEI 1 %", "흡입 회수")
    motor_w: float = 0.35  # 하나 평균 (쓸 때만)
    n_motors: int = 2 + 5 + 1  # XY 2 · 주사기 펌프 5 · 도구 교환 1
    inj_flow_ul_s: float = 0.5
    inj_move_s: float = 6.0  # 옮김 + 찌름 + 뺌

    @property
    def tip_z(self) -> float:
        return self.gz - self.carriage_drop - self.tool_len


@dataclass
class Injection:
    pei_wt: float = 1.0  # 주입액: 멸균생리식염수 + 분지형 PEI
    vol_frac: float = 0.15  # 세포질 부피의 15 % 를 주입 (PEI:GO 0.75 → 97 % 붙음)
    pei_go_saturate: float = 0.5  # PEI : GO 질량비가 이만큼이면 90 % 붙음 (가정, 시험 E 로 잼)
    d_m2_s: float = 5e-11  # PEI 확산 (electrodope 와 같음, 가정)
    leak: float = 0.05  # 막을 넘어 이웃(p) 세포로 새는 몫 — GO 막이 PEI 를 붙잡음 (가정, 시험 F 로 잼)
    n_max: float = 5.0
    band_mm: float = 9.0  # 빛으로 이만큼 쌓을 때마다 도구 작업 (세포 3개 높이)
    lag_bands: int = 1  # 잉크에 닿지 않게 한 띠 아래 세포만 주입


@dataclass
class ToolSpec:
    head: ToolHead = field(default_factory=ToolHead)
    inj: Injection = field(default_factory=Injection)
    tools: tuple[Tool, ...] = TOOLS

    def wet_metals(self) -> list[str]:
        from .materials import NONMETALS

        ok = NONMETALS | {"Na", "Cl", "B", "Si"}
        return [t.name for t in self.tools if not t.elements <= ok]

    def max_work_height_mm(self, light: LightSculptorSpec) -> float:
        """도구 면까지 내렸을 때 너트 판이 Z 모터 방수 통(높이 49 = 통 44 + 뚜껑 5) 위 2 mm 에 머무는 작업물 높이."""
        from .layout import BED_CARRIAGE, PLATE, POD_H, RISER

        return self.head.tip_z - (POD_H + 2 + BED_CARRIAGE + RISER + PLATE)


def _cells(job: dict):
    p, pr = job["piece"], job["prediction"]
    cells = pr["cells"]
    ids = np.array(cells["ids"])
    typ = np.array(cells["type"])
    remap = np.full(int(p.cell.max()) + 1, -1)
    remap[ids] = np.arange(len(ids))
    c = np.where(p.cell >= 0, remap[np.maximum(p.cell, 0)], -1)
    cyto = np.isin(p.material, (POS, NEG)) & (c >= 0)
    vox = p.pitch[0] ** 2 * p.pitch[1]  # mm³ (출력 크기)
    v_cyto = np.bincount(c[cyto], minlength=len(ids)) * vox
    ks = np.nonzero(c >= 0)
    top = np.zeros(len(ids))
    np.maximum.at(top, c[ks], (ks[2] + 1) * p.pitch[1])
    cz = np.array(cells["center_mm"])[:, 2] * p.scale  # 출력 높이
    return typ, v_cyto, top, cz, np.array([w is not None for w in cells["wake_s"]])


def plan_tools(job: dict, ts: ToolSpec | None = None) -> dict:
    """빛 + 도구 시간표: 띠마다 주입할 n 세포 · 시간 · 주입 도핑 결과 (새 생명 신호)."""
    ts = ts or ToolSpec()
    spec, p, pl, pr = job["spec"], job["piece"], job["plan"], job["prediction"]
    h, inj = ts.head, ts.inj
    typ, v_cyto, top, cz, connected = _cells(job)
    H = p.height_mm
    n_bands = math.ceil(H / inj.band_mm)
    band_of = np.minimum((top / inj.band_mm).astype(int), n_bands - 1)
    neg = (typ < 0) & (v_cyto > 0)
    # 주입 시점: 그 세포가 끝난 띠 + lag (마지막 띠들은 다 빚은 뒤, 잉크 밖에서)
    when = np.minimum(band_of + inj.lag_bands, n_bands)
    per_band = [int(((when == b) & neg).sum()) for b in range(n_bands + 1)]
    vol_ul = v_cyto * inj.vol_frac  # mm³ = µL
    t_inj = np.where(neg, h.inj_move_s + vol_ul / h.inj_flow_ul_s, 0.0)
    move_s = 2 * abs(spec.tank.fill_mm - h.tip_z) / h.z_mm_s
    xy = np.array(job["prediction"]["cells"]["center_mm"])[:, :2] * p.scale  # 출력 좌표
    phases = []
    for b in range(n_bands + 1):
        m = (when == b) & neg
        if not m.any():
            continue
        phases.append({"band": b, "after_mm": min((b + 1) * inj.band_mm, H) if b < n_bands else H,
                       "cells": int(m.sum()), "inject_s": float(t_inj[m].sum()),
                       "overhead_s": (move_s if b < n_bands else move_s / 2) + 2 * h.change_s, "final": b >= n_bands,
                       "targets": [(round(float(x), 2), round(float(y), 2), round(float(z), 2), round(float(u), 3))
                                   for (x, y), z, u in zip(xy[m], cz[m], vol_ul[m])]})
    tool_s = sum(x["inject_s"] + x["overhead_s"] for x in phases)
    # 도핑: 주입량이 PEI:GO 포화비를 넘으면 다 붙음 · 세포 반지름만큼 스밈 (구의 첫 모드)
    r_m = (3 * np.maximum(v_cyto, 1e-9) / (4 * math.pi)) ** (1 / 3) / 1000
    ratio = inj.vol_frac * inj.pei_wt * 10 / spec.ink.go_mg_ml
    sat = 1 - math.exp(-ratio * math.log(10) / inj.pei_go_saturate)  # 포화비에서 90 % (lightcal 시험 E 와 같은 식)
    light_band_s = pl["expose_s"] / n_bands  # 다 빚기 전에 주입한 세포는 다음 띠를 빛으로 쌓는 동안 스밈
    tau = r_m ** 2 / (math.pi ** 2 * inj.d_m2_s)
    final_soak = float(3 * np.percentile(tau[neg], 90)) if neg.any() else 0.0
    t_soak = np.where(when < n_bands, light_band_s, final_soak)
    frac = sat * (1 - np.exp(-t_soak / tau))
    pei_n = inj.n_max * frac * (1 - inj.leak)
    p_light, n_light = p.carriers
    net_neg = pei_n[neg] - n_light
    w = np.array(pr["cells"]["cap_f"])
    n_eff = float(np.average(net_neg, weights=w[neg] + 1e-30)) if neg.any() else 0.0
    # p 세포로 새는 몫: 이웃 n 세포 평균 누출을 고르게 (어림)
    pos = typ > 0
    leak_p = inj.n_max * sat * inj.leak * neg.sum() / max(pos.sum(), 1)
    p_eff = p_light - leak_p
    from dataclasses import replace

    doped = replace(p, carriers=(round(max(p_eff, 0.0), 3), round(abs(n_eff), 3)))
    new = body_signs(doped, spec.design_spec(), BodyModel(go_in_cell_mg_ml=spec.ink.go_mg_ml,
                                                          neg_dopant="PEI" if n_eff > 0 else "NBD"))
    duty = tool_s / max(tool_s + pl["expose_s"], 1)
    heat_tool = h.motor_w * h.n_motors
    rise_avg = (sum(spec.heat_w().values()) + heat_tool * duty) / spec.tank.heat_loss_w_k
    rise_peak = (sum(spec.heat_w().values()) + heat_tool) / spec.tank.heat_loss_w_k
    bad = []
    if H > ts.max_work_height_mm(spec):
        bad.append(f"작업물 {H:.0f} mm > 도구 높이 한도 {ts.max_work_height_mm(spec):.0f} mm — 마지막 띠는 도구가 못 닿음")
    if ts.wet_metals():
        bad.append("젖는 도구에 금속: " + ", ".join(ts.wet_metals()))
    if rise_peak > 1.0:
        bad.append(f"도구를 쓰는 동안 배지 +{rise_peak:.2f} K (> 1 K)")
    return {"ts": ts, "phases": phases, "tool_h": tool_s / 3600, "light_h": pl["expose_s"] / 3600,
            "n_inject": int(neg.sum()), "inj_ul": float(vol_ul[neg].sum()), "sat": sat, "tau_h": float(np.median(tau[neg]) / 3600) if neg.any() else 0.0,
            "final_soak_h": final_soak / 3600, "n_eff": n_eff, "p_eff": p_eff, "doped_frac": float((pei_n[neg] > 0.5 * inj.n_max).mean()) if neg.any() else 0.0,
            "piece": doped, "prediction": new, "before_energy_j": pr["energy_j"], "rise_avg_k": rise_avg, "rise_peak_k": rise_peak,
            "max_height_mm": ts.max_work_height_mm(spec), "problems": bad, "unconnected": int((~connected & neg).sum())}


def describe_tools(r: dict) -> str:
    ts, pr = r["ts"], r["prediction"]
    h = ts.head
    lines = ["[조각 도구 — 물속 갠트리 (SC-1 방식 CoreXY), 자석 키네마틱 도구 교환]",
             f"  갠트리 {h.gz:g} mm (잉크 우물 테 아래) · 도구 끝 = 도구 면 {h.tip_z:g} mm (멸균생리식염수 속) · 빛을 쬘 때 주차 {h.park}",
             f"  도구 높이 한도: 작업물 {r['max_height_mm']:.0f} mm 까지 (받침 너트 판이 Z 모터 방수 통 위에 머물게)"]
    for t in ts.tools:
        lines.append(f"    {t.key} {t.name} — {t.tip} · {t.use}")
    lines += [f"  주입 n 도핑: n 세포 {r['n_inject']}개에 PEI {ts.inj.pei_wt:g} % 를 세포질의 {ts.inj.vol_frac * 100:.0f} % 씩 (모두 {r['inj_ul']:.0f} µL) · "
              f"포화 {r['sat'] * 100:.0f} % · 세포 안 스밈 τ 중앙값 {r['tau_h']:.1f} h",
              f"    빛으로 {ts.inj.band_mm:g} mm 쌓을 때마다 받침을 도구 면으로 내려 한 띠 아래 세포에 주입 (잉크층에 PEI 가 닿지 않게) — "
              f"도구 작업 {len(r['phases'])}번 · {r['tool_h']:.1f} h (빛 {r['light_h']:.1f} h 에 더함) · 마지막 스밈 {r['final_soak_h']:.1f} h",
              f"    n 세포 절반 이상 도핑 {r['doped_frac'] * 100:.0f} % · 평균 순 도핑 n {r['n_eff']:+.2f} · p {r['p_eff']:+.2f} ×10¹² cm⁻²",
              f"  에너지 {r['before_energy_j']:.3f} J → {pr['energy_j']:.3f} J (×{pr['energy_j'] / max(r['before_energy_j'], 1e-12):.2f}) · "
              f"페르미 준위 p {pr['ef_pos_mev']:+.0f} / n {pr['ef_neg_mev']:+.0f} meV",
              f"  열: 도구 쓰는 동안 배지 +{r['rise_peak_k']:.2f} K · 평균 +{r['rise_avg_k']:.2f} K",
              "  점검: " + ("통과 (물속 도구 금속 없음)" if not r["problems"] else "; ".join(r["problems"]))]
    return "\n".join(lines)


# ---------- G-code: 주입 · 주사기 조각 (도구 면) ----------
def _tool_header(title: str, top_mm: float, ts: ToolSpec) -> list[str]:
    h = ts.head
    return [f"; SC-2 도구 면 작업 — {title}", "; 빛은 끔 · 갠트리를 펴고 받침을 내려 작업물 꼭대기를 도구 면에 (Z 좌표 = 받침 윗면 기준)",
            "PROJECT_OFF", f"SC2_TOOL_PLANE TOP={top_mm:.2f}  ; 받침 윗면 = 도구 면 {h.tip_z:g} − 꼭대기", "GANTRY_UNPARK"]


def _tool_footer() -> list[str]:
    return ["TOOL_RETURN", "GANTRY_PARK  ; 뒤쪽 가운데 — 받침 기둥 · 빛길 비킴", "SC2_LIGHT_PLANE  ; 받침을 다시 빛 면으로"]


def inject_gcode(phase: dict, top_mm: float, ts: ToolSpec | None = None) -> str:
    """주입 한 번: n 세포마다 유리 피펫을 위에서 세포 가운데까지 찔러 PEI 를 넣음 (Z = 받침 윗면 기준 높이)."""
    ts = ts or ToolSpec()
    h, inj = ts.head, ts.inj
    out = _tool_header(f"n 세포 {phase['cells']}개에 PEI {inj.pei_wt:g} % 주입 (띠 {phase['band']})", top_mm, ts)
    out += ["TOOL_PICK T=T1  ; 주입 주사기 (유리 미세 피펫)", "PRIME T=T1 UL=2"]
    for x, y, z, ul in sorted(phase["targets"], key=lambda t: (round(t[1] / 6), t[0])):  # 줄마다 지그재그 없이 가까운 순
        out += [f"G0 X{x:.2f} Y{y:.2f} Z{top_mm + 3:.2f} F{h.travel_mm_s * 60:.0f}", f"G1 Z{z:.2f} F120",
                f"INJECT UL={ul:.3f} RATE={h.inj_flow_ul_s:g}", f"G1 Z{top_mm + 3:.2f} F120"]
    return "\n".join(out + _tool_footer()) + "\n"


TOOL_FOR = {"carve": ("T2", "흡입 주사기 (깎기)"), "add": ("T0", "쌓기 주사기"), "stroke": ("T0", "쌓기 주사기 (허공 획)")}


def syringe_job(piece, op: str, spec: LightSculptorSpec, cp=None, **kw):
    """SC-1 조각 작업을 빛으로 빚은 몸에 — 같은 격자 (설계 spec 은 이 기계의 칸 · 층)."""
    from . import sculpt as S

    ds = spec.design_spec()
    cp = cp or S.CellParams()
    if op == "add":
        return S.job_add(piece, kw.get("shape", "bud"), kw.get("height", 0.0), cp, ds, at=kw.get("at", (0.0, 0.0)))
    if op == "carve":
        return S.job_carve(piece, kw["center"], kw["radius"], cp, ds)
    if op == "detach":
        return S.job_detach(piece, kw["z"], cp, ds)
    if op == "draw":
        return S.job_strokes(piece, kw["strokes"], cp, ds)
    if op == "attach":
        return S.job_attach(piece, kw["upper"], ds, at=kw.get("at", (0.0, 0.0)))
    raise ValueError(f"모르는 작업: {op}")


def write_syringe_job(job, spec: LightSculptorSpec, folder, ts: ToolSpec | None = None) -> dict:
    """SC-1 의 작업 폴더를 만들고 G-code 를 도구 면 작업으로 바꿈 (홈 잡기 · 배지 채우기 대신 도구 면 · 도구 집기)."""
    from pathlib import Path

    from . import sculpt as S

    ts = ts or ToolSpec()
    top = max(a.height_mm for a in job.after)
    if top > ts.max_work_height_mm(spec):
        raise ValueError(f"작업 뒤 높이 {top:.1f} mm 가 도구 높이 한도 {ts.max_work_height_mm(spec):.0f} mm 를 넘습니다.")
    bm = BodyModel(go_in_cell_mg_ml=spec.ink.go_mg_ml, neg_dopant="NBD")  # 빛으로 빚은 몸 (주입 전): n 세포는 약한 p
    res = S.write_job(job, spec.design_spec(), folder, meshes=False, bm=bm)
    g = Path(res["gcode"])
    lines = g.read_text(encoding="utf-8").splitlines()
    skip = {"G28", "Z_TILT_ADJUST", "G28 Z"}
    out, cur = [], None
    before = job.before.height_mm if job.before is not None else top
    for ln in lines:
        if ln in skip or ln.startswith("FILL ") or ln.startswith("M117 배지 가득") or (ln == "M0" and out and out[-1].startswith("M117 배지")):
            continue
        if ln.startswith("LEAK_CHECK"):
            out += _tool_header(job.title, before, ts)
        if ln.startswith("; ====="):
            kind = ln.split()[2].rstrip(":")
            if kind in TOOL_FOR and TOOL_FOR[kind][0] != cur:
                cur = TOOL_FOR[kind][0]
                out.append(f"TOOL_PICK T={cur}  ; {TOOL_FOR[kind][1]}")
            if kind == "pause" and "붙" in ln:
                out += ["TOOL_PICK T=T4  ; 누름판 — 올린 조각을 눌러 아묾", "PRESS FORCE=0.2"]
                cur = "T4"
        out.append(ln)
    out += _tool_footer()
    g.write_text("\n".join(out) + "\n", encoding="utf-8")
    return res
