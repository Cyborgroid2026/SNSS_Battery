"""빛 조각가 SC-2 실행 — 데스크톱이 실제 기계를 돌리는 묶음과 실행기 (명세: spec/LIGHT.md §9).

묶음 (`export_job`):
- slices/405/L0000.png · slices/530/L0000.png — 프로젝터 화면 그대로 (110×110 mm, 픽셀 0.05 mm, 8비트 회색조).
  DLP 는 밝기가 일정하고 픽셀마다 켜 두는 시간(PWM)으로 회색을 냄 → 회색 = 그 층 최대 노출 대비 비율, 층 노출 시간 = 최대 노출 / 세기.
  위에서 아래로 비추므로 그림 위쪽 = +y (수조 뒤쪽). 광학계가 뒤집으면 job.json 의 flip 으로 맞춤.
- job.json — 층마다 받침 내림 깊이 · 405/530 시간 · 내림·고르기 · 잉크 갈기 · 누설 점검.
- job.gcode · printer_light.cfg — Klipper 기록용 (Z 나사봉 3개 = z_tilt). 실제 노출 시간은 실행기가 맞춤.

실행기 (`run_job`):
- dry: 시간표만 (언제 끝나는지 · 잉크 갈 때).
- 창: 데스크톱 화면 하나를 프로젝터로 (Tk 전체 화면, 위치 지정). Space 멈춤/이어서 · Esc 그만 (곧바로 검은 화면) ·
  ← → 미리보기에서 층 넘기기. --moonraker 를 주면 층마다 Z 를 Moonraker(HTTP) 로 보냄.
- 안전: 시작 · 멈춤 · 끝 · 오류 때 늘 먼저 검은 화면. 누설 점검(LEAK_CHECK)이 실패하면 시작하지 않음.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from .lightsculpt import LightSculptorSpec

PX_MM = 0.05  # 프로젝터 픽셀
FIELD_MM = 110.0


def _pixel_index(n_vox: int, offset: int, vox_mm: float, n_px: int) -> np.ndarray:
    """프로젝터 픽셀 중심 → 설계 칸 번호 (밖이면 −1). 투영 가운데 = 좌표 0."""
    x = (np.arange(n_px) + 0.5) * PX_MM - FIELD_MM / 2
    i = np.floor(x / vox_mm).astype(int) - offset
    i[(i < 0) | (i >= n_vox)] = -1
    return i


def layer_images(E: np.ndarray, G: np.ndarray, offset, vox_mm: float):
    """층 k 마다 (405 회색 · 530 회색 · 405 최대 · 530 최대) — 회색 uint8 (행 0 = +y 끝)."""
    n_px = int(round(FIELD_MM / PX_MM))
    ix = _pixel_index(E.shape[0], offset[0], vox_mm, n_px)
    iy = _pixel_index(E.shape[1], offset[1], vox_mm, n_px)[::-1]  # 그림 위 = +y
    okx, oky = ix >= 0, iy >= 0
    for k in range(E.shape[2]):
        out = []
        for A in (E, G):
            a = A[:, :, k]
            m = float(a.max())
            img = np.zeros((n_px, n_px), dtype=np.uint8)
            if m > 0:
                sub = a[np.ix_(ix[okx], iy[oky])].T  # (y, x)
                img[np.ix_(oky, okx)] = np.round(sub / m * 255).astype(np.uint8)
            out.append((img, m))
        yield k, out[0][0], out[1][0], out[0][1], out[1][1]


def schedule(layer_s405: list[float], layer_s530: list[float], spec: LightSculptorSpec,
             tool_phases: list[dict] | None = None) -> list[dict]:
    """층 시간표 — 잉크 수명을 넘기 전에 잉크 갈기 (그 층 앞에서 멈춤). 도구 작업은 그 띠가 끝난 다음 층 앞에 (잉크 시간엔 안 셈)."""
    life = spec.ink_life_h() * 3600 * 0.95
    rows, t, since = [], 0.0, 0.0
    pending = sorted((x for x in (tool_phases or []) if not x.get("final")), key=lambda x: x["after_mm"])
    for k, (a, b) in enumerate(zip(layer_s405, layer_s530)):
        if a <= 0 and b <= 0:
            continue
        tool = None
        if pending and k * spec.layer_mm >= pending[0]["after_mm"] - 1e-9:
            tool = pending.pop(0)
            t += tool["seconds"]
        dur = a + b + spec.recoat_s
        swap = bool(since + dur > life)
        if swap:
            since = 0.0
        rows.append({"k": k, "z_drop_mm": round((k + 1) * spec.layer_mm, 4), "t405_s": round(a, 2), "t530_s": round(b, 2),
                     "recoat_s": spec.recoat_s, "swap_ink": swap, "start_s": round(t, 1),
                     "tool_before": ({"file": tool["file"], "seconds": round(tool["seconds"], 1), "cells": tool["cells"]} if tool else None)})
        t += dur
        since += dur
    return rows


def plan_schedule(job: dict, tools: dict | None = None) -> dict:
    """층 시간 (405 · 530 = 층 최대 노출 / 세기) + 도구 작업 자리 + 잉크 갈기 → 시간표 (기계 묶음 · 웹 콘솔 같이 씀)."""
    spec, pl = job["spec"], job["plan"]
    E, G = pl["E"], pl["G"]
    pj = spec.projector
    t405 = [float(E[:, :, k].max()) / pj.irradiance_mw_cm2 for k in range(E.shape[2])]
    t530 = [float(G[:, :, k].max()) / pj.green_mw_cm2 for k in range(E.shape[2])]
    phases = []
    for i, ph in enumerate((tools or {}).get("phases", [])):
        phases.append({"after_mm": ph["after_mm"], "seconds": ph["inject_s"] + ph["overhead_s"], "cells": ph["cells"],
                       "file": f"tools/inject_{i:02d}.gcode", "final": ph["final"], "src": ph})
    last_z = max((k for k in range(E.shape[2]) if t405[k] > 0), default=0) * spec.layer_mm
    for ph in phases:  # 마지막 띠에서 끝나는 주입은 다 빚은 뒤로
        ph["final"] = ph["final"] or ph["after_mm"] > last_z + 1e-9
    rows = schedule(t405, t530, spec, phases)
    finals = [x for x in phases if x["final"]]
    total = rows[-1]["start_s"] + rows[-1]["t405_s"] + rows[-1]["t530_s"] + spec.recoat_s if rows else 0.0
    total += sum(x["seconds"] for x in finals)
    return {"rows": rows, "phases": phases, "finals": finals, "total_s": total}


def export_job(job: dict, folder: str | Path, slices: bool = True, tools: dict | None = None) -> dict:
    """실제 기계용 묶음 — 프로젝터 화면 · 시간표 · Klipper 기록. tools(lighttools.plan_tools) 면 주입 G-code 와 도구 작업 자리까지."""
    from PIL import Image

    spec, p, pl = job["spec"], job["piece"], job["plan"]
    folder = Path(folder)
    pj = spec.projector
    if slices:
        for c in ("405", "530"):
            (folder / "slices" / c).mkdir(parents=True, exist_ok=True)
        for k, a, g, ma, mg in layer_images(pl["E"], pl["G"], p.offset, p.pitch[0]):
            if ma > 0:
                Image.fromarray(a).save(folder / "slices" / "405" / f"L{k:04d}.png", optimize=True)
            if mg > 0:
                Image.fromarray(g).save(folder / "slices" / "530" / f"L{k:04d}.png", optimize=True)
    sch = plan_schedule(job, tools)
    if tools:
        from .lighttools import inject_gcode

        (folder / "tools").mkdir(parents=True, exist_ok=True)
        for ph in sch["phases"]:
            (folder / ph["file"]).write_text(inject_gcode(ph["src"], ph["src"]["after_mm"], tools["ts"]), encoding="utf-8")
    rows, finals = sch["rows"], sch["finals"]
    meta = {"machine": spec.name, "piece": p.name, "px_mm": PX_MM, "field_mm": FIELD_MM, "size_px": int(round(FIELD_MM / PX_MM)),
            "flip": {"x": False, "y": False}, "irradiance_mw_cm2": {"405": pj.irradiance_mw_cm2, "530": pj.green_mw_cm2},
            "layer_mm": spec.layer_mm, "ink_life_h": spec.ink_life_h(), "total_h": sch["total_s"] / 3600,
            "ink_swaps": sum(r["swap_ink"] for r in rows), "layers": rows,
            "tool_after": [{"file": x["file"], "seconds": round(x["seconds"], 1), "cells": x["cells"]} for x in finals]}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "job.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "job.gcode").write_text(gcode(meta), encoding="utf-8")
    (folder / "printer_light.cfg").write_text(klipper_light_cfg(spec), encoding="utf-8")
    return meta


def gcode(meta: dict) -> str:
    out = [f"; {meta['machine']} — {meta['piece']} · 층 {len(meta['layers'])} · 약 {meta['total_h']:.1f} h",
           "; Z = 받침 윗면이 수면에서 내려간 깊이 (mm, 아래로 +) — 층 k 는 Z=(k+1)·층두께 에서 노출. 노출은 실행기가 프로젝터로 (PROJECT 는 기록)",
           "LEAK_CHECK", "G28 Z", "G90", "G1 Z0 F120"]
    for r in meta["layers"]:
        if r.get("tool_before"):
            out += ["PROJECT_OFF", f"; 도구 작업 — {r['tool_before']['file']} (n 세포 {r['tool_before']['cells']}개 주입)"]
        if r["swap_ink"]:
            out += ["PROJECT_OFF", "INK_SWAP  ; 잉크 갈기 — 사람이 새 잉크를 붓고 RESUME"]
        out += [f"G1 Z{r['z_drop_mm']:.4f} F30", f"G4 P{int(r['recoat_s'] * 1000)}",
                f"PROJECT LAYER={r['k']} COLOR=405 SECONDS={r['t405_s']:.2f}"]
        if r["t530_s"] > 0:
            out.append(f"PROJECT LAYER={r['k']} COLOR=530 SECONDS={r['t530_s']:.2f}")
    for x in meta.get("tool_after", []):
        out += ["PROJECT_OFF", f"; 도구 작업 (다 빚은 뒤) — {x['file']} (n 세포 {x['cells']}개 주입)"]
    out += ["PROJECT_OFF", "CURE  ; 멸균생리식염수 속 숙성", "M84"]
    return "\n".join(out) + "\n"


def klipper_light_cfg(spec: LightSculptorSpec) -> str:
    """SC-2 Klipper 설정 조각 — Z 나일론 나사봉 3개 (모터는 방수 통 · 자석 커플링). 핀 이름은 예시."""
    from .layout import Z_SCREW

    pts = [(Z_SCREW, -Z_SCREW), (Z_SCREW, Z_SCREW), (-Z_SCREW, -Z_SCREW)]
    out = [f"# {spec.name} — Z 3축 (나일론 M8 나사봉, 1회전 1.25 mm) · 프로젝터는 데스크톱 실행기가 맡음"]
    for i, (name, pin) in enumerate((("stepper_z", "PF11"), ("stepper_z1", "PG0"), ("stepper_z2", "PF9"))):
        out += [f"[{name}]", f"step_pin: {pin}", "dir_pin: PG3", "enable_pin: !PG5", "microsteps: 16", "rotation_distance: 1.25"]
        if i == 0:
            out += ["endstop_pin: ^PG10  # 위 끝 (받침이 수면 바로 아래)", "position_endstop: 0", "position_min: -1",
                    f"position_max: {spec.build_mm[2] + 5:g}", "homing_speed: 2"]
        out.append("")
    out += ["[z_tilt]", "z_positions: " + ", ".join(f"{x:g},{y:g}" for x, y in pts),
            "points: " + ", ".join(f"{x * 0.5:g},{y * 0.5:g}" for x, y in pts), "", "[gcode_macro PROJECT]",
            "gcode:", "  RESPOND MSG=\"PROJECT {params.LAYER} {params.COLOR} {params.SECONDS}s\"",
            "  G4 P{(params.SECONDS|float * 1000)|int}", "",
            "[gcode_macro PROJECT_OFF]", "gcode:", "  RESPOND MSG=\"PROJECT_OFF\"", "",
            "[gcode_macro INK_SWAP]", "gcode:", "  PAUSE", "",
            "[gcode_macro LEAK_CHECK]", "gcode:", "  RESPOND MSG=\"LEAK_CHECK — 흑연 기준 전극 누설 < 50 µA 확인\"", "",
            "[gcode_macro CURE]", "gcode:", f"  G4 P{int(spec.cure_h * 3600 * 1000)}", ""]
    from .console import Console

    out += ["[manual_stepper turn]", "step_pin: PE2", "dir_pin: PE3", "enable_pin: !PD4", "rotation_distance: 360",
            "# 회전 받침 (받침 기둥 위 작은 방수 통, 자석 커플링) — HW 뷰포트 '돌려 보기' (console.py)", "", Console().klipper_macros()]
    return "\n".join(out)


# ---------- 실행 ----------
def describe_schedule(meta: dict) -> str:
    rows = meta["layers"]
    swaps = [r for r in rows if r["swap_ink"]]
    lines = [f"[실행 시간표 — {meta['piece']}] 층 {len(rows)}개 · 약 {meta['total_h']:.1f} h · 잉크 갈기 {len(swaps)}번",
             f"  프로젝터 {meta['size_px']}×{meta['size_px']} px ({meta['px_mm']} mm) · 405 nm {meta['irradiance_mw_cm2']['405']:g} · "
             f"530 nm {meta['irradiance_mw_cm2']['530']:g} mW/cm²"]
    for r in swaps:
        lines.append(f"  잉크 갈기: 층 {r['k']} 앞 · 시작 뒤 {r['start_s'] / 3600:.1f} h")
    tools = [r for r in rows if r.get("tool_before")]
    if tools or meta.get("tool_after"):
        n = sum(r["tool_before"]["cells"] for r in tools) + sum(x["cells"] for x in meta.get("tool_after", []))
        sec = sum(r["tool_before"]["seconds"] for r in tools) + sum(x["seconds"] for x in meta.get("tool_after", []))
        lines.append(f"  도구 작업 {len(tools) + len(meta.get('tool_after', []))}번 (n 세포 {n}개 PEI 주입) · {sec / 3600:.1f} h — "
                     f"층 {', '.join(str(r['k']) for r in tools)} 앞 + 다 빚은 뒤")
    for r in (rows[0], rows[len(rows) // 2], rows[-1]):
        lines.append(f"  층 {r['k']:>4}: 받침 {r['z_drop_mm']:.2f} mm 내림 · 405 {r['t405_s']:.0f} s · 530 {r['t530_s']:.0f} s · "
                     f"시작 {r['start_s'] / 3600:.2f} h")
    return "\n".join(lines)


class Moonraker:
    """Klipper Moonraker HTTP — Z 만 보냄 (노출은 이 실행기가)."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def gcode(self, script: str, timeout: float = 600) -> None:
        import urllib.parse
        import urllib.request

        req = urllib.request.Request(f"{self.url}/printer/gcode/script?script={urllib.parse.quote(script)}", method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                raise RuntimeError(f"Moonraker {r.status}: {script}")


def run_job(folder: str | Path, dry: bool = True, moonraker: str | None = None, geometry: str | None = None,
            speed: float = 1.0) -> dict:
    """dry=True: 시간표만. 아니면 Tk 창(프로젝터)에 층 그림을 시간대로 띄우고, moonraker 가 있으면 Z 를 보냄.

    speed > 1 은 미리보기 (시간을 줄임 — 실제 출력에는 1)."""
    folder = Path(folder)
    meta = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    if dry:
        return {"text": describe_schedule(meta), "meta": meta}
    import tkinter as tk

    from PIL import Image, ImageTk

    mr = Moonraker(moonraker) if moonraker else None
    root = tk.Tk()
    root.configure(bg="black", cursor="none")
    if geometry:  # 프로젝터 출력 화면 위치 · 크기, 예: 1920x1080+1920+0
        root.overrideredirect(True)
        root.geometry(geometry)
    else:
        root.geometry("900x900")
        root.title("SC-2 프로젝터 미리보기")
    W = root.winfo_screenwidth() if geometry is None else int(geometry.split("+")[0].split("x")[0])
    H = root.winfo_screenheight() if geometry is None else int(geometry.split("+")[0].split("x")[1])
    side = min(W, H, 900 if geometry is None else 10 ** 6)
    canvas = tk.Canvas(root, bg="black", highlightthickness=0, width=side, height=side)
    canvas.pack(expand=True)
    label = tk.Label(root, fg="#9aa4b1", bg="black", font=("Noto Sans CJK KR", 11))
    if geometry is None:
        label.pack()
    st = {"i": 0, "phase": "z", "paused": False, "abort": False, "img": None, "log": []}
    rows = meta["layers"]

    def black():
        canvas.delete("all")
        st["img"] = None

    def show(color: str, k: int):
        f = folder / "slices" / color / f"L{k:04d}.png"
        if not f.exists():
            black()
            return
        im = Image.open(f)
        if meta["flip"]["x"]:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if meta["flip"]["y"]:
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
        tint = (0.62, 0.0, 1.0) if color == "405" else (0.0, 1.0, 0.0)  # 미리보기 색 (실제 광엔진은 회색조 그대로)
        rgb = Image.merge("RGB", [im.point(lambda v, t=t: int(v * t)) for t in tint]) if geometry is None else im
        st["img"] = ImageTk.PhotoImage(rgb.resize((side, side), Image.NEAREST))
        canvas.delete("all")
        canvas.create_image(side // 2, side // 2, image=st["img"])

    def step():
        if st["abort"]:
            black()
            root.after(200, root.destroy)
            return
        if st["paused"]:
            root.after(200, step)
            return
        if st["i"] >= len(rows):
            black()
            after = meta.get("tool_after", [])
            if st.get("after_i", 0) < len(after):  # 다 빚은 뒤 도구 작업 (마지막 띠 n 세포 주입)
                tb = after[st.get("after_i", 0)]
                st["after_i"] = st.get("after_i", 0) + 1
                label.config(text=f"도구 작업 (다 빚은 뒤) — n 세포 {tb['cells']}개 주입")
                st["log"].append("도구 끝")
                if mr:
                    mr.gcode((folder / tb["file"]).read_text(encoding="utf-8"), timeout=max(600, tb["seconds"] * 3))
                    root.after(200, step)
                else:
                    root.after(max(1, int(tb["seconds"] * 1000 / speed)), step)
                return
            label.config(text="끝 — 숙성은 멸균생리식염수 속에서")
            st["log"].append("끝")
            root.after(1500, root.destroy)
            return
        r = rows[st["i"]]
        label.config(text=f"층 {r['k']} · {st['phase']} · {st['i'] + 1}/{len(rows)} (Space 멈춤 · Esc 그만)")
        if st["phase"] == "z" and r.get("tool_before") and st.get("tooled") != r["k"]:
            black()  # 도구 작업: 빛은 끔, Moonraker 로 주입 G-code (없으면 미리보기로 시간만)
            st["tooled"] = r["k"]
            tb = r["tool_before"]
            label.config(text=f"도구 작업 — n 세포 {tb['cells']}개 주입 ({tb['file']})")
            st["log"].append(f"도구 {r['k']}")
            if mr:
                mr.gcode((folder / tb["file"]).read_text(encoding="utf-8"), timeout=max(600, tb["seconds"] * 3))
                root.after(200, step)
            else:
                root.after(max(1, int(tb["seconds"] * 1000 / speed)), step)
            return
        if st["phase"] == "z":
            black()
            if r["swap_ink"] and not st.get("swapped") == r["k"]:
                st["paused"], st["swapped"] = True, r["k"]
                label.config(text=f"잉크 갈기 — 새 잉크를 붓고 Space (층 {r['k']} 앞)")
                st["log"].append(f"잉크 갈기 {r['k']}")
                root.after(200, step)
                return
            if mr:
                mr.gcode(f"G1 Z{r['z_drop_mm']:.4f} F30\nM400")
            st["phase"] = "405"
            root.after(int(r["recoat_s"] * 1000 / speed), step)
        elif st["phase"] == "405":
            show("405", r["k"])
            st["phase"] = "530"
            root.after(max(1, int(r["t405_s"] * 1000 / speed)), step)
        else:
            black()
            if r["t530_s"] > 0:
                show("530", r["k"])
            st["log"].append(f"층 {r['k']}")
            st["phase"], st["i"] = "z", st["i"] + 1
            root.after(max(1, int(r["t530_s"] * 1000 / speed)), step)

    def key(ev):
        if ev.keysym == "Escape":
            st["abort"] = True
            black()
        elif ev.keysym == "space":
            st["paused"] = not st["paused"]
            if st["paused"]:
                black()

    root.bind("<Key>", key)
    black()
    root.after(500, step)
    t0 = time.time()
    root.mainloop()
    return {"text": f"실행 {('중단' if st['abort'] else '완료')} · {len([x for x in st['log'] if x.startswith('층')])}층 · "
                    f"{(time.time() - t0) / 60:.1f} 분", "log": st["log"]}


def ink_swaps(meta: dict) -> int:
    return sum(r["swap_ink"] for r in meta["layers"])


def total_hours(meta: dict) -> float:
    return meta["total_h"] if math.isfinite(meta["total_h"]) else float("nan")
