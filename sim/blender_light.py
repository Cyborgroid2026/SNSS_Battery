"""Blender 장면: SNSS 빛 조각가 SC-2 — 배지가 모니터. 수조 위 두 색 프로젝터 · 잉크 우물 · 자라는 존재 · 물속 도구 갠트리(주차) · 수조 아래 데스크톱.

    blender -b --factory-startup --python sim/blender_light.py -- <빛 작업 폴더> <출력 폴더> [--layer K] [--cycles]

빛 작업 폴더 = python -m snss_battery light … 가 만든 sculpt_out/light_jobs/NN_… (summary.json · layout.json · exposure.npz · <이름>_mesh.npz).
좌표: mm × 0.01 = Blender 단위, 프레임 바닥 가운데가 원점 (layout.json 과 같음). 노광면 = 배지 수면.
K 층까지 자란 순간: 받침이 내려가 K 층 윗면이 수면에 있고, 수면에는 그 층의 빛 그림(보라 405 · 초록 530 nm)이 비침.
"""

import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
JOB = Path(argv[0]) if argv else Path("sculpt_out/light_jobs/01_being")
OUT = Path(argv[1]) if len(argv) > 1 and not argv[1].startswith("--") else JOB / "blender"
CYCLES = "--cycles" in argv
S = 0.01
OUT.mkdir(parents=True, exist_ok=True)

summary = json.loads((JOB / "summary.json").read_text(encoding="utf-8"))
LAY = json.loads((JOB / "layout.json").read_text(encoding="utf-8"))
ex = np.load(JOB / "exposure.npz")
E, G = ex["E_mj_cm2"], ex["G_mj_cm2"]
PX, PZ = (float(v) for v in ex["pitch"])
OX, OY = (int(v) for v in ex["offset"])
NAME = summary["name"]
layers = np.nonzero(E.max(axis=(0, 1)) > 0)[0]
K = int(argv[argv.index("--layer") + 1]) if "--layer" in argv else int(layers[int(len(layers) * 0.62)])
FILL = LAY["z_tip"]  # 노광면 = 수면
DZ = FILL - (K + 1) * PZ  # 작업물 바닥(받침 윗면)의 장면 높이
TANK_IN, Z0 = 350, -4  # 36 큐브 수조 안 350 · 안쪽 바닥

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"


# ---------- 재질 · 도형 ----------
def principled(name, color, rough=0.5, alpha=1.0, metallic=0.0, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    if not m.node_tree:
        m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Alpha"].default_value = alpha
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


def above_surface_hidden(m):
    """수면 위(아직 빚지 않은 층)는 투명 — 형상을 다시 계산하지 않고 재질에서 자름."""
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    shader = out.inputs["Surface"].links[0].from_socket
    geo, sep = nt.nodes.new("ShaderNodeNewGeometry"), nt.nodes.new("ShaderNodeSeparateXYZ")
    cmp_ = nt.nodes.new("ShaderNodeMath")
    cmp_.operation = "GREATER_THAN"
    cmp_.inputs[1].default_value = FILL * S
    tr, mix = nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], cmp_.inputs[0])
    nt.links.new(cmp_.outputs[0], mix.inputs["Fac"])
    nt.links.new(shader, mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    for attr, val in (("surface_render_method", "DITHERED"), ("blend_method", "HASHED")):
        try:
            setattr(m, attr, val)
            break
        except (AttributeError, TypeError):
            pass


MAT = {
    "glass": principled("배양조 (유리)", (0.9, 0.95, 1.0), 0.02, alpha=0.14),
    "bath": principled("배지 (멸균생리식염수)", (0.72, 0.88, 0.97), 0.02, alpha=0.12),
    "ink": principled("잉크층 (GO · 감광 PVA · NBD · 에오신 Y, NaCl 10 mM)", (0.09, 0.06, 0.04), 0.1, alpha=0.5),
    "petg": principled("PETG (출력 부품)", (0.95, 0.42, 0.08), 0.4),
    "cf": principled("탄소섬유 봉", (0.04, 0.04, 0.05), 0.3, metallic=0.2),
    "nylon": principled("나일론 나사봉", (0.92, 0.9, 0.84), 0.5),
    "graphite": principled("흑연", (0.06, 0.06, 0.07), 0.35, metallic=0.3),
    "dark": principled("검은 부품", (0.03, 0.03, 0.035), 0.5),
    "bed": principled("배양 받침", (0.88, 0.9, 0.93), 0.3),
    "xps": principled("XPS 단열판", (0.55, 0.75, 0.95), 0.8),
    "wood": principled("받침대 (합판)", (0.55, 0.42, 0.3), 0.6),
    "silicone": principled("IP68 실리콘 (키보드 · 마우스)", (0.2, 0.32, 0.42), 0.55),
    "pc": principled("데스크톱 케이스", (0.1, 0.1, 0.12), 0.4, metallic=0.4),
    "beam405": principled("405 nm 빛길", (0.45, 0.2, 1.0), 0.3, alpha=0.06, emission=(0.45, 0.2, 1.0), strength=1.5),
    "lens": principled("광엔진 렌즈", (0.45, 0.2, 1.0), 0.1, emission=(0.6, 0.45, 1.0), strength=8),
    "mem": principled("막 · 피부 (GO/PVA)", hexrgb("#8f9aa6"), 0.35, alpha=0.25),
    "pos": principled("p 세포질 (+, NBD 접목 rGO)", hexrgb("#e0344b"), 0.45),
    "neg": principled("n 세포질 (−, rGO)", hexrgb("#2f6db5"), 0.45),
}
for r in ("mem", "pos", "neg"):
    above_surface_hidden(MAT[r])


def box(name, size, loc, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=[v * S for v in loc])
    o = bpy.context.object
    o.name = name
    o.scale = [v * S for v in size]
    o.data.materials.append(mat)
    return o


def cyl(name, r, depth, loc, mat, rot=(0, 0, 0), verts=32):
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
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = [v * S for v in p]
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(mat)
    bpy.context.collection.objects.link(o)
    return o


def collection(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[name]
    return c


def lay_obj(b, dz=0.0):
    lo, hi = b["lo"], b["hi"]
    c = [(lo[k] + hi[k]) / 2 for k in range(3)]
    c[2] += dz
    size = [hi[k] - lo[k] for k in range(3)]
    n = b["name"]
    mat = MAT["cf"] if "탄소섬유" in n else MAT["nylon"] if "나일론" in n else MAT["graphite"] if "전극" in n else \
        MAT["dark"] if "케이블" in n else MAT["petg"]
    if b["shape"] == "cyl_z":
        return cyl(n, size[0] / 2, size[2], c, mat)
    if "탄소섬유 봉" in n:
        ax = max(range(3), key=lambda k: size[k])
        return cyl(n, min(size) / 2, size[ax], c, mat, rot={0: (0, math.pi / 2, 0), 1: (math.pi / 2, 0, 0), 2: (0, 0, 0)}[ax], verts=16)
    return box(n, size, c, mat)


# ---------- 배양조 · 기계 (layout.json) ----------
collection("빛 조각가 SC-2")
tank = box("배양조 — 36 큐브 유리 수조", (TANK_IN + 8, TANK_IN + 8, TANK_IN + 6), (0, 0, Z0 + TANK_IN / 2 - 3), MAT["glass"])
bath = box("배지 (멸균생리식염수)", (TANK_IN - 2, TANK_IN - 2, FILL - Z0), (0, 0, (FILL + Z0) / 2), MAT["bath"])
for b in LAY["boxes"]:
    if b["kind"] in ("frame", "static") and "프로젝터" not in b["name"]:
        lay_obj(b)
    elif b["kind"] == "well":
        lay_obj(b)
    elif b["kind"] == "gantry" and "(쓸림)" not in b["name"]:  # 물속 도구 갠트리 — 빛을 쬐는 동안 뒤쪽에 주차
        lay_obj(b)
# 받침이 내려간 만큼: 받침 · 기둥 · 너트 판 (layout 은 가장 높을 때)
nut = next(b for b in LAY["boxes"] if b["name"].startswith("받침 너트 판"))
drop = FILL - PZ - DZ  # 처음(첫 층이 수면) 에서 지금까지 내려간 거리
lay_obj(nut, -drop)
box("배양 받침", (120, 120, 6), (0, 0, DZ - 3), MAT["bed"])
box("받침 기둥", (40, 40, 40), (0, 0, DZ - 26), MAT["petg"])
for sx in (-1, 1):
    box(f"흑연 패드 {'+' if sx < 0 else '−'}", (14, 22, 0.8), (sx * 9.5, 2.5, DZ - 0.4), MAT["graphite"])
# 잉크층 (테 안, 수면에서 아래로)
well = [b for b in LAY["boxes"] if b["kind"] == "well"]
w_in = min(abs(b["lo"][1]) for b in well if "(X)" in b["name"] and b["lo"][1] > 0) if well else 75
ink = box("잉크층", (2 * w_in - 1, 2 * w_in - 1, summary["spec"]["ink"]["depth_mm"]),
          (0, 0, FILL - summary["spec"]["ink"]["depth_mm"] / 2), MAT["ink"])

# ---------- 프로젝터 · 빛길 · 수면의 빛 그림 ----------
pj = next(b for b in LAY["boxes"] if "프로젝터" in b["name"])
lay_obj(pj)
gz = LAY["gz"]
cyl("광엔진 렌즈 (405 + 530 nm)", 12, 6, (0, 0, gz - 3), MAT["lens"])
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=55 * math.sqrt(2) * S, radius2=8 * S, depth=(gz - FILL) * S,
                                location=(0, 0, (gz + FILL) / 2 * S), rotation=(0, 0, math.pi / 4))
bpy.context.object.name = "빛길 (프로젝터 → 수면)"
bpy.context.object.data.materials.append(MAT["beam405"])

nx, ny = E.shape[:2]
e_max = float(np.percentile(E[E > 0], 99))
g_max = float(G.max()) or 1.0
e = np.clip(E[:, :, K].T / e_max, 0, 1)
g = np.clip(G[:, :, K].T / g_max, 0, 1)
rgba = np.stack([0.62 * e, g, e, np.maximum(e, g) > 0.01], -1).astype(np.float32)
img = bpy.data.images.new(f"층 {K} 빛 그림", nx, ny, alpha=True)
img.pixels.foreach_set(rgba.ravel())
img.pack()
fm = bpy.data.materials.new("수면의 빛 그림")
if not fm.node_tree:
    fm.use_nodes = True
nt = fm.node_tree
nt.nodes.remove(nt.nodes["Principled BSDF"])
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
tex.interpolation = "Closest"
em, tr, mix = nt.nodes.new("ShaderNodeEmission"), nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeMixShader")
em.inputs["Strength"].default_value = 4.0
nt.links.new(tex.outputs["Color"], em.inputs["Color"])
nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
nt.links.new(tr.outputs[0], mix.inputs[1])
nt.links.new(em.outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
    try:
        setattr(fm, attr, val)
        break
    except (AttributeError, TypeError):
        pass
bpy.ops.mesh.primitive_plane_add(size=1, location=((OX + nx / 2) * PX * S, (OY + ny / 2) * PX * S, (FILL + 0.3) * S))
frame = bpy.context.object
frame.name = f"수면 = 모니터 (층 {K})"
frame.scale = (nx * PX * S, ny * PX * S, 1)
frame.data.materials.append(fm)

# ---------- 자라는 존재 (K 층까지, 받침과 함께 내려감) ----------
collection(f"존재 — {NAME}")
mz = np.load(JOB / f"{NAME}_mesh.npz")
for role, label in (("pos", "p 세포질"), ("neg", "n 세포질"), ("mem", "막 · 피부")):
    if f"{role}_v" not in mz.files:
        continue
    v = mz[f"{role}_v"].astype(np.float64)
    v[:, 2] += DZ
    f = mz[f"{role}_f"]
    me = bpy.data.meshes.new(label)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", (v * S).astype(np.float32).ravel())
    me.loops.add(len(f) * 3)
    me.loops.foreach_set("vertex_index", f.astype(np.int32).ravel())
    me.polygons.add(len(f))
    me.polygons.foreach_set("loop_start", np.arange(0, len(f) * 3, 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.materials.append(MAT[role])
    bpy.context.collection.objects.link(bpy.data.objects.new(label, me))

# ---------- 수조 아래 데스크톱 · 방수 키보드 · 마우스 (모니터 없음 — 수조가 모니터) ----------
collection("데스크톱 (수조 아래)")
gb = Z0 - 6  # 유리 바닥 아래
box("XPS 단열판 30 mm (+ 바람길)", (TANK_IN + 20, TANK_IN + 20, 30), (0, 0, gb - 15 - 12), MAT["xps"])
for sx in (-1, 1):
    for sy in (-1, 1):
        box("받침대 다리", (30, 30, 520), (sx * 200, sy * 200, gb - 42 - 260), MAT["wood"])
box("받침대 윗판 (바람길 틈 12 mm 위)", (430, 430, 18), (0, 0, gb - 42 - 9 + 12), MAT["wood"])
box("받침대 바닥판", (430, 430, 18), (0, 0, gb - 42 - 520 + 9), MAT["wood"])
box("데스크톱 (GPU · Blender · 콘솔)", (210, 430, 450), (-80, 0, gb - 42 - 520 + 18 + 225), MAT["pc"])
box("키보드 서랍", (430, 200, 14), (0, -310, gb - 140), MAT["wood"])
box("IP68 실리콘 키보드", (360, 120, 16), (-30, -320, gb - 125), MAT["silicone"])
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(190 * S, -320 * S, (gb - 126) * S))
mouse = bpy.context.object
mouse.name = "IP68 방수 마우스"
mouse.scale = (32 * S, 55 * S, 18 * S)
mouse.data.materials.append(MAT["silicone"])
bpy.ops.object.shade_smooth()
tube("HDMI (데스크톱 → 프로젝터)", [(-80, 220, gb - 300), (-120, 230, 200), (-90, 210, gz + 30), (-60, 0, gz + 30)], 3, MAT["dark"])
tube("Z 모터 · 전극 케이블", [(156, 0, FILL + 20), (200, 0, FILL + 10), (220, 120, gb - 200), (30, 150, gb - 300)], 3, MAT["dark"])

# ---------- 빛 · 카메라 · 렌더 ----------
for loc, en in (((1.8, -2.6, 4.6), 900), ((-3.0, 1.0, 2.2), 300)):
    bpy.ops.object.light_add(type="AREA", location=loc)
    bpy.context.object.data.energy = en
    bpy.context.object.data.size = 3
world = bpy.data.worlds.new("배경")
if not world.node_tree:
    world.use_nodes = True
bg = world.node_tree.nodes["Background"].inputs
bg[0].default_value = (0.93, 0.94, 0.96, 1)
bg[1].default_value = 0.6
scene.world = world


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
    c.target, c.track_axis, c.up_axis = t, "TRACK_NEGATIVE_Z", "UP_Y"
    return o


hero = camera("전체", (1300, -1900, 900), (0, -60, 60), 40)
close = camera("수면 (모니터)", (90, -150, FILL + 120), ((OX + nx / 2) * PX, (OY + ny / 2) * PX, FILL - 15), 55)

if CYCLES:
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
else:
    scene.render.engine = "BLENDER_EEVEE"
scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"


def render(cam, path, res=(1600, 1200)):
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print("렌더:", path)


render(hero, OUT / "light_scene.png")
for o in (tank, bath, ink):  # 가까이: 유리 · 배지 · 잉크를 숨기고 어두운 배경 — 빛 그림과 막 아래 세포가 보이게
    o.hide_render = True
bg[0].default_value, bg[1].default_value = (0.012, 0.014, 0.02, 1), 1.0
render(close, OUT / "light_surface.png", (1200, 1000))
for o in (tank, bath, ink):
    o.hide_render = False
bg[0].default_value, bg[1].default_value = (0.93, 0.94, 0.96, 1), 0.6
scene.camera = hero
bpy.ops.wm.save_as_mainfile(filepath=str((OUT / "light.blend").resolve()))
print("저장:", OUT / "light.blend", f"(층 {K})")
