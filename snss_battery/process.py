"""실험 공정 — 통째 결정 (인공세포형), 실험실 장비 기준.

RECIPE.md 3절, 웹 뷰어의 레시피 탭과 실험대가 모두 이 목록을 씁니다.
단계마다 수작업(사람이 손으로 함)인지 기계작업(장비가 혼자 함, 사람은 확인만)인지와
손이 붙어 있는 시간, 걸리는 시간, 장비, 다음 단계로 넘어가는 확인 조건을 적습니다.

실제로 되는지 따져 바꾼 점 (이전 레시피 대비):
- 방향성 동결: 냉동실(사방 −20 °C)에서는 옆면으로도 얼어 들어가 방향성이 깨지므로,
  저온실(+4 °C) 안의 냉각판(−20 °C)에 세움. 옆으로 새는 열이 작아 아래에서 위로만 얾.
- 해동: 4 °C 공기로는 500 mL 얼음이 2 h 에 녹지 않음 (약 40 h) → 25 °C 항온수조.
- 재동결: 냉동실에 그냥 넣으면 사방에서 얼어 세포 방향이 섞이므로 같은 냉각판 세팅으로.
- 섞기: 15 wt% PVA 는 꿀처럼 진해 병을 굴려서는 고르게 섞이지 않음 → 비커에서 교반 후 병에 다시 담음.
- GO 응집: 식염수(154 mM)가 순수 GO 의 임계응집농도(44 mM)보다 진함 → 본 배합 전에 축소 예비 시험.
- 단면 분석: 170 µm 세포는 손 탐침으로 구분 불가 → 액체질소 급속 고정 · 동결건조 · SEM-EDS.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .tissue import ICE_RHO_L, TissueRecipe, freezing

HAND, MACHINE = "hand", "machine"
MODE_KO = {HAND: "수작업", MACHINE: "기계작업"}
WATER_K = 0.6  # 녹은 물(겔) 열전도도 W/(m·K)
BATH_C = 25.0  # 해동 항온수조
COLD_ROOM_C = 4.0  # 냉각판을 두는 저온실


FEM = Path(__file__).resolve().parents[1] / "spec" / "fenicsx_freezing.json"


def fem_hours() -> tuple[float, float] | None:
    """FEniCSx 결과 (sim/freeze_fenicsx.py): (A 조건 동결 h, 25 °C 수조 해동 h). 없으면 None."""
    try:
        cases = json.loads(FEM.read_text(encoding="utf-8"))["cases"]
    except (OSError, KeyError, ValueError):
        return None
    fz = next(c["t_all_h"] for c in cases if c["name"].startswith("A"))
    th = next(c["t_all_h"] for c in cases if c["name"].startswith("해동"))
    return (fz, th) if fz and th else None


def thaw_hours(radius_mm: float, bath_c: float = BATH_C, melt_c: float = -0.6) -> float:
    """원통을 바깥에서 안으로 녹임 (준정상 스테판): t = ρL R² / (4 k ΔT). 윗면·아랫면으로 드는 열은 무시 → 조금 길게 나옴."""
    r = radius_mm / 1000
    return ICE_RHO_L * r * r / (4 * WATER_K * (bath_c - melt_c)) / 3600


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    mode: str  # HAND | MACHINE
    hands_min: float  # 사람이 붙어 있어야 하는 시간
    hours: float  # 단계가 끝날 때까지 걸리는 시간
    equipment: tuple[str, ...]
    action: str
    check: str  # 다음 단계로 넘어가는 조건

    @property
    def mode_ko(self) -> str:
        return MODE_KO[self.mode]

    def to_json(self) -> dict:
        return {**asdict(self), "equipment": list(self.equipment), "mode_ko": self.mode_ko}


def process(rc: TissueRecipe | None = None) -> list[Step]:
    rc = rc or TissueRecipe()
    bat = rc.battery()
    v = rc.bottle_ml
    pva = v * rc.pva_wt / 100
    go = v * rc.go_mg_ml / 4.0
    rest = v - rc.take_out_ml - go
    # 시간: FEniCSx 열전달 계산이 있으면 그 값 (병 벽 · 처음 20 °C 식히기 · 주변 열까지 들어감), 없으면 해석식
    fem = fem_hours()
    fz, th = fem or (freezing(bat.gel_height_mm, rc.plate_c)["hours"], thaw_hours(bat.bottle.inner_diameter_mm / 2))
    src = "FEniCSx" if fem else "스테판 계산"
    n = rc.freeze_thaw - 1
    s = 1 / 25  # 예비 시험 축척 (500 mL → 20 mL)
    return [
        Step("chill", "냉각판 예냉", MACHINE, 5, 0.1, ("순환식 냉각기", "알루미늄 냉각판", "저온실 +4 °C"),
             f"냉각기를 {rc.plate_c:g} °C 로 켠다. 판이 식는 동안(30–60분) 다음 단계를 진행한다.",
             f"판 표면 온도 {rc.plate_c:g} ± 1 °C (동결 세팅 전까지)"),
        Step("weigh", "계량", HAND, 10, 0.2, ("전자저울 0.01 g", "칭량 접시"),
             f"PVA 가루 {pva:.2f} g 을 잰다.", f"{pva:.2f} ± 0.05 g"),
        Step("take", "식염수 덜어 내기", HAND, 5, 0.1, ("메스실린더 100 mL", "250 mL 비커"),
             f"병에서 식염수 {rc.take_out_ml:.0f} mL 를 비커에 덜고, {go:.1f} mL 를 더 덜어 따로 둔다. 병은 마개를 닫아 둔다.",
             f"병에 {rest:.1f} mL 남음"),
        Step("disperse", "PVA 분산", HAND, 10, 0.2, ("교반 막대", "알루미늄 호일"),
             "상온에서 300 rpm 으로 저으며 PVA 를 조금씩 뿌린다. 호일로 덮고 비커째 무게를 적는다.",
             "덩어리 없이 뿌옇게 퍼짐 · 무게 기록"),
        Step("stock", "PVA 용해", MACHINE, 10, 2.0, ("핫플레이트 교반기", "온도 프로브"),
             "용액 온도 90 °C, 300 rpm 으로 약 2 h 녹인다. 30분마다 본다.",
             f"투명하고 덩어리 없음 ({100 * pva / rc.take_out_ml:.0f} wt%, 꿀처럼 진함)"),
        Step("cool", "증발 보정 · 식히기", MACHINE, 5, 0.7, ("전자저울", "증류수", "핫플레이트 교반기 (가열 끔)"),
             "비커째 무게를 재서 줄어든 만큼 증류수를 보충한다. 가열을 끄고 저으며 식힌다.",
             "무게 복원 · 40 °C 이하"),
        Step("pretest", "예비 시험 — GO 응집", HAND, 10, 0.5, ("20 mL 바이알", "피펫"),
             f"식염수 {rest * s:.1f} mL + PVA 용액 {rc.take_out_ml * s:.0f} mL + GO {go * s:.1f} mL 를 섞어 30분 둔다.",
             "빛에 비춰 고른 갈색이면 진행 · 알갱이나 가라앉은 층이 보이면 중단"),
        Step("mix", "비커에서 섞기", MACHINE, 10, 0.6, ("1 L 비커", "핫플레이트 교반기 (가열 끔)"),
             f"병의 남은 식염수 {rest:.1f} mL 를 비커에 붓고 300 rpm 으로 저으며 PVA 용액, GO {go:.1f} mL 순서로 천천히 넣는다. 30분 젓는다.",
             "줄무늬 없이 고른 갈색"),
        Step("degas", "기포 빼기", MACHINE, 5, 0.3, ("진공 데시케이터", "진공 펌프"),
             "15분 감압한다. 거품이 끓어오르면 잠깐 진공을 푼다.", "표면에 기포 없음"),
        Step("refill", "병에 다시 담기", HAND, 10, 0.2, ("깔때기", "전자저울"),
             f"벽을 타고 흐르게 천천히 병에 붓는다. 뚜껑은 반 바퀴 풀어 얹는다.",
             f"{v:.0f} mL · 액면이 어깨 아래 (얼면 9 % 늘어남)"),
        Step("setup", "동결 세팅", HAND, 15, 0.25, ("접촉액 (30 % 에탄올)", "스티로폼 3 cm", "열전대 2개 + 기록계"),
             "병 바닥이 평평한지 보고, 판에 접촉액을 몇 mL 떨어뜨린 뒤 병을 세운다. 옆면·윗면을 단열하고 병 벽 아래·위에 열전대를 붙인다.",
             "바닥 열전대가 내려가기 시작"),
        Step("dfreeze", "방향성 동결", MACHINE, 0, fz, ("냉각판", "저온실 +4 °C", "기록계"),
             f"손대지 않는다. 얼음이 아래에서 위로 자라며 세포가 생긴다 ({src} 약 {fz:.0f} h).",
             "위쪽 열전대 < −3 °C (판 접촉이 나쁘면 더 걸림)"),
        Step("thaw", "해동", MACHINE, 5, th, ("항온수조 25 °C",),
             f"병을 어깨까지 수조에 담근다 ({src} 약 {th:.1f} h).",
             "병을 눌러 단단한 심이 없음"),
        Step("ft", f"재동결 · 해동 × {n}", MACHINE, 30 * n, n * (fz + th), ("냉각판", "항온수조 25 °C"),
             f"동결 세팅과 같은 방법으로 다시 방향성 동결 → 수조 해동을 {n}번 한다. PVA 골격이 단단해진다.",
             "회차마다 열전대 기록 · S4 용 1회 시료는 첫 해동 뒤 바로 분석"),
        Step("demold", "병 절단 · 꺼내기", HAND, 15, 0.3, ("절단 가이드 띠", "커터", "받침"),
             "가이드 띠를 따라 병을 자르고 겔을 받친 채 꺼낸다.", "10분 안에 다음 측정"),
        Step("meas", "윗면–아랫면 전압", HAND, 15, 0.25, ("흑연 막대 2개", "10 MΩ 멀티미터"),
             "윗면·아랫면에 흑연 막대를 대고 DC mV 를 잰다. 정·역 각 3번.", "E2 기록"),
        Step("section", "단면 채취 · 급속 고정", HAND, 30, 0.5, ("면도칼", "액체질소", "실체현미경"),
             "세로로 잘라 단면 사진을 찍고 (자 함께), 위·가운데·아래에서 2 mm 조각을 떼어 액체질소에 10초 담근다.",
             "S1–S3 사진 · 조각 3개 고정"),
        Step("lyo", "동결건조", MACHINE, 10, 24.0, ("동결건조기",), "고정한 조각을 얼린 채로 말린다.", "무게 변화 없음"),
        Step("cond", "단면 분석 — SEM-EDS", MACHINE, 120, 2.0, ("SEM-EDS",),
             "Cl 지도로 벽 근처와 칸 안의 소금 신호를 비교하고, 칸 폭을 잰다.", "E1 · S1 · S2 기록"),
    ]


def summary(steps: list[Step]) -> dict:
    hours = sum(x.hours for x in steps)
    by = {m: sum(x.hours for x in steps if x.mode == m) for m in MODE_KO}
    return {"hours": hours, "days": hours / 24, "hands_h": sum(x.hands_min for x in steps) / 60,
            "hand_steps": sum(x.mode == HAND for x in steps), "machine_steps": sum(x.mode == MACHINE for x in steps),
            "hand_hours": by[HAND], "machine_hours": by[MACHINE]}


def _dur(h: float) -> str:
    return f"{h:.1f} h" if h >= 1 else f"{h * 60:.0f} 분"


def markdown(steps: list[Step] | None = None) -> str:
    """RECIPE.md 3절 표."""
    steps = steps or process()
    rows = ["| # | 단계 | 구분 | 손 | 걸림 | 장비 | 할 일 | 넘어가는 조건 |", "|---|---|---|---|---|---|---|---|"]
    for k, x in enumerate(steps, 1):
        rows.append(f"| {k} | {x.title} | **{x.mode_ko}** | {x.hands_min:.0f} 분 | {_dur(x.hours)} | {' · '.join(x.equipment)} | {x.action} | {x.check} |")
    return "\n".join(rows)


def describe(steps: list[Step] | None = None) -> str:
    steps = steps or process()
    s = summary(steps)
    lines = [f"실험 공정 — 통째 결정 (실험실 장비) · 전체 약 {s['hours']:.0f} h ({s['days']:.1f} 일), 손이 드는 시간 약 {s['hands_h']:.1f} h"]
    for k, x in enumerate(steps, 1):
        lines.append(f"  {k:2d}. [{x.mode_ko}] {x.title:<16} 손 {x.hands_min:4.0f} 분 · {_dur(x.hours):>7} · {', '.join(x.equipment)}")
        lines.append(f"      {x.action}")
        lines.append(f"      → {x.check}")
    return "\n".join(lines)
