"""2D 기술 도면 — 같은 도면을 DXF(R12)와 matplotlib(PDF/PNG)로 출력.

용지 좌표 단위는 mm (A3 가로 420 × 297).
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field
from pathlib import Path

from .cad import BottleDesign
from .materials import format_audit

# 레이어: (DXF 색상 번호, 선 종류, matplotlib 색, 선 굵기 pt, matplotlib 선 스타일)
LAYERS = {
    "OUTLINE": (7, "CONTINUOUS", "#111111", 1.0, "-"),
    "HIDDEN": (8, "DASHED", "#555555", 0.6, (0, (4, 2))),
    "CENTER": (1, "CENTER", "#b03030", 0.4, (0, (10, 2, 2, 2))),
    "DIM": (3, "CONTINUOUS", "#1d5fa8", 0.4, "-"),
    "TEXT": (7, "CONTINUOUS", "#111111", 0.4, "-"),
    "HATCH": (8, "CONTINUOUS", "#888888", 0.3, "-"),
    "THIN": (8, "CONTINUOUS", "#333333", 0.4, "-"),
    "BORDER": (7, "CONTINUOUS", "#111111", 1.4, "-"),
    "MEMBRANE_C": (30, "CONTINUOUS", "#e8833a", 1.2, "-"),
    "MEMBRANE_A": (94, "CONTINUOUS", "#3a9a5b", 1.2, "-"),
    "ELECTRODE": (250, "CONTINUOUS", "#222222", 1.2, "-"),
    "FILL_A": (254, "CONTINUOUS", "#d6e8f5", 0.2, "-"),
    "FILL_B": (151, "CONTINUOUS", "#7fb0dd", 0.2, "-"),
    "DEFECT": (1, "CONTINUOUS", "#d1263b", 1.4, "-"),
    "GRAIN": (8, "CONTINUOUS", "#6b7785", 0.3, "-"),
}



@dataclass
class Prim:
    kind: str  # line | circle | text | solid
    layer: str
    data: tuple


@dataclass
class Sheet:
    width: float = 420.0
    height: float = 297.0
    prims: list[Prim] = field(default_factory=list)

    # ---------- 기본 요소 ----------
    def line(self, x1, y1, x2, y2, layer="OUTLINE") -> None:
        self.prims.append(Prim("line", layer, (x1, y1, x2, y2)))

    def polyline(self, pts, layer="OUTLINE", closed=False) -> None:
        for (a, b), (c, d) in zip(pts, pts[1:] + (pts[:1] if closed else [])):
            self.line(a, b, c, d, layer)

    def rect(self, x0, y0, x1, y1, layer="OUTLINE") -> None:
        self.polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, closed=True)

    def circle(self, cx, cy, r, layer="OUTLINE") -> None:
        self.prims.append(Prim("circle", layer, (cx, cy, r)))

    def text(self, x, y, s, h=2.5, layer="TEXT", align="left", valign="baseline", rot=0.0) -> None:
        self.prims.append(Prim("text", layer, (x, y, s, h, align, valign, rot)))

    def solid(self, pts, layer="DIM") -> None:
        self.prims.append(Prim("solid", layer, tuple(pts)))

    # ---------- 도면 기호 ----------
    def arrow(self, x, y, angle, size=2.5, layer="DIM") -> None:
        """(x, y)를 가리키는 채운 화살촉. angle = 화살이 향하는 방향 (rad)."""
        bx, by = x - size * math.cos(angle), y - size * math.sin(angle)
        nx, ny = -math.sin(angle) * size * 0.18, math.cos(angle) * size * 0.18
        self.solid([(x, y), (bx + nx, by + ny), (bx - nx, by - ny)], layer)

    def dim_h(self, x1, x2, y_feat1, y_feat2, y_dim, label, h=2.5) -> None:
        """수평 치수. y_feat = 치수 보조선이 시작하는 형상 위치."""
        for x, yf in ((x1, y_feat1), (x2, y_feat2)):
            sgn = 1 if y_dim > yf else -1
            self.line(x, yf + sgn * 1.0, x, y_dim + sgn * 1.5, "DIM")
        self.line(x1, y_dim, x2, y_dim, "DIM")
        if abs(x2 - x1) > 7:
            self.arrow(x1, y_dim, math.pi)
            self.arrow(x2, y_dim, 0)
            self.text((x1 + x2) / 2, y_dim + 0.8, label, h, "DIM", "center")
        else:  # 좁은 치수는 화살표를 바깥에
            lo, hi = min(x1, x2), max(x1, x2)
            self.line(lo - 5, y_dim, lo, y_dim, "DIM")
            self.line(hi, y_dim, hi + 5, y_dim, "DIM")
            self.arrow(lo, y_dim, 0)
            self.arrow(hi, y_dim, math.pi)
            self.text(hi + 5.5, y_dim + 0.8, label, h, "DIM")

    def dim_v(self, y1, y2, x_feat1, x_feat2, x_dim, label, h=2.5) -> None:
        for y, xf in ((y1, x_feat1), (y2, x_feat2)):
            sgn = 1 if x_dim > xf else -1
            self.line(xf + sgn * 1.0, y, x_dim + sgn * 1.5, y, "DIM")
        self.line(x_dim, y1, x_dim, y2, "DIM")
        if abs(y2 - y1) > 7:
            self.arrow(x_dim, y1, -math.pi / 2)
            self.arrow(x_dim, y2, math.pi / 2)
            self.text(x_dim - 0.8, (y1 + y2) / 2, label, h, "DIM", "center", rot=90)
        else:
            lo, hi = min(y1, y2), max(y1, y2)
            self.line(x_dim, lo - 5, x_dim, lo, "DIM")
            self.line(x_dim, hi, x_dim, hi + 5, "DIM")
            self.arrow(x_dim, lo, math.pi / 2)
            self.arrow(x_dim, hi, -math.pi / 2)
            self.text(x_dim - 0.8, hi + 5.5, label, h, "DIM", "left", rot=90)

    def leader(self, x, y, tx, ty, label, h=2.5) -> None:
        """(x, y) 형상을 가리키는 지시선 + 설명."""
        self.line(tx, ty, x, y, "DIM")
        self.arrow(x, y, math.atan2(y - ty, x - tx), 2.0)
        right = tx >= x
        end = tx + (1 if right else -1) * (len(label) * h * 0.75 + 1)
        self.line(tx, ty, end, ty, "DIM")
        self.text(tx + (1 if right else -1), ty + 0.8, label, h, "TEXT", "left" if right else "right")

    def centerline_cross(self, cx, cy, r) -> None:
        self.line(cx - r, cy, cx + r, cy, "CENTER")
        self.line(cx, cy - r, cx, cy + r, "CENTER")

    def hatch_rect(self, x0, y0, x1, y1, spacing=1.5) -> None:
        """45° 단면 해칭."""
        if x1 - x0 <= 0 or y1 - y0 <= 0:
            return
        c = y0 - x1
        while c < y1 - x0:
            pts = []
            for x in (x0, x1):  # y = x + c 와 수직 변의 교점
                y = x + c
                if y0 <= y <= y1:
                    pts.append((x, y))
            for y in (y0, y1):
                x = y - c
                if x0 <= x <= x1:
                    pts.append((x, y))
            if len(pts) >= 2:
                pts.sort()
                self.line(*pts[0], *pts[-1], "HATCH")
            c += spacing

    def table(self, x, y_top, col_widths, rows, row_h=5.5, h=2.3, header=True) -> float:
        """좌상단 (x, y_top)에서 아래로 그리는 표. 하단 y 반환."""
        total = sum(col_widths)
        y = y_top
        self.line(x, y, x + total, y, "THIN")
        for r_i, row in enumerate(rows):
            cx = x
            for w, cell in zip(col_widths, row):
                s = _fit_text(str(cell), w - 2, h)
                self.text(cx + 1, y - row_h + 1.6, s, h)
                cx += w
            y -= row_h
            self.line(x, y, x + total, y, "OUTLINE" if header and r_i == 0 else "THIN")
        cx = x
        for w in [0] + col_widths:
            cx += w
            self.line(cx, y_top, cx, y, "THIN")
        return y

    # ---------- 출력 ----------
    def to_dxf(self, path: str | Path) -> None:
        Path(path).write_text(_dxf_r12(self), encoding="ascii")

    def render(self, ax) -> None:
        from matplotlib.patches import Circle, Polygon

        ax.set_xlim(0, self.width)
        ax.set_ylim(0, self.height)
        ax.set_aspect("equal")
        ax.set_axis_off()
        fig_w_in = ax.figure.get_size_inches()[0] * ax.get_position().width
        pt_per_mm = fig_w_in * 72 / self.width
        for p in self.prims:
            _, _, color, lw, ls = LAYERS.get(p.layer, LAYERS["THIN"])
            lw = lw * pt_per_mm / 2.835
            if p.kind == "line":
                x1, y1, x2, y2 = p.data
                ax.plot([x1, x2], [y1, y2], color=color, lw=lw, ls=ls, solid_capstyle="butt")
            elif p.kind == "circle":
                cx, cy, r = p.data
                ax.add_patch(Circle((cx, cy), r, fill=False, ec=color, lw=lw, ls=ls))
            elif p.kind == "solid":
                ax.add_patch(Polygon(p.data, closed=True, fc=color, ec=color, lw=0.25))
            elif p.kind == "text":
                x, y, s, h, align, valign, rot = p.data
                va = {"baseline": "baseline", "middle": "center", "top": "top"}[valign]
                ax.text(x, y, s, fontsize=h * pt_per_mm / 0.72, ha=align, va=va, rotation=rot,
                        color=color if p.layer == "DIM" else "#111111", rotation_mode="anchor")

    def save_pdf(self, path: str | Path, dpi: int = 200) -> None:
        from matplotlib.figure import Figure

        setup_fonts()
        fig = Figure(figsize=(self.width / 25.4, self.height / 25.4))
        ax = fig.add_axes([0, 0, 1, 1])
        self.render(ax)
        fig.savefig(path, dpi=dpi)


def _text_width(s: str, h: float) -> float:
    return sum(h * (1.15 if ord(c) > 0x2E80 else 0.62) for c in s)


def _fit_text(s: str, width: float, h: float) -> str:
    if _text_width(s, h) <= width:
        return s
    while s and _text_width(s + "…", h) > width:
        s = s[:-1]
    return s + "…"


# ---------- DXF R12 ----------
def setup_fonts() -> None:
    """한글 글꼴 + 기호(µ, ✔ 등)용 대체 글꼴."""
    import matplotlib
    from matplotlib import font_manager

    names = {f.name for f in font_manager.fontManager.ttflist}
    family = [c for c in ("NanumGothic", "NanumBarunGothic", "Noto Sans CJK KR", "Noto Sans CJK JP",
                          "Noto Sans KR", "Malgun Gothic", "AppleGothic") if c in names][:1]
    matplotlib.rcParams["font.family"] = family + ["DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["mathtext.fontset"] = "dejavusans"
    matplotlib.rcParams.update({  # 웹·GUI 그림 공통 스타일 (기본 matplotlib 느낌 줄이기)
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#9aa7b4",
        "axes.labelcolor": "#14202b", "axes.titleweight": "bold", "axes.titlesize": 11,
        "xtick.color": "#5d6673", "ytick.color": "#5d6673", "grid.color": "#e6ebf0",
        "axes.prop_cycle": matplotlib.cycler(color=["#2f6db5", "#23a06b", "#f28c38", "#e0344b", "#7a5af8"]),
        "figure.facecolor": "white", "savefig.facecolor": "white", "legend.frameon": False,
    })


def _dxf_text(s: str) -> str:
    return "".join(c if 32 <= ord(c) < 127 else f"\\U+{ord(c):04X}" for c in s)


def _dxf_r12(sheet: Sheet) -> str:
    out: list[str] = []

    def g(code, value) -> None:
        out.append(f"{code:>3}")
        out.append(f"{value:.6f}" if isinstance(value, float) else str(value))

    g(0, "SECTION"); g(2, "HEADER")
    g(9, "$ACADVER"); g(1, "AC1009")
    g(9, "$INSUNITS"); g(70, 4)
    g(9, "$MEASUREMENT"); g(70, 1)
    g(9, "$EXTMIN"); g(10, 0.0); g(20, 0.0); g(30, 0.0)
    g(9, "$EXTMAX"); g(10, float(sheet.width)); g(20, float(sheet.height)); g(30, 0.0)
    g(9, "$LTSCALE"); g(40, 1.0)
    g(0, "ENDSEC")

    g(0, "SECTION"); g(2, "TABLES")
    ltypes = [
        ("CONTINUOUS", "Solid line", []),
        ("DASHED", "__ __ __", [3.0, -1.5]),
        ("CENTER", "____ _ ____", [8.0, -1.5, 1.5, -1.5]),
    ]
    g(0, "TABLE"); g(2, "LTYPE"); g(70, len(ltypes))
    for name, desc, pat in ltypes:
        g(0, "LTYPE"); g(2, name); g(70, 0); g(3, desc); g(72, 65); g(73, len(pat))
        g(40, float(sum(abs(v) for v in pat)))
        for v in pat:
            g(49, float(v))
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "LAYER"); g(70, len(LAYERS))
    for name, (color, ltype, *_rest) in LAYERS.items():
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, color); g(6, ltype)
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "STYLE"); g(70, 1)
    g(0, "STYLE"); g(2, "STANDARD"); g(70, 0); g(40, 0.0); g(41, 1.0); g(50, 0.0); g(71, 0)
    g(42, 2.5); g(3, "malgun.ttf"); g(4, "")
    g(0, "ENDTAB")
    g(0, "ENDSEC")

    g(0, "SECTION"); g(2, "ENTITIES")
    for p in sheet.prims:
        if p.kind == "line":
            x1, y1, x2, y2 = p.data
            g(0, "LINE"); g(8, p.layer)
            g(10, float(x1)); g(20, float(y1)); g(30, 0.0); g(11, float(x2)); g(21, float(y2)); g(31, 0.0)
        elif p.kind == "circle":
            cx, cy, r = p.data
            g(0, "CIRCLE"); g(8, p.layer); g(10, float(cx)); g(20, float(cy)); g(30, 0.0); g(40, float(r))
        elif p.kind == "solid":
            pts = list(p.data) + [p.data[-1]] * (4 - len(p.data))
            g(0, "SOLID"); g(8, p.layer)
            # SOLID 꼭짓점 순서: 1, 2, 4, 3 (Z자)
            for (code, (x, y)) in zip((10, 11, 12, 13), (pts[0], pts[1], pts[3], pts[2])):
                g(code, float(x)); g(code + 10, float(y)); g(code + 20, 0.0)
        elif p.kind == "text":
            x, y, s, h, align, valign, rot = p.data
            g(0, "TEXT"); g(8, p.layer); g(10, float(x)); g(20, float(y)); g(30, 0.0)
            g(40, float(h)); g(1, _dxf_text(s)); g(50, float(rot)); g(7, "STANDARD")
            ha = {"left": 0, "center": 1, "right": 2}[align]
            va = {"baseline": 0, "middle": 2, "top": 3}[valign]
            if ha or va:
                g(72, ha); g(73, va); g(11, float(x)); g(21, float(y)); g(31, 0.0)
    g(0, "ENDSEC")
    g(0, "EOF")
    return "\n".join(out) + "\n"


# ---------- 조립도: 병 결정화 → 절단 → 겔 배터리 ----------
def _scale_label(s: float) -> str:
    return f"{s:g}:1" if s >= 1 else f"1:{1 / s:g}"


def _bottle_profile(d: BottleDesign) -> list[tuple[float, float]]:
    b = d.battery.bottle
    ro, rn = b.outer_diameter_mm / 2, b.neck_diameter_mm / 2
    pts = [(ro, 0.0), (ro, b.body_height_mm)]
    for k in range(1, 9):
        t = k / 8
        pts.append((rn + (ro - rn) * math.cos(t * math.pi / 2), b.body_height_mm + b.shoulder_height_mm * t))
    pts.append((rn, b.body_height_mm + b.shoulder_height_mm + b.neck_height_mm))
    return pts


def assembly_sheet(d: BottleDesign, drawing_no: str = "SNSS-GEL-001") -> Sheet:
    sh = Sheet()
    bt, b = d.battery, d.battery.bottle
    s = 1.0 if 74 + b.total_height_mm <= 283 and b.outer_diameter_mm <= 90 else 0.5
    sh.rect(10, 10, sh.width - 10, sh.height - 10, "BORDER")
    ro, ri, rg = b.outer_diameter_mm / 2, b.inner_diameter_mm / 2, d.gel_radius
    pair_mm = bt.active_height_mm / bt.stack.n_pairs

    # ===== ① 결정화 중인 병 (정면, 중심 단면) =====
    c1 = 30 + ro * s + 12
    y0 = 74

    def B(x, z):
        return c1 + x * s, y0 + z * s

    prof = _bottle_profile(d)
    for sgn in (-1, 1):
        sh.polyline([B(sgn * r, z) for r, z in prof])
        sh.polyline([B(sgn * (r - b.wall_mm), max(z, b.wall_mm)) for r, z in prof[:2]], "THIN")
    sh.line(*B(-ro, 0), *B(ro, 0))
    sh.line(*B(-ri, b.wall_mm), *B(ri, b.wall_mm), "THIN")
    z_neck_top = prof[-1][1]
    rn, rc = b.neck_diameter_mm / 2, b.cap_diameter_mm / 2
    sh.line(*B(-rn, z_neck_top), *B(rn, z_neck_top))
    sh.rect(*B(-rc, z_neck_top), *B(rc, z_neck_top + b.cap_height_mm))
    # 겔 + 층 (10쌍마다 한 줄)
    gz0, gz1 = d.gel_bottom_z, d.gel_top_z
    sh.rect(*B(-rg, gz0), *B(rg, gz1), "OUTLINE")
    step = max(1, bt.stack.n_pairs // 13)
    for k in range(step, bt.stack.n_pairs, step):
        z = gz0 + k * pair_mm
        sh.line(*B(-rg, z), *B(rg, z), "HATCH")
    sh.text(*B(0, (gz0 + gz1) / 2 + 4), "결정 (세포형 도메인층)", 3.0, align="center")
    sh.text(*B(0, (gz0 + gz1) / 2 - 3), f"{2 * bt.stack.n_pairs}층, 선은 {step}쌍마다", 2.2, align="center")
    # 절단선 A, 절개선 B
    for x0_, x1_ in ((-ro - 9, ro + 9),):
        sh.line(*B(x0_, d.cut_z), *B(x1_, d.cut_z), "CENTER")
    for sgn in (-1, 1):
        ax_, ay_ = B(sgn * (ro + 9), d.cut_z)
        sh.text(ax_ + sgn * 1.5, ay_ + 1.2, "A", 3.5, align="left" if sgn > 0 else "right")
    sh.line(*B(0, 0), *B(0, d.cut_z), "CENTER")
    sh.leader(*B(0, d.cut_z * 0.25), *B(ro + 12, d.cut_z * 0.12), "절개선 B (앞·뒤 2줄)", 2.4)
    sh.leader(*B(ro, d.cut_z), *B(ro + 12, d.cut_z + 22), "절단선 A", 2.4)
    # 치수
    bx = B(-ro, 0)[0]
    sh.dim_v(*[B(0, 0)[1], B(0, d.cut_z)[1]], bx, bx, bx - 7, f"{d.cut_z:.1f}")
    sh.dim_v(B(0, gz0)[1], B(0, gz1)[1], B(-rg, 0)[0], B(-rg, 0)[0], bx - 15, f"{bt.gel_height_mm:.1f} (결정)")
    sh.dim_v(B(0, 0)[1], B(0, z_neck_top + b.cap_height_mm)[1], bx, B(-rc, 0)[0], bx - 23,
             f"{b.total_height_mm:.0f}")
    sh.dim_h(B(-ro, 0)[0], B(ro, 0)[0], B(0, 0)[1], B(0, 0)[1], B(0, 0)[1] - 7, f"Ø{b.outer_diameter_mm:g}")
    sh.text(c1, y0 - 14, f"① 결정화 ({b.fill_volume_ml:g} mL 병, {_scale_label(s)})", 3.3, align="center")

    # ===== ② 꺼낸 결정 배터리 + 측정 =====
    c2 = c1 + ro * s + 45 + rg * s
    y2 = 112
    h = d.block_height
    probe = 14 / s

    def G(x, z):
        return c2 + x * s, y2 + z * s

    sh.rect(*G(-rg, 0), *G(rg, h))
    for k in range(step, bt.stack.n_pairs, step):
        sh.line(*G(-rg, k * pair_mm), *G(rg, k * pair_mm), "HATCH")
    sh.line(*G(-rg, 0), *G(rg, 0), "ELECTRODE")
    sh.line(*G(-rg, h), *G(rg, h), "ELECTRODE")
    # 프로브 + 전압계 (측정 장비)
    vx, vy = G(rg + 20, h / 2)
    sh.rect(vx - 9, vy - 6, vx + 9, vy + 6, "THIN")
    sh.text(vx, vy + 1, "V", 4.0, align="center")
    sh.text(vx, vy - 4.5, f"≈{bt.stack.open_circuit_voltage():.1f} V", 2.4, align="center")
    for z, label, yy in ((0, "(-)", vy - 6), (h, "(+)", vy + 6)):
        px, py = G(0, z)
        tip = py - 1.5 if z == 0 else py + 1.5
        end = py - probe * s if z == 0 else py + probe * s
        sh.circle(px, tip, 1.2, "OUTLINE")
        sh.line(px, tip + (-1.2 if z == 0 else 1.2), px, end, "OUTLINE")
        sh.polyline([(px, end), (vx, end), (vx, yy)], "THIN")
        sh.text(px - 2, end + (-3.5 if z == 0 else 1.2), f"{label} 프로브", 2.4, align="right")
    sh.text(vx + 11, vy - 1, "멀티미터", 2.4)
    sh.text(vx + 11, vy - 4.5, "(측정 장비)", 2.1)
    sh.leader(*G(rg * 0.4, h - 0.3), *G(rg + 6, h + 8), "윗면 = (+) 단자면 (그래핀 농축)", 2.3)
    sh.leader(*G(-rg * 0.4, 0.3), *G(-rg - 4, -9), "아래면 = (-) 단자면", 2.3)
    sh.dim_h(G(-rg, 0)[0], G(rg, 0)[0], G(0, 0)[1], G(0, 0)[1], G(0, 0)[1] - probe * s - 11,
             f"Ø{bt.gel_diameter_mm:.1f}")
    sh.dim_v(G(0, 0)[1], G(0, h)[1], G(-rg, 0)[0], G(-rg, 0)[0], G(-rg, 0)[0] - 7, f"{h:.1f}")
    cx, cy = G(-rg + 6, 2)
    sh.circle(cx, cy, 7, "THIN")
    sh.text(cx - 9, cy + 4, "C", 3.5)
    sh.text(c2, y2 - probe * s - 23, f"② 병에서 꺼낸 결정 + 측정 ({_scale_label(s)})", 3.3, align="center")

    # ===== ③ 상면도 =====
    c3x, c3y = 318, 246
    k3 = s * 0.8
    sh.circle(c3x, c3y, rg * k3)
    sh.circle(c3x, c3y, 1.2)
    sh.centerline_cross(c3x, c3y, rg * k3 + 3)
    sh.leader(c3x + 1, c3y + 1, c3x + rg * k3 + 4, c3y + rg * k3 * 0.6, "(+) 프로브 접점", 2.3)
    sh.dim_h(c3x - rg * k3, c3x + rg * k3, c3y - rg * k3, c3y - rg * k3, c3y - rg * k3 - 5,
             f"Ø{bt.gel_diameter_mm:.1f}")
    sh.text(c3x, c3y + rg * k3 + 6, f"③ 상면도 ({_scale_label(k3)})", 3.3, align="center")

    try:
        _detail_voronoi(sh, d, 272, 104, 410, 205)
    except ImportError:  # numpy/scipy 가 없으면 단순 층 그림
        _detail_layers(sh, d, 272, 104, 410, 205)
    _bom_and_title(sh, d, s, drawing_no)

    st = bt.stack
    notes = [
        "실험 순서",
        f"1. 약국 생리식염수 {b.fill_volume_ml:g} mL 병 개봉 (뚜껑 보관).",
        f"2. 그래핀 폴리머 액정 {bt.go_mass_g:.2f} g ({bt.formation.go_mg_per_ml:g} mg/mL)과 반응 화학물질을 병에 부음.",
        "3. 병을 똑바로 세운 채 결정화 (흔들지 말 것: 도메인이 병 높이 방향으로 층을 이뤄야 전압이 더해짐).",
        f"4. 절단선 A(바닥에서 {d.cut_z:.0f} mm) 수평 절단, 절개선 B 2줄 세로 절개 후 병 껍질 제거.",
        f"5. 윗면 자투리를 다듬어 블록 높이 {h:.1f} mm. 별도 전극 없음 — 결정 윗면·아래면이 단자.",
        f"6. 멀티미터 프로브를 윗면(+)·아래면(-) 중앙에 대고 개방전압 측정 (모델 예측 {st.open_circuit_voltage():.1f} V).",
        "7. 측정값은 웹 뷰어 '실험 기록'에 입력해 모델과 비교. 단위 mm, 층 두께는 상세 C에서 과장.",
    ]
    y = 52
    for i, n in enumerate(notes):
        sh.text(16, y, n, 3.0 if i == 0 else 2.3)
        y -= 4.6 if i == 0 else 4.1
    return sh


def _detail_layers(sh: Sheet, d: BottleDesign, x0, y0, x1, y1) -> None:
    st = d.battery.stack
    t = st.geometry.compartment_thickness_mm
    scale = 20 if t <= 0.6 else 10 if t <= 1.2 else 5
    mem = 0.7  # 막 표시 두께 (용지 mm)
    w = 48
    x = x0 + 4
    y = y0 + 12
    sh.line(x, y, x + w, y, "ELECTRODE")
    rows = [(y, "결정 아래면 = (-) 단자면 (그래핀 농축)")]
    for i in range(2):
        for name, conc, mname, layer in (
            (f"A{i + 1}", st.c_dilute * 1000, f"도메인 벽 (양이온 선택) {st.cem.thickness_um:g} µm", "MEMBRANE_C"),
            (f"B{i + 1}", st.c_concentrated * 1000, f"도메인 벽 (음이온 선택) {st.aem.thickness_um:g} µm", "MEMBRANE_A"),
        ):
            hh = t * scale
            sh.rect(x, y, x + w, y + hh, "THIN")
            if name.startswith("B"):
                sh.hatch_rect(x, y, x + w, y + hh, 2.2)
            sh.text(x + 3, y + hh / 2 - 1, name, 3.0)
            rows.append((y + hh / 2, f"도메인 {name}: NaCl {conc:.1f} mM ({'묽음' if name[0] == 'A' else '진함'})"))
            y += hh
            sh.rect(x, y, x + w, y + mem, layer)
            sh.line(x, y + mem / 2, x + w, y + mem / 2, layer)
            rows.append((y + mem / 2, mname))
            y += mem
    sh.line(x, y + 1.5, x + w, y + 1.5, "HIDDEN")
    sh.text(x + w / 2, y + 3, f"… 위로 {2 * st.n_pairs}층까지 (결정화로 저절로 생김)", 2.3, align="center")
    lx = x + w + 6
    for ry, label in rows:
        sh.line(x + w, ry, lx, ry, "DIM")
        sh.text(lx + 1, ry - 0.8, label, 2.2)
    sh.dim_v(y0 + 12, y0 + 12 + t * scale, x, x, x - 3, f"{t:g}")
    sh.text((x0 + x1) / 2, y0 + 2, f"상세 C: 결정 아래쪽 세포형 도메인 ({scale}:1, 벽 두께 과장)", 3.0, align="center")


def _detail_voronoi(sh: Sheet, d: BottleDesign, x0, y0, x1, y1) -> None:
    """상세 C: 결정 아래쪽의 실제 보로노이 도메인 단면 (프랙탈 층 경계 포함)."""
    from .tessellation import analyze_battery

    bt = d.battery
    t = bt.formation.layer_thickness_mm
    size = 60.0  # 용지 mm
    scale = 20 if t <= 0.6 else 10 if t <= 1.2 else 5
    win = size / scale
    layers = max(4, round(win / t))
    res = analyze_battery(bt, bt.fractal_params(window_layers=layers, window_width_mm=win, seed=3))
    ox, oy = x0 + 6, y0 + 14

    def P(x, z):
        return ox + x * scale, oy + z * scale

    zmax = min(res.window[1], win)
    from .plots import _poly_layers

    for poly, lay in zip(res.polygons, _poly_layers(res)):
        if poly[:, 1].min() > zmax:
            continue
        pts = [P(float(x), float(min(z, zmax))) for x, z in poly]
        for k in range(1, len(pts) - 1):
            sh.solid([pts[0], pts[k], pts[k + 1]], "FILL_A" if lay % 2 == 0 else "FILL_B")
    for kind, layer in (("same", "GRAIN"), ("cem", "MEMBRANE_C"), ("aem", "MEMBRANE_A"), ("defect", "DEFECT")):
        for (xa, za), (xb, zb) in res.segments.get(kind, []):
            if min(za, zb) > zmax:
                continue
            sh.line(*P(xa, min(za, zmax)), *P(xb, min(zb, zmax)), layer)
    sh.rect(*P(0, 0), *P(res.window[0], zmax), "OUTLINE")
    sh.line(*P(0, 0), *P(res.window[0], 0), "ELECTRODE")
    sh.dim_h(*[P(0, 0)[0], P(win, 0)[0]], P(0, 0)[1], P(0, 0)[1], P(0, 0)[1] - 6, f"{win:g}")
    sh.dim_v(P(0, 0)[1], P(0, t)[1], P(0, 0)[0], P(0, 0)[0], P(0, 0)[0] - 3, f"{t:g}")
    lx, ly = P(win, 0)[0] + 5, P(0, zmax)[1] - 3
    legend = [("FILL_A", f"묽은 도메인 {bt.stack.c_dilute * 1000:.0f} mM"),
              ("FILL_B", f"진한 도메인 {bt.stack.c_concentrated * 1000:.0f} mM"),
              ("MEMBRANE_C", "양이온 선택 벽"), ("MEMBRANE_A", "음이온 선택 벽"),
              ("DEFECT", "결함 벽 (단락)"), ("GRAIN", "같은 층 도메인 벽"), ("ELECTRODE", "결정 아래면 (-)")]
    for k, (layer, label) in enumerate(legend):
        yy = ly - k * 5.2
        if layer.startswith("FILL"):
            sh.solid([(lx, yy - 1.5), (lx + 5, yy - 1.5), (lx + 5, yy + 1.5)], layer)
            sh.solid([(lx, yy - 1.5), (lx + 5, yy + 1.5), (lx, yy + 1.5)], layer)
        else:
            sh.line(lx, yy, lx + 5, yy, layer)
        sh.text(lx + 7, yy - 1, label, 2.2)
    f = bt.formation
    yy = ly - len(legend) * 5.2 - 2
    for k, line in enumerate((f"보로노이 도메인 {res.n_cells}개, 평균 이웃 {res.mean_neighbors:.1f}",
                              f"층 경계 프랙탈 D={f.interface_dimension:g} (실측 {res.fractal_dim_interfaces:.2f})",
                              f"거칠기 {f.interface_roughness:g}t, 결정핵 D={f.seed_dimension:g}")):
        sh.text(lx, yy - k * 4.2, line, 2.1)
    sh.text((x0 + x1) / 2, y0 + 2, f"상세 C: 결정 아래쪽 보로노이 도메인 단면 ({scale}:1)", 3.0, align="center")


def _bom_and_title(sh: Sheet, d: BottleDesign, s: float, drawing_no: str) -> None:
    x = 240
    cols = [9, 52, 34, 16, 59]
    rows = [["번호", "품명", "재질", "수량", "규격"]]
    rows += [[b.no, b.name, b.material, b.qty, b.spec] for b in reversed(d.bom())]
    y_title_top = 52
    y_bom_top = y_title_top + 5.5 * len(rows) + 2
    sh.text(x, y_bom_top + 2, "부품·재료표", 3.0)
    sh.table(x, y_bom_top, cols, rows)
    tw = sum(cols)
    sh.rect(x, 10, x + tw, y_title_top, "OUTLINE")
    sh.line(x, 38, x + tw, 38, "THIN")
    sh.line(x, 24, x + tw, 24, "THIN")
    sh.line(x + 85, 10, x + 85, 38, "THIN")
    sh.text(x + 3, 42, "SNSS 생리식염수 결정 배터리", 5.0)
    bt = d.battery
    sh.text(x + 3, 31, f"세포형 도메인 {2 * bt.stack.n_pairs}층 · 0.9% 생리식염수 · 금속 무함유", 2.6)
    sh.text(x + 3, 27, f"결정 Ø{bt.gel_diameter_mm:.1f}×{d.block_height:.1f} · {d.mass_g():.0f} g · "
                       f"{bt.stack.open_circuit_voltage():.1f} V", 2.6)
    verdict = "금속 무함유 ✔" if all(a.ok for a in d.audit()) else "금속 포함 ✘"
    sh.text(x + 3, 15, f"재질 검사: {verdict}", 2.8)
    sh.text(x + 88, 31, f"도면번호  {drawing_no}", 2.8)
    sh.text(x + 88, 27, f"척도  {_scale_label(s)}    단위  mm", 2.6)
    sh.text(x + 88, 18, f"작성일  {_dt.date.today().isoformat()}", 2.6)
    sh.text(x + 88, 13, "작성  snss_battery.drawing (자동 생성)", 2.2)


# ---------- 1:1 실물 템플릿 ----------
def cut_sheet(d: BottleDesign) -> Sheet:
    """1:1 인쇄용: 병에 감는 절단 가이드 띠."""
    b = d.battery.bottle
    circ = math.pi * b.outer_diameter_mm
    band_h = d.cut_z + 12
    sh = Sheet(width=circ + 30, height=band_h + 40)
    x0, y0 = 15, 18
    sh.rect(x0, y0, x0 + circ, y0 + band_h)
    cut_y = y0 + d.cut_z
    sh.line(x0, cut_y, x0 + circ, cut_y, "CENTER")
    sh.text(x0 + 3, cut_y + 1.5, f"절단선 A — 병 바닥에서 {d.cut_z:.1f} mm (띠 아래 변을 병 바닥에 맞춤)", 3.0)
    for frac in (0.25, 0.75):
        xs = x0 + circ * frac
        sh.line(xs, y0, xs, cut_y, "CENTER")
        sh.text(xs + 1.5, y0 + 4, "절개선 B", 2.6)
    sh.text(x0, y0 + band_h + 5, f"절단 가이드 띠 1:1 — 둘레 {circ:.1f} mm (Ø{b.outer_diameter_mm:g} 병에 감기)", 3.5)
    sh.text(x0, 8, f"SNSS 1:1 템플릿 (mm) — 배율 100 %로 인쇄 — {_dt.date.today().isoformat()}", 3.0)
    return sh


def export_all(d: BottleDesign, folder: str | Path) -> list[Path]:
    """도면(DXF/PDF/PNG), 1:1 템플릿, STL, OpenSCAD, 재료표 CSV."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    sheet = assembly_sheet(d)
    sheet.to_dxf(folder / "assembly_drawing.dxf")
    sheet.save_pdf(folder / "assembly_drawing.pdf")
    sheet.save_pdf(folder / "assembly_drawing.png", dpi=150)
    tpl = cut_sheet(d)
    tpl.to_dxf(folder / "template_1to1.dxf")
    tpl.save_pdf(folder / "template_1to1.pdf")
    out += [folder / n for n in ("assembly_drawing.dxf", "assembly_drawing.pdf", "assembly_drawing.png",
                                 "template_1to1.dxf", "template_1to1.pdf")]
    out += d.write_stls(folder / "stl")
    d.write_openscad(folder / "battery.scad")
    d.write_bom_csv(folder / "materials.csv")
    out += [folder / "battery.scad", folder / "materials.csv"]
    (folder / "README.txt").write_text(
        "SNSS 생리식염수 결정 배터리 — CAD 출력\n\n"
        "assembly_drawing.*  도면: ① 병 안 결정화 ② 꺼낸 결정 + 측정 ③ 상면도, 상세 C, 재료표, 실험 순서\n"
        "template_1to1.*     1:1 인쇄 템플릿: 병 절단 가이드 띠 (배율 100 % 인쇄)\n"
        "stl/                3D: 결정 블록, 절단된 병\n"
        "battery.scad        OpenSCAD 파라메트릭 모델\n"
        "materials.csv       재료표\n\n" + d.battery.describe() + "\n" + d.summary() + "\n\n"
        + format_audit(d.audit()) + "\n",
        encoding="utf-8",
    )
    out.append(folder / "README.txt")
    return out


def pour_guide_sheet(recipe, bottle_outer_mm: float = 72.0, wall_mm: float = 0.8) -> Sheet:
    """레시피 붓기 가이드 1:1 — 병에 감는 띠, 층마다 높이 눈금 (아래 변 = 병 바닥)."""
    circ = math.pi * bottle_outer_mm
    top_h = wall_mm + recipe.height_mm + 8
    sh = Sheet(width=circ + 40, height=top_h + 46)
    x0, y0 = 20, 22
    sh.rect(x0, y0, x0 + circ, y0 + top_h)
    z = wall_mm
    t_c, t_a = 0.005, 0.008
    for k in range(1, recipe.pairs + 1):
        for name, thick, layer, long in ((f"A{k}", recipe.layer_mm, "OUTLINE", True), (f"CEM{k}", t_c, "MEMBRANE_C", False),
                                         (f"B{k}", recipe.layer_mm, "OUTLINE", True), (f"AEM{k}", t_a, "MEMBRANE_A", False)):
            z += thick
            y = y0 + z
            if long:
                sh.line(x0, y, x0 + circ * 0.18, y, layer)
                sh.line(x0 + circ * 0.82, y, x0 + circ, y, layer)
                sh.text(x0 + circ * 0.185, y - 0.9, f"{name} 위 {z:.1f} mm", 2.0)
            else:
                sh.line(x0 + circ * 0.82, y + 0.25, x0 + circ, y + 0.25, layer)
    sh.line(x0, y0 + wall_mm, x0 + circ, y0 + wall_mm, "CENTER")
    sh.text(x0 + circ / 2, y0 + wall_mm + 1.2, "안쪽 바닥 (병 두께 0.8 mm)", 2.2, align="center")
    sh.text(x0, y0 + top_h + 6, f"붓기 가이드 1:1 — {recipe.name} {recipe.pairs}쌍 × {recipe.layer_mm:g} mm, 층 하나 {recipe.layer_ml:.1f} mL · "
                                 f"아래 변을 병 바닥에 맞춰 감기 (둘레 {circ:.1f} mm)", 3.2)
    sh.text(x0, 9, f"주황 = CEM 벽, 초록 = AEM 벽 (0.4 mL 바름) · 배율 100 % 인쇄 — {_dt.date.today().isoformat()}", 2.6)
    return sh
