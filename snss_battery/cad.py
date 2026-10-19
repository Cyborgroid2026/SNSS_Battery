"""실물 설계: 생리식염수병 안에서 결정화된 결정 배터리 — 병 절단, 결정 블록, 측정 접점.

좌표계 (단위 mm): Z = 병 높이 방향 (병 바닥 바깥면 z=0), X·Y = 단면.
세포형 결정 도메인 층은 Z 방향으로 쌓이고(바닥이 1번 층), 결정의 아래·위 면이 그대로 단자면.
별도 전극 부품은 없다. 멀티미터 프로브는 측정 장비로만 표시한다.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .bottle import BottleGelBattery
from .materials import AuditLine, audit

Tri = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]

SEG = 64  # 원주 분할 수


@dataclass
class BottleDesignParams:
    cut_margin_mm: float = 5.0  # 결정 윗면 ~ 절단선 A
    probe_length_mm: float = 40.0  # 표시용 멀티미터 프로브 길이

    def __post_init__(self) -> None:
        for k, v in self.__dict__.items():
            if v <= 0:
                raise ValueError(f"{k}은(는) 양수여야 합니다.")


@dataclass
class BomItem:
    no: int
    name: str
    material: str
    qty: str
    spec: str
    elements: frozenset[str] = field(default_factory=frozenset)
    in_battery: bool = True  # 최종 배터리에 남는지 (병은 잘라 버림)


@dataclass
class Solid:
    name: str
    kind: str
    triangles: list[Tri]


class BottleDesign:
    def __init__(self, battery: BottleGelBattery, params: BottleDesignParams | None = None) -> None:
        self.battery = battery
        self.p = params or BottleDesignParams()
        if self.cut_z > battery.bottle.body_height_mm:
            raise ValueError("절단선이 병 어깨보다 위에 있습니다. 절단 여유를 줄이세요.")

    # ---------- 치수 ----------
    @property
    def gel_bottom_z(self) -> float:
        return self.battery.bottle.wall_mm

    @property
    def gel_top_z(self) -> float:
        return self.gel_bottom_z + self.battery.gel_height_mm

    @property
    def block_height(self) -> float:
        """다듬은 뒤 겔 블록 높이 = 인공세포 층 높이."""
        return self.battery.active_height_mm

    @property
    def cut_z(self) -> float:
        return self.gel_top_z + self.p.cut_margin_mm

    @property
    def gel_radius(self) -> float:
        return self.battery.gel_diameter_mm / 2

    def layer_bands(self) -> list[tuple[float, float, str]]:
        """(z0, z1, 'a'|'b') — 다듬은 겔 블록 기준 (블록 바닥 z=0)."""
        s = self.battery.stack
        t = s.geometry.compartment_thickness_mm
        tm_c, tm_a = s.cem.thickness_um / 1000, s.aem.thickness_um / 1000
        z, out = 0.0, []
        for _ in range(s.n_pairs):
            out.append((z, z + t, "a"))
            z += t + tm_c
            out.append((z, z + t, "b"))
            z += t + tm_a
        return out

    # ---------- BOM ----------
    def bom(self) -> list[BomItem]:
        b, f, bt = self.battery.bottle, self.battery.formation, self.battery
        s = bt.stack
        return [
            BomItem(1, "멸균생리식염수 0.9 %", "NaCl 수용액", "1병", f"{b.fill_volume_ml:g} mL (약국 판매품)",
                    frozenset({"Na", "Cl", "H", "O"})),
            BomItem(2, "그래핀 폴리머 액정 (GO)", "GO", f"{bt.go_mass_g:.2f} g",
                    f"병 내 {f.go_mg_per_ml:g} mg/mL", s.cem.elements),
            BomItem(3, "반응 화학물질", "레시피", "레시피",
                    f.reactants or "함께 부어 결정화를 일으킴 (입력 대기)", s.aem.elements),
            BomItem(4, "식염수병 (반응 용기)", "PE", "1개", "결정화 후 절단·제거", frozenset({"C", "H"}), False),
            BomItem(5, "멀티미터 + 프로브", "측정 장비", "1조", "전지 부품 아님 (측정용)", frozenset(), False),
        ]

    def audit(self) -> list[AuditLine]:
        """최종 결정 배터리에 남는 재료만 검사 (병·측정 장비 제외)."""
        return audit([(b.name, b.elements, b.material == "NaCl 수용액") for b in self.bom() if b.in_battery])

    def mass_g(self) -> float:
        """결정 블록 (물 + 염 + GO 근사)."""
        bt = self.battery
        gel_ml = bt.gel_area_cm2 * self.block_height / 10
        return gel_ml * 1.005 + bt.go_mass_g * self.block_height / bt.gel_height_mm

    def summary(self) -> str:
        bt = self.battery
        return "\n".join([
            f"결정 블록: Ø{bt.gel_diameter_mm:.1f} × {self.block_height:.1f} mm (다듬기 전 {bt.gel_height_mm:.1f} mm), "
            f"질량 약 {self.mass_g():.0f} g",
            f"절단선 A: 병 바닥에서 {self.cut_z:.1f} mm, 세로 절개선 B 2줄",
            "단자: 결정 아래면(-)·윗면(+) 자체 (별도 전극 없음, 프로브로 측정)",
        ])

    # ---------- 3D ----------
    def solids(self) -> list[Solid]:
        """꺼낸 결정 블록 (블록 바닥 z=0) + 표시용 프로브 2개."""
        h, L = self.block_height, self.p.probe_length_mm
        return [
            Solid("결정 블록", "crystal", _cylinder_z(0, h, self.gel_radius)),
            Solid("프로브 (-)", "probe", _cylinder_z(-L, 0, 1.0, 16)),
            Solid("프로브 (+)", "probe", _cylinder_z(h, h + L, 1.0, 16)),
        ]

    def bottle_solids(self) -> list[Solid]:
        """식염수병: 절단선 A 아래 컵(세로 절개 B로 두 쪽), 위쪽, 뚜껑. 병 바닥 바깥 z=0."""
        b = self.battery.bottle
        ro, w = b.outer_diameter_mm / 2, b.wall_mm
        cut = self.cut_z
        neck_r = b.neck_diameter_mm / 2
        z_sh = b.body_height_mm
        z_top = z_sh + b.shoulder_height_mm + b.neck_height_mm
        upper = [(ro, cut), (ro, z_sh)]
        for k in range(1, 9):  # 어깨: 둥근 테이퍼
            t = k / 8
            upper.append((neck_r + (ro - neck_r) * math.cos(t * math.pi / 2), z_sh + b.shoulder_height_mm * t))
        upper.append((neck_r, z_top))
        slit = 3.0  # 절개선 B 폭 (deg)
        out = []
        for name, a0, a1 in (("병 아래 (왼쪽)", 90 + slit, 270 - slit), ("병 아래 (오른쪽)", -90 + slit, 90 - slit)):
            tris = _revolve([(ro, 0.0), (ro, cut)], w, a0, a1)
            tris += _disc_sector(0.0, w, ro - w, a0, a1)
            out.append(Solid(name, "bottle_lower", tris))
        out.append(Solid("병 위", "bottle_upper", _revolve(upper, w, 0, 360)))
        out.append(Solid("뚜껑", "cap", _cylinder_z(z_top, z_top + b.cap_height_mm, b.cap_diameter_mm / 2)))
        return out

    # ---------- 내보내기 ----------
    def write_stls(self, folder: str | Path) -> list[Path]:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        parts = {
            "crystal_block.stl": self.solids()[0].triangles,
            "saline_bottle_cut.stl": [t for s in self.bottle_solids() for t in s.triangles],
        }
        paths = []
        for name, tris in parts.items():
            _write_binary_stl(folder / name, tris)
            paths.append(folder / name)
        return paths

    def write_openscad(self, path: str | Path) -> None:
        b = self.battery.bottle
        src = f"""// SNSS 생리식염수병 결정 배터리 — 자동 생성 (snss_battery.cad). 단위 mm
$fn = 96;
bottle_d    = {b.outer_diameter_mm};
wall        = {b.wall_mm};
crystal_d   = {self.battery.gel_diameter_mm:.3f};
crystal_h   = {self.block_height:.3f};  // 다듬은 결정 블록 (세포형 도메인 {2 * self.battery.stack.n_pairs}층)
cut_z       = {self.cut_z:.3f};         // 절단선 A (병 바닥에서)
show_bottle = true;

// 꺼낸 결정 블록 (아래면 = -, 윗면 = +)
color("steelblue", 0.9) cylinder(d = crystal_d, h = crystal_h);
// 절단선 A 아래 병 컵 (참고용)
if (show_bottle) translate([0, 0, -wall]) color("white", 0.25) difference() {{
    cylinder(d = bottle_d, h = cut_z);
    translate([0, 0, wall]) cylinder(d = bottle_d - 2 * wall, h = cut_z);
}}
"""
        Path(path).write_text(src, encoding="utf-8")

    def write_bom_csv(self, path: str | Path) -> None:
        import csv

        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.writer(fp)
            w.writerow(["번호", "품명", "재질", "수량", "규격", "구성 원소", "최종 배터리 포함"])
            for b in self.bom():
                w.writerow([b.no, b.name, b.material, b.qty, b.spec, ",".join(sorted(b.elements)),
                            "예" if b.in_battery else "아니오(제거)"])


# ---------- 메쉬 프리미티브 ----------
def _quad(a, b, c, d) -> list[Tri]:
    return [(a, b, c), (a, c, d)]


def _box(x0, x1, y0, y1, z0, z1) -> list[Tri]:
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    out: list[Tri] = []
    for a, b, c, d in faces:
        out += _quad(v[a], v[b], v[c], v[d])
    return out


def _cylinder_z(z0, z1, r, seg=SEG) -> list[Tri]:
    pts = [(r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
    out: list[Tri] = []
    for k in range(seg):
        (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % seg]
        out += _quad((x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1))
        out.append(((0, 0, z0), (x1, y1, z0), (x0, y0, z0)))
        out.append(((0, 0, z1), (x0, y0, z1), (x1, y1, z1)))
    return out


def _revolve(profile, wall, a0_deg, a1_deg, seg=SEG) -> list[Tri]:
    """(r, z) 바깥 윤곽을 두께 wall 의 껍질로 회전. 부분 각도면 잘린 면도 닫음."""
    full = math.isclose(a1_deg - a0_deg, 360)
    n = seg if full else max(4, int(seg * (a1_deg - a0_deg) / 360))
    angs = [math.radians(a0_deg + (a1_deg - a0_deg) * k / n) for k in range(n if full else n + 1)]

    def ring(r, z):
        return [(r * math.cos(a), r * math.sin(a), z) for a in angs]

    outer = [ring(r, z) for r, z in profile]
    inner = [ring(max(r - wall, 0.1), z) for r, z in profile]
    m = len(angs)
    steps = range(m) if full else range(m - 1)
    out: list[Tri] = []
    for i in range(len(profile) - 1):
        for k in steps:
            j = (k + 1) % m
            out += _quad(outer[i][k], outer[i][j], outer[i + 1][j], outer[i + 1][k])
            out += _quad(inner[i][k], inner[i + 1][k], inner[i + 1][j], inner[i][j])
    for i, flip in ((0, True), (len(profile) - 1, False)):  # 위·아래 테두리
        for k in steps:
            j = (k + 1) % m
            q = (outer[i][k], inner[i][k], inner[i][j], outer[i][j])
            out += _quad(*q) if flip else _quad(q[0], q[3], q[2], q[1])
    if not full:  # 절개면
        for k in (0, m - 1):
            for i in range(len(profile) - 1):
                out += _quad(outer[i][k], inner[i][k], inner[i + 1][k], outer[i + 1][k])
    return out


def _disc_sector(z0, z1, r, a0_deg, a1_deg, seg=SEG) -> list[Tri]:
    n = max(4, int(seg * (a1_deg - a0_deg) / 360))
    pts = [(r * math.cos(math.radians(a0_deg + (a1_deg - a0_deg) * k / n)),
            r * math.sin(math.radians(a0_deg + (a1_deg - a0_deg) * k / n))) for k in range(n + 1)]
    out: list[Tri] = []
    for k in range(n):
        (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        out.append(((0, 0, z0), (x1, y1, z0), (x0, y0, z0)))
        out.append(((0, 0, z1), (x0, y0, z1), (x1, y1, z1)))
        out += _quad((x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1))
    for (x, y) in (pts[0], pts[-1]):
        out += _quad((0, 0, z0), (x, y, z0), (x, y, z1), (0, 0, z1))
    return out


def _normal(t: Tri) -> tuple[float, float, float]:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / ln, ny / ln, nz / ln


def _write_binary_stl(path: str | Path, tris: list[Tri]) -> None:
    with open(path, "wb") as fp:
        fp.write(b"SNSS saline-bottle gel battery (mm)".ljust(80, b" "))
        fp.write(struct.pack("<I", len(tris)))
        for t in tris:
            fp.write(struct.pack("<3f", *_normal(t)))
            for v in t:
                fp.write(struct.pack("<3f", *v))
            fp.write(b"\0\0")
