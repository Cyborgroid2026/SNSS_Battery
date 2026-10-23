"""Blender 기본형 · 비파괴 CSG — snss_battery/parts.py 의 SDF 더하기 빼기를 불리언 모디파이어(정확 풀이)로.

단위: 장면 단위 mm (1 BU = 1 mm, scale_length 0.001). 축 0 = X · 1 = Y · 2 = Z.
- 원기둥 · 구는 '단위 모양 × 크기(scale)' — 반지름 · 길이를 크기로 바꾸거나 드라이버로 묶을 수 있음
- 둥근 상자는 실제 크기 정육면체 + 베벨 모디파이어 (폭 = 반지름)
- 노드: ("u", [자식…]) 합 · ("c", 바탕, [빼는 것…]) 빼기 → 바탕 개체에 불리언 모디파이어 (자식은 '재료' 컬렉션에 선으로 숨김)
"""

from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

_UNIT: dict[str, bpy.types.Mesh] = {}


def _unit(kind: str) -> bpy.types.Mesh:
    """한 번 만든 단위 메시를 함께 씀 (원기둥: 반지름 1 · 높이 1 가운데, 구: 반지름 1)."""
    m = _UNIT.get(kind)
    if m is not None and m.name in bpy.data.meshes:
        return m
    m = bpy.data.meshes.new(f"단위 {kind}")
    bm = bmesh.new()
    if kind == "cyl":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=1, radius2=1, depth=1)
    elif kind == "cyl0":  # 바닥이 z 0 인 원기둥 (층 · 기둥)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=64, radius1=1, radius2=1, depth=1, matrix=Matrix.Translation((0, 0, 0.5)))
    elif kind == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1)
    elif kind == "cube0":  # 0…1 정육면체 (배치 상자)
        bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Translation((0.5, 0.5, 0.5)))
    bm.to_mesh(m)
    bm.free()
    _UNIT[kind] = m
    return m


def obj(name, mesh, coll, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    o = bpy.data.objects.new(name, mesh)
    coll.objects.link(o)
    o.location, o.rotation_euler, o.scale = Vector(loc), Euler(rot), Vector(scale)
    return o


_ROT = {0: (0, math.pi / 2, 0), 1: (math.pi / 2, 0, 0), 2: (0, 0, 0)}


def cyl(coll, name, c, r, h, axis=2):
    return obj(name, _unit("cyl"), coll, c, _ROT[axis], (r, r, h))


def cyl0(coll, name, base, r, h):
    return obj(name, _unit("cyl0"), coll, base, (0, 0, 0), (r, r, h))


def sphere(coll, name, c, r):
    return obj(name, _unit("sphere"), coll, c, (0, 0, 0), (r, r, r))


def ellipsoid(coll, name, c, r):
    return obj(name, _unit("sphere"), coll, c, (0, 0, 0), tuple(r))


def box(coll, name, c, size, r=0.0):
    """실제 크기 상자 + (r > 0) 베벨 모디파이어."""
    m = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Diagonal((*size, 1)))
    bm.to_mesh(m)
    bm.free()
    o = obj(name, m, coll, c)
    r = min(float(r), 0.49 * min(size))
    if r > 0.05:
        b = o.modifiers.new("둥글림", "BEVEL")
        b.width, b.segments, b.limit_method = r, 4, "NONE"
        b.harden_normals = False
    return o


def box_lohi(coll, name, lo, hi):
    return obj(name, _unit("cube0"), coll, lo, (0, 0, 0), tuple(max(hi[i] - lo[i], 1e-3) for i in range(3)))


def capsule(coll, name, a, b, r):
    """원기둥 + 두 구 — ('u', …) 노드로 돌려줌."""
    a, b = Vector(a), Vector(b)
    d = b - a
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_euler()
    c = obj(name, _unit("cyl"), coll, (a + b) / 2, rot, (r, r, d.length))
    return ("u", [c, sphere(coll, name + " 끝 1", a, r), sphere(coll, name + " 끝 2", b, r)])


def ring(coll, name, c, r_out, r_in, h, axis=2):
    return ("c", cyl(coll, name, c, r_out, h, axis), [cyl(coll, name + " 안", c, r_in, h + 1, axis)])


def twisted(coll, name, z0, length, width, thick, a0, turn):
    """비틀린 띠 (Kenics 혼합 요소): 상자 + 단순 변형(비틀기) 모디파이어."""
    m = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Diagonal((width, thick, length, 1)))
    edges = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 1e-6]
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=16, use_grid_fill=True)
    bm.to_mesh(m)
    bm.free()
    o = obj(name, m, coll, (0, 0, z0 + length / 2), (0, 0, a0))
    t = o.modifiers.new("비틀기", "SIMPLE_DEFORM")
    t.deform_method, t.deform_axis, t.angle = "TWIST", "Z", turn
    return o


# ---------- CSG 노드 → 개체 ----------
def _hide(o, mat_coll):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    mat_coll.objects.link(o)
    o.display_type = "WIRE"
    o.hide_render = True


def realize(node, mat_coll, name):
    """노드를 실제 개체 하나로: 첫 개체가 바탕, 나머지는 불리언 모디파이어의 재료."""
    if isinstance(node, bpy.types.Object):
        return node
    if node[0] == "u":
        kids = [realize(k, mat_coll, name) for k in node[1]]
        base = kids[0]
        if len(kids) > 1:
            sub = bpy.data.collections.new(f"{name} · 더하기")
            mat_coll.children.link(sub)
            for k in kids[1:]:
                _hide(k, sub)
            m = base.modifiers.new("더하기", "BOOLEAN")
            m.operation, m.operand_type, m.collection, m.solver = "UNION", "COLLECTION", sub, "EXACT"
            m.use_hole_tolerant = True  # 같은 평면에서 만나는 면 (예: 전극 집게 걸이)
        return base
    base = realize(node[1], mat_coll, name)
    tools = [realize(k, mat_coll, name) for k in node[2]]
    if tools:
        sub = bpy.data.collections.new(f"{name} · 빼기")
        mat_coll.children.link(sub)
        for t in tools:
            _hide(t, sub)
        m = base.modifiers.new("빼기", "BOOLEAN")
        m.operation, m.operand_type, m.collection, m.solver = "DIFFERENCE", "COLLECTION", sub, "EXACT"
    return base


def drive(o, path, index, expr, **vars_):
    """드라이버: vars_ = {이름: (대상 ID, data_path)} — 단순 식이면 스크립트 자동 실행 없이도 동작."""
    fc = o.driver_add(path, index) if index is not None else o.driver_add(path)
    while fc.keyframe_points:  # 기본 곡선이 붙으면 아주 작은 값(나노미터 층)이 눌림 → 드라이버 값 그대로
        fc.keyframe_points.remove(fc.keyframe_points[0])
    for m in list(fc.modifiers):
        fc.modifiers.remove(m)
    d = fc.driver
    d.type = "SCRIPTED"
    for k, (idb, dp) in vars_.items():
        v = d.variables.new()
        v.name, v.type = k, "SINGLE_PROP"
        v.targets[0].id, v.targets[0].data_path = idb, dp
    d.expression = expr
    return fc


def eval_mesh(o, depsgraph, world=True):
    """평가된(모디파이어 적용) 메시 → bmesh (세계 좌표)."""
    ev = o.evaluated_get(depsgraph)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    if world:
        bm.transform(ev.matrix_world)
    ev.to_mesh_clear()
    return bm


def volume(o, depsgraph) -> float:
    bm = eval_mesh(o, depsgraph)
    v = abs(bm.calc_volume(signed=True))
    bm.free()
    return v


def manifold(o, depsgraph) -> int:
    """다양체가 아닌 모서리 수 (0 이면 닫힌 고체)."""
    bm = eval_mesh(o, depsgraph, world=False)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n
