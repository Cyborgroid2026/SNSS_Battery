"""약국 생리식염수병 안에서 일어나는 결정화 — 결정 자체가 전지.

과정 (별도 전극·미리 만든 인공세포 없음)
    1. 생리식염수병(0.9 % NaCl)에 그래핀 폴리머 액정(GO) + 함께 반응하는 화학물질을 붓는다.
    2. 병 안에서 결정화(정렬 겔화)가 바닥→위로 진행되며, 세포처럼 막(GO 벽)으로 나뉜
       도메인이 저절로 생긴다. 이웃 도메인의 염 농도가 달라진 채 굳는다 → 태어날 때부터 충전.
    3. 병을 잘라 결정 덩어리를 꺼낸다. 결정의 위·아래 면(그래핀이 모인 면)이 그대로 단자 역할.
       멀티미터 프로브는 측정 장비일 뿐 전지 부품이 아니다.
    4. 다 쓰면 반대 방향 전류로 농도차를 다시 만들어 재사용(2차 전지).

물리적 전제 (중요)
    - 도메인이 한 방향(병 높이)으로 층을 이루어야 막전위가 직렬로 더해진다. 무작위 배열이면 상쇄되어 0 V.
    - 이웃 도메인 벽이 양이온 선택(CEM) / 음이온 선택(AEM)으로 번갈아 생겨야 한다(반응 화학물의 역할).
    - 에너지원은 결정화 때 생긴 농도차뿐이고, 보관 중 막을 통한 염 확산으로 서서히 줄어든다.
    - 별도 전극이 없으므로, 전류를 오래 뽑을 수 있는 양은 결정 표면 그래핀의 전기이중층 용량이 제한한다.
      전압계(전류 ≈ 0)로는 개방전압을 바로 잴 수 있다.
    - '결정화 시 농도비'와 표면 그래핀 양이 핵심 미지수 → 실험으로 측정.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .artificial_cell import ArtificialCellStack, CellGeometry
from .electrolyte import SalineSolution, sterile_normal_saline
from .materials import get_membrane


@dataclass
class BottleSpec:
    """약국 생리식염수병 (PE/PP). 기본값은 일반적인 500 mL 병의 근사 치수 — 실제 병을 재서 바꾸세요."""

    fill_volume_ml: float = 500.0
    outer_diameter_mm: float = 72.0
    wall_mm: float = 0.8
    body_height_mm: float = 150.0  # 바닥 ~ 어깨 시작
    shoulder_height_mm: float = 25.0
    neck_diameter_mm: float = 28.0
    neck_height_mm: float = 15.0
    cap_diameter_mm: float = 32.0
    cap_height_mm: float = 18.0

    def __post_init__(self) -> None:
        for k, v in self.__dict__.items():
            if v <= 0:
                raise ValueError(f"{k}은(는) 양수여야 합니다.")
        if self.fill_height_mm > self.body_height_mm:
            raise ValueError("식염수 높이가 병 몸통보다 높습니다. 병 치수나 용량을 확인하세요.")

    @property
    def inner_diameter_mm(self) -> float:
        return self.outer_diameter_mm - 2 * self.wall_mm

    @property
    def inner_area_cm2(self) -> float:
        return math.pi * (self.inner_diameter_mm / 20) ** 2

    @property
    def fill_height_mm(self) -> float:
        return self.fill_volume_ml / self.inner_area_cm2 * 10

    @property
    def total_height_mm(self) -> float:
        return self.body_height_mm + self.shoulder_height_mm + self.neck_height_mm + self.cap_height_mm


@dataclass
class GelFormation:
    """결정화(겔화) 조건과 그 결과로 생기는 층 구조."""

    go_mg_per_ml: float = 5.0  # 병에 넣는 GO 액정 농도
    layer_thickness_mm: float = 0.5  # 인공세포 한 층 두께
    concentration_ratio: float = 20.0  # 태어날 때 진한 세포 / 묽은 세포 농도비
    shrinkage: float = 0.0  # 겔화 수축률 (0~0.5), 겔 지름·높이가 이만큼 줄어듦
    cation_membrane: str = "go_lc"
    anion_membrane: str = "go_pdda"
    surface_go_mg_cm2: float = 0.0  # 결정 위·아래 면의 그래핀 양. 0 = 자동(도메인 벽 한 장 분량)
    reactants: str = ""  # 함께 붓는 반응 화학물질 (레시피 메모)
    # 보로노이·프랙탈 구조 (tessellation.py 참고)
    interface_dimension: float = 1.25  # 층 경계 프랙탈 차원 (1 = 평평)
    interface_roughness: float = 0.35  # 층 경계 RMS 진폭 / 층 두께
    interface_correlation: float = 0.85  # 이웃 층 경계가 함께 휘는 정도
    seed_dimension: float = 2.0  # 결정핵 분포 프랙탈 차원 (2 = 고름)
    grains_per_layer: float = 3.0  # 층 두께당 결정핵 수

    def __post_init__(self) -> None:
        if self.go_mg_per_ml <= 0 or self.layer_thickness_mm <= 0:
            raise ValueError("GO 농도와 층 두께는 양수여야 합니다.")
        if self.surface_go_mg_cm2 < 0:
            raise ValueError("표면 그래핀 양은 0 이상이어야 합니다 (0 = 자동).")
        if self.concentration_ratio < 1:
            raise ValueError("농도비는 1 이상이어야 합니다 (1 = 농도차 없음 = 방전 상태).")
        if not 0 <= self.shrinkage < 0.5:
            raise ValueError("수축률은 0 이상 0.5 미만이어야 합니다.")


class BottleGelBattery:
    def __init__(self, bottle: BottleSpec | None = None, formation: GelFormation | None = None,
                 saline: SalineSolution | None = None) -> None:
        self.bottle = bottle or BottleSpec()
        self.formation = formation or GelFormation()
        self.saline = saline or sterile_normal_saline()
        f = self.formation
        cem, aem = get_membrane(f.cation_membrane), get_membrane(f.anion_membrane)
        self._pair_mm = 2 * f.layer_thickness_mm + (cem.thickness_um + aem.thickness_um) / 1000
        n_pairs = int(math.floor(self.gel_height_mm / self._pair_mm + 1e-9))  # 딱 맞는 높이의 반올림 오차로 한 쌍 잃지 않게
        if n_pairs < 1:
            raise ValueError("겔 높이가 인공세포 한 쌍보다 작습니다. 층 두께를 줄이세요.")
        self.stack = ArtificialCellStack(
            n_pairs=n_pairs,
            saline=self.saline,
            geometry=CellGeometry(self.gel_area_cm2, f.layer_thickness_mm),
            cation_membrane=cem,
            anion_membrane=aem,
            electrode="rgo",
            electrode_mass_mg=self._surface_go_mg_cm2(n_pairs) * self.gel_area_cm2,
        )
        self.born()

    def fractal_params(self, window_layers: int = 40, window_width_mm: float = 8.0, seed: int = 1):
        from .tessellation import FractalVoronoiParams

        f = self.formation
        return FractalVoronoiParams(f.interface_dimension, f.interface_roughness, f.interface_correlation,
                                    f.seed_dimension, f.grains_per_layer, window_layers, window_width_mm, seed)

    def _surface_go_mg_cm2(self, n_pairs: int) -> float:
        if self.formation.surface_go_mg_cm2 > 0:
            return self.formation.surface_go_mg_cm2
        return self.go_mass_g * 1000 / (2 * n_pairs) / self.gel_area_cm2

    @property
    def surface_go_mg_cm2(self) -> float:
        return self.stack.electrode_mass_mg / self.gel_area_cm2

    # ---------- 형상 ----------
    @property
    def gel_diameter_mm(self) -> float:
        return self.bottle.inner_diameter_mm * (1 - self.formation.shrinkage)

    @property
    def gel_height_mm(self) -> float:
        return self.bottle.fill_height_mm * (1 - self.formation.shrinkage)

    @property
    def gel_area_cm2(self) -> float:
        return math.pi * (self.gel_diameter_mm / 20) ** 2

    @property
    def active_height_mm(self) -> float:
        """층을 이룬 결정 도메인이 차지하는 높이 (나머지는 위쪽 자투리)."""
        return self.stack.n_pairs * self._pair_mm

    @property
    def go_mass_g(self) -> float:
        return self.formation.go_mg_per_ml * self.bottle.fill_volume_ml / 1000

    # ---------- 상태 ----------
    def born(self) -> None:
        """결정화 직후 상태: 묽은/진한 도메인 농도비 = concentration_ratio, 표면 이중층은 아직 미충전."""
        s, r = self.stack, self.formation.concentration_ratio
        s.reset()
        s.x = min(s.c0 * (r - 1) / (r + 1), s.max_shift)

    @property
    def shelf_time_constant_days(self) -> float:
        """보관 중 농도차가 1/e 로 줄어드는 시간 (막을 통한 염 역확산)."""
        s = self.stack
        perm = s.cem.salt_permeability_m_s + s.aem.salt_permeability_m_s
        return s.geometry.thickness_m / (2 * perm) / 86400

    def age(self, days: float) -> None:
        """보관 (회로 미연결) 동안의 자가방전."""
        if days > 0:
            self.stack.x *= math.exp(-days / self.shelf_time_constant_days)

    def describe(self) -> str:
        b, f, s = self.bottle, self.formation, self.stack
        return "\n".join([
            f"용기: 생리식염수 {b.fill_volume_ml:g} mL 병 (내경 {b.inner_diameter_mm:.1f} mm, 식염수 높이 {b.fill_height_mm:.1f} mm)",
            f"겔: Ø{self.gel_diameter_mm:.1f} × {self.gel_height_mm:.1f} mm, GO {self.go_mass_g:.2f} g, "
            f"세포형 결정 도메인 {2 * s.n_pairs}층 ({s.n_pairs}쌍, 층 {f.layer_thickness_mm:g} mm)",
            f"결정화 시 농도비 {f.concentration_ratio:g} → 묽은 도메인 {s.c_dilute * 1000:.1f} mM / "
            f"진한 도메인 {s.c_concentrated * 1000:.1f} mM",
            f"결정 표면 그래핀 {self.surface_go_mg_cm2:.2f} mg/cm² (자체 단자면, 정전용량 {s.electrode_capacitance_f:.2f} F)",
            f"보관 수명(1/e) 약 {self.shelf_time_constant_days:.0f}일",
        ])
