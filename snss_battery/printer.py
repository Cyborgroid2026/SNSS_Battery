"""SNSS 조각가 SC-1 — 3D 펜을 단 상온 3D 프린터 (명세: spec/SCULPTOR.md).

자기가 다루는 소재(SNSS 소재 = GO · 생리식염수 · PVA 가 하나가 된 젤)로 조각하는 기계. **모든 공정은 상온(25 °C)**.
- 펜에 GO · SNSS(멸균생리식염수 0.9 %) · PVA 가 따로 들어가 펜 끝 혼합기에서 처음 만나 하나가 됨
  (미리 섞으면 바로 젤이 되어 막힘 — 그래서 끝에서 섞고, 그 젤화가 곧 굳는 힘)
  · 식염수의 Na⁺ 가 GO 판의 음전하를 가려(임계응집농도 이상) 판들이 정렬된 채 엉김 (기존 assembly 모델)
  · PVA 의 OH 와 GO 의 산소기가 수소결합 → 초분자 젤 (상온, 되돌릴 수 있음)
- 섞는 비율 + 펜 끝 405 nm 빛(상온 광환원) 으로 재료가 정해짐: 세포질(rGO, 전자 통로) · 막·피부(GO, 이온만)
- GO 줄은 선택 밸브로 p형(NBD) · n형(PEI) · 도핑 없음 GO 를 고름 → 세포마다 페르미 준위 (양자층)
- 출력은 투명한 지지 젤 욕조 안에서 — 펜이 3차원 어디든 획을 그으면 욕조가 그 자리에 붙잡음 (3D 펜)
- 더하기(층 · 허공 획) · 깎기(흡입) · 붙이기(수소결합 자가치유) · 떼기(깎아 가름) — 전부 상온
- 펜은 자석 마운트로 떼어 손으로도 씀 — 손으로 더한 것은 스캐너로 읽어 작업물 기억에 반영
- 기계 부품은 3D 프린터로 뽑고 (parts.py — RepRap 방식), 원료·소모품·전자부품은 시중에서 삼 (약국·마트·문구점·철물점·온라인)
- 아날로그 · 디지털 · 양자 공학기기와 호환 (interfaces.py — BNC · SCPI · 10 MHz/PPS · 트리거 · QRNG · C–V 되먹임)
출력물은 금속 무함유. 기계 자체는 일반 3D 프린터처럼 금속 부품(모터·봉·전자)을 씀.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

G = 9.81
RHO_INK = 1010.0  # kg/m³
ROOM_C = 25.0


@dataclass
class Feed:
    """펜으로 들어가는 원료 한 줄 (주사기 펌프)."""

    key: str  # go · snss · pva
    name: str
    stock: str
    elements: frozenset[str]
    volume_ml: float = 20.0
    inner_d_mm: float = 19.1  # 20 mL 주사기
    lead_mm: float = 2.0

    @property
    def area_mm2(self) -> float:
        return math.pi * (self.inner_d_mm / 2) ** 2


@dataclass
class GoVariant:
    """GO 줄 선택 밸브 뒤 저장통 — 상온에서 도펀트를 미리 흡착시킨 GO."""

    key: str  # plain · p · n
    name: str
    dopant: str  # qcap 도펀트 키
    elements: frozenset[str]


@dataclass
class Recipe:
    """펜 끝에서 세 원료를 섞는 비율 → 한 재료."""

    key: str
    name: str
    go: float
    snss: float
    pva: float
    go_variant: str  # plain · p · n
    light: bool  # 405 nm 광환원 켬 → rGO (전자 통로)
    color: str

    def __post_init__(self) -> None:
        if min(self.go, self.snss, self.pva) < 0 or abs(self.go + self.snss + self.pva - 1) > 1e-9:
            raise ValueError(f"{self.name}: 세 원료 비율은 0 이상, 합은 1 이어야 합니다.")


@dataclass
class Pen:
    name: str = "SNSS 펜 (3채널 혼합 · 탈착식)"
    nozzle_mm: float = 0.41  # 22G, 길이 40 mm (욕조 안까지)
    mixer: str = "나선형 미세 혼합기 4 요소"
    dead_volume_ul: float = 1.5  # 혼합기 안 부피 — 재료를 바꿀 때 밀어내는 양
    gel_time_s: float = 3.0  # 섞인 뒤 젤이 되기까지 (가정 — 이보다 오래 머물면 펜 안에서 굳음)
    light: str = "405 nm LED 링 4 × 300 mW — 펜 끝 2 mm 아래 (GO 상온 광환원)"
    carve: str = "가운데 관 역방향 흡입 + 전단 — 젤을 끊어 빨아들여 회수통으로 (열 없음)"
    carve_rate_mm3_s: float = 2.0  # 흡입 회수 속도 (가정)
    mount: str = "자석 키네마틱 마운트 (볼 3 · 홈 3) + 포고핀 6 — 떼어 손으로 씀"


@dataclass
class Bath:
    """지지 젤 욕조 — 항복응력 미세젤. 펜이 지나가면 흐르고, 멈추면 다시 굳어 획을 붙잡음."""

    size_mm: tuple[float, float, float] = (130.0, 130.0, 110.0)
    gel: str = "약국 초음파 젤 (카보머 · 무알코올) 을 그대로 — 항복응력 있는 투명 미세젤"
    yield_pa: float = 25.0  # 초음파 젤 실측 범위 20–60 Pa (가정 — 첫 시험편으로 확인)
    rinse: str = "생리식염수(154 mM)로 헹굼 — 염이 카보머 미세젤을 무르게 해 씻겨 나감"
    elements: frozenset[str] = frozenset({"C", "H", "O", "N"})


@dataclass
class Chamber:
    temp_c: float = ROOM_C
    humidity_rh: float = 90.0  # 젤이 마르지 않게
    note: str = "상온 25 ± 1 °C · 습도 90 % RH (가습기 + SHT45)"


@dataclass
class SculptorSpec:
    name: str = "SNSS 조각가 SC-1"
    build_mm: tuple[float, float, float] = (120.0, 120.0, 100.0)
    frame_mm: tuple[float, float, float] = (420.0, 420.0, 560.0)
    frame: str = "RepRap 방식 — 출력한 꼭짓점 8개 + 철물점 M8 나사봉 12개 (삼각 보강 없이 상자형)"
    kinematics: str = "CoreXY (펜 XY, Ø8 매끈한 봉 + LM8UU) + 갠트리 Z (M8 나사봉 3개) — 욕조 안 허공 획은 XYZ 동시"
    print_speed_mm_s: float = 8.0
    stroke_speed_mm_s: float = 4.0
    travel_speed_mm_s: float = 60.0  # 욕조 안이라 느리게 (흔적이 남지 않게)
    accel_mm_s2: float = 800.0
    layer_mm: float = 0.32
    line_mm: float = 0.41
    shrink_compensation: float = 0.03  # 숙성 중 젤 수축 (가정)
    cure_h: float = 6.0  # 출력 뒤 숙성: 도펀트 흡착 · 수소결합 안정 (상온, 습한 방)
    heal_min: float = 30.0  # 붙인 면이 원래 세기의 80 % 로 아무는 시간 (가정)
    pen: Pen = field(default_factory=Pen)
    bath: Bath = field(default_factory=Bath)
    chamber: Chamber = field(default_factory=Chamber)
    feeds: list[Feed] = field(default_factory=lambda: default_feeds())
    go_variants: list[GoVariant] = field(default_factory=lambda: default_go_variants())
    recipes: dict[str, Recipe] = field(default_factory=lambda: default_recipes())
    scanner: str = "레이저 선 프로파일러 (분해능 50 µm) — 작업물 겉면을 읽어 기억과 맞춤"
    firmware: str = "Klipper (Raspberry Pi 5 + BTT Octopus Pro, 스테퍼 8축)"
    go_stock_mg_ml: float = 10.0
    nacl_stock_mm: float = 154.0
    pva_stock_wt: float = 10.0
    ccc_per_pva_wt: float = 0.15  # PVA 1 wt% 마다 임계응집농도가 15 % 오름 (고분자 입체 안정화, 가정)

    # ---------- 펜 끝 화학 ----------
    def mixed(self, r: Recipe) -> dict:
        return {"go_mg_ml": self.go_stock_mg_ml * r.go, "nacl_mm": self.nacl_stock_mm * r.snss,
                "pva_wt": self.pva_stock_wt * r.pva}

    def gel_check(self, r: Recipe) -> dict:
        """섞인 직후 젤이 되는지 — 기존 GO 액정 조립 모델에 PVA 의 CCC 상승을 얹음."""
        from .assembly import PURE_GO_NACL_CCC_MM, PHASE_LABELS, GrapheneLCDispersion, assess

        m = self.mixed(r)
        ccc = PURE_GO_NACL_CCC_MM * (1 + self.ccc_per_pva_wt * m["pva_wt"])
        rep = assess(GrapheneLCDispersion(go_mg_per_ml=max(m["go_mg_ml"], 1e-6), ccc_mm=ccc), m["nacl_mm"] / 1000)
        ok = rep.forms_membrane
        # 항복응력 (가정): GO 염 겔 ∝ c^2.5, PVA 수소결합이 보탬
        tau = 30.0 * (m["go_mg_ml"] / 5) ** 2.5 * (1 + 0.5 * m["pva_wt"]) if ok else 0.0
        return {**m, "ccc_mm": ccc, "label": PHASE_LABELS[rep.phase], "ok": ok, "yield_pa": tau,
                "free_height_mm": tau / (RHO_INK * G) * 1000}

    def residence_s(self) -> float:
        """혼합기 안에 머무는 시간 — 젤화 시간보다 짧아야 펜이 막히지 않음."""
        flow_ul_s = self.line_mm * self.layer_mm * self.print_speed_mm_s
        return self.pen.dead_volume_ul / flow_ul_s

    def flow_mm3_s(self) -> float:
        return self.line_mm * self.layer_mm * self.print_speed_mm_s

    def feed(self, key: str) -> Feed:
        return next(f for f in self.feeds if f.key == key)

    def check(self) -> list[str]:
        """설계 점검 — 문제 목록 (비면 통과)."""
        bad = []
        for r in self.recipes.values():
            g = self.gel_check(r)
            if not g["ok"]:
                bad.append(f"{r.name}: 섞인 NaCl {g['nacl_mm']:.0f} mM < CCC {g['ccc_mm']:.0f} mM — 펜 끝에서 굳지 않음")
            elif g["yield_pa"] < self.bath.yield_pa:
                bad.append(f"{r.name}: 항복응력 {g['yield_pa']:.0f} Pa 가 욕조({self.bath.yield_pa:g} Pa)보다 약함")
        if self.residence_s() >= self.pen.gel_time_s:
            bad.append(f"혼합기 체류 {self.residence_s():.1f} s ≥ 젤화 {self.pen.gel_time_s:g} s — 펜 안에서 굳음")
        return bad

    def describe(self) -> str:
        b, p, bt = self.build_mm, self.pen, self.bath
        lines = [f"[{self.name} — 3D 펜을 단 상온 3D 프린터]",
                 f"  출력 공간 {b[0]:g}×{b[1]:g}×{b[2]:g} mm · 프레임 {self.frame_mm[0]:g}×{self.frame_mm[1]:g}×{self.frame_mm[2]:g} mm",
                 f"  {self.frame}",
                 f"  {self.kinematics}",
                 f"  층 {self.layer_mm} mm · 선폭 {self.line_mm} mm · 쌓기 {self.print_speed_mm_s:g} mm/s · 허공 획 {self.stroke_speed_mm_s:g} mm/s",
                 f"  방: {self.chamber.note}",
                 f"  욕조: {bt.gel} · 항복응력 {bt.yield_pa:g} Pa · 끝나면 {bt.rinse}",
                 f"  스캐너: {self.scanner}",
                 f"  [{p.name}] 노즐 {p.nozzle_mm} mm · {p.mixer} (부피 {p.dead_volume_ul:g} µL, 체류 {self.residence_s():.1f} s < 젤화 {p.gel_time_s:g} s)",
                 f"    빛: {p.light}", f"    깎기: {p.carve} · {p.carve_rate_mm3_s:g} mm³/s", f"    {p.mount}",
                 "  원료 (따로 들어가 펜 끝에서 하나가 됨):"]
        for f in self.feeds:
            lines.append(f"    {f.name:<5} {f.stock} · 원소 {','.join(sorted(f.elements))}")
        lines.append("    GO 줄 선택 밸브: " + " · ".join(v.name for v in self.go_variants))
        lines.append("  재료 = 섞는 비율 GO : SNSS : PVA → 섞인 뒤 농도 → 굳음 판정:")
        for r in self.recipes.values():
            g = self.gel_check(r)
            lines.append(f"    {r.name:<12} {r.go:.2f} : {r.snss:.2f} : {r.pva:.2f} {'빛 켬' if r.light else '빛 끔'} → "
                         f"GO {g['go_mg_ml']:.1f} mg/mL · NaCl {g['nacl_mm']:.0f} mM (CCC {g['ccc_mm']:.0f}) · PVA {g['pva_wt']:.1f} % "
                         f"→ {'굳음' if g['ok'] else '안 굳음'} · 항복응력 약 {g['yield_pa']:.0f} Pa (욕조 없이 {g['free_height_mm']:.1f} mm 까지 섬)")
        bad = self.check()
        lines.append("  설계 점검: " + ("통과" if not bad else "; ".join(bad)))
        lines += [f"  숙성 {self.cure_h:g} h (상온 · 습한 방) · 붙인 면 아묾 {self.heal_min:g} 분",
                  f"  펌웨어 {self.firmware}"]
        return "\n".join(lines)


def default_feeds() -> list[Feed]:
    return [
        Feed("go", "GO", "그래핀 산화물 수분산 10 mg/mL (선택 밸브 뒤 3통)", frozenset({"C", "H", "O", "N"})),
        Feed("snss", "SNSS", "멸균생리식염수 0.9 % NaCl (154 mM)", frozenset({"Na", "Cl", "H", "O"})),
        Feed("pva", "PVA", "폴리비닐알코올 10 wt% 수용액", frozenset({"C", "H", "O"})),
    ]


def default_go_variants() -> list[GoVariant]:
    return [
        GoVariant("plain", "GO (막용)", "", frozenset({"C", "H", "O"})),
        GoVariant("p", "GO + NBD (p형)", "NBD", frozenset({"C", "H", "N", "O"})),
        GoVariant("n", "GO + PEI (n형)", "PEI", frozenset({"C", "H", "N", "O"})),
    ]


def default_recipes() -> dict[str, Recipe]:
    return {
        "pos": Recipe("pos", "p 세포질 (+)", 0.50, 0.40, 0.10, "p", True, "#e0344b"),
        "neg": Recipe("neg", "n 세포질 (−)", 0.50, 0.40, 0.10, "n", True, "#2f6db5"),
        "mem": Recipe("mem", "막 · 피부", 0.40, 0.45, 0.15, "plain", False, "#c9d2dc"),
    }


@dataclass
class BomLine:
    group: str
    part: str
    qty: str
    spec: str
    where: str = ""  # 구입처 (일상에서 구할 수 있는 곳)


def bom(spec: SculptorSpec | None = None) -> list[BomLine]:
    """시중에서 사는 것 (출력할 수 없는 부품 · 원료 · 소모품). 출력 부품은 parts.printed_parts()."""
    s = spec or SculptorSpec()
    return [
        # 원료 — 펜에 들어가는 것
        BomLine("원료", "멸균생리식염수 0.9 % (SNSS)", "500 mL × 2", "펜 SNSS 줄 · 헹굼", "약국"),
        BomLine("원료", "PVA 세탁풀 / 슬라임용 PVA 풀", "500 mL", "폴리비닐알코올 — 붕사·향료 없는 것, 10 wt% 로 맞춤", "마트 · 문구점"),
        BomLine("원료", "그래핀 산화물(GO) 수분산", "100 mL", "10 mg/mL, 판 크기 5–20 µm", "온라인 (재료·시약 쇼핑몰)"),
        BomLine("원료", "폴리에틸렌이민 (PEI, 분지형)", "25 g", "n형 도펀트 — GO 통에 미리 흡착", "온라인 시약"),
        BomLine("원료", "4-니트로벤젠디아조늄 테트라플루오로붕산염 (NBD)", "5 g", "p형 도펀트 — 차광 보관", "온라인 시약"),
        BomLine("원료", "초음파 젤 (카보머, 무알코올)", "1 L", s.bath.gel, "약국 · 의료기기점"),
        BomLine("원료", "정제수 (증류수)", "2 L", "원료 희석 · 세척", "마트 · 약국"),
        # 소모품
        BomLine("소모품", "일회용 주사기 20 mL", "6개", "원료 3줄 + 예비", "약국"),
        BomLine("소모품", "블런트 바늘 22G (가능하면 40 mm)", "5개", "펜 노즐", "약국 · 의료기기점 · 온라인"),
        BomLine("소모품", "실리콘 관 Ø1/Ø2 mm (수족관 에어호스 가는 것)", "3 m", "펌프 → 펜", "마트 (수족관 코너)"),
        BomLine("소모품", "PETG 필라멘트 1.75 mm", "1 kg", "출력 부품 (parts.py)", "온라인 · 전자상가"),
        # 기계 — 출력할 수 없는 것
        BomLine("기계", "M8 나사봉 (전산볼트) 1 m", "4개", "프레임 12토막 · Z 3개", "철물점"),
        BomLine("기계", "Ø8 스테인리스 환봉 1 m", "2개", "XY 안내봉 4토막", "철물점"),
        BomLine("기계", "M8 너트 · 와셔", "60개", "프레임 꼭짓점 고정", "철물점"),
        BomLine("기계", "LM8UU 직선 베어링", "8개", "XY 캐리지", "온라인 · 전자상가"),
        BomLine("기계", "GT2 벨트 6 mm 2 m + 20T 풀리 2 · 아이들러 4", "1식", "CoreXY", "온라인 · 전자상가"),
        BomLine("기계", "NEMA17 스테퍼", "8개", "XY 2 · Z 3 · 원료 펌프 3", "온라인 · 전자상가"),
        BomLine("기계", "MG90S 서보", "3개", "핀치 밸브 (GO 통 선택)", "온라인 · 전자상가"),
        BomLine("기계", "네오디뮴 자석 Ø10 × 3 + 쇠구슬 Ø8 × 3", "1식", "펜 키네마틱 마운트 (떼어 손으로 씀)", "문구점 · 철물점"),
        BomLine("전자", "Raspberry Pi 5 + BTT Octopus Pro (TMC2209 × 8)", "1식", "Klipper + 다리(interfaces.py)", "온라인 · 전자상가"),
        BomLine("전자", "405 nm LED 3 W × 4 + 정전류 드라이버", "1식", "펜 끝 광환원", "온라인 · 전자상가"),
        BomLine("전자", "레이저 선 모듈 + USB 카메라", "1식", "스캐너 (작업물 겉면 읽기)", "온라인 · 전자상가"),
        BomLine("전자", "SHT45 온습도 · 초음파 가습기 모듈", "1식", s.chamber.note, "온라인 · 전자상가"),
        BomLine("전자", "ADS1115 (ADC) · MCP4728 (DAC) · XTR115 (4–20 mA)", "각 1개", "아날로그 단자 A1–A6", "온라인 · 전자상가"),
        BomLine("전자", "BNC 판넬 잭 × 8 · SMA 판넬 잭 × 3", "1식", "아날로그 · 트리거 · 양자 동기 단자", "온라인 · 전자상가"),
        BomLine("전자", "74HC390 × 4 + 비교기 (10 MHz → 1 PPS 분주)", "1식", "양자 계측기 시간 동기 (Q1)", "온라인 · 전자상가"),
        BomLine("전자", "신호 릴레이 (DPDT)", "1개", "발 단자 ↔ 외부 충전원 A2 연결/분리", "온라인 · 전자상가"),
        BomLine("전원", "24 V 200 W 어댑터", "1개", "가열·냉각 장치 없음 (상온)", "온라인 · 전자상가"),
    ]


def klipper_cfg(spec: SculptorSpec | None = None) -> str:
    """Klipper printer.cfg 의 조각가 고유 부분 (핀 이름은 예시).

    E 는 펜에서 나가는 잉크 부피(mm³). GO·SNSS·PVA 주사기를 extruder_stepper 로 두고
    rotation_distance = 리드 × 단면적 / 몫 으로 가상 [extruder] 축에 동기화 → 섞는 비율.
    """
    s = spec or SculptorSpec()
    out = [f"# {s.name} — Klipper 설정 (조각가 고유 부분). 핀 이름은 예시 — 배선에 맞게 고칠 것.",
           "# 스테퍼 8축: XY 2 + Z 3 + 원료 3. 가열·냉각 없음 (상온).", "",
           "[printer]", "kinematics: corexy", f"max_velocity: {s.travel_speed_mm_s:g}",
           f"max_accel: {s.accel_mm_s2:g}", "max_z_velocity: 5", "",
           "[z_tilt]", "z_positions: -10,-10 | 150,-10 | 70,160", "points: 10,10 | 130,10 | 70,130", "",
           "[extruder]  # 가상 부피 축: 1 mm = 잉크 1 mm³ (모터 없음, 경로 계획용)",
           "step_pin: PF13", "dir_pin: PF12", "enable_pin: !PF14", "microsteps: 16", "rotation_distance: 1000",
           f"nozzle_diameter: {s.line_mm}", "filament_diameter: 1.1284  # 단면적 1 mm² → E(mm) = 부피(mm³)",
           "max_extrude_cross_section: 5", "heater_pin: PA2  # 히터 없음 (자리만)",
           "sensor_type: temperature_host", "control: watermark", "min_temp: 0", "max_temp: 60", "min_extrude_temp: 0", ""]
    for f in s.feeds:
        out += [f"[extruder_stepper feed_{f.key}]  # {f.name}: {f.stock}",
                f"step_pin: PLACEHOLDER_{f.key.upper()}_STEP", f"dir_pin: PLACEHOLDER_{f.key.upper()}_DIR",
                "microsteps: 16", f"rotation_distance: {f.lead_mm * f.area_mm2:.4f}  # 리드 {f.lead_mm} × 단면적 {f.area_mm2:.2f} mm²", ""]
    out += ["[temperature_sensor chamber]", "sensor_type: SHT3X", "i2c_mcu: mcu", "i2c_bus: i2c1", ""]
    for v in s.go_variants:
        out += [f"[output_pin go_{v.key}]  # 핀치 밸브: {v.name}", f"pin: PLACEHOLDER_VALVE_{v.key.upper()}", "value: 0", ""]
    out += ["[output_pin uv_light]  # 405 nm LED 링", "pin: PB7", "pwm: True", "value: 0", "",
            "[output_pin suction]  # 깎은 소재 흡입", "pin: PB9", "value: 0", "",
            "[output_pin humidifier]", "pin: PB10", "value: 1", "",
            "[output_pin trig_layer]  # D3 TTL · Q3 LVTTL — 층·획·깎기 시작마다 뒤집힘 (움직임 큐와 동기)", "pin: PB11", "value: 0", "",
            "[output_pin charge_relay]  # A2 외부 충전원 ↔ 발 단자", "pin: PB12", "value: 0", "",
            "[gcode_macro TRIG]", "description: 트리거 출력 뒤집기 + 다리에 사건 알림 (시간 태거·카메라 동기)",
            "variable_level: 0", "gcode:",
            "  {% set v = 1 - printer['gcode_macro TRIG'].level %}",
            "  SET_PIN PIN=trig_layer VALUE={v}", "  SET_GCODE_VARIABLE MACRO=TRIG VARIABLE=level VALUE={v}",
            "  RESPOND PREFIX=snss MSG=\"TRIG {params.EVENT|default('layer')} {params.N|default(0)}\"", "",
            "[gcode_macro CHARGE]", "description: 외부 충전원(A2)을 존재의 발 단자에 잇거나 뗌", "gcode:",
            "  SET_PIN PIN=charge_relay VALUE={params.ON|default(1)|int}", "",
            "[gcode_macro MIX]",
            "description: 펜 끝 섞는 비율 GO:SNSS:PVA (합 1) · GO 통 선택 · 빛",
            "gcode:",
            "  {% set g = params.GO|float %}{% set s = params.SNSS|float %}{% set p = params.PVA|float %}",
            "  {% set v = params.VARIANT|default('plain') %}"]
    for f in s.feeds:
        share = {"go": "g", "snss": "s", "pva": "p"}[f.key]
        out += [f"  {{% if {share} > 0.001 %}}",
                f"    SET_EXTRUDER_ROTATION_DISTANCE EXTRUDER=feed_{f.key} DISTANCE={{{f.lead_mm * f.area_mm2:.4f} / {share}}}",
                f"    SYNC_EXTRUDER_MOTION EXTRUDER=feed_{f.key} MOTION_QUEUE=extruder",
                "  {% else %}", f"    SYNC_EXTRUDER_MOTION EXTRUDER=feed_{f.key} MOTION_QUEUE=", "  {% endif %}"]
    out += [f"  SET_PIN PIN=go_{v.key} VALUE={{1 if v == '{v.key}' else 0}}" for v in s.go_variants]
    out += ["  SET_PIN PIN=uv_light VALUE={params.LIGHT|default(0)|float}",
            "  PURGE", "",
            "[gcode_macro PURGE]", "description: 퍼지 컵 위에서 혼합기 안 이전 재료를 밀어냄", "gcode:",
            "  SAVE_GCODE_STATE NAME=purge", "  G90", "  G0 Z95 F600", "  G0 X125 Y5 F3000",
            f"  G1 E{s.pen.dead_volume_ul * 2:g} F60", "  RESTORE_GCODE_STATE NAME=purge MOVE=1", "",
            "[gcode_macro CARVE]", "description: 깎기 모드 — 흡입 켬/끔 (열 없음)", "gcode:",
            "  SET_PIN PIN=suction VALUE={params.ON|default(1)|int}", "",
            "[gcode_macro CURE]", "description: 숙성 — 상온 · 습한 방에서 기다림 (도펀트 흡착, 수소결합 안정)", "gcode:",
            "  G4 P{(params.S|float * 1000)|int}", "",
            "[gcode_macro HEAL]", "description: 붙인 면이 아물 때까지 누른 채 기다림", "gcode:",
            "  G4 P{(params.S|float * 1000)|int}", "",
            "[gcode_macro SCAN]", "description: 레이저 프로파일러로 작업물 겉면 읽기 (호스트 스크립트가 받음)", "gcode:",
            "  RESPOND MSG=\"SCAN_BEGIN\"", "  G0 X0 Y0 Z95 F3000", "  G0 X120 F1200", "  RESPOND MSG=\"SCAN_END\"", ""]
    return "\n".join(out)
