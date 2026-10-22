"""빛 조각가 SC-2 — 펜 없이 배지 속 물질 + 전자기파(빛)만으로 결정을 맺게 함 (명세: spec/LIGHT.md).

배양조 속 멸균생리식염수(배지)가 곧 모니터다. 데스크톱(수조 아래)이 설계를 층마다 빛 그림으로 바꿔 위에서 비춘다.

- 잉크층: 배지 위에 뜬 염이 옅은 얇은 층 (NaCl 10 mM < CCC) — GO 가 엉기지 않고 떠 있음, 감광 PVA(PVA-SbQ) 와 함께.
- 빛(405 nm): 빛이 닿은 곳만 감광 PVA 가 가교 → 그 층이 굳음. 더 많이 받은 곳은 GO 가 rGO 로 (세포질, 전자 통로).
  적게 받은 곳은 GO 그대로 (막, 이온만).
- 받침이 한 층 내려가면 굳은 층이 잉크층을 지나 아래 멸균생리식염수(154 mM > CCC) 에 닿아 엉기며 고정.
  빛을 받지 않은 잉크는 위층에 남아 다음 층에 쓰임.
- 초록 빛(530 nm): 잉크 속 에오신 Y(금속 없는 광산화환원 색소)가 들뜬 곳에서만 NBD(디아조늄)가 rGO 에 붙음 → p 세포.
  n 세포는 초록을 받지 않음 (빛으로 n 도핑하는 방법은 아직 없음 → 거의 도핑 없음).

계산:
- 빛 침투 Dp = 1 / (ln10 · (ε_GO·c_GO + a_SbQ·PVA%)), 굳는 깊이 Cd = Dp·ln(E/Ec) (SLA 작업 곡선, Jacobs).
- 층마다 노출량은 칸 기둥마다 위에서 아래로 정함: 위층 빛이 아래로 새어 쌓이는 것까지 셈 (광환원은 누적, 가정).
  막 칸의 누적량이 θ·E_red 를 넘으면 막이 rGO 가 되어 전자가 샘 → 점검.
- 상온: 잉크 표면이 빛을 다 흡수 → 표면 온도 상승 = 빛 세기 / (잉크층 전도 + 공기) ≤ 1 K 가 빛 세기 상한.
  그래서 제작 시간 ≈ E_red · 높이 / (Dp · 빛 세기) — GO 농도(Dp) 와 시간의 맞교환.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np

from .printer import SculptorSpec, Tank, solution_density
from .sculpt import EMPTY, MEM, NEG, POS, BodyModel, CellParams, Piece, body_signs, describe_prediction, design, piece_meshes

D_NACL = 1.5e-9  # NaCl 확산 계수 m²/s (25 °C)
K_WATER = 0.6  # W/m·K


@dataclass
class Ink:
    """잉크 우물 — 떠 있는 테 안, 배지 위에 뜬 염이 옅은 층."""

    nacl_mm: float = 10.0
    go_mg_ml: float = 2.0
    pva_wt: float = 1.0  # 감광 PVA (PVA-SbQ, 스크린 인쇄 감광 유제의 고분자)
    nbd_mm: float = 1.0  # 4-니트로벤젠디아조늄 BF₄ — p 도펀트 (초록 빛이 닿은 곳만 붙음)
    eosin_um: float = 10.0  # 에오신 Y — 530 nm 광산화환원 색소 (C,H,O,Br,Na — 금속 없음)
    depth_mm: float = 10.0  # 잉크층 두께 (수면 → 멸균생리식염수 경계)
    well_mm: float = 150.0  # 떠 있는 테 안쪽 한 변
    src: str = ("GO 수분산 + 감광 PVA(PVA-SbQ) + 정제수, 정제염으로 NaCl 10 mM — 섞은 뒤 차광 보관. "
                "NBD 1 mM · 에오신 Y 10 µM 을 쓰기 직전에 넣음. PEI 같은 양이온 고분자는 넣지 않음 (GO 를 엉기게 함)")

    @property
    def ml(self) -> float:
        return self.well_mm ** 2 * self.depth_mm / 1000


@dataclass
class Projector:
    name: str = ("두 색 DLP 광엔진 — 405 nm (UV 레진 프린터용) + 530 nm, 이색 거울로 합침 · 수조 위 300 mm, "
                 "아래로 투영 110×110 mm, 픽셀 약 50 µm")
    irradiance_mw_cm2: float = 6.0  # 405 nm, 잉크 표면 (상온 한도 안에서)
    green_mw_cm2: float = 6.0  # 530 nm — 405 와 번갈아 켜므로 표면 열은 둘 중 큰 쪽
    reflect: float = 0.02  # 수면 반사
    throw_mm: float = 300.0


@dataclass
class Photo:
    """빛 굳힘 · 광환원 상수 — 모두 가정 (첫 시험편으로 잴 값)."""

    eps_go: float = 15.0  # GO 405 nm 질량 흡광계수 mL·mg⁻¹·cm⁻¹ (상용로그, 가정 — 808 nm 3.6 의 약 4배)
    a_sbq: float = 1.5  # 감광 PVA 1 wt% 당 흡광도 /cm (가정)
    ec_mj_cm2: float = 20.0  # 감광 PVA 가교 문턱 Ec (가정)
    e_red_mj_cm2: float = 1000.0  # GO → rGO (세포질 전자 통로) 누적 노출 (가정, 상온 광환원)
    theta_mem: float = 0.3  # 막 누적량이 θ·E_red 아래면 GO 그대로 (절연, 가정)
    overcure: float = 0.25  # 굳는 깊이 = 층 × (1 + 겹침) — 아래층에 붙음
    eps_go_530: float = 10.0  # GO 530 nm 질량 흡광계수 (가정)
    eps_eosin: float = 95000.0  # 에오신 Y 몰 흡광계수 M⁻¹cm⁻¹ (517 nm 부근 문헌값)
    e_graft_mj_cm2: float = 300.0  # 초록 누적 노출당 NBD 접목 (1 − e^(−D/E_g)) 의 E_g (가정)
    graft_target: float = 0.8  # p 세포 목표 접목 비율
    n_graft_max: float = 5.0  # 다 붙었을 때 정공 밀도 10¹² cm⁻² (SC-1 p 세포와 같음, 가정)
    n_graft_allow: float = 0.1  # n 세포에 새어 붙어도 되는 비율
    tau_dark_h: float = 48.0  # 빛 없이 디아조늄이 rGO 에 저절로 붙는 시간 상수 (가정) — 잉크 속에 있는 동안만


@dataclass
class Desktop:
    where: str = "수조 아래 받침 — 수조 바닥과 사이에 XPS 단열 30 mm + 앞뒤로 빠지는 바람길"
    pc: str = "데스크톱 (GPU · Blender · 설계 콘솔) — 프로젝터 HDMI · Z 모터 USB · 전극 측정 USB"
    keyboard: str = "IP68 실리콘 키보드 (의료용, 물·식염수 세척 가능)"
    mouse: str = "IP68 방수 마우스 (의료용, 밀봉 휠)"
    exhaust_k: float = 5.0  # 단열판 아래 공기 = 방 + 5 K (바람길)
    insulation_w_mk: float = 0.035
    insulation_mm: float = 30.0


@dataclass
class LightSculptorSpec:
    name: str = "SNSS 빛 조각가 SC-2"
    build_mm: tuple[float, float, float] = (110.0, 110.0, 100.0)
    frame_mm: tuple[float, float, float] = (330.0, 330.0, 300.0)
    line_mm: float = 0.41  # 설계 칸 가로 (투영 픽셀 약 8개 묶음)
    shrink_compensation: float = 0.03
    recoat_s: float = 12.0  # 받침 한 층 내림 + 잉크가 고르게 덮일 때까지
    cure_h: float = 6.0  # 다 빚은 뒤 멸균생리식염수 속 숙성
    tank: Tank = field(default_factory=Tank)
    ink: Ink = field(default_factory=Ink)
    projector: Projector = field(default_factory=Projector)
    photo: Photo = field(default_factory=Photo)
    desktop: Desktop = field(default_factory=Desktop)
    z_motor_w: float = 3 * 0.35  # Z 모터 3개 (방수 통 · 자석 커플링) — 물속 기계는 이것뿐
    ccc_per_pva_wt: float = 0.15

    # ---------- 잉크층 ----------
    def ccc_mm(self) -> float:
        from .assembly import PURE_GO_NACL_CCC_MM

        return PURE_GO_NACL_CCC_MM * (1 + self.ccc_per_pva_wt * self.ink.pva_wt)

    def ink_density(self) -> float:
        k = self.ink
        return solution_density(go_g_l=k.go_mg_ml, nacl_mm=k.nacl_mm, pva_g_l=10 * k.pva_wt)

    def ink_life_h(self) -> float:
        """경계에서 올라오는 염이 노광면(잉크층 맨 위)을 CCC 의 80 % 로 만들 때까지 — 그 전에 잉크를 갊."""
        from scipy.special import erfcinv

        k, tk = self.ink, self.tank
        frac = (0.8 * self.ccc_mm() - k.nacl_mm) / (tk.saline_mm - k.nacl_mm)
        x = erfcinv(2 * frac)  # c = c_top + Δc · ½ erfc(d / 2√(Dt))
        d = k.depth_mm / 1000
        return (d / (2 * x)) ** 2 / D_NACL / 3600

    # ---------- 빛 ----------
    def dp_mm(self) -> float:
        a = self.photo.eps_go * self.ink.go_mg_ml + self.photo.a_sbq * self.ink.pva_wt  # 상용로그 /cm
        return 10 / (math.log(10) * a)

    def dp_green_mm(self) -> float:
        a = self.photo.eps_go_530 * self.ink.go_mg_ml + self.photo.eps_eosin * self.ink.eosin_um * 1e-6
        return 10 / (math.log(10) * a)

    def e_graft_target(self) -> float:
        return self.photo.e_graft_mj_cm2 * math.log(1 / (1 - self.photo.graft_target))

    def _membrane_leak(self, x: float) -> float:
        """층 = x·Dp 일 때 세포질 기둥 바로 아래 막 칸이 받는 누적량 / E_red (정상 상태)."""
        ph = self.photo
        e_mem = ph.ec_mj_cm2 * math.exp((1 + ph.overcure) * x)
        return math.exp(-x) + e_mem * (1 - math.exp(-x)) / x / ph.e_red_mj_cm2

    def layer_ratio(self) -> float:
        """층 두께 / Dp — 막 새는 빛이 가장 적은 값 (0.5–4 에서 찾음)."""
        xs = np.linspace(0.5, 4.0, 351)
        return float(xs[np.argmin([self._membrane_leak(x) for x in xs])])

    @property
    def layer_mm(self) -> float:
        return round(self.layer_ratio() * self.dp_mm(), 3)

    def e_cure(self) -> float:
        """층 바닥까지 굳는 노광 (mJ/cm²) — 막 칸은 이것만."""
        ph = self.photo
        return ph.ec_mj_cm2 * math.exp((1 + ph.overcure) * self.layer_mm / self.dp_mm())

    # ---------- 열 (상온) ----------
    def surface_rise_k(self) -> float:
        """잉크 표면: 빛이 거의 다 흡수 → 잉크층 전도(아래 배지로) + 공기(10 W/m²K)."""
        pj = self.projector
        q = max(pj.irradiance_mw_cm2, pj.green_mw_cm2) * 10 * (1 - pj.reflect)  # W/m² (두 색을 번갈아)
        return q / (K_WATER / (self.ink.depth_mm / 1000) + 10.0)

    def heat_w(self) -> dict:
        b, d = self.build_mm, self.desktop
        light = self.projector.irradiance_mw_cm2 * 10 * (1 - self.projector.reflect) * b[0] * b[1] / 1e6
        x, y, _ = (v / 1000 for v in self.tank.inner_mm)
        pc = d.insulation_w_mk / (d.insulation_mm / 1000) * x * y * d.exhaust_k
        return {"빛 (잉크가 흡수)": light, "Z 모터 3": self.z_motor_w, "데스크톱 (단열판 너머)": pc}

    def heat_rise_k(self) -> float:
        return sum(self.heat_w().values()) / self.tank.heat_loss_w_k

    # ---------- 점검 ----------
    def check(self) -> list[str]:
        bad = []
        k, tk = self.ink, self.tank
        if k.nacl_mm + k.nbd_mm >= self.ccc_mm():
            bad.append(f"잉크 염 {k.nacl_mm + k.nbd_mm:g} mM (NaCl + NBD) ≥ CCC {self.ccc_mm():.0f} mM — 잉크 속 GO 가 저절로 엉김")
        if tk.saline_mm <= self.ccc_mm():
            bad.append("멸균생리식염수가 CCC 보다 묽어 내려간 층이 고정되지 않음")
        if self.ink_density() > tk.density - 0.5:
            bad.append(f"잉크 밀도 {self.ink_density():.1f} ≥ 배지 {tk.density:.1f} − 0.5 kg/m³ — 위에 뜨지 않음")
        if self._membrane_leak(self.layer_ratio()) > self.photo.theta_mem:
            bad.append(f"막 아래로 새는 빛 {self._membrane_leak(self.layer_ratio()):.2f}·E_red > θ {self.photo.theta_mem:g} — 막이 rGO 가 됨")
        if self.surface_rise_k() > 1.0:
            bad.append(f"잉크 표면 +{self.surface_rise_k():.2f} K (> 1 K) — 빛 세기를 낮출 것 (상온)")
        if self.heat_rise_k() > 1.0:
            bad.append(f"배지 +{self.heat_rise_k():.2f} K (> 1 K) — 데스크톱 단열 · 바람길 보강")
        if k.depth_mm < 4 * self.layer_mm:
            bad.append("잉크층이 너무 얇아 내려가기 전 굳은 층이 잉크 속에서 버틸 자리가 없음")
        if (self.build_mm[0] > k.well_mm - 20) or (self.build_mm[1] > k.well_mm - 20):
            bad.append("잉크 우물이 출력 공간보다 좁음")
        return bad

    def design_spec(self) -> SculptorSpec:
        """설계(보로노이 세포)는 SC-1 과 같은 함수를 씀 — 칸 크기만 이 기계의 것으로."""
        return replace(SculptorSpec(), build_mm=self.build_mm, line_mm=self.line_mm, layer_mm=self.layer_mm,
                       shrink_compensation=self.shrink_compensation)

    def describe(self) -> str:
        k, pj, ph, tk, d = self.ink, self.projector, self.photo, self.tank, self.desktop
        lines = [f"[{self.name} — 펜 없이 빛으로: 배지가 모니터]",
                 f"  출력 공간 {self.build_mm[0]:g}×{self.build_mm[1]:g}×{self.build_mm[2]:g} mm · 칸 {self.line_mm} mm × 층 {self.layer_mm} mm",
                 f"  배양조: {tk.container} · 멸균생리식염수 {tk.saline_mm:g} mM {tk.fill_mm:g} mm (밀도 {tk.density:.1f} kg/m³)",
                 f"  잉크층 (떠 있는 테 {k.well_mm:g} mm 안, {k.depth_mm:g} mm, {k.ml:.0f} mL): NaCl {k.nacl_mm:g} mM · GO {k.go_mg_ml:g} mg/mL · "
                 f"감광 PVA {k.pva_wt:g} % → 밀도 {self.ink_density():.1f} kg/m³ (배지보다 {tk.density - self.ink_density():.1f} 가벼워 뜸)",
                 f"    CCC {self.ccc_mm():.0f} mM: 잉크 {k.nacl_mm:g} < CCC → 떠 있음 · 배지 {tk.saline_mm:g} > CCC → 내려가면 고정",
                 f"    잉크 수명 {self.ink_life_h():.0f} h (경계에서 올라오는 염이 노광면을 CCC 80 % 로 만들 때까지)",
                 f"    {k.src}",
                 f"  빛: {pj.name} · {pj.irradiance_mw_cm2:g} mW/cm²",
                 f"    침투 Dp {self.dp_mm():.3f} mm · 층 {self.layer_mm} mm (= {self.layer_ratio():.2f} Dp, 막 새는 빛 최소 "
                 f"{self._membrane_leak(self.layer_ratio()):.2f}·E_red < θ {ph.theta_mem:g})",
                 f"    막 = 굳힘만 {self.e_cure():.0f} mJ/cm² · 세포질 = 누적 {ph.e_red_mj_cm2:g} mJ/cm² 이상 (GO → rGO)",
                 f"    초록 530 nm {pj.green_mw_cm2:g} mW/cm² · 침투 {self.dp_green_mm():.3f} mm · p 세포만 누적 {self.e_graft_target():.0f} mJ/cm² "
                 f"→ NBD {100 * ph.graft_target:.0f} % 접목 (정공 {ph.graft_target * ph.n_graft_max:.1f}×10¹² cm⁻²)",
                 f"    잉크 표면 +{self.surface_rise_k():.2f} K · 배지 +{self.heat_rise_k():.2f} K (" +
                 " · ".join(f"{n} {w:.1f} W" for n, w in self.heat_w().items()) + ")",
                 f"  데스크톱: {d.where}", f"    {d.pc}", f"    입력: {d.keyboard} · {d.mouse}",
                 "  물속 기계: 받침 + Z 나일론 나사봉 3 (모터 방수 통 · 자석 커플링) + 흑연 패드 · 전극 — 펜 · 갠트리 없음"]
        bad = self.check()
        lines.append("  설계 점검: " + ("통과" if not bad else "; ".join(bad)))
        return "\n".join(lines)


# ---------- 층마다 빛 그림 ----------
def _columns(floor: np.ndarray, target: np.ndarray, x: float) -> tuple[np.ndarray, np.ndarray]:
    """칸 기둥마다 위층부터: 노출 E_k = max(바닥값, (목표 − 위층에서 새어 온 빛)/c). 누적 D 도 돌려줌.

    층 k 노광면에서 깊이 z 의 빛 = E·exp(−z/Dp). 한 칸(두께 h) 평균 = E·c, c = (1 − r)/x, r = exp(−h/Dp), x = h/Dp.
    n 층 아래 칸 평균 = E·c·rⁿ. 칸 k 누적 D_k = c·(E_k + Q_k), Q_k = r·(E_{k+1} + Q_{k+1}).
    """
    r = math.exp(-x)
    c = (1 - r) / x
    E = np.zeros(floor.shape, dtype=np.float32)
    D = np.zeros(floor.shape, dtype=np.float32)
    Q = np.zeros(floor.shape[:2])
    for k in range(floor.shape[2] - 1, -1, -1):
        e = np.maximum(floor[:, :, k], np.where(target[:, :, k] > 0, (target[:, :, k] - c * Q) / c, 0.0))
        E[:, :, k] = e
        D[:, :, k] = c * (e + Q)
        Q = r * (e + Q)
    return E, D


def exposure_plan(piece: Piece, spec: LightSculptorSpec) -> dict:
    """405 nm (굳힘 · 광환원) 와 530 nm (p 도핑) 의 층별 빛 그림 — 위층 빛이 아래로 새어 쌓이는 것까지."""
    ph = spec.photo
    mat = piece.material
    nz = mat.shape[2]
    h = piece.pitch[1]
    inside = mat != EMPTY
    cyto = (mat == POS) | (mat == NEG)
    mem = mat == MEM
    E, D = _columns(np.where(inside, spec.e_cure(), 0.0), np.where(cyto, ph.e_red_mj_cm2, 0.0), h / spec.dp_mm())
    G, Dg = _columns(np.zeros(mat.shape), np.where(mat == POS, spec.e_graft_target(), 0.0), h / spec.dp_green_mm())
    stray = (~inside) & (D >= ph.ec_mj_cm2)  # 빈 칸(잉크)이 위층 빛으로 굳음 (잉크층 아래는 이미 배지라 r 로 사라짐)
    pj = spec.projector
    t_layer = E.reshape(-1, nz).max(0) / pj.irradiance_mw_cm2 + G.reshape(-1, nz).max(0) / pj.green_mw_cm2 + spec.recoat_s
    t_layer[~inside.any(axis=(0, 1))] = 0.0
    ink_layers = int(spec.ink.depth_mm / h)
    t_ink_h = float(np.mean(t_layer[t_layer > 0])) * ink_layers / 3600 if (t_layer > 0).any() else 0.0
    dark = 1 - math.exp(-t_ink_h / ph.tau_dark_h)  # 잉크 속에 있는 동안 저절로 붙는 몫
    graft = 1 - (1 - (1 - np.exp(-Dg / ph.e_graft_mj_cm2))) * (1 - dark)
    pos, neg = mat == POS, mat == NEG
    return {
        "E": E, "D": D, "G": G, "Dg": Dg, "x": h / spec.dp_mm(),
        "layers": int(inside.any(axis=(0, 1)).sum()),
        "cyto_reduced": float((D[cyto] >= ph.e_red_mj_cm2 * 0.999).mean()) if cyto.any() else 1.0,
        "mem_leaky": float((D[mem] > ph.theta_mem * ph.e_red_mj_cm2).mean()) if mem.any() else 0.0,
        "stray_voxels": int(stray.sum()),
        "stray_ml": float(stray.sum() * piece.pitch[0] ** 2 * h / 1000),
        "ink_layers": ink_layers, "ink_hours": t_ink_h, "dark_graft": dark,
        "p_graft": float(graft[pos].mean()) if pos.any() else 0.0,
        "n_graft": float(graft[neg].mean()) if neg.any() else 0.0,
        "n_graft_over": float((graft[neg] > ph.n_graft_allow + dark).mean()) if neg.any() else 0.0,
        "layer_s": t_layer,
        "expose_s": float(t_layer.sum()),
        "dose_j_cm2_max": float(E.max() / 1000),
        "green_j_cm2_max": float(G.max() / 1000),
    }


def build_time_estimate_h(spec: LightSculptorSpec, height_mm: float) -> float:
    """세포질 기둥의 정상 상태: 층마다 E_red·x → 높이당 E_red/Dp. 맞교환 식 E_red·H/(Dp·I)."""
    return spec.photo.e_red_mj_cm2 * height_mm / (spec.dp_mm() * spec.projector.irradiance_mw_cm2) / 3600


def light_job(shape: str = "being", height_mm: float = 0.0, spec: LightSculptorSpec | None = None,
              cp: CellParams | None = None, name: str = "") -> dict:
    spec = spec or LightSculptorSpec()
    cp = cp or CellParams()
    piece = design(shape, height_mm, cp, spec.design_spec(), name)
    piece.history.append(f"빛 조각가: 층 {spec.layer_mm} mm · 잉크 GO {spec.ink.go_mg_ml:g} mg/mL · 초록 p 도핑")
    plan = exposure_plan(piece, spec)
    n_max = spec.photo.n_graft_max
    # p 세포 = 초록으로 붙은 NBD · n 세포 = 새거나 저절로 붙은 NBD 조금 (역시 p형, 약하게)
    piece.carriers = (round(plan["p_graft"] * n_max, 3), round(plan["n_graft"] * n_max, 3))
    pred = body_signs(piece, spec.design_spec(), BodyModel(go_in_cell_mg_ml=spec.ink.go_mg_ml, neg_dopant="NBD"))
    bare = replace(piece, carriers=(0.0, 0.0))
    base = body_signs(bare, spec.design_spec(), BodyModel(go_in_cell_mg_ml=spec.ink.go_mg_ml, neg_dopant=""))
    return {"spec": spec, "piece": piece, "plan": plan, "prediction": pred, "undoped_energy_j": base["energy_j"]}


def describe_job(job: dict) -> str:
    spec, p, pl = job["spec"], job["piece"], job["plan"]
    t = pl["expose_s"] / 3600
    lines = [f"[빛 조각 — {p.name}] 높이 {p.height_mm:.1f} mm · 세포 {p.n_cells()}개 · 층 {pl['layers']}개 × {p.pitch[1]} mm",
             f"  빛 그림: 층마다 막 {spec.e_cure():.0f} mJ/cm² · 세포질 기둥은 위층에서 새어 내려오는 빛을 빼고 채움 (최대 {pl['dose_j_cm2_max']:.2f} J/cm²)",
             f"  세포질 rGO 됨 {100 * pl['cyto_reduced']:.1f} % · 막이 샘 {100 * pl['mem_leaky']:.2f} % · "
             f"원치 않게 굳는 잉크 {pl['stray_ml']:.2f} mL ({pl['stray_voxels']}칸, 아래가 빈 돌출부 밑)",
             f"  시간: 빛 + 내림 {t:.1f} h (405 nm 만의 맞교환 식 E_red·H/(Dp·I) ≈ {build_time_estimate_h(spec, p.height_mm):.1f} h) + 숙성 {spec.cure_h:g} h · "
             f"잉크 수명 {spec.ink_life_h():.0f} h → 잉크 갈기 {max(0, math.ceil(t / spec.ink_life_h()) - 1)}번",
             f"  초록 p 도핑: p 세포 접목 {100 * pl['p_graft']:.0f} % (정공 {p.carriers[0]:.1f}×10¹² cm⁻²) · "
             f"n 세포 {100 * pl['n_graft']:.1f} % (새어 듦 + 잉크 속 {pl['ink_hours']:.1f} h 저절로 {100 * pl['dark_graft']:.1f} %) · "
             f"허용 넘은 n 세포 칸 {100 * pl['n_graft_over']:.2f} %",
             f"  에너지: 도핑 없을 때 {job['undoped_energy_j']:.3f} J → 초록 p 도핑 {job['prediction']['energy_j']:.3f} J "
             f"(×{job['prediction']['energy_j'] / max(job['undoped_energy_j'], 1e-12):.2f})",
             describe_prediction(job["prediction"])]
    return "\n".join(lines)


def write_light_job(job: dict, folder: str | Path, meshes: bool = True) -> dict:
    """작업 폴더: 층별 빛 그림(npz · PNG 몇 장) · 요약 · 공간 배치 · (Blender 용) 메시."""
    from .layout import make_light_layout

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    spec, p, pl = job["spec"], job["piece"], job["plan"]
    p.save(folder / f"{p.name}.npz")
    np.savez_compressed(folder / "exposure.npz", E_mj_cm2=pl["E"].astype(np.float32), D_mj_cm2=pl["D"].astype(np.float32),
                        G_mj_cm2=pl["G"].astype(np.float32), Dg_mj_cm2=pl["Dg"].astype(np.float32),
                        layer_s=pl["layer_s"], pitch=np.array(p.pitch), offset=np.array(p.offset))
    _frames(pl["E"], pl["G"], p, folder / "frames")
    (folder / "layout.json").write_text(json.dumps(make_light_layout(spec).to_json(), ensure_ascii=False), encoding="utf-8")
    pr = job["prediction"]
    if meshes:
        arrays = {}
        for role, (v, tri, w) in piece_meshes(p, 1, pr["cells"]).items():
            arrays[f"{role}_v"] = v.astype(np.float32)
            arrays[f"{role}_f"] = tri.astype(np.int32)
            if w is not None:
                arrays[f"{role}_wake"] = np.nan_to_num(w, nan=-1).astype(np.float32)
        np.savez_compressed(folder / f"{p.name}_mesh.npz", **arrays)
    summary = {"name": p.name, "pitch": list(p.pitch), "offset": list(p.offset), "height_mm": p.height_mm,"title": f"빛 조각 {p.name}", "machine": spec.name, "spec": asdict(spec) | {"layer_mm": spec.layer_mm, "dp_mm": spec.dp_mm()},
               "plan": {k: v for k, v in pl.items() if k not in ("E", "D", "G", "Dg", "layer_s")},
               "prediction": {k: v for k, v in pr.items() if k not in ("cells", "series")}, "text": describe_job(job),
               "check": spec.check()}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, default=float), encoding="utf-8")
    return {"folder": folder, "summary": summary}


def frame_rgb(E: np.ndarray, G: np.ndarray, k: int, e_max: float, g_max: float) -> np.ndarray:
    """층 k 의 프로젝터 화면 (y, x, 3): 405 nm 는 보라, 530 nm 는 초록으로 겹쳐 그림."""
    e = np.clip(E[:, :, k].T / e_max, 0, 1)
    g = np.clip(G[:, :, k].T / g_max, 0, 1)
    return np.clip(np.stack([0.62 * e, g, e], -1), 0, 1)


def _frames(E: np.ndarray, G: np.ndarray, p: Piece, out: Path, n: int = 6) -> None:
    """층 빛 그림 몇 장 — 데스크톱이 프로젝터로 보내는 화면 (보라 = 405 nm 노출량, 초록 = 530 nm)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .drawing import setup_fonts

    setup_fonts()
    out.mkdir(parents=True, exist_ok=True)
    ks = np.nonzero(E.max(axis=(0, 1)) > 0)[0]
    if not len(ks):
        return
    e_max = float(np.percentile(E[E > 0], 99))
    g_max = float(G.max()) or 1.0
    ext = (p.offset[0] * p.pitch[0], (p.offset[0] + E.shape[0]) * p.pitch[0], p.offset[1] * p.pitch[0], (p.offset[1] + E.shape[1]) * p.pitch[0])
    for k in ks[np.linspace(0, len(ks) - 1, n).astype(int)]:
        fig, ax = plt.subplots(figsize=(4, 4), dpi=110)
        ax.imshow(frame_rgb(E, G, k, e_max, g_max), origin="lower", extent=ext, interpolation="nearest")
        ax.set_title(f"층 {k} · z {k * p.pitch[1]:.1f} mm (보라 405 · 초록 530 nm)", fontsize=8)
        ax.set_xlabel("x mm")
        ax.set_ylabel("y mm")
        fig.tight_layout()
        fig.savefig(out / f"layer_{k:04d}.png")
        plt.close(fig)
