"""Blender: SC-1 출력 부품판 — parts.write_parts 가 만든 STL 을 한 판에 늘어놓고 렌더 · .blend 저장.

    blender -b --factory-startup --python sim/blender_parts.py -- <부품 폴더 (sculpt_out/parts)>
"""

import csv
import math
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
DIR = Path(argv[0]) if argv else Path("sculpt_out/parts")
S = 0.01

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def mat(name, rgb, rough=0.45):
    m = bpy.data.materials.new(name)
    if not m.node_tree:
        m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    return m


COL = {"PETG": mat("PETG 주황", (0.95, 0.42, 0.08)), "레진": mat("레진 회색", (0.55, 0.6, 0.66), 0.3),
       "검정": mat("PETG 검정", (0.03, 0.03, 0.035))}
names = {}
with open(DIR / "parts.csv", encoding="utf-8") as fp:
    rows = list(csv.reader(fp))[1:]
stls = sorted((DIR / "stl").glob("*.stl"), key=lambda p: -p.stat().st_size)
x = y = 0.0
row_h = 0.0
MAXW = 5.2
for f in stls:
    bpy.ops.wm.stl_import(filepath=str(f))
    o = bpy.context.selected_objects[0]
    o.scale = (S, S, S)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    w, d, h = o.dimensions
    if f.stem == "mixer":  # 3 mm 짜리는 키워서 보이게
        o.scale = (6, 6, 6)
        w, d, h = w * 6, d * 6, h * 6
    if x + w > MAXW:
        x, y, row_h = 0.0, y + row_h + 0.25, 0.0
    o.location = (x + w / 2, y + d / 2, h / 2)
    x += w + 0.25
    row_h = max(row_h, d)
    key = "레진" if f.stem == "mixer" else "검정" if f.stem == "led_ring" else "PETG"
    o.data.materials.append(COL[key])
    bpy.ops.object.shade_auto_smooth() if hasattr(bpy.ops.object, "shade_auto_smooth") else None
bpy.ops.mesh.primitive_plane_add(size=30, location=(MAXW / 2, (y + row_h) / 2, 0))
bpy.context.object.data.materials.append(mat("판", (0.82, 0.84, 0.87), 0.6))
bpy.ops.object.light_add(type="AREA", location=(MAXW / 2 - 2, -3, 6))
bpy.context.object.data.energy = 2500
bpy.context.object.data.size = 6
bpy.ops.object.light_add(type="SUN", location=(0, 0, 5))
bpy.context.object.data.energy = 2
bpy.context.object.rotation_euler = (0.5, 0.3, 0.6)
world = bpy.data.worlds.new("배경")
if not world.node_tree:
    world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.95, 0.96, 0.97, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.5
scene.world = world
cam = bpy.data.objects.new("카메라", bpy.data.cameras.new("카메라"))
scene.collection.objects.link(cam)
cy = (y + row_h) / 2
cam.location = (MAXW / 2, cy - 5.0, 4.6)
cam.rotation_euler = (math.radians(47), 0, 0)
cam.data.lens = 34
scene.camera = cam
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1600, 1100
scene.render.filepath = str(DIR / "parts.png")
bpy.ops.render.render(write_still=True)
print("렌더:", DIR / "parts.png")
bpy.ops.wm.save_as_mainfile(filepath=str((DIR / "parts.blend").resolve()))
print("저장:", DIR / "parts.blend")
