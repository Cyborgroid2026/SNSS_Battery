"""SC-1 출력 부품 — 기계를 이루는 부품은 3D 프린터로 뽑는다 (명세: spec/SCULPTOR.md §7).

RepRap 방식: 구조·기구 부품은 흔한 FDM 프린터(베드 220×220 mm)로 PETG 출력, 봉·모터·전자처럼 출력할 수 없는 것만
시중에서 산다 (printer.bom). SC-1 자체는 젤을 빚는 기계라 플라스틱 부품을 직접 뽑지는 못한다 — '부모 프린터'가 뽑음.
모양은 부호 있는 거리장(SDF)을 더하고 빼서 만들고 표면망(mesh.surface_nets)으로 STL 을 만든다 (CAD 프로그램 없이).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .printer import SculptorSpec

PARENT_BED_MM = (220.0, 220.0, 250.0)  # 흔한 FDM 프린터
PETG_G_CM3 = 1.27
FILL = 0.55  # 벽 3겹 + 채움 40 % 의 실효 부피 비 (가정)
G_PER_H = 14.0  # 0.4 mm 노즐 PETG 출력 속도 (가정)
ROD = 8.6  # M8 나사봉 · Ø8 환봉 구멍 (출력 수축 여유)
LM8UU = 15.2


# ---------- SDF 기본형 (mm) ----------
def box(p, c, size, r=0.0):
    q = [np.abs(p[i] - c[i]) - (size[i] / 2 - r) for i in range(3)]
    out = np.sqrt(sum(np.maximum(x, 0) ** 2 for x in q)) + np.minimum(np.maximum(np.maximum(q[0], q[1]), q[2]), 0)
    return out - r


def cyl(p, c, r, h, axis=2):
    """축 axis 방향 원기둥 (가운데 c, 반지름 r, 길이 h)."""
    u, v = [i for i in range(3) if i != axis]
    d_r = np.sqrt((p[u] - c[u]) ** 2 + (p[v] - c[v]) ** 2) - r
    d_h = np.abs(p[axis] - c[axis]) - h / 2
    return np.minimum(np.maximum(d_r, d_h), 0) + np.sqrt(np.maximum(d_r, 0) ** 2 + np.maximum(d_h, 0) ** 2)


def capsule(p, a, b, r):
    ab = np.subtract(b, a, dtype=float)
    t = np.clip(sum((p[i] - a[i]) * ab[i] for i in range(3)) / ab.dot(ab), 0, 1)
    return np.sqrt(sum((p[i] - (a[i] + t * ab[i])) ** 2 for i in range(3))) - r


def sphere(p, c, r):
    return np.sqrt(sum((p[i] - c[i]) ** 2 for i in range(3))) - r


def union(*ds):
    out = ds[0]
    for d in ds[1:]:
        out = np.minimum(out, d)
    return out


def cut(a, *bs):
    for b in bs:
        a = np.maximum(a, -b)
    return a


@dataclass
class PrintedPart:
    key: str
    name: str
    qty: int
    material: str
    role: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    sdf: Callable
    res: float = 0.0  # 0 = 크기에 맞춰 자동

    @property
    def size(self) -> tuple[float, ...]:
        return tuple(h - l for l, h in zip(self.lo, self.hi))

    def fits(self, bed=PARENT_BED_MM) -> bool:
        s = sorted(self.size)
        return s[0] <= sorted(bed)[0] and s[1] <= sorted(bed)[1] and s[2] <= sorted(bed)[2]


# ---------- 부품 ----------
def _corner(p):
    """프레임 꼭짓점: 나사봉 X·Y·Z 세 방향이 서로 비껴 지나감."""
    d = box(p, (0, 0, 0), (36, 36, 36), 3)
    return cut(d, cyl(p, (0, 0, 8), ROD / 2, 40, 0), cyl(p, (0, 0, -8), ROD / 2, 40, 1), cyl(p, (-10, 10, 0), ROD / 2, 40, 2))


def _motor_mount(p):
    """NEMA17 받침: 판(가운데 Ø23, 나사 31 mm 간격) + M8 봉 물림."""
    plate = box(p, (0, 0, 3), (50, 50, 6), 2)
    clamp = box(p, (0, 35, 10), (50, 20, 20), 2)
    d = union(plate, clamp)
    holes = [cyl(p, (0, 0, 3), 11.5, 10)] + [cyl(p, (sx * 15.5, sy * 15.5, 3), 1.7, 10) for sx in (-1, 1) for sy in (-1, 1)]
    return cut(d, *holes, cyl(p, (0, 35, 10), ROD / 2, 60, 0))


def _pen_carriage(p):
    """펜 캐리지: LM8UU 두 줄 + 가운데 펜 구멍 + 자석 키네마틱 마운트 홈 3개 + 벨트 물림."""
    d = union(box(p, (0, 0, 4), (70, 60, 8), 3), box(p, (0, 22, 9), (70, 18, 18), 3), box(p, (0, -22, 9), (70, 18, 18), 3))
    holes = [cyl(p, (0, sy * 22, 9), LM8UU / 2, 80, 0) for sy in (-1, 1)] + [cyl(p, (0, 0, 4), 12, 20)]
    for k in range(3):
        a = math.pi / 2 + k * 2 * math.pi / 3
        holes.append(cyl(p, (17 * math.cos(a), 17 * math.sin(a), 7.5), 5.1, 3.2))  # 자석 Ø10
    holes += [box(p, (sx * 30, 0, 7), (6, 8, 6)) for sx in (-1, 1)]  # 벨트 끝 물림
    return cut(d, *holes)


def _y_end(p):
    """X 봉 끝단(Y 방향으로 달리는 캐리지): LM8UU 1 + X 봉 2."""
    d = box(p, (0, 0, 15), (40, 32, 30), 3)
    return cut(d, cyl(p, (0, 0, 15), LM8UU / 2, 40, 1), cyl(p, (0, 0, 6), ROD / 2, 50, 0), cyl(p, (0, 0, 24), ROD / 2, 50, 0))


def _pen_body(p):
    """SNSS 펜 몸체: 세 원료(GO · SNSS · PVA) 통로가 아래로 모여 혼합기 구멍(Ø3)으로 — 바늘 허브 · 빛 고리 홈 · 마운트 구슬 자리."""
    body = union(cyl(p, (0, 0, 35), 11, 70), cyl(p, (0, 0, 66), 17, 8))
    holes = [cyl(p, (0, 0, 16), 1.6, 22)]  # 혼합기 구멍 z 5–27
    for k in range(3):
        a = k * 2 * math.pi / 3
        holes.append(capsule(p, (6 * math.cos(a), 6 * math.sin(a), 72), (0, 0, 27), 1.0))  # 원료 통로
        holes.append(cyl(p, (6 * math.cos(a), 6 * math.sin(a), 68), 1.6, 8))  # 관 끼우는 자리
        b = math.pi / 2 + k * 2 * math.pi / 3
        holes.append(sphere(p, (17 * math.cos(b), 17 * math.sin(b), 70), 4.1))  # 쇠구슬 Ø8 자리
    holes.append(cyl(p, (0, 0, 2.5), 2.2, 9))  # 바늘 허브 (루어 슬립)
    holes.append(cut(cyl(p, (0, 0, 10), 12, 4), cyl(p, (0, 0, 10), 10, 6)))  # 빛 고리 홈
    return cut(body, *holes)


def _mixer(p):
    """나선형 혼합기 4 요소 (Ø3 × 12 mm): 요소마다 비틀림 방향이 바뀌고 90° 엇갈림 (Kenics 꼴)."""
    z = p[2]
    k = np.clip(np.floor(z / 3.0), 0, 3)
    sgn = np.where(k % 2 == 0, 1.0, -1.0)
    ang = sgn * (z - 3 * k) / 3.0 * math.pi + k * math.pi / 2
    xr = p[0] * np.cos(ang) + p[1] * np.sin(ang)
    yr = -p[0] * np.sin(ang) + p[1] * np.cos(ang)
    ribbon = np.maximum(np.abs(yr) - 0.18, np.abs(xr) - 1.42)
    return np.maximum(ribbon, np.abs(z - 6) - 6)


def _syringe_pump(p):
    """주사기 펌프: 바닥판 + NEMA17 벽 + 주사기 받침(Ø20.2 반원) + 안내봉 구멍 2 + 날개 물림 홈."""
    base = box(p, (0, 0, 3), (130, 44, 6), 2)
    motor = box(p, (-60, 0, 25), (10, 44, 44), 2)
    cradle = box(p, (35, 0, 14), (50, 30, 22), 2)
    stop = box(p, (8, 0, 18), (6, 44, 30), 2)
    d = union(base, motor, cradle, stop)
    holes = [cyl(p, (-60, 0, 25), 11.5, 20, 0)] + [cyl(p, (-60, sy * 15.5, 25 + sz * 15.5), 1.7, 20, 0)
                                                   for sy in (-1, 1) for sz in (-1, 1)]
    holes += [cyl(p, (35, 0, 25), 10.1, 60, 0), box(p, (8, 0, 26), (8, 24, 3))]  # 주사기 몸통 받침 · 날개 물림
    holes += [cyl(p, (-20, sy * 15, 25), 2.1, 90, 0) for sy in (-1, 1)]  # M4 안내봉
    return cut(d, *holes)


def _pinch_valve(p):
    """핀치 밸브: 관 통로(Ø2.2) 를 서보 뿔이 눌러 막음."""
    d = box(p, (0, 0, 7.5), (30, 22, 15), 2)
    return cut(d, cyl(p, (0, 0, 5), 1.1, 40, 0), box(p, (0, 0, 12), (8, 24, 9)), cyl(p, (0, 8, 7.5), 1.5, 20, 2))


def _bath_base(p):
    """욕조 받침 160 × 160: 모서리 L 턱으로 아크릴 욕조 자리 + 배수 홈."""
    d = box(p, (0, 0, 2.5), (160, 160, 5), 3)
    ridges = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            ridges += [box(p, (sx * 70, sy * 60, 6), (4, 24, 4)), box(p, (sx * 60, sy * 70, 6), (24, 4, 4))]
    return cut(union(d, *ridges), box(p, (0, 0, 5), (100, 6, 3)))


def _port_panel(p):
    """단자판: 아날로그 BNC 8 · 양자 SMA 3 · USB-C · RJ45 — interfaces.PORTS."""
    d = union(box(p, (0, 0, 2), (170, 64, 4), 3), box(p, (0, 30, 8), (170, 4, 16)), box(p, (0, -30, 8), (170, 4, 16)))
    holes = [cyl(p, (-70 + i * 20, 12, 2), 4.85, 10) for i in range(8)]  # BNC Ø9.7
    holes += [cyl(p, (-70 + i * 18, -12, 2), 3.3, 10) for i in range(3)]  # SMA Ø6.6
    holes += [box(p, (10, -12, 2), (9.6, 3.6, 10), 1.2), box(p, (45, -12, 2), (16.5, 14.5, 10))]
    return cut(d, *holes)


def _electronics_box(p):
    """전자함 180 × 120 × 50 (위가 열림): 라즈베리파이 · Octopus · 아날로그 보드, 옆 환기 홈."""
    outer = box(p, (0, 0, 25), (180, 120, 50), 4)
    d = cut(outer, box(p, (0, 0, 28), (175, 115, 50), 2))
    vents = [box(p, (-60 + i * 12, 60, 25), (5, 10, 30), 1) for i in range(11)]
    return cut(d, *vents, box(p, (0, -60, 20), (160, 10, 24)))  # 앞은 단자판 자리


def _led_ring(p):
    """빛 고리: 펜 몸체 홈에 끼움, 405 nm LED 4개 (8×8) 가 아래로."""
    d = cut(cyl(p, (0, 0, 3), 17, 6), cyl(p, (0, 0, 3), 11.2, 8))
    return cut(d, *[box(p, (14 * math.cos(k * math.pi / 2), 14 * math.sin(k * math.pi / 2), 0.8), (8.2, 8.2, 2.4)) for k in range(4)])


def _scanner_mount(p):
    """스캐너: 레이저 선 모듈(Ø12) 과 카메라를 30° 로 — 펜 캐리지 옆."""
    d = union(box(p, (0, 0, 2), (60, 30, 4), 2), box(p, (-25, 0, 20), (10, 30, 40), 2), box(p, (25, 0, 20), (10, 30, 40), 2))
    return cut(d, cyl(p, (-25, 0, 30), 6.1, 20, 0), box(p, (25, 0, 30), (12, 24, 24)), cyl(p, (0, 0, 2), 1.7, 10))


def _belt_clamp(p):
    d = box(p, (0, 0, 4), (24, 12, 8), 2)
    return cut(d, box(p, (0, 0, 6.5), (26, 6.4, 1.6)), cyl(p, (-8, 0, 4), 1.7, 10), cyl(p, (8, 0, 4), 1.7, 10))


def printed_parts(spec: SculptorSpec | None = None) -> list[PrintedPart]:
    return [
        PrintedPart("corner", "프레임 꼭짓점", 8, "PETG", "M8 나사봉 상자 프레임 (RepRap)", (-18, -18, -18), (18, 18, 18), _corner),
        PrintedPart("motor_mount", "모터 받침 (NEMA17)", 5, "PETG", "XY 2 · Z 3", (-25, -25, 0), (25, 45, 20), _motor_mount),
        PrintedPart("pen_carriage", "펜 캐리지 (키네마틱 마운트)", 1, "PETG", "펜을 자석으로 붙이고 떼어 손으로", (-35, -31, 0), (35, 31, 18), _pen_carriage),
        PrintedPart("y_end", "X 봉 끝단", 2, "PETG", "CoreXY 의 Y 쪽 캐리지", (-20, -16, 0), (20, 16, 30), _y_end),
        PrintedPart("pen_body", "SNSS 펜 몸체", 1, "PETG (0.25 mm 노즐) 또는 레진", "GO · SNSS · PVA 세 통로 → 혼합기", (-17, -17, 0), (17, 17, 70), _pen_body, 0.25),
        PrintedPart("mixer", "나선형 혼합기 4 요소", 2, "레진 (SLA) — 없으면 0.2 mm 노즐 PETG", "펜 몸체 혼합기 구멍에 끼움", (-1.6, -1.6, 0), (1.6, 1.6, 12), _mixer, 0.06),
        PrintedPart("syringe_pump", "주사기 펌프", 3, "PETG", "GO · SNSS · PVA 원료", (-65, -22, 0), (65, 22, 47), _syringe_pump),
        PrintedPart("pinch_valve", "핀치 밸브", 3, "PETG", "GO 통 선택 (막용 · p형 · n형)", (-15, -11, 0), (15, 11, 15), _pinch_valve),
        PrintedPart("bath_base", "욕조 받침", 1, "PETG", "아크릴 욕조 자리", (-80, -80, 0), (80, 80, 8), _bath_base),
        PrintedPart("port_panel", "단자판 (아날로그 · 디지털 · 양자)", 1, "PETG", "BNC 8 · SMA 3 · USB-C · RJ45", (-85, -32, 0), (85, 32, 16), _port_panel),
        PrintedPart("electronics_box", "전자함", 1, "PETG", "파이 · 보드 · 아날로그 보드", (-90, -60, 0), (90, 60, 50), _electronics_box),
        PrintedPart("led_ring", "405 nm 빛 고리", 1, "PETG (검정)", "펜 끝 광환원", (-17, -17, 0), (17, 17, 6), _led_ring),
        PrintedPart("scanner_mount", "스캐너 받침", 1, "PETG", "레이저 선 + 카메라", (-30, -15, 0), (30, 15, 40), _scanner_mount),
        PrintedPart("belt_clamp", "벨트 물림", 2, "PETG", "GT2 벨트 끝", (-12, -6, 0), (12, 6, 8), _belt_clamp),
    ]


def mesh_part(part: PrintedPart) -> tuple[np.ndarray, np.ndarray, float]:
    """→ (꼭짓점, 삼각형, 실체 부피 cm³)."""
    from .mesh import surface_nets

    size = max(part.size)
    res = part.res or max(0.4, size / 200)  # FDM 노즐 0.4 mm — 더 곱게 해도 출력은 같음
    pad = 2 * res
    axes = [np.arange(l - pad, h + pad + res, res) for l, h in zip(part.lo, part.hi)]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    f = part.sdf((X, Y, Z)).astype(np.float32)
    v, t = surface_nets(f, (res, res, res), (axes[0][0], axes[1][0], axes[2][0]))
    from .mesh import signed_volume

    vol = abs(signed_volume(v, t)) / 1000  # 칸 세기(계단)보다 면에서 잰 부피가 정확
    return v, t, vol


def write_parts(folder: str | Path) -> list[dict]:
    """부품마다 STL + 목록(parts.csv) + 살 것(buy.csv)."""
    from .mesh import write_stl
    from .printer import bom

    folder = Path(folder)
    (folder / "stl").mkdir(parents=True, exist_ok=True)
    rows = []
    for part in printed_parts():
        v, t, vol = mesh_part(part)
        write_stl(folder / "stl" / f"{part.key}.stl", v, t, f"SC-1 {part.key}")
        grams = vol * PETG_G_CM3 * FILL * part.qty
        rows.append({"key": part.key, "name": part.name, "qty": part.qty, "material": part.material, "role": part.role,
                     "size_mm": [round(x, 1) for x in part.size], "volume_cm3": round(vol, 2), "grams": round(grams, 1),
                     "hours": round(grams / G_PER_H, 1), "fits": part.fits(), "triangles": len(t),
                     "stl": f"stl/{part.key}.stl"})
    (folder / "parts.csv").write_text("부품,수량,재료,크기 mm,실체 cm³,필라멘트 g(전체),출력 h(전체),베드 220 들어감,용도\n" + "\n".join(
        f"{r['name']},{r['qty']},{r['material']},{'×'.join(str(x) for x in r['size_mm'])},{r['volume_cm3']},{r['grams']},"
        f"{r['hours']},{'예' if r['fits'] else '아니오'},{r['role']}" for r in rows) + "\n", encoding="utf-8")
    (folder / "buy.csv").write_text("구분,품목,수량,사양,구입처\n" + "\n".join(
        f"{b.group},{b.part},{b.qty},\"{b.spec}\",{b.where}" for b in bom()) + "\n", encoding="utf-8")
    return rows


def describe(rows: list[dict]) -> str:
    g = sum(r["grams"] for r in rows)
    h = sum(r["hours"] for r in rows)
    lines = [f"[SC-1 출력 부품 — 부모 프린터 (베드 {PARENT_BED_MM[0]:g}×{PARENT_BED_MM[1]:g}) 로 뽑음]"]
    for r in rows:
        lines.append(f"  {r['name']:<22} ×{r['qty']} {r['material']:<10} {'×'.join(f'{x:g}' for x in r['size_mm']):>16} mm · "
                     f"{r['grams']:6.1f} g · {r['hours']:4.1f} h{'' if r['fits'] else '  ← 베드보다 큼'}")
    lines.append(f"  합계 PETG 약 {g:.0f} g · 출력 약 {h:.0f} h (부품 {sum(r['qty'] for r in rows)}개)")
    return "\n".join(lines)
