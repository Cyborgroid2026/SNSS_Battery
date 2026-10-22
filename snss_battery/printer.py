"""SNSS QFP-1 — 양자 설계 동결 프린터 (Quantum Freeze Printer) 기계 명세 (명세: spec/PRINTER.md).

모양과 구조만 주면 하나의 존재(Energetic Being)가 되도록 빚는 기계. 출력물(존재)은 금속 무함유,
기계 자체는 일반 3D 프린터처럼 금속 부품(모터·프레임)을 씀.

- 차가운 판(−30 °C) 위에 물 기반 잉크를 한 층씩 짜서 바로 얼림 (동결 프린팅) — 얼음이 형상을 붙잡아 줌
- 헤드 4개: T0 + 미로(GO + 붕산 → B 도핑 p형), T1 − 미로(GO + 요소 → N 도핑 n형), T2 분리막·피부(실리카), T3 지지 얼음(물)
- T0·T1 은 주사기 2개 혼합 헤드 — 섞는 비율로 도핑량(= 페르미 준위)을 층마다 프로그래밍 (qcap 모델)
- 펌웨어 Klipper: 매크로로 혼합비·차가운 판 온도를 G-code 에서 바꿈
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

RHO_WATER = 1000.0  # kg/m³ (잉크 ≈ 물)
LATENT = 334e3  # J/kg 얼음 융해열
CP_WATER = 4186.0
K_ICE = 2.2  # W/m·K (−10 °C 근처 얼음)


@dataclass
class Syringe:
    content: str
    volume_ml: float = 10.0
    inner_d_mm: float = 14.5  # 10 mL 일회용 주사기 안지름
    lead_mm: float = 2.0  # 플런저를 미는 T8 리드스크루 한 바퀴 이동

    @property
    def area_mm2(self) -> float:
        return math.pi * (self.inner_d_mm / 2) ** 2

    def plunger_mm(self, volume_mm3: float) -> float:
        return volume_mm3 / self.area_mm2

    @property
    def steps_per_mm(self) -> float:
        return 200 * 16 / self.lead_mm  # 1.8° 스테퍼, 16 마이크로스텝


@dataclass
class Head:
    tool: int
    name: str
    role: str  # pos · neg · sep · sup
    nozzle_mm: float
    syringes: list[Syringe]
    offset_xy: tuple[float, float]  # T0 노즐 기준
    elements: frozenset[str]
    dopant: str = ""  # 혼합 주사기가 넣는 도펀트
    max_doping_at: float = 0.0  # 도펀트 주사기 100 % 일 때 소성 후 도핑량 (보정값)

    @property
    def mixing(self) -> bool:
        return len(self.syringes) > 1


@dataclass
class ColdPlate:
    size_mm: float = 130.0
    plate: str = "알루미늄 6061 6 mm + PEI 0.2 mm 필름 (잉크가 얼어붙는 면)"
    tec: str = "TEC1-12706 펠티어 4장 (2×2) + 수냉 블록 + 냉각기 (에틸렌글리콜 5 °C)"
    target_c: float = -30.0
    contact_resistance_m2k_w: float = 2e-3  # 판 → 첫 얼음층 접촉 열저항


@dataclass
class Chamber:
    temp_c: float = 4.0  # 프린터를 +4 °C 저온실에 둠 (RECIPE 와 같은 방)
    purge: str = "건조 질소 0.5 L/min — 이슬점 < −35 °C 로 성에 방지"
    h_conv_w_m2k: float = 8.0  # 차가운 얼음 윗면으로 들어오는 자연대류


@dataclass
class PrinterSpec:
    name: str = "SNSS QFP-1 (Quantum Freeze Printer)"
    build_mm: tuple[float, float, float] = (120.0, 120.0, 110.0)
    frame_mm: tuple[float, float, float] = (420.0, 420.0, 540.0)
    kinematics: str = "CoreXY (헤드 XY) + 침대 Z (T8 리드스크루 3개, 자동 수평)"
    print_speed_mm_s: float = 10.0  # 점성 잉크
    travel_speed_mm_s: float = 120.0
    accel_mm_s2: float = 1500.0
    z_lift_mm: float = 1.0  # 쓰지 않는 노즐은 서보로 들어올림
    layer_mm: float = 0.32  # 노즐 0.41 mm 의 약 80 %
    line_mm: float = 0.41
    shrink_compensation: float = 0.15  # 동결건조 + 소성 선수축 → 그만큼 크게 출력
    plate: ColdPlate = field(default_factory=ColdPlate)
    chamber: Chamber = field(default_factory=Chamber)
    heads: list[Head] = field(default_factory=lambda: default_heads())
    firmware: str = "Klipper (Raspberry Pi 5 + BTT Octopus Pro, 스테퍼 8축)"

    def head(self, role: str) -> Head:
        return next(h for h in self.heads if h.role == role)

    # ---------- 동결 속도 (프린터가 지켜야 할 박자) ----------
    def freeze_flux_w_m2(self, height_mm: float, ink_c: float = 4.0) -> float:
        """높이 H 에서 막 올린 층을 얼리는 순열류: 얼음 기둥 전도 − 방 공기 대류."""
        r = self.plate.contact_resistance_m2k_w + height_mm / 1000 / K_ICE
        return (0 - self.plate.target_c) / r - self.chamber.h_conv_w_m2k * (self.chamber.temp_c - 0)

    def freeze_time_s(self, height_mm: float, layer_mm: float | None = None, ink_c: float = 4.0) -> float:
        """한 층(두께 layer)을 다 얼리는 데 걸리는 시간 (준정상 1차원, 스테판)."""
        d = (layer_mm or self.layer_mm) / 1000
        q = self.freeze_flux_w_m2(height_mm + (layer_mm or self.layer_mm) / 2, ink_c)
        if q <= 0:
            return math.inf
        return RHO_WATER * (LATENT + CP_WATER * ink_c) * d / q

    @property
    def max_height_mm(self) -> float:
        """얼음 기둥이 더 이상 위층을 얼리지 못하는 높이."""
        q_conv = self.chamber.h_conv_w_m2k * self.chamber.temp_c
        if q_conv <= 0:
            return math.inf
        return (-self.plate.target_c / q_conv - self.plate.contact_resistance_m2k_w) * K_ICE * 1000

    def freeze_front_um_s(self, height_mm: float) -> float:
        """얼음 전선 속도 — 얼음 결정(기공) 크기를 정함 (빠를수록 기공이 작음)."""
        return self.layer_mm * 1000 / self.freeze_time_s(height_mm)

    # ---------- 압출 ----------
    def flow_mm3_s(self) -> float:
        return self.line_mm * self.layer_mm * self.print_speed_mm_s

    def plunger_speed_mm_min(self, head: Head) -> float:
        return head.syringes[0].plunger_mm(self.flow_mm3_s()) * 60

    def describe(self) -> str:
        b = self.build_mm
        lines = [f"[{self.name}]",
                 f"  출력 공간 {b[0]:g}×{b[1]:g}×{b[2]:g} mm · 프레임 {self.frame_mm[0]:g}×{self.frame_mm[1]:g}×{self.frame_mm[2]:g} mm",
                 f"  {self.kinematics}",
                 f"  층 {self.layer_mm} mm · 선폭 {self.line_mm} mm · 출력 {self.print_speed_mm_s:g} mm/s · 이동 {self.travel_speed_mm_s:g} mm/s",
                 f"  차가운 판 {self.plate.target_c:g} °C ({self.plate.tec})",
                 f"  방 {self.chamber.temp_c:g} °C · {self.chamber.purge}",
                 f"  수축 보정 ×{1 / (1 - self.shrink_compensation):.3f} (소성 선수축 {self.shrink_compensation * 100:.0f} %)",
                 f"  펌웨어 {self.firmware}", "  헤드:"]
        for h in self.heads:
            mix = " + ".join(s.content for s in h.syringes)
            dop = f" · 도핑 최대 {h.dopant} {h.max_doping_at:g} at%" if h.dopant else ""
            lines.append(f"    T{h.tool} {h.name:<12} 노즐 {h.nozzle_mm} mm · {mix}{dop} · 원소 {','.join(sorted(h.elements))}")
        lines.append("  동결 박자 (층 하나 얼리는 시간):")
        for z in (0, 20, 40, 70, 100):
            lines.append(f"    높이 {z:>3} mm: {self.freeze_time_s(z):6.1f} s · 얼음 전선 {self.freeze_front_um_s(z):5.1f} µm/s")
        lines.append(f"  얼릴 수 있는 최대 높이 약 {self.max_height_mm:.0f} mm (방 공기 대류와 균형)")
        lines.append(f"  주사기 플런저 속도 {self.plunger_speed_mm_min(self.heads[0]):.3f} mm/min "
                     f"({self.heads[0].syringes[0].steps_per_mm:g} step/mm)")
        return "\n".join(lines)


def default_heads() -> list[Head]:
    go = "GO 20 mg/mL"
    return [
        Head(0, "+ 미로", "pos", 0.41, [Syringe(go), Syringe(go + " + 붕산 0.5 M")], (0.0, 0.0),
             frozenset({"C", "H", "O", "B"}), "B", 4.0),
        Head(1, "− 미로", "neg", 0.41, [Syringe(go), Syringe(go + " + 요소 1 M")], (30.0, 0.0),
             frozenset({"C", "H", "O", "N"}), "N", 4.0),
        Head(2, "분리막·피부", "sep", 0.41, [Syringe("흄드 실리카 15 wt% + PVA 1 wt%")], (0.0, 30.0),
             frozenset({"Si", "O", "C", "H"})),
        Head(3, "지지 얼음", "sup", 0.61, [Syringe("정제수 + 잔탄검 0.5 wt%")], (30.0, 30.0),
             frozenset({"H", "O", "C"})),
    ]


@dataclass
class BomLine:
    group: str
    part: str
    qty: str
    spec: str


def bom(spec: PrinterSpec | None = None) -> list[BomLine]:
    s = spec or PrinterSpec()
    n_syr = sum(len(h.syringes) for h in s.heads)
    return [
        BomLine("프레임", "알루미늄 2020 압출재", "12개", f"{s.frame_mm[0]:g}/{s.frame_mm[1]:g}/{s.frame_mm[2]:g} mm 각 4개"),
        BomLine("프레임", "폴리카보네이트 덮개 (이중창)", "1식", "단열 + 질소 퍼지 밀폐, 앞문 경첩"),
        BomLine("동작", "NEMA17 스테퍼 (XY CoreXY)", "2개", "0.9°, 2 A"),
        BomLine("동작", "NEMA17 스테퍼 + T8 리드스크루 (Z)", "3개", "자동 수평 (Z_TILT)"),
        BomLine("동작", "MGN12 리니어 레일", "3개", "X 1, Y 2"),
        BomLine("압출", "주사기 펌프 (NEMA14 + T8 2 mm 리드)", f"{n_syr}개", "헤드 위 직결, 10 mL 일회용 주사기"),
        BomLine("압출", "정적 혼합기 (나선형, 6 요소)", "2개", "T0·T1 두 잉크 혼합"),
        BomLine("압출", "노즐 (스테인리스 블런트)", "4개", "22G 0.41 mm ×3, 20G 0.61 mm ×1"),
        BomLine("압출", "노즐 리프트 서보 (MG90S)", "4개", f"쓰지 않는 노즐 {s.z_lift_mm} mm 들어올림"),
        BomLine("냉각", "펠티어 TEC1-12706", "4개", "2×2, 12 V 6 A"),
        BomLine("냉각", "수냉 블록 + 냉각기", "1식", "글리콜 5 °C, 펌프·라디에이터"),
        BomLine("냉각", "차가운 판", "1개", s.plate.plate),
        BomLine("냉각", "NTC 100k 서미스터", "3개", "판 2 + 방 1"),
        BomLine("환경", "습도·이슬점 센서 (SHT45)", "1개", "질소 퍼지 제어"),
        BomLine("환경", "질소 유량계 + 솔레노이드 밸브", "1식", s.chamber.purge),
        BomLine("제어", "Raspberry Pi 5 + BTT Octopus Pro", "1식", "Klipper, TMC2209 ×8"),
        BomLine("제어", "카메라 (층 감시)", "1개", "층마다 사진 → 얼음 전선 확인"),
        BomLine("전원", "24 V 350 W + 12 V 30 A (펠티어)", "각 1개", ""),
    ]


def klipper_cfg(spec: PrinterSpec | None = None) -> str:
    """Klipper printer.cfg 의 프린터 고유 부분 (핀 이름은 보드에 맞게 바꿈).

    E 는 부피(mm³): 가상 [extruder] 축 1 mm = 잉크 1 mm³. 주사기마다 extruder_stepper 를 두고
    rotation_distance = 리드 × 단면적 / 몫 으로 맞춰 가상 축에 동기화한다 → 혼합비 = 몫.
    """
    s = spec or PrinterSpec()
    syr = [(h, j, sy) for h in s.heads for j, sy in enumerate(h.syringes)]
    out = [f"# {s.name} — Klipper 설정 (프린터 고유 부분)",
           "# 스테퍼 12축: XY 2 + Z 3 + 주사기 " + str(len(syr)) + " + 가상 E 1 → Octopus Pro(8) + SKR Pico(4, 두 번째 MCU 'pico')",
           "# 핀 이름은 예시. 실제 배선에 맞게 고칠 것.", "",
           "[printer]", "kinematics: corexy", f"max_velocity: {s.travel_speed_mm_s:g}", f"max_accel: {s.accel_mm_s2:g}",
           "max_z_velocity: 5", "", "[z_tilt]", "z_positions: -10,-10 | 130,-10 | 60,140",
           "points: 10,10 | 110,10 | 60,110", "",
           "[extruder]  # 가상 부피 축 — 모터는 연결하지 않음 (빈 드라이버)",
           "step_pin: pico:gpio14", "dir_pin: pico:gpio13", "enable_pin: !pico:gpio15",
           "microsteps: 16", "rotation_distance: 40  # E 1 = 1 mm³ 로 쓰므로 값 자체는 무관",
           f"nozzle_diameter: {s.line_mm}", "filament_diameter: 1.1284  # 단면적 1 mm² → E(mm) = 부피(mm³)",
           "max_extrude_cross_section: 5", "heater_pin: pico:gpio23  # 히터 없음 (자리만)",
           "sensor_type: temperature_host", "control: watermark", "min_temp: -50", "max_temp: 60",
           "min_extrude_temp: -50", ""]
    for h, j, sy in syr:
        out += [f"[extruder_stepper syr_t{h.tool}_{j}]  # T{h.tool} {h.name} · {sy.content}",
                f"step_pin: PLACEHOLDER_T{h.tool}_{j}_STEP", f"dir_pin: PLACEHOLDER_T{h.tool}_{j}_DIR",
                f"microsteps: 16", f"rotation_distance: {sy.lead_mm * sy.area_mm2:.4f}  # 리드 {sy.lead_mm} mm × 단면적 {sy.area_mm2:.2f} mm²", ""]
    plate = s.plate
    out += ["[heater_generic cold_plate]  # 펠티어 냉각 — 출력이 클수록 차가워지므로 제어 반전",
            "heater_pin: !PA2", "sensor_type: Generic 3950", "sensor_pin: PF4", "control: pid",
            "pid_Kp: 40", "pid_Ki: 1.5", "pid_Kd: 200", "min_temp: -45", "max_temp: 40", "",
            "[temperature_sensor chamber]", "sensor_type: Generic 3950", "sensor_pin: PF5", "",
            "[gcode_macro _MIX]",
            "variable_ratio: {" + ", ".join(f"'{h.tool}': 0.0" for h in s.heads if h.mixing) + "}",
            "variable_tool: -1", "gcode:", "", ""]
    for h in s.heads:
        out += [f"[servo lift{h.tool}]", f"pin: PLACEHOLDER_SERVO{h.tool}", "initial_angle: 90", ""]
    out += ["[gcode_macro SET_MIX]",
            "description: 혼합 헤드의 도펀트 주사기 몫 (0~1). 소성 후 도핑량 = RATIO × 최대 at%",
            "gcode:", "  {% set r = printer['gcode_macro _MIX'].ratio %}",
            "  {% set _ = r.update({params.TOOL: params.RATIO|float}) %}",
            "  SET_GCODE_VARIABLE MACRO=_MIX VARIABLE=ratio VALUE=\"{r}\"",
            "  {% if printer['gcode_macro _MIX'].tool|string == params.TOOL %}_SYNC TOOL={params.TOOL}{% endif %}", "",
            "[gcode_macro _UNSYNC_ALL]", "gcode:"]
    out += [f"  SYNC_EXTRUDER_MOTION EXTRUDER=syr_t{h.tool}_{j} MOTION_QUEUE=" for h, j, _ in syr] + [""]
    out += ["[gcode_macro _SYNC]", "gcode:", "  {% set t = params.TOOL|int %}", "  _UNSYNC_ALL"]
    for h in s.heads:
        out.append(f"  {{% if t == {h.tool} %}}")
        if h.mixing:
            out.append(f"    {{% set r = printer['gcode_macro _MIX'].ratio['{h.tool}']|float %}}")
            for j, sy in enumerate(h.syringes):
                share = "(1 - r)" if j == 0 else "r"
                out += [f"    {{% if {share} > 0.001 %}}",
                        f"      SET_EXTRUDER_ROTATION_DISTANCE EXTRUDER=syr_t{h.tool}_{j} DISTANCE={{{sy.lead_mm * sy.area_mm2:.4f} / {share}}}",
                        f"      SYNC_EXTRUDER_MOTION EXTRUDER=syr_t{h.tool}_{j} MOTION_QUEUE=extruder", "    {% endif %}"]
        else:
            out.append(f"    SYNC_EXTRUDER_MOTION EXTRUDER=syr_t{h.tool}_0 MOTION_QUEUE=extruder")
        out.append("  {% endif %}")
    out += ["  SET_GCODE_VARIABLE MACRO=_MIX VARIABLE=tool VALUE={t}", "",
            "[gcode_macro COLD_PLATE]", "description: 차가운 판 목표 온도로 내리고 도달할 때까지 기다림", "gcode:",
            f"  {{% set t = params.TARGET|default({plate.target_c:g})|float %}}",
            "  SET_HEATER_TEMPERATURE HEATER=cold_plate TARGET={t}",
            "  TEMPERATURE_WAIT SENSOR='heater_generic cold_plate' MAXIMUM={t + 1}", "",
            "[gcode_macro FREEZE_WAIT]", "description: 방금 올린 층이 다 얼 때까지 기다림 (슬라이서가 계산한 초)",
            "gcode:", "  G4 P{(params.S|float * 1000)|int}", "",
            "[gcode_macro NOZZLES_UP]", "gcode:"] + [f"  SET_SERVO SERVO=lift{h.tool} ANGLE=90" for h in s.heads] + [""]
    for h in s.heads:
        out += [f"[gcode_macro T{h.tool}]", f"description: {h.name} 헤드로 바꿈", "gcode:", "  G91", f"  G1 Z{s.z_lift_mm:g} F600", "  G90",
                "  NOZZLES_UP", f"  SET_GCODE_OFFSET X={-h.offset_xy[0]:g} Y={-h.offset_xy[1]:g}",
                f"  SET_SERVO SERVO=lift{h.tool} ANGLE=0", f"  _SYNC TOOL={h.tool}",
                "  G91", f"  G1 Z-{s.z_lift_mm:g} F600", "  G90", ""]
    return "\n".join(out)
