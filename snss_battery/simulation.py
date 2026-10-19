"""충방전 사이클 시뮬레이션과 I-V 특성."""

from __future__ import annotations

import copy
import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .artificial_cell import ArtificialCellStack
from .constants import FARADAY


@dataclass
class CyclePoint:
    time_s: float
    cycle: int
    phase: str  # "charge" | "discharge"
    voltage_v: float
    current_a: float
    soc: float
    c_dilute_mm: float
    c_concentrated_mm: float
    electrode_voltage_v: float


@dataclass
class CycleSummary:
    cycle: int
    charge_mah: float
    discharge_mah: float
    charge_wh: float
    discharge_wh: float
    charge_end: str
    discharge_end: str

    @property
    def born(self) -> bool:
        """결정화로 충전된 상태에서의 첫 방전 (충전 단계 없음)."""
        return self.cycle == 0

    @property
    def coulombic_efficiency(self) -> float:
        return self.discharge_mah / self.charge_mah if self.charge_mah else 0.0

    @property
    def energy_efficiency(self) -> float:
        return self.discharge_wh / self.charge_wh if self.charge_wh else 0.0


@dataclass
class CyclingResult:
    points: list[CyclePoint] = field(default_factory=list)
    cycles: list[CycleSummary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.cycles:
            return "사이클 없음"
        lines = [f"{'사이클':>4} {'충전 mAh':>9} {'방전 mAh':>9} {'쿨롱효율':>8} {'에너지효율':>9}  충전 종료 / 방전 종료"]
        for c in self.cycles:
            if c.born:
                lines.append(f"{'탄생':>4} {'-':>9} {c.discharge_mah:9.4f} {'-':>8} {'-':>9}  "
                             f"결정화로 충전됨 / {c.discharge_end}")
                continue
            lines.append(
                f"{c.cycle:>4} {c.charge_mah:9.4f} {c.discharge_mah:9.4f} "
                f"{c.coulombic_efficiency * 100:7.1f}% {c.energy_efficiency * 100:8.1f}%  "
                f"{c.charge_end} / {c.discharge_end}"
            )
        for w in self.warnings:
            lines.append(f"⚠ {w}")
        return "\n".join(lines)

    def to_csv(self, path: str | Path) -> None:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(CyclePoint.__dataclass_fields__))
            w.writeheader()
            for p in self.points:
                w.writerow(asdict(p))


def cycle_cc(
    stack: ArtificialCellStack,
    current_a: float,
    v_max: float,
    v_min: float,
    n_cycles: int = 3,
    dt_s: float = 10.0,
    rest_s: float = 0.0,
    max_phase_s: float = 7 * 24 * 3600,
    record_every: int = 1,
    born_charged: bool = False,
) -> CyclingResult:
    """정전류 충전(→v_max) / 정전류 방전(→v_min) 반복.

    born_charged=True 이면 현재 상태(결정화로 이미 충전됨)에서 먼저 방전(사이클 0)한 뒤 반복.
    """
    if current_a <= 0 or dt_s <= 0:
        raise ValueError("전류와 시간 스텝은 양수여야 합니다.")
    if v_max <= v_min:
        raise ValueError("충전 상한 전압은 방전 하한 전압보다 커야 합니다.")
    res = CyclingResult()
    t = 0.0
    step = 0

    def record(cycle: int, phase: str, v: float, i: float) -> None:
        nonlocal step
        if step % record_every == 0:
            s = stack.status()
            res.points.append(CyclePoint(t, cycle, phase, v, i, s["soc"], s["c_dilute_mm"],
                                         s["c_concentrated_mm"], s["electrode_voltage_v"]))
        step += 1

    def run_phase(cycle: int, phase: str) -> tuple[float, float, str]:
        nonlocal t
        i = -current_a if phase == "charge" else current_a
        ah = wh = 0.0
        t_start = t
        while True:
            v = stack.terminal_voltage(i)
            if phase == "charge" and v >= v_max:
                return ah, wh, "상한 전압"
            if phase == "discharge" and v <= v_min:
                return ah, wh, "하한 전압"
            if t - t_start >= max_phase_s:
                return ah, wh, "시간 초과"
            record(cycle, phase, v, i)
            warns = stack.step(i, dt_s)
            t += dt_s
            ah += current_a * dt_s / 3600
            wh += abs(v) * current_a * dt_s / 3600
            if warns:
                for w in warns:
                    msg = f"{cycle}사이클 {'충전' if phase == 'charge' else '방전'} 중: {w}"
                    if msg not in res.warnings:
                        res.warnings.append(msg)
                return ah, wh, "안전 한계"

    if born_charged:
        q_out, e_out, end_d = run_phase(0, "discharge")
        res.cycles.append(CycleSummary(0, 0.0, q_out * 1000, 0.0, e_out, "결정화", end_d))

    for c in range(1, n_cycles + 1):
        q_in, e_in, end_c = run_phase(c, "charge")
        if rest_s > 0:
            for _ in range(int(rest_s / dt_s)):
                stack.step(0.0, dt_s)
                t += dt_s
        q_out, e_out, end_d = run_phase(c, "discharge")
        res.cycles.append(CycleSummary(c, q_in * 1000, q_out * 1000, e_in, e_out, end_c, end_d))
        if q_in == 0:
            res.warnings.append("충전이 시작되자마자 상한 전압에 도달 — 전류를 낮추거나 상한 전압을 올리세요.")
            break
    return res


def short_circuit_current(stack: ArtificialCellStack) -> float:
    ocv = stack.open_circuit_voltage()
    return max(ocv, 0.0) / stack.internal_resistance()


def polarization_curve(stack: ArtificialCellStack, n_points: int = 40) -> list[tuple[float, float, float]]:
    """현재 충전 상태에서의 순간 I-V-P (상태는 변하지 않음)."""
    isc = short_circuit_current(stack)
    out = []
    for k in range(n_points):
        i = isc * k / (n_points - 1)
        v = stack.terminal_voltage(i)
        out.append((i, v, i * v))
    return out


def max_power_point(stack: ArtificialCellStack) -> tuple[float, float]:
    """순간 최대 전력 (선형 I-V 이므로 I = Isc/2)."""
    i = short_circuit_current(stack) / 2
    return i, i * stack.terminal_voltage(i)


def suggest_limits(stack: ArtificialCellStack, current_a: float) -> tuple[float, float]:
    """(권장 충전 상한, 방전 하한) — 현재 상태에서 출발해 이온(농도) 한계와 접촉면 전기이중층 한계 중
    먼저 닿는 지점(90~95 %)의 단자전압."""
    vol = stack.geometry.volume_l
    eta = stack.current_efficiency

    def shifted(dq: float) -> ArtificialCellStack:
        s = copy.deepcopy(stack)
        s.q += dq
        s.x = min(max(s.x + eta * dq / (FARADAY * vol), -s.max_shift), s.max_shift)
        return s

    q_el = 0.9 * stack.electrode_capacity_c
    q_ion_up = max(0.95 * stack.max_shift - stack.x, 0.0) * FARADAY * vol / eta
    q_ion_dn = max(stack.x, 0.0) * FARADAY * vol / eta
    v_max = shifted(min(q_el - stack.q, q_ion_up)).terminal_voltage(-current_a)
    v_low = shifted(-min(q_el + stack.q, q_ion_dn)).terminal_voltage(current_a)
    v_min = max(v_low, 0.02 * stack.n_pairs)
    if v_min >= v_max:
        v_min = 0.02 * stack.n_pairs
    return round(v_max, 3), round(v_min, 3)
