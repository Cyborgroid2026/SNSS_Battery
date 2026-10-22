"""조각 — 작업물 기억 · 양자 인공세포 설계 · 더하기/깎기/붙이기/떼기/허공 획 · 경로 · G-code (명세: spec/SCULPTOR.md).

출력물은 **양자 인공세포**로 이루어진 하나의 존재(Energetic Being):
- 몸 = 보로노이 세포 수백~수천 개 (약 3 mm)
- 세포질 = 도핑한 rGO 젤 + 생리식염수: p형 세포(+) 또는 n형 세포(−) — 도핑이 페르미 준위를 정함 (qcap)
- 막 = GO/PVA/식염수 (이온은 지나고 전자는 막음) — p·n 세포가 막을 사이에 두고 만나는 곳에 전하가 쌓임
- 간극연접 = 같은 유형 이웃 세포 사이 막에 뚫린 구멍 (세포질끼리 이어져 전자가 지남) → + 망 · − 망
- 피부 = 막과 같은 재료. 바닥(발바닥)은 피부 없이 열려 있어 단자이자 붙이는 자리: 왼발 +, 오른발 −

상온 전제: 굳는 것은 펜 끝 혼합(초분자 젤), 붙는 것은 수소결합 자가치유, 떼는 것은 깎기(흡입).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from .printer import SculptorSpec, klipper_cfg

EMPTY, POS, NEG, MEM = 0, 1, 2, 3
ROLE = {POS: "pos", NEG: "neg", MEM: "mem"}
CODE = {v: k for k, v in ROLE.items()}
ADD_ORDER = (MEM, POS, NEG)  # 막을 먼저 그어 세포질을 가둠


# ---------- 모양 (완성 크기 mm, 바닥 z = 0) ----------
def _sphere(p, c, r):
    return np.sqrt((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2) - r


def _ellipsoid(p, c, r):
    q = [(p[i] - c[i]) / r[i] for i in range(3)]
    return (np.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2) - 1) * min(r)


def _capsule(p, a, b, r):
    ab = np.subtract(b, a, dtype=float)
    t = np.clip(((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1] + (p[2] - a[2]) * ab[2]) / ab.dot(ab), 0, 1)
    return np.sqrt(sum((p[i] - (a[i] + t * ab[i])) ** 2 for i in range(3))) - r


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _box(p, lo, hi):
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    h = [(hi[i] - lo[i]) / 2 for i in range(3)]
    q = [np.abs(p[i] - c[i]) - h[i] for i in range(3)]
    return np.sqrt(sum(np.maximum(x, 0) ** 2 for x in q)) + np.minimum(np.maximum(np.maximum(q[0], q[1]), q[2]), 0)


def being_sdf(p):
    """서 있는 작은 존재 (높이 72 mm): 머리 · 몸통 · 두 팔 · 두 다리 · 두 발 (왼발 +, 오른발 −)."""
    d = _ellipsoid(p, (0, 0, 36), (13, 10, 16))
    d = _smin(d, _sphere(p, (0, 0, 60), 11), 4)
    for s in (-1, 1):
        d = _smin(d, _capsule(p, (7 * s, 0, 24), (8 * s, 0, 5), 5.2), 3)
        d = _smin(d, _ellipsoid(p, (8.5 * s, 2.5, 2.4), (6, 8.5, 3.2)), 2.5)
        d = _smin(d, _capsule(p, (12 * s, 0, 45), (19 * s, 2, 28), 3.8), 3)
    return np.maximum(d, -p[2])


def seed_sdf(p):
    """씨앗 (높이 58 mm): 달걀 모양, 바닥 평평."""
    return np.maximum(_ellipsoid(p, (0, 0, 27), (20, 20, 31)), -p[2])


def coupon_sdf(p):
    """시험편 12 mm 정육면체 — 잉크·용량 보정용."""
    return _box(p, (-6, -6, 0), (6, 6, 12))


def bud_sdf(p):
    """싹 (높이 18 mm) — 존재 위에 더 붙이는 작은 조각 (예: 머리 위)."""
    return np.maximum(_smin(_ellipsoid(p, (0, 0, 7), (7, 7, 7.5)), _capsule(p, (0, 0, 10), (2, 0, 17), 2.2), 2.5), -p[2])


SHAPES = {"being": (being_sdf, 72.0), "seed": (seed_sdf, 58.0), "coupon": (coupon_sdf, 12.0), "bud": (bud_sdf, 18.0)}


@dataclass
class CellParams:
    cell_mm: float = 3.0  # 보로노이 세포 간격 (완성 크기)
    jitter: float = 0.35  # 씨앗 흔들림 (간격 비)
    type_period_mm: float = 9.0  # p/n 배치 자이로이드 주기 — 같은 유형끼리 이어진 미로가 되게
    skin_mm: float = 0.8
    pore_mm: float = 1.0  # 간극연접 구멍 지름
    carrier_pos: float = 5.0  # p형 세포 정공 밀도 10¹² cm⁻²
    carrier_neg: float = 5.0  # n형 세포 전자 밀도
    seed: int = 7

    def __post_init__(self) -> None:
        if not 1.0 <= self.cell_mm <= 20:
            raise ValueError("세포 간격은 1~20 mm 입니다 (펜 선폭 0.41 mm).")
        if self.pore_mm >= self.cell_mm:
            raise ValueError("간극연접 구멍이 세포보다 큽니다.")


# ---------- 작업물 기억 ----------
@dataclass
class Piece:
    """조각가가 기억하는 작업물. 격자 칸 (i,j,k) 의 출력 좌표 = ((ox+i)·px, (oy+j)·px, (k+½)·pz)."""

    name: str
    material: np.ndarray  # uint8
    cell: np.ndarray  # int32, −1 = 바깥
    ctype: np.ndarray  # int8 세포 번호 → +1 p · −1 n
    offset: tuple[int, int]
    pitch: tuple[float, float]  # (선폭, 층)
    scale: float  # 출력 / 완성
    carriers: tuple[float, float] = (5.0, 5.0)
    history: list[str] = field(default_factory=list)

    @property
    def inside(self) -> np.ndarray:
        return self.material != EMPTY

    @property
    def height_mm(self) -> float:
        ks = np.nonzero(self.inside.any(axis=(0, 1)))[0]
        return (ks[-1] + 1) * self.pitch[1] if len(ks) else 0.0

    def coords(self):
        px, pz = self.pitch
        nx, ny, nz = self.material.shape
        return ((self.offset[0] + np.arange(nx)) * px, (self.offset[1] + np.arange(ny)) * px, (np.arange(nz) + 0.5) * pz)

    def n_cells(self) -> int:
        return int(len(np.unique(self.cell[self.cell >= 0])))

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, material=self.material, cell=self.cell, ctype=self.ctype,
                            meta=json.dumps({"name": self.name, "offset": list(self.offset), "pitch": list(self.pitch),
                                             "scale": self.scale, "carriers": list(self.carriers),
                                             "history": self.history}, ensure_ascii=False))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Piece":
        z = np.load(path)
        m = json.loads(str(z["meta"]))
        return cls(m["name"], z["material"], z["cell"], z["ctype"], tuple(m["offset"]), tuple(m["pitch"]),
                   m["scale"], tuple(m["carriers"]), m["history"])


def _place(p: Piece, ox: int, oy: int, shape: tuple[int, int, int], dz: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """작업물을 (ox, oy) 에서 시작하는 더 큰 격자에 놓기 → (material, cell)."""
    mat = np.zeros(shape, dtype=np.uint8)
    cell = np.full(shape, -1, dtype=np.int32)
    i0, j0 = p.offset[0] - ox, p.offset[1] - oy
    nx, ny, nz = p.material.shape
    nz = min(nz, shape[2] - dz)
    mat[i0:i0 + nx, j0:j0 + ny, dz:dz + nz] = p.material[:, :, :nz]
    cell[i0:i0 + nx, j0:j0 + ny, dz:dz + nz] = p.cell[:, :, :nz]
    return mat, cell


def _union_box(*pieces: Piece, dz: tuple[int, ...] | None = None) -> tuple[int, int, tuple[int, int, int]]:
    dz = dz or (0,) * len(pieces)
    ox = min(p.offset[0] for p in pieces)
    oy = min(p.offset[1] for p in pieces)
    ex = max(p.offset[0] + p.material.shape[0] for p in pieces)
    ey = max(p.offset[1] + p.material.shape[1] for p in pieces)
    ez = max(d + p.material.shape[2] for p, d in zip(pieces, dz))
    return ox, oy, (ex - ox, ey - oy, ez)


# ---------- 설계 ----------
def gyroid(x, y, z, period):
    k = 2 * math.pi / period
    return np.sin(k * x) * np.cos(k * y) + np.sin(k * y) * np.cos(k * z) + np.sin(k * z) * np.cos(k * x)


def _shape_inside(shape: str, height_mm: float, scale: float, X, Y, Z) -> np.ndarray:
    if shape in SHAPES:
        fn, h0 = SHAPES[shape]
        s = (height_mm or h0) / h0
        return fn((X / scale / s, Y / scale / s, Z / scale / s)) < 0
    from .mesh import read_stl, voxelize

    tris = _stl_design(shape, height_mm)
    return voxelize(tris * scale, X[:, 0, 0], Y[0, :, 0], Z[0, 0, :])


def _stl_design(path: str, height_mm: float) -> np.ndarray:
    from .mesh import read_stl

    if not Path(path).exists():
        raise ValueError(f"모양 '{path}' 이(가) 없습니다. 미리 만든 모양: {', '.join(SHAPES)} 또는 .stl 경로")
    t = read_stl(path)
    lo, hi = t.reshape(-1, 3).min(0), t.reshape(-1, 3).max(0)
    t = t - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    return t * (height_mm / (hi[2] - lo[2])) if height_mm else t


def _shape_extent(shape: str, height_mm: float) -> tuple[np.ndarray, np.ndarray]:
    if shape in SHAPES:
        fn, h0 = SHAPES[shape]
        s = (height_mm or h0) / h0
        g = np.linspace(-h0, h0, 97)
        X, Y, Z = np.meshgrid(g, g, np.linspace(0, h0 * 1.05, 61), indexing="ij")
        m = fn((X, Y, Z)) < 0
        pts = np.stack([X[m], Y[m], Z[m]], 1)
        step = np.array([g[1] - g[0]] * 2 + [h0 * 1.05 / 60])
        return (pts.min(0) - step) * s, (pts.max(0) + step) * s
    t = _stl_design(shape, height_mm).reshape(-1, 3)
    return t.min(0), t.max(0)


def shape_grid(shape: str, height_mm: float, spec: SculptorSpec, at: tuple[float, float] = (0.0, 0.0)):
    """모양 → (inside, offset, pitch, scale). at = 출력 좌표 XY 중심 (mm)."""
    scale = 1 / (1 - spec.shrink_compensation)
    lo, hi = _shape_extent(shape, height_mm)
    px, pz = spec.line_mm, spec.layer_mm
    ox = int(math.floor((lo[0] * scale + at[0]) / px)) - 2
    oy = int(math.floor((lo[1] * scale + at[1]) / px)) - 2
    nx = int(math.ceil((hi[0] * scale + at[0]) / px)) + 2 - ox
    ny = int(math.ceil((hi[1] * scale + at[1]) / px)) + 2 - oy
    nz = int(math.ceil(hi[2] * scale / pz)) + 1
    b = spec.build_mm
    if nx * px > b[0] or ny * px > b[1] or nz * pz > b[2]:
        raise ValueError(f"출력 크기가 출력 공간 {b[0]:g}×{b[1]:g}×{b[2]:g} mm 를 넘습니다.")
    X, Y, Z = np.meshgrid((ox + np.arange(nx)) * px - at[0], (oy + np.arange(ny)) * px - at[1],
                          (np.arange(nz) + 0.5) * pz, indexing="ij")
    inside = _shape_inside(shape, height_mm, scale, X, Y, Z)
    if not inside.any():
        raise ValueError("모양 안쪽이 비었습니다 (닫힌 STL 인지 확인).")
    return inside, (ox, oy), (px, pz), scale


def _seed_cells(inside: np.ndarray, region: np.ndarray, offset, pitch, scale, cp: CellParams, first_id: int,
                rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """region 칸들을 새 보로노이 세포로 나눔 → (칸별 세포 번호, 씨앗 좌표, 씨앗 유형)."""
    px, pz = pitch
    idx = np.argwhere(region)
    pts = np.column_stack([(offset[0] + idx[:, 0]) * px, (offset[1] + idx[:, 1]) * px, (idx[:, 2] + 0.5) * pz])
    lo, hi = pts.min(0), pts.max(0)
    h = cp.cell_mm * scale
    axes = [np.arange(lo[i], hi[i] + h, h) for i in range(3)]
    G = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
    G = G + rng.uniform(-cp.jitter, cp.jitter, G.shape) * h
    # 몸 안에 든 씨앗만 (가장 가까운 칸이 region 안)
    tree = cKDTree(pts)
    d, near = tree.query(G)
    G = G[d < 0.75 * h]
    if not len(G):
        G = pts[[len(pts) // 2]]
    _, lab = cKDTree(G).query(pts)
    used = np.unique(lab)
    remap = np.full(len(G), -1)
    remap[used] = np.arange(len(used))
    seeds = G[used]
    g = gyroid(seeds[:, 0] / scale, seeds[:, 1] / scale, seeds[:, 2] / scale, cp.type_period_mm)
    types = np.where(g >= 0, 1, -1).astype(np.int8)
    cells = np.full(inside.shape, -1, dtype=np.int32)
    cells[region] = remap[lab] + first_id
    return cells, seeds, types


def _adjacency(cell: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """이웃 세포 쌍 (a<b) 과 맞닿은 칸 면 수."""
    keys = []
    n = int(cell.max()) + 1
    for ax in range(3):
        a = np.moveaxis(cell, ax, 0)
        u, v = a[:-1], a[1:]
        m = (u >= 0) & (v >= 0) & (u != v)
        lo, hi = np.minimum(u[m], v[m]).astype(np.int64), np.maximum(u[m], v[m]).astype(np.int64)
        keys.append(lo * n + hi)
    k, cnt = np.unique(np.concatenate(keys), return_counts=True)
    return k // n, k % n, cnt


def _components(n: int, a: np.ndarray, b: np.ndarray, mask_edge: np.ndarray) -> np.ndarray:
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    g = coo_matrix((np.ones(mask_edge.sum()), (a[mask_edge], b[mask_edge])), shape=(n, n))
    return connected_components(g, directed=False)[1]


def _fix_types(cell: np.ndarray, ctype: np.ndarray, sole_left: np.ndarray, sole_right: np.ndarray,
               fixed: np.ndarray) -> np.ndarray:
    """같은 유형끼리 이어져 발바닥 단자까지 닿도록 유형을 고침. 고립된(단자에 못 닿는) 덩어리는 뒤집음."""
    ctype = ctype.copy()
    ctype[sole_left] = 1
    ctype[sole_right] = -1
    n = len(ctype)
    a, b, _ = _adjacency(cell)
    for _ in range(8):
        same = ctype[a] == ctype[b]
        comp = _components(n, a, b, same)
        good = np.zeros(n, dtype=bool)
        for t, sole in ((1, sole_left), (-1, sole_right)):
            ok_comps = np.unique(comp[sole[ctype[sole] == t]]) if len(sole) else np.array([], int)
            good |= np.isin(comp, ok_comps) & (ctype == t)
        flip = ~good & ~fixed
        exists = np.zeros(n, dtype=bool)
        exists[np.unique(cell[cell >= 0])] = True
        flip &= exists
        if not flip.any():
            break
        ctype[flip] = -ctype[flip]
    return ctype


def separate(mat: np.ndarray) -> np.ndarray:
    """p 세포질과 n 세포질이 직접 닿는 곳(전기 단락)은 막으로 바꿈 — 늘 막이 사이에 있게."""
    for ax in range(3):
        a = np.moveaxis(mat, ax, 0)
        u, v = a[:-1], a[1:]
        clash = ((u == POS) & (v == NEG)) | ((u == NEG) & (v == POS))
        u[clash & (u == POS)] = MEM  # 한쪽(p 쪽)을 막으로
        v[clash & (v == POS)] = MEM
    return mat


def materialize(cell: np.ndarray, ctype: np.ndarray, pitch, scale, cp: CellParams) -> np.ndarray:
    """세포 번호 · 유형 → 재료: 세포질(p/n) · 막(유형이 다른 이웃 사이, 같은 유형이면 구멍만 남김) · 피부."""
    inside = cell >= 0
    px, pz = pitch
    mat = np.zeros(cell.shape, dtype=np.uint8)
    t = np.zeros(cell.shape, dtype=np.int8)
    t[inside] = ctype[cell[inside]]
    mat[t > 0] = POS
    mat[t < 0] = NEG
    # 막: 이웃과 세포 번호가 다르면, 번호가 작은 쪽 칸 하나 두께
    wall = np.zeros(cell.shape, dtype=bool)
    pair = np.full(cell.shape, -1, dtype=np.int64)
    n = int(cell.max()) + 1
    for ax in range(3):
        for sgn in (1, -1):
            nb = np.roll(cell, -sgn, axis=ax)
            edge = [slice(None)] * 3
            edge[ax] = slice(-1, None) if sgn == 1 else slice(0, 1)
            nb[tuple(edge)] = -1
            m = inside & (nb >= 0) & (nb != cell) & (cell < nb) & ~wall
            wall |= m
            pair[m] = cell[m].astype(np.int64) * n + nb[m]
    # 간극연접: 같은 유형 쌍의 면 가운데 지름 pore 안은 세포질로 둠
    same = wall & (ctype[np.maximum(pair % n, 0)] == t)
    idx = np.argwhere(same)
    if len(idx):
        keys = pair[same]
        uk, inv = np.unique(keys, return_inverse=True)
        cen = np.stack([np.bincount(inv, idx[:, d], len(uk)) for d in range(3)], 1) / np.bincount(inv, minlength=len(uk))[:, None]
        r = (idx - cen[inv]) * np.array([px, px, pz])
        pore = np.sqrt((r ** 2).sum(1)) <= cp.pore_mm * scale / 2
        wall[tuple(idx[pore].T)] = False
    mat[wall] = MEM
    # 피부: 겉면에서 skin 안쪽 (바닥은 열어 둠 — 단자 · 붙이는 자리)
    depth = ndimage.distance_transform_edt(np.pad(inside, ((1, 1), (1, 1), (0, 1))), sampling=(px, px, pz))[1:-1, 1:-1, :-1]
    mat[inside & (depth < cp.skin_mm * scale)] = MEM
    return separate(mat)


def _soles(cell: np.ndarray, offset, pitch) -> tuple[np.ndarray, np.ndarray]:
    """바닥 층에 닿은 세포 — 몸 바닥 가운데보다 왼쪽(−X)이면 +, 오른쪽이면 −."""
    bottom = cell[:, :, 0]
    ids = np.unique(bottom[bottom >= 0])
    if not len(ids):
        return np.array([], int), np.array([], int)
    ii = np.argwhere(bottom >= 0)
    cx = ii[:, 0].mean()
    cnt = np.bincount(bottom[bottom >= 0], minlength=cell.max() + 1)
    sx = np.bincount(bottom[bottom >= 0], weights=np.argwhere(bottom >= 0)[:, 0], minlength=cell.max() + 1)
    mx = sx[ids] / cnt[ids]
    return ids[mx < cx], ids[mx >= cx]


def design(shape: str = "being", height_mm: float = 0.0, cp: CellParams | None = None,
           spec: SculptorSpec | None = None, name: str = "", at=(0.0, 0.0)) -> Piece:
    """새 작업물 설계: 모양 → 양자 인공세포."""
    cp = cp or CellParams()
    spec = spec or SculptorSpec()
    inside, offset, pitch, scale = shape_grid(shape, height_mm, spec, at)
    rng = np.random.default_rng(cp.seed)
    cell, _, ctype = _seed_cells(inside, inside, offset, pitch, scale, cp, 0, rng)
    left, right = _soles(cell, offset, pitch)
    ctype = _fix_types(cell, ctype, left, right, np.zeros(len(ctype), dtype=bool))
    mat = materialize(cell, ctype, pitch, scale, cp)
    return Piece(name or Path(shape).stem, mat, cell, ctype, offset, pitch, scale, (cp.carrier_pos, cp.carrier_neg),
                 [f"설계: {shape} · 세포 {len(np.unique(cell[cell >= 0]))}개"])


# ---------- 작업 (더하기 · 깎기 · 붙이기 · 떼기 · 허공 획) ----------
@dataclass
class Op:
    kind: str  # carve · add · stroke · pause · heal · cure · harvest
    note: str
    grid: np.ndarray | None = None  # carve: bool, add: 재료 코드
    offset: tuple[int, int] = (0, 0)
    dz: int = 0
    strokes: list = field(default_factory=list)  # stroke: [(재료, N×3 출력 좌표)]
    seconds: float = 0.0


@dataclass
class Job:
    title: str
    ops: list[Op]
    before: Piece | None
    after: list[Piece]


def _diff_ops(cur_mat: np.ndarray, tgt_mat: np.ndarray, ox: int, oy: int, note: str) -> list[Op]:
    carve = (cur_mat != EMPTY) & (cur_mat != tgt_mat)
    add = np.where((tgt_mat != EMPTY) & (cur_mat != tgt_mat), tgt_mat, EMPTY).astype(np.uint8)
    ops = []
    if carve.any():
        ops.append(Op("carve", f"{note}: 깎기 {int(carve.sum())}칸", carve, (ox, oy)))
    if add.any():
        ops.append(Op("add", f"{note}: 더하기 {int((add != EMPTY).sum())}칸", add, (ox, oy)))
    return ops


def _finish(spec: SculptorSpec) -> list[Op]:
    return [Op("cure", "배양 (배지 속 숙성, 상온): 도펀트 흡착 · 수소결합 안정", seconds=spec.cure_h * 3600)]


def job_new(piece: Piece, spec: SculptorSpec) -> Job:
    empty = np.zeros_like(piece.material)
    ops = _diff_ops(empty, piece.material, *piece.offset, "새로 빚기")
    ops += _finish(spec) + [Op("harvest", "수확 — 배양 받침째 들어 올려 배지에서 바로 꺼냄 (꺼내기 전 받침 흑연 패드로 충전 · 측정 가능)")]
    return Job(f"새로 빚기 — {piece.name}", ops, None, [piece])


def job_add(piece: Piece, shape: str, height_mm: float, cp: CellParams, spec: SculptorSpec,
            at=(0.0, 0.0), dz_mm: float | None = None) -> Job:
    """작업물에 새 모양을 이어 빚음. 합친 몸으로 세포 막·피부를 다시 정하고, 지금과 다른 칸만 깎고 더함
    (예: 붙는 면의 피부에 창을 내고 같은 유형 세포끼리 간극연접으로 이음)."""
    inside, offset, pitch, scale = shape_grid(shape, height_mm, spec, at)
    if pitch != piece.pitch:
        raise ValueError("격자 간격이 다릅니다.")
    dz = int(round((piece.height_mm if dz_mm is None else dz_mm) / pitch[1])) - 1  # 한 층 겹쳐 맞닿게
    dz = max(dz, 0)
    newp = Piece("new", inside.astype(np.uint8), np.where(inside, 0, -1).astype(np.int32), np.zeros(1, np.int8),
                 offset, pitch, scale)
    ox, oy, shp = _union_box(piece, newp, dz=(0, dz))
    cur_mat, cur_cell = _place(piece, ox, oy, shp)
    new_in = np.zeros(shp, dtype=bool)
    i0, j0 = offset[0] - ox, offset[1] - oy
    nx, ny, nz = inside.shape
    new_in[i0:i0 + nx, j0:j0 + ny, dz:dz + nz] = inside
    region = new_in & (cur_cell < 0)
    rng = np.random.default_rng(cp.seed + len(piece.history))
    first = int(piece.ctype.shape[0])
    cells, _, types = _seed_cells(region, region, (ox, oy), pitch, scale, cp, first, rng)
    cell = np.where(region, cells, cur_cell)
    ctype = np.concatenate([piece.ctype, types])
    fixed = np.zeros(len(ctype), dtype=bool)
    fixed[:first] = True
    left, right = _soles(cell, (ox, oy), pitch)
    left, right = left[left < first], right[right < first]
    ctype = _fix_types(cell, ctype, left, right, fixed)
    tgt = materialize(cell, ctype, pitch, scale, cp)
    after = Piece(piece.name, tgt, cell, ctype, (ox, oy), pitch, scale, piece.carriers,
                  piece.history + [f"더하기: {shape} · 새 세포 {len(types)}개"])
    ops = _diff_ops(cur_mat, tgt, ox, oy, f"{shape} 이어 빚기") + _finish(spec)
    return Job(f"더하기 — {piece.name} + {shape}", ops, piece, [after])


def job_carve(piece: Piece, center_mm, radius_mm: float, cp: CellParams, spec: SculptorSpec) -> Job:
    """구 모양으로 깎아 내고, 새로 드러난 면에 피부를 다시 입힘."""
    xs, ys, zs = piece.coords()
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    cut = (X - center_mm[0]) ** 2 + (Y - center_mm[1]) ** 2 + (Z - center_mm[2]) ** 2 <= radius_mm ** 2
    cell = np.where(cut, -1, piece.cell)
    tgt = materialize(cell, piece.ctype, piece.pitch, piece.scale, cp)
    after = Piece(piece.name, tgt, cell, piece.ctype, piece.offset, piece.pitch, piece.scale, piece.carriers,
                  piece.history + [f"깎기: 구 중심 {tuple(round(c, 1) for c in center_mm)} 반지름 {radius_mm:g} mm"])
    ops = _diff_ops(piece.material, tgt, *piece.offset, "깎고 피부 다시 입히기") + _finish(spec)
    return Job(f"깎기 — {piece.name}", ops, piece, [after])


def job_detach(piece: Piece, z_mm: float, cp: CellParams, spec: SculptorSpec, gap_layers: int = 2) -> Job:
    """높이 z 에서 가로로 잘라 두 조각으로. 잘린 면은 열린 채(세포질 노출) — 다시 붙이는 자리."""
    k = int(z_mm / piece.pitch[1])
    nz = piece.material.shape[2]
    if not 1 <= k < nz - gap_layers - 1:
        raise ValueError(f"자를 높이는 0~{piece.height_mm:.1f} mm 사이여야 합니다.")
    carve = np.zeros(piece.material.shape, dtype=bool)
    carve[:, :, k:k + gap_layers] = piece.inside[:, :, k:k + gap_layers]
    lower_cell = piece.cell.copy()
    lower_cell[:, :, k:] = -1
    upper_cell = piece.cell[:, :, k + gap_layers:].copy()
    pieces = []
    n_skin = int(math.ceil(cp.skin_mm * piece.scale / piece.pitch[1])) + 1
    for nm, c in ((piece.name + "_아래", lower_cell), (piece.name + "_위", upper_cell)):
        if (c >= 0).any():
            mat = materialize(c, piece.ctype, piece.pitch, piece.scale, cp)
            if nm.endswith("_아래"):  # 잘린 윗면은 원래 속 구조 그대로 열어 둠 — 다시 붙이는 자리
                ks = slice(max(k - n_skin, 0), k)
                cut = c[:, :, ks] >= 0
                mat[:, :, ks] = np.where(cut, piece.material[:, :, ks], mat[:, :, ks])
            pieces.append(Piece(nm, mat, c, piece.ctype, piece.offset, piece.pitch, piece.scale, piece.carriers,
                                piece.history + [f"떼기: 높이 {z_mm:g} mm 에서 가름"]))
    ops = [Op("carve", f"높이 {z_mm:g} mm 를 {gap_layers}층 깎아 가름 ({int(carve.sum())}칸)", carve, piece.offset)]
    ops.append(Op("pause", "위 조각을 들어 옮김 (배지 속이라 거의 무게가 없음)"))
    return Job(f"떼기 — {piece.name}", ops, piece, pieces)


def job_attach(lower: Piece, upper: Piece, spec: SculptorSpec, at=(0.0, 0.0)) -> Job:
    """위 조각을 아래 조각 위에 붙임: 자리를 평평히 깎고 → 접합 구슬(같은 유형끼리는 세포질, 다르면 막) →
    사람이 위 조각을 올려 누름 → 수소결합으로 아묾. 두 몸은 하나가 됨 (전압 같고 용량 합)."""
    if lower.pitch != upper.pitch:
        raise ValueError("격자 간격이 다릅니다.")
    px, pz = lower.pitch
    sx, sy = int(round(at[0] / px)), int(round(at[1] / px))
    # 위 조각 바닥 발자국 (아래 조각 격자 기준으로 옮김)
    up = Piece(upper.name, upper.material, upper.cell, upper.ctype,
               (upper.offset[0] + sx, upper.offset[1] + sy), upper.pitch, upper.scale)
    foot = up.cell[:, :, 0] >= 0
    if not foot.any():
        raise ValueError("위 조각 바닥이 비었습니다.")
    ox, oy, shp = _union_box(lower, up)
    lmat, lcell = _place(lower, ox, oy, shp)
    fp = np.zeros(shp[:2], dtype=bool)
    i0, j0 = up.offset[0] - ox, up.offset[1] - oy
    fp[i0:i0 + foot.shape[0], j0:j0 + foot.shape[1]] = foot
    # 자리 높이: 발자국의 30 % 이상이 아래 조각과 겹치는 가장 높은 층
    area = fp.sum()
    k_seat = None
    for k in range(shp[2] - 1, -1, -1):
        if (lcell[:, :, k][fp] >= 0).sum() >= 0.3 * area:
            k_seat = k
            break
    if k_seat is None:
        raise ValueError("위 조각이 아래 조각에 닿을 자리가 없습니다 (at 를 조정).")
    carve = np.zeros(shp, dtype=bool)
    carve[:, :, k_seat + 1:] = (lcell[:, :, k_seat + 1:] >= 0) & fp[:, :, None]
    # 접합 구슬 (k_seat + 1 층)
    n_low = len(lower.ctype)
    ctype = np.concatenate([lower.ctype, upper.ctype])
    ucell0 = np.full(shp[:2], -1, dtype=np.int32)
    ucell0[i0:i0 + foot.shape[0], j0:j0 + foot.shape[1]] = np.where(foot, up.cell[:, :, 0] + n_low, -1)
    seat = lcell[:, :, k_seat]
    both = fp & (seat >= 0)
    bead = np.zeros(shp[:2], dtype=np.uint8)
    t_low = np.where(seat >= 0, ctype[np.maximum(seat, 0)], 0)
    t_up = np.where(ucell0 >= 0, ctype[np.maximum(ucell0, 0)], 0)
    open_low = np.isin(lmat[:, :, k_seat], (POS, NEG))
    bead[both] = MEM
    match = both & (t_low == t_up) & open_low
    bead[match & (t_low > 0)] = POS
    bead[match & (t_low < 0)] = NEG
    # 합친 몸
    k_up = k_seat + 2
    shp2 = (shp[0], shp[1], max(shp[2], k_up + up.material.shape[2]))
    mat = np.zeros(shp2, dtype=np.uint8)
    cell = np.full(shp2, -1, dtype=np.int32)
    mat[:, :, :shp[2]] = np.where(carve, EMPTY, lmat)
    cell[:, :, :shp[2]] = np.where(carve, -1, lcell)
    mat[:, :, k_seat + 1] = np.where(fp & (bead != EMPTY), bead, mat[:, :, k_seat + 1])
    cell[:, :, k_seat + 1] = np.where(fp & (bead != EMPTY), seat, cell[:, :, k_seat + 1])
    um, uc = _place(up, ox, oy, (shp2[0], shp2[1], shp2[2] - k_up))
    sl = slice(k_up, shp2[2])
    mat[:, :, sl] = np.where(um != EMPTY, um, mat[:, :, sl])
    cell[:, :, sl] = np.where(uc >= 0, uc + n_low, cell[:, :, sl])
    mat = separate(mat)
    bead = np.where(fp & (bead != EMPTY), mat[:, :, k_seat + 1], bead)  # 구슬도 단락 없이
    after = Piece(lower.name, mat, cell, ctype, (ox, oy), lower.pitch, lower.scale, lower.carriers,
                  lower.history + [f"붙이기: {upper.name} (자리 높이 {(k_seat + 1) * pz:.1f} mm, 이어진 간극연접 {int(match.sum())}칸)"])
    bead_grid = np.zeros(shp, dtype=np.uint8)
    if k_seat + 1 < shp[2]:
        bead_grid[:, :, k_seat + 1] = np.where(fp, bead, 0)
    ops = []
    if carve.any():
        ops.append(Op("carve", f"자리 평평히 깎기 ({int(carve.sum())}칸)", carve, (ox, oy)))
    if k_seat + 1 < shp[2] and bead.any():
        ops.append(Op("add", f"접합 구슬 ({int((bead != EMPTY).sum())}칸: 같은 유형 세포끼리 이음)", bead_grid, (ox, oy)))
    ops += [Op("pause", f"'{upper.name}' 조각을 자리 위에 올려 가볍게 누르세요"),
            Op("heal", "붙인 면이 아물 때까지 누른 채 기다림 (수소결합 자가치유)", seconds=spec.heal_min * 60)]
    return Job(f"붙이기 — {lower.name} + {upper.name}", ops, lower, [after])


def job_strokes(piece: Piece, strokes: list[dict], cp: CellParams, spec: SculptorSpec) -> Job:
    """허공 획 (Blender 곡선 등): 획 하나 = 길쭉한 새 세포 하나. 같은 유형 세포에 닿는 곳은 피부에 창을 내 이음."""
    px, pz = piece.pitch
    pts_all = np.concatenate([np.asarray(s["points"], float) for s in strokes])
    lo, hi = pts_all.min(0) - 2, pts_all.max(0) + 2
    ox = min(piece.offset[0], int(math.floor(lo[0] / px)))
    oy = min(piece.offset[1], int(math.floor(lo[1] / px)))
    ex = max(piece.offset[0] + piece.material.shape[0], int(math.ceil(hi[0] / px)))
    ey = max(piece.offset[1] + piece.material.shape[1], int(math.ceil(hi[1] / px)))
    ez = max(piece.material.shape[2], int(math.ceil(hi[2] / pz)) + 1)
    shp = (ex - ox, ey - oy, ez)
    cur_mat, cur_cell = _place(piece, ox, oy, shp)
    cell = cur_cell.copy()
    ctype = list(piece.ctype)
    r = spec.line_mm / 2
    xs, ys, zs = (ox + np.arange(shp[0])) * px, (oy + np.arange(shp[1])) * px, (np.arange(shp[2]) + 0.5) * pz
    paths = []
    for s in strokes:
        role = s.get("material", "pos")
        if role not in CODE:
            raise ValueError(f"획 재료는 {', '.join(CODE)} 중 하나입니다.")
        p = np.asarray(s["points"], float)
        if len(p) < 2:
            continue
        if role == "mem":
            t = 0
        else:
            t = 1 if role == "pos" else -1
        cid = len(ctype)
        ctype.append(t if t else 1)
        # 획 둘레 r 안의 칸 (선분마다)
        dense = [p[0]]
        for a, b in zip(p[:-1], p[1:]):
            n = max(1, int(np.linalg.norm(b - a) / (0.5 * px)))
            dense += [a + (b - a) * (i + 1) / n for i in range(n)]
        dense = np.array(dense)
        tree = cKDTree(dense)
        I, J, K = np.meshgrid(np.arange(shp[0]), np.arange(shp[1]), np.arange(shp[2]), indexing="ij")
        box = ((xs[I] >= dense[:, 0].min() - 1) & (xs[I] <= dense[:, 0].max() + 1) & (ys[J] >= dense[:, 1].min() - 1)
               & (ys[J] <= dense[:, 1].max() + 1) & (zs[K] >= dense[:, 2].min() - 1) & (zs[K] <= dense[:, 2].max() + 1))
        idx = np.argwhere(box)
        q = np.column_stack([xs[idx[:, 0]], ys[idx[:, 1]], zs[idx[:, 2]]])
        d, _ = tree.query(q)
        hit = idx[d <= max(r, px / 2)]
        free = cell[tuple(hit.T)] < 0
        cell[tuple(hit[free].T)] = cid
        paths.append((CODE[role], p))
    ctype = np.array(ctype, dtype=np.int8)
    tgt = materialize(cell, ctype, piece.pitch, piece.scale, cp)
    # 획 세포 안은 피부 대신 세포질 (가는 획은 전부 피부 깊이 안이라) — 막 획은 막 그대로
    stroke_ids = np.arange(len(piece.ctype), len(ctype))
    in_stroke = np.isin(cell, stroke_ids)
    roles = {len(piece.ctype) + i: CODE[s.get("material", "pos")] for i, s in enumerate(strokes)}
    for cid, code in roles.items():
        tgt[cell == cid] = code
    tgt = separate(tgt)
    after = Piece(piece.name, tgt, cell, ctype, (ox, oy), piece.pitch, piece.scale, piece.carriers,
                  piece.history + [f"허공 획 {len(paths)}개"])
    window = (cur_mat != EMPTY) & (cur_mat != tgt) & ~in_stroke
    ops = []
    if window.any():
        ops += _diff_ops(np.where(window, cur_mat, EMPTY), np.where(window, tgt, EMPTY), ox, oy, "획이 닿는 피부에 창 내기")
    ops.append(Op("stroke", f"허공 획 {len(paths)}개 (배지에 닿아 겉부터 굳고, 중성 부력으로 버팀)", strokes=paths))
    ops += _finish(spec)
    return Job(f"허공 획 — {piece.name}", ops, piece, [after])


# ---------- 경로 ----------
def _runs(mask: np.ndarray):
    d = np.diff(np.pad(mask.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    r0, s = np.nonzero(d == 1)
    _, e = np.nonzero(d == -1)
    return r0, s, e - 1


def _raster(mask2d: np.ndarray, ox: int, oy: int, px: float, along_x: bool) -> np.ndarray:
    """2D 칸 → 뱀 모양 선분 [x0,y0,x1,y1,칸 수]."""
    grid = mask2d.T if along_x else mask2d
    row, s, e = _runs(grid)
    flip = row % 2 == 1
    a, b = np.where(flip, e, s), np.where(flip, s, e)
    seg = np.empty((len(row), 5))
    if along_x:
        seg[:, 0], seg[:, 2] = (ox + a) * px, (ox + b) * px
        seg[:, 1] = seg[:, 3] = (oy + row) * px
    else:
        seg[:, 1], seg[:, 3] = (oy + a) * px, (oy + b) * px
        seg[:, 0] = seg[:, 2] = (ox + row) * px
    seg[:, 4] = e - s + 1
    return seg[np.lexsort((np.where(flip, -s, s), row))]


@dataclass
class Pass:
    kind: str  # add · carve · stroke
    z: float
    role: str  # pos · neg · mem · carve
    segs: np.ndarray  # add/carve: [x0,y0,x1,y1,n]; stroke: N×3 점
    seconds: float


def plan_passes(job: Job, spec: SculptorSpec) -> list[tuple[Op, list[Pass]]]:
    out = []
    px, pz = spec.line_mm, spec.layer_mm
    v_carve = min(spec.print_speed_mm_s, spec.pen.carve_rate_mm3_s / (px * pz))
    for op in job.ops:
        passes = []
        if op.kind in ("add", "carve"):
            g = op.grid
            ks = range(g.shape[2]) if op.kind == "add" else range(g.shape[2] - 1, -1, -1)
            for k in ks:
                z = (op.dz + k + 1) * pz
                if op.kind == "carve":
                    m = g[:, :, k]
                    if m.any():
                        seg = _raster(m, *op.offset, px, k % 2 == 0)
                        passes.append(Pass("carve", z, "carve", seg, _seconds(seg, v_carve, spec)))
                    continue
                for code in ADD_ORDER:
                    m = g[:, :, k] == code
                    if m.any():
                        seg = _raster(m, *op.offset, px, k % 2 == 0)
                        passes.append(Pass("add", z, ROLE[code], seg, _seconds(seg, spec.print_speed_mm_s, spec)))
        elif op.kind == "stroke":
            for code, pts in op.strokes:
                L = np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()
                passes.append(Pass("stroke", float(pts[:, 2].min()), ROLE[code], pts, L / spec.stroke_speed_mm_s))
        out.append((op, passes))
    return out


def _seconds(seg: np.ndarray, v: float, spec: SculptorSpec) -> float:
    length = np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1])
    gap = np.hypot(seg[1:, 0] - seg[:-1, 2], seg[1:, 1] - seg[:-1, 3])
    return float(length.sum() / v + (seg[length == 0, 4] * spec.line_mm / v).sum() + gap.sum() / spec.travel_speed_mm_s
                 + 0.3 * (gap > 2 * spec.line_mm).sum())


def job_time(job: Job, plan, spec: SculptorSpec) -> dict:
    t_work = sum(p.seconds for _, ps in plan for p in ps)
    switches = sum(1 for _, ps in plan for a, b in zip(ps, ps[1:]) if a.role != b.role) + len(plan)
    t_wait = sum(op.seconds for op in job.ops)
    return {"work_s": float(t_work + 4.0 * switches), "wait_s": float(t_wait), "switches": int(switches),
            "total_s": float(t_work + 4.0 * switches + t_wait)}


def medium_plan(job: Job, plan, spec: SculptorSpec) -> dict:
    """배양조(수중 환경): 처음부터 배지 가득, 작업물은 늘 수면 5 mm 아래. 잉크가 들어오고 깎은 젤을 빨아내며 염도가 조금 바뀜."""
    tk = spec.tank
    vox = spec.line_mm ** 2 * spec.layer_mm / 1000  # mL
    ink = {"pos": 0.0, "neg": 0.0, "mem": 0.0}
    removed = 0.0
    top = job.before.height_mm if job.before is not None else 0.0
    for _, passes in plan:
        for p in passes:
            if p.kind == "add":
                ink[p.role] += float(p.segs[:, 4].sum()) * vox
                top = max(top, p.z)
            elif p.kind == "carve":
                removed += float(p.segs[:, 4].sum()) * vox
            else:
                ink[p.role] += np.linalg.norm(np.diff(p.segs, axis=0), axis=1).sum() * math.pi * (spec.line_mm / 2) ** 2 / 1000
                top = max(top, float(p.segs[:, 2].max()))
    for a in job.after:
        top = max(top, a.height_mm)
    ink_ml = sum(ink.values())
    ink_nacl = sum(v * spec.mixed(spec.recipes[k])["nacl_mm"] for k, v in ink.items()) / ink_ml if ink_ml else 0.0
    after = tk.medium_after(ink_ml, ink_nacl, removed)
    return {"fill_ml": tk.fill_ml() if job.before is None else 0.0, "fill_mm": tk.fill_mm, "top_mm": top,
            "submerged": top <= tk.fill_mm - 5, "ink_ml": ink_ml, "removed_ml": removed, "nacl_after_mm": after,
            "change_medium": after < tk.saline_mm * (1 - tk.change_drop)}


def write_gcode(job: Job, plan, spec: SculptorSpec, path: str | Path, pred: dict | None = None) -> Path:
    path = Path(path)
    cx, cy = spec.build_mm[0] / 2, spec.build_mm[1] / 2
    px, pz = spec.line_mm, spec.layer_mm
    vol = px * px * pz
    lift = 1.0
    t = job_time(job, plan, spec)
    med = medium_plan(job, plan, spec)
    if not med["submerged"]:
        raise ValueError(f"작업물 꼭대기 {med['top_mm']:.1f} mm 가 배지 수면 {med['fill_mm']:g} mm 에 너무 가깝습니다 (5 mm 아래까지).")
    out = [f"; {spec.name} — {job.title}", f"; 작업 {t['work_s'] / 3600:.2f} h + 기다림 {t['wait_s'] / 3600:.2f} h · 재료 바꿈 {t['switches']}회",
           f"; E = 펜에서 나가는 잉크 부피 mm³. 상온 수중 환경: 배양조에 멸균생리식염수(배지) {med['fill_mm']:g} mm 가득, 펜까지 잠김.",
           f"; 잉크 {med['ink_ml']:.1f} mL 가 들어간 뒤 배지 염도 {med['nacl_after_mm']:.1f} mM"
           + (" — 배지를 가세요" if med["change_medium"] else " (갈 필요 없음)"),
           "G21", "G90", "M83", "G28", "Z_TILT_ADJUST", "G28 Z"]
    if med["fill_ml"]:
        out += [f"FILL ML={med['fill_ml']:.0f}  ; 빈 배양조를 배지로 가득 ({med['fill_mm']:g} mm) — 기계까지 통째로 잠김",
                "M117 배지 가득 — 기계가 다 잠겼는지 · 거품이 없는지 확인", "M0"]
    out.append("LEAK_CHECK  ; 물속 기계 누설 점검 (A8)")
    if pred:
        out += ["; " + x for x in describe_prediction(pred).splitlines()]
    last_role = None
    for op, passes in plan:
        out.append(f"; ===== {op.kind}: {op.note}")
        if op.kind == "pause":
            out += ["CARVE ON=0", "SET_PIN PIN=uv_light VALUE=0", f"G0 Z{spec.build_mm[2] - 5:g} F600",
                    f'M117 {op.note}', "M0  ; 사람이 할 일 — 끝나면 재개"]
            continue
        if op.kind in ("heal", "cure"):
            macro = "HEAL" if op.kind == "heal" else "CURE"
            out.append(f"{macro} S={op.seconds:.0f}  ; {op.note}")
            continue
        if op.kind == "harvest":
            out += [f"G0 Z{spec.build_mm[2] - 5:g} F600", f"M117 {op.note}",
                    "M0  ; 수확 — 꺼내기 전 충전하려면 CHARGE ON=1 (받침 흑연 패드)"]
            continue
        last_z = None
        for i_p, p in enumerate(passes):
            if p.z != last_z:  # 층·획 시작 — 트리거 (아날로그/디지털/양자 계측기 동기)
                out.append(f"TRIG EVENT={p.kind} N={i_p}")
                last_z = p.z
            if p.role != last_role:
                if p.role == "carve":
                    out += ["SET_PIN PIN=uv_light VALUE=0", "CARVE ON=1"]
                else:
                    r = spec.recipes[p.role]
                    out += ["CARVE ON=0",
                            f"MIX GO={r.go:.2f} SNSS={r.snss:.2f} PVA={r.pva:.2f} VARIANT={r.go_variant} LIGHT={1 if r.light else 0}"
                            f"  ; {r.name}"]
                last_role = p.role
            if p.kind == "stroke":
                q = p.segs
                out += [f"G0 Z{q[0, 2] + lift:.3f}", f"G0 X{q[0, 0] + cx:.3f} Y{q[0, 1] + cy:.3f} F{spec.travel_speed_mm_s * 60:.0f}",
                        f"G0 Z{q[0, 2]:.3f}"]
                for a, b in zip(q[:-1], q[1:]):
                    e = np.linalg.norm(b - a) * math.pi * (spec.line_mm / 2) ** 2
                    out.append(f"G1 X{b[0] + cx:.3f} Y{b[1] + cy:.3f} Z{b[2]:.3f} E{e:.4f} F{spec.stroke_speed_mm_s * 60:.0f}")
                continue
            v = spec.print_speed_mm_s if p.kind == "add" else min(spec.print_speed_mm_s, spec.pen.carve_rate_mm3_s / (px * pz))
            last = None
            for x0, y0, x1, y1, n in p.segs:
                x0, y0, x1, y1 = x0 + cx, y0 + cy, x1 + cx, y1 + cy
                if last is None or math.hypot(x0 - last[0], y0 - last[1]) > 2 * px:
                    out += [f"G0 Z{p.z + lift:.3f}", f"G0 X{x0:.3f} Y{y0:.3f} F{spec.travel_speed_mm_s * 60:.0f}", f"G0 Z{p.z:.3f}"]
                else:
                    out.append(f"G0 X{x0:.3f} Y{y0:.3f}")
                if p.kind == "carve":
                    out.append(f"G1 X{x1:.3f} Y{y1:.3f} F{v * 60:.0f}" if (x0, y0) != (x1, y1) else "G4 P150")
                elif (x0, y0) == (x1, y1):
                    out.append(f"G1 E{n * vol:.4f} F{60 * spec.flow_mm3_s():.0f}")
                else:
                    out.append(f"G1 X{x1:.3f} Y{y1:.3f} E{n * vol:.4f} F{v * 60:.0f}")
                last = (x1, y1)
    out += ["CARVE ON=0", "SET_PIN PIN=uv_light VALUE=0", f"G0 Z{spec.build_mm[2] - 5:g} F600", "M84"]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def passes_json(job: Job, plan, spec: SculptorSpec, max_segments: int = 300_000) -> dict:
    """Blender · 웹 뷰어용 경로 (출력 좌표, 배양조 가운데 = 원점)."""
    total = sum(len(p.segs) for _, ps in plan for p in ps)
    stride = max(1, math.ceil(total / max_segments))
    t = 0.0
    ops = []
    for op, passes in plan:
        items = []
        for p in passes:
            pts = p.segs[::stride, :4] if p.kind != "stroke" else p.segs
            items.append({"kind": p.kind, "role": p.role, "z": round(p.z, 3), "t0": round(t, 1),
                          "s": round(p.seconds, 1), "segs": np.round(pts, 2).tolist()})
            t += p.seconds
        t += op.seconds
        ops.append({"kind": op.kind, "note": op.note, "passes": items, "wait_s": op.seconds})
    colors = {k: r.color for k, r in spec.recipes.items()} | {"carve": "#f2a33a"}
    names = {k: r.name for k, r in spec.recipes.items()} | {"carve": "깎기 (흡입)"}
    return {"title": job.title, "stride": stride, "total_s": round(t, 1), "colors": colors, "names": names, "ops": ops}


# ---------- 존재의 생명 신호: 세포 단위 두 회로망 (전자망 + 전해질망) ----------
@dataclass
class BodyModel:
    u_max: float = 0.8
    go_in_cell_mg_ml: float = 5.0  # 세포질 GO (레시피 p/n 0.50 × 10 mg/mL)
    retention: float = 0.8  # 광환원 뒤 남는 질량 비 (가정)
    ssa_m2_g: float = 500.0  # 전해질이 닿는 비표면적 (가정)
    sigma_e_s_m: float = 2.0  # 광환원 rGO 젤 전기전도도 (가정, 저밀도)
    mem_kappa_ratio: float = 0.5  # 막 이온전도도 / 젤 이온전도도
    contact_s_m2: float = 1e4  # 발바닥 흑연 패드 접촉 (1 Ω·cm²)


def body_signs(piece: Piece, spec: SculptorSpec | None = None, bm: BodyModel | None = None) -> dict:
    """세포 수 · 용량 · 에너지 · 내부저항 · 발에서 머리까지 깨어나는 시간 (세포마다)."""
    from scipy.sparse import coo_matrix, csc_matrix
    from scipy.sparse.linalg import splu

    from .electrolyte import nacl_conductivity
    from .qcap import QuantumCell, QuantumElectrode

    spec = spec or SculptorSpec()
    bm = bm or BodyModel()
    s = 1 / piece.scale
    px, pz = piece.pitch[0] * s / 1000, piece.pitch[1] * s / 1000  # 완성 크기 m
    vvox = px * px * pz
    cell, mat = piece.cell, piece.material
    ids = np.unique(cell[cell >= 0])
    n = len(ids)
    remap = np.full(int(cell.max()) + 1, -1)
    remap[ids] = np.arange(n)
    c = np.where(cell >= 0, remap[np.maximum(cell, 0)], -1)
    ctype = piece.ctype[ids].astype(float)
    cyto = np.isin(mat, (POS, NEG))
    n_cyto = np.bincount(c[cyto], minlength=n).astype(float)
    n_all = np.bincount(c[c >= 0], minlength=n).astype(float)
    pos = np.argwhere(c >= 0)
    cen = np.stack([np.bincount(c[c >= 0], weights=pos[:, d], minlength=n) for d in range(3)], 1) / np.maximum(n_all, 1)[:, None]
    cen_m = cen * np.array([px, px, pz]) + np.array([piece.offset[0] * px, piece.offset[1] * px, pz / 2])
    # 양자층
    cell_q = QuantumCell(QuantumElectrode("NBD", piece.carriers[0]), QuantumElectrode("PEI", piece.carriers[1]), bm.u_max)
    cp_, cn_ = cell_q.electrode_caps()  # F/m²
    area = n_cyto * vvox * 1e6 * bm.go_in_cell_mg_ml * bm.retention * 1e-3 * bm.ssa_m2_g  # m²
    cap = area * np.where(ctype > 0, cp_, cn_)
    # 이웃 쌍: 이온(모든 면) · 전자(같은 유형, 세포질–세포질 면)
    kappa = nacl_conductivity(spec.nacl_stock_mm * spec.recipes["pos"].snss / 1000)
    ion, ele = {}, {}
    for ax, fa in ((0, px * pz), (1, px * pz), (2, px * px)):
        a = np.moveaxis(c, ax, 0)
        m_ = np.moveaxis(mat, ax, 0)
        u, v = a[:-1], a[1:]
        both = (u >= 0) & (v >= 0) & (u != v)
        key = np.minimum(u, v)[both].astype(np.int64) * n + np.maximum(u, v)[both]
        k, cnt = np.unique(key, return_counts=True)
        for kk, cc in zip(k, cnt):
            ion[kk] = ion.get(kk, 0.0) + cc * fa
        cy = both & np.isin(m_[:-1], (POS, NEG)) & np.isin(m_[1:], (POS, NEG))
        key = np.minimum(u, v)[cy].astype(np.int64) * n + np.maximum(u, v)[cy]
        k, cnt = np.unique(key, return_counts=True)
        for kk, cc in zip(k, cnt):
            ele[kk] = ele.get(kk, 0.0) + cc * fa
    t_wall = piece.pitch[0] * s / 1000

    def edges(d, cond_fn):
        if not d:
            return np.zeros(0, int), np.zeros(0, int), np.zeros(0)
        k = np.fromiter(d.keys(), np.int64)
        a_ = k // n
        b_ = k % n
        A = np.fromiter(d.values(), float)
        dist = np.linalg.norm(cen_m[a_] - cen_m[b_], axis=1)
        return a_, b_, cond_fn(A, dist)

    ia, ib, gi = edges(ion, lambda A, L: 1 / (L / (kappa * A) + t_wall / (bm.mem_kappa_ratio * kappa * A)))
    ea, eb, ge = edges(ele, lambda A, L: bm.sigma_e_s_m * A / L)
    if len(ea):
        same = ctype[ea] == ctype[eb]
        ea, eb, ge = ea[same], eb[same], ge[same]
    # 단자: 바닥 층 세포질
    bot = c[:, :, 0]
    bm_ = mat[:, :, 0]
    g_pos = np.bincount(bot[(bm_ == POS) & (bot >= 0)], minlength=n) * px * px * bm.contact_s_m2
    g_neg = np.bincount(bot[(bm_ == NEG) & (bot >= 0)], minlength=n) * px * px * bm.contact_s_m2
    g_pos[ctype < 0] = 0
    g_neg[ctype > 0] = 0
    # 노드: 전극 0..n-1, 전해질 n..2n-1
    def lap(a_, b_, g, off):
        r = np.concatenate([a_, b_, a_, b_]) + off
        cidx = np.concatenate([a_, b_, b_, a_]) + off
        val = np.concatenate([g, g, -g, -g])
        return r, cidx, val

    r1, c1, v1 = lap(ea, eb, ge, 0)
    r2, c2, v2 = lap(ia, ib, gi, n)
    eps = 1e-9 * max(ge.max() if len(ge) else 0, gi.max() if len(gi) else 0, 1e-12)  # 떠 있는 노드 고정용 아주 작은 누설
    rows = np.concatenate([r1, r2, np.arange(n), np.arange(2 * n)])
    cols = np.concatenate([c1, c2, np.arange(n), np.arange(2 * n)])
    vals = np.concatenate([v1, v2, g_pos + g_neg, np.full(2 * n, eps)])
    Y = coo_matrix((vals, (rows, cols)), shape=(2 * n, 2 * n)).tocsc()
    cr = np.concatenate([np.arange(n), np.arange(n) + n, np.arange(n), np.arange(n) + n])
    cc = np.concatenate([np.arange(n), np.arange(n) + n, np.arange(n) + n, np.arange(n)])
    cv = np.concatenate([cap, cap, -cap, -cap])
    Cm = coo_matrix((cv, (cr, cc)), shape=(2 * n, 2 * n)).tocsc()
    b = np.concatenate([g_pos * bm.u_max, np.zeros(n)])
    # 정상 상태 (다 깨어남)
    cp_sum, cn_sum = cap[ctype > 0].sum(), cap[ctype < 0].sum()
    c_total = 1 / (1 / cp_sum + 1 / cn_sum) if cp_sum and cn_sum else 0.0
    ve = bm.u_max * cp_sum / (cp_sum + cn_sum) if c_total else 0.0
    u_inf = np.where(ctype > 0, bm.u_max - ve, -ve)  # 세포 축전기 전압 (전극 − 전해질)
    # 내부저항: 첫 순간 (축전기 = 단락)
    x0 = splu(csc_matrix(Y + Cm * 1e9)).solve(b)
    i0 = (g_pos * (bm.u_max - x0[:n])).sum()
    esr = bm.u_max / i0 if i0 > 0 else math.inf
    tau = esr * c_total if math.isfinite(esr) else 1.0
    times = np.geomspace(tau * 1e-4, tau * 60, 70)
    x = np.zeros(2 * n)
    t_prev = 0.0
    frac_hist, energy, current = [], [], []
    wake = np.full(n, np.inf)
    prev_frac = np.zeros(n)
    for t in times:
        dt = t - t_prev
        x = splu(csc_matrix(Y + Cm / dt)).solve(Cm @ x / dt + b)
        u = x[:n] - x[n:]
        frac = np.clip(u / np.where(u_inf == 0, 1, u_inf), 0, None)
        hit = (frac >= 0.63) & ~np.isfinite(wake)
        if hit.any():
            w = (0.63 - prev_frac[hit]) / np.maximum(frac[hit] - prev_frac[hit], 1e-12)
            wake[hit] = t_prev + np.clip(w, 0, 1) * dt
        prev_frac = frac
        energy.append(float(0.5 * (cap * u * u).sum()))
        current.append(float((g_pos * (bm.u_max - x[:n])).sum()))
        frac_hist.append(frac)
        t_prev = t
    nonlin = cell_q.energy_area / (0.5 * cell_q.c_area * bm.u_max ** 2)
    live = cap > 0  # 세포질이 없는 (피부만 있는) 작은 세포는 빼고 셈 — 용량이 없으니 깨어남도 없음
    wake[~live] = np.inf
    awake = np.isfinite(wake) & live
    top = cen_m[:, 2] >= np.percentile(cen_m[:, 2], 90)
    vol_ml = n_all.sum() * vvox * 1e6
    return {
        "n_cells": n, "n_pos": int((ctype > 0).sum()), "n_neg": int((ctype < 0).sum()),
        "n_junction_pairs": len(ea), "n_membrane_pairs": int((ctype[ia] != ctype[ib]).sum()) if len(ia) else 0,
        "body_ml": vol_ml, "wet_mass_g": vol_ml * 1.01, "height_mm": piece.height_mm * s,
        "capacitance_f": c_total, "energy_j": 0.5 * c_total * bm.u_max ** 2 * nonlin, "u_max": bm.u_max,
        "esr_ohm": esr, "tau_s": tau, "p_max_w": bm.u_max ** 2 / (4 * esr) if math.isfinite(esr) else 0.0,
        "wake_median_s": float(np.median(wake[awake])) if awake.any() else math.inf,
        "wake_head_s": float(np.median(wake[top & awake])) if (top & awake).any() else math.inf,
        "awake_fraction": float(awake.sum() / max(live.sum(), 1)), "sleeping": int((live & ~awake).sum()),
        "ef_pos_mev": cell_q.positive.mu0_ev * 1000, "ef_neg_mev": cell_q.negative.mu0_ev * 1000,
        "quantum_fraction": cell_q.quantum_fraction, "c_area_uf_cm2": cell_q.c_area * 100,
        "cells": {"center_mm": np.round(cen_m * 1000, 2).tolist(), "type": ctype.astype(int).tolist(),
                  "wake_s": [round(w, 2) if math.isfinite(w) else None for w in wake],
                  "cap_f": np.round(cap, 6).tolist(), "ids": ids.tolist()},
        "series": {"t_s": times.tolist(), "energy_j": energy, "current_a": current},
    }


def describe_prediction(pr: dict) -> str:
    def t(x):
        return "깨지 않음" if not math.isfinite(x) else (f"{x:.0f} s" if x < 120 else f"{x / 60:.1f} 분")

    return "\n".join([
        "[이 작업물이 될 존재 — 생명 신호 (예측)]",
        f"  몸: 높이 {pr['height_mm']:.1f} mm · 부피 {pr['body_ml']:.1f} mL · 약 {pr['wet_mass_g']:.0f} g",
        f"  양자 인공세포 {pr['n_cells']}개 (p {pr['n_pos']} · n {pr['n_neg']}) · 간극연접 {pr['n_junction_pairs']}쌍 · p–n 막 {pr['n_membrane_pairs']}쌍",
        f"  양자층: 페르미 준위 p {pr['ef_pos_mev']:+.0f} / n {pr['ef_neg_mev']:+.0f} meV · 면적당 {pr['c_area_uf_cm2']:.2f} µF/cm² "
        f"(양자 한계 후 남는 용량 {pr['quantum_fraction'] * 100:.0f} %)",
        f"  에너지 {pr['energy_j']:.3f} J ({pr['u_max']:g} V) · 용량 {pr['capacitance_f']:.3f} F · 내부저항 {pr['esr_ohm']:.0f} Ω · 순간 최대 {pr['p_max_w'] * 1000:.1f} mW",
        f"  깨어남 (발에 {pr['u_max']:g} V): 세포 절반 {t(pr['wake_median_s'])} · 머리 {t(pr['wake_head_s'])} · "
        f"깨어난 세포 {pr['awake_fraction'] * 100:.0f} % (잠든 세포 {pr['sleeping']}개)",
        "  (밖에서 충전해야 깨어남 — 스스로 에너지를 만들지는 않음)",
    ])


# ---------- 메시 · 저장 ----------
def piece_meshes(piece: Piece, step: int = 1, wake: dict | None = None) -> dict:
    """재료별 겉면 (출력 좌표 mm) + 꼭짓점마다 세포 깨어남 시간."""
    from .mesh import surface_nets

    mat = piece.material[::step, ::step, ::step]
    cell = piece.cell[::step, ::step, ::step]
    px, pz = piece.pitch
    sp = (px * step, px * step, pz * step)
    org = (piece.offset[0] * px, piece.offset[1] * px, pz / 2)
    wmap = None
    if wake:
        wmap = np.full(int(piece.cell.max()) + 1, np.nan)
        ws = np.array([np.nan if w is None else w for w in wake["wake_s"]])
        wmap[np.array(wake["ids"])] = ws
    out = {}
    for code in (POS, NEG, MEM):
        occ = ndimage.gaussian_filter((mat == code).astype(np.float32), 0.6)
        v, t = surface_nets(0.5 - occ, sp, org)
        if not len(t):
            continue
        attr = None
        if wmap is not None:
            ijk = np.clip(np.round((v - np.array(org)) / np.array(sp)).astype(int), 0, np.array(cell.shape) - 1)
            cid = cell[ijk[:, 0], ijk[:, 1], ijk[:, 2]]
            # 바깥 칸이면 가까운 안쪽 세포
            if (cid < 0).any():
                _, near = ndimage.distance_transform_edt(cell < 0, return_indices=True)
                bad = cid < 0
                q = ijk[bad]
                cid[bad] = cell[near[0][tuple(q.T)], near[1][tuple(q.T)], near[2][tuple(q.T)]]
            attr = wmap[np.maximum(cid, 0)]
        out[ROLE[code]] = (v, t, attr)
    return out


def write_job(job: Job, spec: SculptorSpec, folder: str | Path, meshes: bool = True) -> dict:
    """작업 폴더: G-code · 경로 JSON · 요약 · (작업 뒤 조각) 기억 · 메시."""
    from .mesh import write_stl

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    plan = plan_passes(job, spec)
    preds = [body_signs(p, spec) for p in job.after]
    gc = write_gcode(job, plan, spec, folder / "job.gcode", preds[0] if preds else None)
    (folder / "printer.cfg").write_text(klipper_cfg(spec), encoding="utf-8")
    (folder / "passes.json").write_text(json.dumps(passes_json(job, plan, spec)), encoding="utf-8")
    t = job_time(job, plan, spec)
    med = medium_plan(job, plan, spec)
    t["saline_ml"] = med["fill_ml"]
    t["medium"] = med
    summary = {"title": job.title, "time": t, "ops": [{"kind": o.kind, "note": o.note, "wait_s": o.seconds} for o in job.ops],
               "pieces": [], "recipes": {k: asdict(r) | spec.gel_check(r) for k, r in spec.recipes.items()}}
    for p, pr in zip(job.after, preds):
        p.save(folder / f"{p.name}.npz")
        info = {"name": p.name, "history": p.history, "prediction": {k: v for k, v in pr.items() if k not in ("cells", "series")},
                "text": describe_prediction(pr), "cells": pr["cells"], "series": pr["series"],
                "volumes_ml": {ROLE[c]: float((p.material == c).sum() * p.pitch[0] ** 2 * p.pitch[1] / 1000) for c in ROLE}}
        summary["pieces"].append(info)
        if meshes:
            ms = piece_meshes(p, 1, pr["cells"])
            arrays = {}
            for role, (v, tri, w) in ms.items():
                arrays[f"{role}_v"] = v.astype(np.float32)
                arrays[f"{role}_f"] = tri.astype(np.int32)
                if w is not None:
                    arrays[f"{role}_wake"] = np.nan_to_num(w, nan=-1).astype(np.float32)
                write_stl(folder / f"{p.name}_{role}.stl", v, tri, f"SC-1 {p.name} {role}")
            np.savez_compressed(folder / f"{p.name}_mesh.npz", **arrays)
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    return {"folder": folder, "gcode": gc, "time": t, "predictions": preds, "summary": summary}
