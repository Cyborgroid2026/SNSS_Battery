"""SC-3 영점 막대 + 수조 콘솔 — 실제로 만들 수 있게: 출력 부품 · 살 것 · 놓는 자리 · 조립 순서 · 조립 점검 (명세: spec/SC3_BUILD.md).

한 곳(여기)에서 모든 부품의 자리를 정하고, Blender 장면 'SC-3 영점 막대' 는 이 자리대로 그린다 (출력 부품은 여기서 만든 STL).
좌표: 수조 안 바닥 가운데 = (0, 0, 0), 유리 4 mm, 수조 테 윗면 z 350, 바닥(데스크톱 다리가 서는 곳) z −183.

물속에 들어가는 것은 막대(PC 관 · 흑연 봉) · 팔 관(탄소섬유) · 노즐 머리(PETG/레진) · PEEK 노즐 끝 · FEP 관 · PMMA 광섬유뿐 — 금속 없음.
모터 · 레일 · 2020 보 · 베어링은 모두 수조 위(물 밖)에.

주사: 재료마다 노즐이 따로 (p · 막 · n). 노즐 셋이 팔 관 둘레에 30° 씩 벌어져 있고, 팔 관을 서보가 ±30° 돌려 고른 노즐 하나만
막대 쪽을 향하게 한다 — 나머지 둘은 옆으로 비켜 있어 이미 쌓인 껍질에 닿지 않는다 (check 의 '노즐 틈').
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .parts import PARENT_BED_MM, PETG_G_CM3, FILL, G_PER_H, PrintedPart, box, capsule, cut, cyl, mesh_part, union

ROOT = Path(__file__).resolve().parent.parent


# ---------- 치수 (mm) ----------
@dataclass(frozen=True)
class Geometry:
    tank_inner: float = 350.0
    glass: float = 4.0
    fill: float = 330.0
    zero_z: float = 170.0  # 영점 (막대 끝)
    # 수조 위 틀 — 안장 4 → 2020 보 2 (y ±150) → 가로대 2 (x ±150) → 축받이 막대 (y −45, 떼어 냄)
    saddle_slot_depth: float = 15.0
    beam_y: float = 150.0
    bar_x: float = 150.0
    hub_bar_y: float = -45.0  # 축받이 막대 (2020, x 방향 — 두 가로대 위에 걸침)
    # 팔 — 팔 보(2020, y +35) 위 MGN9 r 레일, r 판의 Z 레일, Z 집게가 팔 관(탄소 Ø10/8)을 잡고 서보로 ±30° 돌림
    arm_beam_y: float = 35.0
    reach_mm: float = 50.0  # 팔 관 축 → 노즐 끝 (r = 0 이면 노즐 끝이 막대 축에)
    nozzle_deg: float = 30.0  # 노즐 사이 각
    r_travel: tuple[float, float] = (0.0, 60.0)  # 노즐 끝 반지름 (CV 채널 r)
    tube_drop: float = 356.0  # Z 집게 가운데 → 노즐 끝
    z_rail_lo: float = 446.0  # Z 레일 (MGN9 200) 아래 끝
    z_rail_len: float = 200.0
    carriage_len: float = 40.0
    # 막대 구동 — 20T → 60T (GT2), 닫힌 벨트 188
    belt_len: float = 188.0
    pulley_teeth: tuple[int, int] = (20, 60)

    @property
    def rim_z(self) -> float:
        return self.tank_inner

    @property
    def wall_x(self) -> float:
        return self.tank_inner / 2 + self.glass / 2  # 유리 벽 가운데

    @property
    def saddle_z(self) -> float:
        return self.rim_z - self.saddle_slot_depth

    @property
    def beam_z(self) -> float:  # 2020 보 밑면
        return self.saddle_z + 30.0

    @property
    def z_travel(self) -> tuple[float, float]:
        """노즐 끝 높이 범위 (Z 캐리지가 레일 안에 있는 동안)."""
        lo = self.z_rail_lo + self.carriage_len / 2 - self.tube_drop
        hi = self.z_rail_lo + self.z_rail_len - self.carriage_len / 2 - self.tube_drop
        return lo, hi

    def belt_center_mm(self) -> float:
        """닫힌 GT2 벨트 길이 → 두 풀리 축 사이 (2 mm 피치)."""
        d1, d2 = (t * 2 / math.pi for t in self.pulley_teeth)
        L = self.belt_len
        b = L - math.pi * (d1 + d2) / 2
        return (b + math.sqrt(b * b - 2 * (d2 - d1) ** 2)) / 4


G = Geometry()
NOZZLES = (("p", "p 세포질 (+, GO p · PVA)", -1), ("mem", "막 · 피부 (GO 막 · PVA)", 0), ("n", "n 세포질 (−, GO n · PVA)", 1))


# ---------- 출력 부품 (설치된 방향의 자기 좌표) ----------
def _rim_saddle(p):
    """수조 테 안장: 유리 벽(4 mm + 실리콘 띠)을 밑에서 물고, 위에 2020 보가 M5 T너트로."""
    d = box(p, (0, 0, 15), (40, 40, 30), 2)
    return cut(d, box(p, (0, 0, 0), (4.8, 60, 30)), cyl(p, (0, 0, 24), 2.75, 14))


def _hub_block(p):
    """막대 축받이: 축받이 막대(2020) 위 판 + 608 베어링 두 개 자리 + 모터 탑 (20T → 60T, 벨트 188)."""
    c = G.belt_center_mm()
    plate = box(p, (-15, 30, 5), (80, 100, 10), 3)
    boss = cyl(p, (0, 0, 25), 17, 30)
    wall = box(p, (0, c + 19, 30), (44, 5, 40), 1)
    top = box(p, (0, c + 1.5, 52.5), (44, 46, 5), 2)
    d = union(plate, boss, wall, top)
    holes = [cyl(p, (0, 0, 25), 5.2, 80), cyl(p, (0, 0, 3.6), 11.05, 7.4), cyl(p, (0, 0, 36.4), 11.05, 7.4),
             cyl(p, (0, c, 52.5), 11.5, 10)] + [cyl(p, (sx * 15.5, c + sy * 15.5, 52.5), 1.7, 10) for sx in (-1, 1) for sy in (-1, 1)]
    holes += [cyl(p, (-45, y, 5), 2.75, 14) for y in (0, 60)]  # 축받이 막대로 M5
    return cut(d, *holes)


def _stick_collet(p):
    """막대 집게: 608 안지름 Ø8 축 + 60T 풀리 + 갈라진 물림 (Ø6 막대, M3 하나)."""
    r60 = G.pulley_teeth[1] / math.pi
    d = union(cyl(p, (0, 0, 19), 4, 42), cyl(p, (0, 0, 40.5), 6, 1), cyl(p, (0, 0, 45), r60, 8), cyl(p, (0, 0, 56.5), 8, 15))
    teeth = [box(p, (r60 * math.cos(a), r60 * math.sin(a), 45), (1.2, 1.2, 9)) for a in np.linspace(0, 2 * math.pi, G.pulley_teeth[1], endpoint=False)]
    return cut(d, cyl(p, (0, 0, 30), 3.1, 80), box(p, (6, 0, 56.5), (12, 1.2, 16)), cyl(p, (0, 0, 58), 1.6, 20, 1), *teeth)


def _r_plate(p):
    """r 판: MGN9H 캐리지 위 판 + Z 기둥(Z 레일 자리) + 위 덮개(Z 모터) + 벨트 물림 턱. 팔 관은 판 구멍을 지나 내려감."""
    base = box(p, (0, 23, 3), (50, 66, 6), 2)
    post = box(p, (0, 53, 111), (50, 6, 210), 1)
    cap = box(p, (0, 32.5, 219), (50, 47, 6), 2)
    tab = box(p, (17.5, 49, -4), (15, 4, 8))
    d = union(base, post, cap, tab)
    holes = [cyl(p, (0, 0, 3), 6, 20), cyl(p, (0, 30, 219), 11.5, 10)]
    holes += [cyl(p, (sx * 8, 35 + sy * 7.5, 3), 1.6, 10) for sx in (-1, 1) for sy in (-1, 1)]  # MGN9H
    holes += [cyl(p, (sx * 15.5, 30 + sy * 15.5, 219), 1.7, 10) for sx in (-1, 1) for sy in (-1, 1)]  # NEMA17
    holes += [cyl(p, (0, 53, z), 1.6, 10, 1) for z in range(20, 210, 20)]  # Z 레일 M3
    return cut(d, *holes)


def _z_clamp(p):
    """Z 집게: 팔 관을 6800 베어링 두 개로 잡고(돌 수 있게), T8 너트 · MGN9H 캐리지 · 고르개 서보 자리."""
    body = box(p, (0, 14, 0), (40, 52, 40), 3)
    tab = box(p, (34, 0, -10), (28, 24, 20), 2)
    d = union(body, tab)
    holes = [cyl(p, (0, 0, 0), 5.3, 60), cyl(p, (0, 0, 17.6), 9.55, 5.2), cyl(p, (0, 0, -17.6), 9.55, 5.2),
             cyl(p, (0, 30, 0), 5.2, 60), box(p, (34, 0, -10), (23.2, 12.6, 30))]
    holes += [cyl(p, (8 * math.cos(a), 30 + 8 * math.sin(a), 20), 1.6, 10) for a in (0.785, 2.356, 3.927, 5.498)]  # 너트 날개
    holes += [cyl(p, (sx * 7.5, 40, sz * 8), 1.6, 12, 1) for sx in (-1, 1) for sz in (-1, 1)]  # 캐리지
    return cut(d, *holes)


def _gear(teeth, bore):
    def f(p):
        r = teeth / 2  # 모듈 1
        d = cyl(p, (0, 0, 3), r, 6)
        cuts = [cyl(p, (0, 0, 3), bore / 2, 10)]
        cuts += [box(p, ((r + 0.4) * math.cos(a), (r + 0.4) * math.sin(a), 3), (1.6, 1.6, 8)) for a in np.linspace(0, 2 * math.pi, teeth, endpoint=False)]
        return cut(d, *cuts)
    return f


def _nozzle_head(p):
    """노즐 머리 (물속, 레진 또는 0.25 노즐 PETG): 팔 관 소켓 · 혼합기 3 (재료마다) · PEEK 노즐 끝 3 (180° ± 30°) · 광섬유 2 (p · n)."""
    d = cyl(p, (0, 0, 7), 13, 34)
    holes = [cyl(p, (0, 0, 19), 5.1, 10)]  # 팔 관 소켓 z 14–24
    for k, (_, _, s) in enumerate(NOZZLES):
        a = math.pi + s * math.radians(G.nozzle_deg)
        ca, sa = math.cos(a), math.sin(a)
        holes.append(cyl(p, (6.5 * ca, 6.5 * sa, 2), 1.6, 12.2))  # 혼합기 z −4…8
        holes.append(capsule(p, (6.5 * ca, 6.5 * sa, -4), (6.5 * ca, 6.5 * sa, 0), 0.6))
        holes.append(capsule(p, (6.5 * ca, 6.5 * sa, 0), (14 * ca, 14 * sa, 0), 0.82))  # PEEK 1/16" 자리
        for j in (-1, 1):  # GO · PVA 관 (FEP 1/16") — 소켓 바닥에서 혼합기 위로
            b = a + j * 0.5
            holes.append(capsule(p, (2.6 * math.cos(b), 2.6 * math.sin(b), 14.5), (6.5 * ca + 0.9 * j * -sa, 6.5 * sa + 0.9 * j * ca, 8), 0.82))
        if s != 0:  # 405 nm 광섬유 Ø0.5 — 노즐 3 mm 위에서 같은 쪽으로
            holes.append(capsule(p, (2.0 * ca, 2.0 * sa, 14.5), (8 * ca, 8 * sa, 5), 0.3))
            holes.append(capsule(p, (8 * ca, 8 * sa, 5), (14 * ca, 14 * sa, 3), 0.3))
    return cut(d, *holes)


def _pump_saddle(p):
    """펌프 받침: SC-1 주사기 펌프 바닥판(130 × 44)을 물고 2020 가로대에 M5 하나로."""
    d = box(p, (0, 0, 5), (60, 52, 10), 2)
    return cut(d, box(p, (0, 0, 8), (70, 44.4, 6)), cyl(p, (0, 0, 2), 2.75, 12), *[cyl(p, (sx * 20, 0, 5), 1.6, 12) for sx in (-1, 1)])


def _valve_plate(p):
    """밸브 판: SC-1 핀치 밸브 3 (PVA 를 노즐 셋으로 나눔) + SG90 서보 3, 2020 보에 M5 둘."""
    d = box(p, (0, 0, 3), (110, 40, 6), 2)
    holes = [box(p, (x, 0, 5), (30.4, 22.4, 4)) for x in (-35, 0, 35)] + [cyl(p, (x, 0, 3), 2.75, 10) for x in (-50, 50)]
    return cut(d, *holes)


def _r_motor_mount(p):
    """r 모터 받침: 팔 보 끝면에 M5 둘, 선반 밑에 NEMA17 (축이 위로, GT2 20T)."""
    face = box(p, (3, 0, 0), (6, 20, 20), 1)
    shelf = box(p, (24, 20, 13), (42, 46, 6), 2)
    rib = box(p, (8, 20, 5), (10, 6, 10))
    d = union(face, shelf, rib)
    holes = [cyl(p, (0, 0, 0), 2.75, 20, 0), cyl(p, (21, 20, 13), 11.5, 10)]
    holes += [cyl(p, (21 + sx * 15.5, 20 + sy * 15.5, 13), 1.7, 10) for sx in (-1, 1) for sy in (-1, 1)]
    return cut(d, *holes)


def _idler_mount(p):
    """아이들러 받침: 팔 보 옆면에 M5, 위에 GT2 아이들러(M5 축)."""
    d = box(p, (0, 9.5, 9.5), (18, 19, 19), 2)
    return cut(d, cyl(p, (0, 0, 9.5), 2.75, 20, 1), cyl(p, (0, 10, 9.5), 2.4, 30))


def _hub_clamp(p):
    """축받이 막대 걸쇠: 가로대 위에 M5, 세운 벽의 손나사(M5)가 축받이 막대 옆 홈을 누름 — 풀면 막대째 위로 뽑힘."""
    d = union(box(p, (0, 0, 2.5), (40, 40, 5), 2), box(p, (0, -17, 12.5), (40, 6, 25), 1))
    return cut(d, cyl(p, (0, 5, 2.5), 2.75, 10), cyl(p, (0, -17, 15), 2.75, 10, 1))


def _tank_corner(p):
    """수조 모서리 잡이: 데스크톱 뚜껑(VHB)에서 XPS · 받침판 · 수조 바닥까지 L 로 감쌈 — 수조가 미끄러지지 않게."""
    return union(box(p, (2.5, -22.5, 34), (5, 55, 68), 1), box(p, (-22.5, 2.5, 34), (55, 5, 68), 1))


def _monitor_foot(p):
    """모니터 발: 바닥에 놓는 판 (밑에 고무 패드 4) + 2020 기둥 자리 (M5 로 기둥 끝 구멍에)."""
    d = union(box(p, (0, 0, 6), (180, 140, 12), 4), box(p, (0, 40, 22), (34, 34, 20), 3))
    return cut(d, box(p, (0, 40, 24), (20.4, 20.4, 20)), cyl(p, (0, 40, 6), 2.75, 20),
               *[cyl(p, (sx * 75, sy * 55, 0), 6.2, 2) for sx in (-1, 1) for sy in (-1, 1)])


def _vesa_plate(p):
    """VESA 75 판: 모니터 뒤에 M4 넷, 2020 기둥에 M5 T너트 둘."""
    d = union(box(p, (0, 4, 0), (100, 8, 100), 3), box(p, (0, 12, 0), (30, 8, 100), 2))
    holes = [cyl(p, (sx * 37.5, 4, sz * 37.5), 2.2, 20, 1) for sx in (-1, 1) for sz in (-1, 1)]
    holes += [cyl(p, (0, 10, z), 2.75, 30, 1) for z in (-25, 25)]
    return cut(d, *holes)


def printed() -> list[PrintedPart]:
    return [
        PrintedPart("rim_saddle", "수조 테 안장", 4, "PETG", "유리 벽 테를 물고 2020 보를 받침", (-20, -20, 0), (20, 20, 30), _rim_saddle),
        PrintedPart("hub_block", "막대 축받이 (608 × 2 · 모터 탑)", 1, "PETG", "막대가 도는 축 · 20T→60T", (-55, -20, 0), (25, 80, 55), _hub_block),
        PrintedPart("stick_collet", "막대 집게 + 60T 풀리", 1, "PETG (0.25 노즐 권장)", "막대를 물고 돌림", (-19.2, -19.2, -2), (19.2, 19.2, 64), _stick_collet),
        PrintedPart("hub_clamp", "축받이 막대 걸쇠 (손나사)", 2, "PETG", "풀면 막대째 뽑음", (-20, -20, 0), (20, 20, 25), _hub_clamp),
        PrintedPart("r_plate", "r 판 (Z 기둥 · 덮개)", 1, "PETG (벽 4겹)", "팔 r 캐리지 → Z 레일 · Z 모터", (-25, -10, -8), (25, 56, 222), _r_plate),
        PrintedPart("z_clamp", "Z 집게 (6800 × 2 · T8 너트 · 서보)", 1, "PETG", "팔 관을 잡고 ±30° 돌림", (-20, -12, -20), (48, 40, 20), _z_clamp),
        PrintedPart("tube_gear", "팔 관 기어 30T", 1, "PETG", "고르개 (모듈 1)", (-16, -16, 0), (16, 16, 6), _gear(30, 10.2)),
        PrintedPart("servo_gear", "서보 기어 15T", 1, "PETG", "MG90S 뿔에 나사", (-8.5, -8.5, 0), (8.5, 8.5, 6), _gear(15, 4.8)),
        PrintedPart("nozzle_head", "노즐 머리 (노즐 3 · 혼합기 3)", 1, "레진 (SLA) — 없으면 0.25 노즐 PETG", "재료마다 노즐 따로", (-13, -13, -10), (13, 13, 24), _nozzle_head, 0.2),
        PrintedPart("pump_saddle", "펌프 받침", 4, "PETG", "SC-1 주사기 펌프를 2020 에", (-30, -26, 0), (30, 26, 10), _pump_saddle),
        PrintedPart("valve_plate", "밸브 판 (핀치 밸브 3)", 1, "PETG", "PVA 세 갈래", (-55, -20, 0), (55, 20, 6), _valve_plate),
        PrintedPart("r_motor_mount", "r 모터 받침", 1, "PETG", "팔 보 끝 · GT2", (0, -10, -10), (45, 43, 16), _r_motor_mount),
        PrintedPart("idler_mount", "아이들러 받침", 1, "PETG", "팔 보 앞 끝", (-9, 0, 0), (9, 19, 19), _idler_mount),
        PrintedPart("tank_corner", "수조 모서리 잡이", 4, "PETG", "데스크톱 위 수조 · XPS · 받침판", (-50, -50, 0), (5, 5, 68), _tank_corner),
        PrintedPart("monitor_foot", "모니터 발", 1, "PETG", "바닥에 놓음", (-90, -70, 0), (90, 70, 32), _monitor_foot),
        PrintedPart("vesa_plate", "VESA 75 판", 1, "PETG", "모니터 ↔ 2020 기둥", (-50, 0, -50), (50, 16, 50), _vesa_plate),
    ]


# 시중에서 사는 것 — (무리, 품목, 수량, 사양, 구입처)
BUY: list[tuple[str, str, int, str, str]] = [
    ("틀", "2020 알루미늄 프로파일 420 mm", 2, "V-slot 2020, 끝 M5 탭 — 보 (y ±150)", "알리 · 국내 프로파일 상점 (재단)"),
    ("틀", "2020 알루미늄 프로파일 320 mm", 3, "가로대 2 (x ±150) · 축받이 막대 1", "〃"),
    ("틀", "2020 알루미늄 프로파일 150 mm", 1, "팔 보 (y +35)", "〃"),
    ("틀", "2020 알루미늄 프로파일 300 mm", 1, "모니터 기둥", "〃"),
    ("틀", "2020 L 브래킷 + M5 × 10 · T너트", 8, "보 ↔ 가로대 4 · 팔 보 2 · 여유 2", "〃"),
    ("틀", "실리콘 띠 0.3 × 20 mm", 1, "안장 홈 속 (유리 보호)", "철물점"),
    ("팔", "MGN9H 리니어 가이드 150 mm", 1, "r 축 (캐리지 1)", "알리 · 하이윈 대리점"),
    ("팔", "MGN9H 리니어 가이드 200 mm", 1, "Z 축 (캐리지 1)", "〃"),
    ("팔", "NEMA17 스테퍼 (42 × 40, 축 24 mm)", 3, "막대 θ · 팔 r · 팔 Z", "3D 프린터 부품점"),
    ("팔", "T8 리드 나사 200 mm (리드 2) + 황동 너트 + 5→8 커플러", 1, "Z — 물 밖", "〃"),
    ("팔", "GT2 20T 풀리 (5 mm 구멍)", 2, "막대 · r 모터", "〃"),
    ("팔", "GT2 아이들러 20T (5 mm 구멍)", 1, "r 벨트", "〃"),
    ("팔", "GT2 벨트 6 mm — 닫힌 188 mm 1 · 열린 400 mm 1", 1, "막대 · r", "〃"),
    ("팔", "608ZZ 베어링", 2, "막대 축받이", "〃"),
    ("팔", "6800ZZ 베어링 (10 × 19 × 5)", 2, "팔 관 (고르개로 돎)", "〃"),
    ("팔", "MG90S 서보 (금속 기어)", 1, "노즐 고르개 ±30° (기어 2:1 → 서보 ±60°)", "〃"),
    ("팔", "탄소섬유 관 Ø10 / Ø8 × 500 mm", 1, "팔 관 — 400 mm 로 자름 (물속)", "RC · 연 부품점"),
    ("주사", "PEEK 관 1/16\" × 0.016\" (Ø1.59 / Ø0.41) 30 cm", 1, "노즐 끝 3 (각 45 mm)", "HPLC 부품점"),
    ("주사", "FEP 관 1/16\" × 0.03\" 3 m", 2, "펌프 → 노즐 머리 6 줄 (GO 3 · PVA 3, 각 1.2 m)", "〃"),
    ("주사", "PMMA 광섬유 Ø0.5 mm 2 m", 1, "405 nm → 노즐 p · n 옆 (휨 반지름 6 mm 이상)", "광섬유 상점"),
    ("주사", "405 nm LED 3 W + 광섬유 SMA 결합 렌즈", 2, "물 밖 Z 집게 위 — p · n 따로 켬", "〃"),
    ("주사", "주사기 20 mL 루어락", 4, "GO p · GO n · GO 막 · PVA", "약국"),
    ("주사", "SG90 서보", 3, "핀치 밸브 (PVA 세 갈래)", "3D 프린터 부품점"),
    ("주사", "NEMA17 스테퍼 (펌프)", 4, "SC-1 주사기 펌프 4 대 (출력은 parts.syringe_pump × 4)", "〃"),
    ("막대", "PC 관 Ø6 / Ø4 × 330 mm", 1, "영점 막대 (물속) — 320 mm 로 자름", "아크릴 · PC 상점"),
    ("막대", "흑연 봉 Ø2 × 300 mm", 2, "막대 속 + · − 단자 (끝 12 mm 드러남, 나머지 실리콘)", "전기분해 전극 상점"),
    ("막대", "도전성 에폭시 + 실리콘 전선 0.3 sq", 1, "흑연 봉 윗끝(z 458, 물 밖) → 막대 위로 빼는 + · − 선", "전자 부품점"),
    ("막대", "수족관 실리콘 (초산 없는 것)", 1, "흑연 봉 고정 · 막대 끝 밀봉", "수족관 · 철물점"),
    ("콘솔", "IP67 방수 함체 약 360 × 360 × 110", 1, "양자 아날로그 데스크톱 본체 — 치수가 다르면 console.Desktop 값을 맞춤", "전기 함체 상점"),
    ("콘솔", "XPS 단열판 30 mm (358 × 358 재단)", 1, "본체 열 → 배지 막음", "철물점"),
    ("콘솔", "아크릴 판 10 mm 358 × 358 (재단)", 1, "수조 받침판", "아크릴 상점"),
    ("콘솔", "EPDM 고무판 2 mm 358 × 358", 1, "수조 밑 패킹", "철물점"),
    ("콘솔", "VHB 양면테이프 19 mm", 1, "모서리 잡이 → 함체 뚜껑 (구멍 안 뚫음)", "〃"),
    ("콘솔", "고무 다리 M6 Ø30 × 25", 4, "함체 밑", "〃"),
    ("콘솔", "IP67 USB 방수 패널 커넥터 (나사 덮개)", 3, "키보드 · 마우스 · 예비 — 함체 앞판", "전기 부품점"),
    ("콘솔", "IP67 HDMI 방수 패널 커넥터 + IP68 HDMI 케이블 2 m", 1, "모니터 (뒤판)", "〃"),
    ("콘솔", "IP67 케이블 글랜드 PG9", 4, "모터 7 · 서보 4 · LED 2 선 다발 → 함체 뒤", "〃"),
    ("바닥", "IP66 방수 모니터 18.5\" (VESA 75, 팬 없음)", 1, "보통 1대 — F1–F4 로 화면 바꿈 (더 이으면 최대 4대)", "산업용 모니터 상점"),
    ("바닥", "IP68 의료용 실리콘 키보드 (숫자판)", 1, "바닥 깔개 위", "의료 · 산업 키보드 상점"),
    ("바닥", "IP68 방수 마우스 (가운데 버튼 · 밀봉 휠)", 1, "바닥 깔개 위", "〃"),
    ("바닥", "실리콘 바닥 깔개 480 × 220 × 3", 1, "키보드 · 마우스 밑 (미끄럼 막이)", "생활용품점"),
    ("배지", "멸균생리식염수 1 L", 41, "수조 330 mm = 40.4 L", "약국"),
]

# 나사 (M3 · M5 · M4) — 모두 물 밖에 쓰임
FASTENERS = [("M5 × 10 + T너트", 30, "2020 에 붙는 모든 것"), ("M5 손나사 × 16", 2, "축받이 막대 걸쇠"),
             ("M3 × 8", 28, "MGN9 캐리지 8 · NEMA17 12 · T8 너트 4 · 서보 4"), ("M3 × 6 (레일)", 18, "MGN9 레일"),
             ("M4 × 10", 4, "VESA 75"), ("M5 × 30 + 너트", 1, "아이들러 축"), ("M3 × 16 + 너트", 1, "막대 집게 물림")]


# ---------- 놓는 자리 ----------
@dataclass
class Item:
    name: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    kind: str  # printed · bought
    key: str = ""  # 출력 부품 key (STL) — bought 는 ""
    shape: str = "box"  # box · cyl_z · cyl_x · cyl_y · stl
    mat: str = "petg"
    on: str = ""  # 받치는 것 (이름) — "바닥" 은 floor
    move: str = ""  # "" · r · rz · turn (팔 r · 팔 r+z · 막대 회전)
    step: int = 0
    explode: tuple[float, float, float] = (0.0, 0.0, 0.0)
    wet: bool = False
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)  # stl: 자기 좌표 원점이 놓이는 곳
    rot: float = 0.0  # stl: z 축 회전 (도, 90 의 배수)
    solid: bool = True  # 충돌 점검에 넣음


def _rot_box(lo, hi, rot):
    pts = [(x, y) for x in (lo[0], hi[0]) for y in (lo[1], hi[1])]
    c, s = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
    q = [(c * x - s * y, s * x + c * y) for x, y in pts]
    return (min(a for a, _ in q), min(b for _, b in q), lo[2]), (max(a for a, _ in q), max(b for _, b in q), hi[2])


def layout(console=None) -> list[Item]:
    """모든 부품의 자리 (ArmR = 0 · ArmZ = 0 · 막대 0° · 노즐 '막' 을 고른 자세)."""
    from .console import Console

    k = console or Console()
    dk, ip = k.desktop, k.inputs
    P = {p.key: p for p in printed()}
    items: list[Item] = []

    def add(name, lo, hi, kind="bought", **kw):
        items.append(Item(name, tuple(map(float, lo)), tuple(map(float, hi)), kind, **kw))

    def put(key, name, pos, rot=0.0, **kw):
        part = P[key]
        lo, hi = _rot_box(part.lo, part.hi, rot)
        add(name, (pos[0] + lo[0], pos[1] + lo[1], pos[2] + lo[2]), (pos[0] + hi[0], pos[1] + hi[1], pos[2] + hi[2]), "printed",
            key=key, shape="stl", pos=tuple(map(float, pos)), rot=rot, **kw)

    T, g = G.tank_inner / 2, G.glass
    fl = dk.floor_z
    # --- 바닥 · 콘솔 (1–4) ---
    X, Y = dk.footprint_mm
    add("방수 데스크톱 함체 (IP67)", (-X / 2, -Y / 2, dk.bottom_z), (X / 2, Y / 2, dk.top_z), mat="pc", on="고무 다리 1", step=1, explode=(0, 0, -60))
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        add(f"고무 다리 {i + 1}", (sx * (X / 2 - 30) - 15, sy * (Y / 2 - 30) - 15, fl), (sx * (X / 2 - 30) + 15, sy * (Y / 2 - 30) + 15, dk.bottom_z),
            shape="cyl_z", mat="black", on="바닥", step=1, explode=(0, 0, -90))
    add("XPS 단열판 30", (-X / 2, -Y / 2, dk.top_z), (X / 2, Y / 2, dk.top_z + dk.insulation_mm), mat="xps", on="방수 데스크톱 함체 (IP67)", step=2, explode=(0, 0, 40))
    zt = dk.top_z + dk.insulation_mm
    add("아크릴 받침판 10", (-X / 2, -Y / 2, zt), (X / 2, Y / 2, zt + 10), mat="glass", on="XPS 단열판 30", step=2, explode=(0, 0, 70))
    add("EPDM 패킹 2", (-X / 2, -Y / 2, zt + 10), (X / 2, Y / 2, zt + 12), mat="black", on="아크릴 받침판 10", step=2, explode=(0, 0, 90))
    for i, rot in enumerate((0, 90, 180, 270)):
        c, s = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
        put("tank_corner", f"수조 모서리 잡이 {i + 1}", (c * (T + g + 0.5) - s * (T + g + 0.5), s * (T + g + 0.5) + c * (T + g + 0.5), dk.top_z), rot,
            on="방수 데스크톱 함체 (IP67)", step=2, explode=(c * 60 - s * 60, s * 60 + c * 60, 0), solid=False)
    add("36 큐브 유리 수조", (-T - g, -T - g, -6), (T + g, T + g, G.tank_inner), mat="glass", on="EPDM 패킹 2", step=3, explode=(0, 0, 160), solid=False)
    add(f"배지 — 멸균생리식염수 {G.fill:g} mm", (-T, -T, 0), (T, T, G.fill), mat="bath", on="36 큐브 유리 수조", step=14, solid=False)
    # 바닥: 깔개 · 키보드 · 마우스 · 모니터
    mw, md, mt = ip.mat_mm
    my = -Y / 2 - ip.front_gap_mm - md / 2
    add("실리콘 바닥 깔개", (-mw / 2, my - md / 2, fl), (mw / 2, my + md / 2, fl + mt), mat="black", on="바닥", step=13, explode=(0, -80, 0))
    kw, kd, kh = ip.keyboard_mm
    kx = -mw / 2 + 20 + kw / 2
    add("IP68 실리콘 키보드", (kx - kw / 2, my - kd / 2, fl + mt), (kx + kw / 2, my + kd / 2, fl + mt + kh), mat="silicone", on="실리콘 바닥 깔개", step=13, explode=(0, -80, 40))
    mw2, md2, mh2 = ip.mouse_mm
    mx = mw / 2 - 20 - mw2 / 2
    add("IP68 방수 마우스", (mx - mw2 / 2, my - md2 / 2, fl + mt), (mx + mw2 / 2, my + md2 / 2, fl + mt + mh2), shape="ellipsoid", mat="silicone",
        on="실리콘 바닥 깔개", step=13, explode=(0, -80, 40))
    W, H, Tm = dk.monitor_mm
    sw, sd, sh = dk.monitor_stand_mm
    for n in range(dk.monitor_count):
        side, col = ((1, 0), (-1, 0), (1, 1), (-1, 1))[n]
        cx, cy = side * (X / 2 + 60 + W / 2 + col * (W + 40)), -Y / 2 + 40
        put("monitor_foot", f"모니터 {n + 1} 발", (cx, cy, fl), on="바닥", step=13, explode=(0, 0, -40))
        post_lo = fl + 12
        add(f"모니터 {n + 1} 기둥 2020 × 300", (cx - 10, cy + 30, post_lo), (cx + 10, cy + 50, post_lo + 300), mat="alu", on=f"모니터 {n + 1} 발", step=13,
            explode=(0, 0, 60))
        zc = fl + sh + H / 2
        put("vesa_plate", f"모니터 {n + 1} VESA 판", (cx, cy + 14, zc), 0, on=f"모니터 {n + 1} 기둥 2020 × 300", step=13, explode=(0, -40, 80))
        add(f"IP66 방수 모니터 {n + 1}", (cx - W / 2, cy + 14 - Tm, zc - H / 2), (cx + W / 2, cy + 14, zc + H / 2), mat="pc",
            on=f"모니터 {n + 1} VESA 판", step=13, explode=(0, -120, 80))
    # --- 수조 위 틀 (5–7) ---
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        put("rim_saddle", f"수조 테 안장 {i + 1}", (sx * G.wall_x, sy * G.beam_y, G.saddle_z), on="36 큐브 유리 수조", step=4, explode=(0, 0, 40))
    bz = G.beam_z
    for sy in (-1, 1):
        add(f"2020 보 420 (y {sy * G.beam_y:+g})", (-210, sy * G.beam_y - 10, bz), (210, sy * G.beam_y + 10, bz + 20), mat="alu",
            on=f"수조 테 안장 {2 + (sy > 0) * 2}", step=5, explode=(0, 0, 80))
    top = bz + 20
    for sx, lab in ((1, "팔 가로대"), (-1, "펌프 가로대")):
        add(f"2020 {lab} 320 (x {sx * G.bar_x:+g})", (sx * G.bar_x - 10, -160, top), (sx * G.bar_x + 10, 160, top + 20), mat="alu",
            on="2020 보 420 (y +150)", step=6, explode=(0, 0, 120))
    # --- 팔 r (8) ---
    ay = G.arm_beam_y
    add("2020 팔 보 150", (25, ay - 10, top + 20), (175, ay + 10, top + 40), mat="alu", on="2020 팔 가로대 320 (x +150)", step=7, explode=(0, 0, 160))
    rz0 = top + 40
    add("MGN9 r 레일 150", (25, ay - 4.5, rz0), (175, ay + 4.5, rz0 + 6.5), mat="steel", on="2020 팔 보 150", step=7, explode=(0, 0, 180))
    cx0 = G.reach_mm  # r = 0 일 때 팔 관 축
    add("MGN9H r 캐리지", (cx0 - 20, ay - 10, rz0 + 3), (cx0 + 20, ay + 10, rz0 + 10), mat="steel", on="MGN9 r 레일 150", move="r", step=7,
        explode=(0, 0, 190), solid=False)
    zp = rz0 + 10
    put("r_motor_mount", "r 모터 받침", (175, ay, top + 30), on="2020 팔 보 150", step=7, explode=(60, 0, 160))
    add("r 모터 NEMA17", (175 + 21 - 21, ay + 20 - 21, top + 33 - 40), (175 + 21 + 21, ay + 20 + 21, top + 33), mat="dark", on="r 모터 받침", step=7,
        explode=(60, 0, 100))
    put("idler_mount", "아이들러 받침", (25, ay + 10, top + 20), on="2020 팔 보 150", step=7, explode=(-40, 30, 160), solid=False)
    # --- 팔 Z (9) ---
    put("r_plate", "r 판 (Z 기둥)", (cx0, 0, zp), on="MGN9H r 캐리지", move="r", step=8, explode=(0, 0, 260))
    add("MGN9 Z 레일 200", (cx0 - 4.5, 43.5, G.z_rail_lo), (cx0 + 4.5, 50, G.z_rail_lo + G.z_rail_len), mat="steel", on="r 판 (Z 기둥)", move="r", step=8,
        explode=(0, 0, 260), solid=False)
    add("Z 모터 NEMA17", (cx0 - 21, 30 - 21, zp + 222), (cx0 + 21, 30 + 21, zp + 262), mat="dark", on="r 판 (Z 기둥)", move="r", step=8, explode=(0, 0, 320))
    add("T8 리드 나사 200", (cx0 - 4, 26, zp + 22), (cx0 + 4, 34, zp + 222), shape="cyl_z", mat="steel", on="Z 모터 NEMA17", move="r", step=8,
        explode=(0, 0, 300), solid=False)
    zc_ = G.zero_z + G.tube_drop
    add("MGN9H Z 캐리지", (cx0 - 10, 40, zc_ - 20), (cx0 + 10, 43.5, zc_ + 20), mat="steel", on="MGN9 Z 레일 200", move="rz", step=8, explode=(0, 0, 280), solid=False)
    put("z_clamp", "Z 집게", (cx0, 0, zc_), on="MGN9H Z 캐리지", move="rz", step=8, explode=(0, -40, 280))
    add("고르개 서보 MG90S", (cx0 + 22.5, -6.2, zc_ - 20), (cx0 + 45.5, 6.2, zc_ + 9), mat="dark", on="Z 집게", move="rz", step=8, explode=(30, -40, 300),
        solid=False)
    put("tube_gear", "팔 관 기어 30T", (cx0, 0, zc_ + 20), on="Z 집게", move="rz", step=8, explode=(0, -40, 320), solid=False)
    put("servo_gear", "서보 기어 15T", (cx0 + 22.5, 0, zc_ + 20), on="Z 집게", move="rz", step=8, explode=(30, -40, 320), solid=False)
    for j, sgn in enumerate((-1, 1)):
        add(f"405 nm LED {'p' if sgn < 0 else 'n'}", (cx0 + sgn * 14 - 6, -18, zc_ + 20), (cx0 + sgn * 14 + 6, -6, zc_ + 34), mat="lens", on="Z 집게", move="rz",
            step=8, explode=(0, -60, 320), solid=False)
    # --- 노즐 머리 · 팔 관 (10) ---
    add("팔 관 탄소 Ø10 × 400", (cx0 - 5, -5, G.zero_z + 14), (cx0 + 5, 5, G.zero_z + 414), shape="cyl_z", mat="cf", on="Z 집게", move="rz", step=9,
        explode=(0, -40, 120), wet=True, solid=False)
    put("nozzle_head", "노즐 머리", (cx0, 0, G.zero_z), on="팔 관 탄소 Ø10 × 400", move="rz", step=9, explode=(0, -40, -40), wet=True)
    for key, lab, s in NOZZLES:
        a = math.pi + s * math.radians(G.nozzle_deg)
        p0 = (cx0 + 9 * math.cos(a), 9 * math.sin(a))
        p1 = (cx0 + G.reach_mm * math.cos(a), G.reach_mm * math.sin(a))
        add(f"PEEK 노즐 {lab}", (min(p0[0], p1[0]), min(p0[1], p1[1]) - 0.8, G.zero_z - 0.8), (max(p0[0], p1[0]), max(p0[1], p1[1]) + 0.8, G.zero_z + 0.8),
            shape="seg", mat="peek", on="노즐 머리", move="rz", step=9, explode=(0, -40, -40), wet=True, solid=False,
            pos=(p0[0], p0[1], G.zero_z), rot=math.degrees(a))
    # --- 펌프 · 밸브 (11) ---
    for i, y in enumerate((-128, -8, 46, 100)):  # 축받이 막대(y −55…−35) · 걸쇠를 비켜
        lab = ("GO p", "GO n", "GO 막", "PVA")[i]
        put("pump_saddle", f"펌프 받침 {lab}", (-G.bar_x, y, top + 20), on="2020 펌프 가로대 320 (x -150)", step=10, explode=(0, 0, 60))
        add(f"주사기 펌프 {lab} (SC-1 출력)", (-G.bar_x - 65, y - 22, top + 24), (-G.bar_x + 65, y + 22, top + 71), mat="petg", on=f"펌프 받침 {lab}",
            step=10, explode=(0, 0, 100))
    put("valve_plate", "밸브 판", (-75, G.beam_y, top), on="2020 보 420 (y +150)", step=10, explode=(0, 40, 60))
    for j, x in enumerate((-110, -75, -40)):
        add(f"핀치 밸브 → 노즐 {NOZZLES[j][0]} (SC-1 출력)", (x - 15, G.beam_y - 11, top + 2), (x + 15, G.beam_y + 11, top + 17), mat="petg", on="밸브 판",
            step=10, explode=(0, 40, 90), solid=False)
    # --- 막대 · 축받이 (12) ---
    hy = G.hub_bar_y
    hub_bar = "2020 축받이 막대 320 (y −45)"
    add(hub_bar, (-160, hy - 10, top + 20), (160, hy + 10, top + 40), mat="alu", on="2020 팔 가로대 320 (x +150)", step=11, explode=(0, 0, 200))
    for i, (sx, side) in enumerate(((1, 1), (-1, -1))):  # 팔 쪽은 +y 옆, 펌프 쪽은 −y 옆 (펌프 자리를 비켜)
        put("hub_clamp", f"축받이 막대 걸쇠 {i + 1}", (sx * G.bar_x, hy + side * 30, top + 20), 0 if side > 0 else 180,
            on=f"2020 {'팔' if sx > 0 else '펌프'} 가로대 320 (x {sx * G.bar_x:+g})", step=11, explode=(0, side * 40, 180), solid=False)
    hz = top + 40
    put("hub_block", "막대 축받이", (0, 0, hz), 90, on=hub_bar, step=11, explode=(0, 0, 220))
    c = G.belt_center_mm()
    add("막대 모터 NEMA17", (-c - 21, -21, hz + 55), (-c + 21, 21, hz + 95), mat="dark", on="막대 축받이", step=11, explode=(0, 0, 260))
    put("stick_collet", "막대 집게 + 60T", (0, 0, hz), on="막대 축받이", move="turn", step=11, explode=(0, 0, 300), solid=False)
    add("영점 막대 PC Ø6 × 320", (-3, -3, G.zero_z), (3, 3, G.zero_z + 320), shape="cyl_z", mat="petg", on="막대 집게 + 60T", move="turn", step=11,
        explode=(0, 0, 300), wet=True, solid=False)
    for sx, lab in ((-1, "+"), (1, "−")):
        add(f"흑연 봉 {lab} Ø2 × 300", (sx * 1.0 - 1, -1, G.zero_z - 12), (sx * 1.0 + 1, 1, G.zero_z + 288), shape="cyl_z", mat="graphite",
            on="영점 막대 PC Ø6 × 320", move="turn", step=11, explode=(0, 0, 300), wet=True, solid=False)
    return items


# ---------- 점검 ----------
def _touch(a: Item, b: Item, tol=0.6) -> bool:
    """두 상자가 닿음 — 한 축은 맞닿고(틈 ≤ tol) 다른 두 축은 겹치거나, 서로 겹침 (끼움)."""
    gaps = [max(a.lo[i] - b.hi[i], b.lo[i] - a.hi[i]) for i in range(3)]
    return all(g <= tol for g in gaps)


def _overlap(a_lo, a_hi, b_lo, b_hi, tol=0.3) -> bool:
    return all(min(a_hi[i], b_hi[i]) - max(a_lo[i], b_lo[i]) > tol for i in range(3))


def _chain(by: dict, it: Item) -> set[str]:
    """받침 사슬 — 이것을 받치는 것, 그것을 받치는 것 … (끼워 맞춘 짝은 겹쳐도 됨)."""
    out, cur = set(), it
    while cur.on in by and cur.on not in out:
        out.add(cur.on)
        cur = by[cur.on]
    return out


def _shift(it: Item, r: float, z: float):
    dx = r if it.move in ("r", "rz") else 0.0
    dz = z if it.move == "rz" else 0.0
    return (it.lo[0] + dx, it.lo[1], it.lo[2] + dz), (it.hi[0] + dx, it.hi[1], it.hi[2] + dz)


def nozzle_clearance(pl: dict | None = None, sample: int = 20000) -> dict:
    """노즐 틈: 칸마다(쌓는 순서) 고른 노즐이 그 칸에 있을 때, 고르지 않은 노즐 끝 · 머리 · 팔 관이 지금 껍질 바깥으로 얼마나 떨어져 있나."""
    from .candy import plan

    pl = pl or plan("being")
    xyz = pl["xyz"]
    zero = np.array(pl["zero_mm"])
    rel = xyz - zero
    rho = np.hypot(rel[:, 0], rel[:, 1])
    R = np.linalg.norm(rel, axis=1)
    idx = np.linspace(0, len(R) - 1, min(sample, len(R))).astype(int)
    rho, z, R = rho[idx], rel[idx, 2], R[idx]
    worst = np.inf
    a = math.radians(G.nozzle_deg)
    # 팔 관 축은 (rho + reach, 0) — 고르지 않은 노즐 끝은 축에서 reach 거리, ±a 만큼 돈 방향
    for s in (-1, 1):
        tx = rho + G.reach_mm - G.reach_mm * math.cos(a)
        ty = s * G.reach_mm * math.sin(a)
        worst = min(worst, float((np.sqrt(tx ** 2 + ty ** 2 + z ** 2) - R).min()))
    # 고르개를 돌리는 동안(±a 사이)도 — 가장 가까운 것은 끝이 축을 지날 때 = 고른 자리
    head = float((np.sqrt((rho + G.reach_mm - 13) ** 2 + z ** 2) - R).min())
    return {"inactive_tip_mm": round(worst, 2), "head_mm": round(head, 2), "shell_mm": float(pl["spec"].shell_mm),
            "rho_max": float(rho.max()), "z_rel": [float(z.min()), float(z.max())], "R_max": float(R.max())}


def check(items: list[Item] | None = None, pl: dict | None = None) -> dict:
    """조립 점검 — 출력 크기 · 받침(뜬 것 없음) · 부딪침(팔을 끝까지 움직여도) · 노즐 틈 · 닿는 범위 · 꺼내는 길 · 벨트."""
    from .candy import plan
    from .console import Console

    items = items or layout()
    by = {it.name: it for it in items}
    pl = pl or plan("being")
    bad, ok = [], []
    # 1 출력 크기
    big = [p.name for p in printed() if not p.fits()]
    (bad if big else ok).append(f"출력 부품 {len(printed())}종 모두 베드 {PARENT_BED_MM[0]:g}×{PARENT_BED_MM[1]:g}×{PARENT_BED_MM[2]:g} 안" if not big
                                else f"베드보다 큼: {', '.join(big)}")
    # 2 받침 — 붕 뜬 것 없음
    fl = Console().desktop.floor_z
    floating = []
    for it in items:
        if it.on == "바닥":
            if abs(it.lo[2] - fl) > 0.6:
                floating.append(f"{it.name} (바닥 {fl:g} 인데 밑면 {it.lo[2]:g})")
        elif it.on not in by:
            floating.append(f"{it.name} (받침 '{it.on}' 없음)")
        elif not _touch(it, by[it.on]):
            floating.append(f"{it.name} ↛ {it.on}")
    (bad if floating else ok).append("뜬 부품: " + "; ".join(floating) if floating else f"부품 {len(items)}개 모두 받침에 닿음 (바닥 것은 z {fl:g})")
    # 3 부딪침 — 팔 r · z 끝까지
    nc = nozzle_clearance(pl)
    zt = G.z_travel
    hits = set()
    fixed = [it for it in items if it.solid and not it.move]
    moving = [it for it in items if it.solid and it.move in ("r", "rz")]
    r_lo, r_hi = G.r_travel
    for r in (r_lo, r_hi):
        for z in (zt[0] - G.zero_z, zt[1] - G.zero_z):
            for m in moving:
                lo, hi = _shift(m, r, z)
                for f in fixed:
                    if f.name in _chain(by, m) or m.name in _chain(by, f):
                        continue
                    if _overlap(lo, hi, f.lo, f.hi):
                        hits.add(f"{m.name} ↔ {f.name} (r {r:g}, z {z:+g})")
    for i, a in enumerate(fixed):
        for b in fixed[i + 1:]:
            if a.name in _chain(by, b) or b.name in _chain(by, a):
                continue
            if _overlap(a.lo, a.hi, b.lo, b.hi):
                hits.add(f"{a.name} ↔ {b.name}")
    (bad if hits else ok).append("부딪침: " + "; ".join(sorted(hits)) if hits else "부딪침 없음 — 팔 r 0…60 · 노즐 높이 끝까지 움직여도")
    # 4 노즐 틈
    if nc["inactive_tip_mm"] >= 2 * nc["shell_mm"] and nc["head_mm"] >= 2 * nc["shell_mm"]:
        ok.append(f"노즐 틈 — 고르지 않은 노즐 끝은 지금 껍질에서 {nc['inactive_tip_mm']:.1f} mm 이상, 머리는 {nc['head_mm']:.1f} mm 이상 바깥 (껍질 {nc['shell_mm']} mm)")
    else:
        bad.append(f"노즐 틈 모자람: 노즐 {nc['inactive_tip_mm']} · 머리 {nc['head_mm']} mm")
    # 5 닿는 범위
    rr = (nc["rho_max"] <= r_hi)
    zz = (zt[0] <= G.zero_z + nc["z_rel"][0] and G.zero_z + nc["z_rel"][1] <= zt[1])
    msg = (f"닿는 범위 — 존재 반지름 {nc['rho_max']:.0f} ≤ r {r_hi:g} · 높이 {G.zero_z + nc['z_rel'][0]:.0f}…{G.zero_z + nc['z_rel'][1]:.0f} ⊂ "
           f"노즐 {zt[0]:.0f}…{zt[1]:.0f} mm")
    (ok if rr and zz else bad).append(msg)
    head_top = zt[1] + 24
    (ok if head_top < G.fill else bad).append(f"노즐 머리 가장 높을 때 윗면 z {head_top:.0f} < 수면 {G.fill:g}")
    # 6 꺼내는 길 — 축받이 막대째 들면 존재가 위로: 막대 축 둘레 (rho_max + 5) 안에 고정 부품 없음
    need = nc["rho_max"] + 5
    block = []
    for it in fixed + [i for i in items if i.move in ("r", "rz")]:
        if it.lo[2] < G.zero_z + nc["z_rel"][1] or it.name.startswith(("2020 축받이", "막대", "축받이", "영점 막대", "흑연")):
            continue
        lo, hi = _shift(it, r_hi, 0) if it.move else (it.lo, it.hi)
        dx = max(lo[0], 0, -hi[0])
        dy = max(lo[1], 0, -hi[1])
        if math.hypot(dx, dy) < need:
            block.append(it.name)
    (bad if block else ok).append(f"꺼내는 길 막힘: {', '.join(block)}" if block else
                                  f"꺼내는 길 — 축받이 막대를 들면 막대 축 둘레 Ø{2 * need:.0f} 가 수면까지 비어 있음 (팔은 r {r_hi:g} 에 둠)")
    # 7 벨트
    c = G.belt_center_mm()
    ok.append(f"막대 벨트 GT2 닫힌 {G.belt_len:g} → 축 사이 {c:.1f} mm (20T→60T, 막대 {Geometry().pulley_teeth[1] // Geometry().pulley_teeth[0]}:1 감속)")
    wet_metal = [it.name for it in items if it.wet and it.mat in ("steel", "alu", "dark")]
    (bad if wet_metal else ok).append(f"물속 금속: {wet_metal}" if wet_metal else "물속 부품에 금속 없음 (막대 · 팔 관 · 머리 · 노즐 · 흑연)")
    return {"ok": not bad, "pass": ok, "fail": bad, "nozzle": nc}


# ---------- 조립 순서 ----------
STEPS: list[tuple[int, str, str]] = [
    (0, "부품 뽑기 · 사기", "출력 부품 표(parts.csv) 대로 뽑고, 살 것(buy.csv)을 모음. 노즐 머리는 레진(SLA) — 없으면 0.25 mm 노즐 PETG. "
                        "SC-1 주사기 펌프 × 4 · 핀치 밸브 × 3 · 혼합기 × 3 도 SC-1 부품에서 뽑음."),
    (1, "데스크톱을 바닥에", "IP67 함체에 고무 다리 4 를 M6 로. 바닥(평평한 곳)에 놓음 — 앞판(USB · SD)이 사람 쪽."),
    (2, "단열 · 받침판 · 모서리 잡이", "함체 뚜껑 위에 XPS 30 → 아크릴 10 → EPDM 2 를 포갬. 모서리 잡이 4 를 네 귀퉁이에 대고 VHB 로 뚜껑에 붙임 (구멍 없음)."),
    (3, "수조 올리기", "빈 36 큐브 수조를 모서리 잡이 안에 내려놓음. 수평계로 수평 (다리 높이로)."),
    (4, "수조 테 안장", "안장 홈에 실리콘 띠를 붙이고, 왼 · 오른 유리 벽 테(y ±150)에 4 개를 끼움."),
    (5, "2020 보 둘", "420 보를 안장 위에 M5 + T너트로 (y ±150). 보 끝은 수조 밖으로 31 mm 씩."),
    (6, "가로대 둘", "320 가로대를 보 위에 L 브래킷으로 — 팔 가로대 x +150, 펌프 가로대 x −150."),
    (7, "팔 r 축", "150 팔 보를 팔 가로대 위에(y +35, x 25…175) L 브래킷 둘로. MGN9 150 레일을 팔 보 윗면에 M3 로. "
                "r 모터 받침(보 끝) + NEMA17, 아이들러 받침(보 앞 끝) + 아이들러, 열린 GT2 벨트를 r 판의 물림 턱에."),
    (8, "팔 Z 축 · 고르개", "r 판을 r 캐리지에 M3 넷. Z 기둥에 MGN9 200 레일, 덮개에 Z 모터 + 커플러 + T8 나사. Z 집게에 6800 베어링 둘 · T8 너트 · MG90S, "
                       "Z 캐리지에 M3 넷. 405 nm LED 둘을 Z 집게 위에."),
    (9, "노즐 머리 · 팔 관", "노즐 머리에 혼합기 3 을 끼우고, PEEK 노즐 끝 3 (각 40 mm) 을 옆 구멍에 에폭시로. FEP 관 6 (GO p · n · 막, PVA × 3) 과 "
                         "광섬유 2 를 팔 관 속으로 꿰어 머리 소켓의 제 구멍에 — 관 끝마다 색 띠(p 빨강 · n 파랑 · 막 노랑). 팔 관을 머리 소켓에 에폭시, "
                         "위에서 Z 집게 베어링에 꽂고 30T 기어를 물림. 서보를 0° 에 두고 '막' 노즐이 −x(막대 쪽)를 보게 맞춤."),
    (10, "펌프 · 밸브 · 관", "펌프 받침 4 를 펌프 가로대에, SC-1 주사기 펌프 4 를 받침에. 밸브 판을 보(y +150)에, 핀치 밸브 3 + SG90 3. "
                          "GO p · n · 막 펌프 → 각자 노즐의 GO 관. PVA 펌프 → Y 이음 둘 → 밸브 3 → 각 노즐의 PVA 관. 관은 팔이 끝까지 가도 당기지 않게 고리를 둠."),
    (11, "막대 · 축받이", "흑연 봉 둘을 PC 관에 넣어 끝 12 mm 만 드러나게, 끝을 실리콘으로 막음. 축받이에 608 둘, 막대 집게를 위에서 꽂고 막대를 집게로 물림 "
                       "(끝이 z 170 = 영점). 축받이 모터 + 20T, 닫힌 벨트 188. 축받이를 축받이 막대(x −45)에 M5 둘 → 막대를 보 위에 걸쇠 + 손나사."),
    (12, "배선", "모터 7 · 서보 4 · LED 2 선을 PG9 글랜드로 함체 뒤에. 함체 앞판에 IP67 USB 3 · 뒤판에 IP67 HDMI."),
    (13, "바닥 — 모니터 · 키보드 · 마우스", "모니터 발을 데스크톱 오른쪽 바닥에, 2020 300 기둥을 발에 M5, VESA 판을 기둥에 T너트, IP66 모니터를 VESA 에 M4 넷. "
                                       "앞 바닥에 깔개, 그 위에 IP68 키보드 · 마우스 — USB 를 앞판 방수 커넥터에."),
    (14, "물 · 영점 맞추기 · 시운전", "수조에 멸균생리식염수 330 mm. r = 0 으로 보내 고른 노즐 끝이 막대 끝(영점)에 닿는지 — 아니면 r 판 나사로 맞춤. "
                                  "물만 넣은 주사기로 노즐 셋을 하나씩 골라 흐름 · 밸브 · 빛 확인 (SD 'test' 굽기)."),
    (15, "꺼내기", "다 자라면 팔을 r 60 으로 보내고, 걸쇠 손나사 둘을 풀어 축받이 막대째 위로 — 존재가 막대에 달려 올라옴."),
]


def assembly_md(items: list[Item] | None = None) -> str:
    items = items or layout()
    rep = check(items)
    out = ["# SC-3 영점 막대 + 수조 콘솔 — 조립 순서", "",
           "`python3 -m snss_battery sc3 build` 이 만든 문서. 부품 자리는 `snss_battery/sc3_build.py` 의 `layout()` (Blender 'SC-3 영점 막대' 장면과 같음).", ""]
    for n, title, text in STEPS:
        used = [it.name for it in items if it.step == n]
        out += [f"## {n}. {title}", "", text, ""] + ([f"부품: {' · '.join(used)}", ""] if used else [])
    out += ["## 조립 점검", ""] + [f"- 통과 — {m}" for m in rep["pass"]] + [f"- **실패** — {m}" for m in rep["fail"]] + [""]
    out += ["## 나사", ""] + [f"- {n} × {q} — {w}" for n, q, w in FASTENERS] + [""]
    return "\n".join(out)


def write(folder: str | Path = ROOT / "cad_out" / "sc3") -> dict:
    """출력 부품 STL · parts.csv · buy.csv · ASSEMBLY.md · layout.json."""
    import json

    from .mesh import write_stl

    folder = Path(folder)
    (folder / "stl").mkdir(parents=True, exist_ok=True)
    rows = []
    for part in printed():
        v, t, vol = mesh_part(part)
        write_stl(folder / "stl" / f"{part.key}.stl", v, t, f"SC-3 {part.key}")
        grams = vol * PETG_G_CM3 * FILL * part.qty
        rows.append({"key": part.key, "name": part.name, "qty": part.qty, "material": part.material, "role": part.role,
                     "size_mm": [round(x, 1) for x in part.size], "grams": round(grams, 1), "hours": round(grams / G_PER_H, 1), "fits": part.fits()})
    (folder / "parts.csv").write_text("부품,수량,재료,크기 mm,필라멘트 g(전체),출력 h(전체),베드 220 들어감,용도\n" + "\n".join(
        f"{r['name']},{r['qty']},{r['material']},{'×'.join(str(x) for x in r['size_mm'])},{r['grams']},{r['hours']},{'예' if r['fits'] else '아니오'},{r['role']}"
        for r in rows) + "\nSC-1 주사기 펌프,4,PETG,130×44×47,,,예,parts.syringe_pump\nSC-1 핀치 밸브,3,PETG,30×22×15,,,예,parts.pinch_valve\n"
        "SC-1 나선형 혼합기,3,레진,3.2×3.2×12,,,예,parts.mixer\n", encoding="utf-8")
    (folder / "buy.csv").write_text("구분,품목,수량,사양,구입처\n" + "\n".join(f"{g},\"{p}\",{q},\"{s}\",{w}" for g, p, q, s, w in BUY) + "\n" +
                                    "\n".join(f"나사,{n},{q},{w}," for n, q, w in FASTENERS) + "\n", encoding="utf-8")
    items = layout()
    (folder / "ASSEMBLY.md").write_text(assembly_md(items), encoding="utf-8")
    (folder / "layout.json").write_text(json.dumps(to_json(items), ensure_ascii=False, indent=1), encoding="utf-8")
    return {"folder": str(folder), "parts": rows, "check": check(items)}


def to_json(items: list[Item] | None = None) -> dict:
    items = items or layout()
    return {"items": [asdict(it) for it in items], "geometry": asdict(G) | {"z_travel": G.z_travel, "belt_center": G.belt_center_mm(), "beam_z": G.beam_z,
                                                                   "wall_x": G.wall_x, "saddle_z": G.saddle_z},
            "nozzles": [{"key": k, "name": n, "side": s, "deg": s * G.nozzle_deg} for k, n, s in NOZZLES],
            "stl_dir": str(ROOT / "cad_out" / "sc3" / "stl"), "steps": [{"n": n, "title": t} for n, t, _ in STEPS]}


def describe(rep: dict | None = None) -> str:
    rep = rep or check()
    lines = ["[SC-3 영점 막대 + 수조 콘솔 — 조립 점검]"] + [f"  통과  {m}" for m in rep["pass"]] + [f"  실패  {m}" for m in rep["fail"]]
    lines.append(f"  출력 부품 {len(printed())}종 · 살 것 {len(BUY)}줄 · 조립 {len(STEPS)}단계 → cad_out/sc3/ASSEMBLY.md")
    return "\n".join(lines)


__all__ = ["G", "Geometry", "NOZZLES", "printed", "BUY", "FASTENERS", "layout", "check", "nozzle_clearance", "STEPS", "write", "to_json", "describe"]
