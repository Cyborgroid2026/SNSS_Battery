"""양자 커패시턴스 — N 도핑 그래핀 전극 + 생리식염수 전기이중층 (명세: spec/BEING.md §2).

그래핀은 디랙 원뿔 때문에 페르미 준위 근처 상태밀도가 0 에 가까워, 전하를 더 넣으려면 전자 에너지 자체가 올라가야 한다.
이 '양자 커패시턴스' C_Q 가 전기이중층 C_EDL 과 직렬로 붙어 전극 전체 용량을 제한한다:  1/C = 1/C_Q + 1/C_EDL.
양자공학 손잡이 = 질소(N) 도핑으로 페르미 준위를 디랙점에서 밀어내 C_Q 를 키우는 것 (금속 없이: C·N 만).

단위: SI (F/m², C/m², V). 전위는 전자 화학퍼텐셜 / e.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .electrolyte import debye_length_nm

E = 1.602176634e-19
KB = 1.380649e-23
HBAR = 1.054571817e-34
EPS0 = 8.8541878128e-12
V_F = 1.0e6  # 그래핀 페르미 속도 m/s
GRAPHENE_ATOMS_M2 = 3.82e19  # 탄소 원자 면밀도
EPS_WATER = 78.4

_PHI = np.linspace(-2.0, 2.0, 8001)  # 채널 전위 격자 V


def cq_ideal(phi, temperature_k: float = 298.15):
    """이상적 단층 그래핀 C_Q(φ) F/m² — Fang 외 (APL 2007):  2e²kT/(π(ħv_F)²) · ln[2(1+cosh(eφ/kT))]."""
    x = np.abs(np.asarray(phi, dtype=float)) * E / (KB * temperature_k)
    return 2 * E * E * KB * temperature_k / (math.pi * (HBAR * V_F) ** 2) * (x + 2 * np.log1p(np.exp(-x)))


def cq_broadened(phi, temperature_k: float = 298.15, broadening_ev: float = 0.06):
    """전하 웅덩이(불순물)로 디랙점이 흐려진 C_Q — 가우스 평균 (폭 = broadening_ev)."""
    phi = np.asarray(phi, dtype=float)
    if broadening_ev <= 0:
        return cq_ideal(phi, temperature_k)
    xs, ws = np.polynomial.hermite_e.hermegauss(32)
    ws = ws / ws.sum()
    return sum(w * cq_ideal(phi + broadening_ev * x, temperature_k) for x, w in zip(xs, ws))


DOPANTS = {"": 0, "N": +1, "B": -1}  # 흑연형 질소 = 전자 주개(n형), 붕소 = 전자 받개(p형) — 둘 다 비금속


@dataclass
class QuantumElectrode:
    """도핑한 환원 그래핀(N-rGO / B-rGO) 전극의 계면 (젖는 면적 기준)."""

    dopant: str = "N"  # "N" n형 · "B" p형 · "" 도핑 없음
    doping_at: float = 1.0  # 격자에 들어간 도펀트 at%
    donor_efficiency: float = 0.3  # 도펀트 하나가 내놓는(받는) 전하 수 (가정, 문헌 0.2~0.5)
    temperature_k: float = 298.15
    broadening_ev: float = 0.06  # 전하 웅덩이 폭 (rGO 결함, 가정)
    c_stern_uf_cm2: float = 21.0  # 헬름홀츠(스턴)층 µF/cm² (흑연 기저면 문헌값)
    molarity: float = 0.154  # 0.9 % 생리식염수
    wetted_faces: int = 2  # 한 장의 양면이 다 젖으면 상태밀도를 두 면이 나눠 씀 → 면적당 C_Q 절반

    def __post_init__(self) -> None:
        if self.dopant not in DOPANTS or self.doping_at < 0 or self.wetted_faces not in (1, 2):
            raise ValueError("도펀트는 N·B·없음, 도핑은 0 이상, 젖는 면은 1 또는 2 입니다.")
        if self.fermi_shift_ev > 0.95:
            raise ValueError("도핑이 너무 큽니다 (페르미 준위 > 0.95 eV).")
        cq = cq_broadened(_PHI, self.temperature_k, self.broadening_ev)
        sig = np.concatenate([[0.0], np.cumsum(0.5 * (cq[1:] + cq[:-1]) * np.diff(_PHI))])
        sig -= np.interp(0.0, _PHI, sig)
        mu0 = self.mu0_ev
        # 화학퍼텐셜 이동 φ = Δμ/e → 늘어난 전자 전하 dσ, 그때의 전극 전위(전자 에너지 기준) φ + dσ/C_EDL
        phi = np.linspace(-1.0, 1.0, 4001)
        dsig = (np.interp(mu0 + phi, _PHI, sig) - np.interp(mu0, _PHI, sig)) / self.wetted_faces
        self._phi, self._dsig = phi, dsig
        self._e = phi + dsig / self.c_edl

    # ---------- 물성 ----------
    @property
    def label(self) -> str:
        return f"{self.dopant}-rGO {self.doping_at:g} at%" if self.dopant and self.doping_at else "rGO (도핑 없음)"

    @property
    def n0_m2(self) -> float:
        return self.doping_at / 100 * GRAPHENE_ATOMS_M2 * self.donor_efficiency if self.dopant else 0.0

    @property
    def fermi_shift_ev(self) -> float:
        """도핑으로 디랙점에서 벗어난 페르미 준위 크기 |E_F0| = ħv_F√(πn₀)."""
        return HBAR * V_F * math.sqrt(math.pi * self.n0_m2) / E

    @property
    def mu0_ev(self) -> float:
        """부호 있는 평형 페르미 준위 (n형 +, p형 −)."""
        return DOPANTS[self.dopant] * self.fermi_shift_ev

    @property
    def c_diffuse(self) -> float:
        return EPS_WATER * EPS0 / (debye_length_nm(self.molarity) * 1e-9)

    @property
    def c_edl(self) -> float:
        """스턴층 + 확산층(구이–채프먼 최솟값) 직렬 F/m² — 전위 무관 상수로 둠 (보수적)."""
        cs = self.c_stern_uf_cm2 * 1e-2
        return 1 / (1 / cs + 1 / self.c_diffuse)

    def cq_at(self, phi):
        """젖는 면적당 양자 커패시턴스 (평형에서 움직인 화학퍼텐셜 φ = Δμ/e)."""
        return cq_broadened(self.mu0_ev + np.asarray(phi), self.temperature_k, self.broadening_ev) / self.wetted_faces

    def charge(self, e_v):
        """전극 전위 E (전기 전위, 영전하 기준) → 전극에 쌓인 전하 C/m² (+ = 전자를 뺌).

        표는 전자 에너지 기준(μ 가 오르면 전자가 늘어남)이라 전기 전위로는 부호를 뒤집는다: μ/e = −E.
        """
        return -np.interp(-np.asarray(e_v, dtype=float), self._e, self._dsig)

    def channel(self, e_v):
        """전극 전위 E 에서 그래핀 화학퍼텐셜이 평형값에서 움직인 몫 Δμ/e (양극이면 −)."""
        return np.interp(-np.asarray(e_v, dtype=float), self._e, self._phi)

    def c_total(self, e_v):
        """미분 용량 dσ/dE = (1/C_Q + 1/C_EDL)⁻¹."""
        cq = self.cq_at(self.channel(e_v))
        return 1 / (1 / cq + 1 / self.c_edl)


@dataclass
class CellCurve:
    u: np.ndarray  # 셀 전압 V
    q: np.ndarray  # 전하 C/m² (전극 하나의 젖는 면적 기준)
    e_pos: np.ndarray  # 양극 전위 (영전하 기준)
    e_neg: np.ndarray


@dataclass
class QuantumCell:
    """양극 + 음극 (젖는 면적이 같다고 봄). 전위는 전하 중성 조건으로 비대칭하게 나뉨."""

    positive: QuantumElectrode = field(default_factory=lambda: QuantumElectrode("B"))
    negative: QuantumElectrode = field(default_factory=lambda: QuantumElectrode("N"))
    u_max: float = 0.8  # 중성 NaCl 수계 탄소 전극의 안전 전압창 (염소 발생 전)

    def __post_init__(self) -> None:
        if not 0 < self.u_max <= 1.2:
            raise ValueError("셀 전압은 0~1.2 V (물 분해 전) 이어야 합니다.")
        self._curve = self.curve()

    @classmethod
    def symmetric(cls, electrode: QuantumElectrode, u_max: float = 0.8) -> "QuantumCell":
        return cls(electrode, electrode, u_max)

    def split(self, u):
        """전하 중성 q₊(E₊) + q₋(E₊ − U) = 0 을 이분법으로 풂 → E₊."""
        u = np.atleast_1d(np.asarray(u, dtype=float))
        lo, hi = np.zeros_like(u), u.copy()
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            f = self.positive.charge(mid) + self.negative.charge(mid - u)
            lo, hi = np.where(f < 0, mid, lo), np.where(f < 0, hi, mid)
        return 0.5 * (lo + hi)

    def curve(self, n: int = 401) -> CellCurve:
        u = np.linspace(0.0, self.u_max, n)
        ep = self.split(u)
        return CellCurve(u, self.positive.charge(ep), ep, ep - u)

    # ---------- 면적당 성능 ----------
    @property
    def c_area(self) -> float:
        """셀 평균 용량 Q/U, F/m² (전극 하나 면적 기준)."""
        c = self._curve
        return float(c.q[-1] / c.u[-1])

    @property
    def energy_area(self) -> float:
        """U_max 까지 저장 에너지 ∫U dQ, J/m²."""
        c = self._curve
        return float(np.sum(0.5 * (c.u[1:] + c.u[:-1]) * np.diff(c.q)))

    @property
    def c_edl_series(self) -> float:
        return 1 / (1 / self.positive.c_edl + 1 / self.negative.c_edl)

    @property
    def quantum_fraction(self) -> float:
        """양자 커패시턴스가 없을 때(이상적 금속 전극) 대비 남는 용량 비율."""
        return self.c_area / self.c_edl_series

    def electrode_caps(self) -> tuple[float, float]:
        """만충 시 양극·음극 각각의 평균 용량 F/m² (분산 회로망에 씀)."""
        c = self._curve
        return float(c.q[-1] / c.e_pos[-1]), float(c.q[-1] / -c.e_neg[-1])

    def describe(self) -> str:
        p, n = self.positive, self.negative
        cp, cn = self.electrode_caps()
        c = self._curve
        return "\n".join([
            f"[양자층 — 양극 {p.label} · 음극 {n.label} · 생리식염수 {p.molarity * 1000:.0f} mM]",
            f"  페르미 준위: 양극 {p.mu0_ev * 1000:+.0f} meV · 음극 {n.mu0_ev * 1000:+.0f} meV (디랙점 기준)",
            f"  전기이중층 C_EDL = {p.c_edl * 100:.1f} µF/cm² (스턴 {p.c_stern_uf_cm2:g} + 확산 {p.c_diffuse * 100:.0f})",
            f"  셀 {self.u_max:g} V: 평균 {self.c_area * 100:.2f} µF/cm² · 에너지 {self.energy_area * 100:.2f} µJ/cm²"
            f" · 양자 한계 후 남는 용량 {self.quantum_fraction * 100:.0f} %",
            f"  양극/음극 용량 {cp * 100:.2f} / {cn * 100:.2f} µF/cm²  (전위 {c.e_pos[-1]:+.3f} / {c.e_neg[-1]:+.3f} V)",
        ])


def doping_sweep(levels=(0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 4.0), **kw) -> list[dict]:
    """같은 도핑량에서 대칭(N/N) 과 비대칭(B/N) 셀 비교."""
    out = []
    for x in levels:
        sym = QuantumCell.symmetric(QuantumElectrode("N", x, **kw))
        asym = QuantumCell(QuantumElectrode("B", x, **kw), QuantumElectrode("N", x, **kw))
        out.append({"doping_at": x, "ef_mev": sym.negative.fermi_shift_ev * 1000,
                    "sym_c": sym.c_area * 100, "sym_e": sym.energy_area * 100, "sym_qf": sym.quantum_fraction,
                    "asym_c": asym.c_area * 100, "asym_e": asym.energy_area * 100, "asym_qf": asym.quantum_fraction})
    return out
