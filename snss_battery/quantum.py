"""SNSS-QB 양자 모듈 — 금속 무함유 유기 미세공진기 Dicke 형 양자 배터리 (명세: spec/QUANTUM.md).

생리식염수 결정 배터리 자체는 양자 배터리가 아니다 (상온 물속 이온 → 결맞음 ≈ fs).
이 모듈은 별도의 광학 양자 배터리로, 분자 N 개가 '함께' 충전될 때 충전 시간이 N 이 커질수록 짧아지는
집단(초흡수) 이점을 계산한다. 계산은 Rust(rust/src/quantum.rs) · C#(Snss.Lab/Quantum.cs) 와 같은 RK4 로 맞춘다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

N_LIST = (1, 2, 4, 8, 16, 32, 64, 128)

HBAR = 1.054571817e-34
PLANCK = 6.62607015e-34
C_LIGHT = 2.99792458e8
EV = 1.602176634e-19
AVOGADRO = 6.02214076e23


@dataclass
class ChargeResult:
    n: int
    steps: int
    tau: float  # 1/g 단위
    energy: float  # ħω 단위 (최대 N)
    ergotropy: float
    power: float
    advantage: float  # 병렬형 대비 평균 전력 비


def charge(n: int) -> ChargeResult:
    """Tavis–Cummings 충전: 광자 N 개 → 분자 N 개 (spec §1–2)."""
    off = [(n - k) * math.sqrt(k + 1) for k in range(n)]  # H[k,k+1]
    norm = max((off[k - 1] if k > 0 else 0.0) + (off[k] if k < n else 0.0) for k in range(n + 1))
    dt = 0.02 / norm
    re = [0.0] * (n + 1)
    im = [0.0] * (n + 1)
    re[0] = 1.0

    def deriv(r, i):
        # dc/dt = -i H c  →  d(re)/dt = H·im, d(im)/dt = -H·re
        dr, di = [0.0] * (n + 1), [0.0] * (n + 1)
        for k in range(n + 1):
            hr = hi = 0.0
            if k > 0:
                hr += off[k - 1] * r[k - 1]
                hi += off[k - 1] * i[k - 1]
            if k < n:
                hr += off[k] * r[k + 1]
                hi += off[k] * i[k + 1]
            dr[k] = hi
            di[k] = -hr
        return dr, di

    def energy(r, i):
        return sum(k * (r[k] * r[k] + i[k] * i[k]) for k in range(n + 1))

    prev = energy(re, im)
    step = 0
    while True:
        k1r, k1i = deriv(re, im)
        k2r, k2i = deriv([re[k] + 0.5 * dt * k1r[k] for k in range(n + 1)], [im[k] + 0.5 * dt * k1i[k] for k in range(n + 1)])
        k3r, k3i = deriv([re[k] + 0.5 * dt * k2r[k] for k in range(n + 1)], [im[k] + 0.5 * dt * k2i[k] for k in range(n + 1)])
        k4r, k4i = deriv([re[k] + dt * k3r[k] for k in range(n + 1)], [im[k] + dt * k3i[k] for k in range(n + 1)])
        new_re = [re[k] + dt / 6 * (k1r[k] + 2 * k2r[k] + 2 * k3r[k] + k4r[k]) for k in range(n + 1)]
        new_im = [im[k] + dt / 6 * (k1i[k] + 2 * k2i[k] + 2 * k3i[k] + k4i[k]) for k in range(n + 1)]
        e_new = energy(new_re, new_im)
        if e_new < prev and step > 0:
            break
        re, im, prev = new_re, new_im, e_new
        step += 1
    tau = step * dt
    p = [re[k] * re[k] + im[k] * im[k] for k in range(n + 1)]
    w = prev - (1.0 - max(p))
    power = prev / tau
    p_par = n / (math.pi / 2)
    return ChargeResult(n, step, tau, prev, w, power, power / p_par)


def scaling(n_list=N_LIST) -> tuple[list[ChargeResult], float]:
    rows = [charge(n) for n in n_list]
    xs = [math.log(r.n) for r in rows]
    ys = [math.log(r.tau) for r in rows]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return rows, -slope


# ---------- 실제 소자 ----------
@dataclass
class QuantumModule:
    rabi_ev: float = 0.10  # 측정 집단 라비 분열
    t2_fs: float = 50.0  # 분자 위상 이완
    q_factor: float = 150.0
    wavelength_nm: float = 590.0
    dye_wt: float = 1.0
    dye_mw: float = 1080.0
    active_diameter_mm: float = 24.0
    excited_lifetime_ns: float = 4.0
    layers: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.layers:
            self.layers = module_layers(self.wavelength_nm)

    @property
    def active_thickness_mm(self) -> float:
        return next(t for name, mat, d, t in self.layers if name == "활성층")

    @property
    def n_molecules(self) -> float:
        vol_cm3 = math.pi * (self.active_diameter_mm / 20) ** 2 * self.active_thickness_mm / 10
        return vol_cm3 * 1.18 * self.dye_wt / 100 / self.dye_mw * AVOGADRO

    @property
    def max_energy_j(self) -> float:
        return self.n_molecules * PLANCK * C_LIGHT / (self.wavelength_nm * 1e-9)

    def real_time_fs(self, tau_sqrt_n: float) -> float:
        omega_r = self.rabi_ev * EV / HBAR
        return tau_sqrt_n / (omega_r / 2) * 1e15

    @property
    def cavity_lifetime_fs(self) -> float:
        omega = 2 * math.pi * C_LIGHT / (self.wavelength_nm * 1e-9)
        return self.q_factor / omega * 1e15

    def report(self) -> dict:
        rows, a = scaling()
        tau_sqrt_n = rows[-1].tau * math.sqrt(rows[-1].n)
        t_fs = self.real_time_fs(tau_sqrt_n)
        quantum_ok = t_fs < self.t2_fs and t_fs < self.cavity_lifetime_fs
        return {"rows": rows, "exponent": a, "tau_sqrt_n": tau_sqrt_n, "charge_fs": t_fs,
                "t2_fs": self.t2_fs, "cavity_fs": self.cavity_lifetime_fs, "quantum_ok": quantum_ok,
                "n_molecules": self.n_molecules, "max_energy_j": self.max_energy_j,
                "lifetime_ns": self.excited_lifetime_ns}

    def describe(self) -> str:
        r = self.report()
        lines = ["[SNSS-QB 양자 모듈 — 유기 미세공진기 Dicke 형]",
                 "  N  | 충전시간 τ(1/g) | 저장 E/N | 에르고트로피/N | 병렬 대비 전력 Γ"]
        for x in r["rows"]:
            lines.append(f"  {x.n:<3}| {x.tau:14.5f} | {x.energy / x.n:8.4f} | {x.ergotropy / x.n:13.4f} | {x.advantage:8.3f}")
        lines += [
            f"  충전 시간 ∝ N^-{r['exponent']:.3f}  (집단 이점: 분자가 많을수록 더 빨리 충전)",
            f"  실제 소자 (ħΩ_R = {self.rabi_ev} eV): 충전 약 {r['charge_fs']:.1f} fs · 분자 위상 이완 {r['t2_fs']:.0f} fs · "
            f"광자 수명 {r['cavity_fs']:.1f} fs → {'양자 이점 유효' if r['quantum_ok'] else '결맞음이 먼저 깨짐 — 고전 충전과 구별 불가'}",
            f"  색소 분자 약 {r['n_molecules']:.2e} 개, 최대 저장 {r['max_energy_j'] * 1e3:.3f} mJ, 저장 수명 약 {r['lifetime_ns']:g} ns",
            "  → 전구를 켜기에는 저장 시간이 너무 짧음 (빛으로 매우 빨리 충전·방출하는 장치)",
        ]
        return "\n".join(lines)


def module_layers(wavelength_nm: float = 590.0, pairs: int = 8) -> list[tuple[str, str, float, float]]:
    """(이름, 재질, 지름 mm, 두께 mm) — 아래에서 위로 (spec §4)."""
    t_sio2 = wavelength_nm / (4 * 1.46) * 1e-6
    t_sin = wavelength_nm / (4 * 2.00) * 1e-6
    t_act = wavelength_nm / (2 * 1.49) * 1e-6
    out = [("기판", "용융 실리카 SiO2", 25.0, 1.0)]
    for k in range(pairs):
        out += [(f"아래 거울 SiO2 {k + 1}", "SiO2", 24.0, t_sio2), (f"아래 거울 Si3N4 {k + 1}", "Si3N4", 24.0, t_sin)]
    out.append(("활성층", "PMMA + 페릴렌 다이이미드 색소 1 wt%", 24.0, t_act))
    for k in range(pairs):
        out += [(f"위 거울 Si3N4 {k + 1}", "Si3N4", 24.0, t_sin), (f"위 거울 SiO2 {k + 1}", "SiO2", 24.0, t_sio2)]
    out.append(("덮개", "용융 실리카 SiO2", 25.0, 0.5))
    return out


MODULE_ELEMENTS = {
    "용융 실리카 SiO2": frozenset({"Si", "O"}), "SiO2": frozenset({"Si", "O"}), "Si3N4": frozenset({"Si", "N"}),
    "PMMA + 페릴렌 다이이미드 색소 1 wt%": frozenset({"C", "H", "N", "O"}),
}


def analytic_volume_mm3(layers=None) -> float:
    layers = layers or module_layers()
    return sum(math.pi * (d / 2) ** 2 * t for _, _, d, t in layers)
