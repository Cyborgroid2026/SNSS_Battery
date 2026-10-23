"""FreeCAD 설계 — 이 저장소의 모든 작품 치수를 한 JSON 으로 모아 FreeCAD 로 넘김 (명세: spec/FREECAD.md).

FreeCAD 쪽 코드(freecad/SNSS/)는 snss_battery 를 import 하지 않는다 (FreeCAD 의 파이썬 3.11 · 따로 된 numpy).
그래서 값은 늘 여기서 계산해 `cad_out/freecad/design.json` 으로 넘기고, FreeCAD 는 그 값으로 매개변수 설계를 짓는다.
설계를 FreeCAD 에서 바꾼 뒤에는 존재 모양을 STL 로 내보내 `sculpt new 이름 --shape …stl` · `light 이름 --shape …` 로 돌려보낸다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cad_out" / "freecad"
ADDON = ROOT / "freecad" / "SNSS"
FREECAD_DIRS = [Path.home() / "Applications" / "freecad-1.1.4"]


# ---------- 존재 모양: sculpt.SHAPES 의 SDF 를 B-rep 기본형으로 (부드러운 합 k 는 FreeCAD 에서 필렛 없이 합집합) ----------
# 종류: ellipsoid (c, r=(rx,ry,rz)) · sphere (c, r) · capsule (a, b, r) · box (lo, hi). 모두 바닥 z = 0 아래는 잘라 냄.
def shape_prims() -> dict:
    being = [
        {"name": "몸통", "kind": "ellipsoid", "c": [0, 0, 36], "r": [13, 10, 16]},
        {"name": "머리", "kind": "sphere", "c": [0, 0, 60], "r": 11},
    ]
    for s, side in ((-1, "왼"), (1, "오른")):
        being += [
            {"name": f"{side}다리", "kind": "capsule", "a": [7 * s, 0, 24], "b": [8 * s, 0, 5], "r": 5.2},
            {"name": f"{side}발 ({'+' if s < 0 else '−'})", "kind": "ellipsoid", "c": [8.5 * s, 2.5, 2.4], "r": [6, 8.5, 3.2]},
            {"name": f"{side}팔", "kind": "capsule", "a": [12 * s, 0, 45], "b": [19 * s, 2, 28], "r": 3.8},
        ]
    return {
        "being": {"label": "서 있는 존재 (Energetic Being)", "height": 72.0, "prims": being},
        "seed": {"label": "씨앗", "height": 58.0, "prims": [{"name": "달걀", "kind": "ellipsoid", "c": [0, 0, 27], "r": [20, 20, 31]}]},
        "bud": {"label": "싹 (덧붙이는 조각)", "height": 18.0,
                "prims": [{"name": "봉오리", "kind": "ellipsoid", "c": [0, 0, 7], "r": [7, 7, 7.5]},
                          {"name": "줄기", "kind": "capsule", "a": [0, 0, 10], "b": [2, 0, 17], "r": 2.2}]},
        "coupon": {"label": "시험편 12 mm", "height": 12.0, "prims": [{"name": "정육면체", "kind": "box", "lo": [-6, -6, 0], "hi": [6, 6, 12]}]},
    }


def sdf_volumes(step: float = 0.25) -> dict:
    """sculpt.SHAPES 의 SDF 부피 (cm³) — FreeCAD B-rep (부드러운 합 없음) 과 대조."""
    import numpy as np

    from .sculpt import SHAPES

    out = {}
    for key, (fn, h0) in SHAPES.items():
        g = np.arange(-h0 * 0.6, h0 * 0.6, step)
        zs = np.arange(0, h0 * 1.05, step)
        tot = 0
        for z in zs:  # 층마다 (메모리 절약)
            X, Y = np.meshgrid(g, g, indexing="ij")
            tot += int((fn((X, Y, np.full_like(X, z + step / 2))) < 0).sum())
        out[key] = tot * step ** 3 / 1000
    return out


def coupons() -> dict:
    """SC-2 빛 상수 보정 사다리 (lightcal): 칸마다 노출 · 예측 굳은 두께 Cd = Dp·ln(E/Ec)."""
    import math

    from .lightcal import COLS, GAP_MM, SQUARE_MM, ladders
    from .lightsculpt import LightSculptorSpec

    sp = LightSculptorSpec()
    lad = ladders(sp)
    dp, ec = sp.dp_mm(), sp.photo.ec_mj_cm2
    return {"square": SQUARE_MM, "gap": GAP_MM, "cols": COLS, "dp": dp, "ec": ec, "layer": sp.layer_mm, "e_cure": sp.e_cure(),
            "ladders": {k: [float(x) for x in v] for k, v in lad.items()},
            "cd_A": [max(0.0, dp * math.log(e / ec)) for e in lad["A"]]}


def _parts_rows() -> list[dict]:
    """출력 부품 목록 + SDF 표면망 부피 (parts.mesh_part — FreeCAD B-rep 부피와 대조, 약 8 s)."""
    from .parts import PARENT_BED_MM, mesh_part, printed_parts

    return [{"key": p.key, "name": p.name, "qty": p.qty, "material": p.material, "role": p.role, "lo": p.lo, "hi": p.hi,
             "fits_bed": p.fits(PARENT_BED_MM), "sdf_volume_cm3": round(mesh_part(p)[2], 5)} for p in printed_parts()]


def design() -> dict:
    from . import __version__
    from .cad import BottleDesign
    from .bottle import BottleGelBattery
    from .interfaces import PORTS
    from .layout import BED_CARRIAGE, HAND, NUT_R, PEN_STACK, PLATE, POD_H, RISER, Z_SCREW, make_layout, make_light_layout
    from .lightcal import SQUARE_MM
    from .lightsculpt import LightSculptorSpec
    from .lighttools import TOOLS, ToolHead
    from .parts import LM8UU, PARENT_BED_MM, ROD
    from .printer import SculptorSpec
    from .quantum import module_layers

    sc1, sc2 = SculptorSpec(), LightSculptorSpec()
    lay1 = make_layout(sc1)
    lay1_json = lay1.to_json() | {"parked": [{"name": b.name, "lo": b.lo, "hi": b.hi, "kind": b.kind, "shape": b.shape}
                                             for b in lay1.parked()], "bed_bottom_min": lay1.bed_bottom_min}
    bat = BottleGelBattery()
    bd = BottleDesign(bat)
    th = ToolHead()
    return {
        "version": __version__,
        "const": {"ROD": ROD, "LM8UU": LM8UU, "PLATE": PLATE, "BED_CARRIAGE": BED_CARRIAGE, "HAND": HAND, "Z_SCREW": Z_SCREW,
                  "POD_H": POD_H, "NUT_R": NUT_R,
                  "PEN_STACK": PEN_STACK, "RISER": RISER, "PARENT_BED": PARENT_BED_MM},
        "sc1": {"name": sc1.name, "frame": sc1.frame_mm, "build": sc1.build_mm, "tank": asdict(sc1.tank) | {"inner_mm": sc1.tank.inner_mm},
                "layout": lay1_json},
        "sc2": {"name": sc2.name, "frame": sc2.frame_mm, "build": sc2.build_mm, "tank_inner": sc2.tank.inner_mm, "fill": sc2.tank.fill_mm,
                "ink": {"well": sc2.ink.well_mm, "depth": sc2.ink.depth_mm}, "throw": sc2.projector.throw_mm,
                "insulation": sc2.desktop.insulation_mm, "layout": make_light_layout(sc2).to_json(),
                "tool_head": {"gz": th.gz, "tool_len": th.tool_len, "drop": th.carriage_drop, "tip_z": th.tip_z, "park": th.park,
                              "pumps": th.pumps},
                "tools": [{"key": t.key, "name": t.name, "tip": t.tip, "use": t.use} for t in TOOLS],
                "coupon_square": SQUARE_MM},
        "parts": _parts_rows(),
        "ports": [{"key": p.key, "domain": p.domain, "connector": p.connector, "signal": p.signal} for p in PORTS],
        "shapes": shape_prims(),
        "shape_sdf_volume_cm3": sdf_volumes(),
        "coupons": coupons(),
        "quantum": [{"name": n, "material": m, "d": d, "t": t} for n, m, d, t in module_layers()],
        "bottle": asdict(bat.bottle) | {"gel_bottom": bd.gel_bottom_z, "gel_top": bd.gel_top_z, "block_h": bd.block_height,
                                         "cut_z": bd.cut_z, "gel_r": bd.gel_radius},
        "jobs": _jobs(),
        "console": __import__("snss_battery.console", fromlist=["Console"]).Console().to_json(),
    }


def _jobs() -> dict:
    """마지막 작업의 세포 표면망 STL (FreeCAD 에서 설계 모양과 겹쳐 봄)."""
    out = {}
    for kind, base in (("sc1", ROOT / "sculpt_out" / "jobs"), ("sc2", ROOT / "sculpt_out" / "light_jobs")):
        jobs = sorted(p for p in base.glob("*") if p.is_dir()) if base.exists() else []
        for j in reversed(jobs):
            stls = {r: str(s) for r in ("pos", "neg", "mem") for s in j.glob(f"*_{r}.stl")}
            if stls:
                out[kind] = {"folder": str(j), "stl": stls}
                break
    return out


# ---------- FreeCAD 실행 ----------
def freecad_bin(gui: bool = False) -> Path | None:
    names = ["freecad", "FreeCAD"] if gui else ["freecadcmd", "FreeCADCmd"]
    for d in FREECAD_DIRS:
        for n in names:
            p = d / "usr" / "bin" / n
            if p.exists():
                return p
    for n in names:
        if shutil.which(n):
            return Path(shutil.which(n))
    return None


def user_mod_dir() -> Path:
    """FreeCAD 1.x 사용자 Mod 폴더 (애드온을 여기에 링크)."""
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "FreeCAD"
    return base / "v1-1" / "Mod"


def install_addon() -> Path:
    mod = user_mod_dir()
    mod.mkdir(parents=True, exist_ok=True)
    link = mod / "SNSS"
    if link.is_symlink() or link.exists():
        if link.resolve() == ADDON.resolve():
            return link
        if link.is_symlink():
            link.unlink()
        else:
            raise RuntimeError(f"{link} 이(가) 이미 있습니다 (다른 SNSS 애드온) — 지우고 다시 하세요")
    link.symlink_to(ADDON, target_is_directory=True)
    return link


def write_design(out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    f = out / "design.json"
    f.write_text(json.dumps(design(), ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return f


def run_build(out: Path = OUT, only: str = "", gui: bool = False) -> dict:
    """FreeCAD 로 모든 작품을 짓고 점검 → validation.json.
    gui=True: 화면 없는 GUI (QT_QPA_PLATFORM=offscreen) — 색 · 투명도 · 미리보기 그림까지 파일에 저장. 안 되면 머리 없이."""
    exe = freecad_bin(gui) or freecad_bin(False)
    if exe is None:
        raise RuntimeError("FreeCAD 가 없습니다: ./tools.sh freecad 가 ~/Applications 에 FreeCAD 1.1.4 를 받습니다")
    install_addon()
    f = write_design(out)
    val = out / "validation.json"
    if val.exists():
        val.unlink()
    env = dict(os.environ, SNSS_DESIGN=str(f), SNSS_OUT=str(out), SNSS_ONLY=only, SNSS_ADDON=str(ADDON))
    if gui and exe.name.lower() == "freecad":
        env["QT_QPA_PLATFORM"] = "offscreen"
        for k in ("DISPLAY", "WAYLAND_DISPLAY"):  # 화면이 잡혀 있으면 화면 없는 GUI 가 X 를 붙잡고 멈춤
            env.pop(k, None)
    import tempfile

    with tempfile.TemporaryDirectory() as cache:  # 짓기마다 따로 된 캐시 — 끊긴 짓기의 '문서 복구' 창이 다음 GUI 짓기를 막지 않게
        env["XDG_CACHE_HOME"] = cache
        try:
            r = subprocess.run([str(exe), str(ADDON / "build_all.py")], env=env, capture_output=True, text=True, timeout=900 if gui else 1800)
        except subprocess.TimeoutExpired:
            if gui:
                return run_build(out, only, gui=False)
            raise
    if not val.exists() and gui:
        return run_build(out, only, gui=False)
    log = (r.stdout or "") + (r.stderr or "")
    (out / "build.log").write_text(log, encoding="utf-8")
    if not val.exists():
        raise RuntimeError("FreeCAD 짓기가 실패했습니다:\n" + log[-4000:])
    return json.loads(val.read_text(encoding="utf-8"))


def open_gui(out: Path = OUT) -> str:
    exe = freecad_bin(True)
    if exe is None:
        raise RuntimeError("FreeCAD 가 없습니다: ./tools.sh freecad")
    install_addon()
    files = [str(out / f) for f in ("SC1_Sculptor.FCStd", "SC2_LightSculptor.FCStd", "Being_Shapes.FCStd") if (out / f).exists()]
    if not files:
        raise RuntimeError("먼저 python3 -m snss_battery freecad 로 지으세요")
    subprocess.Popen([str(exe), *files], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return " · ".join(Path(f).name for f in files)


def describe(v: dict) -> str:
    lines = [f"[FreeCAD 설계 — {v['freecad']}] 문서 {len(v['docs'])}개 → {OUT.relative_to(ROOT)}/"]
    for d in v["docs"]:
        lines.append(f"  {d['file']:<26} 개체 {d['objects']:>4} · 고체 {d['solids']:>4} · 다시 계산 오류 {len(d['errors'])} · "
                     f"유효하지 않은 모양 {len(d['invalid'])}" + (f"  ← {'; '.join((d['errors'] + d['invalid'])[:3])}" if d['errors'] or d['invalid'] else ""))
    if v.get("parts"):
        worst = max(v["parts"], key=lambda p: abs(p.get("rel", 0) or 0))
        lines.append(f"  출력 부품 {len(v['parts'])}종 B-rep 부피 ↔ SDF 표면망 부피: 가장 큰 차이 {worst['name']} "
                     f"{100 * (worst.get('rel') or 0):+.1f} %")
    for k, m in v.get("motion", {}).items():
        lines.append(f"  {k} 움직임 점검 (받침을 맨 아래까지): " + ("통과" if not m else "; ".join(f"{x['bed']} ↔ {x['part']} {x['gap']} mm" for x in m[:4])))
    for k, c in v.get("clearance", {}).items():
        bad = [x for x in c if x["gap"] < 2.0]
        lines.append(f"  {k} 공간 점검 (B-rep 실제 거리): 비어 있어야 할 곳 {len({x['zone'] for x in c})}곳 · "
                     + ("통과" if not bad else "; ".join(f"{x['zone']} ↔ {x['part']} {x['gap']:.1f} mm" for x in bad[:4])))
    for k, s in v.get("shapes", {}).items():
        lines.append(f"  모양 {k:<7} 부피 {s['volume_cm3']:.2f} cm³ · 높이 {s['height']:.1f} mm → {s['stl']}")
    if v.get("exports"):
        lines.append(f"  내보낸 파일 {len(v['exports'])}개 (STEP · STL)")
    return "\n".join(lines)
