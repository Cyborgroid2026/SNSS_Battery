"""SC-1 출력 부품 20종 — Blender 비파괴 CSG (freecad/SNSS/snss_fc/printed.py · snss_battery/parts.py 와 같은 치수).

부품마다 '부품 — key' 컬렉션에 완성 개체 하나 (조립 장면이 이 컬렉션을 인스턴스로 씀),
'재료 — key' 컬렉션에 더하고 빼는 기본형 (선으로 보임 — 옮기거나 크기를 바꾸면 부품이 다시 계산됨).
공통 치수: 장면의 '치수' 빈 개체 속성 Rod (8.6) · Lm8uu (15.2) — 나사봉 · 부싱 구멍이 드라이버로 묶임.
"""

from __future__ import annotations

import math

from . import prim as P


class Ctx:
    def __init__(self, coll, dims):
        self.c, self.dims, self.bound = coll, dims, []

    def bound_cyl(self, name, c, key, h, axis=2, extra=0.0):
        """지름이 '치수' 속성(Rod · Lm8uu)에 묶인 원기둥 (+extra mm)."""
        o = P.cyl(self.c, name, c, (self.dims[key] + extra) / 2, h, axis)
        self.bound.append((o, key, extra))
        return o


def _polar(n, r, z, start=0.0):
    return [(r * math.cos(start + k * 2 * math.pi / n), r * math.sin(start + k * 2 * math.pi / n), z) for k in range(n)]


def corner(t):
    c = t.c
    return ("c", P.box(c, "꼭짓점 몸", (0, 0, 0), (36, 36, 36), 3),
            [t.bound_cyl("X 봉 구멍", (0, 0, 8), "Rod", 40, 0), t.bound_cyl("Y 봉 구멍", (0, 0, -8), "Rod", 40, 1),
             t.bound_cyl("Z 봉 구멍", (-10, 10, 0), "Rod", 40, 2)])


def motor_mount(t):
    c = t.c
    return ("c", ("u", [P.box(c, "판", (0, 0, 3), (50, 50, 6), 2), P.box(c, "봉 물림", (0, 35, 10), (50, 20, 20), 2)]),
            [P.cyl(c, "NEMA17 턱", (0, 0, 3), 11.5, 10)] + [P.cyl(c, "모터 나사", (sx * 15.5, sy * 15.5, 3), 1.7, 10)
                                                         for sx in (-1, 1) for sy in (-1, 1)] +
            [t.bound_cyl("봉 구멍", (0, 35, 10), "Rod", 60, 0)])


def pen_carriage(t):
    c = t.c
    holes = [t.bound_cyl("LM8UU 자리", (0, sy * 22, 9), "Lm8uu", 80, 0) for sy in (-1, 1)] + [P.cyl(c, "펜 구멍", (0, 0, 4), 12, 20)]
    holes += [P.cyl(c, "키네마틱 자석 Ø10", p, 5.1, 3.2) for p in _polar(3, 17, 7.5, math.pi / 2)]
    holes += [P.box(c, "벨트 끝 물림", (sx * 30, 0, 7), (6, 8, 6)) for sx in (-1, 1)]
    return ("c", ("u", [P.box(c, "판", (0, 0, 4), (70, 60, 8), 3), P.box(c, "부싱 줄 +", (0, 22, 9), (70, 18, 18), 3),
                        P.box(c, "부싱 줄 −", (0, -22, 9), (70, 18, 18), 3)]), holes)


def y_end(t):
    return ("c", P.box(t.c, "몸", (0, 0, 15), (40, 32, 30), 3),
            [t.bound_cyl("LM8UU 자리", (0, 0, 15), "Lm8uu", 40, 1), t.bound_cyl("X 봉 아래", (0, 0, 6), "Rod", 50, 0),
             t.bound_cyl("X 봉 위", (0, 0, 24), "Rod", 50, 0)])


def pen_body(t):
    c = t.c
    holes = [P.cyl(c, "혼합기 구멍 Ø3.2", (0, 0, 16), 1.6, 22)]
    for k, lab in enumerate(("GO", "SNSS", "PVA")):
        a = k * 2 * math.pi / 3
        holes.append(P.capsule(c, f"원료 통로 {lab}", (6 * math.cos(a), 6 * math.sin(a), 72), (0, 0, 27), 1.0))
        holes.append(P.cyl(c, f"관 자리 {lab}", (6 * math.cos(a), 6 * math.sin(a), 68), 1.6, 8))
        b = math.pi / 2 + k * 2 * math.pi / 3
        holes.append(P.sphere(c, "쇠구슬 Ø8 자리", (17 * math.cos(b), 17 * math.sin(b), 70), 4.1))
    holes += [P.cyl(c, "노즐 허브 (루어)", (0, 0, 2.5), 2.2, 9), P.ring(c, "빛 고리 홈", (0, 0, 10), 12, 10, 4)]
    return ("c", ("u", [P.cyl(c, "몸체 Ø22", (0, 0, 35), 11, 70), P.cyl(c, "마운트 테", (0, 0, 66), 17, 8)]), holes)


def mixer(t):
    els = []
    for k in range(4):
        sgn = 1 if k % 2 == 0 else -1
        els.append(P.twisted(t.c, f"혼합 요소 {k + 1}", k * 3.0 - (0.01 if k else 0), 3.0 + (0.01 if k else 0), 2.84, 0.36,
                             k * math.pi / 2 + sgn * math.pi / 2, sgn * math.pi))
    return ("u", els)


def syringe_pump(t):
    c = t.c
    holes = [P.cyl(c, "모터 턱", (-60, 0, 25), 11.5, 20, 0)] + [P.cyl(c, "모터 나사", (-60, sy * 15.5, 25 + sz * 15.5), 1.7, 20, 0)
                                                           for sy in (-1, 1) for sz in (-1, 1)]
    holes += [P.cyl(c, "주사기 받침 Ø20.2", (35, 0, 25), 10.1, 60, 0), P.box(c, "날개 물림", (8, 0, 26), (8, 24, 3))]
    holes += [P.cyl(c, "M4 안내봉", (-20, sy * 15, 25), 2.1, 90, 0) for sy in (-1, 1)]
    return ("c", ("u", [P.box(c, "바닥판", (0, 0, 3), (130, 44, 6), 2), P.box(c, "모터 벽", (-60, 0, 25), (10, 44, 44), 2),
                        P.box(c, "주사기 받침", (35, 0, 14), (50, 30, 22), 2), P.box(c, "멈춤", (8, 0, 18), (6, 44, 30), 2)]), holes)


def pinch_valve(t):
    c = t.c
    return ("c", P.box(c, "몸", (0, 0, 7.5), (30, 22, 15), 2),
            [P.cyl(c, "관 통로 Ø2.2", (0, 0, 5), 1.1, 40, 0), P.box(c, "서보 뿔 자리", (0, 0, 12), (8, 24, 9)),
             P.cyl(c, "서보 축", (0, 8, 7.5), 1.5, 20, 2)])


def tank_base(t):
    c = t.c
    kids = [P.box(c, "판", (0, 0, 2.5), (170, 170, 5), 3)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            kids += [P.box(c, "모서리 턱", (sx * 79, sy * 69, 6), (4, 24, 4)), P.box(c, "모서리 턱", (sx * 69, sy * 79, 6), (24, 4, 4))]
    return ("c", ("u", kids), [P.box(c, "전선 홈", (0, 0, 5), (110, 6, 3))])


def pad_holder(t):
    c = t.c
    handles = [("c", P.box(c, "손잡이", (sx * 31, 2, 3), (14, 14, 6), 3), [P.cyl(c, "손잡이 고리", (sx * 33, 2, 3), 3.5, 10)]) for sx in (-1, 1)]
    cuts = [P.box(c, f"흑연 패드 자리 {'+' if sx < 0 else '−'}", (sx * 9.5, 2.5, 5.4), (14, 22, 1.4)) for sx in (-1, 1)]
    cuts += [P.box(c, "전선 홈", (sx * 9.5, 16, 4.5), (3, 8, 2)) for sx in (-1, 1)]
    return ("c", ("u", [P.box(c, "받침", (0, 2, 3), (50, 36, 6), 3), *handles]), cuts)


def level_probe(t):
    c = t.c
    return ("c", ("u", [P.box(c, "기둥", (0, 0, 20), (22, 8, 40), 2), P.box(c, "걸이", (0, 8, 38), (22, 16, 4), 1),
                        P.box(c, "걸이 턱", (0, 15, 30), (22, 4, 20), 1)]),
            [P.cyl(c, "연필심 자리", (sx, 0, 20), 1.1, 44) for sx in (-5, 5)])


def port_panel(t):
    c = t.c
    holes = [P.cyl(c, f"BNC A{i + 1}", (-70 + i * 20, 12, 2), 4.85, 10) for i in range(8)]
    holes += [P.cyl(c, f"SMA Q{i + 1}", (-70 + i * 18, -12, 2), 3.3, 10) for i in range(3)]
    holes += [P.box(c, "USB-C", (10, -12, 2), (9.6, 3.6, 10), 1.2), P.box(c, "RJ45", (45, -12, 2), (16.5, 14.5, 10))]
    return ("c", ("u", [P.box(c, "판", (0, 0, 2), (170, 64, 4), 3), P.box(c, "날개 뒤", (0, 30, 8), (170, 4, 16)),
                        P.box(c, "날개 앞", (0, -30, 8), (170, 4, 16))]), holes)


def electronics_box(t):
    c = t.c
    vents = [P.box(c, "환기 홈", (-60 + i * 12, 60, 25), (5, 10, 30), 1) for i in range(11)]
    return ("c", P.box(c, "통", (0, 0, 25), (180, 120, 50), 4),
            [P.box(c, "안", (0, 0, 28), (175, 115, 50), 2), *vents, P.box(c, "단자판 자리", (0, -60, 20), (160, 10, 24))])


def motor_pod(t):
    c = t.c
    body = ("u", [("c", P.cyl(c, "통", (0, 0, 22), 28, 44), [P.cyl(c, "속", (0, 0, 25), 24, 44)]),
                  P.ring(c, "뚜껑 받침 테", (0, 0, 42), 31, 24, 4)])
    return ("c", body, [P.ring(c, "O-링 홈", (0, 0, 43.2), 28.6, 26.4, 1.8)] +
            [P.cyl(c, "모터 나사 (막힌 구멍)", (sx * 15.5, sy * 15.5, 6), 1.7, 8) for sx in (-1, 1) for sy in (-1, 1)])


def pod_lid(t):
    c = t.c
    return ("c", P.cyl(c, "뚜껑", (0, 0, 2.5), 31, 5),
            [P.cyl(c, "케이블 글랜드 PG9", (0, 0, 2.5), 7.6, 8)] + [P.cyl(c, "나사", p, 1.7, 8) for p in _polar(6, 29, 2.5)])


def coupler(t):
    c = t.c
    return ("c", ("u", [P.cyl(c, "원판", (0, 0, 3), 22, 6), P.cyl(c, "풀리 축", (0, 0, 10), 5, 10)]),
            [P.cyl(c, "묻힌 자석 Ø10", p, 5.1, 3.2) for p in _polar(6, 15, 2.9)] + [P.cyl(c, "축 Ø5", (0, 0, 10), 2.6, 30)])


def bushing(t):
    c = t.c
    o = P.cyl(c, "부싱", (0, 0, 12), 7.5, 24)
    t.bound.append((o, "Lm8uu", -0.2))
    return ("c", o, [P.cyl(c, "봉 구멍 Ø8.3", (0, 0, 12), 4.15, 30), P.box(c, "벌어지는 틈", (0, 4, 12), (1.2, 8, 26))])


def led_ring(t):
    c = t.c
    return ("c", P.ring(t.c, "고리", (0, 0, 3), 17, 11.2, 6),
            [P.box(c, "405 nm LED", (14 * math.cos(k * math.pi / 2), 14 * math.sin(k * math.pi / 2), 0.8), (8.2, 8.2, 2.4)) for k in range(4)])


def scanner_mount(t):
    c = t.c
    return ("c", ("u", [P.box(c, "판", (0, 0, 2), (60, 30, 4), 2), P.box(c, "레이저 기둥", (-25, 0, 20), (10, 30, 40), 2),
                        P.box(c, "카메라 기둥", (25, 0, 20), (10, 30, 40), 2)]),
            [P.cyl(c, "레이저 Ø12", (-25, 0, 30), 6.1, 20, 0), P.box(c, "카메라 창", (25, 0, 30), (12, 24, 24)), P.cyl(c, "나사", (0, 0, 2), 1.7, 10)])


def belt_clamp(t):
    c = t.c
    return ("c", P.box(c, "몸", (0, 0, 4), (24, 12, 8), 2),
            [P.box(c, "GT2 벨트 홈", (0, 0, 6.5), (26, 6.4, 1.6)), P.cyl(c, "나사", (-8, 0, 4), 1.7, 10), P.cyl(c, "나사", (8, 0, 4), 1.7, 10)])


PARTS = {k: v for k, v in globals().items() if k in (
    "corner", "motor_mount", "pen_carriage", "y_end", "pen_body", "mixer", "syringe_pump", "pinch_valve", "tank_base", "pad_holder",
    "level_probe", "port_panel", "electronics_box", "motor_pod", "pod_lid", "coupler", "bushing", "led_ring", "scanner_mount", "belt_clamp")}
