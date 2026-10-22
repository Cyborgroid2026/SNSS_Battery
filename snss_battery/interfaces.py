"""아날로그 · 디지털 · 양자 공학기기 호환 — SC-1 의 바깥 연결 (명세: spec/SCULPTOR.md §6).

구조: Klipper(움직임·펜) ← Moonraker API ← **다리(bridge)** — 라즈베리파이에서 도는 이 모듈.
다리가 세 세계의 말을 G-code 로 옮기고, 측정값을 작업물 기억으로 되돌린다.
- 아날로그: BNC 단자(±10 V, 0–10 V, 4–20 mA) — 오실로스코프 · 멀티미터 · 전원장치 · 포텐시오스탯 · 함수발생기 · 노브
- 디지털: USB · 이더넷(Moonraker HTTP/WebSocket, SCPI 원시 TCP 5025) · TTL 트리거 · G-code 파일 · JSON
- 양자: 10 MHz 기준 · 1 PPS 시간 동기, 층/획 트리거(시간 태거 · 락인), 양자 난수 발생기(QRNG) 씨앗,
        C–V(양자 커패시턴스) 측정 → 페르미 준위 역산 → 도핑 되먹임
하드웨어가 없으면 모의(simulated) 백엔드로 같은 동작을 한다 — 시험·웹 뷰어용.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

ANALOG, DIGITAL, QUANTUM = "아날로그", "디지털", "양자"


@dataclass(frozen=True)
class Port:
    domain: str
    key: str
    connector: str
    signal: str
    direction: str  # 입력 · 출력 · 양방향
    use: str


PORTS: tuple[Port, ...] = (
    # 아날로그 — 존재의 발 단자와 펜을 계측기·노브에 그대로
    Port(ANALOG, "A1", "BNC", "±10 V 차동 (16비트 ADS1115, 1/3 분압 · 입력 1 MΩ)", "입력",
         "존재의 발 단자 전압 → 오실로스코프·멀티미터와 병렬로 기록"),
    Port(ANALOG, "A2", "BNC", "0–1 V 정전압 · 정전류 (외부 전원장치·포텐시오스탯)", "입력",
         "존재를 깨우는 충전 — 발 단자로 바로 이어짐 (릴레이로 분리)"),
    Port(ANALOG, "A3", "BNC", "0–10 V → GO 몫 0–1", "입력", "노브·함수발생기로 펜 끝 혼합비를 실시간 조절"),
    Port(ANALOG, "A4", "BNC", "0–10 V → 405 nm 빛 세기 0–100 %", "입력", "광환원 정도(= rGO 전도도) 조절"),
    Port(ANALOG, "A5", "BNC", "사인 10 mV rms, 10 Hz–1 kHz (MCP4728 + RC 필터)", "출력",
         "교류 소신호 — 락인 증폭기와 함께 C–V(양자 커패시턴스) 측정"),
    Port(ANALOG, "A6", "단자대", "4–20 mA (XTR115)", "출력", "방 온도·습도를 공업용 기록계로"),
    # 디지털
    Port(DIGITAL, "D1", "USB-C", "USB 2.0 (Klipper 직렬 · 다리)", "양방향", "PC 에서 G-code · 작업물 기억 주고받기"),
    Port(DIGITAL, "D2", "RJ45", "이더넷 — Moonraker HTTP/WebSocket · SCPI TCP 5025 · MQTT", "양방향",
         "실험실 자동화 (LabVIEW · PyVISA · Node-RED) — SCPI 명령으로 조각가를 계측기처럼"),
    Port(DIGITAL, "D3", "BNC", "TTL 3.3/5 V 트리거 출력 (층 시작마다 뒤집힘)", "출력", "카메라·계측기 동기"),
    Port(DIGITAL, "D4", "BNC", "TTL 트리거 입력", "입력", "외부 장비가 작업 시작·일시정지"),
    Port(DIGITAL, "D5", "핀 헤더", "I²C · SPI · UART 확장", "양방향", "센서·모듈 추가"),
    # 양자
    Port(QUANTUM, "Q1", "SMA", "10 MHz 기준 입력 (사인/구형, 0–10 dBm) → 분주 1 PPS", "입력",
         "양자 계측기(시간 태거 · NV 자력계 마이크로파원 · 락인)와 같은 시간 기준"),
    Port(QUANTUM, "Q2", "SMA", "1 PPS 입력 (LVTTL) → 라즈베리파이 pps-gpio + chrony", "입력", "작업 기록 시각을 µs 로 맞춤"),
    Port(QUANTUM, "Q3", "SMA", "LVTTL 트리거 출력 (층·획·깎기 시작, 움직임 큐와 동기)", "출력",
         "시간 태거·단일광자 검출기·락인에 사건 표시"),
    Port(QUANTUM, "Q4", "USB", "양자 난수 발생기 (QRNG) 장치 또는 파일", "입력", "세포 씨앗(보로노이 배치)을 양자 난수로"),
    Port(QUANTUM, "Q5", "파일/네트워크", "C–V 측정값 CSV (락인 · 임피던스 분석기 · 포텐시오스탯)", "입력",
         "양자 커패시턴스 → 페르미 준위 역산 → 다음 층 도핑 되먹임"),
)


# ---------- 아날로그 ----------
def volts_to_share(v: float, full_scale: float = 10.0) -> float:
    """0–10 V → 0–1 (넘치면 자름)."""
    return min(max(v / full_scale, 0.0), 1.0)


def ma_to_value(ma: float, lo: float, hi: float) -> float:
    """4–20 mA → lo–hi. 4 mA 아래는 선 끊김."""
    if ma < 3.8:
        raise ValueError(f"{ma:.2f} mA — 4–20 mA 선이 끊겼습니다.")
    return lo + (min(ma, 20.0) - 4.0) / 16.0 * (hi - lo)


def value_to_ma(x: float, lo: float, hi: float) -> float:
    return 4.0 + 16.0 * min(max((x - lo) / (hi - lo), 0.0), 1.0)


def analog_mix(go_v: float, base) -> tuple[float, float, float]:
    """A3 노브 전압으로 GO 몫을 정하고, 나머지는 레시피의 SNSS:PVA 비율대로 나눔."""
    g = volts_to_share(go_v)
    rest = base.snss + base.pva
    return g, (1 - g) * base.snss / rest, (1 - g) * base.pva / rest


# ---------- 디지털: SCPI ----------
@dataclass
class BridgeState:
    mix: tuple[float, float, float] = (0.40, 0.45, 0.15)
    variant: str = "plain"
    light: float = 0.0
    carving: bool = False
    ref: str = "INT"
    layer_trigger: bool = True
    last_cv: list = field(default_factory=list)


class Scpi:
    """SCPI(IEEE 488.2 꼴) 명령 → Klipper G-code. 계측기처럼 조각가를 다룸 (PyVISA: TCPIP::<ip>::5025::SOCKET).

    send(line) → (G-code 목록, 응답 문자열 또는 None). 실제로 보내는 일은 다리가 Moonraker 로.
    """

    IDN = "SNSS,SC-1 조각가,0001,0.3"

    def __init__(self, state: BridgeState | None = None, measure=None) -> None:
        self.s = state or BridgeState()
        self.measure = measure or (lambda what: float("nan"))

    def send(self, line: str) -> tuple[list[str], str | None]:
        line = line.strip()
        if not line:
            return [], None
        head, _, arg = line.partition(" ")
        h = head.upper()
        args = [a.strip() for a in arg.split(",")] if arg else []
        s = self.s
        if h == "*IDN?":
            return [], self.IDN
        if h == "*RST":
            s.__init__()
            return ["CARVE ON=0", "SET_PIN PIN=uv_light VALUE=0", "G28"], None
        if h == "*OPC?":
            return ["M400"], "1"
        if h in ("MIX:RAT", "MIX:RATIO"):
            g, sn, pv = (float(a) for a in args[:3])
            if min(g, sn, pv) < 0 or abs(g + sn + pv - 1) > 1e-6:
                raise ValueError("MIX:RAT — 세 몫은 0 이상, 합 1")
            s.mix = (g, sn, pv)
            if len(args) > 3:
                s.variant = args[3].lower()
            if len(args) > 4:
                s.light = float(args[4])
            return [self._mix()], None
        if h in ("MIX:RAT?", "MIX:RATIO?"):
            return [], ",".join(f"{x:.3f}" for x in s.mix) + f",{s.variant},{s.light:g}"
        if h == "LIGH":
            s.light = min(max(float(args[0]), 0.0), 1.0)
            return [f"SET_PIN PIN=uv_light VALUE={s.light:.3f}"], None
        if h in ("CARV", "CARVE"):
            s.carving = args[0].upper() in ("ON", "1")
            return [f"CARVE ON={int(s.carving)}"], None
        if h in ("JOB:STAR", "JOB:START"):
            return [f"SDCARD_PRINT_FILE FILENAME={args[0].strip(chr(34))}"], None
        if h in ("JOB:PAUS", "JOB:PAUSE"):
            return ["PAUSE"], None
        if h in ("JOB:RES", "JOB:RESUME"):
            return ["RESUME"], None
        if h in ("MEAS:VOLT?", "MEAS:VOLTAGE?"):
            return [], f"{self.measure('volt'):.6g}"
        if h in ("MEAS:CQ?", "MEAS:CAP?"):
            return [], f"{self.measure('cap'):.6g}"
        if h in ("SYST:SYNC:REF", "SYSTEM:SYNC:REF"):
            if args[0].upper() not in ("INT", "EXT"):
                raise ValueError("SYST:SYNC:REF INT|EXT")
            s.ref = args[0].upper()
            return [], None
        if h in ("SYST:SYNC:REF?",):
            return [], s.ref
        if h in ("TRIG:LAY", "TRIG:LAYER"):
            s.layer_trigger = args[0].upper() in ("ON", "1")
            return [], None
        raise ValueError(f"모르는 명령: {head}")

    def _mix(self) -> str:
        g, sn, pv = self.s.mix
        return f"MIX GO={g:.3f} SNSS={sn:.3f} PVA={pv:.3f} VARIANT={self.s.variant} LIGHT={self.s.light:g}"


def serve_scpi(host: str = "127.0.0.1", port: int = 5025, execute=print) -> None:
    """SCPI 원시 소켓 서버 (줄 단위). execute(gcode) 로 G-code 를 넘김 — 다리는 Moonraker 로 보냄."""
    import socketserver

    scpi = Scpi()

    class H(socketserver.StreamRequestHandler):
        def handle(self):
            for raw in self.rfile:
                try:
                    gcode, reply = scpi.send(raw.decode(errors="ignore"))
                    for g in gcode:
                        execute(g)
                    if reply is not None:
                        self.wfile.write((reply + "\n").encode())
                except ValueError as e:
                    self.wfile.write(f'-100,"{e}"\n'.encode())

    with socketserver.ThreadingTCPServer((host, port), H) as srv:
        print(f"SCPI 다리: {host}:{port}")
        srv.serve_forever()


# ---------- 양자: 난수 · 시간 · 양자 커패시턴스 되먹임 ----------
def qrng_seed(source: str | None = None, n_bytes: int = 8) -> tuple[int, str]:
    """양자 난수 발생기에서 씨앗. source = 장치(/dev/qrandom0 등)·파일 경로.
    없으면 운영체제 난수(os.urandom)로 대신하고 그렇다고 알림."""
    if source:
        p = Path(source)
        if not p.exists():
            raise ValueError(f"QRNG '{source}' 이(가) 없습니다.")
        with open(p, "rb") as fp:
            b = fp.read(n_bytes)
        if len(b) < n_bytes:
            raise ValueError("QRNG 에서 받은 바이트가 모자랍니다.")
        return int.from_bytes(b, "big") % (2 ** 63), f"양자 난수 ({source})"
    return int.from_bytes(os.urandom(n_bytes), "big") % (2 ** 63), "운영체제 난수 (QRNG 없음)"


def pps_divider_ratio(ref_hz: float = 10e6) -> int:
    """10 MHz → 1 PPS 분주비 (74HC390 10분주 × 7단)."""
    n = round(ref_hz)
    if n <= 0 or 10 ** round(math.log10(n)) != n:
        raise ValueError("기준 주파수는 10 의 거듭제곱 Hz 여야 합니다 (예: 10 MHz).")
    return n


def fit_carrier(points: list[tuple[float, float]], dopant: str, lo: float = 0.0, hi: float = 25.0) -> dict:
    """측정한 C–V 점들 [(전극 전위 V, 용량 µF/cm²)] 에 양자 커패시턴스 모델을 맞춰 도핑 전하 밀도와 페르미 준위를 역산."""
    import numpy as np

    from .qcap import QuantumElectrode

    e = np.array([p[0] for p in points], float)
    c = np.array([p[1] for p in points], float)

    def err(x):
        return float(np.mean((QuantumElectrode(dopant, x).c_total(e) * 100 - c) ** 2))

    a, b = lo, hi
    g = (math.sqrt(5) - 1) / 2
    x1, x2 = b - g * (b - a), a + g * (b - a)
    f1, f2 = err(x1), err(x2)
    for _ in range(60):
        if f1 < f2:
            b, x2, f2 = x2, x1, f1
            x1 = b - g * (b - a)
            f1 = err(x1)
        else:
            a, x1, f1 = x1, x2, f2
            x2 = a + g * (b - a)
            f2 = err(x2)
    x = (a + b) / 2
    el = QuantumElectrode(dopant, x)
    return {"carrier_1e12": x, "ef_mev": el.mu0_ev * 1000, "rms_uf_cm2": math.sqrt(err(x))}


def doping_feedback(measured_1e12: float, target_1e12: float, ratio: float, gain: float = 0.8) -> float:
    """다음 층의 도펀트 몫: 도핑량 ∝ 혼합 몫 (보정 곡선이 원점 통과 직선이라 가정) — 비례 되먹임."""
    if measured_1e12 <= 0:
        return min(1.0, ratio * 1.5 if ratio > 0 else 0.1)
    ideal = ratio * target_1e12 / measured_1e12
    return min(max(ratio + gain * (ideal - ratio), 0.0), 1.0)


def ports_table() -> list[dict]:
    return [p.__dict__ for p in PORTS]


def describe() -> str:
    lines = ["[SC-1 바깥 연결 — 아날로그 · 디지털 · 양자 공학기기 호환]"]
    for dom in (ANALOG, DIGITAL, QUANTUM):
        lines.append(f"  {dom}:")
        for p in PORTS:
            if p.domain == dom:
                lines.append(f"    {p.key} {p.connector:<6} {p.direction:<4} {p.signal} — {p.use}")
    lines.append("  SCPI 예: *IDN? · MIX:RAT 0.5,0.4,0.1,p,1 · LIGH 0.8 · CARV ON · JOB:STAR job.gcode · MEAS:CQ? · SYST:SYNC:REF EXT")
    return "\n".join(lines)
