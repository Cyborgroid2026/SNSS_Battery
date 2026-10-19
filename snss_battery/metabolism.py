"""대사 — 결정 안에서 에너지를 계속 만들어 내는 방법 (생물학적 요소 없음).

생명체도 에너지를 무(無)에서 만들지 않는다: 먹이를 태우거나 빛을 받는다. 이 결정의 '먹이'는
  1. 빛 (광합성형)      : 도메인 벽 속 금속 없는 광촉매(g-C3N4 등)가 빛을 받아 묽은→진한 쪽으로 이온을 퍼 올림
  2. 내장 연료 (소화형) : 진한 도메인 속 연료(포도당 등)가 금속 없는 탄소 촉매로 천천히 산화되며 이온을 만들고,
                          결정 아래면(연료 산화)·윗면(공기 산소 환원)이 연료전지처럼 반응 → 연속 전류 가능
  3. 증발 (호흡형)      : 윗면 증발로 생기는 전체 농도 기울기. CEM/AEM 이 번갈아 있어 거의 상쇄됨
  4. 레시피 반응물      : 함께 붓는 화학물이 반응하며 이온을 만드는 경우 (사용자가 값 입력)

모든 재생은 '쌍마다 내부 펌프 전류'(이온쌍/초 × F)로 농도차를 다시 만든다 → ArtificialCellStack.step(pump_a).
수치는 문헌 범위의 가정값이며, 실험으로 보정해야 한다.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

from .constants import FARADAY, thermal_voltage

PLANCK = 6.62607015e-34
LIGHT_SPEED = 2.99792458e8
ELEMENTARY = 1.602176634e-19


# ---------- 에너지원 ----------
@dataclass
class LightPump:
    enabled: bool = True
    irradiance_mw_cm2: float = 10.0  # 광촉매가 흡수하는 청색·근자외 대역 세기 (한낮 햇빛 ≈ 5~10, 실내 ≈ 0.05)
    wavelength_nm: float = 405.0
    quantum_efficiency: float = 1e-3  # 퍼 올린 이온쌍 / 흡수 광자 (가정)
    penetration_mm: float = 1.0  # 빛이 결정 옆면에서 들어가는 깊이
    day_hours: float = 12.0  # 하루 중 빛 있는 시간 (24 = 항상)

    def lit(self, t_s: float) -> bool:
        return self.enabled and (t_s / 3600.0) % 24.0 < self.day_hours

    def lit_area_cm2(self, bat) -> float:
        """한 쌍에서 빛을 받는 벽 면적 (옆면 띠)."""
        return math.pi * bat.gel_diameter_mm / 10 * min(self.penetration_mm, bat.gel_diameter_mm / 2) / 10

    def pump_a(self, bat) -> float:
        photon = PLANCK * LIGHT_SPEED / (self.wavelength_nm * 1e-9)
        flux = self.irradiance_mw_cm2 * 1e-3 / photon  # 광자/s/cm²
        return ELEMENTARY * flux * self.quantum_efficiency * self.lit_area_cm2(bat)


@dataclass
class FuelSupply:
    enabled: bool = True
    name: str = "포도당 (비효소 산화, 금속 없는 탄소 촉매)"
    conc_mm: float = 50.0  # 진한 도메인 속 연료 농도
    ions_per_molecule: float = 1.0  # 산화 1분자당 생기는 이온쌍
    rate_per_day: float = 0.3  # 1차 반응 속도 상수
    fuel_cell_contacts: bool = True  # 아래면 연료 산화 + 윗면 공기 산소 환원 (N-도핑 탄소)
    contact_asr_ohm_cm2: float = 30.0
    remaining: float = 1.0

    def pump_a(self, bat) -> float:
        if not self.enabled or self.remaining <= 0:
            return 0.0
        mol0 = self.conc_mm * 1e-3 * bat.stack.geometry.volume_l  # 쌍 하나(진한 도메인 1개)의 연료
        return self.ions_per_molecule * FARADAY * self.rate_per_day / 86400.0 * mol0 * self.remaining

    def consume(self, dt_s: float) -> None:
        if self.enabled:
            self.remaining *= math.exp(-self.rate_per_day * dt_s / 86400.0)


@dataclass
class Evaporation:
    enabled: bool = True
    evap_mm_per_h: float = 0.2
    salt_diffusivity_m2_s: float = 1.5e-9

    def emf_v(self, bat) -> float:
        """윗면 쪽으로 생기는 전체 기울기. 번갈아 놓인 CEM(+)·AEM(−) 기여가 서로 상쇄."""
        if not self.enabled:
            return 0.0
        s = bat.stack
        v = self.evap_mm_per_h * 1e-3 / 3600.0
        pe = v * bat.gel_height_mm * 1e-3 / self.salt_diffusivity_m2_s
        ratio = min(math.exp(min(pe, 50.0)), 6.1 / s.c0)
        vt = thermal_voltage(s.saline.temperature_c)
        return 0.5 * (s.cem.selectivity_at(s.c0) - s.aem.selectivity_at(s.c0)) * vt * math.log(ratio)


@dataclass
class RecipeReactant:
    enabled: bool = False
    name: str = "레시피 반응물 (입력 대기)"
    amount_mmol: float = 0.0  # 결정 전체에 넣은 양
    ions_per_reaction: float = 1.0
    rate_per_day: float = 0.0
    remaining: float = 1.0

    def pump_a(self, bat) -> float:
        if not self.enabled or self.remaining <= 0:
            return 0.0
        mol_pair = self.amount_mmol * 1e-3 / bat.stack.n_pairs
        return self.ions_per_reaction * FARADAY * self.rate_per_day / 86400.0 * mol_pair * self.remaining

    def consume(self, dt_s: float) -> None:
        if self.enabled:
            self.remaining *= math.exp(-self.rate_per_day * dt_s / 86400.0)


@dataclass
class Metabolism:
    light: LightPump = field(default_factory=LightPump)
    fuel: FuelSupply = field(default_factory=FuelSupply)
    evaporation: Evaporation = field(default_factory=Evaporation)
    reactant: RecipeReactant = field(default_factory=RecipeReactant)

    def attach(self, bat) -> None:
        s = bat.stack
        s.faradaic_contacts = self.fuel.enabled and self.fuel.fuel_cell_contacts
        s.contact_asr_ohm_cm2 = self.fuel.contact_asr_ohm_cm2 if s.faradaic_contacts else 0.0
        s.extra_emf_v = self.evaporation.emf_v(bat)

    def pump_a(self, bat, t_s: float) -> float:
        return ((self.light.pump_a(bat) if self.light.lit(t_s) else 0.0)
                + self.fuel.pump_a(bat) + self.reactant.pump_a(bat))

    def consume(self, dt_s: float) -> None:
        self.fuel.consume(dt_s)
        self.reactant.consume(dt_s)

    def power_budget_w(self, bat) -> dict[str, float]:
        """각 먹이가 만드는 화학(농도차) 전력 = 펌프 전류 × 이온 기전력 (쌍 전체)."""
        e_ion = bat.stack.n_pairs * bat.stack.membrane_potential_pair()
        return {
            "빛 (광합성형, 낮 동안)": self.light.pump_a(bat) * e_ion if self.light.enabled else 0.0,
            "내장 연료 (소화형, 시작 시)": self.fuel.pump_a(bat) * e_ion,
            "증발 (호흡형)": abs(self.evaporation.emf_v(bat)) * 1e-3 if self.evaporation.enabled else 0.0,
            "레시피 반응물": self.reactant.pump_a(bat) * e_ion,
        }


# ---------- 부하 ----------
@dataclass
class LED:
    name: str = "빨강 LED + 470 Ω"
    vf_v: float = 1.85  # 1 mA 에서의 순방향 전압
    ideality: float = 2.0
    visible_a: float = 20e-6  # 어두운 곳에서 희미하게 보임
    clear_a: float = 0.5e-3  # 밝은 방에서도 또렷
    series_ohm: float = 470.0  # LED 보호 저항 (없으면 처음 순간 수십 mA 로 LED 손상)

    def diode_voltage(self, i: float) -> float:
        nvt = self.ideality * 0.025693
        i_s = 1e-3 / math.exp(self.vf_v / nvt)
        return nvt * math.log(max(i, 0.0) / i_s + 1.0)

    def voltage(self, i: float) -> float:
        return self.diode_voltage(i) + self.series_ohm * i

    def label(self, i: float) -> str:
        if i >= self.clear_a:
            return "또렷하게 켜짐"
        if i >= self.visible_a:
            return "희미하게 켜짐 (어두운 곳)"
        return "꺼짐"

    def lit(self, i: float) -> bool:
        return i >= self.visible_a


@dataclass
class IncandescentBulb:
    name: str = "백열 꼬마전구 2.5 V 0.3 A"
    rated_v: float = 2.5
    rated_a: float = 0.3
    cold_ratio: float = 0.1  # 차가운 필라멘트 저항 / 뜨거운 저항
    glow_fraction: float = 0.15  # 정격 전력의 이 비율 이상이면 붉게 빛남

    @property
    def rated_w(self) -> float:
        return self.rated_v * self.rated_a

    def resistance(self, i: float) -> float:
        r_hot = self.rated_v / self.rated_a
        r = r_hot * self.cold_ratio
        for _ in range(30):  # 필라멘트 온도(전력)에 따른 저항
            p = i * i * r
            r = r_hot * (self.cold_ratio + (1 - self.cold_ratio) * min(p / self.rated_w, 1.5) ** 0.6)
        return r

    def voltage(self, i: float) -> float:
        return i * self.resistance(i)

    def label(self, i: float) -> str:
        p = i * self.voltage(i)
        if p >= 0.6 * self.rated_w:
            return "밝게 켜짐"
        if p >= self.glow_fraction * self.rated_w:
            return "붉게 빛남"
        return "꺼짐"

    def lit(self, i: float) -> bool:
        return i * self.voltage(i) >= self.glow_fraction * self.rated_w


def operating_current(ocv: float, r_int: float, load) -> float:
    """OCV − I·R = V_load(I) 의 해 (이분법)."""
    if ocv <= 0:
        return 0.0
    lo, hi = 0.0, ocv / r_int
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if ocv - mid * r_int - load.voltage(mid) > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------- 시뮬레이션 ----------
@dataclass
class LoadPoint:
    time_h: float
    current_a: float
    load_v: float
    power_w: float
    lit_source: bool  # 빛이 비추는 중
    state: str
    ocv_v: float
    soc: float
    fuel_left: float


@dataclass
class LoadRun:
    load_name: str
    parallel: int
    points: list[LoadPoint]

    def on_fraction(self) -> float:
        return sum(p.state != "꺼짐" for p in self.points) / max(len(self.points), 1)

    def first_off_h(self) -> float | None:
        for p in self.points:
            if p.state == "꺼짐":
                return p.time_h
        return None

    def peak_power_w(self) -> float:
        return max((p.power_w for p in self.points), default=0.0)


def simulate(battery, metabolism: Metabolism, load, hours: float = 48.0, dt_s: float = 60.0,
             parallel: int = 1, record_every: int = 1) -> LoadRun:
    """결정을 parallel 조각으로 잘라 병렬 연결(전압 1/k, 저항 1/k²)한 뒤 부하를 계속 연결."""
    bat = copy.deepcopy(battery)
    met = copy.deepcopy(metabolism)
    met.attach(bat)
    s = bat.stack
    k = max(1, parallel)
    pts = []
    steps = int(hours * 3600 / dt_s)
    for n in range(steps + 1):
        t = n * dt_s
        ocv, r = s.open_circuit_voltage() / k, s.internal_resistance() / k ** 2
        i = operating_current(ocv, r, load)
        if n % record_every == 0:
            v = load.voltage(i)
            pts.append(LoadPoint(t / 3600, i, v, i * v, met.light.lit(t), load.label(i), ocv, s.state_of_charge,
                                 met.fuel.remaining))
        s.step(i / k, dt_s, met.pump_a(bat, t))
        met.consume(dt_s)
    return LoadRun(load.name, k, pts)


def best_parallel(battery, metabolism: Metabolism, load, max_k: int = 64) -> int:
    """부하 전력이 최대가 되는 병렬 분할 수."""
    bat = copy.deepcopy(battery)
    met = copy.deepcopy(metabolism)
    met.attach(bat)
    s = bat.stack
    best, best_p = 1, -1.0
    for k in range(1, min(max_k, s.n_pairs) + 1):
        i = operating_current(s.open_circuit_voltage() / k, s.internal_resistance() / k ** 2, load)
        p = i * load.voltage(i)
        if p > best_p:
            best, best_p = k, p
    return best


@dataclass
class LightingVerdict:
    led: LoadRun
    bulb: LoadRun
    budget_w: dict
    led_need_w: float
    bulb_need_w: float
    lines: list[str]

    def describe(self) -> str:
        return "\n".join(self.lines)


def evaluate_lighting(battery, metabolism: Metabolism | None = None, hours: float = 168.0) -> LightingVerdict:
    met = metabolism or Metabolism()
    led, bulb = LED(), IncandescentBulb()
    led_run = simulate(battery, met, led, hours=hours, dt_s=60.0, record_every=10)
    k = best_parallel(battery, met, bulb)
    bulb_run = simulate(battery, met, bulb, hours=2.0, dt_s=2.0, parallel=k, record_every=15)
    bat = copy.deepcopy(battery)
    met.attach(bat)
    budget = met.power_budget_w(bat)
    led_need = led.visible_a * led.voltage(led.visible_a)
    bulb_need = bulb.glow_fraction * bulb.rated_w
    sustain = budget["빛 (광합성형, 낮 동안)"] + budget["내장 연료 (소화형, 시작 시)"] + budget["레시피 반응물"]

    lines = ["[먹이(대사)별 화학 전력]"]
    for name, w in budget.items():
        lines.append(f"  {name:<22} {w * 1000:9.3f} mW")
    lines.append(f"  합계(증발 제외)          {sustain * 1000:9.3f} mW")
    lines.append("")
    on = led_run.on_fraction()
    last_day = [p for p in led_run.points if p.time_h >= hours - 24]
    lit_on = [p for p in last_day if p.lit_source]
    dark_on = [p for p in last_day if not p.lit_source]

    def frac(ps):
        return sum(p.state != "꺼짐" for p in ps) / max(len(ps), 1)

    lines.append(f"[LED] {led.name}: 희미하게 보이려면 {led_need * 1e6:.0f} µW, 또렷하려면 "
                 f"{led.clear_a * led.voltage(led.clear_a) * 1000:.2f} mW (보호 저항 손실 포함)")
    lines.append(f"  연결 직후 전류 {led_run.points[0].current_a * 1000:.1f} mA (보호 저항 덕분에 20 mA 이하)")
    lines.append(f"  {hours:g}시간 동안 켜져 있던 비율 {on * 100:.0f} % · 마지막 하루: 빛 있을 때 {frac(lit_on) * 100:.0f} %, "
                 f"어두울 때 {frac(dark_on) * 100:.0f} %")
    if lit_on:
        avg = sum(p.current_a for p in lit_on) / len(lit_on)
        lines.append(f"  빛 있을 때 평균 전류 {avg * 1e6:.1f} µA → {led.label(avg)}")
    off = led_run.first_off_h()
    lines.append(f"  처음 꺼지는 시각: {'꺼지지 않음' if off is None else f'{off:.1f} h'}")
    lines.append("")
    lines.append(f"[꼬마전구] {bulb.name}: 붉게라도 빛나려면 {bulb_need * 1000:.0f} mW 필요")
    lines.append(f"  결정을 {k}조각으로 잘라 병렬 연결할 때 최대 {bulb_run.peak_power_w() * 1000:.1f} mW → "
                 f"{bulb.label(bulb_run.points[0].current_a)} (시작 순간)")
    off_b = bulb_run.first_off_h()
    lines.append(f"  붉게 빛나는 시간: {'2시간 이상' if off_b is None else f'{off_b * 60:.1f} 분'} (결정화 때 저장된 농도차로)")
    lines.append(f"  지속 가능 여부: 대사 전력 {sustain * 1000:.3f} mW ≪ 필요 {bulb_need * 1000:.0f} mW → "
                 f"{'지속 가능' if sustain >= bulb_need else '지속 불가 (저장분으로만 잠깐)'}")
    if sustain > 0:
        lines.append(f"  지속 점등에 필요한 대사 전력 배수: ×{bulb_need / sustain:,.0f}")
    return LightingVerdict(led_run, bulb_run, budget, led_need, bulb_need, lines)
