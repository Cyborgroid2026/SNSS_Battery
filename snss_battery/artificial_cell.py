"""인공세포 스택 — 이온 농도차로 에너지를 저장하는 2차 전지 모델.

구조 (전기뱀장어 발전세포 / 하이드로겔 적층 전원과 같은 원리):

    [전극]─ A │CEM│ B │AEM│ A │CEM│ B │AEM│ ... ─[전극]
            └───── 1쌍 ─────┘

- A, B: 막으로 둘러싸인 인공세포 (내부는 생리식염수)
- CEM : 양이온 선택막 (Na⁺ 통과)  /  AEM : 음이온 선택막 (Cl⁻ 통과)
- 조립 직후: 모든 세포가 0.9% 식염수로 같은 농도 → 전압 0 (방전 상태)
- 충전  : 외부 전류로 A의 NaCl을 B로 이동 → A는 묽어지고 B는 진해짐
- 방전  : 농도차가 막전위(세포의 막전위와 같은 원리)를 만들고, 이온이 되돌아가며 전류 공급

전압:  V = N·(α_c+α_a)·(RT/F)·ln(c_B/c_A) + q/C_eff − I·R
       (마지막 항 전 q/C_eff 는 양 끝 그래핀 전극의 전기이중층 전압)
전하 이동: 전류 I 가 흐르면 η·I/F [mol/s] 의 NaCl 이 이동 (η = 평균 이온 선택도)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import FARADAY, thermal_voltage
from .electrolyte import SalineSolution, nacl_conductivity, sterile_normal_saline
from .materials import (
    AuditLine, CurrentCollector, EndElectrode, Membrane, Selectivity, audit,
    get_collector, get_end_electrode, get_membrane,
)


@dataclass
class CellGeometry:
    membrane_area_cm2: float = 2.0  # 인공세포 사이 막 면적
    compartment_thickness_mm: float = 0.5  # 세포 두께 (막 사이 이온 이동 거리)

    def __post_init__(self) -> None:
        if self.membrane_area_cm2 <= 0 or self.compartment_thickness_mm <= 0:
            raise ValueError("막 면적과 세포 두께는 양수여야 합니다.")

    @property
    def area_m2(self) -> float:
        return self.membrane_area_cm2 * 1e-4

    @property
    def thickness_m(self) -> float:
        return self.compartment_thickness_mm * 1e-3

    @property
    def volume_ul(self) -> float:
        return self.membrane_area_cm2 * self.compartment_thickness_mm * 100.0

    @property
    def volume_l(self) -> float:
        return self.volume_ul * 1e-6


class ArtificialCellStack:
    def __init__(
        self,
        n_pairs: int = 10,
        saline: SalineSolution | None = None,
        geometry: CellGeometry | None = None,
        cation_membrane: Membrane | str = "go_lc",
        anion_membrane: Membrane | str = "go_pdda",
        electrode: EndElectrode | str = "rgo",
        electrode_mass_mg: float = 50.0,
        collector: CurrentCollector | str = "graphite_paper",
        min_molarity: float = 0.002,
    ) -> None:
        if n_pairs < 1:
            raise ValueError("인공세포 쌍 수는 1 이상이어야 합니다.")
        if electrode_mass_mg <= 0:
            raise ValueError("전극 질량은 양수여야 합니다.")
        self.n_pairs = n_pairs
        self.saline = saline or sterile_normal_saline()
        self.geometry = geometry or CellGeometry()
        self.cem = get_membrane(cation_membrane) if isinstance(cation_membrane, str) else cation_membrane
        self.aem = get_membrane(anion_membrane) if isinstance(anion_membrane, str) else anion_membrane
        if self.cem.selectivity != Selectivity.CATION:
            raise ValueError(f"{self.cem.name}은(는) 양이온 선택막이 아닙니다.")
        if self.aem.selectivity != Selectivity.ANION:
            raise ValueError(f"{self.aem.name}은(는) 음이온 선택막이 아닙니다.")
        self.electrode = get_end_electrode(electrode) if isinstance(electrode, str) else electrode
        self.electrode_mass_mg = electrode_mass_mg
        self.collector = get_collector(collector) if isinstance(collector, str) else collector
        self.c0 = self.saline.molarity
        if not 0 < min_molarity < self.c0:
            raise ValueError("최소 농도는 0보다 크고 초기 식염수 농도보다 작아야 합니다.")
        self.min_molarity = min_molarity
        # 대사(metabolism.py)가 바꾸는 항목
        self.faradaic_contacts = False  # True: 접촉면에서 연료 산화/공기 환원 반응 → 이중층 포화 없음
        self.contact_asr_ohm_cm2 = 0.0  # 반응 접촉면 하나의 면저항
        self.extra_emf_v = 0.0  # 증발로 생기는 전체 농도 기울기 기전력
        self.reset()

    # ---------- 상태 ----------
    def reset(self) -> None:
        self.x = 0.0  # A→B 로 옮겨진 NaCl [mol/L]
        self.q = 0.0  # 전극에 저장된 전하 [C]

    @property
    def c_dilute(self) -> float:
        return self.c0 - self.x

    @property
    def c_concentrated(self) -> float:
        return self.c0 + self.x

    @property
    def max_shift(self) -> float:
        return self.c0 - self.min_molarity

    @property
    def state_of_charge(self) -> float:
        return self.x / self.max_shift

    @property
    def current_efficiency(self) -> float:
        """평균 이온 선택도 η. 평균 농도는 항상 c0 로 일정."""
        return 0.5 * (self.cem.selectivity_at(self.c0) + self.aem.selectivity_at(self.c0))

    # ---------- 용량 ----------
    @property
    def electrode_capacitance_f(self) -> float:
        return self.electrode_mass_mg * 1e-3 * self.electrode.specific_capacitance_f_g

    @property
    def ionic_capacity_c(self) -> float:
        return self.max_shift * self.geometry.volume_l * FARADAY / self.current_efficiency

    @property
    def electrode_capacity_c(self) -> float:
        return self.electrode_capacitance_f * self.electrode.safe_voltage_v

    @property
    def capacity_c(self) -> float:
        return min(self.ionic_capacity_c, self.electrode_capacity_c)

    @property
    def capacity_mah(self) -> float:
        return self.capacity_c / 3.6

    @property
    def limiting_factor(self) -> str:
        if self.ionic_capacity_c <= self.electrode_capacity_c:
            return "인공세포 염 농도 (세포 부피를 키우면 증가)"
        return "양 끝 접촉면 그래핀의 전기이중층 용량 (접촉면 그래핀을 늘리면 증가)"

    # ---------- 전기적 특성 ----------
    def membrane_potential_pair(self) -> float:
        """한 쌍(CEM+AEM)의 막전위 [V]."""
        vt = thermal_voltage(self.saline.temperature_c)
        alpha = self.cem.selectivity_at(self.c0) + self.aem.selectivity_at(self.c0)
        return alpha * vt * math.log(self.c_concentrated / self.c_dilute)

    def electrode_voltage(self) -> float:
        """끝단 접촉면 하나에 걸린 이중층 전압 [V] (반응 접촉면이면 0)."""
        if self.faradaic_contacts:
            return 0.0
        return self.q / self.electrode_capacitance_f

    def open_circuit_voltage(self) -> float:
        return self.n_pairs * self.membrane_potential_pair() + 2.0 * self.electrode_voltage() + self.extra_emf_v

    def pair_resistance(self) -> float:
        g, t = self.geometry, self.saline.temperature_c
        r_mem = (self.cem.area_resistance_ohm_cm2 + self.aem.area_resistance_ohm_cm2) / g.membrane_area_cm2
        r_a = g.thickness_m / (nacl_conductivity(self.c_dilute, t) * g.area_m2)
        r_b = g.thickness_m / (nacl_conductivity(self.c_concentrated, t) * g.area_m2)
        return r_mem + r_a + r_b

    def internal_resistance(self) -> float:
        r = self.n_pairs * self.pair_resistance() + 2.0 * self.collector.resistance_ohm
        if self.faradaic_contacts:
            r += 2.0 * self.contact_asr_ohm_cm2 / self.geometry.membrane_area_cm2
        return r

    def terminal_voltage(self, current_a: float) -> float:
        """current_a > 0: 방전, < 0: 충전."""
        return self.open_circuit_voltage() - current_a * self.internal_resistance()

    # ---------- 시간 전개 ----------
    def step(self, current_a: float, dt_s: float, pump_a: float = 0.0) -> list[str]:
        """dt 동안 전류를 흘리고 경고 목록을 반환.

        pump_a: 각 쌍 안에서 묽은→진한 쪽으로 염을 퍼 올리는 내부 재생(대사) 전류 [A]. 이온 1쌍/전하.
        """
        g = self.geometry
        dx = -self.current_efficiency * current_a * dt_s / (FARADAY * g.volume_l)
        dx += pump_a * dt_s / (FARADAY * g.volume_l)
        # 농도차에 의한 염 역확산 (막 2장) — 자가방전
        perm = self.cem.salt_permeability_m_s + self.aem.salt_permeability_m_s
        flux = perm * g.area_m2 * (self.c_concentrated - self.c_dilute) * 1000.0  # mol/s
        dx -= flux * dt_s / g.volume_l
        self.x = min(max(self.x + dx, -self.max_shift), self.max_shift)
        if not self.faradaic_contacts:
            self.q -= current_a * dt_s

        warnings = []
        if not self.faradaic_contacts and abs(self.electrode_voltage()) > self.electrode.safe_voltage_v:
            warnings.append("접촉면(전극) 전압이 안전 한계 초과 → 물 분해(가스) 위험")
        if abs(self.x) >= self.max_shift:
            warnings.append("묽은 세포의 염이 바닥남 (농도 한계)")
        return warnings

    def status(self) -> dict[str, float]:
        return {
            "c_dilute_mm": self.c_dilute * 1000,
            "c_concentrated_mm": self.c_concentrated * 1000,
            "membrane_potential_mv": self.membrane_potential_pair() * 1000,
            "electrode_voltage_v": self.electrode_voltage(),
            "soc": self.state_of_charge,
        }

    # ---------- 보고 ----------
    def audit(self) -> list[AuditLine]:
        return audit([
            ("양이온 선택막", self.cem.elements, False),
            ("음이온 선택막", self.aem.elements, False),
            ("끝단 전극", self.electrode.elements, False),
            ("집전체", self.collector.elements, False),
            ("식염수", frozenset({"Na", "Cl", "H", "O"}), True),
        ])

    def describe(self) -> str:
        g = self.geometry
        n_cells = 2 * self.n_pairs
        return "\n".join([
            f"인공세포 스택: {self.n_pairs}쌍 ({n_cells}개 세포), 세포당 {g.volume_ul:.0f} µL "
            f"(막 {g.membrane_area_cm2:g} cm² × 두께 {g.compartment_thickness_mm:g} mm), "
            f"식염수 총 {n_cells * g.volume_ul / 1000:.2f} mL",
            f"  막: {self.cem.name} / {self.aem.name}, 이온 선택도 η={self.current_efficiency:.2f}",
            f"  전극: {self.electrode.name} {self.electrode_mass_mg:g} mg × 2 "
            f"({self.electrode_capacitance_f:.2f} F), 집전체: {self.collector.name}",
            f"  용량 {self.capacity_mah:.3f} mAh — 제한 요인: {self.limiting_factor}",
            f"  현재: SOC {self.state_of_charge * 100:.1f}%, 묽은 세포 {self.c_dilute * 1000:.1f} mM / "
            f"진한 세포 {self.c_concentrated * 1000:.1f} mM, OCV {self.open_circuit_voltage():.3f} V, "
            f"내부저항 {self.internal_resistance():.1f} Ω",
        ])
