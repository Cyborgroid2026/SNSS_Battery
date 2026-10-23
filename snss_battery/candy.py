"""SC-3 영점 막대 — 패드 없이, 영점 좌표 막대 위에 결정(존재)이 생성됨 (명세: spec/CANDY.md).

멸균생리식염수(154 mM > CCC)가 가득한 수조 안에 위에서 **영점 막대**을 꽂고, 막대가 돌면서(θ) 주사 팔(r · z)의
GO · PVA 주사기가 잉크를 넣는다. 잉크는 배지에 닿자마자 염으로 엉기고(SC-1 과 같은 물리), 405 nm 빛(전자기파)이
세포질을 광환원. 쌓는 순서는 **영점에서 가까운 칸부터** — 솜사탕이 막대에 감겨 자라는 모습처럼, 영점에서 껍질이 바깥으로 두꺼워진다 (솜사탕은 모습만 빌린 비유). 다 자라면 막대째 뽑는다.

모터는 모두 수조 위 다리(물 밖)에 — 물에 잠기는 것은 막대 · 팔 · 주사 끝 (PETG · 탄소섬유 · PEEK · 흑연)뿐.
과정(Process)은 단계(껍질 묶음)의 목록이라 **반복**(repeat) · **수정**(edit) 할 수 있고, 그대로 SD 로 구워진다 (sdcard.py).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np

from .sculpt import MEM, NEG, POS, design


@dataclass(frozen=True)
class Stick:
    """영점 막대 — 위 다리에서 아래로. 끝이 영점, 그 둘레에 존재가 붙어 자람. 막대째 뽑아 꺼냄."""

    diameter_mm: float = 6.0  # PETG 관 + 흑연 심 두 줄 (+ · −, 실리콘으로 갈라 둠)
    leads: str = "연필심 Ø2 두 줄 (+ 한쪽 · − 반대쪽, 끝 12 mm 만 드러남) — 존재의 단자"
    zero_mm: tuple[float, float, float] = (0.0, 0.0, 34.0)  # 존재 좌표의 영점 (몸통 가운데) — 막대는 머리 위로 빠짐
    rpm_max: float = 6.0


@dataclass(frozen=True)
class Syringes:
    """주사기 넷 (물 밖 펌프 → 실리콘 관 → 팔 끝 혼합 노즐): GO 세 통(p · n · 막) + PVA. 염은 배지가 줌."""

    go_mg_ml: float = 10.0
    pva_wt: float = 10.0
    ratio: dict = field(default_factory=lambda: {POS: (0.83, 0.17), NEG: (0.83, 0.17), MEM: (0.73, 0.27)})  # GO : PVA
    nozzle_mm: float = 0.41  # PEEK
    speed_mm_s: float = 8.0
    light_nm: float = 405.0  # 노즐 옆 빛 — 세포질만 켬 (막은 끔)


@dataclass(frozen=True)
class CandySpec:
    name: str = "SC-3 영점 막대 — 결정이 영점 좌표 막대 위에서 생성"
    tank_inner_mm: tuple[float, float, float] = (350.0, 350.0, 350.0)
    fill_mm: float = 330.0
    work_center_z: float = 170.0  # 수조 안에서 영점 높이 (가운데쯤 — 사방이 비어 자람)
    bridge_z: float = 380.0  # 수조 위 다리 (모터 · 막대 회전 · 팔 레일, 물 밖)
    bridge_hole_mm: float = 120.0  # 다리 가운데 구멍 — 막대를 빼면 존재가 이 구멍으로 올라옴
    stick: Stick = field(default_factory=Stick)
    syringes: Syringes = field(default_factory=Syringes)
    shell_mm: float = 0.41  # 껍질 두께 = 선폭
    layer_mm: float = 0.32
    shells_per_step: int = 8  # 과정 한 단계 = 껍질 8개 (≈ 3.3 mm) — 반복 · 수정 단위

    @property
    def zero_tank(self) -> tuple[float, float, float]:
        """수조 좌표의 영점 (막대 끝)."""
        return (0.0, 0.0, self.work_center_z)


MAT_NAME = {POS: "p 세포질", NEG: "n 세포질", MEM: "막 · 피부"}


# ---------- 계획: 영점부터 껍질 순서 ----------
def plan(shape: str = "being", height_mm: float = 0.0, spec: CandySpec | None = None, name: str = "") -> dict:
    """설계(sculpt.design 의 칸 · 세포 · 재료)를 영점 거리 순서의 껍질과 단계로."""
    spec = spec or CandySpec()
    piece = design(shape, height_mm, name=name or Path(shape).stem)
    px, pz = piece.pitch
    ox, oy = piece.offset
    I, J, K = np.nonzero(piece.material != 0)
    x = (ox + I + 0.5) * px
    y = (oy + J + 0.5) * px
    z = (K + 0.5) * pz
    zx, zy, zz = spec.stick.zero_mm
    zz = min(zz, float(z.max()) * 0.5)  # 낮은 모양은 가운데 높이로
    d = np.sqrt((x - zx) ** 2 + (y - zy) ** 2 + (z - zz) ** 2)
    stick = (np.hypot(x - zx, y - zy) < spec.stick.diameter_mm / 2) & (z > zz)  # 막대 자리 (머리 위로 빠지는 길) — 비워 둠
    keep = ~stick
    mat = piece.material[I, J, K][keep]
    d, x, y, z = d[keep], x[keep], y[keep], z[keep]
    shell = np.floor(d / spec.shell_mm).astype(int)
    order = np.lexsort((np.arctan2(y - zy, x - zx), z, shell))  # 껍질 → 높이 → 각도 (막대가 도는 방향)
    vox_mm3 = px * px * pz
    flow = spec.syringes.nozzle_mm * spec.layer_mm * spec.syringes.speed_mm_s  # mm³/s
    n_shell = int(shell.max()) + 1
    per_shell = np.bincount(shell, minlength=n_shell)
    mats = np.zeros((n_shell, 4), int)
    np.add.at(mats, (shell, mat), 1)
    steps = []
    for k0 in range(0, n_shell, spec.shells_per_step):
        k1 = min(n_shell, k0 + spec.shells_per_step)
        n = int(per_shell[k0:k1].sum())
        if n == 0:
            continue
        m = mats[k0:k1].sum(0)
        steps.append({"i": len(steps), "shells": [k0, k1], "r_mm": [round(k0 * spec.shell_mm, 2), round(k1 * spec.shell_mm, 2)],
                      "voxels": n, "volume_mm3": round(n * vox_mm3, 2), "seconds": round(n * vox_mm3 / flow, 1),
                      "materials": {MAT_NAME[c]: int(m[c]) for c in (POS, NEG, MEM)}, "repeat": 1, "flow": 1.0, "skip": False,
                      "note": ""})
    return {"spec": spec, "piece": piece, "zero_mm": (zx, zy, zz), "order": order, "shell": shell[order], "mat": mat[order],
            "xyz": np.stack([x, y, z], 1)[order], "steps": steps, "flow_mm3_s": flow, "vox_mm3": vox_mm3}


# ---------- 과정: 반복 · 수정 ----------
@dataclass
class Process:
    """단계 목록 — 반복 · 건너뛰기 · 흐름 배율 · 메모. JSON 으로 남고 SD 로 구워짐. 고친 기록(edits)도 함께."""

    name: str
    steps: list[dict]
    edits: list[dict] = field(default_factory=list)

    @classmethod
    def from_plan(cls, pl: dict, name: str) -> "Process":
        return cls(name, [dict(s) for s in pl["steps"]])

    def edit(self, i: int, **kw) -> "Process":
        """kw: repeat (덧쌓기 횟수) · flow (흐름 배율 0.3–2) · skip · note."""
        s = self.steps[i]
        for k, v in kw.items():
            if k not in ("repeat", "flow", "skip", "note"):
                raise ValueError(f"고칠 수 없는 항목: {k}")
            if k == "repeat":
                v = max(1, int(v))
            if k == "flow":
                v = min(2.0, max(0.3, float(v)))
            self.edits.append({"step": i, "key": k, "from": s[k], "to": v})
            s[k] = v
        return self

    def timeline(self) -> list[dict]:
        """실제로 도는 순서 (반복 펼침) — 단계마다 시작 · 끝 시각."""
        t, out = 0.0, []
        for s in self.steps:
            if s["skip"]:
                continue
            for r in range(s["repeat"]):
                dt = s["seconds"] / s["flow"]
                out.append({"step": s["i"], "pass": r + 1, "t0": round(t, 1), "t1": round(t + dt, 1), "r_mm": s["r_mm"], "flow": s["flow"]})
                t += dt
        return out

    def total_s(self) -> float:
        tl = self.timeline()
        return tl[-1]["t1"] if tl else 0.0

    def to_json(self) -> dict:
        return {"name": self.name, "steps": self.steps, "edits": self.edits, "timeline": self.timeline(), "total_s": self.total_s()}

    @classmethod
    def load(cls, f: str | Path) -> "Process":
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        return cls(d["name"], d["steps"], d.get("edits", []))

    def save(self, f: str | Path) -> Path:
        f = Path(f)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
        return f


def state_at(pl: dict, proc: Process, t: float) -> dict:
    """시뮬레이션: 시각 t 에 자란 정도 — 몇 번째 단계, 영점에서 반지름, 쌓인 칸 수 (재생 · 모니터용)."""
    done, cur = 0, None
    for seg in proc.timeline():
        if t >= seg["t1"]:
            continue
        cur = seg
        break
    steps = {s["i"]: s for s in proc.steps}
    for seg in proc.timeline():
        if seg["t1"] <= t and seg["pass"] == 1:
            done += steps[seg["step"]]["voxels"]
    if cur is None:
        return {"t": t, "step": None, "radius_mm": float(pl["shell"][-1] + 1) * pl["spec"].shell_mm, "voxels": done, "finished": True}
    s = steps[cur["step"]]
    frac = (t - cur["t0"]) / max(1e-9, cur["t1"] - cur["t0"])
    r = s["r_mm"][0] + frac * (s["r_mm"][1] - s["r_mm"][0])
    part = int(frac * s["voxels"]) if cur["pass"] == 1 else 0
    return {"t": t, "step": cur["step"], "pass": cur["pass"], "radius_mm": round(r, 2), "voxels": done + part, "finished": False}


def strokes(pl: dict, spec: CandySpec | None = None) -> np.ndarray:
    """칸 순서 → 기계 좌표 (막대 각도 θ°, 팔 r mm, 팔 z mm, 재료) — 막대가 θ 로 돌고 팔은 반지름 · 높이만 움직임."""
    spec = spec or pl["spec"]
    zx, zy, zz = pl["zero_mm"]
    xyz = pl["xyz"]
    dx, dy = xyz[:, 0] - zx, xyz[:, 1] - zy
    th = np.degrees(np.arctan2(dy, dx))
    r = np.hypot(dx, dy)
    zt = spec.work_center_z + (xyz[:, 2] - zz)
    return np.stack([th, r, zt, pl["mat"].astype(float)], 1)


def check(pl: dict) -> list[str]:
    """설계 점검: 존재가 수조 안 · 수면 아래에 자라고, 막대째 뽑을 때 다리 아래로 빠지는지."""
    sp = pl["spec"]
    bad = []
    xyz = pl["xyz"]
    zx, zy, zz = pl["zero_mm"]
    top = sp.work_center_z + (xyz[:, 2].max() - zz)
    bottom = sp.work_center_z + (xyz[:, 2].min() - zz)
    half = max(np.abs(xyz[:, 0] - zx).max(), np.abs(xyz[:, 1] - zy).max())
    if top > sp.fill_mm - 5:
        bad.append(f"존재 꼭대기 {top:.0f} mm 가 수면 {sp.fill_mm:g} mm 에 너무 가까움")
    if bottom < 10:
        bad.append(f"존재 밑 {bottom:.0f} mm 가 수조 바닥에 닿음")
    if half > sp.tank_inner_mm[0] / 2 - 30:
        bad.append("존재가 수조 벽 30 mm 안으로 들어옴")
    if 2 * half + 10 > sp.bridge_hole_mm:
        bad.append(f"존재 폭 {2 * half:.0f} mm 가 다리 구멍 {sp.bridge_hole_mm:g} mm 를 못 지나감 (막대째 뽑기)")
    return bad


def describe(pl: dict, proc: Process) -> str:
    sp, p = pl["spec"], pl["piece"]
    n = len(pl["mat"])
    lines = [f"[{sp.name} — {proc.name}] 높이 {p.height_mm:.1f} mm · 칸 {n} · 영점 {tuple(round(v, 1) for v in pl['zero_mm'])} mm (존재 좌표)",
             f"  막대 Ø{sp.stick.diameter_mm:g} ({sp.stick.leads}) · 주사기 GO {sp.syringes.go_mg_ml:g} mg/mL ×3 (p · n · 막) + PVA {sp.syringes.pva_wt:g} % — 염은 배지 154 mM",
             f"  껍질 {int(pl['shell'][-1]) + 1}개 × {sp.shell_mm} mm → 단계 {len(proc.steps)}개 (단계 = 껍질 {sp.shells_per_step}) · 흐름 {pl['flow_mm3_s']:.2f} mm³/s",
             f"  시간 약 {proc.total_s() / 3600:.1f} h (반복 · 수정 반영) · 고친 것 {len(proc.edits)}건"]
    for s in proc.steps[:3] + ([{"i": "…"}] if len(proc.steps) > 6 else []) + proc.steps[-3:]:
        if s.get("i") == "…":
            lines.append("    …")
            continue
        flag = " (건너뜀)" if s["skip"] else f" ×{s['repeat']}" if s["repeat"] > 1 else ""
        lines.append(f"    단계 {s['i']:>2}  r {s['r_mm'][0]:5.1f}–{s['r_mm'][1]:5.1f} mm · 칸 {s['voxels']:>6} · {s['seconds'] / 60:5.1f} 분{flag}")
    bad = check(pl)
    lines.append("  점검: " + ("통과 — 수면 아래 · 수조 안에서 자라고 막대째 뽑힘" if not bad else "; ".join(bad)))
    return "\n".join(lines)


def write_job(pl: dict, proc: Process, out: str | Path = "sculpt_out") -> Path:
    """작업 폴더 sculpt_out/candy_jobs/NN_이름/: process.json · strokes.npy · plan.json (기억은 sculpt 와 같은 npz)."""
    base = Path(out) / "candy_jobs"
    base.mkdir(parents=True, exist_ok=True)
    n = len([p for p in base.glob("*") if p.is_dir()]) + 1
    f = base / f"{n:02d}_{proc.name}"
    f.mkdir()
    proc.save(f / "process.json")
    np.save(f / "strokes.npy", strokes(pl).astype(np.float32))
    sp = pl["spec"]
    (f / "plan.json").write_text(json.dumps({"spec": asdict(sp) | {"syringes": {k: v for k, v in asdict(sp.syringes).items() if k != "ratio"}},
                                             "zero_mm": pl["zero_mm"], "height_mm": pl["piece"].height_mm, "voxels": int(len(pl["mat"])),
                                             "flow_mm3_s": pl["flow_mm3_s"], "check": check(pl)}, ensure_ascii=False, indent=1, default=float),
                                 encoding="utf-8")
    return f


__all__ = ["CandySpec", "Process", "plan", "state_at", "strokes", "check", "describe", "write_job", "replace"]
