"""전기 임피던스 단층촬영(EIT) — 데스크톱이 배지 속에서 자라는 존재를 '전기로 봄' (빛 조각가 SC-2, 명세: spec/EIT.md).

멸균생리식염수(154 mM, 1.56 S/m)는 도체다. 수조 네 벽 안쪽에 흑연 막대(연필심) 전극을 두 줄(링) 붙이고 이웃한 두 전극으로
약한 교류(10 kHz)를 흘린 뒤, 나머지 이웃 쌍의 전압을 잰다. 존재(세포질 = rGO 전자 통로 + 이온, 막 = 이온 절반)가 배지와
전도도가 달라 전압 분포가 바뀐다 → 설계(데스크톱이 아는 기대 상태)와 잰 값의 차이로 '어디가 다른가'를 그림으로 되찾는다.

- 전압: 구동 쌍 전압을 20 mV 로 맞춤 (≤ 50 mV) — 탄소 전극 안전 전압창 0.8 V 보다 훨씬 낮아 전기분해 없음.
  10 kHz 교류라 평균(직류)이 0 → 누설 감시(직류 50 µA, 저역 통과)와 주파수로 갈림.
- 정방향: 수조 전체를 칸으로 나눈 유한체적 (가운데 출력 기둥은 7 mm, 벽 · 바닥 쪽은 점점 굵게), 칸 사이 전도는 반 칸씩 직렬,
  전극은 벽 칸에 접촉 임피던스(전기이중층, 10 kHz)로 이어진 마디. 기준(접지) = 기존 배지 전도도 전극 자리.
- 역문제: 한 번 선형화한 차이 영상. 야코비안은 수반(adjoint) 장: ∂V_dp/∂σ_j = −Σ_면 ∂g/∂σ_j (Δu_d)(Δu_p).
  잡음으로 정규화하고 NOSER (R = diag JᵀJ) 티호노프: δσ = R⁻¹Jᵀ(J R⁻¹Jᵀ + λI)⁻¹ δV.
- 셈하지 않는 것: 탄소섬유 프레임 봉 · 나사봉 · 방수 통 (받침과 기둥만 절연체로 넣음), 막의 용량성(위상), 전극 둘레 퍼짐 저항의 세밀함.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

from .electrolyte import nacl_conductivity

SIGMA_INSULATOR = 1e-6  # PETG 받침 · 기둥 (S/m, 사실상 절연)


@dataclass
class EITSpec:
    # 전극 자리:
    #   "collar_bed"   (기본) A 줄 = 떠 있는 잉크 우물 테 치마 안쪽 (z 319, 치마 끝 318 아래로 안 나옴) · B 줄 = 배양 받침 테두리 (받침과 함께 내려감)
    #   "collar_riser" A 줄 = 위와 같음 · B 줄 = 받침 기둥 네 옆면 위쪽
    #   "sleeve"       테를 z 288 까지 내린 소매에 두 줄 — 도구 갠트리(z 283–316) 와 겹치므로 도구 단계 전에 소매를 들어 올려야 함
    #   "walls"        수조 벽 (비교용)
    place: str = "collar_bed"
    rings_z_mm: tuple[float, ...] = (313.0, 296.0)  # sleeve · walls 의 두 줄 높이
    collar_z_mm: float = 319.0  # A 줄: 치마 끝(318) 과 잉크층(320) 사이 — 갠트리 빔 윗면 316 보다 위
    collar_strip_mm2: float = 12.0  # 치마 안쪽 면에 박은 흑연 띠 6 × 2 mm (튀어나오지 않음)
    bed_strip_mm2: float = 18.0  # 받침 옆면 위쪽 흑연 띠 6 × 3 mm
    bed_drop_mm: float = 1.5  # 받침 윗면에서 띠 가운데까지
    riser_strip_mm2: float = 36.0  # 기둥 옆면 흑연 띠 6 × 6 mm
    riser_drop_mm: float = 12.0  # 받침 아래면에서 띠 가운데까지
    skirt_bottom_mm: float = 318.0  # 잉크 우물 테 치마 끝 (= 수면 − 잉크층 − 2)
    gantry_parked: bool = True  # EIT 는 도구 갠트리가 주차했을 때만 잼 (빔 · 캐리지 · 레일 = 절연체로 넣음)
    per_wall: int = 4  # 면마다 전극 → 링마다 16
    sleeve_mm: float = 75.0  # 소매 안쪽 반폭 (= 잉크 우물 테 안쪽)
    sleeve_t_mm: float = 3.0  # PETG 두께 (절연)
    sleeve_bottom_mm: float = 288.0  # (sleeve) 소매 끝
    meas_ms: float = 1.08  # 값 하나 재는 시간 (가정) → 한 장 = 값 수 × 이것
    integrate_layers: int = 10  # 오래 남는 잘못(덧굳음 · 빠진 곳)은 여러 층 동안 같은 자리 → 그만큼 더 평균
    protocol: str = "adjacent"  # "adjacent" = 링 안 이웃 쌍 · "deep" = + 위아래 쌍(A_i–B_i) + 링 안 4칸 건너 쌍 (몸을 꿰뚫는 전류)
    rod: str = "흑연 띠 · 막대 (흑연 시트를 오린 띠 또는 2B 연필심) — 드러낸 면만 배지에 닿고 나머지는 실리콘으로 덮음 (금속 없음)"
    rod_d_mm: float = 2.0
    rod_len_mm: float = 20.0
    freq_hz: float = 10e3
    drive_mv: float = 20.0  # 구동 쌍 전압 (진폭)
    v_cap_mv: float = 50.0
    c_dl_f_m2: float = 0.1  # 흑연 전기이중층 10 µF/cm² (가정) → 접촉 임피던스 |Z| = 1/(2πfC)
    noise_rel: float = 1e-3  # 잰 전압의 0.1 % (가정)
    noise_floor_v: float = 1e-6
    fine_mm: float = 7.5
    fine_xy_mm: float = 75.0  # 가운데 출력 기둥 반폭 (= 소매 안쪽, 칸 경계를 맞춤)
    fine_z_mm: tuple[float, float] = (190.0, 330.0)
    grow: float = 1.3  # 바깥으로 칸이 굵어지는 비
    porosity: float = 0.97  # 젤 속 이온이 지나는 몫 (PVA · GO 1–2 %, 가정)
    sigma_e_s_m: float = 2.0  # 광환원 rGO 전자 전도 (sculpt.BodyModel 과 같은 가정)
    mem_ratio: float = 0.5  # 막 이온 전도 / 젤 이온 전도 (sculpt.BodyModel 과 같은 가정)
    mu: float = 0.1  # 정규화 세기 (λ = μ · 평균 대각)
    noser_p: float = 0.5  # R = diag(JᵀJ)^p — 1 이면 둔한 깊은 칸이 부풀어 위치가 틀어짐 (덧굳음 시험으로 고름)
    roi_depth_mm: float = 80.0  # 되찾는 칸: 소매 안쪽 기둥, 수면에서 이만큼 아래까지
    probe_mm: tuple[float, float, float] = (-130.0, 136.0, 80.0)  # 기존 배지 전도도 전극 = 접지

    @property
    def zc_ohm_m2(self) -> float:
        """전기이중층 면적 임피던스 |Z| = 1/(2πfC) (Ω·m²)."""
        return 1 / (2 * math.pi * self.freq_hz * self.c_dl_f_m2)

    @property
    def contact_ohm(self) -> float:
        """막대 전극(sleeve · walls) 하나의 접촉 임피던스."""
        return self.zc_ohm_m2 / (math.pi * self.rod_d_mm * self.rod_len_mm * 1e-6)


def _graded(lo: float, hi: float, f_lo: float, f_hi: float, h: float, grow: float, first: tuple = ()) -> np.ndarray:
    """[lo, hi] 의 칸 경계: [f_lo, f_hi] 는 h 칸, 바깥은 first 칸(소매 벽) 다음 grow 비로 굵어지다 끝에 정확히 맞춤."""
    n = max(1, round((f_hi - f_lo) / h))
    mid = np.linspace(f_lo, f_hi, n + 1)

    def side(span):
        if span <= 1e-9:
            return np.array([])
        fixed = [f for f in first if f < span]
        rest = span - sum(fixed)
        sizes, s = [], h * grow
        while sum(sizes) < rest:
            sizes.append(s)
            s *= grow
        sizes = np.array(sizes) * rest / sum(sizes) if sizes else np.array([])
        return np.cumsum(np.concatenate([fixed, sizes]))

    left = f_lo - side(f_lo - lo)[::-1]
    right = f_hi + side(hi - f_hi)
    return np.concatenate([left, mid, right]) if len(left) else np.concatenate([[lo], mid[1:], right]) if lo < f_lo else np.concatenate([mid, right])


@dataclass
class Grid:
    ex: np.ndarray
    ey: np.ndarray
    ez: np.ndarray

    @property
    def shape(self):
        return len(self.ex) - 1, len(self.ey) - 1, len(self.ez) - 1

    @property
    def n(self) -> int:
        return int(np.prod(self.shape))

    def centers(self):
        return [(e[1:] + e[:-1]) / 2 for e in (self.ex, self.ey, self.ez)]

    def widths(self):
        return [np.diff(e) for e in (self.ex, self.ey, self.ez)]

    def index(self, x, y, z) -> int:
        i = int(np.clip(np.searchsorted(self.ex, x) - 1, 0, self.shape[0] - 1))
        j = int(np.clip(np.searchsorted(self.ey, y) - 1, 0, self.shape[1] - 1))
        k = int(np.clip(np.searchsorted(self.ez, z) - 1, 0, self.shape[2] - 1))
        return int(np.ravel_multi_index((i, j, k), self.shape))

    def box_fraction(self, lo, hi) -> np.ndarray:
        """축에 나란한 상자가 칸마다 차지하는 몫."""
        f = []
        for e, a, b in zip((self.ex, self.ey, self.ez), lo, hi):
            ov = np.clip(np.minimum(e[1:], b) - np.maximum(e[:-1], a), 0, None)
            f.append(ov / np.diff(e))
        return f[0][:, None, None] * f[1][None, :, None] * f[2][None, None, :]


def make_grid(tank_mm: float, fill_mm: float, es: EITSpec) -> Grid:
    t = tank_mm / 2
    first = (es.sleeve_t_mm,)  # 잉크 우물 테 (치마 · 소매) 벽 두께 한 칸
    exy = _graded(-t, t, -es.fine_xy_mm, es.fine_xy_mm, es.fine_mm, es.grow, first)
    # z: 수면 · 잉크층 바닥(320) · 치마 끝(318) 에 칸 경계를 맞추고, 그 아래로 fine 칸, 더 아래는 굵게
    ink_b = fill_mm - 10.0
    top = [fill_mm, (fill_mm + ink_b) / 2, ink_b, es.skirt_bottom_mm]
    z = es.skirt_bottom_mm
    while z - es.fine_mm >= es.fine_z_mm[0] - 1e-9:
        z -= es.fine_mm
        top.append(z)
    low = _graded(0.0, z, z, z, es.fine_mm, es.grow)[:-1]  # 0 → z (굵어짐)
    ez = np.concatenate([low[low < z - 1e-9], np.array(top[::-1])])
    return Grid(exy, exy.copy(), np.unique(np.round(ez, 6)))


# ---------- 전도도 지도 ----------
@dataclass
class Scene:
    """한 순간의 배양조: 배지 · 잉크층 · 받침 · (K 층까지 자란) 존재 · 덧붙인 덩어리."""

    tank_mm: float = 350.0
    fill_mm: float = 330.0
    well_mm: float = 150.0
    ink_depth_mm: float = 10.0
    sigma_med: float = field(default_factory=lambda: nacl_conductivity(0.154))
    sigma_ink: float = field(default_factory=lambda: nacl_conductivity(0.010))
    piece: object = None  # sculpt.Piece
    layer: int | None = None
    blobs: list = field(default_factory=list)  # 배지 속 덧붙은 덩어리 (중심 xyz mm, 반지름 mm, σ S/m) — 존재와 겹치지 않는 곳
    bed: bool = True
    gantry: bool = True

    @property
    def dz(self) -> float:
        """받침 윗면(작업물 z = 0) 의 장면 높이 — K 층 윗면이 수면."""
        if self.piece is None or self.layer is None:
            return self.fill_mm - 40.0
        return self.fill_mm - (self.layer + 1) * self.piece.pitch[1]

    def ion_sigma(self, x, y, z):
        w = self.well_mm / 2
        ink = (np.abs(x) < w) & (np.abs(y) < w) & (z > self.fill_mm - self.ink_depth_mm)
        return np.where(ink, self.sigma_ink, self.sigma_med)


def conductivity(grid: Grid, sc: Scene, es: EITSpec) -> np.ndarray:
    nx, ny, nz = grid.shape
    w = sc.well_mm / 2
    sig = np.full(grid.shape, sc.sigma_med)
    f_ink = grid.box_fraction((-w, -w, sc.fill_mm - sc.ink_depth_mm), (w, w, sc.fill_mm + 1))
    sig += f_ink * (sc.sigma_ink - sc.sigma_med)
    vol = np.einsum("i,j,k->ijk", *grid.widths())
    # 존재: 작업물 칸(0.41 × 0.41 × 0.30 mm)을 큰 칸에 부피 비로 더함 (산술 평균, 가정)
    if sc.piece is not None:
        from .sculpt import EMPTY, MEM, NEG, POS

        p = sc.piece
        mat = p.material
        kmax = mat.shape[2] - 1 if sc.layer is None else min(sc.layer, mat.shape[2] - 1)
        idx = np.argwhere(mat[:, :, : kmax + 1] != EMPTY)
        m = mat[idx[:, 0], idx[:, 1], idx[:, 2]]
        x = (p.offset[0] + idx[:, 0]) * p.pitch[0]
        y = (p.offset[1] + idx[:, 1]) * p.pitch[0]
        z = (idx[:, 2] + 0.5) * p.pitch[1] + sc.dz
        si = sc.ion_sigma(x, y, z)
        s_mat = np.where((m == POS) | (m == NEG), es.porosity * si + es.sigma_e_s_m, np.where(m == MEM, es.mem_ratio * si, si))
        ok = z < sc.fill_mm
        sig += _deposit(grid, x[ok], y[ok], z[ok], (s_mat - si)[ok] * p.pitch[0] ** 2 * p.pitch[1], vol)
    for (c, r, s) in sc.blobs:
        g = np.arange(-r + 0.5, r, 1.0)  # 1 mm 점
        X, Y, Z = np.meshgrid(g, g, g, indexing="ij")
        ins = X ** 2 + Y ** 2 + Z ** 2 <= r * r
        x, y, z = X[ins] + c[0], Y[ins] + c[1], Z[ins] + c[2]
        sig += _deposit(grid, x, y, z, s - sc.ion_sigma(x, y, z), vol)
    # 잉크 우물 테 (PETG, 절연): 치마는 318 까지 · sleeve 면 소매를 288 까지 내림
    a, b = es.sleeve_mm, es.sleeve_mm + es.sleeve_t_mm
    z0, z1 = (es.sleeve_bottom_mm if es.place == "sleeve" else es.skirt_bottom_mm), sc.fill_mm + 5
    for lo, hi in (((-b, -b, z0), (b, -a, z1)), ((-b, a, z0), (b, b, z1)), ((-b, -b, z0), (-a, b, z1)), ((a, -b, z0), (b, b, z1))):
        sig += grid.box_fraction(lo, hi) * (SIGMA_INSULATOR - sig)
    if sc.bed:  # 받침 · 기둥 · 너트 판 (PETG, 절연) — 받침과 함께 내려감
        for lo, hi in _bed_boxes(sc.dz):
            sig += grid.box_fraction(lo, hi) * (SIGMA_INSULATOR - sig)
    if sc.gantry and es.gantry_parked:  # 주차한 도구 갠트리 · 레일 · 모터 통 (겉이 에폭시 · PETG — 절연으로 봄, 가정)
        for lo, hi in _gantry_boxes():
            sig += grid.box_fraction(lo, hi) * (SIGMA_INSULATOR - sig)
    return np.maximum(sig, SIGMA_INSULATOR)


def _bed_boxes(dz: float) -> list:
    from .layout import BED_CARRIAGE, PLATE, RISER

    return [((-60, -60, dz - PLATE), (60, 60, dz)),
            ((-20, -20, dz - PLATE - RISER), (20, 20, dz - PLATE)),
            ((-114, -114, dz - PLATE - RISER - BED_CARRIAGE), (114, 114, dz - PLATE - RISER))]


_GANTRY: list | None = None


def _gantry_boxes() -> list:
    """layout 의 도구 갠트리 중 고정 부품 + 주차 자리 (쓸고 지나가는 범위는 뺌)."""
    global _GANTRY
    if _GANTRY is None:
        from .layout import make_light_layout

        _GANTRY = [(b.lo, b.hi) for b in make_light_layout().boxes if b.kind == "gantry" and "(쓸림)" not in b.name]
    return _GANTRY


def _cell_ids(grid: Grid, x, y, z):
    nx, ny, nz = grid.shape
    i = np.clip(np.searchsorted(grid.ex, x) - 1, 0, nx - 1)
    j = np.clip(np.searchsorted(grid.ey, y) - 1, 0, ny - 1)
    k = np.clip(np.searchsorted(grid.ez, z) - 1, 0, nz - 1)
    return (i * ny + j) * nz + k


def _deposit(grid: Grid, x, y, z, dvol_sigma, vol) -> np.ndarray:
    out = np.bincount(_cell_ids(grid, x, y, z), weights=dvol_sigma, minlength=grid.n).reshape(grid.shape)
    return out / vol


# ---------- 전극 ----------
def _ring(half: float, z: float, per_side: int, inset: float) -> list:
    """정사각 둘레 (반폭 half) 에 면마다 per_side 개, 시계 반대 방향. inset = 면에서 배지 쪽으로 (+ 안쪽 · − 바깥쪽)."""
    s = (np.arange(per_side) + 0.5) / per_side * 2 * half - half
    h = half - inset
    return ([(x, -h, z) for x in s] + [(h, y, z) for y in s] + [(x, h, z) for x in s[::-1]] + [(-h, y, z) for y in s[::-1]])


def electrode_sites(es: EITSpec, sc: "Scene", tank_mm: float) -> tuple[list, np.ndarray, np.ndarray]:
    """→ (위치 목록, 링 번호, 접촉 임피던스 Ω). B 줄(받침 · 기둥) 은 받침과 함께 내려감."""
    n = es.per_wall
    if es.place in ("collar_bed", "collar_riser"):
        a = _ring(es.sleeve_mm, es.collar_z_mm, n, 1.0)  # 치마 안쪽 면 → 안쪽 칸
        if es.place == "collar_bed":
            b = _ring(60.0, sc.dz - es.bed_drop_mm, n, -1.0)  # 받침 옆면 → 바깥 칸
            area_b = es.bed_strip_mm2
        else:
            from .layout import PLATE

            b = _ring(20.0, sc.dz - PLATE - es.riser_drop_mm, n, -4.0)
            area_b = es.riser_strip_mm2
        pos = a + b
        zc = np.array([es.zc_ohm_m2 / (es.collar_strip_mm2 * 1e-6)] * len(a) + [es.zc_ohm_m2 / (area_b * 1e-6)] * len(b))
    else:
        half = tank_mm / 2 if es.place == "walls" else es.sleeve_mm
        pos = [p for z in es.rings_z_mm for p in _ring(half, z, n, 1.0)]
        zc = np.full(len(pos), es.contact_ohm)
    ring = np.repeat(np.arange(len(pos) // (4 * n)), 4 * n)
    return pos, ring, zc


def drive_pairs(ring: np.ndarray, protocol: str = "adjacent") -> list[tuple[int, int]]:
    """구동 · 측정 쌍. adjacent: 링 안 이웃 (고리). deep: + 링 사이 같은 자리 (A_i–B_i) + 링 안 4칸 건너."""
    out = []
    rings = [np.nonzero(ring == r)[0] for r in np.unique(ring)]
    for ids in rings:
        out += [(int(ids[i]), int(ids[(i + 1) % len(ids)])) for i in range(len(ids))]
    if protocol == "deep":
        for a, b in zip(rings[:-1], rings[1:]):
            out += [(int(x), int(y)) for x, y in zip(a, b)]
        for ids in rings:
            out += [(int(ids[i]), int(ids[(i + 4) % len(ids)])) for i in range(len(ids))]
    return out


# ---------- 정방향 ----------
class Forward:
    """유한체적 + 전극 마디. solve() 는 쌍마다 단위 전류(1 A) 일 때의 칸 · 전극 전위."""

    def __init__(self, grid: Grid, sigma: np.ndarray, cells: np.ndarray, zc: np.ndarray, es: EITSpec, ground: int):
        self.grid, self.sigma, self.cells, self.zc, self.es, self.ground = grid, sigma, cells, np.asarray(zc, float), es, ground
        nx, ny, nz = grid.shape
        widths = [w * 1e-3 for w in grid.widths()]  # m
        idx = np.arange(grid.n).reshape(grid.shape)
        A, B, G, DA, DB = [], [], [], [], []
        for ax in range(3):
            a = np.take(idx, range(grid.shape[ax] - 1), axis=ax).ravel()
            b = np.take(idx, range(1, grid.shape[ax]), axis=ax).ravel()
            ia, ib = np.unravel_index(a, grid.shape), np.unravel_index(b, grid.shape)
            o1, o2 = [d for d in range(3) if d != ax]
            area = widths[o1][ia[o1]] * widths[o2][ia[o2]]
            ha, hb = widths[ax][ia[ax]] / 2, widths[ax][ib[ax]] / 2
            sa, sb = sigma.ravel()[a], sigma.ravel()[b]
            g = area / (ha / sa + hb / sb)
            A.append(a), B.append(b), G.append(g)
            DA.append(g * g * ha / (area * sa * sa))  # ∂g/∂σ_a
            DB.append(g * g * hb / (area * sb * sb))
        self.fa, self.fb, self.fg = np.concatenate(A), np.concatenate(B), np.concatenate(G)
        self.dga, self.dgb = np.concatenate(DA), np.concatenate(DB)
        ne = len(cells)
        n = grid.n + ne
        gc = 1 / self.zc  # 전극마다 접촉 전도
        ea = np.arange(grid.n, n)
        rows = np.concatenate([self.fa, self.fb, self.fa, self.fb, ea, cells, ea, cells])
        cols = np.concatenate([self.fa, self.fb, self.fb, self.fa, ea, cells, cells, ea])
        vals = np.concatenate([self.fg, self.fg, -self.fg, -self.fg, gc, gc, -gc, -gc])
        K = sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
        keep = np.setdiff1d(np.arange(n), [ground])
        self.keep, self.n = keep, n
        self.K = K
        self.lu = splu(K[keep][:, keep].tocsc(), permc_spec="MMD_AT_PLUS_A")

    def solve(self, pairs: list[tuple[int, int]]) -> np.ndarray:
        """(마디 수, 쌍 수) 전위 — 전극 a 로 +1 A 넣고 b 로 뺌."""
        f = np.zeros((self.n, len(pairs)))
        for c, (a, b) in enumerate(pairs):
            f[self.grid.n + a, c] = 1.0
            f[self.grid.n + b, c] = -1.0
        u = np.zeros((self.n, len(pairs)))
        u[self.keep] = self.lu.solve(f[self.keep])
        return u

    def electrode_currents(self, u: np.ndarray) -> np.ndarray:
        """전극마다 배지로 나가는 전류 (A) — 넣은 전류 그대로여야 하고 합은 0."""
        return (u[self.grid.n:] - u[self.cells]) / self.zc[:, None]


def transfer(u: np.ndarray, nvox: int, pairs) -> np.ndarray:
    """Z[d, p] = 구동 d (1 A) 일 때 측정 쌍 p 의 전압 (Ω)."""
    ue = u[nvox:]
    return np.stack([ue[a] - ue[b] for a, b in pairs], axis=1)  # (구동, 측정)


def measure_mask(pairs) -> np.ndarray:
    """구동 전극을 포함한 측정 쌍은 뺌 (전류가 흐르는 전극은 접촉 전압 때문에 못 믿음)."""
    m = np.ones((len(pairs), len(pairs)), dtype=bool)
    for d, (a, b) in enumerate(pairs):
        for p, (c, e) in enumerate(pairs):
            if {a, b} & {c, e}:
                m[d, p] = False
    return m


def jacobian(fw: Forward, u: np.ndarray, roi: np.ndarray, chunk: int = 1000) -> np.ndarray:
    """∂Z[d,p]/∂σ_j (j ∈ roi) — (구동 × 측정, roi). 수반 장 = 같은 쌍의 단위 전류 장 (상반성)."""
    pos = np.full(fw.grid.n, -1)
    pos[roi] = np.arange(len(roi))
    P = u.shape[1]
    J = np.zeros((P * P, len(roi)))
    for side, dg in ((fw.fa, fw.dga), (fw.fb, fw.dgb)):
        sel = np.nonzero(pos[side] >= 0)[0]
        for s0 in range(0, len(sel), chunk):
            f = sel[s0:s0 + chunk]
            du = u[fw.fa[f]] - u[fw.fb[f]]  # (면, 쌍)
            outer = (du[:, :, None] * du[:, None, :]).reshape(len(f), P * P) * (-dg[f])[:, None]
            S = sp.coo_matrix((np.ones(len(f)), (np.arange(len(f)), pos[side[f]])), shape=(len(f), len(roi))).tocsr()
            J += (S.T @ outer).T
    return J


# ---------- 한 장면 재기 ----------
@dataclass
class Frame:
    sigma: np.ndarray
    v: np.ndarray  # 잰 전압 (V), 측정 마스크 순서
    z: np.ndarray  # 전달 임피던스 전체 (Ω)
    current_a: float
    drive_v: float
    fw: Forward
    u: np.ndarray


class EIT:
    """정해진 격자 · 전극으로 장면을 재고, 기대 상태 대비 차이를 되찾음."""

    def __init__(self, es: EITSpec | None = None, tank_mm: float = 350.0, fill_mm: float = 330.0):
        self.es = es or EITSpec()
        self.tank_mm, self.fill_mm = tank_mm, fill_mm
        self.grid = make_grid(tank_mm, fill_mm, self.es)
        _, self.ring, _ = electrode_sites(self.es, Scene(tank_mm=tank_mm, fill_mm=fill_mm), tank_mm)
        self.pairs = drive_pairs(self.ring, self.es.protocol)
        self.mask = measure_mask(self.pairs)
        self.ground = self.grid.index(*self.es.probe_mm)
        xc, yc, zc = self.grid.centers()
        es = self.es
        inx = np.nonzero(np.abs(xc) <= es.fine_xy_mm)[0]
        inz = np.nonzero((zc >= fill_mm - es.roi_depth_mm) & (zc <= fill_mm))[0]
        I, J_, K = np.meshgrid(inx, inx, inz, indexing="ij")
        self.roi = np.ravel_multi_index((I.ravel(), J_.ravel(), K.ravel()), self.grid.shape)
        self.current_a: float | None = None
        self._frames: dict = {}
        self._jac: dict = {}

    def frame(self, sc: Scene) -> Frame:
        if id(sc) in self._frames:
            return self._frames[id(sc)][1]
        sig = conductivity(self.grid, sc, self.es)
        pos, _, zc = electrode_sites(self.es, sc, self.tank_mm)  # B 줄은 받침과 함께 내려감
        cells = np.array([self.grid.index(*p) for p in pos])
        self.pos = pos
        fw = Forward(self.grid, sig, cells, zc, self.es, self.ground)
        u = fw.solve(self.pairs)
        z = transfer(u, self.grid.n, self.pairs)
        if self.current_a is None:  # 처음(기대 상태) 에 구동 전압 = drive_mv 로 전류를 정하고 그다음엔 같은 전류
            self.current_a = self.es.drive_mv * 1e-3 / float(np.max(np.abs(np.diag(z))))
        i = self.current_a
        f = Frame(sig, i * z[self.mask], z, i, float(np.max(np.abs(np.diag(z)))) * i, fw, u)
        self._frames[id(sc)] = (sc, f)  # sc 를 붙잡아 id 가 다시 쓰이지 않게
        return f

    def noise_std(self, ref: Frame, n_avg: int = 1) -> np.ndarray:
        """한 장 잡음 / √(평균 장 수) — 우연 잡음만 줄어듦 (모형 오차 · 느린 흐름은 그대로, 명세 참고)."""
        return (self.es.noise_rel * np.abs(ref.v) + self.es.noise_floor_v) / math.sqrt(max(1, n_avg))

    def noisy(self, f: Frame, n_avg: int = 1, seed: int = 0) -> np.ndarray:
        return f.v + np.random.default_rng(seed).normal(0, 1, f.v.shape) * self.noise_std(f, n_avg)

    def reconstruct(self, ref: Frame, meas_v: np.ndarray, n_avg: int = 1) -> tuple[np.ndarray, dict]:
        """기대 상태(ref) 에서 선형화한 한 번 풀이 → ROI 칸의 δσ (S/m)."""
        if id(ref) not in self._jac:
            self._jac[id(ref)] = (ref, (jacobian(ref.fw, ref.u, self.roi) * ref.current_a)[self.mask.ravel()])
        J = self._jac[id(ref)][1]
        s = self.noise_std(ref, n_avg)
        Jw, dv = J / s[:, None], (meas_v - ref.v) / s
        r = np.einsum("ij,ij->j", Jw, Jw) ** self.es.noser_p + 1e-30  # NOSER
        JR = Jw / r
        M = JR @ Jw.T
        lam = self.es.mu * np.trace(M) / len(M)
        ds = JR.T @ np.linalg.solve(M + lam * np.eye(len(M)), dv)
        img = np.zeros(self.grid.n)
        img[self.roi] = ds
        snr = float(np.linalg.norm(meas_v - ref.v) / np.linalg.norm(s))
        return img.reshape(self.grid.shape), {"snr": snr, "lambda": lam}

    def truth(self, a: Scene, b: Scene) -> np.ndarray:
        return self.frame(b).sigma - self.frame(a).sigma

    def locate(self, img: np.ndarray, sign: float = 0.0) -> tuple[np.ndarray, float]:
        """반값 이상 칸의 무게중심 (mm) · 그 부피 (mL). sign 이 있으면 그 부호만."""
        v = img.copy() if sign == 0 else np.clip(img * np.sign(sign), 0, None)
        a = np.abs(v)
        sel = a >= 0.5 * a.max()
        xc, yc, zc = self.grid.centers()
        X, Y, Z = np.meshgrid(xc, yc, zc, indexing="ij")
        w = a * sel
        c = np.array([(w * X).sum(), (w * Y).sum(), (w * Z).sum()]) / w.sum()
        vol = np.einsum("i,j,k->ijk", *self.grid.widths())
        return c, float(vol[sel].sum() / 1000)


# ---------- 보고서 ----------
def _scenarios(eit: EIT, piece, layer: int, spec_light) -> list[dict]:
    fill = eit.fill_mm
    base = Scene(fill_mm=fill, well_mm=spec_light.ink.well_mm, ink_depth_mm=spec_light.ink.depth_mm, piece=piece, layer=layer)
    out = []
    # 1) 덧굳음 덩어리: 몸 옆 18 mm, 잉크층 바로 아래 — 위층 빛이 새어 굳은 rGO 덩어리 (지름 12 mm)
    xs = np.nonzero(piece.material[:, :, : layer + 1].any(axis=(1, 2)))[0]
    x_edge = (piece.offset[0] + xs.max()) * piece.pitch[0]
    c_blob = (x_edge + 18.0, 0.0, fill - 22.0)
    s_cured = eit.es.porosity * base.sigma_med + eit.es.sigma_e_s_m
    out.append({"name": "덧굳은 덩어리 (지름 12 mm, 몸 옆)", "a": base,
                "b": Scene(**{**base.__dict__, "blobs": [(c_blob, 6.0, s_cured)]}), "center": np.array(c_blob), "sign": 1.0,
                "vol_ml": 4 / 3 * math.pi * 6 ** 3 / 1000})
    # 2) 빠진 곳: 몸통 속 지름 12 mm 가 굳지 않음 → 그 칸들이 배지 (작업물 격자에서 지움)
    from dataclasses import replace as _rep

    from .sculpt import EMPTY

    built = np.argwhere(piece.material[:, :, max(0, layer - 60): max(1, layer - 20)] != EMPTY)
    ci = built.mean(axis=0) + np.array([0, 0, max(0, layer - 60)])
    c_miss = np.array([(piece.offset[0] + ci[0]) * piece.pitch[0], (piece.offset[1] + ci[1]) * piece.pitch[0],
                       (ci[2] + 0.5) * piece.pitch[1] + base.dz])
    X, Y, Z = np.meshgrid(*[np.arange(n) for n in piece.material.shape], indexing="ij")
    d2 = (((piece.offset[0] + X) * piece.pitch[0] - c_miss[0]) ** 2 + ((piece.offset[1] + Y) * piece.pitch[0] - c_miss[1]) ** 2
          + ((Z + 0.5) * piece.pitch[1] + base.dz - c_miss[2]) ** 2)
    holed = _rep(piece, material=np.where(d2 <= 36.0, EMPTY, piece.material).astype(piece.material.dtype))
    removed = float((piece.material[d2 <= 36.0] != EMPTY).sum() * piece.pitch[0] ** 2 * piece.pitch[1] / 1000)
    out.append({"name": "빠진 곳 (지름 12 mm, 몸통 속)", "a": base, "b": Scene(**{**base.__dict__, "piece": holed}),
                "center": c_miss, "sign": 0.0, "vol_ml": removed})
    # 3) 자람: Δ = 10 층 (받침도 함께 내려감)
    d = 10
    prev = Scene(**{**base.__dict__, "layer": max(0, layer - d)})
    out.append({"name": f"자람 ({d}층 = {d * piece.pitch[1]:.1f} mm, 받침도 내려감)", "a": prev, "b": base, "center": None, "sign": 0.0,
                "vol_ml": None})
    return out


PLACES = {
    "collar_bed": "A 줄 잉크 우물 테 치마 (z 319) + B 줄 배양 받침 테두리 (받침과 함께 내려감)",
    "collar_riser": "A 줄 잉크 우물 테 치마 (z 319) + B 줄 받침 기둥 옆면",
    "sleeve": "테를 z 288 까지 내린 소매에 두 줄 (z 313 · 296) — 도구 단계 전에 소매를 들어 올려야 함",
    "walls": "수조 벽 두 줄 (z 300 · 265)",
}


def _evaluate(eit: EIT, piece, layer: int, spec_l, n_avg: int) -> tuple[list, list, Frame]:
    rows, figs = [], []
    scen = _scenarios(eit, piece, layer, spec_l)
    for n, s in enumerate(scen):
        ref, meas = eit.frame(s["a"]), eit.frame(s["b"])
        img, info = eit.reconstruct(ref, eit.noisy(meas, n_avg, seed=n), n_avg)
        tru = eit.truth(s["a"], s["b"])
        tr, im = tru.ravel()[eit.roi], img.ravel()[eit.roi]
        corr = float(np.corrcoef(tr, im)[0, 1]) if tr.std() > 0 and im.std() > 0 else 0.0
        dv = meas.v - ref.v
        row = {"name": s["name"], "snr1": float(np.linalg.norm(dv) / np.linalg.norm(eit.noise_std(ref))),
               "snr": float(np.linalg.norm(dv) / np.linalg.norm(eit.noise_std(ref, n_avg))),  # 잡음 없는 차이 / 평균 뒤 잡음
               "corr": corr, "max_dv_uv": float(np.max(np.abs(dv)) * 1e6)}
        if s["center"] is not None:  # 오래 남는 잘못: 여러 층 평균 · 선형 영역에서 신호 ∝ 부피 → 신호/잡음 3 이 되는 지름
            k = eit.es.integrate_layers
            row["snr_k"] = row["snr"] * math.sqrt(k)
            row["d_min_mm"] = 12.0 * (3.0 / max(row["snr"], 1e-9)) ** (1 / 3)
            row["d_min_k_mm"] = 12.0 * (3.0 / max(row["snr_k"], 1e-9)) ** (1 / 3)
            c, vol = eit.locate(img, s["sign"])
            row.update(err_mm=float(np.linalg.norm(c - s["center"])), center=c.tolist(), truth_center=s["center"].tolist(),
                       vol_ml=vol, truth_vol_ml=s["vol_ml"])
        rows.append(row)
        figs.append((s, tru, img))
    return rows, figs, eit.frame(scen[0]["a"])


def eit_report(job_or_shape="being", layer: int | None = None, out_dir: str | Path | None = None,
               es: EITSpec | None = None, height_mm: float = 0.0, compare: bool = False) -> dict:
    """빛 조각가 작업 하나(또는 모양 이름)의 K 층 순간: 전극 · 전압 · 세 가지 차이(덧굳음 · 빠짐 · 자람)의 검출 · 위치 오차.

    job_or_shape: lightsculpt.light_job 결과(dict) 또는 모양 이름 ("being", "coupon", …).
    compare: 다른 전극 자리(PLACES) 도 같은 세 차이로 재어 표로 (자리마다 약 30 s 더).
    한 층을 빚는 동안(수 분) 같은 장면을 여러 장 재어 평균 → 우연 잡음이 √N 로 줄어듦.
    """
    import time
    from dataclasses import replace

    from .lightsculpt import LightSculptorSpec, exposure_plan
    from .sculpt import CellParams, design

    t0 = time.time()
    if isinstance(job_or_shape, dict):
        spec_l, piece = job_or_shape["spec"], job_or_shape["piece"]
        plan = job_or_shape.get("plan")
    else:
        spec_l = LightSculptorSpec()
        piece = design(job_or_shape, height_mm, CellParams(), spec_l.design_spec(), str(job_or_shape))
        plan = None
    plan = plan or exposure_plan(piece, spec_l)
    ks = np.nonzero(piece.material.any(axis=(0, 1)))[0]
    if layer is None:
        layer = int(ks[0] + 0.62 * (ks[-1] - ks[0]))
    tk = spec_l.tank
    eit = EIT(es, tk.inner_mm[0], tk.fill_mm)
    es = eit.es
    layer_s = float(plan["layer_s"][layer]) if plan["layer_s"][layer] > 0 else float(np.mean(plan["layer_s"][plan["layer_s"] > 0]))
    n_avg = max(1, int(layer_s / (eit.mask.sum() * es.meas_ms * 1e-3)))
    rows, figs, base = _evaluate(eit, piece, layer, spec_l, n_avg)
    cur = base.fw.electrode_currents(base.u) * base.current_a
    res = {
        "layer": layer, "place": es.place, "n_electrodes": len(eit.ring), "n_rings": int(eit.ring.max()) + 1, "n_drives": len(eit.pairs),
        "n_meas": int(eit.mask.sum()), "protocol": es.protocol, "grid": list(eit.grid.shape), "n_cells": eit.grid.n, "roi_cells": len(eit.roi),
        "current_ua": base.current_a * 1e6, "drive_mv": base.drive_v * 1e3,
        "meas_mv_max": float(np.max(np.abs(base.v)) * 1e3), "meas_uv_min": float(np.min(np.abs(base.v)) * 1e6),
        "contact_ohm": [float(base.fw.zc.min()), float(base.fw.zc.max())], "current_sum_a": float(np.abs(cur.sum(axis=0)).max()),
        "electrode_z_mm": sorted({round(p[2], 1) for p in eit.pos}), "bed_top_mm": _scenarios(eit, piece, layer, spec_l)[0]["a"].dz,
        "layer_s": layer_s, "n_avg": n_avg, "scenarios": rows,
    }
    if compare:
        res["compare"] = {es.place: rows}
        for place in PLACES:
            if place == es.place:
                continue
            extra = {"rings_z_mm": (300.0, 265.0)} if place == "walls" else {}
            other = EIT(replace(es, place=place, **extra), tk.inner_mm[0], tk.fill_mm)
            n_o = max(1, int(layer_s / (other.mask.sum() * es.meas_ms * 1e-3)))
            res["compare"][place] = _evaluate(other, piece, layer, spec_l, n_o)[0]
    res["seconds"] = time.time() - t0
    res["text"] = describe(res, es)
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        res["figure"] = str(_figure(eit, figs, piece, layer, out_dir / "eit.png"))
    return res


def describe(r: dict, es: EITSpec) -> str:
    lines = [f"[EIT — 배지 속을 전기로 봄] 층 {r['layer']} 순간 (받침 윗면 z {r['bed_top_mm']:.1f} mm)",
             f"  전극: {es.rod}",
             f"    {PLACES[es.place]} · {r['n_rings']}줄 × 16 = {r['n_electrodes']}개 · 높이 {', '.join(f'{z:g}' for z in r['electrode_z_mm'])} mm · "
             f"접지 = 배지 전도도 전극 자리",
             f"    도구 갠트리(빔 · 캐리지 z 283–316) 와 겹치지 않음 — EIT 는 갠트리가 주차했을 때만 잼 (빔 · 레일은 절연체로 넣음)"
             if es.place in ("collar_bed", "collar_riser") else
             f"    {'⚠ 소매는 도구 갠트리 쓸림(z 283–316) 과 겹침 — 도구 단계 전에 소매를 들어 올려야 함' if es.place == 'sleeve' else '수조 벽 — 몸에서 약 15 cm'}",
             f"  교류 {es.freq_hz / 1000:g} kHz · 전류 {r['current_ua']:.0f} µA · 구동 쌍 {r['drive_mv']:.0f} mV (상한 {es.v_cap_mv:g} mV, 탄소 안전창 800 mV) · "
             f"잰 전압 {r['meas_uv_min']:.1f} µV ~ {r['meas_mv_max']:.1f} mV",
             f"    직류 평균 0 → 누설 감시(직류 50 µA)와 주파수로 갈림 · 접촉 임피던스 {r['contact_ohm'][0]:.0f}–{r['contact_ohm'][1]:.0f} Ω "
             f"(이중층 {es.c_dl_f_m2 * 100:g} µF/cm², 가정)",
             f"  {'이웃 쌍' if r['protocol'] == 'adjacent' else '이웃 · 위아래 · 4칸 건너 쌍'} 구동 {r['n_drives']} × 같은 쌍 측정 → {r['n_meas']}개 값 · 칸 {r['grid'][0]}×{r['grid'][1]}×{r['grid'][2]} = {r['n_cells']} "
             f"(가운데 {es.fine_mm:g} mm) · 되찾는 칸 {r['roi_cells']} · 계산 {r['seconds']:.0f} s",
             f"  잡음: 한 장 {es.noise_rel * 100:g} % (가정) · 이 층 {r['layer_s'] / 60:.1f} 분 동안 {r['n_avg']}장 평균 → ÷{math.sqrt(r['n_avg']):.0f}"]
    for s in r["scenarios"]:
        det = "검출" if s["snr"] >= 3 else "검출 어려움"
        line = (f"  · {s['name']}: 신호/잡음 {s['snr']:.1f} ({det}; 한 장이면 {s['snr1']:.2f}) · 최대 전압 차 {s['max_dv_uv']:.2f} µV · "
                f"참값과 상관 {s['corr']:.2f}")
        if "err_mm" in s:
            line += f" · 위치 오차 {s['err_mm']:.0f} mm · 반값 부피 {s['vol_ml']:.1f} mL (참 {s['truth_vol_ml']:.1f})"
            line += (f"\n      {es.integrate_layers}층 동안 평균하면 신호/잡음 {s['snr_k']:.1f} · 신호/잡음 3 이 되는 지름: 한 층 {s['d_min_mm']:.0f} mm · "
                     f"{es.integrate_layers}층 {s['d_min_k_mm']:.0f} mm (어림, 신호 ∝ 부피)")
        lines.append(line)
    if "compare" in r:
        lines.append("  전극 자리 비교 — 한 층 신호/잡음 · 위치 오차 (덧굳음 · 빠진 곳 지름 12 mm, 자람 10층):")
        for place, rows in r["compare"].items():
            b, m, g = rows
            lines.append(f"    {place:<13} 덧굳음 {b['snr']:4.1f} · {b['err_mm']:3.0f} mm | 빠진 곳 {m['snr']:4.2f} · {m['err_mm']:3.0f} mm | "
                         f"자람 {g['snr']:5.0f} | 덧굳음 지름 하한 {b['d_min_mm']:.0f} mm ({es.integrate_layers}층 {b['d_min_k_mm']:.0f} mm)")
    lines.append("  (데스크톱은 설계로 기대 전압을 계산해 두고, 잰 값과의 차이로 어디가 설계와 다른지 그림으로 되찾음 — 해상도는 cm 급)")
    return "\n".join(lines)


def _figure(eit: EIT, figs, piece, layer, path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .drawing import setup_fonts

    setup_fonts()
    xc, yc, zc = eit.grid.centers()
    fig, axs = plt.subplots(2, len(figs) + 1, figsize=(4.2 * (len(figs) + 1), 7.6), dpi=100)
    ax = axs[0, 0]
    t = eit.tank_mm / 2
    ax.add_patch(plt.Rectangle((-t, -t), 2 * t, 2 * t, fill=False, color="#5d6673"))
    for (x, y, z), r in zip(eit.pos, eit.ring):
        ax.plot(x, y, "o", ms=5 if r == 0 else 3, color="#23a06b" if r == 0 else "#1d5fa8")
    foot = piece.material.any(axis=2)
    ii, jj = np.nonzero(foot)
    ax.plot((piece.offset[0] + ii) * piece.pitch[0], (piece.offset[1] + jj) * piece.pitch[0], ",", color="#e0344b")
    ax.set_aspect("equal")
    ax.set_title("위에서: 전극 두 줄 · 존재 발자국", fontsize=9)
    axs[1, 0].axis("off")
    axs[1, 0].text(0, 0.5, "위: 참 Δσ (y 단면)\n아래: 되찾은 Δσ\n(빨강 +, 파랑 −)", fontsize=10)
    for c, (s, tru, img) in enumerate(figs, start=1):
        cy = s["center"][1] if s["center"] is not None else 0.0
        j = int(np.clip(np.searchsorted(eit.grid.ey, cy) - 1, 0, eit.grid.shape[1] - 1))
        for rI, (data, lab) in enumerate(((tru, "참"), (img, "되찾음"))):
            a = axs[rI, c]
            sl = data[:, j, :].T
            m = float(np.abs(sl).max()) or 1.0
            a.pcolormesh(eit.grid.ex, eit.grid.ez, sl, cmap="RdBu_r", vmin=-m, vmax=m, shading="flat")
            a.set_xlim(-110, 110)
            a.set_ylim(170, 335)
            a.axhline(eit.fill_mm, color="#555", lw=0.8)
            for z in eit.es.rings_z_mm:
                a.axhline(z, color="#23a06b", lw=0.6, ls=":")
            if s["center"] is not None:
                a.plot(s["center"][0], s["center"][2], "+", color="k", ms=10)
            a.set_title(f"{lab}: {s['name']}", fontsize=8)
            a.set_xlabel("x mm", fontsize=8)
            a.set_ylabel("z mm", fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
