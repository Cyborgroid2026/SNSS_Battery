"""점검 · 내보내기 — FreeCAD 가 지은 설계를 B-rep 으로 다시 확인한다.

1. 문서마다: 다시 계산 오류 · 유효하지 않은 모양(BRepCheck) · 고체 수
2. 출력 부품: B-rep 부피 ↔ snss_battery/parts.py 의 SDF 표면망 부피
3. 공간 점검: layout.py 는 부품을 '감싸는 상자'로 보지만, 여기서는 실제 원기둥 · 출력 부품 모양과 비어 있어야 할 곳의 거리 (distToShape)
4. 움직임 점검: 받침을 맨 아래(BedDrop = 출력 높이)까지 내렸을 때 받침 무리 ↔ 고정 부품 거리
5. 모양: 존재 모양 부피 ↔ sculpt.SHAPES 의 SDF 부피, STL 내보내기 (→ sculpt new · light 의 --shape)
"""

from __future__ import annotations

from pathlib import Path

import FreeCAD as App
import Part


def _global(o):
    """App::Part 안에 든 개체의 세계 배치 (링크에는 getGlobalPlacement 가 없어서 직접)."""
    pl = o.Placement if hasattr(o, "Placement") else App.Placement()
    seen = set()
    cur = o
    while True:
        par = next((p for p in cur.InList if p.TypeId == "App::Part" and cur in p.Group and p.Name not in seen), None)
        if par is None:
            return pl
        seen.add(par.Name)
        pl = par.Placement.multiply(pl)
        cur = par


def _world_shapes(group):
    """그룹(또는 App::Part) 아래 보이는 모양을 세계 좌표로 — (이름, 모양)."""
    out = []
    for o in group.OutList if hasattr(group, "OutList") else []:
        if o.TypeId in ("App::DocumentObjectGroup", "App::Part"):
            out += _world_shapes(o)
            continue
        if o.TypeId == "Spreadsheet::Sheet":
            continue
        try:
            s = Part.getShape(o, "", transform=False)
        except Exception:
            continue
        if s is None or s.isNull() or not s.Solids:
            continue
        s = s.copy()
        s.Placement = _global(o)
        out.append((o.Label, s))
    return out


def doc_report(doc) -> dict:
    doc.recompute()
    errors, invalid, solids = [], [], 0
    for o in doc.Objects:
        st = o.State
        if "Invalid" in st or "Error" in st:
            errors.append(f"{o.Label}: {', '.join(st)}")
        s = getattr(o, "Shape", None)
        if o.TypeId.startswith("Part::") and s is not None and not s.isNull():
            if not s.isValid():
                invalid.append(o.Label)
            if o.TypeId != "App::Link":
                solids += len(s.Solids)
    return {"name": doc.Name, "label": doc.Label, "file": Path(doc.FileName).name if doc.FileName else doc.Name,
            "objects": len(doc.Objects), "solids": solids, "errors": errors, "invalid": invalid}


def parts_report(doc) -> list[dict]:
    rows = []
    for o in doc.Objects:
        if o.TypeId == "Part::FeaturePython" and hasattr(o, "SdfVolume"):
            v = o.Shape.Volume / 1000
            ref = o.SdfVolume or None
            bb = o.Shape.BoundBox
            rows.append({"key": o.Key, "name": o.Label, "volume_cm3": round(v, 4), "sdf_volume_cm3": ref,
                         "rel": (v - ref) / ref if ref else None, "valid": o.Shape.isValid(),
                         "size_mm": [round(bb.XLength, 2), round(bb.YLength, 2), round(bb.ZLength, 2)], "qty": o.Qty})
    return rows


def _find(doc, prefix):
    return next(o for o in doc.Objects if o.Label.startswith(prefix))


def clearance(doc) -> list[dict]:
    """비어 있어야 할 곳 ↔ 고정 부품 (실제 모양) 가장 가까운 거리."""
    zones = _world_shapes(_find(doc, "비어 있어야 할 곳"))
    fixed = _world_shapes(_find(doc, "고정"))
    try:
        fixed += _world_shapes(_find(doc, "출력 부품"))
    except StopIteration:
        pass
    out = []
    for zn, zs in zones:
        zb = zs.BoundBox
        best = {}
        for fn, fs in fixed:
            fb = fs.BoundBox
            sep = max(fb.XMin - zb.XMax, zb.XMin - fb.XMax, fb.YMin - zb.YMax, zb.YMin - fb.YMax, fb.ZMin - zb.ZMax, zb.ZMin - fb.ZMax)
            if sep > 25:  # 멀리 있는 것은 상자만으로 충분
                continue
            d = zs.distToShape(fs)[0]
            if d < 1e-9:
                d = -zs.common(fs).Volume ** (1 / 3) if zs.common(fs).Volume > 1e-6 else 0.0
            if fn not in best or d < best[fn]:
                best[fn] = d
        for fn, d in sorted(best.items(), key=lambda kv: kv[1])[:3]:
            out.append({"zone": zn, "part": fn, "gap": round(d, 2)})
    return out


def bed_motion(doc, drop: float) -> list[dict]:
    """받침을 drop 만큼 내렸을 때 받침 무리 ↔ 고정 부품 거리 (2 mm 아래만)."""
    sh = doc.getObject("Params")
    old = sh.get("BedDrop")
    sh.set("BedDrop", str(drop))
    doc.recompute()
    try:
        bed = _world_shapes(_find(doc, "배양 받침 (BedDrop"))
        fixed = _world_shapes(_find(doc, "고정"))
        try:
            fixed += _world_shapes(_find(doc, "출력 부품"))
        except StopIteration:
            pass
        out = []
        for bn, bs in bed:
            if "존재" in bn:
                continue
            if bs.BoundBox.ZMin < 0:
                out.append({"bed": bn, "part": "수조 바닥 (z 0)", "gap": round(bs.BoundBox.ZMin, 2), "drop": drop})
            for fn, fs in fixed:
                if "배양조" in fn or ("나사봉" in fn and "너트" in bn):  # 너트는 나사봉에 물려 있는 것이 정상
                    continue
                d = bs.distToShape(fs)[0]
                if d < 2.0:
                    out.append({"bed": bn, "part": fn, "gap": round(d, 2), "drop": drop})
        return out
    finally:
        sh.set("BedDrop", str(old))
        doc.recompute()


def shape_report(doc, out: Path, sdf: dict) -> dict:
    import MeshPart

    res = {}
    (out / "shapes").mkdir(parents=True, exist_ok=True)
    for o in doc.Objects:
        key = getattr(o, "SNSSShape", None)
        if not key:
            continue
        s = o.Shape
        m = MeshPart.meshFromShape(Shape=s, LinearDeflection=0.05, AngularDeflection=0.25, Relative=False)
        f = out / "shapes" / f"{key}.stl"
        m.write(str(f))
        ref = sdf.get(key)
        res[key] = {"volume_cm3": round(s.Volume / 1000, 4), "sdf_volume_cm3": round(ref, 4) if ref else None,
                    "rel": (s.Volume / 1000 - ref) / ref if ref else None, "height": round(s.BoundBox.ZLength, 3),
                    "valid": s.isValid(), "triangles": m.CountFacets, "stl": str(f.relative_to(out.parent.parent))}
    return res


def export_step(doc, out: Path, fname: str, roots=None) -> str:
    import Import

    objs = roots or [o for o in doc.RootObjects if o.TypeId not in ("Spreadsheet::Sheet",)]
    p = out / "step" / fname
    p.parent.mkdir(parents=True, exist_ok=True)
    Import.export(objs, str(p))
    return str(p.relative_to(out.parent.parent))


def export_part_stls(doc, out: Path) -> list[str]:
    import MeshPart

    files = []
    (out / "stl").mkdir(parents=True, exist_ok=True)
    for o in doc.Objects:
        if o.TypeId == "Part::FeaturePython" and hasattr(o, "SdfVolume"):
            m = MeshPart.meshFromShape(Shape=o.Shape, LinearDeflection=0.02, AngularDeflection=0.2, Relative=False)
            f = out / "stl" / f"{o.Key}.stl"
            m.write(str(f))
            files.append(str(f.relative_to(out.parent.parent)))
    return files
