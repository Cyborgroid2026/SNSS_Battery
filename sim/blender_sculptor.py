"""Blender 장면: SNSS 조각가 SC-1 + 작업물(양자 인공세포 존재) — 렌더 · .blend · (선택) 동영상.

    blender -b --factory-startup --python sim/blender_sculptor.py -- <작업 폴더> <출력 폴더> [--anim] [--cycles]

작업 폴더 = python -m snss_battery sculpt … 가 만든 sculpt_out/jobs/NN_… (summary.json · passes.json · <이름>_mesh.npz).
좌표: 출력 mm × 0.01 = Blender 단위. 배양조 바닥 가운데가 원점. 배양조 = 프린터 몸체, 멸균생리식염수(배지)로 가득 — 펜까지 잠김.
세포 메시의 'wake' 속성(초) = 그 세포가 깨어나는 시간 → 재질의 시계가 그 시간을 지나면 빛남.
"""

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
JOB = Path(argv[0]) if argv else Path("sculpt_out/jobs/01_new_being")
OUT = Path(argv[1]) if len(argv) > 1 else JOB / "blender"
ANIM = "--anim" in argv
CYCLES = "--cycles" in argv
S = 0.01  # mm → Blender 단위
OUT.mkdir(parents=True, exist_ok=True)

summary = json.loads((JOB / "summary.json").read_text(encoding="utf-8"))
passes = json.loads((JOB / "passes.json").read_text(encoding="utf-8"))
piece = summary["pieces"][0]
NAME = piece["name"]
wakes = [w for w in piece["cells"]["wake_s"] if w is not None]
WAKE_MAX = max(wakes) if wakes else 1.0
WAKE_MED = float(np.median(wakes)) if wakes else 0.5

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"


# ---------- 재질 ----------
def principled(name, color, rough=0.5, alpha=1.0, metallic=0.0, transmission=0.0, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    if not m.node_tree:  # Blender 5: 재질은 늘 노드 (use_nodes 는 없어질 예정)
        m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Alpha"].default_value = alpha
    if "Transmission Weight" in b.inputs:
        b.inputs["Transmission Weight"].default_value = transmission
    if emission:
        b.inputs["Emission Color"].default_value = (*emission, 1)
        b.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
                break
            except (AttributeError, TypeError):
                pass
    return m


def hexrgb(h):
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4))


def cell_material(name, color):
    """세포질 재질: 'wake' 속성 < 시계 → 빛남. wake < 0 (잠든 세포) 은 어둡게."""
    m = bpy.data.materials.new(name)
    if not m.node_tree:  # Blender 5: 재질은 늘 노드 (use_nodes 는 없어질 예정)
        m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.45
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "wake"
    clock = nt.nodes.new("ShaderNodeValue")
    clock.name = clock.label = "clock"
    clock.outputs[0].default_value = WAKE_MAX * 1.1
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    nt.links.new(clock.outputs[0], sub.inputs[0])
    nt.links.new(attr.outputs["Fac"], sub.inputs[1])
    ramp = nt.nodes.new("ShaderNodeMath")
    ramp.operation = "DIVIDE"
    ramp.use_clamp = True
    ramp.inputs[1].default_value = max(WAKE_MAX * 0.08, 1e-3)
    nt.links.new(sub.outputs[0], ramp.inputs[0])
    alive = nt.nodes.new("ShaderNodeMath")
    alive.operation = "GREATER_THAN"
    alive.inputs[1].default_value = -0.5
    nt.links.new(attr.outputs["Fac"], alive.inputs[0])
    glow = nt.nodes.new("ShaderNodeMath")
    glow.operation = "MULTIPLY"
    nt.links.new(ramp.outputs[0], glow.inputs[0])
    nt.links.new(alive.outputs[0], glow.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (*[c * 0.18 for c in color], 1)
    mix.inputs["B"].default_value = (*color, 1)
    nt.links.new(glow.outputs[0], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    nt.links.new(mix.outputs["Result"], b.inputs["Emission Color"])
    em = nt.nodes.new("ShaderNodeMath")
    em.operation = "MULTIPLY"
    em.inputs[1].default_value = 2.5
    nt.links.new(glow.outputs[0], em.inputs[0])
    nt.links.new(em.outputs[0], b.inputs["Emission Strength"])
    return m


MAT = {
    "frame": principled("알루미늄", (0.62, 0.64, 0.67), 0.35, metallic=0.9),
    "dark": principled("검은 부품", (0.03, 0.03, 0.035), 0.5),
    "rail": principled("레일", (0.5, 0.52, 0.55), 0.25, metallic=1.0),
    "pen": principled("펜 몸체 (SLA 수지)", (0.88, 0.9, 0.93), 0.3),
    "needle": principled("바늘", (0.8, 0.8, 0.82), 0.2, metallic=1.0),
    "led": principled("405 nm 빛", (0.45, 0.2, 1.0), 0.3, emission=(0.45, 0.2, 1.0), strength=6),
    "bath": principled("배지 (멸균생리식염수)", (0.72, 0.88, 0.97), 0.02, alpha=0.14),
    "acrylic": principled("배양조 (투명 밀폐용기)", (0.9, 0.95, 1.0), 0.02, alpha=0.16),
    "graphite": principled("흑연 패드", (0.06, 0.06, 0.07), 0.35, metallic=0.3),
    "go": principled("GO 원료", (0.12, 0.08, 0.05), 0.3),
    "snss": principled("SNSS 원료", (0.7, 0.85, 1.0), 0.05, alpha=0.5),
    "pva": principled("PVA 원료", (0.95, 0.95, 0.92), 0.2),
    "mem": principled("막 · 피부 (GO/PVA)", hexrgb("#8f9aa6"), 0.35, alpha=0.18),
    "pos": cell_material("p 세포질 (+)", hexrgb("#e0344b")),
    "neg": cell_material("n 세포질 (−)", hexrgb("#2f6db5")),
    "plate": principled("판", (0.18, 0.19, 0.21), 0.4, metallic=0.6),
}


# ---------- 도형 ----------
def box(name, size, loc, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=[v * S for v in loc])
    o = bpy.context.object
    o.name = name
    o.scale = [v * S for v in size]
    o.data.materials.append(mat)
    return o


def cyl(name, r, depth, loc, mat, rot=(0, 0, 0), verts=48):
    bpy.ops.mesh.primitive_cylinder_add(radius=r * S, depth=depth * S, location=[v * S for v in loc], rotation=rot, vertices=verts)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def tube(name, pts, r, mat):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r * S
    cu.bevel_resolution = 4
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = [v * S for v in p]
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(mat)
    bpy.context.collection.objects.link(o)
    return o


def mesh_from(name, v, f, mat, wake=None):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", (v * S).astype(np.float32).ravel())
    me.loops.add(len(f) * 3)
    me.loops.foreach_set("vertex_index", f.astype(np.int32).ravel())
    me.polygons.add(len(f))
    me.polygons.foreach_set("loop_start", np.arange(0, len(f) * 3, 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(len(f), dtype=bool))
    if wake is not None:
        a = me.attributes.new("wake", "FLOAT", "POINT")
        a.data.foreach_set("value", wake.astype(np.float32))
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    return o


def collection(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    lc = bpy.context.view_layer.layer_collection.children[name]
    bpy.context.view_layer.active_layer_collection = lc
    return c


# ---------- 기계 — 통째로 배지에 잠김 (공간 배치 = layout.json, snss_battery/layout.py) ----------
collection("조각가 SC-1 (물속)")
LAY = json.loads((JOB / "layout.json").read_text(encoding="utf-8"))
TANK_IN, FILL_MM = 350, 330  # printer.Tank: 36 큐브 수조 안 350, 배지 330 mm
MAT["cf"] = principled("탄소섬유 봉", (0.04, 0.04, 0.05), 0.3, metallic=0.2)
MAT["petg"] = principled("PETG (출력 부품)", (0.95, 0.42, 0.08), 0.4)
MAT["nylon"] = principled("나일론 나사봉", (0.92, 0.9, 0.84), 0.5)

# 펜 위치 = 마지막 경로 끝 (없으면 작업물 위). 작업물 좌표는 받침 윗면 = 0.
pen_xyz = (0.0, 0.0, 60.0)
for op in reversed(passes["ops"]):
    ps = [p for p in op["passes"] if p["segs"]]
    if ps:
        s = ps[-1]["segs"][-1]
        pen_xyz = (s[2], s[3], ps[-1]["z"]) if ps[-1]["kind"] != "stroke" else tuple(s)
        break
px_, py_, pz_ = pen_xyz
# 갠트리는 고정, 받침이 내려감 → 펜 끝(배치 z_tip)이 지금 층 높이에 오도록 기계 전체를 작업물 기준으로 놓음
MZ = pz_ - LAY["z_tip"]  # 배치 좌표(프레임 바닥 = 0) → 장면
Z0 = MZ - 4  # 수조 바닥
GZ = LAY["gz"] + MZ
tip = (px_, py_, pz_)


def lay_mat(b):
    n = b["name"]
    for key, m in (("탄소섬유", "cf"), ("나일론", "nylon"), ("전극", "graphite"), ("케이블", "dark")):
        if key in n:
            return MAT[m]
    for key, m in (("GO", "go"), ("SNSS", "snss"), ("PVA", "pva")):
        if n.startswith("원료 주사기") and n.endswith(key):
            return MAT[m]
    return MAT["petg"]


def lay_obj(b):
    lo, hi = b["lo"], b["hi"]
    c = [(lo[k] + hi[k]) / 2 for k in range(3)]
    c[2] += MZ
    size = [hi[k] - lo[k] for k in range(3)]
    if b["shape"] == "cyl_z":
        return cyl(b["name"], size[0] / 2, size[2], c, lay_mat(b), verts=32)
    if "탄소섬유 봉" in b["name"] or "레일" in b["name"]:  # 가로 봉은 원기둥으로
        ax = max(range(3), key=lambda k: size[k])
        rot = {0: (0, math.pi / 2, 0), 1: (math.pi / 2, 0, 0), 2: (0, 0, 0)}[ax]
        return cyl(b["name"], min(size) / 2, size[ax], c, lay_mat(b), rot=rot, verts=16)
    return box(b["name"], size, c, lay_mat(b))


tank = box("배양조 — 36 큐브 유리 수조", (TANK_IN + 8, TANK_IN + 8, TANK_IN + 6), (0, 0, Z0 + TANK_IN / 2), MAT["acrylic"])
box("수조 받침대", (TANK_IN + 40, TANK_IN + 40, 14), (0, 0, Z0 - 10), MAT["plate"])
# 고정 부품 (프레임 · Z 나사봉 · 방수 통 · 원료 · 전극 · 케이블 · Y 레일 · XY 모터) — 움직이는 '쓸림' 상자는 빼고
for b in LAY["boxes"]:
    if b["kind"] in ("frame", "static", "gantry") and "(쓸림)" not in b["name"]:
        lay_obj(b)
# 움직이는 갠트리: X 빔은 펜 Y 에, 캐리지는 펜 XY 에
for sx in (-1, 1):
    box("X 봉 끝단 (PETG)", (40, 32, 30), (sx * 121, py_, GZ), MAT["petg"])
cyl("X 빔 (탄소섬유)", 4, 202, (0, py_, GZ), MAT["cf"], rot=(0, math.pi / 2, 0), verts=16)
box("펜 캐리지 (PETG)", (70, 62, 30), (px_, py_, GZ - 6), MAT["petg"])
# 배양 받침 (Z 나사봉 너트 판 위) + 흑연 패드 (왼발 +, 오른발 −) — 받침째 들어 올려 수확
bed = next(b for b in LAY["boxes"] if b["kind"] == "bed")
bw = bed["hi"][0] - bed["lo"][0]
box("배양 받침", (bw, bw, 6), (0, 0, -3), MAT["pen"])
box("받침 너트 판 (나사봉 3)", (bw, bw, 10), (0, 0, -11), MAT["petg"])
for sx in (-1, 1):
    box("수확 손잡이", (8, 30, 14), (sx * (bw / 2 + 4), 0, 4), MAT["pen"])
pads = [box(f"흑연 패드 {'+' if sx < 0 else '−'}", (14, 22, 0.8), (sx * 9.5, 2.5, -0.4), MAT["graphite"]) for sx in (-1, 1)]
# 펜 (물속): 바늘 + 몸체 + 실리콘에 묻힌 빛 고리
cyl("바늘 22G", 0.5, 40, (tip[0], tip[1], tip[2] + 20), MAT["needle"], verts=16)
cyl("펜 몸체", 11, 70, (tip[0], tip[1], tip[2] + 75), MAT["pen"])
cyl("혼합기", 5, 14, (tip[0], tip[1], tip[2] + 45), MAT["pen"])
bpy.ops.mesh.primitive_torus_add(major_radius=9 * S, minor_radius=2 * S, location=(tip[0] * S, tip[1] * S, (tip[2] + 42) * S))
bpy.context.object.name = "405 nm 빛 고리 (실리콘 속)"
bpy.context.object.data.materials.append(MAT["led"])
box("카메라 방수 통 (스캐너)", (40, 22, 30), (tip[0] + 45, tip[1], GZ - 40), MAT["petg"])
# 원료 관: 주사기 위 → 펜 몸체 위
for key, lab in (("go", "GO"), ("snss", "SNSS"), ("pva", "PVA")):
    sy = next(b for b in LAY["boxes"] if b["name"] == f"원료 주사기 {lab}")
    x, y, top = (sy["lo"][0] + sy["hi"][0]) / 2, (sy["lo"][1] + sy["hi"][1]) / 2, sy["hi"][2] + MZ
    tube(f"원료 관 {lab}", [(x, y, top), (x + 20, y, top + 40), (tip[0] - 30, tip[1] + 10, tip[2] + 150),
                           (tip[0], tip[1], tip[2] + 110)], 1.2, MAT[key])
# 방수 케이블 → 배양조 밖 단자판
tube("방수 케이블 (24 V + 이더넷, 밖)", [(156, 0, Z0 + FILL_MM + 20), (TANK_IN / 2 + 30, 0, Z0 + FILL_MM + 40),
                                     (TANK_IN / 2 + 110, 40, Z0 + 140)], 3, MAT["dark"])
box("배양조 밖 단자판 (BNC · SMA · USB · RJ45)", (40, 170, 64), (TANK_IN / 2 + 120, 40, Z0 + 128), MAT["petg"])

# 빛
bpy.ops.object.light_add(type="AREA", location=(1.6, -2.4, 4.2))
bpy.context.object.data.energy = 900
bpy.context.object.data.size = 3
bpy.ops.object.light_add(type="AREA", location=(-3.0, 1.0, 2.0))
bpy.context.object.data.energy = 300
bpy.context.object.data.size = 3
bpy.ops.object.light_add(type="SUN", location=(0, 0, 6))
bpy.context.object.data.energy = 1.5
bpy.context.object.rotation_euler = (0.6, 0.2, 0.8)
world = bpy.data.worlds.new("배경")
if not world.node_tree:
    world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.93, 0.94, 0.96, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
scene.world = world

# ---------- 작업물 ----------
collection("작업물 — " + NAME)
mz = np.load(JOB / f"{NAME}_mesh.npz")
objs = {}
for role in ("pos", "neg", "mem"):
    if f"{role}_v" in mz.files:
        w = mz[f"{role}_wake"] if f"{role}_wake" in mz.files else None
        objs[role] = mesh_from({"pos": "p 세포질", "neg": "n 세포질", "mem": "막 · 피부"}[role],
                               mz[f"{role}_v"], mz[f"{role}_f"], MAT[role], w)
allv = np.concatenate([mz[f"{r}_v"] for r in ("pos", "neg", "mem") if f"{r}_v" in mz.files])
lo, hi = allv.min(0), allv.max(0)
center = (lo + hi) / 2
H = hi[2]
water = box("배지 (멸균생리식염수) — 기계까지 잠김", (TANK_IN - 2, TANK_IN - 2, FILL_MM), (0, 0, Z0 + FILL_MM / 2), MAT["bath"])
BATH = [tank, water]

# 경로 (뷰포트 참고용, 렌더 안 함)
collection("경로")
segs = []
for op in passes["ops"]:
    for p in op["passes"]:
        if p["kind"] == "stroke":
            q = p["segs"]
            segs += [(a, b) for a, b in zip(q[:-1], q[1:])]
        else:
            segs += [((s[0], s[1], p["z"]), (s[2], s[3], p["z"])) for s in p["segs"][::4]]
if segs:
    me = bpy.data.meshes.new("경로")
    verts = np.array([v for ab in segs for v in ab], dtype=np.float32) * S
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.edges.add(len(segs))
    me.edges.foreach_set("vertices", np.arange(len(verts), dtype=np.int32))
    me.update()
    po = bpy.data.objects.new("펜 경로", me)
    bpy.context.collection.objects.link(po)
    po.hide_render = True
bpy.context.view_layer.layer_collection.children["경로"].hide_viewport = True


# ---------- 카메라 · 렌더 ----------
def camera(name, loc, target, lens=50):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.clip_start = 0.01
    o = bpy.data.objects.new(name, cam)
    scene.collection.objects.link(o)
    o.location = [v * S for v in loc]
    t = bpy.data.objects.new(name + " 목표", None)
    scene.collection.objects.link(t)
    t.location = [v * S for v in target]
    c = o.constraints.new("TRACK_TO")
    c.target = t
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    return o


hero = camera("전체", (760, -1050, Z0 + 568), (40, 0, Z0 + 158), 50)
close = camera("작업물", (center[0] + 2.1 * H, center[1] - 2.6 * H, H * 1.0), (center[0], center[1], H * 0.48), 60)

if CYCLES:
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = "GPU"
    except Exception:
        pass
else:
    scene.render.engine = "BLENDER_EEVEE"
scene.render.film_transparent = False
scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"


def set_clock(t):
    for role in ("pos", "neg"):
        MAT[role].node_tree.nodes["clock"].outputs[0].default_value = t


def studio(dark: bool):
    """가까이 찍을 때: 배양조 · 배지를 숨기고 어두운 배경 — 깨어나는 세포의 빛이 보이게."""
    for o in BATH:
        o.hide_render = dark
    bg = world.node_tree.nodes["Background"].inputs
    bg[0].default_value = (0.012, 0.014, 0.02, 1) if dark else (0.93, 0.94, 0.96, 1)
    bg[1].default_value = 1.0 if dark else 0.45


def render(cam, path, res=(1600, 1200)):
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print("렌더:", path)


set_clock(WAKE_MAX * 1.1)
studio(False)
render(hero, OUT / "sculptor.png")
studio(True)
for i, (t, lab) in enumerate(((0.0, "잠듦"), (WAKE_MED, "절반"), (WAKE_MAX * 1.1, "깨어남"))):
    set_clock(t)
    render(close, OUT / f"wake_{i}.png", (1000, 1000))

if ANIM:
    # 1~72: 아래에서 위로 쌓임 · 73~144: 발에서 깨어남.
    # 쌓기는 재질 안에서 높이 위를 투명하게 (형상을 다시 계산하지 않아 빠름)
    FB, FE = 72, 144
    scene.frame_start, scene.frame_end = 1, FE

    for role in ("pos", "neg", "mem"):
        nt = MAT[role].node_tree
        out = nt.nodes["Material Output"]
        shader = out.inputs["Surface"].links[0].from_socket
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        h = nt.nodes.new("ShaderNodeValue")
        h.name = h.label = "height"
        cmp_ = nt.nodes.new("ShaderNodeMath")
        cmp_.operation = "GREATER_THAN"
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(geo.outputs["Position"], sep.inputs[0])
        nt.links.new(sep.outputs["Z"], cmp_.inputs[0])
        nt.links.new(h.outputs[0], cmp_.inputs[1])
        nt.links.new(cmp_.outputs[0], mix.inputs["Fac"])
        nt.links.new(shader, mix.inputs[1])
        nt.links.new(tr.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        h.outputs[0].default_value = 0.0
        h.outputs[0].keyframe_insert("default_value", frame=1)
        h.outputs[0].default_value = float(H * S * 1.02)
        h.outputs[0].keyframe_insert("default_value", frame=FB)
        if role != "mem":
            try:
                MAT[role].surface_render_method = "DITHERED"
            except (AttributeError, TypeError):
                MAT[role].blend_method = "HASHED"
    for role in ("pos", "neg"):
        node = MAT[role].node_tree.nodes["clock"]
        node.outputs[0].default_value = 0.0
        node.outputs[0].keyframe_insert("default_value", frame=FB)
        node.outputs[0].default_value = WAKE_MAX * 1.1
        node.outputs[0].keyframe_insert("default_value", frame=FE)
    scene.camera = close
    scene.render.resolution_x, scene.render.resolution_y = 720, 720
    try:
        scene.eevee.taa_render_samples = 16
    except AttributeError:
        pass
    scene.render.fps = 24
    im = scene.render.image_settings
    try:
        if hasattr(im, "media_type"):  # Blender 5: 동영상은 media_type 부터
            im.media_type = "VIDEO"
        im.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.filepath = str(OUT / "being.mp4")
        bpy.ops.render.render(animation=True)
    except (TypeError, AttributeError):  # 동영상 출력이 없으면 PNG 프레임 → 시스템 ffmpeg
        import shutil
        import subprocess

        if hasattr(im, "media_type"):
            im.media_type = "IMAGE"
        im.file_format = "PNG"
        frames = OUT / "frames"
        frames.mkdir(exist_ok=True)
        scene.render.filepath = str(frames / "f_####")
        bpy.ops.render.render(animation=True)
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "24", "-i", str(frames / "f_%04d.png"),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(OUT / "being.mp4")], check=True)
            shutil.rmtree(frames)
    if hasattr(im, "media_type"):
        im.media_type = "IMAGE"
    im.file_format = "PNG"
    print("동영상:", OUT / "being.mp4")

set_clock(WAKE_MAX * 1.1)
studio(False)
scene.camera = hero
bpy.ops.wm.save_as_mainfile(filepath=str((OUT / "sculptor.blend").resolve()))
print("저장:", OUT / "sculptor.blend")
