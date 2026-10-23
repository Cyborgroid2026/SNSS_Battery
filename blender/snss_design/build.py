"""모든 작품을 Blender 장면으로 짓는다 — 값은 design.json (snss_battery/fcparams.design, FreeCAD 와 같은 값).

파일 하나 (cad_out/blender/SNSS_Design.blend), 장면 9개 — 장면마다 '치수 — …' 빈 개체의 속성이 설계 값 (N 패널 'SNSS' 에도 나옴):
  SC-1 조각가      PenX · PenY (갠트리) · BedDrop (받침) — 드라이버로 움직임. 출력 부품은 'SC-1 부품' 장면의 컬렉션 인스턴스
  SC-1 부품        출력 부품 20종 — 불리언 · 베벨 · 비틀기 모디파이어 (비파괴), 재료(선)를 옮기면 다시 계산. Rod · Lm8uu 드라이버
  SC-2 빛 조각가   ToolX · ToolY · BedDrop
  SC-2 도구        T0–T5
  존재 모양        메타볼 (SDF 의 부드러운 합과 같은 방식) — 편집 모드에서 요소를 옮기고 키우고 더함
  빚은 세포        마지막 SC-1 작업의 p · n · 막 (줄인 메시)
  시험편           SC-1 정육면체 · SC-2 사다리 A(높이 = Dp·ln(E/Ec) 드라이버) · B · C
  양자 모듈        Lambda 하나로 35층 두께 · 위치 (드라이버 사슬)
  병 결정          이전 방향 — 병 · 결정 블록 · 절단선 A · 절개선 B · 프로브
"""

from __future__ import annotations

import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import parts as PT
from . import prim as P

COLORS = {
    "petg": ((0.86, 0.89, 0.92), 1), "petg_dark": ((0.18, 0.19, 0.21), 1), "cf": ((0.12, 0.12, 0.13), 1),
    "nylon": ((0.95, 0.92, 0.82), 1), "graphite": ((0.27, 0.27, 0.29), 1), "cable": ((0.08, 0.08, 0.09), 1),
    "glass": ((0.70, 0.86, 0.90), 0.15), "bath": ((0.55, 0.75, 0.95), 0.10), "zone": ((1.0, 0.62, 0.2), 0.12),
    "pos": ((0.90, 0.32, 0.26), 1), "neg": ((0.26, 0.46, 0.90), 1), "mem": ((0.88, 0.86, 0.78), 0.45),
    "ink": ((0.36, 0.30, 0.24), 0.55), "dark": ((0.16, 0.16, 0.19), 1), "beam": ((0.55, 0.30, 1.0), 0.18),
    "lens": ((0.50, 0.30, 1.0), 0.8), "wood": ((0.70, 0.55, 0.38), 1), "xps": ((0.55, 0.75, 0.95), 1),
    "silicone": ((0.90, 0.90, 0.93), 1), "pc": ((0.15, 0.15, 0.17), 1), "pipette": ((0.85, 0.93, 1.0), 0.45),
    "peek": ((0.82, 0.70, 0.50), 1), "being": ((0.95, 0.55, 0.30), 1), "silica": ((0.80, 0.90, 0.98), 0.6),
    "sio2": ((0.70, 0.85, 1.0), 0.7), "sin": ((0.95, 0.80, 0.45), 0.7), "active": ((0.95, 0.25, 0.20), 1),
    "bottle": ((0.85, 0.92, 0.95), 0.25), "crystal": ((0.35, 0.55, 0.85), 0.85), "red": ((0.85, 0.15, 0.12), 1),
    "black": ((0.08, 0.08, 0.08), 1),
}
STIFF = 4.0  # 메타볼 강성 — 서 있는 존재 부피가 SDF(부드러운 합) 와 0.2 % 안 (시험으로 고름)
THRESH = 0.6
K_META = math.sqrt(1 - (THRESH / STIFF) ** (1 / 3))  # 요소 하나의 표면 반지름 / 영향 반지름


# ---------- 장면 · 재질 · 컬렉션 ----------
def material(key):
    name = f"SNSS {key}"
    m = bpy.data.materials.get(name)
    if m is None:
        rgb, a = COLORS[key]
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*rgb, a)
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = (*rgb, 1)
        b.inputs["Alpha"].default_value = a
        b.inputs["Roughness"].default_value = 0.1 if a < 1 else 0.55
        if a < 1:
            for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
                try:
                    setattr(m, attr, val)
                except (AttributeError, TypeError):
                    pass
    return m


def paint(o, key):
    if o.type in ("MESH", "META") and o.data is not None:
        o.data.materials.clear()
        o.data.materials.append(material(key))
    o.color = material(key).diffuse_color
    return o


def scene(name, first=False):
    sc = bpy.data.scenes.get("Scene") if first and bpy.data.scenes.get("Scene") else bpy.data.scenes.new(name)
    sc.name = name
    u = sc.unit_settings
    u.system, u.scale_length, u.length_unit = "METRIC", 0.001, "MILLIMETERS"
    w = bpy.data.worlds.new(f"하늘 {name}")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value, bg.inputs[1].default_value = (0.92, 0.93, 0.95, 1), 0.7
    sc.world = w
    for i, (rot, e) in enumerate((((0.9, 0.2, 0.6), 3.0), ((1.2, -0.3, -2.2), 1.2))):
        lt = bpy.data.objects.new(f"해 {i + 1}", bpy.data.lights.new(f"해 {name} {i}", "SUN"))
        lt.data.energy, lt.rotation_euler = e, rot
        sc.collection.objects.link(lt)
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1000
    return sc


def coll(parent, name):
    c = bpy.data.collections.new(name)
    (parent.collection if isinstance(parent, bpy.types.Scene) else parent).children.link(c)
    return c


def empty(c, name, loc=(0, 0, 0), parent=None, size=10):
    o = bpy.data.objects.new(name, None)
    c.objects.link(o)
    o.empty_display_size = size
    o.location = loc
    if parent is not None:
        o.parent = parent
    return o


def dims(sc, c, rows):
    """rows: (이름, 값, 설명, 최소, 최대) → 빈 개체 속성 (드라이버의 출처)."""
    o = empty(c, f"치수 — {sc.name}", (0, 0, 0), size=20)
    o.empty_display_type = "ARROWS"
    for k, v, desc, lo, hi in rows:
        o[k] = float(v)
        o.id_properties_ui(k).update(description=desc, min=lo, max=hi, soft_min=lo, soft_max=hi, subtype="NONE")
    sc["snss_dims"] = o.name
    return o


def inst(c, part_coll, name, loc, rot=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None)
    o.instance_type, o.instance_collection = "COLLECTION", part_coll
    c.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    if parent is not None:
        o.parent = parent
    return o


def material_of(name):
    return ("cf" if "탄소섬유" in name else "nylon" if "나일론" in name else "graphite" if "전극" in name
            else "cable" if "케이블" in name else "dark" if "프로젝터" in name else "petg")


def lay_obj(c, b, key=None, parent=None):
    lo, hi, n = b["lo"], b["hi"], b["name"]
    size = [hi[i] - lo[i] for i in range(3)]
    ctr = [(lo[i] + hi[i]) / 2 for i in range(3)]
    if b.get("shape") == "cyl_z":
        o = P.cyl0(c, n, (ctr[0], ctr[1], lo[2]), size[0] / 2, size[2])
    elif "탄소섬유 봉" in n:
        ax = max(range(3), key=lambda k: size[k])
        o = P.cyl(c, n, ctr, min(size) / 2, size[ax], ax)
    else:
        o = P.box_lohi(c, n, lo, hi)
    o["layout"] = True
    if parent is not None:
        o.parent = parent
    return paint(o, key or material_of(n))


def mesh_obj(c, name, verts, faces, key):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    return paint(o, key)


def cone(c, name, base, r1, r2, h, key):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=r1, radius2=r2, depth=h, matrix=Matrix.Translation((0, 0, h / 2)))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    o.location = base
    return paint(o, key)


def _bath(sc_coll, inner, fill):
    X, Y, Z = inner
    c = coll(sc_coll, "배양조 · 배지")
    panes = [((-X / 2 - 4, -Y / 2 - 4, -6), (X / 2 + 4, Y / 2 + 4, 0))]
    for s in (-1, 1):
        panes += [((s * X / 2 if s > 0 else -X / 2 - 4, -Y / 2 - 4, 0), (X / 2 + 4 if s > 0 else -X / 2, Y / 2 + 4, Z)),
                  ((-X / 2, s * Y / 2 if s > 0 else -Y / 2 - 4, 0), (X / 2, Y / 2 + 4 if s > 0 else -Y / 2, Z))]
    for i, (lo, hi) in enumerate(panes):
        paint(P.box_lohi(c, f"유리 수조 — {'바닥' if i == 0 else f'벽 {i}'}", lo, hi), "glass")
    paint(P.box_lohi(c, f"배지 — 멸균생리식염수 {fill:g} mm", (-X / 2, -Y / 2, 0), (X / 2, Y / 2, fill)), "bath")
    return c


def _zones(sc, L, root):
    z = coll(root, "비어 있어야 할 곳 (layout zones)")
    for b in L["zones"]:
        o = lay_obj(z, b, "zone")
        o.display_type = "WIRE"
        o.hide_render = True
    sw = coll(root, "움직이는 것이 쓸고 지나가는 범위")
    for b in L["boxes"]:
        if b["kind"] in ("gantry", "bed") and "(쓸림)" in b["name"]:
            o = lay_obj(sw, b, "zone")
            o.display_type = "WIRE"
            o.hide_render = True
    for cc in (z, sw):  # 점검은 design.json 의 상자로 하므로 꺼 둬도 됨 (눈 아이콘 대신 화면 끄기)
        cc.hide_viewport = True


def layer_coll(sc, c, lc=None):
    lc = lc or sc.view_layers[0].layer_collection
    if lc.collection == c:
        return lc
    for ch in lc.children:
        r = layer_coll(sc, c, ch)
        if r is not None:
            return r
    return None


# ---------- SC-1 부품 ----------
def build_parts(D, first=False):
    sc = scene("SC-1 부품", first)
    root = sc.collection
    d = dims(sc, coll(root, "치수"), [("Rod", 8.6, "M8 나사봉 · Ø8 봉 구멍 (출력 수축 여유)", 7.5, 10.0),
                                       ("Lm8uu", 15.2, "LM8UU · 미끄럼 부싱 자리", 14.5, 16.5)])
    outc = coll(root, "출력 부품 20종 (완성 — 조립이 인스턴스로 씀)")
    matc = coll(root, "재료 (CSG — 선으로 보이는 더하고 빼는 기본형)")
    info = {p["key"]: p for p in D["parts"]}
    out = {}
    for i, (key, fn) in enumerate(PT.PARTS.items()):
        nm = info[key]["name"]
        pc = coll(outc, f"부품 — {nm}")
        mc = coll(matc, f"재료 — {nm}")
        t = PT.Ctx(mc, {"Rod": 8.6, "Lm8uu": 15.2})
        base = P.realize(fn(t), mc, nm)
        for c in list(base.users_collection):
            c.objects.unlink(base)
        pc.objects.link(base)
        base.name = nm
        base["snss_part"] = key
        base["qty"] = info[key]["qty"]
        base["material"] = info[key]["material"]
        base["sdf_volume_cm3"] = float(info[key]["sdf_volume_cm3"] or 0)
        paint(base, "petg_dark" if key == "led_ring" else "petg")
        for o, k, extra in t.bound:
            for ax in (0, 1):
                P.drive(o, "scale", ax, f"(v + {extra}) / 2", v=(d, f'["{k}"]'))
        inv = Matrix.LocRotScale(base.location, base.rotation_euler, base.scale).inverted()
        for o in _all_objects(mc):  # 재료는 바탕을 따라 움직임 (바탕의 크기 배율은 물려받지 않게 역행렬)
            if o is not base and o.parent is None:
                o.parent = base
                o.matrix_parent_inverse = inv
        x, y = (i % 5) * 230.0, -(i // 5) * 230.0
        base.location = (x, y, 0)
        pc.instance_offset = (x, y, 0)
        out[key] = pc
    return sc, out


def _all_objects(c):
    yield from c.objects
    for ch in c.children:
        yield from _all_objects(ch)


# ---------- SC-1 조립 ----------
def build_sc1(D, parts, shapes):
    s, L, C = D["sc1"], D["sc1"]["layout"], D["const"]
    FX, FY, FZ = s["frame"]
    bz = s["build"][2]
    z_tip, gz, park = L["z_tip"], L["gz"], L["park"]
    sc = scene("SC-1 조각가", first=True)
    root = coll(sc, "조각가 SC-1")
    d = dims(sc, coll(root, "치수"), [("PenX", park[0], "펜 X (주차 = 뒤쪽 가운데)", -L["travel"][0], L["travel"][0]),
                                       ("PenY", park[1], "펜 Y", -L["travel"][1], L["travel"][1]),
                                       ("BedDrop", 72.0, f"받침 내림 mm (0 = 첫 층, 최대 {bz:g})", 0, bz)])
    _bath(root, s["tank"]["inner_mm"], s["tank"]["fill_mm"])
    fixed = coll(root, "고정 (프레임 · 정지 부품)")
    for b in L["boxes"]:
        if (b["kind"] in ("frame", "static") or (b["kind"] == "gantry" and "(쓸림)" not in b["name"])) \
                and not b["name"].startswith("꼭짓점"):
            if "모터 방수 통" in b["name"] or "펌프 방수 통" in b["name"]:
                continue  # 출력 부품 인스턴스로
            lay_obj(fixed, b, "petg_dark" if b["name"] == "전자 방수 통" else None)
    h = FX / 2 - 18
    for sx in (-1, 1):
        for sy in (-1, 1):
            for zc in (18, FZ - 18):
                inst(fixed, parts["corner"], "프레임 꼭짓점", (sx * h, sy * h, zc))
    pods = [(x, y, 0, "Z") for x, y in ((C["Z_SCREW"], -C["Z_SCREW"]), (C["Z_SCREW"], C["Z_SCREW"]), (-C["Z_SCREW"], -C["Z_SCREW"]))]
    pods += [(-118, y, 0, lab) for y, lab in ((-20, "GO"), (40, "SNSS"), (100, "PVA"))]
    pods += [(sx * 121, 121, gz - 70, "XY") for sx in (-1, 1)]
    for x, y, z, lab in pods:
        inst(fixed, parts["motor_pod"], f"모터 방수 통 ({lab})", (x, y, z))
        inst(fixed, parts["pod_lid"], f"방수 통 뚜껑 ({lab})", (x, y, z + 44))
    inst(fixed, parts["port_panel"], "단자판 (배양조 밖)", (0, -FY / 2 - 70, -6), (math.pi / 2, 0, 0))
    inst(fixed, parts["level_probe"], "배지 전도도 전극 집게", (-130, 160, s["tank"]["fill_mm"] - 30))
    # 갠트리 (PenY) → 캐리지 · 펜 (PenX)
    mov = coll(root, "움직임 (갠트리 · 받침)")
    g = empty(mov, "갠트리 — X 빔 (PenY)")
    P.drive(g, "location", 1, f"v - {park[1]}", v=(d, '["PenY"]'))
    for b in L["parked"]:
        if b["name"].startswith("X 빔"):
            lo, hi = b["lo"], b["hi"]
            for dz in (-6, 6):
                o = P.cyl(mov, "X 봉 (탄소섬유 Ø8)", ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2 + dz), 4, hi[0] - lo[0], 0)
                o.parent = g
                paint(o, "cf")
    for sx in (-1, 1):
        inst(mov, parts["y_end"], "X 봉 끝단", (sx * 121, park[1], gz - 15), (0, 0, math.pi / 2), g)
    car = empty(mov, "캐리지 · 펜 (PenX)", parent=g)
    P.drive(car, "location", 0, f"v - {park[0]}", v=(d, '["PenX"]'))
    px, py = park
    bzp = z_tip + 40
    inst(mov, parts["pen_carriage"], "펜 캐리지 (자석 키네마틱)", (px, py, gz - 15), parent=car)
    inst(mov, parts["pen_body"], "SNSS 펜 몸체 (GO · SNSS · PVA → 혼합기)", (px, py, bzp), parent=car)
    inst(mov, parts["mixer"], "나선형 혼합기", (px, py, bzp + 10), parent=car)
    inst(mov, parts["led_ring"], "405 nm 빛 고리", (px, py, bzp + 7), parent=car)
    cone(mov, "PEEK 노즐 Ø0.41 (40 mm)", (px, py, z_tip), 0.205, 1.6, 40, "peek").parent = car
    for k, lab in enumerate(("GO", "SNSS", "PVA")):
        a = k * 2 * math.pi / 3
        o = P.cyl0(mov, f"원료 관 {lab} (실리콘 Ø3)", (px + 6 * math.cos(a), py + 6 * math.sin(a), bzp + 66), 1.5, gz - bzp - 30)
        o.parent = car
        paint(o, "silicone")
    # 받침 (BedDrop): 배양 받침 + 세 팔 너트 판 + 존재
    bed = empty(mov, "배양 받침 (BedDrop)")
    P.drive(bed, "location", 2, "-v", v=(d, '["BedDrop"]'))
    top = z_tip
    inst(mov, parts["pad_holder"], "배양 받침 (흑연 패드 2 · 수확 손잡이)", (0, -2, top - 6), parent=bed)
    nz = top - 6 - C["BED_CARRIAGE"]
    paint(P.box_lohi(mov, "너트 판 가운데", (-30, -30, nz), (30, 30, nz + C["BED_CARRIAGE"])), "petg").parent = bed
    for x, y in ((C["Z_SCREW"], -C["Z_SCREW"]), (C["Z_SCREW"], C["Z_SCREW"]), (-C["Z_SCREW"], -C["Z_SCREW"])):
        L_ = math.hypot(x, y)
        arm = P.box(mov, "너트 판 팔", (x / 2, y / 2, nz + C["BED_CARRIAGE"] / 2), (L_, 24, C["BED_CARRIAGE"]))
        arm.rotation_euler = (0, 0, math.atan2(y, x))
        arm.parent = bed
        paint(arm, "petg")
        nut = P.cyl0(mov, "받침 너트 (나일론, 나사봉에 물림)", (x, y, nz), C["NUT_R"], C["BED_CARRIAGE"])
        nut.parent = bed
        paint(nut, "nylon")
    for sx in (-1, 1):
        paint(P.box_lohi(mov, f"흑연 패드 {'+ (왼발)' if sx < 0 else '− (오른발)'}", (sx * 9.5 - 7, -10.5, top - 1.1),
                         (sx * 9.5 + 7, 11.5, top - 0.6)), "graphite").parent = bed
    inst(mov, shapes["being"], "빚는 존재 (존재 모양 장면의 being)", (0, 0, top), parent=bed)["being"] = True
    _zones(sc, L, root)
    _camera(sc, (0, 0, 150), 700, (1.0, -1.3, 0.8))
    return sc


# ---------- SC-2 도구 ----------
def _tool(c, matc, t, L):
    tip, body = 30.0, L - 45.0
    k = t["key"]
    mount = P.cyl(c, "자석 키네마틱 마운트", (0, 0, L - 7.5), 14, 15)
    paint(mount, "petg")
    seats = coll(matc, f"{k} 재료")
    mount.modifiers.new("쇠구슬 자리", "BOOLEAN")
    m = mount.modifiers[-1]
    m.operation, m.operand_type, m.collection, m.solver = "DIFFERENCE", "COLLECTION", seats, "EXACT"
    for p in ((10 * math.cos(math.pi / 2 + i * 2 * math.pi / 3), 10 * math.sin(math.pi / 2 + i * 2 * math.pi / 3), L) for i in range(3)):
        s = P.sphere(seats, "쇠구슬 자리 Ø8.2", p, 4.1)
        s.display_type, s.hide_render, s.parent = "WIRE", True, mount  # 마운트를 옮기면 함께
        s.matrix_parent_inverse = Matrix.LocRotScale(mount.location, mount.rotation_euler, mount.scale).inverted()
    if k in ("T0", "T1", "T2"):
        paint(P.cyl(c, "주사기 몸통 (PETG)", (0, 0, tip + body / 2), 9.5, body), "petg")
    else:
        paint(P.cyl(c, "도구 자루 (PETG)", (0, 0, tip + body / 2), 6, body), "petg")
    if k == "T0":
        cone(c, "PEEK 노즐 Ø0.41", (0, 0, 0), 0.205, 1.6, tip, "peek")
        paint(P.cyl(c, "나선 혼합기 자리", (0, 0, tip - 6), 2.4, 12), "peek")
    elif k == "T1":
        cone(c, "당겨 뽑은 유리 미세 피펫 (끝 Ø0.1)", (0, 0, 0), 0.05, 1.2, tip, "pipette")
    elif k == "T2":
        tube = P.realize(P.ring(c, "PEEK 흡입관 Ø1.0", (0, 0, tip / 2), 0.8, 0.5, tip), seats, "T2")
        for o in seats.all_objects:
            if o.name.startswith("PEEK 흡입관 Ø1.0 안"):
                o.parent = tube
                o.matrix_parent_inverse = Matrix.LocRotScale(tube.location, tube.rotation_euler, tube.scale).inverted()
        paint(tube, "peek")
    elif k == "T3":
        for n, cc, sz in (("PETG 활 (가로)", (0, 0, tip - 2), (34, 4, 4)), ("PETG 활 (왼)", (-15, 0, tip / 2), (4, 4, tip)),
                          ("PETG 활 (오른)", (15, 0, tip / 2), (4, 4, tip))):
            paint(P.box(c, n, cc, sz), "petg")
        paint(P.cyl(c, "나일론 낚싯줄 0.2 mm", (0, 0, 1), 0.1, 26, 0), "nylon")
    elif k == "T4":
        paint(P.cyl(c, "누름판 자루", (0, 0, tip / 2 + 2), 3, tip - 4), "petg")
        paint(P.box(c, "PETG 누름판 20 × 20", (0, 0, 2.5), (20, 20, 3), 1), "petg")
        paint(P.box(c, "실리콘 패드", (0, 0, 0.5), (20, 20, 1), 0.4), "silicone")
    elif k == "T5":
        for sx in (-0.5, 0.5):
            paint(P.cyl(c, "연필심 0.3 mm", (sx, 0, tip / 2), 0.15, tip), "graphite")
        paint(P.box(c, "실리콘 피복", (0, 0, tip / 2 + 3), (2.2, 1.2, tip - 6), 0.3), "silicone")


def build_tools(D):
    s = D["sc2"]
    th = s["tool_head"]
    sc = scene("SC-2 도구")
    dims(sc, coll(sc, "치수"), [("ToolLen", th["tool_len"], "도구 길이 (마운트 15 + 몸체 40 + 끝 30)", 50, 150)])
    root = coll(sc, "도구 T0–T5 (끝 = z 0)")
    matc = coll(sc, "재료 (CSG)")
    out = {}
    for i, t in enumerate(s["tools"]):
        c = coll(root, f"도구 — {t['key']} {t['name']}")
        _tool(c, matc, t, th["tool_len"])
        for o in c.all_objects:
            if o.parent is None:
                o.location.x += i * 40.0
        c.instance_offset = (i * 40.0, 0, 0)
        out[t["key"]] = c
    _camera(sc, (100, 0, 45), 260, (0.3, -1, 0.35))
    return sc, out


# ---------- SC-2 빛 조각가 ----------
def build_sc2(D, parts, tools, shapes):
    s, L, C = D["sc2"], D["sc2"]["layout"], D["const"]
    th = s["tool_head"]
    FX, FY, FZ = s["frame"]
    fill, gz = s["fill"], L["gz"]
    px, py = th["park"]
    sc = scene("SC-2 빛 조각가")
    root = coll(sc, "빛 조각가 SC-2")
    d = dims(sc, coll(root, "치수"), [("ToolX", px, "도구 캐리지 X (주차 = 뒤쪽)", -90, 90), ("ToolY", py, "도구 캐리지 Y", -110, 110),
                                       ("BedDrop", 72.0, "받침 내림 mm (0 = 첫 층이 수면)", 0, s["build"][2])])
    _bath(root, s["tank_inner"], fill)
    fixed = coll(root, "고정 (프레임 · 정지 부품)")
    for b in L["boxes"]:
        n = b["name"]
        if b["kind"] in ("frame", "static", "well") or (b["kind"] == "gantry" and "(쓸림)" not in n and "(주차)" not in n):
            if n.startswith(("꼭짓점", "도구 걸이")) or "방수 통" in n and "XY" not in n:
                continue
            lay_obj(fixed, b)
    h = FX / 2 - 18
    for sx in (-1, 1):
        for sy in (-1, 1):
            for zc in (18, FZ - 18):
                inst(fixed, parts["corner"], "프레임 꼭짓점", (sx * h, sy * h, zc))
    for y, lab in zip((-40, 7, 53, 100), th["pumps"][:4]):
        inst(fixed, parts["motor_pod"], f"주사기 펌프 방수 통 {lab}", (-118, y, 0))
    inst(fixed, parts["motor_pod"], f"주사기 펌프 방수 통 {th['pumps'][4]}", (118, 0, 0))
    for x, y in ((C["Z_SCREW"], -C["Z_SCREW"]), (C["Z_SCREW"], C["Z_SCREW"]), (-C["Z_SCREW"], -C["Z_SCREW"])):
        inst(fixed, parts["motor_pod"], "Z 모터 방수 통", (x, y, 0))
    paint(P.cyl0(fixed, "광엔진 렌즈 (405 + 530 nm, 이색 거울)", (0, 0, gz - 2.5), 12, 6), "lens")
    optic = coll(root, "빛 · 잉크 (점검에서 장애물 아님)")
    w = s["ink"]["well"] / 2
    paint(P.box_lohi(optic, f"잉크층 {s['ink']['depth']:g} mm", (-w + 0.5, -w + 0.5, fill - s["ink"]["depth"]), (w - 0.5, w - 0.5, fill)), "ink")
    bx, by = s["build"][0] / 2, s["build"][1] / 2
    vs = [(-bx, -by, fill), (bx, -by, fill), (bx, by, fill), (-bx, by, fill),
          (-8, -8, gz - 2.5), (8, -8, gz - 2.5), (8, 8, gz - 2.5), (-8, 8, gz - 2.5)]
    fs = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh_obj(optic, "빛길 (렌즈 → 수면 110 × 110)", vs, fs, "beam")
    ty = by + 16 + 31 + 16
    rack = coll(fixed, "도구 걸이 (뒤쪽)")
    paint(P.box_lohi(rack, "도구 걸이 막대", (-90, ty + 12, th["gz"] - 30), (90, ty + 20, th["gz"] - 22)), "petg")
    for i, t in enumerate(s["tools"]):
        if t["key"] != "T1":
            inst(rack, tools[t["key"]], f"걸이 {t['key']} {t['name']}", (-75 + 30 * i, ty, th["tip_z"] + 2))
    mov = coll(root, "움직임 (도구 갠트리 · 받침)")
    g = empty(mov, "도구 갠트리 — X 빔 (ToolY)")
    P.drive(g, "location", 1, f"v - {py}", v=(d, '["ToolY"]'))
    for dz in (-6, 6):
        o = P.cyl(mov, "X 봉 (탄소섬유 Ø8)", (0, py, th["gz"] + dz), 4, 202, 0)
        o.parent = g
        paint(o, "cf")
    car = empty(mov, "도구 캐리지 (ToolX)", parent=g)
    P.drive(car, "location", 0, f"v - {px}", v=(d, '["ToolX"]'))
    inst(mov, parts["pen_carriage"], "도구 캐리지 (자석 키네마틱)", (px, py, th["gz"] - 21), parent=car)
    inst(mov, tools["T1"], "T1 주입 주사기 (장착)", (px, py, th["tip_z"]), parent=car)
    bed = empty(mov, "배양 받침 (BedDrop)")
    P.drive(bed, "location", 2, "-v", v=(d, '["BedDrop"]'))
    top = fill
    for n, lo, hi in (("배양 받침 120 × 120", (-60, -60, top - 6), (60, 60, top)),
                      (f"받침 기둥 ({C['RISER']:g} mm)", (-20, -20, top - 6 - C["RISER"]), (20, 20, top - 6))):
        paint(P.box_lohi(mov, n, lo, hi), "petg").parent = bed
    nut = next(b for b in L["boxes"] if b["name"].startswith("받침 너트 판"))
    lay_obj(mov, nut, "petg", bed)
    for sx in (-1, 1):
        paint(P.box_lohi(mov, f"흑연 패드 {'+' if sx < 0 else '−'}", (sx * 9.5 - 7, -8.5, top - 0.8), (sx * 9.5 + 7, 13.5, top)), "graphite").parent = bed
    inst(mov, shapes["being"], "빚는 존재 (존재 모양 장면의 being)", (0, 0, top), parent=bed)["being"] = True
    desk = coll(root, "데스크톱 (수조 아래 — 모니터 없음, 수조가 모니터)")
    TI, gb, ins = s["tank_inner"][0], -6, s["insulation"]
    top_z = gb - 42 + 12
    for n, lo, hi, k in (
            (f"XPS 단열판 {ins:g} mm", (-(TI + 20) / 2, -(TI + 20) / 2, gb - 12 - ins), ((TI + 20) / 2, (TI + 20) / 2, gb - 12), "xps"),
            ("받침대 윗판", (-215, -215, top_z - 18), (215, 215, top_z), "wood"),
            ("받침대 바닥판", (-215, -215, gb - 42 - 520), (215, 215, gb - 42 - 502), "wood"),
            ("데스크톱 (GPU · Blender · 설계 콘솔)", (-185, -215, gb - 42 - 502), (25, 215, gb - 42 - 52), "pc"),
            ("키보드 서랍", (-215, -410, gb - 147), (215, -210, gb - 133), "wood"),
            ("IP68 실리콘 키보드", (-210, -380, gb - 133), (150, -260, gb - 117), "silicone")):
        paint(P.box_lohi(desk, n, lo, hi), k)
    for sx in (-1, 1):
        for sy in (-1, 1):
            paint(P.box_lohi(desk, "받침대 다리", (sx * 200 - 15, sy * 200 - 15, gb - 42 - 520), (sx * 200 + 15, sy * 200 + 15, gb - 42)), "wood")
    paint(P.ellipsoid(desk, "IP68 방수 마우스", (190, -320, gb - 126), (16, 27.5, 9)), "silicone")
    _zones(sc, L, root)
    _camera(sc, (0, -60, 60), 1250, (1.0, -1.3, 0.8))
    return sc


# ---------- 존재 모양 (메타볼) ----------
def _meta(c, key, prims, res=0.3):
    mb = bpy.data.metaballs.new(key)
    mb.resolution, mb.render_resolution, mb.threshold = res, res * 0.7, THRESH
    o = bpy.data.objects.new(key, mb)
    c.objects.link(o)
    for p in prims:
        k = p["kind"]
        if k == "sphere":
            el = mb.elements.new(type="BALL")
            el.co, el.radius = p["c"], p["r"] / K_META
        elif k == "ellipsoid":
            r = min(p["r"])
            el = mb.elements.new(type="ELLIPSOID")
            el.co, el.radius = p["c"], r / K_META
            el.size_x, el.size_y, el.size_z = (x / r for x in p["r"])
        elif k == "capsule":
            a, b = Vector(p["a"]), Vector(p["b"])
            el = mb.elements.new(type="CAPSULE")
            el.co, el.radius, el.size_x = (a + b) / 2, p["r"] / K_META, (b - a).length / 2
            el.rotation = Vector((1, 0, 0)).rotation_difference((b - a).normalized())
        el.stiffness = STIFF
        el.select = False
    return paint(o, "being")


def build_shapes(D):
    sc = scene("존재 모양")
    root = coll(sc, "존재 모양 — 메타볼 (편집 모드: 요소를 옮기고 · 키우고 · 더함)")
    out = {}
    for i, (key, sp) in enumerate(D["shapes"].items()):
        c = coll(root, f"모양 — {sp['label']} ({key})")
        if key == "coupon":
            o = paint(P.box_lohi(c, "coupon", (-6, -6, 0), (6, 6, 12)), "being")
        else:
            o = _meta(c, key, sp["prims"])
        o["SNSSShape"] = key
        o["TargetHeight"] = 0.0
        o.id_properties_ui("TargetHeight").update(description="조각가로 보낼 때 완성 높이 mm (0 = 그대로)", min=0, max=90)
        x = (i - 1.5) * 110.0
        o.location.x = x
        c.instance_offset = (x, 0, 0)
        out[key] = c
    floor = paint(P.box_lohi(root, "바닥 z 0 (아래는 잘라 냄 — 받침에 붙는 면)", (-220, -60, -0.4), (220, 60, 0)), "zone")
    floor.hide_render = True
    _camera(sc, (0, 0, 30), 330, (0.15, -1, 0.25))
    return sc, out


def build_cells(D, reduce=0.1):
    job = D.get("jobs", {}).get("sc1")
    if not job:
        return None
    return load_cells(Path(job["folder"]), reduce)


def load_cells(folder: Path, reduce=0.1):
    """작업 폴더의 이름_mesh.npz (p · n · 막 표면망) → '빚은 세포' 장면 (있으면 비우고 다시)."""
    import numpy as np

    npz = next(Path(folder).glob("*_mesh.npz"), None)
    if npz is None:
        return None
    sc = bpy.data.scenes.get("빚은 세포") or scene("빚은 세포")
    for c in list(sc.collection.children):
        for o in list(c.all_objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(c)
    c = coll(sc, f"작업 {Path(folder).name} — 양자 인공세포")
    z = np.load(npz)
    for role, label, k in (("pos", "p 세포질 (+)", "pos"), ("neg", "n 세포질 (−)", "neg"), ("mem", "막 · 피부 (GO)", "mem")):
        if f"{role}_v" not in z.files:
            continue
        v, f = z[f"{role}_v"].astype(np.float32), z[f"{role}_f"].astype(np.int32)
        me = bpy.data.meshes.new(label)
        me.vertices.add(len(v))
        me.vertices.foreach_set("co", v.ravel())
        me.loops.add(len(f) * 3)
        me.loops.foreach_set("vertex_index", f.ravel())
        me.polygons.add(len(f))
        me.polygons.foreach_set("loop_start", np.arange(0, len(f) * 3, 3, dtype=np.int32))
        me.update(calc_edges=True)
        o = bpy.data.objects.new(label, me)
        c.objects.link(o)
        dm = o.modifiers.new("줄이기", "DECIMATE")
        dm.ratio = reduce
        small = bpy.data.meshes.new_from_object(o.evaluated_get(dg_of(sc)))
        o.modifiers.remove(dm)
        o.data = small
        bpy.data.meshes.remove(me)
        o.name = f"{label} — 삼각형 {len(small.polygons)}"
        paint(o, k)
    if sc.camera is None:
        _camera(sc, (0, 0, 36), 120, (0.4, -1, 0.4))
    return sc


# ---------- 시험편 ----------
def build_coupons(D):
    cp = D["coupons"]
    sc = scene("시험편")
    root = coll(sc, "시험편")
    d = dims(sc, coll(root, "치수"), [("Dp", round(cp["dp"], 4), "침투 깊이 Dp mm (가정 — 보정값을 넣어 봄)", 0.02, 1.0),
                                       ("Ec", cp["ec"], "굳는 문턱 Ec mJ/cm² (가정)", 1, 200)])
    paint(P.box(coll(root, "SC-1"), "SC-1 시험편 12 mm", (0, 0, 6), (12, 12, 12)), "being")
    s, gp, cols = cp["square"], cp["gap"], cp["cols"]
    pitch = s + gp
    for li, (key, doses) in enumerate(cp["ladders"].items()):
        c = coll(root, f"SC-2 사다리 {key} — " + {"A": "굳힘 (높이 = Dp·ln(E/Ec))", "B": "광환원", "C": "초록 530 nm 접목"}[key])
        rows = math.ceil(len(doses) / cols)
        y0 = 40 + li * (rows * pitch + gp + 15)
        paint(P.box_lohi(c, f"받침 판 {key}", (20, y0, -2), (20 + cols * pitch + gp, y0 + rows * pitch + gp, 0)), "petg")
        for i, e in enumerate(doses):
            r, col = divmod(i, cols)
            x, y = 20 + gp + col * pitch, y0 + gp + r * pitch
            hgt = max(cp["cd_A"][i], 0.01) if key == "A" else cp["layer"] * 1.25
            o = paint(P.box_lohi(c, f"{key}{i + 1} — {e:g} mJ/cm²", (x, y, 0), (x + s, y + s, hgt)),
                      "crystal" if key == "A" else "graphite" if key == "B" else "pos")
            if key == "A":
                P.drive(o, "scale", 2, f"max(0.01, dp * log({e} / ec))", dp=(d, '["Dp"]'), ec=(d, '["Ec"]'))
    _camera(sc, (50, 80, 0), 170, (0.2, -0.6, 1.2))
    return sc


# ---------- 양자 모듈 ----------
def build_qmodule(D):
    sc = scene("양자 모듈")
    root = coll(sc, "SNSS-QB — 유기 미세공진기 Dicke 형")
    d = dims(sc, coll(root, "치수"), [("Lambda", 590, "공진 파장 nm", 400, 800), ("nSiO2", 1.46, "SiO2 굴절률", 1.3, 1.6),
                                       ("nSiN", 2.0, "Si3N4 굴절률", 1.8, 2.2), ("nAct", 1.49, "활성층 굴절률", 1.3, 1.8)])
    c = coll(root, f"층 {len(D['quantum'])}개 (아래 → 위)")
    prev = None
    for l in D["quantum"]:
        n, m = l["name"], l["material"]
        o = P.cyl0(c, n, (0, 0, 0), l["d"] / 2, l["t"])
        o["material"] = m
        if n == "활성층":
            P.drive(o, "scale", 2, "lam / (2 * n) * 1e-6", lam=(d, '["Lambda"]'), n=(d, '["nAct"]'))
            key = "active"
        elif m == "SiO2":
            P.drive(o, "scale", 2, "lam / (4 * n) * 1e-6", lam=(d, '["Lambda"]'), n=(d, '["nSiO2"]'))
            key = "sio2"
        elif m == "Si3N4":
            P.drive(o, "scale", 2, "lam / (4 * n) * 1e-6", lam=(d, '["Lambda"]'), n=(d, '["nSiN"]'))
            key = "sin"
        else:
            key = "silica"
        if prev is not None:
            P.drive(o, "location", 2, "z + t", z=(prev, "location[2]"), t=(prev, "scale[2]"))
        paint(o, key)
        prev = o
    _camera(sc, (0, 0, 0.75), 45, (0.3, -1, 0.5))
    return sc


# ---------- 병 결정 ----------
def build_bottle(D):
    b = D["bottle"]
    sc = scene("병 결정")
    root = coll(sc, "SNSS 병 결정 (이전 방향)")
    c = coll(root, "병 (PE · 약국 생리식염수 500 mL)")
    R, W, H, SH, NR, NH = b["outer_diameter_mm"] / 2, b["wall_mm"], b["body_height_mm"], b["shoulder_height_mm"], b["neck_diameter_mm"] / 2, b["neck_height_mm"]
    prof = [(0, 0), (R, 0), (R, H), (NR, H + SH), (NR, H + SH + NH), (NR - W, H + SH + NH), (NR - W, H + SH), (R - W, H), (R - W, W), (0, W)]
    vs, fs, seg = [], [], 96
    for i in range(seg):
        a = 2 * math.pi * i / seg
        vs += [(r * math.cos(a), r * math.sin(a), z) for r, z in prof]
    n = len(prof)
    for i in range(seg):
        j = (i + 1) % seg
        for k in range(n - 1):
            if prof[k][0] == 0 and prof[k + 1][0] == 0:
                continue
            fs.append((i * n + k, j * n + k, j * n + k + 1, i * n + k + 1))
    o = mesh_obj(c, "생리식염수 병 (벽 0.8 mm)", vs, fs, "bottle")
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    paint(P.cyl0(c, "뚜껑", (0, 0, H + SH + NH), b["cap_diameter_mm"] / 2, b["cap_height_mm"]), "petg")
    k = coll(root, "결정 · 절단")
    paint(P.cyl0(k, "결정 블록 — 인공세포 약 1억 개 (통째 결정)", (0, 0, b["gel_bottom"]), b["gel_r"], b["block_h"]), "crystal")
    ring = P.realize(P.ring(k, "절단선 A (띠 2 mm)", (0, 0, b["cut_z"]), R + 0.6, R, 2), k, "절단선 A")
    paint(ring, "red")
    paint(P.box(k, "절개선 B (세로)", (R + 0.3, 0, b["gel_bottom"] + b["block_h"] / 2), (0.6, 2, b["block_h"])), "red")
    paint(P.cyl0(k, "프로브 + (윗면)", (0, 0, b["gel_bottom"] + b["block_h"]), 1.0, 40), "red")
    paint(P.cyl0(k, "프로브 − (아랫면)", (0, 0, b["gel_bottom"] - 40), 1.0, 40), "black")
    _camera(sc, (0, 0, 95), 260, (0.6, -1, 0.35))
    return sc


def dg_of(sc):
    """장면의 평가된 depsgraph (머리 없는 Blender 에도 창이 없어서 context 를 바꿔 얻음)."""
    vl = sc.view_layers[0]
    with bpy.context.temp_override(scene=sc, view_layer=vl):
        dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return dg


def _camera(sc, target, dist, d):
    cam = bpy.data.objects.new(f"카메라 — {sc.name}", bpy.data.cameras.new(f"카메라 {sc.name}"))
    sc.collection.objects.link(cam)
    cam.data.lens, cam.data.clip_start, cam.data.clip_end = 50, 0.5, 20000
    t = Vector(target)
    cam.location = t + Vector(d).normalized() * dist
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
