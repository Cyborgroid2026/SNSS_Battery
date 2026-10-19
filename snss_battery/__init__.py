"""SNSS Battery — 약국 생리식염수병 안에서 결정화되는 인공세포형 겔 2차 전지 모델링 패키지.

식염수 + 그래핀 액정/고분자가 병 안에서 겔로 굳으며 인공세포 층을 만들고, 층 사이의
이온 농도차(태어날 때부터 충전됨)에 에너지를 저장한다. 금속을 쓰지 않는다.
"""

from .artificial_cell import ArtificialCellStack, CellGeometry
from .bottle import BottleGelBattery, BottleSpec, GelFormation
from .assembly import GrapheneLCDispersion, Phase, assess, classify_phase
from .electrolyte import SalineSolution, sterile_normal_saline
from .materials import COLLECTORS, END_ELECTRODES, MEMBRANES, Selectivity
from .simulation import CyclingResult, cycle_cc, max_power_point, polarization_curve, suggest_limits

__version__ = "0.2.0"

__all__ = [
    "ArtificialCellStack", "CellGeometry",
    "BottleGelBattery", "BottleSpec", "GelFormation",
    "GrapheneLCDispersion", "Phase", "assess", "classify_phase",
    "SalineSolution", "sterile_normal_saline",
    "COLLECTORS", "END_ELECTRODES", "MEMBRANES", "Selectivity",
    "CyclingResult", "cycle_cc", "max_power_point", "polarization_curve", "suggest_limits",
]
