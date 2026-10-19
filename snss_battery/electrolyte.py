"""생리식염수(NaCl 수용액) 물성."""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass

from .constants import NACL_MOLAR_MASS, NACL_SATURATION_MOLAR

# 25°C NaCl 수용액 전기전도도 (mol/L, mS/cm) — 문헌값 근사.
# 0.154 mol/L ≈ 0.9 wt% (생리식염수) ≈ 15.6 mS/cm
_CONDUCTIVITY_TABLE_25C: list[tuple[float, float]] = [
    (0.0, 0.0),
    (0.001, 0.1237),
    (0.01, 1.185),
    (0.05, 5.55),
    (0.1, 10.67),
    (0.154, 15.6),
    (0.5, 47.0),
    (1.0, 85.8),
    (2.0, 145.0),
    (3.0, 187.0),
    (4.0, 213.0),
    (5.0, 222.0),
    (6.1, 225.0),
]

_TEMP_COEFF = 0.0212  # 전도도 온도계수 (1/°C)
_PURE_WATER_S_PER_M = 5.5e-6

NORMAL_SALINE_MOLAR = 0.154


def _interp(table: list[tuple[float, float]], x: float) -> float:
    xs = [p[0] for p in table]
    if x <= xs[0]:
        return table[0][1]
    if x >= xs[-1]:
        return table[-1][1]
    i = bisect_left(xs, x)
    (x0, y0), (x1, y1) = table[i - 1], table[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def nacl_conductivity(molarity: float, temperature_c: float = 25.0) -> float:
    """NaCl 수용액 전도도 σ [S/m]."""
    k25 = _interp(_CONDUCTIVITY_TABLE_25C, max(molarity, 0.0)) * 0.1  # mS/cm → S/m
    return max(k25 * (1.0 + _TEMP_COEFF * (temperature_c - 25.0)), _PURE_WATER_S_PER_M)


def debye_length_nm(molarity: float) -> float:
    """1:1 전해질 디바이 길이 [nm] (25°C 근사). 막 전하가 이온을 걸러내는 거리 척도."""
    return 0.304 / math.sqrt(max(molarity, 1e-9))


def wt_percent_to_molarity(wt_percent: float) -> float:
    density = 0.997 + 0.0071 * wt_percent  # g/mL
    return min(wt_percent / 100.0 * density * 1000.0 / NACL_MOLAR_MASS, NACL_SATURATION_MOLAR)


@dataclass
class SalineSolution:
    """NaCl 수용액. 기본값은 약국 멸균생리식염수(0.9 wt%, 25°C, pH 7)."""

    nacl_wt_percent: float = 0.9
    temperature_c: float = 25.0
    ph: float = 7.0

    def __post_init__(self) -> None:
        if not 0 < self.nacl_wt_percent <= 26.5:
            raise ValueError("NaCl 농도는 0 초과 26.5 wt% 이하여야 합니다.")
        if not 0.0 <= self.temperature_c <= 80.0:
            raise ValueError("온도는 0~80°C 범위여야 합니다.")
        if not 0.0 <= self.ph <= 14.0:
            raise ValueError("pH는 0~14 범위여야 합니다.")

    @property
    def molarity(self) -> float:
        return wt_percent_to_molarity(self.nacl_wt_percent)

    @property
    def conductivity_s_per_m(self) -> float:
        return nacl_conductivity(self.molarity, self.temperature_c)

    @property
    def debye_length_nm(self) -> float:
        return debye_length_nm(self.molarity)

    @property
    def water_window_v(self) -> float:
        """열역학적 물 분해 전압 [V] (pH 무관 1.229 V)."""
        return 1.229

    def describe(self) -> str:
        return (
            f"NaCl {self.nacl_wt_percent:.2f} wt% ({self.molarity * 1000:.0f} mM), "
            f"{self.temperature_c:.1f}°C, pH {self.ph:.1f}, σ={self.conductivity_s_per_m:.3f} S/m, "
            f"디바이 길이 {self.debye_length_nm:.2f} nm"
        )


def sterile_normal_saline(temperature_c: float = 25.0) -> SalineSolution:
    """멸균생리식염수(0.9% NaCl) 프리셋."""
    return SalineSolution(0.9, temperature_c, 7.0)
