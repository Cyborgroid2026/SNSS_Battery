"""Blender → 조각가: 모양(메시)과 허공 획(곡선)을 내보냄.

Blender 안에서 (Scripting 탭 → 이 파일 열기 → 실행) 또는
    blender 내 작업.blend -b --python sim/blender_export.py -- [출력 폴더]

- 선택한 메시 → <출력>/shape.stl (mm). 조각가: python -m snss_battery sculpt new 이름 --shape <출력>/shape.stl
- 곡선 객체 → <출력>/strokes.json. 재질은 사용자 속성 "material" (pos · neg · mem) 또는 이름 앞머리 pos_ · neg_ · mem_
  조각가: python -m snss_battery sculpt draw 이름 --strokes <출력>/strokes.json
좌표: 장면 단위 → mm (장면 단위 배율 반영). 원점 = 수조 바닥 가운데, Z 위.
"""

import json
import struct
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = Path(argv[0]) if argv else Path(bpy.path.abspath("//")) / "sculpt_out"
OUT.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
MM = scene.unit_settings.scale_length * 1000 if scene.unit_settings.system != "NONE" else 1.0  # Blender 단위 → mm
deps = bpy.context.evaluated_depsgraph_get()


def material_of(o) -> str:
    m = o.get("material")
    if m in ("pos", "neg", "mem"):
        return m
    for k in ("pos", "neg", "mem"):
        if o.name.lower().startswith(k + "_"):
            return k
    return "pos"


# ---------- 메시 → STL ----------
meshes = [o for o in bpy.context.selected_objects if o.type == "MESH"] or [o for o in scene.objects if o.type == "MESH"]  # 고른 메시가 없으면 전부
tris = []
for o in meshes:
    ev = o.evaluated_get(deps)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    mw = o.matrix_world
    co = [mw @ v.co for v in me.vertices]
    for t in me.loop_triangles:
        tris.append([tuple(c * MM for c in co[i]) for i in t.vertices])
    ev.to_mesh_clear()
if tris:
    with open(OUT / "shape.stl", "wb") as fp:
        fp.write(b"SNSS sculptor shape from Blender".ljust(80, b" "))
        fp.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            fp.write(struct.pack("<3f", 0, 0, 0))
            for v in (a, b, c):
                fp.write(struct.pack("<3f", *v))
            fp.write(b"\0\0")
    print(f"모양: {OUT / 'shape.stl'} (삼각형 {len(tris)}개, 메시 {len(meshes)}개)")

# ---------- 곡선 → 획 ----------
from mathutils.geometry import interpolate_bezier

strokes = []
for o in scene.objects:
    if o.type != "CURVE":
        continue
    mw = o.matrix_world
    for sp in o.data.splines:  # 굵기(bevel)와 상관없이 중심선을 씀
        pts = []
        if sp.type == "BEZIER":
            bp = list(sp.bezier_points)
            pairs = list(zip(bp[:-1], bp[1:])) + ([(bp[-1], bp[0])] if sp.use_cyclic_u else [])
            for a, b in pairs:
                seg = interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, max(sp.resolution_u, 2) + 1)
                pts += seg if not pts else seg[1:]
        else:
            pts = [p.co.xyz for p in sp.points]
        pts = [tuple(round(c * MM, 3) for c in (mw @ v)) for v in pts]
        if len(pts) >= 2:
            strokes.append({"name": o.name, "material": material_of(o), "points": pts})
if strokes:
    (OUT / "strokes.json").write_text(json.dumps({"unit": "mm", "strokes": strokes}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(f"획: {OUT / 'strokes.json'} ({len(strokes)}개)")
if not tris and not strokes:
    print("내보낼 메시·곡선이 없습니다.")
