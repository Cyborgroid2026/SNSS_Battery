"""실험대 19단계 — 물리 엔진 렌더 (Blender 5: Mantaflow 유체 · Bullet 강체 · Cycles 경로 추적) (명세: spec/PHYSICS.md §렌더).

    blender -b --factory-startup --python sim/blender_bench.py -- <physics.json> <출력 폴더> [--steps take,mix] [--samples 96] [--quick] [--rebake]

Mantaflow 캐시(<출력>/cache_*)가 있으면 다시 굽지 않고 씀 — 물리 값을 바꿨으면 --rebake.

physics.json = snss_battery.benchphys 결과 (report/make_pptx.py · ./tools.sh bench-render 가 만듦). 단계마다 그 숫자로 장면을 움직인다:
- Mantaflow FLIP 유체: take(식염수 붓기) · refill(진한 혼합액을 깔때기로) — 점도 ν = μ/ρ, 표면장력 그대로.
  교반 (disperse · mix): 300 rpm 자석 막대를 '유도(GUIDE)' 효과체로 — 막대가 지나는 칸에 막대 속도를 줌.
  막대를 충돌체로 두면 FLIP 입자가 지워져 부피가 줄었음 (시험: 2 s 에 58 → 35 mm). 유도는 부피 보존 (평균 액면 그대로).
  엔진이 만든 소용돌이 깊이(가운데 ↔ 벽)를 engine.json 에 적어 benchphys 의 랭킨 어림과 나란히 보임.
- Bullet 강체: weigh(PVA 알갱이가 쌓이는 안식각) · disperse(Mantaflow 가 만든 소용돌이 면을 충돌면으로 — 알갱이가 가운데로).
- 기포: 스토크스 종단 속도로 떠오르는 입자 (degas). 동결 전선: FEniCSx 가운데 기둥 (dfreeze · ft). 해동 얼음 심: 스테판.
- 겔 처짐: 선형 탄성 ε(z) = ρg(H − z)/E, 옆으로 ν = 0.5 (demold).
- 색: GO 흡광 ε(550 nm) ≈ 2.5 mL·mg⁻¹·cm⁻¹ (가정) → 흡수 계수 ln10·ε·c (0.5 mg/mL → 290 m⁻¹).
좌표: 미터 (실제 크기). 각 단계 그림 = <출력>/stepNN.png (2.54 : 1, 발표 자료와 같은 비).
"""

import json
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PHYS = {s["id"]: s for s in json.loads(Path(argv[0]).read_text(encoding="utf-8"))}
ORDER = list(PHYS)
OUT = Path(argv[1])
OUT.mkdir(parents=True, exist_ok=True)
QUICK = "--quick" in argv
ONLY = argv[argv.index("--steps") + 1].split(",") if "--steps" in argv else ORDER
SAMPLES = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else (24 if QUICK else 96)
RES = (915, 360) if QUICK else (1830, 720)
FLUID_RES = 48 if QUICK else 96
LN10 = math.log(10)


# ---------- 재질 ----------
def mat(name, color=(0.8, 0.8, 0.8), rough=0.4, metal=0.0, trans=0.0, ior=1.45, emit=None, strength=0.0, alpha=1.0,
        absorb=None, scatter=None, coat=0.0, sss=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    if not m.node_tree:
        m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Transmission Weight"].default_value = trans
    b.inputs["IOR"].default_value = ior
    b.inputs["Alpha"].default_value = alpha
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Subsurface Weight"].default_value = sss
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    out = nt.nodes["Material Output"]
    if absorb or scatter:  # 순수 흡수 (색 = 지나가는 빛, 계수 m⁻¹) + 흐림 (산란)
        vols = []
        if absorb:
            va = nt.nodes.new("ShaderNodeVolumeAbsorption")
            va.inputs["Color"].default_value = (*absorb[0], 1)
            va.inputs["Density"].default_value = absorb[1]
            vols.append(va)
        if scatter:
            vs = nt.nodes.new("ShaderNodeVolumeScatter")
            vs.inputs["Color"].default_value = (0.95, 0.95, 0.95, 1)
            vs.inputs["Density"].default_value = scatter
            vols.append(vs)
        if len(vols) == 2:
            add = nt.nodes.new("ShaderNodeAddShader")
            nt.links.new(vols[0].outputs[0], add.inputs[0])
            nt.links.new(vols[1].outputs[0], add.inputs[1])
            nt.links.new(add.outputs[0], out.inputs["Volume"])
        else:
            nt.links.new(vols[0].outputs[0], out.inputs["Volume"])
    return m


def bump(m, scale=400.0, strength=0.15, kind="noise"):
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexVoronoi" if kind == "voronoi" else "ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    if kind == "voronoi":
        tex.feature = "DISTANCE_TO_EDGE"
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = strength
    nt.links.new(tex.outputs["Distance" if kind == "voronoi" else "Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def go_absorb(c_mg_ml):
    """GO 흡수 계수 (m⁻¹): ln10 · ε · c, ε ≈ 2.5 mL·mg⁻¹·cm⁻¹ (가정)."""
    return LN10 * 2.5 * c_mg_ml * 100


def M():
    return {
        "bench": mat("실험대 (밝은 페놀 상판)", (0.42, 0.43, 0.44), 0.45),
        "wall": mat("벽", (0.42, 0.47, 0.52), 0.85),
        "glass": mat("붕규산 유리", (1, 1, 1), 0.0, trans=1.0, ior=1.47),
        "pet": mat("PET 병", (0.96, 0.98, 1.0), 0.03, trans=1.0, ior=1.57),
        "saline": mat("생리식염수", (1, 1, 1), 0.0, trans=1.0, ior=1.334),
        "pva": mat("PVA 용액 (15 %)", (1, 1, 1), 0.02, trans=1.0, ior=1.36, scatter=6.0),
        "go_stock": mat("GO 분산액 4 mg/mL", (0.2, 0.12, 0.06), 0.02, trans=1.0, ior=1.334, absorb=((0.55, 0.36, 0.2), go_absorb(4.0))),
        "go_mix": mat("섞은 액 (PVA 3 % · GO 0.5 mg/mL)", (0.8, 0.6, 0.4), 0.02, trans=1.0, ior=1.34,
                      absorb=((0.62, 0.42, 0.24), go_absorb(0.5))),
        "ice": bump(mat("얼음 (GO 겔)", (0.92, 0.95, 1.0), 0.18, trans=0.85, ior=1.31, absorb=((0.7, 0.55, 0.4), go_absorb(0.5) * 0.6)),
                    3000, 0.35, "voronoi"),
        "gel": bump(mat("PVA-GO 크라이오겔", (0.55, 0.42, 0.3), 0.45, sss=0.3), 2500, 0.25, "voronoi"),
        "al": mat("알루미늄", (0.91, 0.92, 0.92), 0.32, metal=1.0),
        "steel": mat("스테인리스 (기구)", (0.75, 0.76, 0.78), 0.22, metal=1.0),
        "frost": bump(mat("서리", (0.95, 0.97, 1.0), 0.9), 800, 0.6),
        "white": mat("흰 플라스틱", (0.86, 0.87, 0.88), 0.35, coat=0.3),
        "ceramic": mat("세라믹 상판", (0.93, 0.93, 0.92), 0.25),
        "dark": mat("검은 플라스틱", (0.02, 0.02, 0.022), 0.45),
        "lcd": mat("표시창", (0.01, 0.015, 0.01), 0.2),
        "digit": mat("숫자 (초록)", (0.2, 1, 0.4), 0.5, emit=(0.25, 1.0, 0.45), strength=6),
        "red": mat("숫자 (빨강)", (1, 0.2, 0.1), 0.5, emit=(1.0, 0.25, 0.12), strength=6),
        "foam": bump(mat("스티로폼 단열재", (0.95, 0.95, 0.93), 0.8), 600, 0.4),
        "foil": mat("알루미늄 호일", (0.85, 0.86, 0.87), 0.25, metal=1.0),
        "powder": mat("PVA 알갱이", (0.97, 0.96, 0.93), 0.7),
        "graphite": mat("흑연 막대", (0.06, 0.06, 0.065), 0.45, metal=0.3),
        "copper": mat("전선 (빨강)", (0.6, 0.05, 0.04), 0.4),
        "wire_b": mat("전선 (검정)", (0.02, 0.02, 0.02), 0.4),
        "yellow": mat("멀티미터 몸체", (0.95, 0.72, 0.08), 0.4),
        "water": mat("항온수조 물", (1, 1, 1), 0.0, trans=1.0, ior=1.333),
        "acrylic": mat("아크릴", (1, 1, 1), 0.02, trans=1.0, ior=1.49),
        "ln2": mat("액체질소 김", (1, 1, 1), 1.0, alpha=0.0, scatter=60.0),
        "bubble": mat("기포", (1, 1, 1), 0.0, trans=1.0, ior=1.0 / 1.34),
        "blade": mat("면도날", (0.8, 0.82, 0.84), 0.12, metal=1.0),
        "ruler": mat("자", (0.92, 0.9, 0.82), 0.5),
        "tube": mat("실리콘 관", (0.85, 0.88, 0.9), 0.3, trans=0.5, ior=1.41),
        "sample": mat("마른 시료 (동결건조)", (0.35, 0.28, 0.22), 0.8),
        "screen": mat("화면", (0.02, 0.02, 0.025), 0.3),
    }


# ---------- 도형 ----------
def obj_from_bm(name, bm, material):
    """날카로운 모서리(30° 넘게 꺾임)는 매끄럽게 섞지 않음 — 섞으면 비커 벽 전체의 굴절 법선이 기울어 금속처럼 보임."""
    for e in bm.edges:
        if e.is_manifold and e.calc_face_angle(0.0) > math.radians(30):
            e.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def _thicken(profile, t):
    """열린 윤곽 (안쪽 면) → 바깥으로 t 만큼 두께를 준 닫힌 윤곽. 바깥 = 진행 방향의 오른쪽 (바닥은 아래, 벽은 밖)."""
    p = np.array(profile, float)
    n = np.zeros_like(p)
    for i in range(len(p) - 1):
        d = p[i + 1] - p[i]
        d /= np.linalg.norm(d) + 1e-12
        n[i] += (d[1], -d[0])
        n[i + 1] += (d[1], -d[0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    out = p + t * n
    if p[0][0] == 0:
        out[0][0] = 0.0
    return [tuple(x) for x in p] + [tuple(x) for x in out[::-1]]


def revolve(name, profile, material, loc=(0, 0, 0), segs=96, solid=0.0):
    """(r, z) 윤곽을 z 축으로 돌린 면. solid > 0 이면 윤곽(안쪽 면) 바깥으로 그 두께를 준 닫힌 입체 (유리 · PET 벽 —
    안에 넣는 액체와 겹치지 않음)."""
    closed = solid > 0
    prof = _thicken(profile, solid) if closed else profile
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in prof]
    for a, b in zip(vs[:-1], vs[1:]):
        bm.edges.new((a, b))
    if closed:
        bm.edges.new((vs[-1], vs[0]))
    bmesh.ops.spin(bm, geom=bm.verts[:] + bm.edges[:], cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=segs, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-7, edges=bm.edges[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.faces.ensure_lookup_table()
    vol = sum(f.calc_center_median().dot(f.normal) * f.calc_area() for f in bm.faces) / 3  # 발산 정리 — 밖을 보면 +
    if vol < 0:  # 굴절이 거꾸로 (1/n) 계산되지 않게 법선을 바깥으로
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    o = obj_from_bm(name, bm, material)
    o.location = loc
    return o


def box(name, size, loc, material, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    if bevel:
        b = o.modifiers.new("모서리", "BEVEL")
        b.width, b.segments = bevel, 3
    return o


def cyl(name, r, h, loc, material, rot=(0, 0, 0), verts=64):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, rotation=rot, vertices=verts)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o


def text(body, loc, size, material, rot=(math.pi / 2, 0, 0)):
    cu = bpy.data.curves.new(body, "FONT")
    cu.body = body
    cu.size = size
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.extrude = size * 0.02
    o = bpy.data.objects.new(f"글 {body}", cu)
    bpy.context.collection.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    o.data.materials.append(material)
    return o


def tube(name, pts, r, material):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 4
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu)
    o.data.materials.append(material)
    bpy.context.collection.objects.link(o)
    return o


def beaker(name, r_in, h, loc, mats, wall=0.0022):
    """비커: 바닥 두껍고 위가 열린 유리, 입구 테두리 말림."""
    prof = [(0.0, 0.0), (r_in, 0.0), (r_in, h)]
    return revolve(name, prof, mats["glass"], loc, solid=wall)


def liquid_cyl(name, r, depth, loc, material, vortex_mm=0.0, r_core=0.0):
    """원기둥 액체. 윗면은 랭킨 소용돌이 (가운데 Δh 아래로, 바깥 1/r² 로 회복) — 부피 보존하게 평균 높이를 맞춤."""
    n_r = 40
    rs = np.linspace(0, r, n_r)
    dh = vortex_mm / 1000
    rc = max(r_core, 1e-4)
    shape = np.where(rs < rc, -dh * (1 - 0.5 * (rs / rc) ** 2), -dh * 0.5 * (rc / np.maximum(rs, 1e-9)) ** 2)
    mean = np.sum(shape * rs) / np.sum(rs) if dh else 0.0
    top = depth + shape - mean
    prof = [(0.0, 0.0), (r, 0.0)] + [(float(rr), float(z)) for rr, z in zip(rs[::-1], top[::-1])]
    return revolve(name, prof, material, loc, segs=96)


def bottle_profile(scale=1.0):
    """약국 생리식염수 500 mL PET 병 (안지름 70.4 mm) — 몸통 · 어깨 · 목."""
    r, H = 0.0352, 0.155
    pts = [(0.0, 0.0), (r - 0.004, 0.0), (r, 0.004), (r, H)]
    for k in range(1, 9):
        t = k / 8
        pts.append((r - (r - 0.0125) * (1 - math.cos(t * math.pi / 2)), H + 0.03 * math.sin(t * math.pi / 2)))
    pts += [(0.0125, H + 0.045), (0.0135, H + 0.046), (0.0135, H + 0.052)]
    return [(x * scale, z * scale) for x, z in pts], H


def bottle(name, loc, mats, cap=True, rot=(0, 0, 0)):
    prof, H = bottle_profile()
    o = revolve(name, [(x - 0.0008 if x > 0 else 0.0, z) for x, z in prof], mats["pet"], loc, solid=0.0008)
    o.rotation_euler = rot
    if cap:
        c = cyl("병뚜껑", 0.0145, 0.014, (0, 0, H + 0.058), mats["white"])
        c.parent = o
    return o, H


def env(mats):
    """실험실: 에폭시 실험대 · 벽 · 소프트박스 빛 · 회색 하늘."""
    box("실험대", (2.4, 1.0, 0.04), (0, 0.1, -0.02), mats["bench"])
    box("벽", (2.4, 0.02, 1.2), (0, 0.42, 0.6), mats["wall"])
    for loc, size, power in (((0.3, -1.0, 1.2), 1.2, 45), ((-1.0, -0.2, 0.6), 0.8, 12), ((0.9, 0.3, 0.6), 0.6, 9)):
        bpy.ops.object.light_add(type="AREA", location=loc)
        L = bpy.context.object
        L.data.size, L.data.energy = size, power
        L.visible_camera = False
        L.rotation_euler = (Vector((0, 0.1, 0.05)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    w = bpy.data.worlds.new("실험실")
    bpy.context.scene.world = w
    if not w.node_tree:
        w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.86, 0.88, 0.9, 1)  # 밝은 실험실 — 유리 옆면이 비추는 주변
    bg.inputs[1].default_value = 0.75


ENV = ("실험대", "벽")


def scene_bbox():
    """보이는 물체(실험대 · 벽 · 숨긴 충돌체 빼고)의 세계 좌표 경계 상자."""
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.hide_render or o.name in ENV or o.name.startswith("알갱이"):
            continue
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    a = np.array([p[:] for p in pts])
    return a.min(0), a.max(0), a


def camera(loc, target, lens=50, fstop=0.0, focus=None, margin=1.1):
    """보는 방향은 (target − loc) — 거리 · 겨냥은 장면 경계 상자가 화면에 꼭 들어오게 자동 (2.54 : 1)."""
    cam = bpy.data.cameras.new("카메라")
    cam.lens = lens
    cam.clip_start = 0.005
    o = bpy.data.objects.new("카메라", cam)
    bpy.context.scene.collection.objects.link(o)
    fwd = (Vector(target) - Vector(loc)).normalized()
    rot = fwd.to_track_quat("-Z", "Y")
    o.rotation_euler = rot.to_euler()
    lo, hi, corners = scene_bbox()
    c = Vector(((lo + hi) / 2).tolist())
    right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
    th = 18 / lens  # 센서 가로 36 mm
    tv = th / (RES[0] / RES[1])
    d = 0.0
    for p in corners:
        q = Vector(p.tolist()) - c
        d = max(d, abs(q.dot(right)) / th - q.dot(fwd), abs(q.dot(up)) / tv - q.dot(fwd))
    d *= margin
    o.location = c - fwd * d
    if fstop:
        cam.dof.use_dof, cam.dof.aperture_fstop = True, fstop
        cam.dof.focus_distance = (Vector(focus) - o.location).length if focus else d
    bpy.context.scene.camera = o
    return o


def hotplate(loc, mats, temp=None, rpm=300):
    x, y, z = loc
    box("핫플레이트 몸체", (0.18, 0.2, 0.09), (x, y, z + 0.045), mats["white"], bevel=0.008)
    box("세라믹 상판", (0.17, 0.17, 0.006), (x, y + 0.008, z + 0.093), mats["ceramic"], bevel=0.002)
    box("표시창", (0.06, 0.003, 0.022), (x - 0.035, y - 0.1, z + 0.055), mats["lcd"])
    for i, (val, m_) in enumerate(((f"{temp:.0f}C" if temp is not None else "OFF", mats["red"]), (f"{rpm}", mats["digit"]))):
        text(val, (x - 0.035 + (0 if i == 0 else 0.07), y - 0.1025, z + 0.055), 0.012, m_)
    cyl("손잡이", 0.011, 0.012, (x + 0.05, y - 0.104, z + 0.045), mats["dark"], rot=(math.pi / 2, 0, 0))
    return z + 0.096


def balance(loc, mats, reading):
    x, y, z = loc
    box("저울 몸체", (0.2, 0.26, 0.07), (x, y, z + 0.035), mats["white"], bevel=0.01)
    cyl("저울 접시", 0.065, 0.004, (x, y + 0.03, z + 0.075), mats["steel"])
    box("저울 표시창", (0.08, 0.003, 0.024), (x, y - 0.131, z + 0.04), mats["lcd"])
    text(reading, (x, y - 0.1325, z + 0.04), 0.013, mats["digit"])
    return z + 0.077


def render(step_no, sid):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception:  # noqa: BLE001
        pass
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
    sc.cycles.volume_bounces = 2
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.view_settings.view_transform = "AgX"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(OUT / f"step{step_no:02d}.png")
    bpy.ops.render.render(write_still=True)
    print("렌더:", sc.render.filepath, sid)


# ---------- 물리 엔진 ----------
def bake_fluid(domain, frames, cache, key=None):
    """굽기. key(그 장면의 물리 값)가 캐시에 적힌 것과 같으면 다시 굽지 않고 읽음."""
    sc = bpy.context.scene
    ds = domain.modifiers["Fluid"].domain_settings
    ds.cache_type = "ALL"
    ds.cache_directory = str(cache)
    ds.cache_frame_start, ds.cache_frame_end = 1, frames
    sc.frame_start, sc.frame_end = 1, frames
    t = time.time()
    last = Path(cache) / "mesh" / f"fluid_mesh_{frames:04d}.bobj.gz"
    n = 0
    kf = Path(cache) / "key.json"
    key = json.dumps({**(key or {}), "frames": frames, "res": FLUID_RES}, sort_keys=True, default=str)
    same = kf.exists() and kf.read_text(encoding="utf-8") == key
    if last.exists() and same and "--rebake" not in argv:  # 같은 장면 · 같은 물리 값이면 캐시를 읽음 (교반은 한 번에 30 분)
        sc.frame_set(frames)
        n = len(domain.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices)
        if n > 8:
            print(f"Mantaflow 캐시 다시 씀 ({cache}) — 다시 구우려면 --rebake")
    if n <= 8:
        with bpy.context.temp_override(object=domain, active_object=domain, scene=sc):
            bpy.ops.fluid.bake_all()
        sc.frame_set(frames)
        n = len(domain.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices)
        kf.parent.mkdir(parents=True, exist_ok=True)
        kf.write_text(key, encoding="utf-8")
    print(f"Mantaflow 굽기 {time.time() - t:.0f} s · 액체 메시 꼭짓점 {n}")
    if n <= 8:
        raise RuntimeError("Mantaflow 가 액체를 만들지 못함 (흘러나오는 곳이 충돌체 안?)")


def fluid_domain(center, size, viscosity_si, rho, sigma, res):
    """Mantaflow 액체 영역: ν = μ/ρ 를 (밑수 × 10^−지수) 로, 표면장력은 N/m 그대로 (Mantaflow 무차원 값으로 0.07 → 0.07)."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    d = bpy.context.object
    d.name = "Mantaflow 영역"
    d.scale = size
    bpy.ops.object.transform_apply(scale=True)
    m = d.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    ds = m.domain_settings
    ds.domain_type = "LIQUID"
    ds.resolution_max = res
    ds.use_mesh = True
    ds.mesh_particle_radius = 1.4
    nu = viscosity_si / rho
    ex = math.floor(-math.log10(nu)) + 1
    ds.use_viscosity = nu > 3e-6
    ds.viscosity_base, ds.viscosity_exponent = nu * 10 ** ex, ex
    ds.surface_tension = sigma
    ds.use_adaptive_timesteps = True
    ds.mesh_scale = 1 if QUICK else 2  # 액면 메시를 격자보다 2배 곱게
    ds.mesh_smoothen_pos, ds.mesh_smoothen_neg = 2, 2
    return d


ENGINE_OUT = {}


def stir_fluid(r_in, depth, bar_len, rpm, mu, rho, base, frames, cache, res):
    """자석 막대 교반 — Mantaflow (막대 = 유도 효과체). base = 비커 안 바닥 (x, y, z). 끝 프레임의 영역(액체 메시)과 깊이를 돌려줌."""
    x0, y0, z0 = base
    hole = cyl("비커 안쪽", r_in, 0.4, (x0, y0, z0 + 0.2), M()["glass"])
    hz = depth + 0.03
    dom = fluid_domain((x0, y0, z0 + hz / 2 - 0.001), (2 * r_in + 0.008, 2 * r_in + 0.008, hz), mu, rho, 0.07, res)
    collider_with_hole("비커 충돌체", (2 * r_in + 0.03, 2 * r_in + 0.03, hz + 0.03), (x0, y0, z0 + hz / 2 - 0.01), hole)
    bpy.ops.mesh.primitive_cylinder_add(radius=r_in - 0.0008, depth=depth, location=(x0, y0, z0 + depth / 2), vertices=48)
    liq = bpy.context.object
    liq.name = "처음 액체"
    lf = liq.modifiers.new("Fluid", "FLUID")
    lf.fluid_type, lf.flow_settings.flow_type, lf.flow_settings.flow_behavior = "FLOW", "LIQUID", "GEOMETRY"
    liq.hide_render = True
    ang = 2 * math.pi * rpm / 60 * (frames - 1) / 24
    objs = []
    for name, size, guide in (("교반 막대 (유도)", (bar_len, max(0.008, 2.5 * 2 * r_in / res), 0.008), True),
                              ("교반 막대", (bar_len, 0.008, 0.008), False)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x0, y0, z0 + 0.0045))
        o = bpy.context.object
        o.name = name
        o.scale = size
        bpy.ops.object.transform_apply(scale=True)
        if not guide:
            bev = o.modifiers.new("둥글게", "BEVEL")
            bev.width, bev.segments = 0.0039, 4
            o.data.materials.append(M()["white"])
        o.rotation_mode = "XYZ"
        o.rotation_euler = (0, 0, 0)
        o.keyframe_insert("rotation_euler", frame=1)
        o.rotation_euler = (0, 0, ang)
        o.keyframe_insert("rotation_euler", frame=frames)
        _linear(o)
        objs.append(o)
    g = objs[0]
    gm = g.modifiers.new("Fluid", "FLUID")
    gm.fluid_type = "EFFECTOR"
    es = gm.effector_settings
    es.effector_type, es.guide_mode, es.velocity_factor, es.subframes = "GUIDE", "AVERAGED", 1.0, 2
    g.hide_render = True
    ds = dom.modifiers["Fluid"].domain_settings
    ds.use_guide, ds.guide_source, ds.guide_vel_factor = True, "EFFECTOR", 1.0
    bake_fluid(dom, frames, cache, {"r_in": r_in, "depth": depth, "bar": bar_len, "rpm": rpm, "mu": mu, "rho": rho})
    ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
    pts = [(v.co - Vector((x0, y0, 0))) for v in ev.data.vertices]
    rr = [math.hypot(p.x, p.y) for p in pts]
    c = [p.z for p, r in zip(pts, rr) if r < 0.15 * r_in]
    w = [p.z for p, r in zip(pts, rr) if r > 0.85 * r_in]
    dh = (max(w) - max(c)) * 1000 if c and w else float("nan")
    print(f"Mantaflow 소용돌이 깊이 (가운데 ↔ 벽) {dh:.1f} mm")
    return dom, dh


def _linear(o):
    """회전 키프레임을 일정한 빠르기로 (Blender 5 의 층 액션 · 옛 액션 둘 다)."""
    act = o.animation_data.action
    try:
        fcs = act.fcurves
    except AttributeError:
        from bpy_extras import anim_utils

        fcs = anim_utils.action_get_channelbag_for_slot(act, o.animation_data.action_slot).fcurves
    for fc in fcs:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def collider_with_hole(name, block_size, block_center, hole_obj):
    """영역을 꽉 채운 블록에서 그릇 안쪽을 파냄 (얇은 벽 사이로 FLIP 입자가 새지 않게)."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=block_center)
    b = bpy.context.object
    b.name = name
    b.scale = block_size
    bpy.ops.object.transform_apply(scale=True)
    bo = b.modifiers.new("구멍", "BOOLEAN")
    bo.operation, bo.object, bo.solver = "DIFFERENCE", hole_obj, "EXACT"
    with bpy.context.temp_override(object=b, active_object=b, selected_objects=[b]):
        bpy.ops.object.modifier_apply(modifier="구멍")
    hole_obj.hide_render = True
    m = b.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "EFFECTOR"
    m.effector_settings.effector_type = "COLLISION"
    b.hide_render = True
    return b


def inflow(loc, r, vel, rot=(0, 0, 0), until=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=r * 1.5, location=loc, rotation=rot, vertices=24)
    o = bpy.context.object
    o.name = "흘러나옴 (inflow)"
    m = o.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "FLOW"
    fs = m.flow_settings
    fs.flow_type, fs.flow_behavior, fs.flow_source = "LIQUID", "INFLOW", "MESH"
    fs.use_initial_velocity = True
    fs.velocity_coord = vel
    o.hide_render = True
    if until:
        fs.use_inflow = True
        fs.keyframe_insert("use_inflow", frame=until - 1)
        fs.use_inflow = False
        fs.keyframe_insert("use_inflow", frame=until)
    return o


def rigid_grains(n, center, spread, r, mats, seed=1, mass=1e-5):
    """Bullet: 알갱이 n 개 (지름 2r, 확대 표현) — 숟가락 끝에서 떨어지게 위에 흩뿌림."""
    rng = np.random.default_rng(seed)
    sc = bpy.context.scene
    if sc.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    rw = sc.rigidbody_world
    rw.substeps_per_frame, rw.solver_iterations = 60, 20  # 1 m/s 로 떨어져도 한 단계에 알갱이 반지름보다 덜 움직이게
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=r, location=(0, 0, -1))
    proto = bpy.context.object
    proto.data.materials.append(mats["powder"])
    grains = []
    for i in range(n):
        o = proto.copy()
        o.data = proto.data
        o.name = f"알갱이 {i}"
        o.location = Vector(center) + Vector((rng.normal(0, spread), rng.normal(0, spread), rng.uniform(0, spread * 4)))
        o.rotation_euler = tuple(rng.uniform(0, 6.28, 3))
        o.scale = (1, rng.uniform(0.7, 1.0), rng.uniform(0.6, 1.0))
        bpy.context.collection.objects.link(o)
        grains.append(o)
    bpy.data.objects.remove(proto)
    for o in grains:
        with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
            bpy.ops.rigidbody.object_add(type="ACTIVE")
        o.rigid_body.mass, o.rigid_body.friction, o.rigid_body.restitution = mass, 0.7, 0.05
        o.rigid_body.collision_shape = "CONVEX_HULL"
        o.rigid_body.use_margin, o.rigid_body.collision_margin = True, r * 0.05
    return grains


def passive(o, friction=0.6, shape="MESH"):
    if bpy.context.scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
        bpy.ops.rigidbody.object_add(type="PASSIVE")
    o.rigid_body.collision_shape, o.rigid_body.friction = shape, friction
    o.rigid_body.use_margin, o.rigid_body.collision_margin = True, 0.0002  # 기본 여유 4 cm 면 알갱이가 허공에 멈춤


def run_rigid(frames):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frames
    sc.rigidbody_world.point_cache.frame_end = frames
    t = time.time()
    for f in range(1, frames + 1):
        sc.frame_set(f)
    print(f"Bullet {frames} 프레임 {time.time() - t:.0f} s")


# ---------- 단계 장면 ----------
def s_chill(P, m):
    """냉각판: 알루미늄 판에 서리 (−20 °C, 저온실 이슬점 아래), 냉각기와 실리콘 관."""
    box("냉각판 (알루미늄)", (0.3, 0.3, 0.012), (0, 0.02, 0.006), m["al"], bevel=0.002)
    fr = box("서리", (0.29, 0.29, 0.0012), (0, 0.02, 0.0126), m["frost"])
    fr.modifiers.new("거칠기", "DISPLACE").strength = 0.0006
    box("순환식 냉각기", (0.26, 0.3, 0.3), (0.33, 0.12, 0.15), m["white"], bevel=0.01)
    box("냉각기 표시창", (0.09, 0.003, 0.03), (0.3, -0.031, 0.24), m["lcd"])
    text("-20.0", (0.3, -0.0325, 0.24), 0.018, m["red"])
    for dy in (-0.05, 0.05):
        tube("부동액 관", [(0.2, 0.06 + dy, 0.1), (0.17, 0.0 + dy, 0.03), (0.14, 0.02 + dy, 0.008)], 0.006, m["tube"])
    camera((0.05, -0.62, 0.36), (0.1, 0.06, 0.06), 42)


def s_weigh(P, m):
    top = balance((0, 0.05, 0), m, "15.00 g")
    boat = revolve("칭량 접시", [(0.0, 0.0), (0.03, 0.0), (0.042, 0.012)], m["white"], (0, 0.08, top), solid=0.0008)
    passive(boat, 0.9)
    grains = rigid_grains(350 if not QUICK else 150, (0.0, 0.08, top + 0.06), 0.006, 0.0011, m)
    run_rigid(70 if not QUICK else 40)
    camera((0.0, -0.35, 0.3), (0.0, 0.07, 0.08), 70, 2.8, (0.0, 0.08, top + 0.01))


def s_take(P, m):
    """Mantaflow: 병에서 메스실린더로 식염수를 따름 — 흘러나오는 속도 = 꿀럭 흐름 유량 / 출구 넓이 (benchphys)."""
    r = P["render"]
    revolve("메스실린더 (100 mL)", [(0.0, 0.0), (0.0135, 0.0), (0.0135, 0.25)], m["glass"], (0, 0, 0.012), solid=0.0018)
    cyl("받침", 0.04, 0.012, (0, 0, 0.006), m["glass"])
    d = Vector((-0.82, 0, -0.57)).normalized()  # 병목 방향 (수평 아래 35°)
    mouth = Vector((0.006, 0, 0.3))
    prof, H = bottle_profile()
    base = mouth - d * (H + 0.052)
    th = math.atan2(d.x, d.z)
    b, _ = bottle("생리식염수 병", tuple(base), m, cap=False, rot=(0, th, 0))
    hole = cyl("구멍", 0.0135, 0.4, (0, 0, 0.012 + 0.2), m["glass"])
    dom = fluid_domain((0.01, 0, 0.16), (0.08, 0.04, 0.32), r["mu"], r["rho"], r["sigma"], FLUID_RES)
    collider_with_hole("실린더 충돌체", (0.08, 0.04, 0.272), (0.01, 0, 0.126), hole)  # 위 끝 = 실린더 입구 (0.262) — 흘러나오는 곳은 비움
    r_out = 0.0065
    v = r["pour_ml_s"] * 1e-6 / (math.pi * r_out ** 2)
    inflow(tuple(mouth + d * 0.004), r_out, tuple(d * v), rot=(0, th, 0))
    bake_fluid(dom, 24, OUT / "cache_take", r)  # 1 s × 56 mL/s ≈ 56 mL
    dom.data.materials.append(m["saline"])
    camera((0.14, -0.42, 0.26), (0.03, 0, 0.17), 55)


def s_disperse(P, m):
    """Mantaflow 교반 (250 mL, 300 rpm) 이 만든 소용돌이 면을 Bullet 충돌면으로 — PVA 알갱이가 떨어져 가운데로 미끄러짐."""
    r = P["render"]
    top = hotplate((0, 0.02, 0), m, None, r["rpm"])
    beaker("250 mL 비커", 0.0335, 0.095, (0, 0.03, top), m)
    fr = 36 if QUICK else 96  # 4 s — 물은 자리 잡는 데 (에크만) 약 5 s
    dom, dh = stir_fluid(0.0335, 0.0284, 0.025, r["rpm"], r["mu"], r["rho"], (0, 0.03, top), fr, OUT / "cache_disperse",
                         48 if QUICK else 72)
    ENGINE_OUT["disperse"] = {"vortex_mm": dh, "formula_mm": r["vortex_mm"], "t_s": (fr - 1) / 24, "spinup_s": r["spinup_s"]}
    dom.data.materials.append(m["saline"])
    surf = bpy.data.objects.new("소용돌이 면 (Bullet 충돌)", bpy.data.meshes.new_from_object(dom.evaluated_get(bpy.context.evaluated_depsgraph_get())))
    bpy.context.collection.objects.link(surf)
    surf.matrix_world = dom.matrix_world
    surf.hide_render = True
    passive(surf, 0.03)
    rigid_grains(260 if not QUICK else 80, (0.014, 0.035, top + 0.07), 0.004, 0.0005, m, seed=3)
    sc = bpy.context.scene
    sc.rigidbody_world.point_cache.frame_start = 1
    run_rigid(fr)  # 같은 프레임 범위 — 끝 프레임에서 유체 면과 알갱이가 맞음
    camera((0.0, -0.12, 0.45), (0.0, 0.03, top + 0.02), 70)


def s_stock(P, m):
    """90 °C 15 % PVA (점도 767 mPa·s) — 층흐름이라 소용돌이 없음, 호일 아래 김 서림."""
    top = hotplate((0, 0.02, 0), m, 90, 300)
    beaker("250 mL 비커", 0.0335, 0.095, (0, 0.03, top), m)
    liquid_cyl("PVA 원액 (90 °C)", 0.0332, 0.036, (0, 0.03, top + 0.0022), m["pva"])
    foil = box("호일 뚜껑", (0.085, 0.085, 0.0006), (0, 0.03, top + 0.097), m["foil"])
    foil.modifiers.new("구김", "DISPLACE").strength = 0.002
    cyl("온도 프로브", 0.0018, 0.13, (0.018, 0.04, top + 0.07), m["steel"], rot=(0.15, 0, 0))
    mist = cyl("김 (수증기)", 0.033, 0.055, (0, 0.03, top + 0.067), m["ln2"])
    mist.data.materials[0] = mat("김 (90 °C 수증기)", (1, 1, 1), 1.0, alpha=0.0, scatter=8.0)
    camera((0.0, -0.36, 0.25), (0.0, 0.03, top + 0.04), 65)


def s_cool(P, m):
    top = balance((-0.03, 0.04, 0), m, "131.08 g")
    beaker("250 mL 비커", 0.0335, 0.095, (-0.03, 0.07, top), m)
    liquid_cyl("PVA 원액 (식는 중)", 0.0332, 0.036, (-0.03, 0.07, top + 0.0022), m["pva"])
    wb, _ = bottle("증류수 세척병", (0.11, 0.06, 0.0), m, cap=True)
    tube("세척병 꼭지", [(0.11, 0.06, 0.21), (0.07, 0.07, 0.22), (0.0, 0.07, 0.17)], 0.002, m["tube"])
    for k in range(4):  # 보충하는 물방울 (물의 모세관 길이 2.7 mm 쯤)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0013, location=(-0.004 - 0.003 * k, 0.07, top + 0.12 - 0.018 * k))
        bpy.context.object.data.materials.append(m["saline"])
    camera((0.02, -0.4, 0.26), (0.0, 0.06, 0.1), 55)


def s_pretest(P, m):
    """20 mL 바이알: 응집 덩이 (스몰루호프스키, 30 분 뒤 지름 r) 와 바닥에 가라앉은 층 (스토크스)."""
    r = P["render"]
    for x, label in ((-0.03, "대조 (물)"), (0.03, "식염수")):
        revolve(f"바이알 {label}", [(0.0, 0.0), (0.0135, 0.0), (0.0135, 0.06), (0.009, 0.064), (0.009, 0.07)], m["glass"], (x, 0.05, 0), solid=0.0012)
        cap = cyl("바이알 뚜껑", 0.0105, 0.012, (x, 0.05, 0.075), m["dark"])
        if x < 0:
            liquid_cyl("GO (응집 없음)", 0.0131, 0.042, (x, 0.05, 0.0012), m["go_stock"]).data.materials[0] = m["go_mix"]
        else:
            lq = liquid_cyl("GO (응집)", 0.0131, 0.042, (x, 0.05, 0.0012), mat("응집한 GO 액", (0.9, 0.8, 0.7), 0.05, trans=1.0, ior=1.34,
                                                                                   absorb=((0.75, 0.62, 0.48), go_absorb(0.5) * 0.35)))
            sed = cyl("가라앉은 덩이층", 0.0128, max(r["settle_mm"], 0.3) / 1000 * 3, (x, 0.05, 0.0014), m["go_stock"])
            rng = np.random.default_rng(5)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1, location=(0, 0, -1))
            fl = bpy.context.object
            fl.data.materials.append(m["go_stock"])
            for i in range(160):  # 덩이: 눈에 보이게 크게 (실제 지름 r) — 무작위 위치
                o = fl.copy()
                o.data = fl.data
                rr, th = 0.011 * math.sqrt(rng.random()), rng.uniform(0, 6.28)
                o.location = (x + rr * math.cos(th), 0.05 + rr * math.sin(th), rng.uniform(0.003, 0.04))
                o.scale = (rng.uniform(0.25, 0.6) / 1000,) * 3
                bpy.context.collection.objects.link(o)
            bpy.data.objects.remove(fl)
    lb = box("뒤 조명판 (빛에 비춰 봄)", (0.12, 0.004, 0.09), (0.0, 0.085, 0.045), mat("조명판", (1, 1, 1), 0.5, emit=(1, 0.98, 0.94), strength=25))
    camera((0.0, -0.22, 0.09), (0.0, 0.05, 0.035), 60)


def s_mix(P, m):
    """Mantaflow 교반 (1 L, 500 mL 섞은 액, 300 rpm, 점도 15 mPa·s) — 엔진이 만든 소용돌이 · GO 를 벽 쪽으로 가늘게."""
    r = P["render"]
    top = hotplate((0, 0.02, 0), m, None, r["rpm"])
    beaker("1 L 비커", 0.0525, 0.145, (0, 0.03, top), m)
    fr = 36 if QUICK else 72  # 3 s
    dom, dh = stir_fluid(0.0525, r["depth_mm"] / 1000, 0.04, r["rpm"], r["mu"], r["rho"], (0, 0.03, top), fr,
                         OUT / "cache_mix", 48 if QUICK else 72)
    ENGINE_OUT["mix"] = {"vortex_mm": dh, "formula_mm": r["vortex_mm"], "t_s": (fr - 1) / 24, "spinup_s": r["spinup_s"]}
    dom.data.materials.append(m["go_mix"])
    revolve("GO 비커", [(0.0, 0.0), (0.0335, 0.0), (0.0335, 0.095)], m["glass"], (0.15, 0.05, top + 0.14), solid=0.0018).rotation_euler = (0, -1.0, 0)
    tube("GO 가는 줄기", [(0.07, 0.05, top + 0.2), (0.05, 0.04, top + 0.13), (0.042, 0.035, top + r["depth_mm"] / 1000 + 0.004)], 0.0012, m["go_stock"])
    camera((0.0, -0.3, 0.5), (0.02, 0.03, top + 0.05), 55)


def s_degas(P, m):
    """감압 5 kPa: 기포가 커져 (×2.7) 스토크스 속도로 떠오름 — 큰 기포는 위에, 작은 것은 아직 깊이."""
    r = P["render"]
    revolve("데시케이터 바닥", [(0.0, 0.0), (0.13, 0.0), (0.13, 0.05), (0.14, 0.055)], m["glass"], (0, 0.05, 0), solid=0.004)
    revolve("데시케이터 뚜껑", [(0.14, 0.0), (0.135, 0.04), (0.1, 0.11), (0.03, 0.14), (0.0, 0.142)], m["glass"], (0, 0.05, 0.055), solid=0.004)
    cyl("진공 밸브", 0.012, 0.03, (0, 0.05, 0.21), m["steel"])
    tube("진공 관", [(0, 0.05, 0.225), (0.08, 0.1, 0.26), (0.25, 0.15, 0.1), (0.3, 0.15, 0.0)], 0.005, m["tube"])
    beaker("1 L 비커", 0.0525, 0.145, (0, 0.05, 0.004), m)
    d = r["depth_mm"] / 1000
    liquid_cyl("섞은 액", 0.0522, d, (0, 0.05, 0.0062), m["go_mix"])
    rng = np.random.default_rng(9)
    t = 10.0  # 감압 뒤 10 s 의 모습
    for (rb, vb), n in zip(zip(r["bubble_r_mm"], r["rise_mm_s"]), (40, 120)):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=16, ring_count=8, location=(0, 0, -1))
        proto = bpy.context.object
        proto.data.materials.append(m["bubble"])
        for i in range(n):
            z0 = rng.uniform(0, d)
            z = z0 + vb / 1000 * t
            if z > d - rb / 1000:
                z = d - rb / 1000 * 0.6  # 표면에 모인 기포
            o = proto.copy()
            o.data = proto.data
            rr, th = 0.05 * math.sqrt(rng.random()), rng.uniform(0, 6.28)
            o.location = (rr * math.cos(th), 0.05 + rr * math.sin(th), 0.0062 + z)
            o.scale = (rb / 1000 * 2.5,) * 3  # 보이게 2.5배
            bpy.context.collection.objects.link(o)
        bpy.data.objects.remove(proto)
    camera((0.0, -0.5, 0.3), (0.0, 0.05, 0.07), 50)


def s_refill(P, m):
    """Mantaflow: 진한 혼합액(15 mPa·s) 을 깔때기로 — 물결 없는 유량 아래로 벽을 타게."""
    r = P["render"]
    b, H = bottle("생리식염수 병", (0, 0, 0), m, cap=False)
    liquid_cyl("병 속 (이미 담긴)", 0.0341, 0.06, (0, 0, 0.0008), m["go_mix"])
    revolve("깔때기", [(0.0065, 0.17), (0.0065, 0.2), (0.045, 0.245), (0.047, 0.25)], m["glass"], (0, 0, 0.012), solid=0.0015)
    bk = revolve("1 L 비커 (붓는 중)", [(0.0, 0.0), (0.0525, 0.0), (0.0525, 0.145)], m["glass"], (0.09, 0, 0.27), solid=0.0018)
    bk.rotation_euler = (0, -1.25, 0)
    hole_prof, _ = bottle_profile()
    hole = revolve("병 구멍", [(0.0, -0.001)] + [(max(x - 0.0008, 0.001), z) for x, z in hole_prof[1:]] + [(0.0125, 0.3)], m["glass"])
    fun = revolve("깔때기 구멍", [(0.0, 0.17), (0.006, 0.17), (0.006, 0.2), (0.044, 0.245), (0.044, 0.33), (0.0, 0.33)], m["glass"], (0, 0, 0.012))
    un = hole.modifiers.new("합", "BOOLEAN")
    un.operation, un.object = "UNION", fun
    with bpy.context.temp_override(object=hole, active_object=hole, selected_objects=[hole]):
        bpy.ops.object.modifier_apply(modifier="합")
    fun.hide_render = True
    dom = fluid_domain((0.0, 0, 0.17), (0.11, 0.1, 0.34), r["mu"], r["rho"], 0.06, FLUID_RES)
    collider_with_hole("병 · 깔때기 충돌체", (0.11, 0.1, 0.34), (0.0, 0, 0.17), hole)
    v = r["pour_ml_s"] * 1e-6 / (math.pi * 0.0055 ** 2)  # 물결 없는 최대 유량 / 출구 넓이
    dv = Vector((-0.9, 0, -0.45)).normalized()
    inflow((0.032, 0, 0.3), 0.0055, tuple(dv * v), rot=(0, math.atan2(dv.x, dv.z), 0))
    bake_fluid(dom, 36 if QUICK else 60, OUT / "cache_refill", r)
    dom.data.materials.append(m["go_mix"])
    camera((0.15, -0.5, 0.28), (0.02, 0, 0.16), 45)


def _freeze_scene(m, front_mm, H_mm, full=False):
    box("냉각판", (0.24, 0.24, 0.012), (0, 0.04, 0.006), m["al"], bevel=0.002)
    box("서리", (0.235, 0.235, 0.0012), (0, 0.04, 0.0126), m["frost"])
    o, H = bottle("병 (동결 중)", (0, 0.04, 0.013), m, cap=True)
    zf = min(front_mm, H_mm) / 1000
    if zf > 0:
        liquid_cyl("얼음 (아래에서 위로)", 0.0341, zf, (0, 0.04, 0.0138), m["ice"])
    if not full and zf < H_mm / 1000:
        liquid_cyl("아직 액체", 0.0341, H_mm / 1000 - zf, (0, 0.04, 0.0138 + zf), m["go_mix"])
    # 단열재: 반만 (안이 보이게 자른 모양)
    for x in (-0.07, 0.07):
        box("단열재 (스티로폼 3 cm)", (0.03, 0.03, 0.23), (x, 0.08, 0.13), m["foam"])
    box("단열재 (뒤)", (0.17, 0.03, 0.23), (0, 0.095, 0.13), m["foam"])
    box("단열재 (위)", (0.17, 0.1, 0.03), (0, 0.06, 0.26), m["foam"])
    for z in (0.02, H_mm / 1000):
        tube("열전대", [(0.036, 0.04, z), (0.06, 0.0, z + 0.01), (0.2, -0.05, 0.02)], 0.0008, m["copper"])
    camera((0.06, -0.46, 0.22), (0.0, 0.05, 0.1), 50)


def s_setup(P, m):
    _freeze_scene(m, 0.0, PHYS["dfreeze"]["render"]["height_mm"])


def s_dfreeze(P, m):
    r = P["render"]
    zf = float(np.interp(r["show_at_h"], r["front_t_h"], r["front_mm"]))
    _freeze_scene(m, zf, r["height_mm"])


def s_ft(P, m):
    r = PHYS["dfreeze"]["render"]
    _freeze_scene(m, r["height_mm"], r["height_mm"], full=True)


def s_thaw(P, m):
    """25 °C 수조: 겉부터 녹아 얼음 심 반지름 R√(1 − t/t_all) (준정상 스테판) — 절반 지났을 때."""
    H = PHYS["dfreeze"]["render"]["height_mm"] / 1000
    box("항온수조 (아크릴)", (0.32, 0.24, 0.2), (0, 0.06, 0.1), m["acrylic"]).modifiers.new("두께", "SOLIDIFY").thickness = 0.004
    box("수조 물", (0.312, 0.232, 0.175), (0, 0.06, 0.0915), m["water"])
    bottle("병 (해동 중)", (0, 0.06, 0.004), m, cap=True)
    liquid_cyl("녹은 겔", 0.0341, H, (0, 0.06, 0.005), m["go_mix"])
    liquid_cyl("얼음 심", 0.0341 * math.sqrt(0.5), H * 0.9, (0, 0.06, 0.005 + H * 0.05), m["ice"])
    box("히터 · 표시창", (0.08, 0.06, 0.05), (0.12, 0.06, 0.225), m["white"])
    text("25.0", (0.12, 0.029, 0.225), 0.016, m["red"])
    camera((0.0, -0.55, 0.28), (0.0, 0.06, 0.1), 45)


def s_demold(P, m):
    """제 무게로 처진 겔: 높이 z 에서 세로 변형 ρg(H − z)/E, 옆으로 0.5 배 부풂 (선형 탄성, benchphys)."""
    r = P["render"]
    H, R, e0 = r["height_mm"] / 1000, r["diam_mm"] / 2000 * 0.98, r["strain"]
    zs = np.linspace(0, H, 40)
    # 위에서 내려오는 무게 → 아래일수록 많이 눌림: 새 높이 z' = ∫ (1 − e0 (H − z)/H) dz
    zn = np.concatenate([[0], np.cumsum((1 - e0 * (H - zs[:-1]) / H) * np.diff(zs))])
    rn = R * (1 + 0.5 * e0 * (H - zs) / H)
    prof = [(0.0, 0.0)] + [(float(a), float(b)) for a, b in zip(rn, zn)] + [(0.0, float(zn[-1]))]
    revolve("PVA-GO 겔 (처짐)", prof, m["gel"], (0, 0.05, 0.004))
    box("받침 판", (0.16, 0.16, 0.004), (0, 0.05, 0.002), m["white"])
    half, _ = bottle("잘린 병", (0.13, 0.08, 0.0), m, cap=False)
    half.rotation_euler = (0, math.pi / 2, 0.4)
    half.location = (0.14, 0.09, 0.04)
    box("커터", (0.1, 0.012, 0.008), (-0.12, -0.02, 0.004), m["yellow"])
    box("커터 날", (0.03, 0.0003, 0.006), (-0.055, -0.02, 0.004), m["blade"])
    camera((0.02, -0.42, 0.18), (0.0, 0.05, 0.065), 55)


def s_meas(P, m):
    H = PHYS["dfreeze"]["render"]["height_mm"] / 1000 * (1 - PHYS["demold"]["render"]["strain"] / 2)
    liquid_cyl("PVA-GO 겔", 0.034, H, (0, 0.05, 0.004), m["gel"])
    box("받침 판", (0.16, 0.16, 0.004), (0, 0.05, 0.002), m["white"])
    cyl("흑연 막대 (윗면)", 0.003, 0.08, (0.02, 0.05, H + 0.04), m["graphite"], rot=(0.4, 0, 0))
    cyl("흑연 막대 (아랫면)", 0.003, 0.08, (0.05, 0.03, 0.03), m["graphite"], rot=(0, 1.2, 0.3))
    box("멀티미터", (0.09, 0.04, 0.17), (0.2, 0.05, 0.085), m["yellow"], bevel=0.008)
    box("멀티미터 창", (0.07, 0.003, 0.035), (0.2, 0.029, 0.13), m["lcd"])
    text("0.12 mV", (0.2, 0.0275, 0.13), 0.012, mat("숫자 (검정)", (0.02, 0.02, 0.02), 0.5))
    tube("빨강 전선", [(0.033, 0.045, H + 0.075), (0.1, 0.0, 0.15), (0.19, 0.03, 0.03)], 0.0018, m["copper"])
    tube("검정 전선", [(0.085, 0.02, 0.045), (0.14, -0.01, 0.02), (0.21, 0.03, 0.03)], 0.0018, m["wire_b"])
    camera((0.06, -0.42, 0.2), (0.07, 0.05, 0.07), 45)


def s_section(P, m):
    revolve("액체질소 듀어", [(0.0, 0.0), (0.06, 0.0), (0.06, 0.14), (0.055, 0.145)], m["steel"], (0.08, 0.06, 0), solid=0.004)
    fog = cyl("질소 김 (라이덴프로스트)", 0.06, 0.05, (0.08, 0.06, 0.16), m["ln2"])
    fog.data.materials[0] = mat("질소 김", (1, 1, 1), 1.0, alpha=0.0, scatter=40.0)
    H = 0.06
    liquid_cyl("겔 반쪽 (단면)", 0.034, H, (-0.1, 0.06, 0.004), m["gel"]).rotation_euler = (math.pi / 2, 0, 0)
    box("도마", (0.2, 0.14, 0.008), (-0.1, 0.05, 0.004), m["white"])
    box("자", (0.15, 0.025, 0.002), (-0.1, -0.01, 0.009), m["ruler"])
    for k in range(3):
        box(f"2 mm 조각 {k}", (0.002, 0.004, 0.004), (0.06 + 0.012 * k, 0.03, 0.14 + 0.004 * k), m["gel"])
    tube("핀셋", [(0.02, 0.0, 0.2), (0.06, 0.03, 0.15)], 0.0015, m["steel"])
    camera((-0.02, -0.45, 0.25), (-0.01, 0.06, 0.08), 45)


def s_lyo(P, m):
    box("동결건조기 받침", (0.3, 0.3, 0.08), (0, 0.08, 0.04), m["white"], bevel=0.01)
    revolve("아크릴 통", [(0.11, 0.0), (0.11, 0.22)], m["acrylic"], (0, 0.08, 0.08), solid=0.005)
    cyl("아크릴 뚜껑", 0.115, 0.01, (0, 0.08, 0.305), m["acrylic"])
    for z in (0.12, 0.2):
        cyl("선반", 0.1, 0.004, (0, 0.08, z), m["steel"])
        for k in range(3):
            box("마른 조각", (0.006, 0.006, 0.002), (-0.02 + 0.02 * k, 0.08, z + 0.003), m["sample"])
    revolve("응축기 서리", [(0.06, 0.0), (0.06, 0.03)], m["frost"], (0, 0.08, 0.081), solid=0.004)
    box("표시창", (0.08, 0.003, 0.025), (0, -0.071, 0.05), m["lcd"])
    text("-50C 10Pa", (0, -0.0725, 0.05), 0.009, m["digit"])
    camera((0.0, -0.6, 0.3), (0.0, 0.08, 0.14), 45)


def s_cond(P, m):
    """SEM-EDS: 시료대 + 화면에 Cl 지도 (보로노이 세포 벽에 소금이 몰림 — 세포 폭 170 µm)."""
    cyl("SEM 시료대 (알루미늄 스텁)", 0.0063, 0.006, (0, 0.04, 0.003), m["al"])
    box("마른 시료", (0.006, 0.006, 0.002), (0, 0.04, 0.007), m["sample"])
    cyl("탄소 테이프", 0.006, 0.0005, (0, 0.04, 0.0062), m["dark"])
    box("모니터", (0.24, 0.015, 0.15), (0.09, 0.12, 0.1), m["dark"], bevel=0.005)
    box("모니터 다리", (0.03, 0.015, 0.03), (0.09, 0.125, 0.015), m["dark"])
    scr = box("화면 (Cl 지도)", (0.226, 0.002, 0.136), (0.09, 0.112, 0.1), m["screen"])
    box("SEM 시료실 문", (0.12, 0.1, 0.03), (-0.02, 0.05, -0.015 + 0.0), m["steel"])
    sm = mat("Cl 지도", (0, 0, 0), 0.5)
    nt = sm.node_tree
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 60
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.0, (0.1, 1.0, 0.35, 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.08, (0.0, 0.03, 0.01, 1)
    nt.links.new(vor.outputs["Distance"], ramp.inputs[0])
    b = nt.nodes["Principled BSDF"]
    nt.links.new(ramp.outputs[0], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 3.0
    scr.data.materials[0] = sm
    camera((0.0, -0.32, 0.16), (0.03, 0.15, 0.12), 32)


SCENES = {"chill": s_chill, "weigh": s_weigh, "take": s_take, "disperse": s_disperse, "stock": s_stock, "cool": s_cool,
          "pretest": s_pretest, "mix": s_mix, "degas": s_degas, "refill": s_refill, "setup": s_setup, "dfreeze": s_dfreeze,
          "thaw": s_thaw, "ft": s_ft, "demold": s_demold, "meas": s_meas, "section": s_section, "lyo": s_lyo, "cond": s_cond}

for no, sid in enumerate(ORDER, 1):
    if sid not in ONLY:
        continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    mats = M()
    env(mats)
    try:
        SCENES[sid](PHYS[sid], mats)
        render(no, sid)
        if ENGINE_OUT:  # 엔진이 잰 값 (소용돌이 깊이) — 발표 자료 물리 칸이 읽음
            f = OUT / "engine.json"
            old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            f.write_text(json.dumps({**old, **ENGINE_OUT}, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — 한 장면이 실패해도 나머지는 그림
        import traceback

        traceback.print_exc()
        print("실패:", sid, e)
