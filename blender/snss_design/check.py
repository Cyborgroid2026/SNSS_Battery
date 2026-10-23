"""점검 · 내보내기 — Blender 에서 지은 설계를 메시로 다시 확인 (freecad/SNSS/snss_fc/check.py 와 같은 점검).

1. 출력 부품: 평가된 메시 부피 ↔ snss_battery/parts.py SDF 표면망 부피 · 다양체 아닌 모서리 수
2. 존재 모양: 메타볼 → 메시 → 바닥 z 0 에서 잘라 막음 → 부피 ↔ sculpt.SHAPES SDF 부피 · STL (→ sculpt new · light --shape)
3. 공간 점검: layout 의 '비어 있어야 할 곳' 상자 ↔ 고정 부품 (컬렉션 인스턴스까지) — BVH 겹침 + 꼭짓점 · 상자 면 표본 거리
4. 움직임 점검: BedDrop 을 출력 높이까지 → 받침 무리 ↔ 고정 부품 · 수조 바닥
메시 거리라 원기둥은 48각 — B-rep(FreeCAD)보다 0.1 mm 안팎 거칠다.
"""

from __future__ import annotations

import struct
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import prim as P
from .build import dg_of


def _bm_of(ob, matrix):
    me = ob.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(matrix)
    ob.to_mesh_clear()
    return bm


def collect(sc, coll_name_prefix, dg, skip=()):
    """컬렉션(이름 앞머리) 아래 모든 메시를 세계 좌표로 — 컬렉션 인스턴스 포함. → [(이름, bmesh)]"""
    roots = [c for c in bpy.data.collections if c.name.startswith(coll_name_prefix) and sc.user_of_id(c)]
    names = {o.name for c in roots for o in c.all_objects}
    out = []
    for inst in dg.object_instances:
        src = (inst.parent.original if inst.is_instance and inst.parent else inst.object.original)
        if src.name not in names or any(k in src.name for k in skip):
            continue
        ob = inst.object
        if ob.type not in ("MESH", "META") or ob.hide_render and not inst.is_instance and ob.display_type == "WIRE":
            continue
        if inst.is_instance and ob.original.display_type == "WIRE":
            continue  # 인스턴스 속 CSG 재료
        bm = _bm_of(ob, inst.matrix_world.copy())
        if bm.verts:
            out.append((src.name, bm))
        else:
            bm.free()
    return out


def _bbox(bm):
    xs = [v.co for v in bm.verts]
    return Vector([min(p[i] for p in xs) for i in range(3)]), Vector([max(p[i] for p in xs) for i in range(3)])


def _pt_box(p, lo, hi):
    d = Vector([max(lo[i] - p[i], 0, p[i] - hi[i]) for i in range(3)])
    return d.length


def _box_samples(lo, hi, n=9):
    pts = []
    for ax in range(3):
        u, v = [i for i in range(3) if i != ax]
        for side in (lo[ax], hi[ax]):
            for i in range(n):
                for j in range(n):
                    p = [0, 0, 0]
                    p[ax], p[u], p[v] = side, lo[u] + (hi[u] - lo[u]) * i / (n - 1), lo[v] + (hi[v] - lo[v]) * j / (n - 1)
                    pts.append(Vector(p))
    return pts


def _box_bvh(lo, hi):
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([vs[i] for i in f])
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def box_gap(lo, hi, bm, bvh):
    inside = [v.co for v in bm.verts if all(lo[i] < v.co[i] < hi[i] for i in range(3))]
    if inside:
        return -min(min(min(p[i] - lo[i], hi[i] - p[i]) for i in range(3)) for p in inside)
    if _box_bvh(lo, hi).overlap(bvh):
        return 0.0
    d = min(_pt_box(v.co, lo, hi) for v in bm.verts)
    for p in _box_samples(lo, hi):
        hit = bvh.find_nearest(p)
        if hit[0] is not None:
            d = min(d, hit[3])
    return d


def mesh_gap(a, ta, b, tb):
    if ta.overlap(tb):
        return 0.0
    d = min(tb.find_nearest(v.co)[3] for v in a.verts)
    return min(d, min(ta.find_nearest(v.co)[3] for v in b.verts))


def clearance(sc, L) -> list[dict]:
    dg = dg_of(sc)
    fixed = collect(sc, "고정", dg)
    trees = [(n, bm, BVHTree.FromBMesh(bm), *_bbox(bm)) for n, bm in fixed]
    out = []
    for z in L["zones"]:
        lo, hi = Vector(z["lo"]), Vector(z["hi"])
        best = {}
        for n, bm, t, blo, bhi in trees:
            sep = max(max(blo[i] - hi[i], lo[i] - bhi[i]) for i in range(3))
            if sep > 25:
                continue
            g = box_gap(lo, hi, bm, t)
            best[n] = min(best.get(n, 1e9), g)
        for n, g in sorted(best.items(), key=lambda kv: kv[1])[:3]:
            out.append({"zone": z["name"], "part": n, "gap": round(g, 2)})
    for _, bm, *_ in trees:
        bm.free()
    return out


def bed_motion(sc, drop) -> list[dict]:
    d = bpy.data.objects[sc["snss_dims"]]
    old = d["BedDrop"]
    d["BedDrop"] = float(drop)
    d.update_tag()
    try:
        dg = dg_of(sc)
        bed = [(n, bm) for n, bm in collect(sc, "움직임", dg) if True]
        roots = [o for o in sc.objects if o.name.startswith("배양 받침 (BedDrop")]
        bed_names = {c.name for r in roots for c in r.children_recursive}  # 회전 받침 아래까지
        bed = [(n, bm) for n, bm in bed if n in bed_names and "존재" not in n]
        fixed = [(n, bm) for n, bm in collect(sc, "고정", dg) if "나사봉" not in n]
        out = []
        for n, bm in bed:
            lo, hi = _bbox(bm)
            if lo.z < 0:
                out.append({"bed": n, "part": "수조 바닥 (z 0)", "gap": round(lo.z, 2), "drop": drop})
            ta = BVHTree.FromBMesh(bm)
            for fn, fb in fixed:
                flo, fhi = _bbox(fb)
                if max(max(flo[i] - hi[i], lo[i] - fhi[i]) for i in range(3)) > 5:
                    continue
                g = mesh_gap(bm, ta, fb, BVHTree.FromBMesh(fb))
                if g < 2.0 and not ("너트" in n and "나사봉" in fn):
                    out.append({"bed": n, "part": fn, "gap": round(g, 2), "drop": drop})
        for _, bm in bed + fixed:
            bm.free()
        return out
    finally:
        d["BedDrop"] = old
        d.update_tag()
        dg_of(sc)


def write_stl(path: Path, bm):
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"SNSS Blender design".ljust(80, b" "))
        f.write(struct.pack("<I", len(bm.faces)))
        for fc in bm.faces:
            n = fc.normal
            f.write(struct.pack("<3f", n.x, n.y, n.z))
            for v in fc.verts:
                f.write(struct.pack("<3f", *v.co))
            f.write(b"\0\0")


def _at_origin(o, dg):
    """평가된 메시를 세계 좌표로 (크기 · 회전 포함) 가져온 뒤 개체 위치만 빼서 원점으로 (부품판 · 모양 줄에서 꺼냄)."""
    bm = P.eval_mesh(o, dg, world=True)
    t = o.evaluated_get(dg).matrix_world.translation.copy()
    bmesh.ops.translate(bm, verts=bm.verts, vec=-t)
    return bm


def parts_report(sc, out: Path) -> list[dict]:
    dg = dg_of(sc)
    rows = []
    for o in sc.objects:
        key = o.get("snss_part")
        if not key:
            continue
        bm = _at_origin(o, dg)
        v = abs(bm.calc_volume(signed=True)) / 1000
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        write_stl(out / "stl" / f"{key}.stl", bm)
        bm.free()
        ref = o.get("sdf_volume_cm3") or None
        rows.append({"key": key, "name": o.name, "volume_cm3": round(v, 4), "sdf_volume_cm3": ref, "rel": (v - ref) / ref if ref else None,
                     "nonmanifold_edges": nm, "qty": o.get("qty")})
    return rows


def shape_mesh(o, dg):
    return P.shape_bmesh(o, dg)


def shapes_report(sc, out: Path, sdf: dict) -> dict:
    dg = dg_of(sc)
    res = {}
    for o in sc.objects:
        key = o.get("SNSSShape")
        if not key:
            continue
        bm = shape_mesh(o, dg)
        v = abs(bm.calc_volume(signed=True)) / 1000
        lo, hi = _bbox(bm)
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        f = out / "shapes" / f"{key}.stl"
        write_stl(f, bm)
        n = len(bm.faces)
        bm.free()
        ref = sdf.get(key)
        res[key] = {"volume_cm3": round(v, 4), "sdf_volume_cm3": round(ref, 4) if ref else None, "rel": (v - ref) / ref if ref else None,
                    "height": round(hi.z - lo.z, 2), "nonmanifold_edges": nm, "triangles": n, "stl": str(f.relative_to(out.parent.parent))}
    return res


def scene_report(sc) -> dict:
    dg = dg_of(sc)
    bad_drivers = []
    for o in sc.objects:
        ad = o.animation_data
        if ad:
            bad_drivers += [f"{o.name}.{fc.data_path}[{fc.array_index}]" for fc in ad.drivers if not fc.driver.is_valid]
    bad_mods = [f"{o.name}: {m.name}" for o in sc.objects for m in getattr(o, "modifiers", [])
                if m.type == "BOOLEAN" and (m.collection is None and m.object is None)]
    meshes = [o for o in sc.objects if o.type in ("MESH", "META")]
    return {"scene": sc.name, "objects": len(sc.objects), "meshes": len(meshes), "instances": sum(1 for o in sc.objects if o.instance_type == "COLLECTION"),
            "drivers": sum(len(o.animation_data.drivers) for o in sc.objects if o.animation_data), "bad_drivers": bad_drivers, "bad_modifiers": bad_mods}


def render(sc, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    sc.render.filepath = str(path)
    sc.render.resolution_percentage = 70
    bpy.ops.render.render(write_still=True, scene=sc.name)
    return str(path)
