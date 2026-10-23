"""Blender 설계 — 모든 작품을 Blender 장면으로 짓고 점검 (명세: spec/BLENDER_DESIGN.md).

FreeCAD 설계(fcparams)와 같은 design.json 을 쓰고, blender/build_design.py 가 Blender(머리 없이) 안에서
cad_out/blender/SNSS_Design.blend (장면 9개) · 부품 · 모양 STL · 미리보기 PNG · validation.json 을 만든다.
Blender 창에서는 애드온 'SNSS 설계' (blender/snss_design) 로 고치고 · 점검하고 · 조각가로 보낸다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .fcparams import ROOT, design

OUT = ROOT / "cad_out" / "blender"
ADDON = ROOT / "blender" / "snss_design"


def blender_bin() -> str | None:
    return shutil.which("blender")


def addon_dir() -> Path:
    """Blender 사용자 애드온 폴더 (~/.config/blender/<판>/scripts/addons) — 판은 blender --version 에서."""
    exe = blender_bin()
    ver = "5.2"
    if exe:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
        for w in r.stdout.split():
            if w[:1].isdigit() and w.count(".") >= 1:
                ver = ".".join(w.split(".")[:2])
                break
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "blender" / ver / "scripts" / "addons"
    return base


def install_addon() -> Path:
    d = addon_dir()
    d.mkdir(parents=True, exist_ok=True)
    link = d / "snss_design"
    if link.is_symlink() and link.resolve() == ADDON.resolve():
        return link
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        raise RuntimeError(f"{link} 이(가) 이미 있습니다 — 지우고 다시 하세요")
    link.symlink_to(ADDON, target_is_directory=True)
    return link


def run_build(out: Path = OUT, render: bool = True) -> dict:
    exe = blender_bin()
    if exe is None:
        raise RuntimeError("blender 가 없습니다 (sudo snap install blender --classic)")
    out.mkdir(parents=True, exist_ok=True)
    from . import sc3_build

    sc3_build.write()  # SC-3 출력 부품 STL — Blender 장면이 이 모양을 그대로 씀
    f = out / "design.json"
    f.write_text(json.dumps(design(), ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    val = out / "validation.json"
    if val.exists():
        val.unlink()
    args = [exe, "-b", "--factory-startup", "--python", str(ROOT / "blender" / "build_design.py"), "--", str(f), str(out)]
    if not render:
        args.append("--no-render")
    r = subprocess.run(args, capture_output=True, text=True, timeout=3600)
    log = (r.stdout or "") + (r.stderr or "")
    (out / "build.log").write_text(log, encoding="utf-8")
    if not val.exists():
        raise RuntimeError("Blender 짓기가 실패했습니다:\n" + log[-4000:])
    return json.loads(val.read_text(encoding="utf-8"))


def open_gui(out: Path = OUT) -> str:
    exe = blender_bin()
    f = out / "SNSS_Design.blend"
    if exe is None or not f.exists():
        raise RuntimeError("먼저 python3 -m snss_battery blender-design 로 지으세요")
    install_addon()
    subprocess.Popen([exe, "--addons", "snss_design", str(f)], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f.name


def serve_web(port: int = 8790, host: str = "127.0.0.1", out: Path = OUT) -> int:
    """브라우저 속 Blender — Blender(머리 없이)가 SNSS_Design.blend 를 열고 웹 서버가 됨 (Ctrl+C 로 멈춤)."""
    exe = blender_bin()
    f = out / "SNSS_Design.blend"
    if exe is None:
        raise RuntimeError("blender 가 없습니다")
    if not f.exists():
        run_build(out)
    port = _free_port(host, port)
    if port is None:
        return 0
    print(f"브라우저 속 Blender → http://{host}:{port}/   (VS Code: Ctrl+Shift+P → 'Browser: Open Integrated Browser' 에 붙여 넣기)", flush=True)
    try:
        return subprocess.call(
            [exe, "-b", str(f), "--python", str(ROOT / "blender" / "serve_web.py"), "--", "--port", str(port), "--host", host])
    except KeyboardInterrupt:
        print("\n브라우저 속 Blender 를 멈췄습니다.")
        return 0


def _free_port(host: str, port: int) -> int | None:
    """그 포트에 이미 SNSS 서버가 있으면 주소만 알려 주고 None, 다른 프로그램이 쓰고 있으면 다음 빈 포트."""
    import socket
    import urllib.request

    for p in range(port, port + 20):
        with socket.socket() as s:
            if s.connect_ex((host, p)) != 0:
                return p
        try:
            with urllib.request.urlopen(f"http://{host}:{p}/api/info", timeout=3) as r:
                if "blender" in json.loads(r.read()):
                    print(f"브라우저 속 Blender 가 이미 켜져 있습니다 → http://{host}:{p}/\n"
                          f"  (끄려면: 그 터미널에서 Ctrl+C, 또는 pkill -x blender)")
                    return None
        except Exception:  # noqa: BLE001
            pass
        print(f"포트 {p} 는 다른 프로그램이 쓰고 있어 다음 포트로 갑니다.")
    raise RuntimeError(f"포트 {port}–{port + 19} 가 모두 쓰이고 있습니다 (--port 로 다른 포트를)")


def describe(v: dict) -> str:
    lines = [f"[Blender 설계 — Blender {v['blender']}] 장면 {len(v['scenes'])}개 → {OUT.relative_to(ROOT)}/SNSS_Design.blend"]
    for s in v["scenes"]:
        bad = s["bad_drivers"] + s["bad_modifiers"]
        lines.append(f"  {s['scene']:<14} 개체 {s['objects']:>4} · 메시 {s['meshes']:>4} · 인스턴스 {s['instances']:>3} · 드라이버 {s['drivers']:>3}"
                     + (f"  ← 고장 {bad[:3]}" if bad else ""))
    if v.get("parts"):
        worst = max(v["parts"], key=lambda p: abs(p.get("rel") or 0))
        nm = sum(p["nonmanifold_edges"] for p in v["parts"])
        lines.append(f"  출력 부품 {len(v['parts'])}종 메시 부피 ↔ SDF: 가장 큰 차이 {worst['name']} {100 * (worst.get('rel') or 0):+.1f} % · "
                     f"다양체 아닌 모서리 {nm}")
    for k, m in v.get("motion", {}).items():
        lines.append(f"  {k} 움직임 점검 (받침을 맨 아래까지): " + ("통과" if not m else "; ".join(f"{x['bed']} ↔ {x['part']} {x['gap']} mm" for x in m[:4])))
    for k, c in v.get("clearance", {}).items():
        bad = [x for x in c if x["gap"] < 2.0]
        lines.append(f"  {k} 공간 점검 (메시 거리): " + ("통과" if not bad else "; ".join(f"{x['zone']} ↔ {x['part']} {x['gap']:.1f} mm" for x in bad[:4])))
    for k, s in v.get("shapes", {}).items():
        lines.append(f"  모양 {k:<7} 메타볼 부피 {s['volume_cm3']:.2f} cm³ (SDF {s['sdf_volume_cm3']} · {100 * (s['rel'] or 0):+.1f} %) · "
                     f"높이 {s['height']:.1f} mm → {s['stl']}")
    if v.get("renders"):
        lines.append(f"  미리보기 {len(v['renders'])}장 → {OUT.relative_to(ROOT)}/preview/")
    return "\n".join(lines)
