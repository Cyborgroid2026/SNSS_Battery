"""그래핀(산화그래핀, GO) 액정 + 식염수 자기조립 ("결정화") 판정.

식염수에 GO를 넣었을 때 굳는 현상은 엄밀히는 결정화가 아니라
염이 GO 판 사이의 정전기적 반발을 가려(디바이 차폐) 판들이 응집·겔화하는 현상입니다.
GO 농도가 충분하면 판들이 먼저 한 방향으로 정렬(네마틱 액정)되고,
그 상태로 응집되면 정렬된 막/겔 — 인공세포의 '세포막' 재료 — 이 됩니다.

- 액정 전이: 얇은 판에 대한 Onsager형 근사 φ_I ≈ 3.3·t/D, φ_N ≈ 4.2·t/D
- 염 응집: 임계응집농도(CCC). 순수 GO + NaCl 문헌값 약 44 mM.
  고분자로 입체 안정화하면 CCC가 올라감 → 파라미터로 조절.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .electrolyte import debye_length_nm

GO_DENSITY_G_CM3 = 1.8
PURE_GO_NACL_CCC_MM = 44.0


class Phase(str, Enum):
    ISOTROPIC = "isotropic"
    BIPHASIC = "biphasic"
    NEMATIC = "nematic"
    AGGREGATED = "aggregated"
    ALIGNED_GEL = "aligned_gel"


PHASE_LABELS = {
    Phase.ISOTROPIC: "등방성 분산 (무질서, 흐르는 액체)",
    Phase.BIPHASIC: "등방/액정 2상 공존",
    Phase.NEMATIC: "네마틱 액정 (판들이 정렬, 아직 유동)",
    Phase.AGGREGATED: "무질서 응집/침전 (막 품질 낮음)",
    Phase.ALIGNED_GEL: "정렬 응집 겔 = 막 형성 ('결정화')",
}


@dataclass
class GrapheneLCDispersion:
    go_mg_per_ml: float = 5.0  # GO 농도 (= g/L)
    flake_size_um: float = 10.0  # 판 가로 크기 D
    flake_thickness_nm: float = 1.0  # 단일층 GO ≈ 1 nm
    ccc_mm: float = PURE_GO_NACL_CCC_MM  # 임계응집농도 (고분자 첨가 시 상승)

    def __post_init__(self) -> None:
        for name in ("go_mg_per_ml", "flake_size_um", "flake_thickness_nm", "ccc_mm"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name}은(는) 양수여야 합니다.")

    @property
    def aspect_ratio(self) -> float:
        """t/D (작을수록 낮은 농도에서 액정이 됨)."""
        return self.flake_thickness_nm / (self.flake_size_um * 1000.0)

    @property
    def volume_fraction(self) -> float:
        return self.go_mg_per_ml / 1000.0 / GO_DENSITY_G_CM3

    @property
    def isotropic_limit_mg_ml(self) -> float:
        return 3.3 * self.aspect_ratio * GO_DENSITY_G_CM3 * 1000.0

    @property
    def nematic_limit_mg_ml(self) -> float:
        return 4.2 * self.aspect_ratio * GO_DENSITY_G_CM3 * 1000.0


def classify_phase(d: GrapheneLCDispersion, nacl_mm: float) -> Phase:
    ordered = d.go_mg_per_ml >= d.isotropic_limit_mg_ml
    if nacl_mm >= d.ccc_mm:
        return Phase.ALIGNED_GEL if ordered else Phase.AGGREGATED
    if d.go_mg_per_ml >= d.nematic_limit_mg_ml:
        return Phase.NEMATIC
    if ordered:
        return Phase.BIPHASIC
    return Phase.ISOTROPIC


@dataclass
class AssemblyReport:
    phase: Phase
    nacl_mm: float
    dispersion: GrapheneLCDispersion

    @property
    def forms_membrane(self) -> bool:
        return self.phase == Phase.ALIGNED_GEL

    def describe(self) -> str:
        d = self.dispersion
        return "\n".join([
            f"GO {d.go_mg_per_ml:g} mg/mL, 판 {d.flake_size_um:g} µm × {d.flake_thickness_nm:g} nm, "
            f"CCC {d.ccc_mm:g} mM | NaCl {self.nacl_mm:.0f} mM (디바이 길이 {debye_length_nm(self.nacl_mm / 1000):.2f} nm)",
            f"  액정 시작 {d.isotropic_limit_mg_ml:.2f} mg/mL, 완전 네마틱 {d.nematic_limit_mg_ml:.2f} mg/mL",
            f"  판정: {PHASE_LABELS[self.phase]}",
        ])


def assess(d: GrapheneLCDispersion, nacl_molarity: float) -> AssemblyReport:
    mm = nacl_molarity * 1000.0
    return AssemblyReport(classify_phase(d, mm), mm, d)
