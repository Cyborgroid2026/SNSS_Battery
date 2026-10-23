"""SC-1 출력 부품 20종 — snss_battery/parts.py 와 같은 치수 · 같은 더하기 빼기를 정확한 B-rep 으로.

부품마다 `PARAMS` (FreeCAD 속성으로 보이는 설계 치수) 와 `build(P) -> Part.Shape`.
공통 치수 Rod (M8 나사봉 · Ø8 봉 구멍 8.6) · Lm8uu (15.2) 는 문서의 '치수' 표에 묶임 — 거기서 바꾸면 모든 부품이 따라 바뀜.
"""

from __future__ import annotations

import math

from .prim import box, capsule, cut, cyl, polar, ring, sphere, twisted_ribbon, union

COMMON = {"Rod": (8.6, "M8 나사봉 · Ø8 봉 구멍 (출력 수축 여유)"), "Lm8uu": (15.2, "LM8UU · 미끄럼 부싱 자리")}


def corner(P):
    s, rod = P["Size"], P["Rod"]
    d = box((0, 0, 0), (s, s, s), P["Round"])
    return cut(d, cyl((0, 0, 8), rod / 2, s + 4, 0), cyl((0, 0, -8), rod / 2, s + 4, 1), cyl((-10, 10, 0), rod / 2, s + 4, 2))


def motor_mount(P):
    w = P["Width"]
    plate = box((0, 0, 3), (w, w, 6), 2)
    clamp = box((0, 35, 10), (w, 20, 20), 2)
    holes = [cyl((0, 0, 3), P["Boss"] / 2, 10)] + [cyl((sx * 15.5, sy * 15.5, 3), 1.7, 10) for sx in (-1, 1) for sy in (-1, 1)]
    return cut(union(plate, clamp), *holes, cyl((0, 35, 10), P["Rod"] / 2, 60, 0))


def pen_carriage(P):
    d = union(box((0, 0, 4), (70, 60, 8), 3), box((0, 22, 9), (70, 18, 18), 3), box((0, -22, 9), (70, 18, 18), 3))
    holes = [cyl((0, sy * 22, 9), P["Lm8uu"] / 2, 80, 0) for sy in (-1, 1)] + [cyl((0, 0, 4), P["PenHole"] / 2, 20)]
    holes += [cyl(c, P["Magnet"] / 2 + 0.1, 3.2) for c in polar(3, 17, 7.5, math.pi / 2)]  # 자석 Ø10
    holes += [box((sx * 30, 0, 7), (6, 8, 6)) for sx in (-1, 1)]  # 벨트 끝 물림
    return cut(d, *holes)


def y_end(P):
    d = box((0, 0, 15), (40, 32, 30), 3)
    return cut(d, cyl((0, 0, 15), P["Lm8uu"] / 2, 40, 1), cyl((0, 0, 6), P["Rod"] / 2, 50, 0), cyl((0, 0, 24), P["Rod"] / 2, 50, 0))


def pen_body(P):
    """세 원료(GO · SNSS · PVA) 통로가 아래로 모여 혼합기 구멍(Ø3.2)으로."""
    L = P["Length"]
    body = union(cyl((0, 0, L / 2), P["BodyD"] / 2, L), cyl((0, 0, L - 4), 17, 8))
    holes = [cyl((0, 0, 16), P["MixerHole"] / 2, 22)]  # 혼합기 구멍 z 5–27
    for k in range(3):
        a = k * 2 * math.pi / 3
        holes.append(capsule((6 * math.cos(a), 6 * math.sin(a), L + 2), (0, 0, 27), P["Channel"] / 2))  # 원료 통로
        holes.append(cyl((6 * math.cos(a), 6 * math.sin(a), L - 2), 1.6, 8))  # 관 끼우는 자리
        b = math.pi / 2 + k * 2 * math.pi / 3
        holes.append(sphere((17 * math.cos(b), 17 * math.sin(b), L), 4.1))  # 쇠구슬 Ø8 자리 (키네마틱)
    holes.append(cyl((0, 0, 2.5), 2.2, 9))  # 노즐 허브 (루어 슬립)
    holes.append(ring((0, 0, 10), 12, 10, 4))  # 빛 고리 홈
    return cut(body, *holes)


def mixer(P):
    """나선형 혼합기 (Kenics): 요소마다 180° 비틀림 방향이 바뀌고 90° 엇갈림."""
    n, el, d, t = int(P["Elements"]), P["ElementLen"], P["Diameter"], P["Thick"]
    parts = []
    for k in range(n):
        sgn = 1 if k % 2 == 0 else -1
        a0 = k * math.pi / 2
        parts.append(twisted_ribbon(k * el - (0.01 if k else 0), el + (0.01 if k else 0), d - 0.16, t, a0, a0 + sgn * math.pi))
    return union(*parts)


def syringe_pump(P):
    base = box((0, 0, 3), (130, 44, 6), 2)
    motor = box((-60, 0, 25), (10, 44, 44), 2)
    cradle = box((35, 0, 14), (50, 30, 22), 2)
    stop = box((8, 0, 18), (6, 44, 30), 2)
    holes = [cyl((-60, 0, 25), 11.5, 20, 0)] + [cyl((-60, sy * 15.5, 25 + sz * 15.5), 1.7, 20, 0) for sy in (-1, 1) for sz in (-1, 1)]
    holes += [cyl((35, 0, 25), P["Syringe"] / 2, 60, 0), box((8, 0, 26), (8, 24, 3))]  # 주사기 몸통 받침 · 날개 물림
    holes += [cyl((-20, sy * 15, 25), 2.1, 90, 0) for sy in (-1, 1)]  # M4 안내봉
    return cut(union(base, motor, cradle, stop), *holes)


def pinch_valve(P):
    d = box((0, 0, 7.5), (30, 22, 15), 2)
    return cut(d, cyl((0, 0, 5), P["Tube"] / 2, 40, 0), box((0, 0, 12), (8, 24, 9)), cyl((0, 8, 7.5), 1.5, 20, 2))


def tank_base(P):
    s = P["Size"]
    d = box((0, 0, 2.5), (s, s, 5), 3)
    ridges = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            ridges += [box((sx * (s / 2 - 6), sy * (s / 2 - 16), 6), (4, 24, 4)), box((sx * (s / 2 - 16), sy * (s / 2 - 6), 6), (24, 4, 4))]
    return cut(union(d, *ridges), box((0, 0, 5), (110, 6, 3)))


def pad_holder(P):
    """배양 받침: 발바닥 밑 흑연 패드 두 장 (왼발 +, 오른발 −) · 양쪽 손잡이 고리 (받침째 수확)."""
    px = P["PadX"]
    d = union(box((0, 2, 3), (50, 36, 6), 3),
              *[cut(box((sx * 31, 2, 3), (14, 14, 6), 3), cyl((sx * 33, 2, 3), 3.5, 10)) for sx in (-1, 1)])
    pockets = [box((sx * px, 2.5, 5.4), (P["PadW"], P["PadL"], 1.4)) for sx in (-1, 1)]  # 흑연 시트 0.5 mm + 여유
    channels = [box((sx * px, 16, 4.5), (3, 8, 2)) for sx in (-1, 1)]
    return cut(d, *pockets, *channels)


def level_probe(P):
    d = union(box((0, 0, 20), (22, 8, 40), 2), box((0, 8, 38), (22, 16, 4), 1), box((0, 15, 30), (22, 4, 20), 1))
    return cut(d, cyl((-5, 0, 20), P["Lead"] / 2 + 0.1, 44), cyl((5, 0, 20), P["Lead"] / 2 + 0.1, 44))


def port_panel(P):
    d = union(box((0, 0, 2), (170, 64, 4), 3), box((0, 30, 8), (170, 4, 16)), box((0, -30, 8), (170, 4, 16)))
    holes = [cyl((-70 + i * 20, 12, 2), P["Bnc"] / 2, 10) for i in range(8)]  # BNC Ø9.7
    holes += [cyl((-70 + i * 18, -12, 2), P["Sma"] / 2, 10) for i in range(3)]  # SMA Ø6.6
    holes += [box((10, -12, 2), (9.6, 3.6, 10), 1.2), box((45, -12, 2), (16.5, 14.5, 10))]  # USB-C · RJ45
    return cut(d, *holes)


def electronics_box(P):
    L, W, H = P["Length"], P["Width"], P["Height"]
    d = cut(box((0, 0, H / 2), (L, W, H), 4), box((0, 0, H / 2 + 3), (L - 5, W - 5, H), 2))
    vents = [box((-60 + i * 12, W / 2, H / 2), (5, 10, 30), 1) for i in range(11)]
    return cut(d, *vents, box((0, -W / 2, 20), (160, 10, 24)))


def motor_pod(P):
    """모터 방수 통: 바닥 벽 3 mm 너머 자석 커플링 — 축 구멍이 없어 물길이 없음 (수족관 펌프 방식)."""
    R, H = P["Radius"], P["Height"]
    d = cut(cyl((0, 0, H / 2), R, H), cyl((0, 0, H / 2 + 3), R - P["Wall"], H))
    d = union(d, ring((0, 0, H - 2), R + 3, R - P["Wall"], 4))  # 뚜껑 받침 테
    return cut(d, ring((0, 0, H - 0.8), R + 0.6, R - 1.6, 1.8),  # O-링 홈
               *[cyl((sx * 15.5, sy * 15.5, 6), 1.7, 8) for sx in (-1, 1) for sy in (-1, 1)])


def pod_lid(P):
    d = cyl((0, 0, 2.5), P["Radius"], 5)
    return cut(d, cyl((0, 0, 2.5), P["Gland"] / 2, 8), *[cyl(c, 1.7, 8) for c in polar(6, P["Radius"] - 2, 2.5)])


def coupler(P):
    d = union(cyl((0, 0, 3), P["Radius"], 6), cyl((0, 0, 10), 5, 10))
    pockets = [cyl(c, P["Magnet"] / 2 + 0.1, 3.2) for c in polar(int(P["Magnets"]), 15, 2.9)]
    return cut(d, *pockets, cyl((0, 0, 10), 2.6, 30))


def bushing(P):
    L = P["Length"]
    d = cyl((0, 0, L / 2), P["Lm8uu"] / 2 - 0.1, L)
    return cut(d, cyl((0, 0, L / 2), P["Bore"] / 2, L + 6), box((0, 4, L / 2), (1.2, 8, L + 2)))


def led_ring(P):
    d = ring((0, 0, 3), 17, 11.2, 6)
    return cut(d, *[box((14 * math.cos(k * math.pi / 2), 14 * math.sin(k * math.pi / 2), 0.8), (8.2, 8.2, 2.4)) for k in range(int(P["Leds"]))])


def scanner_mount(P):
    d = union(box((0, 0, 2), (60, 30, 4), 2), box((-25, 0, 20), (10, 30, 40), 2), box((25, 0, 20), (10, 30, 40), 2))
    return cut(d, cyl((-25, 0, 30), P["Laser"] / 2 + 0.1, 20, 0), box((25, 0, 30), (12, 24, 24)), cyl((0, 0, 2), 1.7, 10))


def belt_clamp(P):
    d = box((0, 0, 4), (24, 12, 8), 2)
    return cut(d, box((0, 0, 6.5), (26, P["Belt"] + 0.4, 1.6)), cyl((-8, 0, 4), 1.7, 10), cyl((8, 0, 4), 1.7, 10))


# key → (만드는 함수, {속성: (기본값, 설명)}) — 공통 치수(Rod · Lm8uu)는 쓰는 부품에만
PARTS = {
    "corner": (corner, {"Size": (36.0, "꼭짓점 한 변"), "Round": (3.0, "모서리 반지름"), "Rod": COMMON["Rod"]}),
    "motor_mount": (motor_mount, {"Width": (50.0, "판 한 변"), "Boss": (23.0, "NEMA17 가운데 턱 구멍"), "Rod": COMMON["Rod"]}),
    "pen_carriage": (pen_carriage, {"PenHole": (24.0, "펜 구멍 지름"), "Magnet": (10.0, "키네마틱 자석 지름"), "Lm8uu": COMMON["Lm8uu"]}),
    "y_end": (y_end, {"Rod": COMMON["Rod"], "Lm8uu": COMMON["Lm8uu"]}),
    "pen_body": (pen_body, {"Length": (70.0, "펜 몸체 길이"), "BodyD": (22.0, "몸체 지름"), "MixerHole": (3.2, "혼합기 구멍"),
                            "Channel": (2.0, "원료 통로 지름")}),
    "mixer": (mixer, {"Elements": (4.0, "혼합 요소 수"), "ElementLen": (3.0, "요소 길이 (180° 비틀림)"), "Diameter": (3.0, "혼합기 지름"),
                      "Thick": (0.36, "띠 두께")}),
    "syringe_pump": (syringe_pump, {"Syringe": (20.2, "주사기 몸통 받침 지름")}),
    "pinch_valve": (pinch_valve, {"Tube": (2.2, "실리콘 관 통로")}),
    "tank_base": (tank_base, {"Size": (170.0, "받침 한 변")}),
    "pad_holder": (pad_holder, {"PadX": (9.5, "패드 가운데 ±x (발 간격 반)"), "PadW": (14.0, "흑연 패드 폭"), "PadL": (22.0, "흑연 패드 길이")}),
    "level_probe": (level_probe, {"Lead": (2.0, "연필심 지름")}),
    "port_panel": (port_panel, {"Bnc": (9.7, "BNC 구멍"), "Sma": (6.6, "SMA 구멍")}),
    "electronics_box": (electronics_box, {"Length": (180.0, "길이"), "Width": (120.0, "폭"), "Height": (50.0, "높이")}),
    "motor_pod": (motor_pod, {"Radius": (28.0, "통 바깥 반지름"), "Height": (44.0, "통 높이"), "Wall": (4.0, "벽 두께")}),
    "pod_lid": (pod_lid, {"Radius": (31.0, "뚜껑 반지름"), "Gland": (15.2, "케이블 글랜드 PG9 구멍")}),
    "coupler": (coupler, {"Radius": (22.0, "원판 반지름"), "Magnets": (6.0, "자석 수"), "Magnet": (10.0, "자석 지름")}),
    "bushing": (bushing, {"Length": (24.0, "길이"), "Bore": (8.3, "탄소섬유 봉 구멍"), "Lm8uu": COMMON["Lm8uu"]}),
    "led_ring": (led_ring, {"Leds": (4.0, "405 nm LED 수")}),
    "scanner_mount": (scanner_mount, {"Laser": (12.0, "레이저 선 모듈 지름")}),
    "belt_clamp": (belt_clamp, {"Belt": (6.0, "GT2 벨트 폭")}),
}


def build(key: str, P: dict | None = None):
    fn, spec = PARTS[key]
    p = {k: v[0] for k, v in spec.items()}
    p.update(P or {})
    return fn(p)
