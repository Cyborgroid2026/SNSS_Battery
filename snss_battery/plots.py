"""GUI와 웹 뷰어가 함께 쓰는 matplotlib 그림."""

from __future__ import annotations

import copy
import math

from matplotlib import colormaps
from matplotlib.cm import ScalarMappable
from matplotlib.colors import ListedColormap, Normalize
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle
from matplotlib.ticker import FuncFormatter

from .artificial_cell import ArtificialCellStack
from .assembly import PHASE_LABELS, GrapheneLCDispersion, Phase, classify_phase
from .constants import FARADAY
from .simulation import CyclingResult, max_power_point

PHASE_COLORS = {
    Phase.ISOTROPIC: "#dfe7f2",
    Phase.BIPHASIC: "#b9d3ee",
    Phase.NEMATIC: "#7fb2e5",
    Phase.AGGREGATED: "#e9c9a8",
    Phase.ALIGNED_GEL: "#6cc08b",
}
PHASE_ORDER = list(PHASE_COLORS)

PART_COLORS = {
    "plate": ("#9ecae1", 0.25),
    "electrode": ("#222222", 1.0),
    "frame_a": ("#c6dbef", 0.95),
    "frame_b": ("#2171b5", 0.95),
    "frame_e": ("#969696", 0.95),
    "cem": ("#e8833a", 1.0),
    "aem": ("#3a9a5b", 1.0),
    "rod": ("#e6d3a3", 1.0),
    "nut": ("#c9a66b", 1.0),
}


def stack_at_soc(stack: ArtificialCellStack, soc: float) -> ArtificialCellStack:
    """원본은 두고, 주어진 SOC(0~1)까지 손실 없이 충전된 사본."""
    s = copy.deepcopy(stack)
    s.q = soc * s.capacity_c
    s.x = min(s.current_efficiency * s.q / (FARADAY * s.geometry.volume_l), s.max_shift)
    return s


def plot_assembly(fig, disp: GrapheneLCDispersion, nacl_mm: float) -> None:
    fig.clear()
    ax = fig.add_subplot(111)
    nx, ny = 160, 120
    gos = [10 ** (-2 + 3.3 * i / (nx - 1)) for i in range(nx)]  # 0.01–20 mg/mL
    nacls = [10 ** (3.5 * j / (ny - 1)) for j in range(ny)]  # 1–3000 mM
    probe = copy.copy(disp)
    grid = []
    for n in nacls:
        row = []
        for g in gos:
            probe.go_mg_per_ml = g
            row.append(PHASE_ORDER.index(classify_phase(probe, n)))
        grid.append(row)
    cmap = ListedColormap([PHASE_COLORS[p] for p in PHASE_ORDER])
    ax.pcolormesh(gos, nacls, grid, cmap=cmap, vmin=-0.5, vmax=len(PHASE_ORDER) - 0.5, shading="auto")
    ax.set_xscale("log")
    ax.set_yscale("log")
    plain = FuncFormatter(lambda v, _pos: f"{v:g}")
    ax.xaxis.set_major_formatter(plain)
    ax.yaxis.set_major_formatter(plain)
    ax.axhline(154, color="k", ls=":", lw=1)
    ax.text(gos[1], 154 * 1.1, "약국 생리식염수 0.9% (154 mM)", fontsize=8)
    ax.plot([disp.go_mg_per_ml], [nacl_mm], marker="*", ms=18, color="crimson", mec="white")
    ax.set_xlabel("GO 농도 [mg/mL]")
    ax.set_ylabel("NaCl 농도 [mM]")
    ax.set_title("그래핀 액정 + 식염수 상태도 (★ = 현재 배합)")
    ax.legend(handles=[Patch(color=PHASE_COLORS[p], label=PHASE_LABELS[p]) for p in PHASE_ORDER],
              loc="upper left", fontsize=8, framealpha=0.9)


def plot_structure(fig, s: ArtificialCellStack) -> None:
    fig.clear()
    ax = fig.add_subplot(111)
    cmap = colormaps["Blues"]
    norm = Normalize(0, 2 * s.c0 * 1000)
    shown = list(range(s.n_pairs)) if s.n_pairs <= 5 else [0, 1, 2, None, s.n_pairs - 1]
    w, gap, x = 1.0, 0.12, 0.6
    ax.add_patch(Rectangle((0, -0.1), 0.35, 1.2, color="#333"))
    ax.text(0.17, -0.2, "결정\n아래면(-)", ha="center", va="top", fontsize=8)
    for idx in shown:
        if idx is None:
            ax.text(x + 0.4, 0.5, "…", ha="center", va="center", fontsize=22)
            x += 0.8
            continue
        for name, conc, mem, mem_color in (
            ("A", s.c_dilute * 1000, "CEM", "#e8833a"),
            ("B", s.c_concentrated * 1000, "AEM", "#3a9a5b"),
        ):
            ax.add_patch(FancyBboxPatch((x, 0), w, 1, boxstyle="round,pad=0.02,rounding_size=0.25",
                                        fc=cmap(norm(conc)), ec="#4a6fa5", lw=1.2))
            txt = "white" if conc > s.c0 * 1000 * 1.1 else "#123"
            ax.text(x + w / 2, 0.6, f"{name}{idx + 1}", ha="center", fontsize=9, color=txt, weight="bold")
            ax.text(x + w / 2, 0.36, f"{conc:.0f} mM", ha="center", fontsize=8, color=txt)
            x += w
            ax.add_patch(Rectangle((x, -0.05), gap, 1.1, color=mem_color))
            if idx == shown[0]:
                ax.text(x + gap / 2, 1.12, mem, ha="center", fontsize=8, color=mem_color, weight="bold")
            x += gap
    ax.add_patch(Rectangle((x + 0.1, -0.1), 0.35, 1.2, color="#333"))
    ax.text(x + 0.27, -0.2, "결정\n윗면(+)", ha="center", va="top", fontsize=8)
    if s.x > 0:
        ax.annotate("", xy=(0.65, 1.4), xytext=(2.0, 1.4),
                    arrowprops=dict(arrowstyle="->", color="#e8833a", lw=2))
        ax.text(2.1, 1.4, "방전 시 Na⁺ 가 진한 세포 → 묽은 세포로 (CEM 통과), Cl⁻ 는 반대로 (AEM 통과)",
                va="center", fontsize=8, color="#555")
    ax.set_xlim(-0.2, x + 0.7)
    ax.set_ylim(-0.75, 1.65)
    ax.set_aspect("equal")
    ax.set_axis_off()
    _, p = max_power_point(s)
    ax.set_title(
        f"SOC {s.state_of_charge * 100:.0f}% | 개방전압 {s.open_circuit_voltage():.3f} V "
        f"(막전위 {s.membrane_potential_pair() * 1000:.1f} mV/쌍 × {s.n_pairs}쌍 + 접촉면) | "
        f"순간 최대 {p * 1000:.2f} mW",
        fontsize=10,
    )
    fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax, orientation="horizontal",
                 fraction=0.05, pad=0.02, label="도메인 내부 NaCl 농도 [mM]")


def plot_cycles(fig, res: CyclingResult, v_max: float, v_min: float) -> None:
    fig.clear()
    if not res.points:
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, "기록된 데이터 없음\n" + "\n".join(res.warnings), ha="center", va="center",
                transform=ax.transAxes)
        ax.set_axis_off()
        return
    t = [p.time_s / 3600 for p in res.points]
    ax1 = fig.add_subplot(311)
    for phase, color, label in (("charge", "tab:red", "충전"), ("discharge", "tab:blue", "방전")):
        ax1.plot(t, [p.voltage_v if p.phase == phase else math.nan for p in res.points], color=color, label=label)
    ax1.axhline(v_max, color="tab:red", ls="--", lw=0.8)
    ax1.axhline(v_min, color="tab:blue", ls="--", lw=0.8)
    ax1.set_ylabel("단자전압 [V]")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(alpha=0.3)
    ax2 = fig.add_subplot(312, sharex=ax1)
    ax2.plot(t, [p.c_dilute_mm for p in res.points], color="#7fb2e5", label="묽은 도메인 A")
    ax2.plot(t, [p.c_concentrated_mm for p in res.points], color="#08306b", label="진한 도메인 B")
    ax2.set_ylabel("NaCl [mM]")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(alpha=0.3)
    ax3 = fig.add_subplot(313, sharex=ax1)
    ax3.plot(t, [p.soc * 100 for p in res.points], color="tab:purple")
    ax3.set_ylabel("SOC [%]", color="tab:purple")
    ax3.set_xlabel("시간 [h]")
    ax3.grid(alpha=0.3)
    ax4 = ax3.twinx()
    ax4.plot(t, [p.electrode_voltage_v for p in res.points], color="tab:gray", lw=1)
    ax4.set_ylabel("접촉면 전압 [V]", color="tab:gray")


def plot_battery_3d(fig, design) -> None:
    """병에서 꺼낸 결정 블록 + 측정 프로브. 층 경계는 몇 쌍마다 고리로 표시."""
    from matplotlib.colors import to_rgba
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    fig.clear()
    ax = fig.add_subplot(111, projection="3d")
    colors = {"crystal": ("#9ecae1", 0.85), "probe": ("#c0392b", 1.0)}
    tris, cols = [], []
    for solid in design.solids():
        rgba = to_rgba(*colors.get(solid.kind, ("#999999", 1.0)))
        tris += solid.triangles
        cols += [rgba] * len(solid.triangles)
    ax.add_collection3d(Poly3DCollection(tris, facecolors=cols, edgecolor="none"))
    st = design.battery.stack
    r, h = design.gel_radius, design.block_height
    step = max(1, st.n_pairs // 12)
    pair = h / st.n_pairs
    th = [2 * math.pi * k / 64 for k in range(65)]
    for k in range(step, st.n_pairs, step):
        ax.plot([r * math.cos(t) for t in th], [r * math.sin(t) for t in th], [k * pair] * len(th),
                color="#2171b5", lw=0.6)
    reach = r
    ax.set_xlim(-r, reach)
    ax.set_ylim(-r, r)
    L = design.p.probe_length_mm
    ax.set_zlim(-L, h + L)
    ax.set_box_aspect((reach + r, 2 * r, h + 2 * L))
    ax.set_xlabel("X [mm]")
    ax.set_ylabel("Y [mm]")
    ax.set_zlabel("높이 [mm]")
    ax.view_init(elev=18, azim=-60)
    ax.set_title(f"병에서 꺼낸 결정 · 세포형 도메인 {2 * st.n_pairs}층 (고리 = {step}쌍마다) · "
                 "빨강 = 측정 프로브", fontsize=9)


# ---------- 보로노이 · 프랙탈 ----------
def _plain_log(ax, axes="xy") -> None:
    """로그 축 눈금을 10^-1 대신 0.1 처럼 표시 (한글 글꼴에서 위첨자 마이너스가 깨지는 문제 회피)."""
    from matplotlib.ticker import FuncFormatter, NullFormatter

    fmt = FuncFormatter(lambda v, _p: f"{v:g}")
    for name in axes:
        axis = ax.xaxis if name == "x" else ax.yaxis
        axis.set_major_formatter(fmt)
        axis.set_minor_formatter(NullFormatter())


_WALL_STYLE = {
    "same": ("#6b7785", 0.5),
    "cem": ("#e8833a", 1.6),
    "aem": ("#3a9a5b", 1.6),
    "defect": ("#d1263b", 2.4),
}


def plot_voronoi_section(fig, res, n_layers: int = 8, title: str | None = None, ax=None) -> None:
    """결정 단면의 보로노이 도메인 (아래쪽 n_layers 층 확대)."""
    from matplotlib.collections import LineCollection, PolyCollection

    if ax is None:
        fig.clear()
        ax = fig.add_subplot(111)
    W = res.window[0]
    z_max = min(res.window[1], n_layers * res.layer_mm)
    polys, cols = [], []
    for poly, c in zip(res.polygons, _poly_layers(res)):
        if poly[:, 1].min() > z_max:
            continue
        polys.append(poly)
        cols.append("#96c4de" if c % 2 == 0 else "#2668a8")
    ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors="none", alpha=0.9))
    for kind, (color, lw) in _WALL_STYLE.items():
        seg = res.segments.get(kind)
        if seg is not None and len(seg):
            ax.add_collection(LineCollection(seg, colors=color, linewidths=lw))
    s = res.seeds[res.seeds[:, 1] <= z_max]
    ax.plot(s[:, 0], s[:, 1], ".", ms=1.5, color="#111")
    ax.set_xlim(0, W)
    ax.set_ylim(0, z_max)
    ax.set_aspect("equal")
    ax.set_xlabel("가로 [mm]")
    ax.set_ylabel("높이 [mm]")
    p = res.params
    ax.set_title(title or f"보로노이 도메인 단면 — 층 경계 D={p.interface_dimension:.2f}, 거칠기 {p.roughness:.2f}t, "
                          f"결정핵 D={p.seed_dimension:.2f}", fontsize=9)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#96c4de", label="묽은 도메인"), Patch(color="#2668a8", label="진한 도메인"),
                       Line2D([], [], color="#e8833a", lw=2, label="양이온 선택 벽"),
                       Line2D([], [], color="#3a9a5b", lw=2, label="음이온 선택 벽"),
                       Line2D([], [], color="#d1263b", lw=2.4, label="결함 벽 (층 건너뜀 → 단락)"),
                       Line2D([], [], color="#111", marker=".", lw=0, label="결정핵 (보로노이 씨앗)")],
              loc="upper right", fontsize=7, framealpha=0.9)


def _poly_layers(res):
    """polygons 는 영역이 닫힌 도메인만 담고 있으므로 같은 순서의 층 번호를 다시 계산."""
    import numpy as np

    cents = np.array([poly.mean(axis=0) for poly in res.polygons])
    if not len(cents):
        return []
    d = ((cents[:, None, :] - res.seeds[None, :, :]) ** 2).sum(-1) if len(cents) * len(res.seeds) < 4e7 else None
    if d is None:
        from scipy.spatial import cKDTree
        idx = cKDTree(res.seeds).query(cents)[1]
    else:
        idx = d.argmin(1)
    return res.layers[idx]


def plot_fractal_sweeps(fig, by_dim, by_rough) -> None:
    fig.clear()
    for k, (rows, xkey, xlabel) in enumerate((
        (by_dim, lambda r: r.params.interface_dimension, "층 경계 프랙탈 차원 D"),
        (by_rough, lambda r: r.params.roughness, "층 경계 거칠기 (RMS / 층 두께)"),
    )):
        ax = fig.add_subplot(1, 2, k + 1)
        x = [xkey(r) for r in rows]
        ax.plot(x, [r.ocv_v for r in rows], "o-", color="#1d5fa8", label="개방전압 [V]")
        ax.plot(x, [r.max_power_mw / 10 for r in rows], "s-", color="#3a9a5b", label="최대전력 [×10 mW]")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("V  /  ×10 mW")
        ax.grid(alpha=0.3)
        ax2 = ax.twinx()
        ax2.semilogy(x, [max(r.leak_current_ma, 1e-4) for r in rows], "^--", color="#d1263b", label="내부 누설 [mA]")
        ax2.set_ylabel("내부 누설 전류 [mA] (로그)", color="#d1263b")
        _plain_log(ax2, "y")
        best = max(rows, key=lambda r: r.max_power_mw - r.leak_current_ma * r.ocv_v)
        ax.axvline(xkey(best), color="#999", ls=":")
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="lower left")
        ax.set_title("프랙탈 차원에 따른 변화" if k == 0 else "경계 거칠기에 따른 변화", fontsize=10)


def plot_fractal_map(fig, grid, dims, roughs) -> None:
    """D × 거칠기 지도: 유효 출력 = 최대전력 − 내부 누설 손실."""
    import numpy as np

    fig.clear()
    ax = fig.add_subplot(111)
    Z = np.array([[max(r.max_power_mw - r.leak_current_ma * r.ocv_v, 0) for r in row] for row in grid])
    im = ax.imshow(Z, origin="lower", aspect="auto", cmap="viridis",
                   extent=(dims[0] - 0.05, dims[-1] + 0.05, roughs[0] - 0.05, roughs[-1] + 0.05))
    j, i = np.unravel_index(np.argmax(Z), Z.shape)
    ax.plot(dims[i], roughs[j], marker="*", ms=18, color="crimson", mec="white")
    ax.set_xlabel("층 경계 프랙탈 차원 D")
    ax.set_ylabel("층 경계 거칠기 (RMS / 층 두께)")
    ax.set_title(f"유효 출력 지도 (최대전력 − 누설 손실) · ★ 최적 D={dims[i]:.1f}, 거칠기 {roughs[j]:.1f}", fontsize=10)
    fig.colorbar(im, ax=ax, label="유효 출력 [mW]")


def plot_box_counting(fig, res) -> None:
    import numpy as np

    fig.clear()
    ax = fig.add_subplot(111)
    for key, color, label in (("interfaces", "#e8833a", "층 경계 하나"), ("walls", "#1d5fa8", "모든 도메인 벽")):
        bc = res.box_counts.get(key) or {}
        if not bc.get("eps"):
            continue
        x = 1 / np.array(bc["eps"])
        y = np.array(bc["counts"])
        ax.loglog(x, y, "o", color=color)
        c = np.polyfit(np.log(x), np.log(y), 1)
        ax.loglog(x, np.exp(np.polyval(c, np.log(x))), "-", color=color,
                  label=f"{label}: D = {c[0]:.2f}" + (" (여러 경계 평균 " + f"{res.fractal_dim_interfaces:.2f})"
                                                       if key == "interfaces" else ""))
    _plain_log(ax)
    ax.set_xlabel("1 / 상자 크기 ε [1/mm]")
    ax.set_ylabel("벽이 지나는 상자 수 N(ε)")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    ax.set_title("박스 카운팅 프랙탈 차원 (기울기 = D)", fontsize=10)


def plot_voronoi_stats(fig, res) -> None:
    import numpy as np

    fig.clear()
    ax1 = fig.add_subplot(121)
    ks = sorted(res.neighbor_hist)
    tot = sum(res.neighbor_hist.values()) or 1
    ax1.bar(ks, [res.neighbor_hist[k] / tot for k in ks], color="#2668a8")
    ax1.axvline(6, color="#d1263b", ls="--", lw=1)
    ax1.set_xlabel("이웃 도메인 수 (변의 수)")
    ax1.set_ylabel("비율")
    ax1.set_title(f"이웃 수 분포 · 평균 {res.mean_neighbors:.2f} (보로노이 이론값 6)", fontsize=9)
    ax2 = fig.add_subplot(122)
    a = res.areas
    bins = np.logspace(np.log10(a.min()), np.log10(a.max()), 30)
    ax2.hist(a, bins=bins, color="#3a9a5b")
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    _plain_log(ax2)
    ax2.set_xlabel("도메인 면적 [mm²]")
    ax2.set_ylabel("개수")
    ax2.set_title(f"도메인 크기 분포 · 변동계수 {res.area_cv:.2f}", fontsize=9)
