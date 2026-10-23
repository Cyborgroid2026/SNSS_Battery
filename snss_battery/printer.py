"""SNSS 조각가 SC-1 — 3D 펜을 단 상온 3D 프린터 (명세: spec/SCULPTOR.md).

자기가 다루는 소재(SNSS 소재 = GO · 생리식염수 · PVA 가 하나가 된 젤)로 조각하는 기계. **모든 공정은 상온(25 °C)**.
- 펜에 GO · SNSS(멸균생리식염수 0.9 %) · PVA 가 따로 들어가 펜 끝 혼합기에서 처음 만나 하나가 됨
  (미리 섞으면 바로 젤이 되어 막힘 — 그래서 끝에서 섞고, 그 젤화가 곧 굳는 힘)
  · 식염수의 Na⁺ 가 GO 판의 음전하를 가려(임계응집농도 이상) 판들이 정렬된 채 엉김 (기존 assembly 모델)
  · PVA 의 OH 와 GO 의 산소기가 수소결합 → 초분자 젤 (상온, 되돌릴 수 있음)
- 섞는 비율 + 펜 끝 405 nm 빛(상온 광환원) 으로 재료가 정해짐: 세포질(rGO, 전자 통로) · 막·피부(GO, 이온만)
- GO 줄은 선택 밸브로 p형(NBD) · n형(PEI) · 도핑 없음 GO 를 고름 → 세포마다 페르미 준위 (양자층)
- **수중 배양 환경** — 프린터 몸체가 멸균생리식염수(= 배지)를 가득 채운 배양조이고, 펜까지 통째로 잠겨 작업함
  · 세포 배양하듯 결정체(존재)가 배지 속에서 층층이 자라고, 배지 속에서 숙성(배양)됨
  · 잉크가 배지(154 mM)에 닿으면 겉부터 엉겨 굳음 (GO 습식 방사의 염 응고조와 같은 원리)
  · 잉크와 배지의 밀도가 거의 같아 자기 무게가 거의 없음(중성 부력) — 받침 없이 허공 획도 버팀
  · 다 자라면 바닥 배양 받침(흑연 패드 2장, 왼발 + · 오른발 −)째 들어 올려 배지에서 바로 꺼냄 (수확)
  · **기계까지 통째로 배지에 잠김** — 젖는 쪽은 비금속만(PETG · 탄소섬유 봉 · 나일론 나사봉 · 유리섬유 벨트) 이라 녹슬지 않고
    배지에 금속 이온이 섞이지 않음. 모터는 방수 통 안에서 자석 커플링으로 벽 너머를 돌리고(수족관 펌프 방식, 축 구멍 없음),
    전자는 방수 통 하나에, 방수 케이블 한 가닥(24 V + 이더넷)만 배양조 밖 단자판으로 — 누설 전류 감시로 새면 전원 차단
- 더하기(층 · 허공 획) · 깎기(흡입) · 붙이기(수소결합 자가치유) · 떼기(깎아 가름) — 전부 상온
- 펜은 자석 마운트로 떼어 손으로도 씀 — 손으로 더한 것은 스캐너로 읽어 작업물 기억에 반영
- 기계 부품은 3D 프린터로 뽑고 (parts.py — RepRap 방식), 원료·소모품·전자부품은 시중에서 삼 (약국·마트·문구점·철물점·온라인)
- 아날로그 · 디지털 · 양자 공학기기와 호환 (interfaces.py — BNC · SCPI · 10 MHz/PPS · 트리거 · QRNG · C–V 되먹임)
출력물은 금속 무함유. 기계의 금속(모터 · 자석 · 전자)은 모두 방수 통 안이나 실리콘 속에 있어 배지에 닿지 않음.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

G = 9.81
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
    name: str = "SNSS 펜 (3채널 혼합 · 탈착식 · 물속)"
    nozzle_mm: float = 0.41  # 22G 상당 — PEEK 노즐 (스테인리스 바늘은 물속 금속이라 쓰지 않음)
    mixer: str = "나선형 미세 혼합기 4 요소"
    dead_volume_ul: float = 1.5  # 혼합기 안 부피 — 재료를 바꿀 때 밀어내는 양
    gel_time_s: float = 3.0  # 섞인 뒤 젤이 되기까지 (가정 — 이보다 오래 머물면 펜 안에서 굳음)
    light: str = "405 nm LED 링 4 × 300 mW — 투명 실리콘으로 묻어 물속에서 펜 끝 2 mm 아래를 비춤 (GO 상온 광환원)"
    seal: str = "몸체 O-링 2개 · 전선 · LED 는 투명 실리콘으로 묻음 — 펜 통째로 배지에 잠김"
    carve: str = "가운데 관 역방향 흡입 + 전단 — 젤을 끊어 빨아들여 회수통으로 (열 없음)"
    carve_rate_mm3_s: float = 2.0  # 흡입 회수 속도 (가정)
    mount: str = "자석 키네마틱 마운트 (자석·구슬은 PETG 속에 묻음, 볼 3 · 홈 3) — 떼어 손으로 씀 (전선은 실리콘 속)"


RHO_WATER_25 = 997.05  # kg/m³
NACL_KG_M3_PER_MM = 0.0405  # 녹은 NaCl 1 mM 이 밀도에 보태는 양


def solution_density(go_g_l: float = 0.0, nacl_mm: float = 0.0, pva_g_l: float = 0.0) -> float:
    """묽은 수용액 밀도 kg/m³ — 녹은 것마다 c·(1 − ρ_물/ρ_고체) 를 더함 (GO 1.8, PVA 1.27 g/cm³)."""
    return (RHO_WATER_25 + go_g_l * (1 - RHO_WATER_25 / 1800) + pva_g_l * (1 - RHO_WATER_25 / 1270)
            + NACL_KG_M3_PER_MM * nacl_mm)


@dataclass
class Tank:
    """배양조 = 기계 전체가 잠기는 수조. 멸균생리식염수(배지)를 가득 채우고 그 안에서 결정체를 키움, 다 자라면 받침째 꺼냄."""

    inner_mm: tuple[float, float, float] = (350.0, 350.0, 350.0)
    container: str = "36 큐브 수조 (유리, 안 350 mm) — 마트 · 수족관"
    saline_mm: float = 154.0  # 0.9 % NaCl
    fill_mm: float = 330.0  # 기계(높이 300) 위로 30 mm 더 — 기계까지 통째로 잠김
    medium_src: str = ("약국 생리식염수 1 L × 40, 또는 직접: 정제수 40 L + 정제염(NaCl 99.5 % 이상, 첨가물 없는 것) 360 g "
                       "— 뜯는 순간 '멸균'은 아니므로 UV 살균기로 깨끗하게 유지")
    pump: str = "수족관 물갈이 펌프 (분당 5 L) — 채우기 · 배지 갈기"
    pump_ml_s: float = 80.0
    filter: str = "수족관 스펀지 여과기 + UV 살균기 — 떠다니는 GO · PVA 조각을 거르고 배지를 깨끗하게 (작업 사이에만 켬)"
    pads: str = "배양 받침의 흑연 패드 2장 (흑연 시트 또는 굵은 연필심) — 왼발 +, 오른발 −"
    probe: str = "배지 전도도 전극: 연필심 2개 (교류 1 kHz) — 염도가 떨어지면 배지를 갈 때"
    change_drop: float = 0.05  # 배지 염도가 5 % 넘게 떨어지면 갈기
    wall_u_w_m2k: float = 10.0  # 유리 벽 · 수면 → 방 공기 열전달 (자연대류, 가정)

    @property
    def area_mm2(self) -> float:
        return self.inner_mm[0] * self.inner_mm[1]

    @property
    def density(self) -> float:
        return solution_density(nacl_mm=self.saline_mm)

    def fill_ml(self, height_mm: float | None = None) -> float:
        return self.area_mm2 * (self.fill_mm if height_mm is None else height_mm) / 1000

    @property
    def nacl_g(self) -> float:
        return self.fill_ml() / 1000 * self.saline_mm / 1000 * 58.44

    def medium_after(self, ink_ml: float, ink_nacl_mm: float, removed_ml: float = 0.0) -> float:
        """잉크가 들어오고 깎은 젤을 빨아낸 뒤 배지 염도 (mM) — 잉크는 배지보다 묽음."""
        v0 = self.fill_ml()
        return (v0 * self.saline_mm + ink_ml * ink_nacl_mm - removed_ml * self.saline_mm) / (v0 + ink_ml - removed_ml)

    @property
    def heat_loss_w_k(self) -> float:
        """배지 → 방 공기 (네 벽 + 수면)."""
        x, y, _ = (v / 1000 for v in self.inner_mm)
        h = self.fill_mm / 1000
        return self.wall_u_w_m2k * (2 * (x + y) * h + x * y)


@dataclass
class Submersion:
    """기계까지 물속 — 젖는 쪽 비금속, 금속 · 전기는 방수 통 안."""

    wet: tuple[tuple[str, frozenset], ...] = (
        ("출력 부품 PETG", frozenset({"C", "H", "O"})),
        ("탄소섬유 봉 Ø8 (프레임 · XY 안내)", frozenset({"C", "H", "O", "N"})),
        ("나일론 나사봉 M8 (Z)", frozenset({"C", "H", "O", "N"})),
        ("유리섬유 심 GT2 벨트 (네오프렌)", frozenset({"C", "H", "Cl", "Si", "O"})),
        ("투명 실리콘 · O-링 (NBR)", frozenset({"Si", "O", "C", "H", "N"})),
        ("흑연 패드 · 연필심", frozenset({"C"})),
        ("PEEK 노즐 (펜 끝)", frozenset({"C", "H", "O"})),
    )
    pods: str = "모터 방수 통 8개 (PETG + O-링, 자석 커플링 — 축 구멍 없음) · 전자 방수 통 1개 · 카메라 방수 통 1개 (창)"
    coupling: str = "네오디뮴 자석 6개씩 두 원판 — 안쪽은 모터 축, 바깥쪽은 PETG 속에 묻혀 풀리를 돌림 (벽 3 mm)"
    tether: str = "방수 케이블 한 가닥 (24 V + 이더넷, 케이블 글랜드) → 배양조 밖 단자판 (BNC · SMA · USB · RJ45)"
    leak: str = "누설 감시: 배지 속 흑연 기준 전극 ↔ 전원 접지 사이 전류 > 50 µA 면 전원 차단"
    leak_limit_ua: float = 50.0
    motor_w: float = 0.35  # 모터 하나 평균 — 물속이라 부력이 짐을 받쳐 전류를 낮춤 (움직일 때 0.4 A, 멈추면 0.1 A)
    n_motors: int = 8
    electronics_w: float = 1.6  # 라즈베리파이 Zero 2 W + 제어 보드 (방수 통 → 배지로)
    led_w: float = 1.2 * 0.3  # 405 nm 빛 평균 (켜는 시간 30 %)

    @property
    def heat_w(self) -> float:
        return self.motor_w * self.n_motors + self.electronics_w + self.led_w

    def wet_metals(self) -> list[str]:
        from .materials import NONMETALS

        ok = NONMETALS | {"Na", "Cl"}  # 배지 자체의 이온
        return [name for name, els in self.wet if not els <= ok]


@dataclass
class Chamber:
    temp_c: float = ROOM_C
    note: str = "상온 25 ± 1 °C — 배지 속이라 마르지 않음 (덮개로 증발 · 먼지만 막음)"


@dataclass
class SculptorSpec:
    name: str = "SNSS 조각가 SC-1"
    build_mm: tuple[float, float, float] = (110.0, 110.0, 90.0)  # 높이: 너트 판이 방수 통 위 · XY 방수 통이 위 꼭짓점 아래 (layout · FreeCAD)
    frame_mm: tuple[float, float, float] = (330.0, 330.0, 300.0)  # 36 큐브 수조 안에 통째로
    frame: str = "RepRap 방식, 통째로 물속 — 출력한 PETG 꼭짓점 8개 + 탄소섬유 봉 Ø8 12개 (금속 없음)"
    kinematics: str = ("CoreXY (펜 XY, 탄소섬유 봉 + 출력 PETG 미끄럼 부싱) + Z (나일론 나사봉 M8 3개) — "
                       "모터는 방수 통 속 자석 커플링 · 허공 획은 XYZ 동시")
    print_speed_mm_s: float = 8.0
    stroke_speed_mm_s: float = 4.0
    travel_speed_mm_s: float = 60.0  # 물속이라 느리게 (물결이 작업물을 흔들지 않게)
    accel_mm_s2: float = 800.0
    layer_mm: float = 0.32
    line_mm: float = 0.41
    shrink_compensation: float = 0.03  # 숙성 중 젤 수축 (가정)
    cure_h: float = 6.0  # 다 빚은 뒤 배양(숙성): 도펀트 흡착 · 수소결합 안정 (상온, 배지 속)
    heal_min: float = 30.0  # 붙인 면이 원래 세기의 80 % 로 아무는 시간 (가정)
    pen: Pen = field(default_factory=Pen)
    tank: Tank = field(default_factory=Tank)
    sub: Submersion = field(default_factory=Submersion)
    chamber: Chamber = field(default_factory=Chamber)
    feeds: list[Feed] = field(default_factory=lambda: default_feeds())
    go_variants: list[GoVariant] = field(default_factory=lambda: default_go_variants())
    recipes: dict[str, Recipe] = field(default_factory=lambda: default_recipes())
    scanner: str = "레이저 선 프로파일러 (분해능 50 µm) — 작업물 겉면을 읽어 기억과 맞춤"
    firmware: str = "Klipper (Raspberry Pi Zero 2 W + BTT Octopus Pro, 스테퍼 8축 · 저전류) — 전자 방수 통 안"
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
        rho = solution_density(m["go_mg_ml"], m["nacl_mm"], m["pva_wt"] * 10)
        drho = rho - self.tank.density  # 배지와 밀도 차 (+ 면 가라앉으려 함)
        free = tau / (max(abs(drho), 1e-3) * G) * 1000
        return {**m, "ccc_mm": ccc, "label": PHASE_LABELS[rep.phase], "ok": ok, "yield_pa": tau,
                "density": rho, "drho": drho, "free_height_mm": free,
                "free_height_air_mm": tau / (rho * G) * 1000,
                "bath_gels": self.tank.saline_mm >= ccc,  # 덜 섞인 잉크도 배지에 닿으면 겉부터 엉김
                "drift_mm_min": abs(drho) * G * (self.line_mm / 1000) ** 2 / (18 * 0.89e-3) * 6e4}

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
            elif g["free_height_mm"] < self.build_mm[2]:
                bad.append(f"{r.name}: 식염수 속에서 {g['free_height_mm']:.0f} mm 까지만 섬 (< 출력 높이 {self.build_mm[2]:g} mm)")
            if not g["bath_gels"]:
                bad.append(f"{r.name}: 배지가 CCC 보다 묽어 겉이 엉기지 않음")
        if self.frame_mm[2] > self.tank.fill_mm - 10:
            bad.append(f"기계 높이 {self.frame_mm[2]:g} mm 가 배지 수면 {self.tank.fill_mm:g} mm 에 잠기지 않음")
        if max(self.frame_mm[:2]) > min(self.tank.inner_mm[:2]):
            bad.append("기계가 배양조보다 넓음")
        if self.heat_rise_k() > 1.0:
            bad.append(f"배지가 기계 열로 {self.heat_rise_k():.1f} K 오름 (> 1 K — 상온 유지 실패)")
        for name in self.sub.wet_metals():
            bad.append(f"젖는 부품에 금속: {name}")
        if self.build_mm[2] > self.tank.fill_mm - 5:
            bad.append(f"출력 높이 {self.build_mm[2]:g} mm 가 배지 수면 {self.tank.fill_mm:g} mm 에 너무 가까움")
        if self.residence_s() >= self.pen.gel_time_s:
            bad.append(f"혼합기 체류 {self.residence_s():.1f} s ≥ 젤화 {self.pen.gel_time_s:g} s — 펜 안에서 굳음")
        return bad

    def heat_rise_k(self) -> float:
        """기계 열(모터 · 전자 · 빛)이 배지로 → 정상 상태 온도 상승 = 열 / (벽 · 수면 열전달)."""
        return self.sub.heat_w / self.tank.heat_loss_w_k

    def describe(self) -> str:
        b, p, tk = self.build_mm, self.pen, self.tank
        lines = [f"[{self.name} — 3D 펜을 단 상온 3D 프린터]",
                 f"  출력 공간 {b[0]:g}×{b[1]:g}×{b[2]:g} mm · 프레임 {self.frame_mm[0]:g}×{self.frame_mm[1]:g}×{self.frame_mm[2]:g} mm",
                 f"  {self.frame}",
                 f"  {self.kinematics}",
                 f"  층 {self.layer_mm} mm · 선폭 {self.line_mm} mm · 쌓기 {self.print_speed_mm_s:g} mm/s · 허공 획 {self.stroke_speed_mm_s:g} mm/s",
                 f"  방: {self.chamber.note}",
                 f"  배양조 (기계까지 통째로 잠김): {tk.container} · 안 {tk.inner_mm[0]:g}×{tk.inner_mm[1]:g}×{tk.inner_mm[2]:g} mm",
                 f"    배지 = 멸균생리식염수 {tk.saline_mm:g} mM (밀도 {tk.density:.1f} kg/m³) · {tk.fill_mm:g} mm 가득 "
                 f"({tk.fill_ml() / 1000:.1f} L, NaCl {tk.nacl_g:.0f} g)",
                 f"    배지 마련: {tk.medium_src}",
                 f"    {tk.pump}", f"    {tk.filter}", f"    {tk.pads} — 받침째 들어 올려 수확", f"    {tk.probe}",
                 f"  물속 기계: {self.sub.pods}", f"    {self.sub.coupling}", f"    {self.sub.tether}", f"    {self.sub.leak}",
                 f"    젖는 쪽: " + " · ".join(n for n, _ in self.sub.wet) + (" — 금속 없음" if not self.sub.wet_metals() else ""),
                 f"    열: 기계 {self.sub.heat_w:.1f} W → 배지 +{self.heat_rise_k():.2f} K (벽 · 수면 {tk.heat_loss_w_k:.1f} W/K)",
                 f"  스캐너: {self.scanner}",
                 f"  [{p.name}] 노즐 {p.nozzle_mm} mm · {p.mixer} (부피 {p.dead_volume_ul:g} µL, 체류 {self.residence_s():.1f} s < 젤화 {p.gel_time_s:g} s)",
                 f"    빛: {p.light}", f"    물속: {p.seal}", f"    깎기: {p.carve} · {p.carve_rate_mm3_s:g} mm³/s", f"    {p.mount}",
                 "  원료 (따로 들어가 펜 끝에서 하나가 됨):"]
        for f in self.feeds:
            lines.append(f"    {f.name:<5} {f.stock} · 원소 {','.join(sorted(f.elements))}")
        lines.append("    GO 줄 선택 밸브: " + " · ".join(v.name for v in self.go_variants))
        lines.append("  재료 = 섞는 비율 GO : SNSS : PVA → 섞인 뒤 농도 → 굳음 판정:")
        for r in self.recipes.values():
            g = self.gel_check(r)
            lines.append(f"    {r.name:<12} {r.go:.2f} : {r.snss:.2f} : {r.pva:.2f} {'빛 켬' if r.light else '빛 끔'} → "
                         f"GO {g['go_mg_ml']:.1f} mg/mL · NaCl {g['nacl_mm']:.0f} mM (CCC {g['ccc_mm']:.0f}) · PVA {g['pva_wt']:.1f} % "
                         f"→ {'굳음' if g['ok'] else '안 굳음'} · 항복응력 약 {g['yield_pa']:.0f} Pa · 밀도 차 {g['drho']:+.1f} kg/m³ "
                         f"→ 식염수 속 {g['free_height_mm'] / 1000:.1f} m 까지 섬 (공기 중이면 {g['free_height_air_mm']:.1f} mm)")
        bad = self.check()
        lines.append("  설계 점검: " + ("통과" if not bad else "; ".join(bad)))
        lines += [f"  배양(숙성) {self.cure_h:g} h (상온 · 배지 속) · 붙인 면 아묾 {self.heal_min:g} 분 · 다 자라면 받침째 꺼냄",
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
        BomLine("원료", "생리식염수 0.9 % 1 L — 또는 정제수 40 L + 정제염 360 g", "40 L 분량",
                f"배지 — 배양조 {s.tank.fill_ml() / 1000:.0f} L (기계까지 잠김) + 펜 SNSS 줄", "약국 · 마트 (정제수 · 첨가물 없는 정제염)"),
        BomLine("원료", "PVA 세탁풀 / 슬라임용 PVA 풀", "500 mL", "폴리비닐알코올 — 붕사·향료 없는 것, 10 wt% 로 맞춤", "마트 · 문구점"),
        BomLine("원료", "그래핀 산화물(GO) 수분산", "100 mL", "10 mg/mL, 판 크기 5–20 µm", "온라인 (재료·시약 쇼핑몰)"),
        BomLine("원료", "폴리에틸렌이민 (PEI, 분지형)", "25 g", "n형 도펀트 — GO 통에 미리 흡착", "온라인 시약"),
        BomLine("원료", "4-니트로벤젠디아조늄 테트라플루오로붕산염 (NBD)", "5 g", "p형 도펀트 — 차광 보관", "온라인 시약"),
        # 소모품
        BomLine("소모품", "일회용 주사기 20 mL", "6개", "원료 3줄 + 예비 (물속에 그대로)", "약국"),
        BomLine("소모품", "PEEK 노즐 Ø0.41 (22G 상당, 루어)", "5개", "펜 노즐 — 스테인리스 바늘 대신 (물속 금속 없음)", "온라인 (HPLC · 디스펜싱 부품)"),
        BomLine("소모품", "실리콘 관 Ø1/Ø2 mm (수족관 에어호스 가는 것)", "3 m", "주사기 → 펜", "마트 (수족관 코너)"),
        BomLine("소모품", "PETG 필라멘트 1.75 mm", "2 kg", "출력 부품 (parts.py, 약 1.2 kg)", "온라인 · 전자상가"),
        # 배양조 — 기계까지 담그는 수조
        BomLine("배양조", "36 큐브 유리 수조 (안 350 × 350 × 350 mm)", "1개", "기계 전체가 잠기는 배양조", "마트 · 수족관"),
        BomLine("배양조", "수족관 물갈이 펌프 (분당 5 L)", "1개", s.tank.pump, "마트 (수족관 코너)"),
        BomLine("배양조", "수족관 스펀지 여과기 + UV 살균기", "각 1개", s.tank.filter, "마트 (수족관 코너)"),
        BomLine("배양조", "흑연 시트 0.5 mm (또는 굵은 연필심 2B)", "1장", s.tank.pads + " · " + s.tank.probe + " · 누설 기준 전극", "문구점 · 온라인"),
        # 물속 기계 — 젖는 쪽은 비금속
        BomLine("물속 기계", "탄소섬유 봉 Ø8 × 1 m", "5개", "프레임 12토막 + XY 안내봉 4토막 (금속 없음)", "낚시·연·모형 가게 · 온라인"),
        BomLine("물속 기계", "나일론 나사봉 M8 × 1 m + 나일론 너트", "1개 · 20개", "Z 3토막", "철물점"),
        BomLine("물속 기계", "GT2 벨트 6 mm (유리섬유 심, 쇠 심 아님) 2 m + 출력 풀리", "1식", "CoreXY", "온라인 · 전자상가"),
        BomLine("물속 기계", "투명 실리콘 실란트 (욕실용) · O-링 (NBR, Ø50 × 10 · Ø20 × 2)", "1개 · 12개", s.sub.pods + " · " + s.pen.seal, "철물점"),
        BomLine("물속 기계", "네오디뮴 자석 Ø10 × 3", "100개", s.sub.coupling + " · 펜 마운트", "문구점 · 온라인"),
        BomLine("물속 기계", "방수 케이블 (4심 전원 + 이더넷) 2 m · 케이블 글랜드 PG9", "1식", s.sub.tether, "전자상가 · 철물점"),
        # 방수 통 안 (금속 · 전기)
        BomLine("방수 통 안", "NEMA17 스테퍼 (얇은 것 23 mm)", "8개", "XY 2 · Z 3 · 원료 펌프 3 — 저전류", "온라인 · 전자상가"),
        BomLine("방수 통 안", "MG90S 서보", "3개", "핀치 밸브 (GO 통 선택)", "온라인 · 전자상가"),
        BomLine("방수 통 안", "Raspberry Pi Zero 2 W + BTT Octopus Pro (TMC2209 × 8)", "1식", "Klipper + 다리(interfaces.py) — 저전력", "온라인 · 전자상가"),
        BomLine("방수 통 안", "405 nm LED 3 W × 4 + 정전류 드라이버", "1식", "펜 끝 광환원 (실리콘으로 묻음)", "온라인 · 전자상가"),
        BomLine("방수 통 안", "레이저 선 모듈 + USB 카메라", "1식", "스캐너 (창 달린 방수 통)", "온라인 · 전자상가"),
        BomLine("방수 통 안", "누설 감시: 연산증폭기 + 릴레이 · 온도 센서 (DS18B20, 실리콘 속)", "1식", s.sub.leak, "온라인 · 전자상가"),
        # 배양조 밖 단자판
        BomLine("밖 단자판", "ADS1115 (ADC) · MCP4728 (DAC) · XTR115 (4–20 mA)", "각 1개", "아날로그 단자 A1–A8", "온라인 · 전자상가"),
        BomLine("밖 단자판", "BNC 판넬 잭 × 8 · SMA 판넬 잭 × 3", "1식", "아날로그 · 트리거 · 양자 동기 단자", "온라인 · 전자상가"),
        BomLine("밖 단자판", "74HC390 × 4 + 비교기 (10 MHz → 1 PPS 분주)", "1식", "양자 계측기 시간 동기 (Q1)", "온라인 · 전자상가"),
        BomLine("밖 단자판", "신호 릴레이 (DPDT)", "1개", "발 단자 ↔ 외부 충전원 A2 연결/분리", "온라인 · 전자상가"),
        BomLine("전원", "24 V 100 W 어댑터 (누전 차단 콘센트에)", "1개", "가열·냉각 장치 없음 (상온) — 방수 케이블로 물속 전자 통", "온라인 · 전자상가"),
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
            "[output_pin saline_pump]  # 배양조 정량 펌프 (약국 생리식염수 병 → 배양조)", "pin: PB10", "value: 0", "",
            "[gcode_macro FILL]", "description: 배양조에 배지(멸균생리식염수) ML 만큼 부음 (보정 mL/s)", "gcode:",
            "  SET_PIN PIN=saline_pump VALUE=1",
            f"  G4 P{{(params.ML|float / {s.tank.pump_ml_s:g} * 1000)|int}}",
            "  SET_PIN PIN=saline_pump VALUE=0", "",
            "[output_pin trig_layer]  # D3 TTL · Q3 LVTTL — 층·획·깎기 시작마다 뒤집힘 (움직임 큐와 동기)", "pin: PB11", "value: 0", "",
            "[output_pin charge_relay]  # A2 외부 충전원 ↔ 발 단자", "pin: PB12", "value: 0", "",
            "[gcode_macro TRIG]", "description: 트리거 출력 뒤집기 + 다리에 사건 알림 (시간 태거·카메라 동기)",
            "variable_level: 0", "gcode:",
            "  {% set v = 1 - printer['gcode_macro TRIG'].level %}",
            "  SET_PIN PIN=trig_layer VALUE={v}", "  SET_GCODE_VARIABLE MACRO=TRIG VARIABLE=level VALUE={v}",
            "  RESPOND PREFIX=snss MSG=\"TRIG {params.EVENT|default('layer')} {params.N|default(0)}\"", "",
            "[gcode_macro LEAK_CHECK]", "description: 물속 기계 누설 점검 — 다리가 A8 을 읽어 문턱을 넘으면 전원 차단", "gcode:",
            "  RESPOND PREFIX=snss MSG=\"LEAK_CHECK\"", "  G4 P500", "",
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
