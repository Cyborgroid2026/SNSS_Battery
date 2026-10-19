"""인공세포 조직 — 식염수병 안 식염수에서 바로 생기는 결정을 '비어 있지만 에너지가 담긴 인공세포'의 3차원 조직으로 본 구조 모델.

층(띠)도, 세포 극성도 없다. 모든 세포는 같은 종류이고, 막은 모두 같은 GO/PVA 벽이다.

어떻게 생기나 (병 하나에서)
  1. 병에 생리식염수 + GO + PVA 를 섞어 둔다.
  2. 병을 차가운 금속판 위에 세워(옆면 단열) 아래에서 위로 천천히 얼린다 (방향성 동결).
     얼음 결정 하나하나가 세포의 틀이 되고, GO·PVA 는 얼음에서 밀려나 결정 경계에 모여 막이 된다 (얼음 주형).
  3. 소금은 얼음에 거의 들어가지 못한다 (분배 계수 k_eff ≪ 1). 그래서 녹은 뒤 세포 안(내강)은 묽고,
     밀려난 소금은 결정 경계의 막 사이에 진한 소금물로 모인다 (바다 얼음의 염수 통로와 같은 현상).
  4. 녹이면 얼음 자리가 묽은 식염수 내강이 되고, PVA 미세결정이 막을 붙잡는다.
     → 빈 인공세포: 안에 생물학·공학 요소는 없고, 내강–막 사이 소금물의 농도차로 에너지만 담김.

프랙탈 · 보로노이 연속성 (2D 탭과 같은 생성 규칙)
  - 결정핵: 2D 모델과 같은 규칙 (흔들린 격자 또는 Soneira–Peebles 뭉침, 차원 D_s + 1), 간격 = 세포 크기
  - 동결 전선: Weierstrass–Mandelbrot 프랙탈 곡면 (2D 경계와 같은 진폭 법칙 γ^((D−2)k), 같은 8 mm 장)
    — 성분 띠가 아니라 얼음이 지나간 '시각'의 모양. 세포마다 얼 때의 전선 속도 → 내강에 남는 소금.
  - 보로노이 원소가 그대로 구조: 세포(3D) = 내강, 면(2D) = 막 사이 소금물 막, 모서리(1D) = 소금물 통로

전기 (정직한 결과)
  - 회로망: 내강 노드 + 소금물 막 노드, 막(내강↔소금물)마다 확산 전위, 통로(소금물↔소금물)는 저항만.
  - 극성·층이 없어 막전위가 사방으로 상쇄 → 윗면–아랫면 전압은 거의 0. 남는 것은 동결 속도 차이로 생긴
    완만한 기울기 전압뿐. 에너지는 세포 안에 '잠겨' 있고, 꺼내려면 이후의 공학 요소(채널·전극 연결)가 필요.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .constants import GAS_CONSTANT, celsius_to_kelvin, thermal_voltage
from .electrolyte import nacl_conductivity

SALINE_M = 0.1545
EUTECTIC_M = 5.2  # NaCl–물 공정점 (23.3 wt%, −21.1 °C) — 소금물이 더 진해질 수 없음
WALL_ALPHA = 0.30  # GO(−)·PVA 벽의 순 양이온 선택도 (극성 없음, 모든 벽 같음)
WALL_ASR = 5.0  # 벽 면저항 Ω·cm²
D_SALT = 1.5e-9  # 물속 NaCl 확산계수 m²/s
K0 = 0.01  # 평형 분배 계수 (얼음/물)
BL_UM = 100.0  # 동결 전선 앞 확산 경계층 두께 µm


def k_eff(v_m_s: float) -> float:
    """Burton–Prim–Slichter 유효 분배 계수: 전선이 빠를수록 얼음(→ 내강)에 소금이 더 갇힘."""
    x = v_m_s * BL_UM * 1e-6 / D_SALT
    return K0 / (K0 + (1 - K0) * math.exp(-x))


@dataclass
class TissueParams:
    """3차원 계산 창 (결정 가운데 높이). 결정핵·동결 전선은 2D 보로노이·프랙탈 모델(FractalVoronoiParams)의 규칙을 따른다."""

    window_mm: float = 1.34
    height_mm: float = 3.0
    cell_um: float = 167.0  # 세포 크기 = 결정핵 간격 (2D: 0.5 mm ÷ 3, 동결 추정 140–280 µm)
    film_um: float = 6.0  # 막 사이 소금물 막 두께
    vein_um: float = 4.0  # 소금물 통로(보로노이 모서리) 반지름
    plate_c: float = -20.0
    seed: int = 1

    def __post_init__(self) -> None:
        if min(self.window_mm, self.height_mm, self.cell_um, self.film_um, self.vein_um) <= 0:
            raise ValueError("크기 변수는 모두 양수여야 합니다.")


@dataclass
class Face:
    a: int
    b: int  # 이웃 세포 (경계면: -1 아래 / -2 위 / -3 옆)
    area_mm2: float
    poly: np.ndarray
    verts: tuple  # 보로노이 꼭짓점 번호 (통로 찾기용)

    @property
    def kind(self) -> str:
        return "wall" if self.b >= 0 else "boundary"


@dataclass
class Cell:
    idx: int
    seed: np.ndarray
    conc_m: float  # 내강 농도
    freeze_h: float  # 이 세포가 언 시각 (프랙탈 전선)
    v_um_s: float  # 그때 전선 속도
    volume_mm3: float = 0.0
    film_mm3: float = 0.0  # 둘레 소금물 막 몫
    energy_j: float = 0.0
    faces: list[int] = field(default_factory=list)


@dataclass
class TissueResult:
    params: TissueParams
    fractal: object
    cells: list[Cell]
    faces: list[Face]
    veins: list[tuple]  # (면 i, 면 j, 길이 mm)
    c_lumen: tuple  # (최소, 평균, 최대) M
    c_brine: float
    wall_mv: float  # 내강–소금물 막 하나의 확산 전위
    ocv_window_v: float
    r_window_ohm: float
    full: dict
    continuity: dict

    def describe(self) -> str:
        p, fp, f, c = self.params, self.fractal, self.full, self.continuity
        nw = sum(1 for x in self.faces if x.b >= 0)
        return "\n".join([
            f"인공세포 조직 (3D 보로노이 · 프랙탈 동결 전선, 층·극성 없음) — 계산 창 {p.window_mm:g}×{p.window_mm:g}×{p.height_mm:g} mm",
            f"  보로노이 원소: 세포 {len(self.cells)}개 (내강) · 막 {nw}장 (사이에 소금물 막 {p.film_um:g} µm) · 소금물 통로 {len(self.veins)}개 (모서리)",
            f"  2D 와 같은 규칙: 결정핵 간격 {p.cell_um:.0f} µm, 결정핵 D_s {fp.seed_dimension:g}, 동결 전선 D {fp.interface_dimension:g} "
            f"(측정 ≈ {c['d_front']:.2f}, 같은 {c['field_mm']:g} mm 장), 전선 굴곡 {c['front_um']:.0f} µm",
            f"  농도: 내강 {1000 * self.c_lumen[1]:.1f} mM (얼음이 녹은 자리, k_eff {c['k_eff']:.3f}) · 막 사이 소금물 {self.c_brine:.2f} M",
            f"  막 하나의 확산 전위 {self.wall_mv:.1f} mV — 세포마다 사방으로 같아 서로 상쇄",
            f"  저장 화학 에너지: 세포 하나 평균 {1e6 * c['e_cell_mean']:.1f} µJ · 병 전체 약 {f['energy_j']:.0f} J (잠겨 있음)",
            f"  윗면–아랫면 전압: 계산 창 {1e6 * self.ocv_window_v:+.1f} µV · 병 전체 약 {1000 * f['ocv_v']:+.2f} mV "
            f"(동결 기울기 몫) → 사실상 0 V, LED 불가",
            f"  병 전체: 인공세포 약 {f['n_cells'] / 1e6:.0f}백만 개, 내부저항 약 {f['r_ohm']:.0f} Ω",
            "  세포 안 생물학적·공학적 요소: 없음 — 에너지를 꺼내려면 이후 공학 요소(채널·전극 연결)가 필요",
        ])


# ---------- 생성 (2D 모델과 같은 규칙) ----------
def _seeds3(fp, W: float, H: float, spacing: float, rng) -> np.ndarray:
    if fp.seed_dimension >= 1.999:
        nx, nz = max(2, round(W / spacing)), max(2, round(H / spacing))
        g = np.stack(np.meshgrid((np.arange(nx) + 0.5) * W / nx, (np.arange(nx) + 0.5) * W / nx,
                                 (np.arange(nz) + 0.5) * H / nz, indexing="ij"), -1).reshape(-1, 3)
        return g + rng.uniform(-0.42, 0.42, g.shape) * [W / nx, W / nx, H / nz]
    levels, m = 4, 2 ** (fp.seed_dimension + 1)
    s0 = spacing * 2 ** levels
    pts = rng.uniform(0, 1, (max(1, round(W * W * H / s0 ** 3)), 3)) * [W, W, H]
    half = s0 / 2
    for _ in range(levels):
        c = rng.poisson(m, len(pts))
        c[c == 0] = 1
        pts = np.repeat(pts, c, axis=0) + rng.uniform(-half, half, (int(c.sum()), 3))
        half /= 2
    for ax, L in ((0, W), (1, W), (2, H)):
        q = np.abs(pts[:, ax])
        pts[:, ax] = np.clip(np.where(q > L, 2 * L - q, q), L * 1e-4, L * (1 - 1e-4))
    _, keep = np.unique(np.floor(pts / (spacing * 0.05)), axis=0, return_index=True)
    return pts[np.sort(keep)]


def _front(fp, L0: float, amp_mm: float, fine: float, rng):
    """프랙탈 동결 전선 모양 S(x, y) [mm] — 2D 경계와 같은 Weierstrass–Mandelbrot 생성 규칙 (방향이 다른 평면파)."""
    gamma = 1.7
    terms = max(4, int(math.log(L0 / (fine / 2)) / math.log(gamma)) + 1)
    k = np.arange(terms)
    a = gamma ** ((fp.interface_dimension - 2) * k)
    norm = math.sqrt(float(np.sum(a ** 2)) / 2)
    f = 2 * math.pi * gamma ** k / L0
    th, ph = rng.uniform(0, 2 * math.pi, terms), rng.uniform(0, 2 * math.pi, terms)

    def S(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        if fp.roughness == 0:
            return np.zeros_like(np.asarray(x, dtype=float))
        arg = f[:, None] * (np.asarray(x)[None] * np.cos(th)[:, None] + np.asarray(y)[None] * np.sin(th)[:, None]) + ph[:, None]
        return amp_mm * np.einsum("t,tm->m", a, np.cos(arg)) / norm

    return S


def _width_dimension(h: np.ndarray, dx: float, l_min: float, l_max: float) -> float:
    """거칠기 폭 방법: w(L) ∝ L^H, D = 2 − H."""
    ls = np.geomspace(l_min, l_max, 8)
    ws = []
    for L in ls:
        k = max(2, int(L / dx))
        m = len(h) // k
        ws.append(float(np.mean(h[: m * k].reshape(m, k).std(axis=1))))
    return 2 - float(np.polyfit(np.log(ls), np.log(ws), 1)[0])


def _order(poly: np.ndarray, normal: np.ndarray, idx: np.ndarray):
    c = poly.mean(axis=0)
    u = poly[0] - c
    u /= np.linalg.norm(u) or 1
    v = np.cross(normal, u)
    o = np.argsort(np.arctan2((poly - c) @ v, (poly - c) @ u))
    return poly[o], idx[o]


def _area(poly: np.ndarray) -> float:
    c = poly.mean(axis=0)
    s = np.zeros(3)
    for i in range(len(poly)):
        s += np.cross(poly[i] - c, poly[(i + 1) % len(poly)] - c)
    return 0.5 * float(np.linalg.norm(s))


# ---------- 방향성 동결 ----------
ICE_K = 2.2  # 얼음 열전도도 W/(m·K)
ICE_RHO_L = 917 * 334e3  # J/m³


def freezing(height_mm: float, plate_c: float = -20.0, melt_c: float = -0.6) -> dict:
    """스테판 문제 z(t) = sqrt(2kΔT t / ρL). 세포 폭은 전선 속도에 반비례 (얼음 주형 경향, 추정)."""
    dT = melt_c - plate_c
    z = height_mm / 1000
    t = z * z * ICE_RHO_L / (2 * ICE_K * dT)
    v_top, v_mid = z / (2 * t), (z / 2) / (2 * t / 4)
    cell = lambda v: min(600.0, max(20.0, 300.0 * (1e-6 / v)))
    return {"hours": t / 3600, "v_top_um_s": v_top * 1e6, "v_mid_um_s": v_mid * 1e6,
            "cell_top_um": cell(v_top), "cell_mid_um": cell(v_mid), "delta_t": dT}


def front_speed(z_mm: float, plate_c: float = -20.0, melt_c: float = -0.6) -> float:
    """높이 z 를 지날 때 전선 속도 [m/s] (스테판: v = kΔT / (ρL z))."""
    return ICE_K * (melt_c - plate_c) / (ICE_RHO_L * max(z_mm, 0.5) / 1000)


# ---------- 조직 ----------
def build_tissue(fp, p: TissueParams | None = None, total_height_mm: float | None = None,
                 area_mm2: float | None = None, temp_c: float = 25.0) -> TissueResult:
    from scipy.sparse import lil_matrix
    from scipy.sparse.linalg import spsolve
    from scipy.spatial import ConvexHull, Voronoi

    p = p or TissueParams()
    rng = np.random.default_rng(p.seed)
    W, H, sp = p.window_mm, p.height_mm, p.cell_um / 1000
    Htot = total_height_mm or 128.0
    z0 = Htot / 2 - H / 2  # 계산 창: 결정 가운데 높이
    pts = _seeds3(fp, W, H, sp, rng)
    n = len(pts)
    S = _front(fp, fp.window_width_mm, fp.roughness * 3 * sp, sp, rng)  # 전선 굴곡 = 거칠기 × 2D 층 두께(3 결정핵)

    mirrors = [pts]
    for ax, L in ((0, W), (1, W), (2, H)):
        for side in (0, L):
            q = pts.copy()
            q[:, ax] = 2 * side - q[:, ax]
            mirrors.append(q)
    allp = np.vstack(mirrors)
    vor = Voronoi(allp)

    # 세포마다: 언 시각(프랙탈 전선이 지나간 때) → 전선 속도 → 내강 농도
    cells = []
    fz = freezing(Htot, p.plate_c)
    t_tot = fz["hours"]
    for i in range(n):
        z_eff = z0 + pts[i, 2] - float(S(pts[i:i + 1, 0], pts[i:i + 1, 1])[0])  # 전선이 늦게 온 곳은 '더 높은' 셈
        v = front_speed(z_eff, p.plate_c)
        cells.append(Cell(i, pts[i], SALINE_M * k_eff(v), t_tot * (z_eff / Htot) ** 2, v * 1e6))
    for c in cells:
        c.volume_mm3 = float(ConvexHull(vor.vertices[vor.regions[vor.point_region[c.idx]]]).volume)

    faces: list[Face] = []
    for (i, j), rv in zip(vor.ridge_points, vor.ridge_vertices):
        if i >= n and j >= n:
            continue
        if i >= n:
            i, j = j, i
        idx = np.array(rv)
        normal = allp[j] - allp[i]
        normal /= np.linalg.norm(normal)
        poly, idx = _order(vor.vertices[idx], normal, idx)
        area = _area(poly)
        if area < 1e-9:
            continue
        b = j if j < n else (-1 if (j - n) // n == 4 else -2 if (j - n) // n == 5 else -3)
        faces.append(Face(i, b, area, poly, tuple(int(x) for x in idx)))
        cells[i].faces.append(len(faces) - 1)
        if b >= 0:
            cells[b].faces.append(len(faces) - 1)

    # 소금물 막 (막 사이) · 통로 (모서리를 공유하는 막끼리)
    film = p.film_um / 1000
    walls = [k for k, f in enumerate(faces) if f.b >= 0]
    v_film = sum(faces[k].area_mm2 * film for k in walls)
    v_lumen = sum(c.volume_mm3 for c in cells) - v_film
    salt_lumen = sum(c.conc_m * c.volume_mm3 for c in cells) * (v_lumen / (v_lumen + v_film))
    c_brine = min(EUTECTIC_M, (SALINE_M * (v_lumen + v_film) - salt_lumen) / v_film)
    for c in cells:
        c.film_mm3 = sum(0.5 * faces[k].area_mm2 * film for k in c.faces if faces[k].b >= 0)
    edge_faces: dict = {}
    for k in walls:
        vs = faces[k].verts
        for a_, b_ in zip(vs, vs[1:] + vs[:1]):
            edge_faces.setdefault((min(a_, b_), max(a_, b_)), []).append(k)
    veins = []
    for (a_, b_), fs in edge_faces.items():
        L = float(np.linalg.norm(vor.vertices[a_] - vor.vertices[b_]))
        for x in range(len(fs)):
            for y in range(x + 1, len(fs)):
                veins.append((fs[x], fs[y], L))

    # 에너지: 세포 내강 + 둘레 소금물 몫이 원래 0.9 % 로 섞일 때 나오는 자유에너지
    rt = GAS_CONSTANT * celsius_to_kelvin(temp_c)
    mix = lambda c, v_l: 2 * rt * v_l * 1e-6 * (c * math.log(c / SALINE_M) - c + SALINE_M) if c > 0 else 0.0
    for c in cells:
        c.energy_j = mix(c.conc_m, c.volume_mm3 - c.film_mm3) + mix(c_brine, c.film_mm3)

    # ---------- 회로망: 내강 0..n-1 · 소금물 막 n.. · 아래 단자 · 위 단자 ----------
    vt = thermal_voltage(temp_c)
    film_node = {k: n + q for q, k in enumerate(walls)}
    N = n + len(walls) + 2
    T0, T1 = N - 2, N - 1
    sig_b = nacl_conductivity(c_brine, temp_c)
    edges = []  # (u, v, G, e): 끊긴 상태에서 V_v − V_u = e
    c_mean_l = float(np.mean([c.conc_m for c in cells]))
    wall_e = WALL_ALPHA * vt * math.log(c_brine / c_mean_l)
    for k in walls:
        f = faces[k]
        cen = f.poly.mean(axis=0)
        A = f.area_mm2 * 1e-6
        for ci in (f.a, f.b):
            c = cells[ci]
            d = max(float(np.linalg.norm(cen - c.seed)) * 1e-3, 1e-6)
            r = d / (nacl_conductivity(c.conc_m, temp_c) * A) + WALL_ASR / (f.area_mm2 * 1e-2) + (film / 2) * 1e-3 / (sig_b * A)
            # 확산 전위: 묽은 내강 → 진한 소금물 쪽이 (양이온 선택 벽에서) 음 — 세포마다 같은 크기
            e = WALL_ALPHA * vt * math.log(c_brine / c.conc_m)
            edges.append((ci, film_node[k], 1 / r, -e))
    a_vein = math.pi * (p.vein_um * 1e-6) ** 2
    for fa, fb, L in veins:
        ca, cb = faces[fa].poly.mean(axis=0), faces[fb].poly.mean(axis=0)
        d = max(float(np.linalg.norm(ca - cb)), L / 2) * 1e-3
        edges.append((film_node[fa], film_node[fb], sig_b * a_vein / d, 0.0))
    for f in faces:
        if f.b in (-1, -2):  # 윗면·아랫면에 닿은 세포 → 흑연 막대 쪽 단자
            c = cells[f.a]
            d = max(float(np.linalg.norm(f.poly.mean(axis=0) - c.seed)) * 1e-3, 1e-6)
            g = nacl_conductivity(c.conc_m, temp_c) * f.area_mm2 * 1e-6 / d
            edges.append((T0, f.a, g, 0.0) if f.b == -1 else (f.a, T1, g, 0.0))

    def solve(with_emf: bool, inject: float) -> np.ndarray:
        G = lil_matrix((N, N))
        rhs = np.zeros(N)
        for u, v, g, e in edges:
            G[u, u] += g; G[v, v] += g; G[u, v] -= g; G[v, u] -= g
            if with_emf and e:
                rhs[u] -= g * e
                rhs[v] += g * e
        rhs[T1] += inject
        G[T0, :] = 0
        G[T0, T0] = 1
        rhs[T0] = 0
        return spsolve(G.tocsr(), rhs)

    ocv = float(solve(True, 0.0)[T1])
    r_win = float(solve(False, 1.0)[T1])

    # ---------- 연속성 측정 ----------
    L0 = fp.window_width_mm
    xs = np.linspace(0, L0, 2048, endpoint=False)
    hs = S(xs, np.full_like(xs, W / 2))
    lines = [S(xs, np.full_like(xs, y)) for y in np.linspace(0, L0, 8, endpoint=False)]  # 여러 단면의 평균
    cont = {"field_mm": L0, "d_set": fp.interface_dimension,
            "d_front": float(np.mean([_width_dimension(h, xs[1] - xs[0], 0.5, L0 / 3) for h in lines])) if fp.roughness > 0 else 1.0,
            "front_um": float(np.std(hs)) * 1000, "k_eff": float(np.mean([k_eff(c.v_um_s * 1e-6) for c in cells])),
            "e_cell_mean": float(np.mean([c.energy_j for c in cells])), "cell_um": p.cell_um,
            "x": xs[::8].tolist(), "front": hs[::8].tolist()}

    full = {}
    if total_height_mm and area_mm2:
        # 병 전체 기울기 전압: 맨 아래·맨 위 내강 농도 차이만큼 (극성이 없어 세포 수로 곱해지지 않음)
        c_bot = SALINE_M * k_eff(front_speed(1.0, p.plate_c))
        c_top = SALINE_M * k_eff(front_speed(Htot, p.plate_c))
        full["ocv_v"] = ocv * Htot / H  # 계산 창(가운데)의 기울기 전압을 높이만큼
        full["gradient_bound_v"] = WALL_ALPHA * vt * abs(math.log(c_bot / c_top))
        full["r_ohm"] = r_win * (Htot / H) * (W * W / area_mm2)
        full["n_cells"] = n / (W * W * H) * area_mm2 * Htot
        full["energy_j"] = sum(c.energy_j for c in cells) / (W * W * H) * area_mm2 * Htot
        full["c_bottom_mM"], full["c_top_mM"] = c_bot * 1000, c_top * 1000
    conc = [c.conc_m for c in cells]
    return TissueResult(p, fp, cells, faces, veins, (min(conc), float(np.mean(conc)), max(conc)), c_brine,
                        wall_e * 1000, ocv, r_win, full, cont)


def tissue_for(battery, p: TissueParams | None = None, fp=None) -> TissueResult:
    """병 결정의 인공세포 조직 — 프랙탈 변수는 battery.fractal_params() (2D 보로노이 탭과 같은 값)."""
    return build_tissue(fp or battery.fractal_params(), p, battery.gel_height_mm, battery.gel_area_cm2 * 100,
                        battery.stack.saline.temperature_c)


@dataclass
class TissueRecipe:
    """통째 결정화 (인공세포형): 병 안의 식염수를 그대로 쓰고 한 번에 섞어 아래에서 위로 얼림. 층·극성 없음."""

    name: str = "통째 결정 (인공세포형)"
    bottle_ml: float = 500.0
    take_out_ml: float = 100.0  # PVA 를 녹이려고 병에서 덜어 내는 식염수
    pva_wt: float = 3.0
    go_mg_ml: float = 0.5
    plate_c: float = -20.0
    freeze_thaw: int = 3

    def amounts(self) -> list[tuple[str, list[tuple[str, float, str]]]]:
        v = self.bottle_ml
        pva = v * self.pva_wt / 100
        go_disp = v * self.go_mg_ml / 4.0
        return [
            ("PVA 용액 (병에서 덜어 낸 식염수로)", [("덜어 낸 생리식염수", self.take_out_ml, "mL"), ("PVA 가루", pva, "g"),
                                                ("농도", 100 * pva / self.take_out_ml, "wt%")]),
            ("그래핀 폴리머 액정 (GO)", [("GO 분산액 4 mg/mL", go_disp, "mL"), ("병 안 GO", self.go_mg_ml, "mg/mL")]),
            ("병에 다시 넣기", [("병에 남은 식염수", v - self.take_out_ml, "mL"),
                             ("더 빼낼 식염수 (넘침 방지)", go_disp, "mL"), ("최종 부피", v, "mL")]),
        ]

    def battery(self):
        from .bottle import BottleGelBattery, BottleSpec, GelFormation

        return BottleGelBattery(BottleSpec(fill_volume_ml=self.bottle_ml),
                                GelFormation(go_mg_per_ml=self.go_mg_ml, reactants="PVA 크라이오겔 · GO (방향성 동결)"))
