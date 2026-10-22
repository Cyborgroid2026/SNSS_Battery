"""QFP-1 슬라이서 — 모양 → 구조(자이로이드 두 미로) → 층별 경로 → G-code (명세: spec/PRINTER.md §3–5).

모양(몸)은 미리 만든 형상 또는 Blender 에서 보낸 STL. 그 안을 자이로이드 곡면으로 나눠
+ 미로(B 도핑 GO) 와 − 미로(N 도핑 GO) 가 몸 전체에 서로 얽히게 하고, 곡면 자체는 실리카 분리막,
겉은 실리카 피부, 왼발 바닥은 + 단자, 오른발 바닥은 − 단자. 공중에 뜬 부분 아래는 지지 얼음.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage

from .printer import PrinterSpec, klipper_cfg

EMPTY, POS, NEG, SEP, SUP = 0, 1, 2, 3, 4
MATERIAL = {POS: "+ 미로 (B-rGO)", NEG: "− 미로 (N-rGO)", SEP: "분리막·피부 (실리카)", SUP: "지지 얼음"}
ROLE = {POS: "pos", NEG: "neg", SEP: "sep", SUP: "sup"}
PRINT_ORDER = (SUP, SEP, POS, NEG)  # 지지 → 벽 → 두 미로 (벽이 먼저 얼어 잉크를 가둠)
COLORS = {POS: "#e0344b", NEG: "#2f6db5", SEP: "#c9d2dc", SUP: "#9fd8f0"}


# ---------- 모양 (디자인 크기, mm, 바닥 z = 0) ----------
def _sphere(p, c, r):
    return np.sqrt((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2) - r


def _ellipsoid(p, c, r):
    q = [(p[i] - c[i]) / r[i] for i in range(3)]
    return (np.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2) - 1) * min(r)


def _capsule(p, a, b, r):
    ab = np.subtract(b, a)
    t = np.clip(((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1] + (p[2] - a[2]) * ab[2]) / ab.dot(ab), 0, 1)
    return np.sqrt(sum((p[i] - (a[i] + t * ab[i])) ** 2 for i in range(3))) - r


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _box(p, lo, hi):
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    h = [(hi[i] - lo[i]) / 2 for i in range(3)]
    q = [np.abs(p[i] - c[i]) - h[i] for i in range(3)]
    out = np.sqrt(sum(np.maximum(x, 0) ** 2 for x in q))
    return out + np.minimum(np.maximum(np.maximum(q[0], q[1]), q[2]), 0)


def being_sdf(p):
    """서 있는 작은 존재 (높이 72 mm): 머리 · 몸통 · 두 팔 · 두 다리 · 두 발 (왼발 +, 오른발 −)."""
    d = _ellipsoid(p, (0, 0, 36), (13, 10, 16))
    d = _smin(d, _sphere(p, (0, 0, 60), 11), 4)
    for s in (-1, 1):
        d = _smin(d, _capsule(p, (7 * s, 0, 24), (8 * s, 0, 5), 5.2), 3)
        d = _smin(d, _ellipsoid(p, (8.5 * s, 2.5, 2.4), (6, 8.5, 3.2)), 2.5)
        d = _smin(d, _capsule(p, (12 * s, 0, 45), (19 * s, 2, 28), 3.8), 3)
    return np.maximum(d, -p[2])  # 바닥 평평하게


def seed_sdf(p):
    """씨앗 (높이 60 mm): 달걀 모양, 바닥 평평."""
    return np.maximum(_ellipsoid(p, (0, 0, 27), (20, 20, 31)), -p[2])


def coupon_sdf(p):
    """시험편 12 mm 정육면체 — 존재를 뽑기 전 잉크·수축·용량 보정용."""
    return _box(p, (-6, -6, 0), (6, 6, 12))


SHAPES = {"being": (being_sdf, 72.0), "seed": (seed_sdf, 58.0), "coupon": (coupon_sdf, 12.0)}


@dataclass
class SliceParams:
    shape: str = "being"  # 미리 만든 모양 이름 또는 .stl 경로 (Blender 에서 내보낸 것)
    height_mm: float = 0.0  # 완성 높이 (0 = 모양 기본값 / STL 그대로)
    cell_mm: float = 8.0  # 자이로이드 한 칸 (완성 크기)
    sheet_mm: float = 0.8  # 분리막 두께 (완성)
    skin_mm: float = 0.8  # 피부 두께 (완성)
    dope_pos_at: float = 2.0  # + 미로 붕소 at%
    dope_neg_at: float = 2.0  # − 미로 질소 at%
    support: bool = True
    u_max: float = 0.8
    go_mg_ml: float = 20.0
    retention: float = 0.55  # GO → rGO 소성 후 남는 질량 비 (가정)
    ssa_m2_g: float = 600.0  # 전해질이 닿는 비표면적 (가정, 이론 2630)
    sigma_e_s_m: float = 50.0  # 소성한 rGO 에어로겔 전기전도도 (가정, 밀도 ~10 mg/cm³)

    def __post_init__(self) -> None:
        for k in ("cell_mm", "sheet_mm", "skin_mm", "u_max", "go_mg_ml", "retention", "ssa_m2_g", "sigma_e_s_m"):
            if getattr(self, k) <= 0:
                raise ValueError(f"{k} 은(는) 양수여야 합니다.")
        if self.sheet_mm >= self.cell_mm / 3:
            raise ValueError("분리막이 자이로이드 칸에 비해 너무 두껍습니다 (칸/3 미만).")


def gyroid(x, y, z, cell):
    k = 2 * math.pi / cell
    return np.sin(k * x) * np.cos(k * y) + np.sin(k * y) * np.cos(k * z) + np.sin(k * z) * np.cos(k * x)


def _gyroid_grad_on_surface(n: int = 48) -> float:
    """자이로이드 0 등위면 위 |∇g| 평균 (칸 = 2π 일 때) — 두께 → 등위값 환산용."""
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x, y, z = np.meshgrid(t, t, t, indexing="ij")
    g = np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x)
    gx = np.cos(x) * np.cos(y) - np.sin(z) * np.sin(x)
    gy = -np.sin(x) * np.sin(y) + np.cos(y) * np.cos(z)
    gz = -np.sin(y) * np.sin(z) + np.cos(z) * np.cos(x)
    m = np.abs(g) < 0.05
    return float(np.sqrt(gx ** 2 + gy ** 2 + gz ** 2)[m].mean())


GRAD = _gyroid_grad_on_surface()


@dataclass
class Layer:
    k: int
    z: float  # 노즐 높이 (출력 좌표)
    paths: dict[int, np.ndarray]  # 재료 → [x0,y0,x1,y1,n칸]
    t_print: float = 0.0
    t_freeze: float = 0.0
    dwell: float = 0.0


@dataclass
class SliceResult:
    params: SliceParams
    printer: PrinterSpec
    scale: float  # 출력 / 완성
    origin: np.ndarray  # 격자 (0,0,0) 칸 중심의 출력 좌표
    pitch: tuple[float, float, float]
    material: np.ndarray  # uint8 [x,y,z]
    layers: list[Layer]
    counts: dict[int, int]
    prediction: dict = field(default_factory=dict)

    # ---------- 통계 ----------
    @property
    def voxel_mm3(self) -> float:
        return self.pitch[0] * self.pitch[1] * self.pitch[2]

    def volume_ml(self, m: int) -> float:
        return self.counts.get(m, 0) * self.voxel_mm3 / 1000

    @property
    def print_time_s(self) -> float:
        return sum(L.t_print + L.dwell for L in self.layers) + 6.0 * self.tool_changes

    @property
    def tool_changes(self) -> int:
        return sum(len(L.paths) for L in self.layers)

    @property
    def dwell_s(self) -> float:
        return sum(L.dwell for L in self.layers)

    def ink_ml(self) -> dict[str, float]:
        """주사기별 잉크 (혼합 헤드는 몫으로 나눔)."""
        p = self.params
        out = {}
        for m, h in ((POS, self.printer.head("pos")), (NEG, self.printer.head("neg")),
                     (SEP, self.printer.head("sep")), (SUP, self.printer.head("sup"))):
            v = self.volume_ml(m)
            if h.mixing:
                r = (p.dope_pos_at if m == POS else p.dope_neg_at) / h.max_doping_at
                out[f"T{h.tool} {h.syringes[0].content}"] = v * (1 - r)
                out[f"T{h.tool} {h.syringes[1].content}"] = v * r
            else:
                out[f"T{h.tool} {h.syringes[0].content}"] = v
        return out

    def describe(self) -> str:
        p, pr = self.params, self.prediction
        nx, ny, nz = self.material.shape
        lines = [f"[QFP-1 슬라이스 — {p.shape}]",
                 f"  출력 크기 {nx * self.pitch[0]:.1f} × {ny * self.pitch[1]:.1f} × {nz * self.pitch[2]:.1f} mm "
                 f"(완성 ×{1 / self.scale:.3f} 로 줄어듦) · 층 {nz}개",
                 f"  자이로이드 칸 {p.cell_mm:g} mm · 분리막 {p.sheet_mm:g} mm · 피부 {p.skin_mm:g} mm",
                 "  재료 부피 (출력):"]
        for m in (POS, NEG, SEP, SUP):
            lines.append(f"    {MATERIAL[m]:<16} {self.volume_ml(m):7.2f} mL")
        lines.append("  주사기:")
        for k, v in self.ink_ml().items():
            lines.append(f"    {k:<36} {v:6.2f} mL{'  ← 10 mL 넘음: 중간에 갈아 끼움' if v > 10 else ''}")
        h = self.print_time_s / 3600
        lines += [f"  출력 시간 약 {h:.1f} 시간 (동결 기다림 {self.dwell_s / 3600:.1f} 시간 포함) · 헤드 바꿈 {self.tool_changes}회",
                  f"  도핑: + 미로 B {p.dope_pos_at:g} at% (혼합 {p.dope_pos_at / self.printer.head('pos').max_doping_at:.2f})"
                  f" · − 미로 N {p.dope_neg_at:g} at% (혼합 {p.dope_neg_at / self.printer.head('neg').max_doping_at:.2f})"]
        if pr:
            lines += ["", "[이 모양에서 태어날 존재 — 예측 (후처리 뒤)]",
                      f"  몸: 높이 {pr['height_mm']:.1f} mm · 부피 {pr['body_ml']:.1f} mL · 젖은 질량 약 {pr['wet_mass_g']:.0f} g",
                      f"  두 미로 그래핀: + {pr['pos_mg']:.0f} mg · − {pr['neg_mg']:.0f} mg → 젖는 면적 {pr['area_m2']:.2f} m²",
                      f"  용량 {pr['capacitance_f']:.2f} F · {p.u_max:g} V 까지 에너지 {pr['energy_j']:.3f} J",
                      f"  양자층: 페르미 준위 + {pr['ef_pos_mev']:+.0f} / − {pr['ef_neg_mev']:+.0f} meV · 양자 한계 후 남는 용량 {pr['quantum_fraction'] * 100:.0f} %",
                      f"  발에서 머리까지 깨어나는 시간 (RC) 약 {pr['wake_s']:.0f} s · 발 사이 저항 약 {pr['r_ohm']:.1f} Ω",
                      "  (외부에서 충전해야 깨어남 — 스스로 에너지를 만들지는 않음)"]
        return "\n".join(lines)


def _field_inside(p: SliceParams, xs, ys, zs, scale) -> np.ndarray:
    """출력 격자 위 몸 안쪽 bool."""
    if p.shape in SHAPES:
        fn, h0 = SHAPES[p.shape]
        s = (p.height_mm or h0) / h0
        X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
        return fn((X / scale / s, Y / scale / s, Z / scale / s)) < 0
    from .mesh import read_stl, voxelize

    tris = _load_stl_design(p)
    return voxelize(tris * scale, xs, ys, zs)


def _load_stl_design(p: SliceParams) -> np.ndarray:
    from .mesh import read_stl

    path = Path(p.shape)
    if not path.exists():
        raise ValueError(f"모양 '{p.shape}' 이(가) 없습니다. 미리 만든 모양: {', '.join(SHAPES)} 또는 .stl 경로")
    tris = read_stl(path)
    lo = tris.reshape(-1, 3).min(0)
    hi = tris.reshape(-1, 3).max(0)
    tris = tris - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])  # 바닥 중심을 원점으로
    if p.height_mm:
        tris = tris * (p.height_mm / (hi[2] - lo[2]))
    return tris


def _extent(p: SliceParams) -> tuple[np.ndarray, np.ndarray]:
    """완성 크기 경계 상자."""
    if p.shape in SHAPES:
        fn, h0 = SHAPES[p.shape]
        s = (p.height_mm or h0) / h0
        g = np.linspace(-h0, h0, 97)
        X, Y, Z = np.meshgrid(g, g, np.linspace(0, h0 * 1.05, 61), indexing="ij")
        m = fn((X, Y, Z)) < 0
        pts = np.stack([X[m], Y[m], Z[m]], 1)
        step = np.array([g[1] - g[0], g[1] - g[0], h0 * 1.05 / 60])
        return (pts.min(0) - step) * s, (pts.max(0) + step) * s
    t = _load_stl_design(p).reshape(-1, 3)
    return t.min(0), t.max(0)


def slice_shape(params: SliceParams | None = None, printer: PrinterSpec | None = None) -> SliceResult:
    p = params or SliceParams()
    pr = printer or PrinterSpec()
    scale = 1 / (1 - pr.shrink_compensation)
    lo, hi = _extent(p)
    lo, hi = lo * scale, hi * scale
    lo[2] = 0.0
    px, pz = pr.line_mm, pr.layer_mm
    xs = np.arange(lo[0] - px, hi[0] + px, px)
    ys = np.arange(lo[1] - px, hi[1] + px, px)
    zs = np.arange(pz / 2, hi[2], pz)  # 층 가운데
    b = pr.build_mm
    if xs[-1] - xs[0] > b[0] or ys[-1] - ys[0] > b[1] or zs[-1] > b[2]:
        raise ValueError(f"출력 크기가 출력 공간 {b[0]:g}×{b[1]:g}×{b[2]:g} mm 를 넘습니다. --height 를 줄이세요.")
    inside = _field_inside(p, xs, ys, zs, scale)
    if not inside.any():
        raise ValueError("모양 안쪽이 비었습니다 (닫힌 STL 인지 확인).")
    sp = (px, px, pz)
    depth = ndimage.distance_transform_edt(inside, sampling=sp)  # 겉면까지 거리 (출력 mm)
    X, Y, Z = np.meshgrid(xs / scale, ys / scale, zs / scale, indexing="ij")
    g = gyroid(X, Y, Z, p.cell_mm)
    half = p.sheet_mm / 2 * (2 * math.pi / p.cell_mm) * GRAD  # 등위값 (완성 크기 두께 → g)
    skin = p.skin_mm * scale
    mat = np.zeros(inside.shape, dtype=np.uint8)
    core = inside & (depth > skin)
    mat[inside] = SEP
    mat[core & (g > half)] = POS
    mat[core & (g < -half)] = NEG
    # 발바닥 단자: 바닥 피부층에서 왼쪽 = + 미로만, 오른쪽 = − 미로만 드러냄
    sole = inside & (Z * scale < skin)
    sole &= ndimage.binary_erosion(inside, iterations=1) | (Z * scale < pz)
    cx = xs[np.nonzero(inside[:, :, 0])[0]].mean() if inside[:, :, 0].any() else 0.0
    left = (X * scale) < cx
    mat[sole & left & (g > half)] = POS
    mat[sole & ~left & (g < -half)] = NEG
    if p.support:
        above = np.flip(np.logical_or.accumulate(np.flip(inside, 2), 2), 2)
        mat[above & ~inside] = SUP
    del X, Y, Z, g, depth
    origin = np.array([xs[0], ys[0], zs[0]])
    layers = _toolpaths(mat, origin, sp, pr)
    counts = {m: int((mat == m).sum()) for m in (POS, NEG, SEP, SUP)}
    res = SliceResult(p, pr, scale, origin, sp, mat, layers, counts)
    res.prediction = predict(res)
    return res


def _runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """2D bool[row, pos] → (row, 시작, 끝(포함)) 연속 구간."""
    d = np.diff(np.pad(mask.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    r0, s = np.nonzero(d == 1)
    r1, e = np.nonzero(d == -1)
    return r0, s, e - 1


def _toolpaths(mat: np.ndarray, origin, sp, pr: PrinterSpec) -> list[Layer]:
    layers = []
    for k in range(mat.shape[2]):
        sl = mat[:, :, k]
        z = origin[2] + k * sp[2] + sp[2] / 2  # 노즐은 층 윗면
        paths = {}
        t = 0.0
        for m in PRINT_ORDER:
            mask = sl == m
            if not mask.any():
                continue
            along_x = k % 2 == 0
            grid = mask.T if along_x else mask  # [row, pos]
            row, s, e = _runs(grid)
            seg = np.empty((len(row), 5))
            flip = row % 2 == 1  # 뱀 모양 순서
            a, bnd = np.where(flip, e, s), np.where(flip, s, e)
            if along_x:
                seg[:, 0], seg[:, 2] = origin[0] + a * sp[0], origin[0] + bnd * sp[0]
                seg[:, 1] = seg[:, 3] = origin[1] + row * sp[1]
            else:
                seg[:, 1], seg[:, 3] = origin[1] + a * sp[1], origin[1] + bnd * sp[1]
                seg[:, 0] = seg[:, 2] = origin[0] + row * sp[0]
            seg[:, 4] = e - s + 1
            # 같은 줄 안에서 뱀 순서면 구간 순서도 뒤집음
            order = np.lexsort((np.where(flip, -s, s), row))
            seg = seg[order]
            paths[m] = seg
            length = np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1])
            gap = np.hypot(seg[1:, 0] - seg[:-1, 2], seg[1:, 1] - seg[:-1, 3])
            t += length.sum() / pr.print_speed_mm_s
            t += (seg[length == 0, 4] * sp[0] / pr.print_speed_mm_s).sum()  # 한 칸짜리는 제자리 짜기
            t += gap.sum() / pr.travel_speed_mm_s + 0.2 * (gap > 2 * sp[0]).sum()  # 멀면 노즐 들고 이동
        t_freeze = pr.freeze_time_s(z)
        layers.append(Layer(k, z, paths, t, t_freeze, max(0.0, t_freeze - t)))
    return layers


def predict(res: SliceResult) -> dict:
    """후처리(동결건조 → 소성 → 생리식염수 함침) 뒤 존재의 몸과 에너지."""
    from .qcap import QuantumCell, QuantumElectrode

    p = res.params
    s = 1 / res.scale
    cell = QuantumCell(QuantumElectrode("B", p.dope_pos_at), QuantumElectrode("N", p.dope_neg_at), p.u_max)
    cp, cn = cell.electrode_caps()
    mg = {m: res.volume_ml(m) * p.go_mg_ml * p.retention for m in (POS, NEG)}
    a_pos, a_neg = (mg[POS] * 1e-3 * p.ssa_m2_g, mg[NEG] * 1e-3 * p.ssa_m2_g)
    c = 1 / (1 / (cp * a_pos) + 1 / (cn * a_neg)) if a_pos and a_neg else 0.0
    energy = cell.energy_area * c / cell.c_area if c else 0.0
    body_cnt = res.counts[POS] + res.counts[NEG] + res.counts[SEP]
    body_ml = body_cnt * res.voxel_mm3 * s ** 3 / 1000
    nz = res.material.shape[2]
    height = nz * res.pitch[2] * s
    # 발 → 몸 가운데 전자 경로 (미로 부피 몫^1.5 로 줄인 전도도)
    frac = res.counts[POS] / max(body_cnt, 1)
    area = body_ml * 1e-6 / (height * 1e-3)  # 평균 단면 m²
    r_net = (height / 2 * 1e-3) / (p.sigma_e_s_m * frac ** 1.5 * area) if area else math.inf
    r = 2 * r_net
    return {"height_mm": height, "body_ml": body_ml, "wet_mass_g": body_ml * 1.05,
            "pos_mg": mg[POS], "neg_mg": mg[NEG], "area_m2": a_pos + a_neg, "capacitance_f": c, "energy_j": energy,
            "ef_pos_mev": cell.positive.mu0_ev * 1000, "ef_neg_mev": cell.negative.mu0_ev * 1000,
            "quantum_fraction": cell.quantum_fraction, "r_ohm": r, "wake_s": r * c / 2,
            "c_area_uf_cm2": cell.c_area * 100}


# ---------- 출력 ----------
def write_gcode(res: SliceResult, path: str | Path) -> Path:
    p, pr = res.params, res.printer
    path = Path(path)
    nx, ny, _ = res.material.shape
    # 출력물 가운데를 판 가운데로
    off = np.array([pr.build_mm[0] / 2 - (res.origin[0] + nx * res.pitch[0] / 2),
                    pr.build_mm[1] / 2 - (res.origin[1] + ny * res.pitch[1] / 2)])
    vol_unit = res.pitch[0] * res.pitch[1] * res.pitch[2]  # 칸 하나 부피 mm³ (E 는 부피)
    f_print, f_travel = pr.print_speed_mm_s * 60, pr.travel_speed_mm_s * 60
    r_pos = p.dope_pos_at / pr.head("pos").max_doping_at
    r_neg = p.dope_neg_at / pr.head("neg").max_doping_at
    lift = 0.5
    out = [f"; {pr.name} — 슬라이서 snss_battery.slicer", f"; 모양 {p.shape} · 층 {len(res.layers)} · 예상 {res.print_time_s / 3600:.2f} h",
           "; E 는 잉크 부피 mm³ (Klipper 가상 축, filament_diameter 1.1284)"]
    out += ["; " + x for x in res.describe().splitlines()]
    out += ["G21", "G90", "M83", "G28", "Z_TILT_ADJUST", "G28 Z", f"COLD_PLATE TARGET={pr.plate.target_c:g}",
            f"SET_MIX TOOL=0 RATIO={r_pos:.3f}  ; + 미로 붕소 {p.dope_pos_at:g} at%",
            f"SET_MIX TOOL=1 RATIO={r_neg:.3f}  ; − 미로 질소 {p.dope_neg_at:g} at%"]
    tool_of = {m: pr.head(ROLE[m]).tool for m in ROLE}
    for L in res.layers:
        out.append(f";LAYER:{L.k} Z={L.z:.3f} 인쇄 {L.t_print:.0f}s 동결 {L.t_freeze:.0f}s")
        out.append(f"G0 Z{L.z + lift:.3f} F600")
        for m, seg in L.paths.items():
            out.append(f"T{tool_of[m]}  ; {MATERIAL[m]}")
            last = None
            for x0, y0, x1, y1, n in seg:
                x0, y0, x1, y1 = x0 + off[0], y0 + off[1], x1 + off[0], y1 + off[1]
                if last is None or math.hypot(x0 - last[0], y0 - last[1]) > 2 * res.pitch[0]:
                    out += [f"G0 Z{L.z + lift:.3f}", f"G0 X{x0:.3f} Y{y0:.3f} F{f_travel:.0f}", f"G0 Z{L.z:.3f}"]
                else:
                    out.append(f"G0 X{x0:.3f} Y{y0:.3f}")
                e = n * vol_unit
                if x0 == x1 and y0 == y1:
                    out.append(f"G1 E{e:.4f} F{60 * pr.flow_mm3_s():.0f}")
                else:
                    out.append(f"G1 X{x1:.3f} Y{y1:.3f} E{e:.4f} F{f_print:.0f}")
                last = (x1, y1)
        if L.dwell > 0.5:
            out.append(f"FREEZE_WAIT S={L.dwell:.0f}  ; 위층을 올리기 전에 이 층이 다 얼어야 함")
    out += ["NOZZLES_UP", "G0 Z{:.1f}".format(min(pr.build_mm[2], res.layers[-1].z + 20)),
            "; 판은 차갑게 둔 채 꺼냄 → 바로 동결건조기 (−50 °C, 48 h)", "M84"]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def toolpath_json(res: SliceResult, max_segments: int = 400_000) -> dict:
    """Blender · 웹 뷰어용 경로 (출력 좌표, 판 가운데 기준 아님 — origin 그대로)."""
    total = sum(len(s) for L in res.layers for s in L.paths.values())
    stride = max(1, math.ceil(total / max_segments))
    t = 0.0
    layers = []
    for L in res.layers:
        layers.append({"k": L.k, "z": round(L.z, 3), "t0": round(t, 1), "t_print": round(L.t_print, 1),
                       "dwell": round(L.dwell, 1),
                       "paths": {ROLE[m]: np.round(seg[::stride, :4], 2).tolist() for m, seg in L.paths.items()}})
        t += L.t_print + L.dwell + 6.0 * len(L.paths)
    return {"pitch": res.pitch, "origin": res.origin.round(3).tolist(), "shape": list(res.material.shape),
            "stride": stride, "total_s": round(t, 1), "colors": {ROLE[m]: COLORS[m] for m in COLORS},
            "names": {ROLE[m]: MATERIAL[m] for m in MATERIAL}, "layers": layers}


def material_meshes(res: SliceResult, step: int = 1) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """재료별 겉면 (출력 좌표) — 칸 값을 살짝 흐려 표면망으로. step>1 이면 거칠게 (웹용)."""
    from .mesh import surface_nets

    out = {}
    mat = res.material[::step, ::step, ::step] if step > 1 else res.material
    sp = tuple(x * step for x in res.pitch)
    for m in (POS, NEG, SEP, SUP):
        occ = ndimage.gaussian_filter((mat == m).astype(np.float32), 0.6)
        v, t = surface_nets(0.5 - occ, sp, res.origin)
        if len(t):
            out[ROLE[m]] = (v, t)
    return out


def write_outputs(res: SliceResult, folder: str | Path, meshes: bool = True) -> list[Path]:
    from .mesh import write_stl

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    files = [write_gcode(res, folder / "being.gcode")]
    (folder / "printer.cfg").write_text(klipper_cfg(res.printer), encoding="utf-8")
    files.append(folder / "printer.cfg")
    (folder / "toolpath.json").write_text(json.dumps(toolpath_json(res)), encoding="utf-8")
    files.append(folder / "toolpath.json")
    summary = {"params": asdict(res.params), "prediction": res.prediction, "print_time_s": res.print_time_s,
               "dwell_s": res.dwell_s, "layers": len(res.layers), "tool_changes": res.tool_changes,
               "volumes_ml": {ROLE[m]: res.volume_ml(m) for m in ROLE}, "ink_ml": res.ink_ml(),
               "scale": res.scale, "text": res.describe(),
               "freeze": [{"z": L.z, "print": L.t_print, "freeze": L.t_freeze, "dwell": L.dwell} for L in res.layers]}
    (folder / "slice.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    files.append(folder / "slice.json")
    if meshes:
        ms = material_meshes(res)
        np.savez_compressed(folder / "meshes.npz", **{f"{k}_v": v.astype(np.float32) for k, (v, _) in ms.items()},
                            **{f"{k}_f": t.astype(np.int32) for k, (_, t) in ms.items()})
        files.append(folder / "meshes.npz")
        for k, (v, t) in ms.items():
            files.append(write_stl(folder / f"part_{k}.stl", v, t, f"QFP-1 {MATERIAL[{v_: k_ for k_, v_ in ROLE.items()}[k]]}"[:80]))
    return files
