"""CAD 생성(Rust truck 커널 · C# STEP 작성기) + OpenCascade 검증.

    python -m snss_battery cadcheck [--out cad_out/step] [--ocp 경로]

OpenCascade 파이썬 바인딩(OCP)이 있으면 STEP 파일을 읽어 고체 수·B-rep 유효성·층별 부피를 해석값과 대조한다.
없으면 생성만 하고, 마지막 검증 기록(spec/cad_validation.json)을 보여 준다.
설치: pip install cadquery-ocp  (또는 --ocp 로 설치 경로 지정)
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "spec" / "cad_validation.json"
FILES = ("qmodule_rust.step", "qmodule_csharp.step", "crystal_block_rust.step", "crystal_block_csharp.step")


def generate(out: Path) -> list[str]:
    out = out.resolve()  # cargo·dotnet 은 각자 폴더에서 실행되므로 절대 경로
    out.mkdir(parents=True, exist_ok=True)
    logs = []
    if shutil.which("cargo"):
        p = subprocess.run(["cargo", "run", "--release", "--quiet", "--", str(out)], cwd=ROOT / "rust_cad",
                           capture_output=True, text=True, timeout=1800)
        logs.append(p.stdout.strip() or p.stderr[-500:])
    if shutil.which("dotnet"):
        p = subprocess.run(["dotnet", "run", "-c", "Release", "--project", "Snss.Lab", "--", "qcad", str(out)],
                           cwd=ROOT / "csharp", capture_output=True, text=True, timeout=600)
        logs.append(p.stdout.strip() or p.stderr[-500:])
    return logs


def analytic_layers() -> dict[str, list[tuple[float, float]]]:
    from .quantum import module_layers

    q = [(d, t) for _, _, d, t in module_layers()]
    di = 72.0 - 1.6
    n = int((500 / (math.pi * (di / 20) ** 2) * 10) // (2 * 0.5 + 0.013))
    c = [(di, 0.5), (di, 0.005), (di, 0.5), (di, 0.008)] * n
    return {"qmodule": q, "crystal_block": c}


def _occt_read(path: Path) -> list[dict]:
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    r = STEPControl_Reader()
    if r.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"{path.name}: STEP 읽기 실패")
    r.TransferRoots()
    ex = TopExp_Explorer(r.OneShape(), TopAbs_SOLID)
    out = []
    while ex.More():
        s = TopoDS.Solid(ex.Current())
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(s, g)
        nf, fx = 0, TopExp_Explorer(s, TopAbs_FACE)
        while fx.More():
            nf += 1
            fx.Next()
        out.append({"valid": bool(BRepCheck_Analyzer(s).IsValid()), "volume": g.Mass(), "faces": nf})
        ex.Next()
    return out


def validate(out: Path, ocp_path: str | None = None) -> dict:
    if ocp_path:
        sys.path.insert(0, ocp_path)
    import importlib.util

    if importlib.util.find_spec("OCP") is None:
        return {"error": "OpenCascade(OCP) 없음 — pip install cadquery-ocp 후 다시 실행하거나 --ocp 로 경로 지정"}
    ana = analytic_layers()
    rep = {"tool": "OpenCascade (OCP) STEPControl_Reader + BRepCheck_Analyzer + BRepGProp",
           "date": _dt.datetime.now().isoformat(timespec="seconds"), "files": {}}
    vols = {}
    for name in FILES:
        kind = name.rsplit("_", 1)[0]
        solids = _occt_read(out / name)
        ref = [math.pi * (d / 2) ** 2 * t for d, t in ana[kind]]
        rel = max(abs(s["volume"] - v) / v for s, v in zip(solids, ref)) if len(solids) == len(ref) else math.inf
        vols[name] = [s["volume"] for s in solids]
        rep["files"][name] = {"solids": len(solids), "expected": len(ref), "valid": sum(s["valid"] for s in solids),
                              "faces_per_solid": sorted({s["faces"] for s in solids}),
                              "volume_mm3": sum(vols[name]), "analytic_mm3": sum(ref), "max_layer_rel_err": rel,
                              "ok": len(solids) == len(ref) and all(s["valid"] for s in solids) and rel < 1e-6}
    for kind in ("qmodule", "crystal_block"):
        a, b = vols[f"{kind}_rust.step"], vols[f"{kind}_csharp.step"]
        rep[f"{kind}_rust_vs_csharp_max_rel"] = max(abs(x - y) / y for x, y in zip(a, b)) if len(a) == len(b) else math.inf
    rep["ok"] = all(f["ok"] for f in rep["files"].values())
    RECORD.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def format_report(rep: dict) -> str:
    if "error" in rep:
        return rep["error"]
    lines = [f"[OpenCascade 검증] {rep['date']} — {'✔ 모두 통과' if rep['ok'] else '✘ 실패 있음'}"]
    for name, f in rep["files"].items():
        lines.append(f"  {name:<26} 고체 {f['solids']}/{f['expected']}, 유효 {f['valid']}, 면/고체 {f['faces_per_solid']}, "
                     f"부피 {f['volume_mm3']:.6f} mm³ (해석 {f['analytic_mm3']:.6f}), 층별 최대 오차 {f['max_layer_rel_err']:.1e}")
    for kind in ("qmodule", "crystal_block"):
        lines.append(f"  {kind}: Rust vs C# 층별 부피 최대 차 {rep[f'{kind}_rust_vs_csharp_max_rel']:.1e}")
    return "\n".join(lines)


def last_record() -> dict | None:
    return json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.exists() else None


def run(out: str | Path = "cad_out/step", ocp_path: str | None = None) -> dict:
    out = Path(out).resolve()
    logs = generate(out)
    rep = validate(out, ocp_path or os.environ.get("SNSS_OCP_PATH"))
    rep["generate_log"] = logs
    return rep
