"""실험대 19단계의 현실 물리 — 단계마다 실제 물성으로 계산 (명세: spec/PHYSICS.md).

process.py 의 단계(같은 id)마다: 무엇이 물리적으로 일어나는지, 얼마나 걸리는지, 레시피 시간이 맞는지, 무엇을 조심할지.
이 숫자가 웹 '실험대' 의 물리 칸과 그림, Blender 물리 엔진 렌더(sim/blender_bench.py — Mantaflow 유체 · Bullet 강체),
발표 자료(report/make_pptx.py)를 함께 움직인다.

물성 (25 °C 근처, 출처 표시):
- 물: 점도 Vogel 식, 포화 증기압 Antoine 식 (1–100 °C), 증발 잠열 2.501·10⁶ − 2370·T J/kg, 열용량 4180 J/kg·K.
- PVA 수용액 (Mw 약 9만, 99 % 가수분해 기준): 4 wt% 가 20 °C 에서 28 mPa·s (제품 규격값). 농도 · 온도 의존성은 가정 —
  얽힌 영역(4 % 이상) η ∝ c⁴, 그 아래 η ∝ c², 온도는 아레니우스 Ea = 25 kJ/mol.
- GO: 판 하나 1 µm², 면밀도 1.2 mg/m² (산소기를 단 단층, 가정), 응집 덩이 프랙탈 차원 1.8.
- PVA 크라이오겔 탄성률 E = 0.35 kPa · c² · n^½ (c wt%, n 동결-해동 횟수 — 10 % · 3회 ≈ 60 kPa 에 맞춘 가정).
'가정' 이 붙은 값은 시험으로 바꿔야 한다. 계산은 모두 손으로 따라갈 수 있는 닫힌 식 · 작은 상미분방정식.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .process import COLD_ROOM_C, BATH_C, fem_hours, process, thaw_hours
from .tissue import TissueRecipe

G = 9.81
R_GAS = 8.314
KB = 1.380649e-23
T_ROOM = 22.0
P_ATM = 101325.0
M_W = 0.018015


# ---------- 물성 ----------
def mu_water(t_c: float) -> float:
    """물 점도 Pa·s (Vogel, 0–100 °C 에서 2 % 안)."""
    return 2.414e-5 * 10 ** (247.8 / (t_c + 273.15 - 140))


def p_sat(t_c: float) -> float:
    """물 포화 증기압 Pa (Antoine, 1–100 °C)."""
    return 133.322 * 10 ** (8.07131 - 1730.63 / (233.426 + t_c))


def rho_vapor(t_c: float, rh: float = 1.0) -> float:
    return rh * p_sat(t_c) * M_W / (R_GAS * (t_c + 273.15))


def latent(t_c: float) -> float:
    return 2.501e6 - 2370 * t_c


def mu_pva(c_wt: float, t_c: float = 20.0, eta4_mpas: float = 28.0, ea: float = 25e3) -> float:
    """PVA 수용액 점도 Pa·s — 4 wt% 28 mPa·s (20 °C) 기준, 농도 · 온도 의존성은 가정 (모듈 설명)."""
    if c_wt <= 0:
        return mu_water(t_c)
    n = 4.0 if c_wt >= 4 else 2.0
    eta20 = eta4_mpas * (c_wt / 4) ** n * 1e-3
    return max(mu_water(t_c), eta20 * math.exp(ea / R_GAS * (1 / (t_c + 273.15) - 1 / 293.15)))


# ---------- 교반 (자석 막대) ----------
@dataclass(frozen=True)
class Stir:
    rpm: float
    bar_mm: float
    tank_mm: float  # 비커 안지름
    depth_mm: float  # 액체 깊이
    rho: float
    mu: float

    @property
    def re(self) -> float:
        return self.rho * (self.rpm / 60) * (self.bar_mm / 1000) ** 2 / self.mu

    @property
    def regime(self) -> str:
        return "층흐름" if self.re < 100 else ("천이" if self.re < 1e4 else "난류")

    def vortex_mm(self, kappa: float = 0.6) -> float:
        """소용돌이 깊이 Δh = (κ_eff ω R)² / g — 액체가 막대 속도의 κ 만큼 돎 (가정 0.6), 점성이 크면 줄어듦 (1 − e^(−Re/500))."""
        k = kappa * (1 - math.exp(-self.re / 500))
        w = 2 * math.pi * self.rpm / 60
        return (k * w * self.bar_mm / 2000) ** 2 / G * 1000

    def mix_s(self, po: float = 1.0) -> float:
        """섞이는 시간 (Grenville 상관식, 출력수 Po = 1 가정). 층흐름은 확산 · 접힘에 기대므로 inf."""
        n = self.rpm / 60
        r2 = (self.tank_mm / self.bar_mm) ** 2
        if self.re < 100:
            return math.inf
        if self.re < 6370 / po ** (1 / 3):
            return 34596 * po ** (-2 / 3) / self.re * r2 / n
        return 5.2 * po ** (-1 / 3) * r2 / n


# ---------- 열 ----------
def heat_curve(m_kg: float, t0: float, t_set: float, power_w: float, area_side: float, area_top: float, hours: float,
               cover_leak: float = 0.05, h_conv: float = 10.0, cp: float = 4000.0, dt: float = 5.0) -> dict:
    """가열 · 유지 · 증발: m c dT/dt = P(온도 제어) − h A (T − T∞) − L ṁ,  ṁ = f · h_m A_top (ρ_v(T) − ρ_v,∞).

    h_m = h / (ρ_air c_air Le^⅔) ≈ 0.010 m/s (자연대류 열-물질 상사). f = 호일 뚜껑으로 새는 몫 (가정)."""
    hm = h_conv / (1.16 * 1006 * 0.9)
    t, temp, m, out_t, out_T, out_m = 0.0, t0, m_kg, [], [], []
    t_reach = None
    while t <= hours * 3600:
        loss = h_conv * (area_side + area_top * (1 - cover_leak)) * (temp - T_ROOM)
        evap = cover_leak * hm * area_top * max(rho_vapor(temp) - rho_vapor(T_ROOM, 0.5), 0)
        need = loss + latent(temp) * evap
        p = power_w if temp < t_set else min(power_w, need)  # 설정 온도에 닿으면 손실만 메움
        temp += (p - need) * dt / (m * cp)
        m -= evap * dt
        if t_reach is None and temp >= t_set - 0.5:
            t_reach = t
        if int(t) % 60 == 0:
            out_t.append(t / 60), out_T.append(round(temp, 2)), out_m.append(round((m_kg - m) * 1000, 2))
        t += dt
    return {"reach_min": (t_reach or math.nan) / 60, "evap_g": (m_kg - m) * 1000, "t_min": out_t, "T": out_T, "lost_g": out_m}


def cool_curve(m_kg: float, t0: float, t_end: float, area: float, area_top: float, cover_leak: float = 0.05,
               h_conv: float = 12.0, cp: float = 4000.0, dt: float = 5.0) -> dict:
    """가열을 끄고 저으며 식힘 (뉴턴 냉각 + 증발)."""
    hm = h_conv / (1.16 * 1006 * 0.9)
    t, temp, m, ts, Ts = 0.0, t0, m_kg, [], []
    while temp > t_end and t < 6 * 3600:
        evap = cover_leak * hm * area_top * max(rho_vapor(temp) - rho_vapor(T_ROOM, 0.5), 0)
        temp -= (h_conv * area * (temp - T_ROOM) + latent(temp) * evap) * dt / (m * cp)
        m -= evap * dt
        if int(t) % 60 == 0:
            ts.append(t / 60), Ts.append(round(temp, 2))
        t += dt
    return {"min": t / 60, "evap_g": (m_kg - m) * 1000, "t_min": ts, "T": Ts}


# ---------- GO 응집 ----------
def go_aggregation(go_mg_ml: float, nacl_mm: float, pva_wt: float, mu: float, minutes: float = 30.0,
                   sheet_um2: float = 1.0, areal_mg_m2: float = 1.2, d_f: float = 1.8, w_stab: float = 1.0) -> dict:
    """스몰루호프스키 빠른 응집: t½ = 3 μ W / (4 kT n₀). 덩이 크기 a·N^(1/Df), 실효 밀도 Δρ (R/a)^(Df−3), 스토크스로 가라앉음.

    CCC = 44 mM × (1 + 0.15·PVA%) (printer.py 와 같은 가정). 염이 CCC 보다 묽으면 W 를 크게 (느린 응집)."""
    ccc = 44.0 * (1 + 0.15 * pva_wt)
    w = w_stab if nacl_mm >= ccc else w_stab * math.exp(3 * (ccc / max(nacl_mm, 1) - 1))
    m_sheet = sheet_um2 * 1e-12 * areal_mg_m2 * 1e-6  # kg
    n0 = go_mg_ml / m_sheet  # kg/m³ = mg/mL → 개수/m³
    kt = KB * (T_ROOM + 273.15)
    t_half = 3 * mu * w / (4 * kt * n0)
    a = math.sqrt(sheet_um2) / 2 * 1e-6
    ts = np.linspace(0, minutes * 60, 61)
    n_agg = 1 + ts / t_half
    r = a * n_agg ** (1 / d_f)
    drho = 800.0 * (r / a) ** (d_f - 3)  # GO(1800) − 물, 덩이 속 물로 묽어짐
    v = 2 / 9 * drho * G * r ** 2 / mu
    settled_mm = float(np.trapezoid(v, ts) * 1000)
    return {"ccc_mm": ccc, "aggregates": nacl_mm >= ccc, "t_half_s": t_half, "radius_um": float(r[-1] * 1e6),
            "settle_mm": settled_mm, "t_min": list(np.round(ts / 60, 1)), "r_um": list(np.round(r * 1e6, 2))}


# ---------- 단계 ----------
@dataclass
class StepPhys:
    id: str
    title: str
    engine: str  # 이 단계를 그리는 물리 엔진: mantaflow · bullet · fenicsx · 해석식
    items: list[tuple[str, str]]
    verdict: str
    ok: bool = True  # 레시피 시간 · 방법이 물리와 맞음
    series: dict = field(default_factory=dict)  # 웹 그림용 시간 곡선 {"x":…, "y":…, "xl":…, "yl":…}
    render: dict = field(default_factory=dict)  # Blender 장면 값 (점도 · 깊이 · 소용돌이 · 기포 …)

    def to_json(self) -> dict:
        return {"id": self.id, "title": self.title, "engine": self.engine, "items": self.items, "verdict": self.verdict,
                "ok": self.ok, "series": self.series, "render": self.render}


def _f(x: float, d: int = 1) -> str:
    return f"{x:,.{d}f}"


def bench_physics(rc: TissueRecipe | None = None) -> list[StepPhys]:
    rc = rc or TissueRecipe()
    steps = {s.id: s for s in process(rc)}
    bat = rc.battery()
    v = rc.bottle_ml
    pva_g = v * rc.pva_wt / 100
    c_stock = 100 * pva_g / rc.take_out_ml  # 15 wt%
    go_ml = v * rc.go_mg_ml / 4.0
    rest = v - rc.take_out_ml - go_ml
    mu_mix = mu_pva(rc.pva_wt, T_ROOM)
    rho_mix = 1005 + 2.7 * rc.pva_wt  # PVA 1 wt% 당 약 +2.7 kg/m³ (ρ_PVA 1270)
    bottle_d = bat.bottle.inner_diameter_mm
    H = bat.gel_height_mm
    out: list[StepPhys] = []

    def add(sid, engine, items, verdict, ok=True, series=None, render=None):
        out.append(StepPhys(sid, steps[sid].title, engine, items, verdict, ok, series or {}, render or {}))

    # 1. 냉각판 예냉: 알루미늄 판 300×300×10 mm + 냉각기 부동액 2 L, 냉각 능력 200 W (가정)
    c_plate = 2.43 * 900 + 2.0 * 3500
    leak = 8 * 0.09 * (COLD_ROOM_C - rc.plate_c) / 2
    t_chill = c_plate * (COLD_ROOM_C - rc.plate_c) / (200 - leak) / 60
    add("chill", "해석식", [("판 + 부동액 열용량", f"{c_plate / 1000:.1f} kJ/K"), ("저온실 → 판 새는 열 (평균)", f"{leak:.0f} W"),
                            ("냉각 능력 (가정)", "200 W"), ("−20 °C 까지", f"약 {t_chill:.0f} 분")],
        f"냉각기 부동액까지 식혀야 해서 약 {t_chill:.0f} 분 — 레시피 '30–60 분' 안 · 그동안 다음 단계 진행이 맞음.", t_chill < 60)

    # 2. 계량: 공기 부력 보정 (PVA 1.27 g/cm³ · 강철 분동 8.0)
    corr = pva_g * (1.2 / 1270 - 1.2 / 8000)
    add("weigh", "해석식", [("읽은 값", f"{pva_g:.2f} g"), ("공기 부력 보정", f"+{corr * 1000:.0f} mg"), ("허용", "±50 mg")],
        f"부력 보정 {corr * 1000:.0f} mg 는 허용 오차 50 mg 안 — 보정 없이 써도 됨.", corr < 0.05)

    # 3. 덜어 내기: 병목 Ø22 mm 로 꿀럭 흐름 (공기가 거꾸로 들어가며) — Q ≈ 0.25 √g d^(5/2) (꿀럭 흐름 근사), 눈금 읽기 (모세관 길이)
    q = 0.25 * math.sqrt(G) * 0.022 ** 2.5 * 1e6
    lc = math.sqrt(0.072 / (1005 * G)) * 1000
    add("take", "mantaflow", [("병목 꿀럭 흐름 Q ≈ 0.25√g d^2.5", f"약 {q:.0f} mL/s"), ("100 mL 붓기", f"{100 / q:.0f} s"),
                              ("메니스커스 높이 (모세관 길이)", f"{lc:.1f} mm"), ("100 mL 실린더 눈금", "±0.5 mL")],
        "메니스커스 아래 끝을 눈높이에서 읽음 — 모세관 길이 2.7 mm 라 비스듬히 보면 1 mL 넘게 틀림.",
        render={"rho": 1005, "mu": mu_water(T_ROOM), "sigma": 0.072, "pour_ml_s": q, "color": "saline"})

    # 4. PVA 분산: 100 mL 식염수, 250 mL 비커 (안 67 mm), 막대 25 mm, 300 rpm
    st4 = Stir(300, 25, 67, 100e3 / (math.pi * 33.5 ** 2), 1005, mu_water(T_ROOM))
    v_sink = 2 / 9 * (1270 - 1005) * G * (50e-6) ** 2 / mu_water(T_ROOM)
    add("disperse", "bullet", [("레이놀즈 수", f"{st4.re:,.0f} ({st4.regime})"), ("소용돌이 깊이", f"{st4.vortex_mm():.1f} mm"),
                               ("섞이는 시간", f"{st4.mix_s():.0f} s"), ("PVA 알갱이 (Ø100 µm) 가라앉는 속도", f"{v_sink * 1000:.1f} mm/s")],
        "찬 물에서 PVA 는 녹지 않고 젖기만 함 — 소용돌이(약 {:.0f} mm)로 끌려 들어가게 가장자리에 조금씩. 한 번에 부으면 겉만 젖은 덩이(피시아이).".format(st4.vortex_mm()),
        render={"rho": 1005, "mu": mu_water(T_ROOM), "vortex_mm": st4.vortex_mm(), "particles": 400, "particle_um": 100,
                "sink_mm_s": v_sink * 1000, "rpm": 300, "color": "saline"})

    # 5. PVA 용해 (90 °C, 2 h, 호일 덮음): 핫플레이트 유효 150 W (가정)
    m5 = (rc.take_out_ml * 1.005 + pva_g) / 1000
    a_side, a_top = math.pi * 0.067 * 0.035, math.pi * 0.0335 ** 2
    hc = heat_curve(m5, T_ROOM, 90.0, 150.0, a_side, a_top, 2.0)
    mu90 = mu_pva(c_stock, 90.0)
    st5 = Stir(300, 25, 67, 35, 1050, mu90)
    add("stock", "해석식", [("90 °C 까지", f"{hc['reach_min']:.1f} 분"), ("15 % PVA 점도 90 °C / 20 °C", f"{mu90 * 1000:,.0f} / {mu_pva(c_stock) * 1000:,.0f} mPa·s"),
                            ("교반 레이놀즈 수", f"{st5.re:.0f} ({st5.regime} — 소용돌이 없음)"), ("2 h 증발 (호일 새는 몫 5 %, 가정)", f"{hc['evap_g']:.1f} g")],
        f"90 °C 에서도 {mu90 * 1000:,.0f} mPa·s 라 층흐름 — 막대가 겉돌 수 있어 속도를 올리기보다 시간이 녹임. 증발 약 {hc['evap_g']:.0f} g → 다음 단계에서 보충.",
        series={"x": hc["t_min"], "y": hc["T"], "xl": "분", "yl": "°C"},
        render={"mu": mu90, "rho": 1050, "steam": True, "T": 90})

    # 6. 증발 보정 · 식히기
    m6 = m5 - hc["evap_g"] / 1000
    cc = cool_curve(m6, 90.0, 40.0, a_side + a_top, a_top)
    add("cool", "해석식", [("보충할 증류수", f"{hc['evap_g']:.1f} g"), ("40 °C 까지 (뉴턴 냉각 + 증발)", f"{cc['min']:.0f} 분"),
                           ("식는 동안 더 증발", f"{cc['evap_g']:.2f} g"), ("40 °C 점도", f"{mu_pva(c_stock, 40) * 1000:,.0f} mPa·s")],
        (f"식는 데 약 {cc['min']:.0f} 분 — 레시피 {steps['cool'].hours * 60:.0f} 분과 맞음." if abs(cc["min"] - steps["cool"].hours * 60) < 20 else
         f"공기로 식히면 약 {cc['min']:.0f} 분 — 레시피 {steps['cool'].hours * 60:.0f} 분보다 김. 비커를 찬물 그릇에 담그면 몇 분.") +
        f" 보충은 뜨거울 때 (식으며 더 줄어드는 양은 {cc['evap_g']:.1f} g 뿐).",
        abs(cc["min"] - steps["cool"].hours * 60) < 20, series={"x": cc["t_min"], "y": cc["T"], "xl": "분", "yl": "°C"})

    # 7. 예비 시험: 식염수 + PVA 원액(식염수로 만듦) + GO(물) — 염 농도
    s = 1 / 25
    v_sal, v_pva, v_go = rest * s, rc.take_out_ml * s, go_ml * s
    nacl = 154 * (v_sal + v_pva) / (v_sal + v_pva + v_go)
    pva7 = c_stock * v_pva / (v_sal + v_pva + v_go)
    ag = go_aggregation(rc.go_mg_ml, nacl, pva7, mu_pva(pva7))
    add("pretest", "해석식", [("섞인 염", f"{nacl:.0f} mM (CCC {ag['ccc_mm']:.0f} mM)"), ("응집 반감기 (스몰루호프스키)", f"{ag['t_half_s']:.0f} s"),
                              ("30 분 뒤 덩이 지름", f"{2 * ag['radius_um']:.0f} µm"), ("30 분 가라앉음", f"{ag['settle_mm']:.2f} mm")],
        ("염이 CCC 보다 진해 몇 초 만에 응집 시작 — 30 분이면 덩이가 눈에 보이는 크기. 계산은 '중단' 쪽: PVA 가 GO 를 감싸 늦추는지(W > 1) 이 시험으로 확인."
         if ag["aggregates"] else "염이 CCC 보다 묽어 느린 응집 — 고른 갈색 예상."),
        not ag["aggregates"], series={"x": ag["t_min"], "y": ag["r_um"], "xl": "분", "yl": "덩이 반지름 µm"},
        render={"aggregate_um": 2 * ag["radius_um"], "settle_mm": ag["settle_mm"]})

    # 8. 비커에서 섞기: 1 L 비커 (안 105 mm), 막대 40 mm, 500 mL
    depth8 = v * 1e3 / (math.pi * 52.5 ** 2)
    st8 = Stir(300, 40, 105, depth8, rho_mix, mu_mix)
    da = st8.mix_s() / ag["t_half_s"] if math.isfinite(st8.mix_s()) else math.inf
    add("mix", "mantaflow", [("섞인 점도 (PVA {:.0f} %)".format(rc.pva_wt), f"{mu_mix * 1000:.0f} mPa·s"), ("레이놀즈 수", f"{st8.re:,.0f} ({st8.regime})"),
                             ("소용돌이 깊이", f"{st8.vortex_mm():.1f} mm"), ("섞이는 시간", f"{st8.mix_s():.0f} s"),
                             ("담쾰러 수 (섞임 / 응집)", f"{da:.0f}")],
        f"섞이는 데 {st8.mix_s():.0f} s 인데 응집은 {ag['t_half_s']:.0f} s — GO 가 넣는 자리에서 먼저 엉김 (Da {da:.0f} ≫ 1). 가늘게 · 소용돌이 벽 쪽으로 넣을 것.",
        da < 1, render={"rho": rho_mix, "mu": mu_mix, "vortex_mm": st8.vortex_mm(), "rpm": 300, "depth_mm": depth8, "color": "go_mix"})

    # 9. 기포 빼기: 진공 5 kPa (가정), 기포 0.15 · 0.05 mm
    pv = 5e3
    grow = (P_ATM / pv) ** (1 / 3)
    rise = {r0: 2 / 9 * rho_mix * G * (r0 * grow * 1e-3) ** 2 / mu_mix for r0 in (0.15, 0.05)}
    boil = p_sat(T_ROOM)
    add("degas", "mantaflow", [("감압 5 kPa 에서 기포 부피", f"×{grow ** 3:.0f} (반지름 ×{grow:.1f})"),
                               ("떠오름 Ø0.3 / Ø0.1 mm (스토크스)", f"{rise[0.15] * 1000:.1f} / {rise[0.05] * 1000:.2f} mm/s"),
                               ("액면까지 (깊이 {:.0f} mm)".format(depth8), f"{depth8 / (rise[0.05] * 1000):.0f} s"),
                               ("끓는 압력 (22 °C 물)", f"{boil / 1000:.1f} kPa")],
        f"5 kPa 면 기포가 커져 수십 초 안에 빠짐 · {boil / 1000:.1f} kPa 아래로 내리면 물이 끓음 — 15 분은 넉넉, 펌프 하한을 3 kPa 위로.",
        render={"bubble_r_mm": [0.15 * grow, 0.05 * grow], "rise_mm_s": [rise[0.15] * 1000, rise[0.05] * 1000], "mu": mu_mix,
                "depth_mm": depth8, "color": "go_mix"})

    # 10. 병에 담기: 벽을 타는 액막 (누셀트), 물결 없는 한계 Re_film < 30
    per = math.pi * bottle_d / 1000
    q_max = 30 * mu_mix * per / 4 / rho_mix
    gam = q_max * rho_mix / per
    delta = (3 * mu_mix * gam / (rho_mix ** 2 * G)) ** (1 / 3)
    add("refill", "mantaflow", [("물결 없는 최대 유량 (Re_막 < 30)", f"{q_max * 1e6:.0f} mL/s"), ("그때 액막 두께", f"{delta * 1000:.2f} mm"),
                                ("500 mL 최소 시간", f"{v / (q_max * 1e6):.0f} s")],
        f"{q_max * 1e6:.0f} mL/s 아래로 벽을 타면 공기를 말아 넣지 않음 — 500 mL 에 {v / (q_max * 1e6):.0f} s 이상.",
        render={"pour_ml_s": q_max * 1e6, "mu": mu_mix, "rho": rho_mix, "color": "go_mix"})

    # 11. 동결 세팅: 판–병 바닥 접촉 (틈 0.2 mm) — 공기 vs 30 % 에탄올
    h_air, h_eth, h_pet = 0.024 / 2e-4, 0.45 / 2e-4, 0.15 / 3e-4
    u_air, u_eth = 1 / (1 / h_air + 1 / h_pet), 1 / (1 / h_eth + 1 / h_pet)
    add("setup", "해석식", [("공기 틈 0.2 mm", f"{h_air:.0f} W/m²K"), ("접촉액 0.2 mm", f"{h_eth:,.0f} W/m²K"), ("PET 바닥 0.3 mm", f"{h_pet:.0f} W/m²K"),
                            ("바닥 전체 (공기 → 접촉액)", f"{u_air:.0f} → {u_eth:.0f} W/m²K (×{u_eth / u_air:.1f})")],
        f"접촉액이 바닥 열전달을 {u_eth / u_air:.1f} 배 — 바닥으로만 빠르게 얼려 방향성을 지킴. 병 바닥이 오목하면 그 틈이 공기로 남음.")

    # 12–14. 동결 · 해동: FEniCSx
    fem = fem_hours()
    fz, th = fem if fem else (steps["dfreeze"].hours, steps["thaw"].hours)
    zs, ts = _fem_front()
    vf = np.diff(zs) / np.maximum(np.diff(np.array(ts) * 3600), 1e-9) * 1e3 if len(zs) > 2 else np.array([math.nan])  # µm/s
    i_min = int(np.argmin(vf)) if len(zs) > 2 else 0
    add("dfreeze", "fenicsx", [("다 어는 시간 (FEniCSx 축대칭)", f"{fz:.1f} h"),
                               ("전선 속도 바닥 · 가운데", f"{vf[0]:.1f} · {vf[len(vf) // 2]:.1f} µm/s"),
                               ("가장 느린 곳", f"{vf[i_min]:.2f} µm/s (높이 {zs[i_min]:.0f} mm)" if len(zs) > 2 else "—"),
                               ("얼며 늘어나는 부피", "9 % (액면이 어깨 아래여야)")],
        f"아래에서 위로만 얾 (옆이 앞서지 않음 — FEniCSx 옆 앞섬 0). 전선은 바닥 {vf[0]:.0f} µm/s 에서 위로 갈수록 느려져 "
        f"높이 {zs[i_min]:.0f} mm 에서 {vf[i_min]:.1f} µm/s — 세포가 위로 갈수록 넓어짐. 마지막 몇 mm 는 윗면 쪽에서도 얼어 빨리 닫힘.",
        series={"x": list(np.round(ts, 2)), "y": list(np.round(zs, 1)), "xl": "h", "yl": "얼음 전선 mm"},
        render={"front_t_h": list(np.round(ts, 3)), "front_mm": list(np.round(zs, 2)), "height_mm": H, "show_at_h": fz * 0.6})
    th_an = thaw_hours(bottle_d / 2)
    add("thaw", "fenicsx", [("FEniCSx (25 °C 수조)", f"{th:.2f} h"), ("스테판 원통 해석식 (옆면만)", f"{th_an:.2f} h"),
                            ("공기 4 °C 였다면", f"약 {thaw_hours(bottle_d / 2, COLD_ROOM_C):.0f} h")],
        f"수조라서 {th:.1f} h — 같은 일을 4 °C 공기로 하면 하루가 넘음 (레시피를 수조로 바꾼 이유).")
    n = rc.freeze_thaw
    e_n = [0.35 * rc.pva_wt ** 2 * k ** 0.5 for k in range(1, n + 1)]
    add("ft", "fenicsx", [("회차마다 (동결 + 해동)", f"{fz + th:.1f} h"), ("겔 탄성률 1 → {} 회 (가정)".format(n), " → ".join(f"{e:.1f}" for e in e_n) + " kPa")],
        "동결-해동을 거듭할수록 PVA 미결정이 늘어 단단해짐 (탄성률 ∝ √n, 가정).", series={"x": list(range(1, n + 1)), "y": e_n, "xl": "회", "yl": "kPa"})

    # 15. 꺼내기: 제 무게로 처짐
    e_gel = e_n[-1] * 1e3
    sig = rho_mix * G * H / 1000
    strain_base = sig / e_gel
    sag_mm = H * strain_base / 2
    add("demold", "bullet", [("바닥 응력 ρgH", f"{sig / 1000:.2f} kPa"), ("겔 탄성률 (PVA {:.0f} %, {}회)".format(rc.pva_wt, n), f"{e_gel / 1000:.1f} kPa"),
                             ("바닥 변형 · 키 줄어듦", f"{100 * strain_base:.0f} % · {sag_mm:.0f} mm"), ("바닥 부풂 (푸아송 0.5)", f"{50 * strain_base:.0f} %")],
        f"PVA {rc.pva_wt:.0f} % 겔은 무르게 계산됨 — 세워 두면 키가 약 {sag_mm:.0f} mm 줄고 바닥이 부풂. 받침에 눕히지 말고 병째 잘라 받친 채로, 바로 재기.",
        strain_base < 0.1, render={"strain": strain_base, "height_mm": H, "diam_mm": bottle_d})

    # 16. 윗면–아랫면 전압: 꺼낸 직후 온도 차 → 열전위
    alpha = 0.6 / (1050 * 3900)
    tau = (bottle_d / 2000) ** 2 / (5.78 * alpha) / 60
    add("meas", "해석식", [("겔 온도 고르게 되는 시간 (원통 첫 모드)", f"{tau:.0f} 분"), ("염수 열전위 (가정)", "약 0.2 mV/K"),
                           ("윗·아랫면 0.5 K 차이면", "≈ 0.1 mV 거짓 신호")],
        f"꺼낸 뒤 겔 온도가 고르게 되는 데 약 {tau:.0f} 분 — 10 분 안에 재면 온도 차가 0.1 mV 급 거짓 전압을 만듦. 정 · 역 측정 + 양면 온도를 함께 적을 것.",
        tau < 10)

    # 17. 액체질소 급속 고정: 2 mm 조각, 막비등 h ≈ 150 W/m²K
    vol_a = 2e-3 / 6
    tau17 = 1000 * 2000 * vol_a / 150
    t150 = tau17 * math.log((0 + 196) / (-150 + 196))
    add("section", "해석식", [("라이덴프로스트 막비등 h", "≈ 150 W/m²K"), ("−150 °C 까지", f"{t150:.0f} s"),
                              ("식는 빠르기", f"≈ {150 / t150:.0f} K/s")],
        f"10 초 담그면 {t150:.0f} s 안에 다 얼어 얼음 결정 µm 급 — 170 µm 세포와 소금 분포를 그대로 잡음.", t150 < 10)

    # 18. 동결건조: 2 mm 조각, 마른 층 k 0.03 W/mK, 선반 ΔT 20 K
    t18 = 917 * 2.84e6 * 0.97 * (1e-3) ** 2 / (2 * 0.03 * 20) / 3600
    add("lyo", "해석식", [("승화 (마른 층 열전도 한계, 양면)", f"약 {t18:.1f} h"), ("레시피", f"{steps['lyo'].hours:.0f} h")],
        f"2 mm 조각은 열 · 수증기 저항을 넉넉히 잡아도 몇 시간 — 24 h 는 충분.")

    # 19. SEM-EDS: 전자 침투 깊이 (Kanaya–Okayama), 마른 겔 밀도 0.2 g/cm³
    def ko(kv):
        return 0.0276 * 12 * kv ** 1.67 / (6 ** 0.89 * 0.2)
    add("cond", "해석식", [("전자 퍼짐 15 kV (마른 겔 0.2 g/cm³)", f"{ko(15):.0f} µm"), ("5 kV", f"{ko(5):.1f} µm"), ("세포 폭", "≈ 170 µm")],
        f"15 kV 면 신호가 {ko(15):.0f} µm 로 퍼져 얇은 벽과 칸이 섞임 — 5–10 kV 로 벽/칸 Cl 비를 잴 것.", ko(15) < 17)
    return out


def _fem_front() -> tuple[list[float], list[float]]:
    """FEniCSx 가운데 기둥: 높이 z 를 얼음 전선이 지난 시각 → (z mm, t h) 를 시간 순으로."""
    from .process import FEM
    import json

    try:
        c = json.loads(FEM.read_text(encoding="utf-8"))["cases"][0]
        g = c["grid"]
        return [float(z) for z in g["z_mm"]], [float(row[0]) for row in g["t_h"]]
    except (OSError, KeyError, ValueError, IndexError):
        return [], []


def describe(rc: TissueRecipe | None = None) -> str:
    lines = ["[실험대 19단계 — 현실 물리]"]
    for k, s in enumerate(bench_physics(rc), 1):
        lines.append(f"  {k:>2}. {s.title} ({s.engine}) {'✔' if s.ok else '⚠'} " + " · ".join(f"{a} {b}" for a, b in s.items))
        lines.append(f"      → {s.verdict}")
    return "\n".join(lines)
