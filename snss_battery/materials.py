"""금속 무함유 재료 데이터베이스와 금속 검사.

수치는 문헌 범위에서 고른 **출발값(placeholder)** 입니다. 실제 배합으로 만든 막의
막전위·면저항·염 투과도를 측정해 교체하세요.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# 비금속 + 준금속 원소. 이 외의 원소는 금속으로 간주.
NONMETALS = frozenset({
    "H", "He", "B", "C", "N", "O", "F", "Ne", "Si", "P", "S", "Cl", "Ar",
    "As", "Se", "Br", "Kr", "Te", "I", "Xe", "At", "Rn",
})
# 체액에 원래 존재하는 이온 — 전해질(식염수) 안에서만 허용
BODY_FLUID_IONS = frozenset({"Na", "K", "Ca", "Mg"})


class Selectivity(str, Enum):
    CATION = "cation"  # 음전하 막 → Na⁺ 통과 (세포막의 Na⁺ 채널 역할)
    ANION = "anion"  # 양전하 막 → Cl⁻ 통과


@dataclass(frozen=True)
class Membrane:
    """인공세포막 (그래핀 액정 기반 이온 선택성 막)."""

    key: str
    name: str
    selectivity: Selectivity
    elements: frozenset[str]
    permselectivity: float  # 묽은 용액에서의 이온 선택도 α0 (0~1)
    half_screening_molar: float  # 이 평균 농도에서 선택도가 절반으로 (디바이 차폐)
    area_resistance_ohm_cm2: float
    salt_permeability_m_s: float  # 농도차에 의한 염 역확산 (자가방전)
    thickness_um: float
    note: str = ""

    def selectivity_at(self, mean_molarity: float) -> float:
        return self.permselectivity / (1.0 + mean_molarity / self.half_screening_molar)


@dataclass(frozen=True)
class EndElectrode:
    """스택 양 끝에서 이온 전류를 전자 전류로 바꾸는 탄소 전극 (전기이중층)."""

    key: str
    name: str
    elements: frozenset[str]
    specific_capacitance_f_g: float
    safe_voltage_v: float  # 전극 하나에 걸 수 있는 최대 전압 (넘으면 물 분해/가스)
    note: str = ""


@dataclass(frozen=True)
class CurrentCollector:
    key: str
    name: str
    elements: frozenset[str]
    resistance_ohm: float
    note: str = ""


_CHO = frozenset({"C", "H", "O"})

MEMBRANES: dict[str, Membrane] = {m.key: m for m in [
    Membrane("go_lc", "GO 액정 적층막", Selectivity.CATION, _CHO,
             0.85, 0.30, 5.0, 2e-11, 5.0,
             "카복실기 음전하 → 양이온 선택. 식염수 응집으로 형성되는 기본 막"),
    Membrane("go_pss", "GO/PSS 복합막", Selectivity.CATION, _CHO | {"S"},
             0.92, 0.60, 4.0, 1e-11, 8.0,
             "설폰산기 추가로 음전하 밀도↑ → 고농도에서도 선택도 유지"),
    Membrane("go_pdda", "GO/PDDA 복합막", Selectivity.ANION, _CHO | {"N", "Cl"},
             0.80, 0.30, 6.0, 2e-11, 8.0,
             "4급 암모늄 양이온 고분자로 전하 반전 → 음이온 선택"),
    Membrane("go_pei", "GO/PEI 복합막", Selectivity.ANION, _CHO | {"N"},
             0.70, 0.20, 7.0, 4e-11, 8.0,
             "아민기 양전하(중성 pH에서 일부만 양성자화) → 선택도 낮음"),
]}

END_ELECTRODES: dict[str, EndElectrode] = {e.key: e for e in [
    EndElectrode("rgo", "환원 그래핀 산화물 (rGO)", _CHO, 150.0, 0.6),
    EndElectrode("lc_rgo", "액정 정렬 rGO", _CHO, 200.0, 0.6,
                 "액정 정렬로 이온 경로 단축 (비정전용량은 가정값)"),
    EndElectrode("activated_carbon", "활성탄", _CHO, 120.0, 0.6),
]}

COLLECTORS: dict[str, CurrentCollector] = {c.key: c for c in [
    CurrentCollector("graphite_paper", "흑연 종이", frozenset({"C"}), 0.1),
    CurrentCollector("carbon_cloth", "탄소 섬유 천", frozenset({"C"}), 0.5),
    CurrentCollector("rgo_film", "rGO 필름", _CHO, 10.0),
]}


def _lookup(table: dict, key: str, what: str):
    try:
        return table[key.lower()]
    except KeyError:
        raise KeyError(f"알 수 없는 {what} '{key}'. 사용 가능: {', '.join(table)}") from None


def get_membrane(key: str) -> Membrane:
    return _lookup(MEMBRANES, key, "막")


def get_end_electrode(key: str) -> EndElectrode:
    return _lookup(END_ELECTRODES, key, "전극")


def get_collector(key: str) -> CurrentCollector:
    return _lookup(COLLECTORS, key, "집전체")


def membranes_by_selectivity(sel: Selectivity) -> list[Membrane]:
    return [m for m in MEMBRANES.values() if m.selectivity == sel]


@dataclass
class AuditLine:
    component: str
    elements: frozenset[str]
    metals: frozenset[str]
    is_electrolyte: bool = False

    @property
    def ok(self) -> bool:
        if self.is_electrolyte:
            return self.metals <= BODY_FLUID_IONS
        return not self.metals


def audit(components: list[tuple[str, frozenset[str], bool]]) -> list[AuditLine]:
    """[(이름, 원소, 전해질 여부)] → 금속 포함 여부 검사."""
    return [AuditLine(name, els, frozenset(els - NONMETALS), is_el) for name, els, is_el in components]


def format_audit(lines: list[AuditLine]) -> str:
    out = []
    for ln in lines:
        els = ",".join(sorted(ln.elements))
        if ln.ok and ln.metals:
            mark = f"✔ ({'/'.join(sorted(ln.metals))}⁺는 체액 이온으로 허용)"
        elif ln.ok:
            mark = "✔ 금속 없음"
        else:
            mark = f"✘ 금속 포함: {', '.join(sorted(ln.metals))}"
        out.append(f"  {ln.component:<14} [{els}] {mark}")
    verdict = "금속 무함유 ✔" if all(ln.ok for ln in lines) else "금속 포함 ✘"
    return f"금속 검사: {verdict}\n" + "\n".join(out)
