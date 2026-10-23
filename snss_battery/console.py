"""수조 콘솔 — 수조 밑에 붙는 방수 데스크톱 + IP68 키보드 · 마우스 = 'HW 뷰포트' (명세: spec/CONSOLE.md).

Blender 화면에서 키보드 · 마우스로 설계 대상을 돌려 보고 · 옮겨 보고 · 골라 살피듯, 같은 키 · 마우스로
**수조(배지) 속에 실제로 맺힌 존재**를 살핀다. 화면 속 카메라가 도는 대신, 기계가 존재를 돌리고(회전 받침) · 올리고 내리고(받침 Z) ·
골라 비춘다(보기 빛, 굳지 않는 630 nm). 수조가 모니터이고, 데스크톱은 그 모니터 밑에 붙은 본체다.

좌표: 수조 안 바닥 = z 0 (layout 과 같음). 유리 바닥 6 mm → 수조 바깥 바닥 z −6.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Desktop:
    """수조 바로 밑에 붙는 방수 데스크톱 (팬 없는 밀폐 본체). 위에서 아래로: 수조 받침 테 → XPS 단열 → 본체 → 다리."""

    footprint_mm: tuple[float, float] = (358.0, 358.0)  # = 수조 바깥 (안 350 + 유리 4 × 2)
    tray_mm: float = 12.0  # 수조 받침 테: EPDM 패킹 + PETG 테 (수조가 미끄러지지 않고, 새는 물은 앞 홈으로)
    insulation_mm: float = 30.0  # XPS — 본체 열이 배지로 가지 않게 (lightsculpt.Desktop 과 같음)
    body_h_mm: float = 110.0  # 밀폐 본체 (IP67, 팬 없음)
    fin_mm: float = 18.0  # 양 옆 방열 핀 (방 공기로)
    feet_mm: float = 25.0
    rating: str = "IP67 밀폐 · 팬 없음 (양 옆 방열 핀) · 앞판 IP67 M12 · USB-C 단자 · 뒤 방수 케이블 (프로젝터 HDMI · Z · 전극)"
    pc: str = ("양자 아날로그 데스크톱 — 계산하지 않음: SD / microSD 에 구워 온 아날로그 제어 전압(CV) 표를 양자 기준 시계(10 MHz → 1 PPS)에 맞춰 "
               "DAC 로 내보내고, 구워 온 화면을 모니터에 띄움 (굽기 · 설계 · 시뮬레이션은 지금 컴퓨터)")
    pc_w: float = 25.0
    slots: tuple[str, ...] = ("SD (SDXC, 앞판 왼쪽 · 방수 덮개)", "microSD (앞판 오른쪽 · 방수 덮개)")
    monitors: tuple[tuple[str, str], ...] = (
        ("모니터 1 — 지금 단계", "SD 의 monitors/step_NN.png — 그 단계까지 자란 모습 (위 · 옆), 영점 표시"),
        ("모니터 2 — 시간표", "monitors/timeline.png + 진행 막대 · 단계 표시점 (반복 = 주황)"),
        ("모니터 3 — 수조 카메라", "앞 유리 카메라 — 실제로 자라는 존재 (사람이 보는 그대로)"),
        ("모니터 4 — 아날로그 계측", "CV 채널 9개 · 배지 전도도 · 누설 · 10 MHz / PPS 잠김"))
    video_out: str = "HDMI 2 · DisplayPort 2 (뒤판, IP67 덮개) — 모니터 4대, 수조 옆 받침 팔"
    analog: str = ("DAC 16비트 × 9 (±10 V) → 주사기 펌프 · 봉 회전 · 팔 r · z · 405 nm 빛 · 트리거, ADC × 8 ← 배지 전도도 · 누설 · 발 단자 · C–V — "
                   "SD 읽기와 화면 띄우기만 하는 작은 디지털 부분 (마이크로컨트롤러), 그 밖은 아날로그 신호 길")

    @property
    def top_z(self) -> float:
        """본체 윗면 (XPS 아래) — 수조 바깥 바닥 −6 에서 받침 테 · XPS 만큼 아래."""
        return -6.0 - self.tray_mm - self.insulation_mm

    @property
    def bottom_z(self) -> float:
        return self.top_z - self.body_h_mm


@dataclass(frozen=True)
class Inputs:
    """데스크톱 앞에 붙는 입력 — 접는 받침판(데스크톱 앞판에 경첩) 위 IP68 키보드 · 마우스, 짧은 IP67 M12 선으로 데스크톱에."""

    tray_mm: tuple[float, float, float] = (420.0, 190.0, 10.0)  # 접는 받침판 (펼친 크기)
    tray_drop_mm: float = 20.0  # 본체 윗면에서 받침판까지 아래로
    keyboard: str = "IP68 실리콘 키보드 (의료용, 물·식염수 세척 가능) — 숫자판 있는 것 (Blender 숫자판 시점)"
    keyboard_mm: tuple[float, float, float] = (360.0, 120.0, 16.0)
    mouse: str = "IP68 방수 마우스 (의료용, 밀봉 휠 · 가운데 버튼) — Blender 처럼 가운데 끌기로 돌려 보기"
    mouse_mm: tuple[float, float, float] = (64.0, 110.0, 36.0)


@dataclass(frozen=True)
class Turntable:
    """회전 받침 — Blender 의 '돌려 보기'를 기계로: 존재를 앞 유리 쪽으로 돌림. 빚는 동안은 0° 에 묶음."""

    limit_deg: float = 180.0  # ±180° — 흑연 패드 전선이 꼬이지 않는 한도 (슬립링 없음, 금속 없음)
    deg_s: float = 30.0
    motor: str = "N20 기어 모터 (6 V, 30 rpm) — 작은 방수 통 속, 자석 커플링 (축 구멍 없음)"
    pod_mm: tuple[float, float] = (20.0, 30.0)  # 작은 방수 통 반지름 · 높이
    disc_sc1_mm: float = 3.0  # SC-1: 배양 받침 밑 자석 원판 두께 (펜 끝을 그만큼 올림)
    disc_sc2_mm: tuple[float, float] = (59.0, 6.0)  # SC-2: 120 받침판을 대신하는 원판 반지름 · 두께 (높이 같음)


@dataclass(frozen=True)
class ViewLight:
    """보기 빛 — 고른 곳을 비춤. SC-2 광엔진의 세 번째 색 (빨강 630 nm). SC-1 은 없음 (펜의 405 nm 고리는 굳힘)."""

    nm: float = 630.0
    mw_cm2: float = 0.5
    note: str = ("가정: 630 nm 는 GO 광환원 · 감광 PVA(SbQ, 300–400 nm) · 에오신 Y(약 520 nm) 를 거의 일으키지 않음 — "
                 "시험편으로 10 분 비춰 굳은 두께 · 저항이 그대로인지 잴 것")


# (Blender 키 · 마우스, Blender 화면에서, 수조 모니터(기계)에서, G-code 매크로)
HW_KEYMAP: tuple[tuple[str, str, str, str], ...] = (
    ("가운데 버튼 끌기 (좌우) · 숫자판 4 / 6", "돌려 보기 (궤도)", "회전 받침이 돌아 존재의 다른 면이 앞 유리로 (±180°)", "TURN A=<도>"),
    ("가운데 버튼 끌기 (위아래) · 숫자판 8 / 2", "위아래로 돌려 보기", "기계는 그대로 — 사람이 수조 위 · 옆에서 (유리 정육면체 5면이 투명)", "—"),
    ("Shift + 가운데 끌기 (위아래) · Ctrl + 숫자판 8 / 2", "옮겨 보기 (위아래)", "받침이 오르내림 — 존재를 수면 · 눈높이로", "G1 Z<mm> (BedDrop)"),
    ("휠", "확대 · 축소", "SC-2: 보기 빛 창 크기 (그 부분만 밝힘) · SC-1: 없음", "VIEW_LIGHT R=<mm>"),
    ("왼쪽 클릭", "고르기", "SC-2: 고른 곳을 보기 빛(630 nm)으로 비춤 · SC-1: 화면만", "VIEW_LIGHT X=<mm> Y=<mm> R=<mm>"),
    ("숫자판 1 · 3 · 7", "앞 · 옆 · 위 시점", "회전 0° · 90° · (위) 받침을 수면 바로 아래로", "TURN A=0|90 · G1 Z"),
    ("Home", "전체 보기", "회전 0° · 받침 기본 · 보기 빛 끔", "TURN A=0 · G1 Z · VIEW_LIGHT R=0"),
    ("Ctrl + 휠 · Alt + B", "단면 (층) 보기", "SC-2: 그 층의 설계 단면을 보기 빛으로 수면에 비춤", "VIEW_LIGHT LAYER=<k>"),
    ("Space · ← →", "재생 · 한 단계", "SD 재생 멈춤 · 이어서 · 앞뒤 단계 표시점으로 (모니터 2 에 표시)", "PAUSE · RESUME"),
    ("R · S · F", "다시 · 건너뛰기 · 흐름", "SC-3: 이 단계 한 번 더 · 건너뛰기 · 흐름 배율 — SD 의 edits.json 에 적어 지금 컴퓨터가 다시 구움", "—"),
)


@dataclass(frozen=True)
class Console:
    desktop: Desktop = field(default_factory=Desktop)
    inputs: Inputs = field(default_factory=Inputs)
    turntable: Turntable = field(default_factory=Turntable)
    view_light: ViewLight = field(default_factory=ViewLight)

    def heat_into_bath_w(self, insulation_w_mk: float = 0.035, top_rise_k: float = 5.0, inner_mm=(350.0, 350.0)) -> float:
        """본체 윗면이 배지보다 top_rise_k 높을 때 XPS 를 지나 배지로 가는 열 (lightsculpt.heat_w 의 '데스크톱' 과 같은 식)."""
        x, y = (v / 1000 for v in inner_mm)
        return insulation_w_mk / (self.desktop.insulation_mm / 1000) * x * y * top_rise_k

    def gcode(self, action: str, **kw) -> list[str]:
        """HW 뷰포트 동작 → Klipper 매크로 (printer_light.cfg / printer.cfg 의 TURN · VIEW_LIGHT)."""
        t = self.turntable
        if action == "turn":
            a = max(-t.limit_deg, min(t.limit_deg, float(kw.get("deg", 0))))
            return [f"TURN A={a:.1f}"]
        if action == "bed":
            return [f"G1 Z{float(kw['z']):.2f} F180"]
        if action == "view_light":
            if kw.get("r", 0) <= 0:
                return ["VIEW_LIGHT R=0"]
            return [f"VIEW_LIGHT X={kw['x']:.1f} Y={kw['y']:.1f} R={kw['r']:.1f}"]
        if action == "home":
            return ["VIEW_LIGHT R=0", "TURN A=0", f"G1 Z{float(kw.get('z', 0)):.2f} F180"]
        raise ValueError(action)

    def klipper_macros(self) -> str:
        t, v = self.turntable, self.view_light
        return "\n".join([
            "[gcode_macro TURN]", f"description: 회전 받침 (±{t.limit_deg:g}°) — HW 뷰포트 돌려 보기", "gcode:",
            "  {% set a = params.A|default(0)|float %}",
            f"  {{% if a|abs > {t.limit_deg:g} %}}{{ action_raise_error('회전 한도 ±{t.limit_deg:g}°') }}{{% endif %}}",
            f"  MANUAL_STEPPER STEPPER=turn MOVE={{a}} SPEED={t.deg_s:g}", "",
            "[gcode_macro VIEW_LIGHT]", f"description: 보기 빛 {v.nm:g} nm (굳지 않음) — 고른 곳 비춤", "gcode:",
            "  RESPOND MSG=\"VIEW_LIGHT {rawparams}\"  ; 데스크톱 프로젝터 창이 빨강 원(또는 층 단면)을 그림", ""])

    def describe(self) -> str:
        d, i, t, v = self.desktop, self.inputs, self.turntable, self.view_light
        lines = [
            "[수조 콘솔 — 수조가 모니터, 밑에 붙은 방수 데스크톱 + 키보드 · 마우스 = HW 뷰포트]",
            f"  데스크톱: 수조 바로 밑 {d.footprint_mm[0]:g}×{d.footprint_mm[1]:g} mm — 받침 테 {d.tray_mm:g} · XPS {d.insulation_mm:g} · "
            f"본체 {d.body_h_mm:g} mm (윗면 z {d.top_z:g}) · {d.rating}",
            f"    {d.pc} → 배지로 새는 열 약 {self.heat_into_bath_w():.1f} W (XPS 너머)",
            f"    슬롯: {' · '.join(d.slots)} · 화면: {d.video_out}",
            *[f"      {n}: {w}" for n, w in d.monitors],
            f"    신호: {d.analog}",
            f"  입력: 데스크톱 앞판에 경첩으로 붙은 접는 받침판 {i.tray_mm[0]:g}×{i.tray_mm[1]:g} 위 — {i.keyboard} · {i.mouse}",
            f"  회전 받침: ±{t.limit_deg:g}° · {t.motor} · 빚는 동안은 0° 에 묶음",
            f"  보기 빛: {v.nm:g} nm {v.mw_cm2:g} mW/cm² (SC-2 광엔진 세 번째 색) — {v.note}",
            "  키 · 마우스 (Blender 와 같음) → Blender 화면 / 수조 모니터:"]
        for k, scr, hw, g in HW_KEYMAP:
            lines.append(f"    {k:<38} {scr:<16} │ {hw}  [{g}]")
        return "\n".join(lines)

    def to_json(self) -> dict:
        from dataclasses import asdict

        return asdict(self) | {"desktop_top_z": self.desktop.top_z, "desktop_bottom_z": self.desktop.bottom_z,
                               "keymap": [list(r) for r in HW_KEYMAP], "heat_into_bath_w": self.heat_into_bath_w()}
