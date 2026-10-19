"""보로노이 + 프랙탈 도메인 네트워크 — 결정 단면의 세포형 구조와 그 전기적 결과.

결정화 = 결정핵(씨앗)에서 같은 속도로 자라 만나는 곳이 벽 → 결정핵의 보로노이 분할 (Johnson–Mehl).

프랙탈 요소
    1. 층 경계(묽은/진한 도메인층 사이)가 Weierstrass–Mandelbrot 프랙탈 곡선 (차원 D_i, 1 = 평평)
       — 그래핀 액정 정렬이 흐트러질수록 경계가 거칠어짐
    2. 결정핵 분포가 Soneira–Peebles 프랙탈 점집합 (차원 D_s, 2 = 고른 분포, 낮을수록 뭉침)
       — 크고 작은 도메인이 섞인 다중 스케일 보로노이

전기 네트워크 (2D 단면, 깊이 1 mm 당)
    노드 = 보로노이 도메인, 간선 = 도메인 벽 (막 저항 + 양쪽 도메인 내부 저항, 막전위 기전력)
    - 층 번호 차이 ±1 벽: 이온 선택막, 막전위 ±E (아래 층이 짝수면 CEM, 홀수면 AEM)
    - 같은 층 벽: 막전위 0 (같은 농도), 저항만
    - 층 번호 차이 ≥2 벽: 결함 — 선택성 없음, 층을 건너뛰는 단락 경로
    → 개방전압·테브난 저항·개방 상태의 내부 순환 손실을 풀어 실제 소자 크기로 환산.

numpy, scipy 필요.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from scipy.spatial import Voronoi

from .constants import thermal_voltage
from .electrolyte import nacl_conductivity
from .specrng import SpecRNG, round_half_up


@dataclass
class FractalVoronoiParams:
    interface_dimension: float = 1.25  # 층 경계 프랙탈 차원 D_i (1 ≤ D_i < 2)
    roughness: float = 0.35  # 층 경계 RMS 진폭 / 층 두께
    correlation: float = 0.85  # 이웃 층 경계가 같은 모양으로 휘는 정도 (1 = 완전히 나란함, 0 = 제각각)
    seed_dimension: float = 2.0  # 결정핵 분포 프랙탈 차원 D_s (1 < D_s ≤ 2)
    grains_per_layer: float = 3.0  # 층 두께 안에 들어가는 평균 결정핵 수 (세로)
    window_layers: int = 40  # 계산 창의 층 수 (결과는 전체 층 수로 환산)
    window_width_mm: float = 8.0
    seed: int = 1

    def __post_init__(self) -> None:
        if not 1.0 <= self.interface_dimension < 2.0:
            raise ValueError("층 경계 프랙탈 차원은 1 이상 2 미만이어야 합니다.")
        if not 1.0 < self.seed_dimension <= 2.0:
            raise ValueError("결정핵 분포 프랙탈 차원은 1 초과 2 이하여야 합니다.")
        if self.roughness < 0 or self.grains_per_layer <= 0 or self.window_width_mm <= 0:
            raise ValueError("거칠기·결정핵 밀도·창 폭은 양수여야 합니다.")
        if not 0.0 <= self.correlation <= 1.0:
            raise ValueError("층 경계 상관도는 0~1 이어야 합니다.")
        if self.window_layers < 4:
            raise ValueError("계산 창은 4층 이상이어야 합니다.")


@dataclass
class VoronoiNetworkResult:
    params: FractalVoronoiParams
    layer_mm: float
    n_layers_total: int
    # 장치 환산값
    ocv_v: float
    ocv_flat_v: float  # 같은 조건, 평평한 층 (D=1, 거칠기 0)
    resistance_ohm: float
    leak_current_ma: float  # 개방 상태에서 결함 경로로 도는 내부 전류 (자가방전)
    # 구조 지표
    n_cells: int
    mean_neighbors: float
    area_cv: float  # 도메인 면적 변동계수
    interface_roughness: float  # 실제 이온선택막 길이 / 평평한 경계 길이
    defect_fraction: float  # 결함 벽 길이 / 층간 벽 길이
    fractal_dim_interfaces: float  # 박스 카운팅 실측 (층간 벽)
    fractal_dim_walls: float  # 박스 카운팅 실측 (모든 벽)
    # 그림용
    seeds: np.ndarray = field(repr=False, default=None)
    layers: np.ndarray = field(repr=False, default=None)
    polygons: list = field(repr=False, default_factory=list)
    segments: dict = field(repr=False, default_factory=dict)
    box_counts: dict = field(repr=False, default_factory=dict)
    neighbor_hist: dict = field(repr=False, default_factory=dict)
    areas: np.ndarray = field(repr=False, default=None)
    window: tuple = (0.0, 0.0)
    raw: dict = field(repr=False, default_factory=dict)  # 창 단위 원시값 (교차 검증용)

    @property
    def efficiency(self) -> float:
        return self.ocv_v / self.ocv_flat_v if self.ocv_flat_v else 0.0

    @property
    def max_power_mw(self) -> float:
        return self.ocv_v ** 2 / (4 * self.resistance_ohm) * 1000

    def describe(self) -> str:
        p = self.params
        return "\n".join([
            f"보로노이·프랙탈 네트워크: 층 경계 D_i={p.interface_dimension:.2f} (거칠기 {p.roughness:.2f}t, "
            f"상관도 {p.correlation:.2f}), "
            f"결정핵 D_s={p.seed_dimension:.2f}",
            f"  도메인 {self.n_cells}개/창, 평균 이웃 {self.mean_neighbors:.2f}, 면적 변동계수 {self.area_cv:.2f}",
            f"  실측 프랙탈 차원: 층간 벽 {self.fractal_dim_interfaces:.2f}, 전체 벽 {self.fractal_dim_walls:.2f}",
            f"  막 길이 증가 ×{self.interface_roughness:.2f}, 결함 벽 {self.defect_fraction * 100:.1f} %",
            f"  개방전압 {self.ocv_v:.2f} V (평평한 층 {self.ocv_flat_v:.2f} V의 {self.efficiency * 100:.0f} %), "
            f"내부저항 {self.resistance_ohm:.0f} Ω, 최대전력 {self.max_power_mw:.0f} mW, "
            f"내부 누설 {self.leak_current_ma:.3f} mA",
        ])


# ---------- 결정핵 (씨앗) ----------
def _seeds(p: FractalVoronoiParams, width: float, height: float, spacing: float, rng) -> np.ndarray:
    if p.seed_dimension >= 1.999:  # 고른 분포: 흔들린 격자 (최소 거리가 있는 결정핵)
        nx, nz = max(2, round_half_up(width / spacing)), max(2, round_half_up(height / spacing))
        gx, gz = np.meshgrid((np.arange(nx) + 0.5) * width / nx, (np.arange(nz) + 0.5) * height / nz)
        pts = np.column_stack([gx.ravel(), gz.ravel()])
        pts += rng.uniform(-0.42, 0.42, pts.shape) * [width / nx, height / nz]
        return pts
    # Soneira–Peebles: 각 단계에서 크기를 절반으로 줄이며 평균 2^D_s 개의 자식 결정핵
    levels = 4
    m = 2 ** p.seed_dimension
    s0 = spacing * 2 ** levels
    n0 = max(1, round_half_up(width * height / s0 ** 2))
    pts = rng.uniform(0, 1, (n0, 2)) * [width, height]
    half = s0 / 2
    for _ in range(levels):
        counts = rng.poisson(m, len(pts))
        counts[counts == 0] = 1
        parents = np.repeat(pts, counts, axis=0)
        pts = parents + rng.uniform(-half, half, parents.shape)
        half /= 2
    pts[:, 0] = np.mod(pts[:, 0], width)
    z = np.abs(pts[:, 1])  # 위·아래 경계에서 반사 (경계에 결정핵이 몰려 생기는 가짜 도메인 방지)
    z = np.where(z > height, 2 * height - z, z)
    pts[:, 1] = np.clip(z, height * 1e-4, height * (1 - 1e-4))
    _, keep = np.unique(np.floor(pts / (spacing * 1e-3) + 0.5), axis=0, return_index=True)
    return pts[np.sort(keep)]


# ---------- 프랙탈 층 경계 ----------
def _interfaces(p: FractalVoronoiParams, width: float, t: float, n: int, rng):
    gamma, lam0 = 1.7, width
    terms = max(4, int(math.log(lam0 / (t / p.grains_per_layer / 2)) / math.log(gamma)) + 1)
    k = np.arange(terms)
    amp = gamma ** ((p.interface_dimension - 2) * k)
    norm = math.sqrt(float(np.sum(amp ** 2)) / 2)
    phases = rng.uniform(0, 2 * math.pi, (n, terms))
    common = rng.uniform(0, 2 * math.pi, terms)  # 모든 층이 공유하는 굴곡 (액정 층의 나란한 휨)
    freq = 2 * math.pi * gamma ** k / lam0
    wc, wi = math.sqrt(p.correlation), math.sqrt(1 - p.correlation)

    def heights(x: np.ndarray) -> np.ndarray:
        """각 경계 k(행)에서 x(열)의 높이."""
        base = (np.arange(1, n + 1) * t)[:, None]
        if p.roughness == 0:
            return np.broadcast_to(base, (n, len(x)))
        w_own = np.einsum("t,ntx->nx", amp, np.cos(freq[None, :, None] * x[None, None, :] + phases[:, :, None]))
        w_com = np.einsum("t,tx->x", amp, np.cos(freq[:, None] * x[None, :] + common[:, None]))
        return base + p.roughness * t * (wc * w_com[None, :] + wi * w_own) / norm

    return heights


# ---------- 보로노이 + 네트워크 ----------
def analyze(stack, layer_mm: float, n_layers_total: int, area_mm2: float,
            params: FractalVoronoiParams | None = None, keep_geometry: bool = True) -> VoronoiNetworkResult:
    """stack: ArtificialCellStack (막·농도·온도), layer_mm: 층 두께, area_mm2: 소자 단면적."""
    p = params or FractalVoronoiParams()
    rng = SpecRNG(p.seed)  # 명세 난수: Rust·C# 구현과 같은 구조를 만든다
    t, W = layer_mm, p.window_width_mm
    Nw = p.window_layers
    H = Nw * t
    pts = _seeds(p, W, H, t / p.grains_per_layer, rng)
    n = len(pts)

    # 층 번호: 결정핵이 몇 개의 프랙탈 경계보다 위에 있는가
    heights = _interfaces(p, W, t, Nw - 1, rng)
    layer = np.sum(pts[:, 1][None, :] > heights(pts[:, 0]), axis=0).astype(int)

    # 거울상으로 창 안에 갇힌 보로노이
    mirrors = [pts * [1, -1], pts * [1, -1] + [0, 2 * H], pts * [-1, 1], pts * [-1, 1] + [2 * W, 0]]
    vor = Voronoi(np.vstack([pts] + mirrors))
    V = vor.vertices
    rp = vor.ridge_points
    rv = np.array([r if -1 not in r else [0, 0] for r in vor.ridge_vertices])
    valid = np.array([-1 not in r for r in vor.ridge_vertices])
    i, j = rp[:, 0], rp[:, 1]
    lengths = np.where(valid, np.linalg.norm(V[rv[:, 0]] - V[rv[:, 1]], axis=1), 0.0)

    vt = thermal_voltage(stack.saline.temperature_c)
    ratio = math.log(stack.c_concentrated / stack.c_dilute) if stack.x > 0 else 0.0
    a_c, a_a = stack.cem.selectivity_at(stack.c0), stack.aem.selectivity_at(stack.c0)
    e_cem, e_aem = a_c * vt * ratio, a_a * vt * ratio
    r_c = stack.cem.area_resistance_ohm_cm2 * 100  # Ω·mm²
    r_a = stack.aem.area_resistance_ohm_cm2 * 100
    sig = np.where(layer % 2 == 0, nacl_conductivity(stack.c_dilute, stack.saline.temperature_c),
                   nacl_conductivity(stack.c_concentrated, stack.saline.temperature_c)) / 1000  # S/mm

    # 도메인 사이 벽
    inner = valid & (i < n) & (j < n) & (lengths > 1e-9)
    ii, jj, L = i[inner], j[inner], lengths[inner]
    d = np.linalg.norm(pts[ii] - pts[jj], axis=1)
    dl = layer[jj] - layer[ii]
    lower = np.minimum(layer[ii], layer[jj])
    is_c = lower % 2 == 0
    active = np.abs(dl) == 1
    r_wall = np.where(active, np.where(is_c, r_c, r_a), (r_c + r_a) / 2)
    R = r_wall / L + d / 2 / (sig[ii] * L) + d / 2 / (sig[jj] * L)
    G = 1 / R
    emf = np.where(active, np.sign(dl) * np.where(is_c, e_cem, e_aem), 0.0)  # i→j 전위 상승

    # 전극 접촉 (아래 = 0 V 고정, 위 = 노드 n)
    contacts = []
    for block, node in ((1, None), (2, n)):  # 거울 블록 1: 아래, 2: 위
        lo, hi = block * n, (block + 1) * n
        sel = valid & (((i < n) & (j >= lo) & (j < hi)) | ((j < n) & (i >= lo) & (i < hi)))
        cells = np.where(i[sel] < n, i[sel], j[sel])
        Lc = lengths[sel]
        dist = np.abs(pts[cells, 1] - (0 if block == 1 else H))
        Gc = 1 / (np.maximum(dist, 1e-3) / (sig[cells] * np.maximum(Lc, 1e-9)) + 1e-3)
        contacts.append((cells, Gc, node))

    def solve(with_emf: bool, inject_top: float):
        N = n + 1
        rows, cols, vals = [], [], []
        b = np.zeros(N)

        def add(a, c, g):
            rows.extend([a, c, a, c])
            cols.extend([a, c, c, a])
            vals.extend([g, g, -g, -g])

        rows += list(ii) + list(jj) + list(ii) + list(jj)
        cols += list(ii) + list(jj) + list(jj) + list(ii)
        vals += list(G) + list(G) + list(-G) + list(-G)
        if with_emf:
            np.add.at(b, ii, -G * emf)
            np.add.at(b, jj, G * emf)
        bot_cells, bot_g, _ = contacts[0]
        rows += list(bot_cells)
        cols += list(bot_cells)
        vals += list(bot_g)
        top_cells, top_g, _ = contacts[1]
        for c, g in zip(top_cells, top_g):
            add(int(c), n, float(g))
        b[n] += inject_top
        A = coo_matrix((vals, (rows, cols)), shape=(N, N)).tocsr()
        return spsolve(A, b)

    phi = solve(True, 0.0)
    v_oc_win = float(phi[n])
    r_win = float(solve(False, 1.0)[n])
    flow = G * (phi[ii] + emf - phi[jj])
    p_loss_win = float(np.sum(flow ** 2 / G))

    scale_n = n_layers_total / Nw  # 저항·손실: 층 수 비율
    scale_v = n_layers_total / (Nw - 1)  # 전압: 막(층 경계) 수 비율 — 창 안 경계는 Nw-1 개, 소자는 층마다 1개
    depth_scale = (W * 1.0) / area_mm2
    ocv = v_oc_win * scale_v
    res = r_win * scale_n * depth_scale
    p_dev = p_loss_win * scale_n / depth_scale
    leak = p_dev / ocv * 1000 if ocv > 0 else 0.0

    # 평평한 기준 (같은 결정핵, 경계 평평)
    if p.roughness > 0 or p.interface_dimension > 1:
        flat = analyze(stack, layer_mm, n_layers_total, area_mm2,
                       FractalVoronoiParams(1.0, 0.0, p.correlation, p.seed_dimension, p.grains_per_layer,
                                            p.window_layers, p.window_width_mm, p.seed), keep_geometry=False)
        ocv_flat = flat.ocv_v
    else:
        ocv_flat = ocv

    # 구조 지표
    nb = np.bincount(np.concatenate([ii, jj]), minlength=n)
    interior = (pts[:, 0] > 2 * t) & (pts[:, 0] < W - 2 * t) & (pts[:, 1] > 2 * t) & (pts[:, 1] < H - 2 * t)
    mean_nb = float(nb[interior].mean()) if interior.any() else float(nb.mean())
    polys, areas = [], np.zeros(n)
    for c in range(n):
        reg = vor.regions[vor.point_region[c]]
        if not reg or -1 in reg:
            continue
        poly = V[reg]
        x, z = poly[:, 0], poly[:, 1]
        areas[c] = 0.5 * abs(np.dot(x, np.roll(z, 1)) - np.dot(z, np.roll(x, 1)))
        if keep_geometry:
            polys.append(poly)
    area_cv = float(areas[areas > 0].std() / areas[areas > 0].mean())
    interlayer = dl != 0
    flat_len = (Nw - 1) * W
    rough = float(L[active].sum() / flat_len) if flat_len else 1.0
    defect = float(L[np.abs(dl) >= 2].sum() / max(L[interlayer].sum(), 1e-9))

    seg = {}
    if keep_geometry:
        sv = rv[inner]
        a_pts, b_pts = V[sv[:, 0]], V[sv[:, 1]]
        for name, mask in (("same", dl == 0), ("cem", active & is_c), ("aem", active & ~is_c),
                           ("defect", np.abs(dl) >= 2)):
            seg[name] = np.stack([a_pts[mask], b_pts[mask]], axis=1)
    else:
        sv = rv[inner]
        a_pts, b_pts = V[sv[:, 0]], V[sv[:, 1]]
    # 층 경계 하나씩 따로 측정해 평균 (여러 경계를 한꺼번에 세면 평면을 채워 2에 가까워짐)
    fine = t / p.grains_per_layer
    dims, box_if = [], None
    for kk in range(Nw // 4, 3 * Nw // 4, max(1, Nw // 8)):
        m = active & (lower == kk)
        if m.sum() < 8:
            continue
        bc = box_counting(np.stack([a_pts[m], b_pts[m]], axis=1), W, W, fine, top=W / 2)
        dims.append(bc["dimension"])
        box_if = box_if or bc
    box_if = box_if or {"eps": [], "counts": [], "dimension": float("nan")}
    box_if = {**box_if, "dimension": float(np.nanmean(dims)) if dims else float("nan")}
    box_all = box_counting(np.stack([a_pts, b_pts], axis=1), W, H, fine)

    hist = {int(k): int(v) for k, v in zip(*np.unique(nb[interior], return_counts=True))} if interior.any() else {}
    raw = {"n_cells": n, "n_inner_ridges": int(inner.sum()), "v_oc_window": v_oc_win, "r_window": r_win,
           "p_loss_window": p_loss_win, "active_length": float(L[active].sum()),
           "defect_length": float(L[np.abs(dl) >= 2].sum()), "mean_neighbors": mean_nb,
           "box_dim_walls": box_all["dimension"]}
    return VoronoiNetworkResult(
        raw=raw,
        params=p, layer_mm=t, n_layers_total=n_layers_total,
        ocv_v=ocv, ocv_flat_v=ocv_flat, resistance_ohm=res, leak_current_ma=leak,
        n_cells=n, mean_neighbors=mean_nb, area_cv=area_cv, interface_roughness=rough,
        defect_fraction=defect, fractal_dim_interfaces=box_if["dimension"], fractal_dim_walls=box_all["dimension"],
        seeds=pts if keep_geometry else None, layers=layer if keep_geometry else None,
        polygons=polys, segments=seg, box_counts={"interfaces": box_if, "walls": box_all},
        neighbor_hist=hist, areas=areas[areas > 0] if keep_geometry else None, window=(W, H),
    )


def box_counting(segments: np.ndarray, width: float, height: float, fine: float, top: float | None = None) -> dict:
    """선분 집합의 박스 카운팅 차원. 크기 ε 를 창 크기 ~ 결정핵 간격 사이에서 바꿔 가며 센다."""
    if len(segments) == 0:
        return {"eps": [], "counts": [], "dimension": float("nan")}
    a, b = segments[:, 0], segments[:, 1]
    seg_len = np.linalg.norm(b - a, axis=1)
    big = top or max(width, height) / 2
    eps_list = []
    e = big
    while e >= fine * 1.5:
        eps_list.append(e)
        e /= 1.6
    counts = []
    for eps in eps_list:
        k = np.maximum(1, np.ceil(seg_len / (eps / 2))).astype(int)
        idx = np.repeat(np.arange(len(a)), k)
        frac = (np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)) / np.repeat(k, k)
        pts = a[idx] + (b[idx] - a[idx]) * frac[:, None]
        cells = np.unique(np.floor(pts / eps).astype(np.int64), axis=0)
        counts.append(len(cells))
    x = np.log(1 / np.array(eps_list))
    y = np.log(np.array(counts))
    dim = float(np.polyfit(x, y, 1)[0]) if len(x) >= 2 else float("nan")
    return {"eps": eps_list, "counts": counts, "dimension": dim}


def sweep_interface_dimension(stack, layer_mm, n_layers_total, area_mm2, base: FractalVoronoiParams | None = None,
                              dims=(1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8)) -> list[VoronoiNetworkResult]:
    base = base or FractalVoronoiParams()
    out = []
    for D in dims:
        prm = FractalVoronoiParams(D, base.roughness if D > 1 else 0.0, base.correlation, base.seed_dimension,
                                   base.grains_per_layer, base.window_layers, base.window_width_mm, base.seed)
        out.append(analyze(stack, layer_mm, n_layers_total, area_mm2, prm, keep_geometry=False))
    return out


def sweep_roughness(stack, layer_mm, n_layers_total, area_mm2, base: FractalVoronoiParams | None = None,
                    values=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0)) -> list[VoronoiNetworkResult]:
    base = base or FractalVoronoiParams()
    return [analyze(stack, layer_mm, n_layers_total, area_mm2,
                    FractalVoronoiParams(base.interface_dimension, r, base.correlation, base.seed_dimension,
                                         base.grains_per_layer, base.window_layers, base.window_width_mm, base.seed),
                    keep_geometry=False) for r in values]


def analyze_battery(battery, params: FractalVoronoiParams | None = None, keep_geometry: bool = True):
    """BottleGelBattery 에 바로 적용."""
    s = battery.stack
    return analyze(s, battery.formation.layer_thickness_mm, 2 * s.n_pairs, battery.gel_area_cm2 * 100,
                   params, keep_geometry)
