"""모든 작품을 FreeCAD 문서로 짓는다 — 값은 design.json (snss_battery/fcparams.py) 에서.

문서 (cad_out/freecad/):
  SC1_Parts.FCStd         SC-1 출력 부품 20종 — 매개변수 개체 (속성 창의 '설계 치수'), 공통 치수 표 Params (Rod · Lm8uu)
  SC1_Sculptor.FCStd      조각가 SC-1 조립 — 수조 · 배지 · 프레임 · Z · 갠트리 · 펜 · 원료 · 전자 · 받침 + 비어 있어야 할 곳.
                          표 Params 의 PenX · PenY · BedDrop 을 바꾸면 펜과 받침이 움직임 (출력 부품은 SC1_Parts 로 링크)
  SC2_Tools.FCStd         SC-2 조각 도구 T0–T5 (자석 키네마틱 마운트 + 몸체 + 끝)
  SC2_LightSculptor.FCStd 빛 조각가 SC-2 조립 — 잉크 우물 · 두 색 광엔진 · 빛길 · 받침 기둥 · 물속 도구 갠트리 · 데스크톱 · IP68 키보드 · 마우스
  Being_Shapes.FCStd      존재 모양 4가지 (being · seed · bud · coupon) — 기본형을 끌어 고치고 '조각가로 보내기'
  Being_Cells.FCStd       마지막으로 빚은 존재의 양자 인공세포 (p · n · 막 표면망, 줄인 것)
  Coupons.FCStd           시험편 — SC-1 12 mm 정육면체 · SC-2 빛 사다리 A(굳은 두께 예측) · B · C
  QModule.FCStd           SNSS-QB 양자 모듈 — 파장 Lambda 하나로 거울 · 활성층 두께가 식으로 정해짐
  Bottle_Crystal.FCStd    이전 방향: 생리식염수 병 · 결정 블록 · 절단선 A · 절개선 B · 프로브
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import FreeCAD as App
import Part

from . import features, prim, printed
from .style import paint

V = App.Vector
R = App.Rotation


# ---------- 문서 도우미 ----------
def new_doc(name: str, label: str):
    for d in list(App.listDocuments().values()):
        if d.Name == name:
            App.closeDocument(d.Name)
    doc = App.newDocument(name)
    doc.Label = label
    return doc


def sheet(doc, rows, name="Params", label="치수"):
    """rows: (별칭, 값, 설명) — A 설명 · B 값 (별칭)."""
    sh = doc.addObject("Spreadsheet::Sheet", name)
    sh.Label = label
    sh.set("A1", "설명")
    sh.set("B1", "값")
    sh.set("C1", "별칭")
    for i, (alias, value, desc) in enumerate(rows, start=2):
        sh.set(f"A{i}", desc)
        sh.set(f"B{i}", str(value))
        sh.setAlias(f"B{i}", alias)
        sh.set(f"C{i}", alias)
    doc.recompute()
    return sh


def group(doc, label, parent=None):
    g = doc.addObject("App::DocumentObjectGroup", "Group")
    g.Label = label
    if parent is not None:
        parent.addObject(g)
    return g


def apart(doc, label, parent=None):
    p = doc.addObject("App::Part", "Part")
    p.Label = label
    if parent is not None:
        parent.addObject(p)
    return p


def feat(doc, label, shape, parent=None, color="petg", hidden=False):
    o = doc.addObject("Part::Feature", "Feature")
    o.Label = label
    o.Shape = shape
    if parent is not None:
        parent.addObject(o)
    return paint(o, color, hidden)


def pbox(doc, label, lo, hi, parent=None, color="petg", hidden=False):
    o = doc.addObject("Part::Box", "Box")
    o.Label = label
    o.Length, o.Width, o.Height = (max(hi[i] - lo[i], 1e-3) for i in range(3))
    o.Placement = App.Placement(V(*lo), R())
    if parent is not None:
        parent.addObject(o)
    return paint(o, color, hidden)


def pcyl(doc, label, base, r, h, axis=2, parent=None, color="petg", hidden=False):
    o = doc.addObject("Part::Cylinder", "Cylinder")
    o.Label = label
    o.Radius, o.Height = r, h
    rot = {2: R(), 0: R(V(0, 1, 0), 90), 1: R(V(1, 0, 0), -90)}[axis]
    o.Placement = App.Placement(V(*base), rot)
    if parent is not None:
        parent.addObject(o)
    return paint(o, color, hidden)


def material_of(name: str) -> str:
    return ("cf" if "탄소섬유" in name else "nylon" if "나일론" in name else "graphite" if "전극" in name
            else "cable" if "케이블" in name else "dark" if "프로젝터" in name else "petg")


def layout_obj(doc, b, parent, color=None, hidden=False):
    """layout.py 의 상자 하나 → Part::Box / Part::Cylinder (가로 탄소섬유 봉은 눕힌 원기둥)."""
    lo, hi, n = b["lo"], b["hi"], b["name"]
    color = color or material_of(n)
    size = [hi[i] - lo[i] for i in range(3)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    if b.get("shape") == "cyl_z":
        return pcyl(doc, n, (c[0], c[1], lo[2]), size[0] / 2, size[2], 2, parent, color, hidden)
    if "탄소섬유 봉" in n:
        ax = max(range(3), key=lambda k: size[k])
        base = list(c)
        base[ax] = lo[ax]
        return pcyl(doc, n, base, min(size) / 2, size[ax], ax, parent, color, hidden)
    return pbox(doc, n, lo, hi, parent, color, hidden)


def link(doc, target, label, placement, parent=None):
    lk = doc.addObject("App::Link", "Link")
    lk.setLink(target)
    lk.Label = label
    lk.Placement = placement
    if parent is not None:
        parent.addObject(lk)
    return lk


def at(x, y, z, rot=None):
    return App.Placement(V(x, y, z), rot or R())


def save(doc, out: Path, fname: str) -> Path:
    doc.recompute()
    p = out / fname
    doc.saveAs(str(p))
    return p


# ---------- SC-1 출력 부품 ----------
def build_parts(D, out):
    doc = new_doc("SC1_Parts", "SC-1 출력 부품 (PETG · 부모 프린터)")
    sh = sheet(doc, [("Rod", printed.COMMON["Rod"][0], printed.COMMON["Rod"][1]),
                     ("Lm8uu", printed.COMMON["Lm8uu"][0], printed.COMMON["Lm8uu"][1]),
                     ("BedX", D["const"]["PARENT_BED"][0], "부모 프린터 베드 X"), ("BedY", D["const"]["PARENT_BED"][1], "베드 Y")])
    g = group(doc, "출력 부품 20종 (부품판 — 베드 220 × 220 칸)")
    info = {p["key"]: p for p in D["parts"]}
    objs = {}
    for i, key in enumerate(printed.PARTS):
        o = features.make_part(doc, key, info.get(key), name=key)
        o.Label = f"{info[key]['name']} ×{info[key]['qty']}" if key in info else key
        for common in ("Rod", "Lm8uu"):
            if common in printed.PARTS[key][1]:
                o.setExpression(common, f"Params.{common}")
        g.addObject(o)
        paint(o, "petg_dark" if key == "led_ring" else "petg")
        objs[key] = o
    doc.recompute()
    # 부품판: 원점에 지은 부품을 보기 좋게 5 × 4 칸에 놓은 링크 (원형은 원점 그대로 — 조립이 링크함)
    board = group(doc, "부품판 (보기용 배치)")
    for i, (key, o) in enumerate(objs.items()):
        bb = o.Shape.BoundBox
        x, y = (i % 5) * 230.0, -(i // 5) * 230.0
        link(doc, o, f"판 — {o.Label}", at(x - bb.Center.x, y - bb.Center.y, -bb.ZMin), board)
    for o in objs.values():
        o.Visibility = False if App.GuiUp else o.Visibility
    return doc, objs, save(doc, out, "SC1_Parts.FCStd")


# ---------- SC-1 조각가 조립 ----------
def _bath(doc, inner, fill, parent):
    """36 큐브 유리 수조 (유리 4 mm · 바닥 6 mm) + 배지. 수조 안 바닥 = z 0."""
    X, Y, Z = inner
    glass = prim.cut(prim.box_lohi((-X / 2 - 4, -Y / 2 - 4, -6), (X / 2 + 4, Y / 2 + 4, Z)),
                     prim.box_lohi((-X / 2, -Y / 2, 0), (X / 2, Y / 2, Z + 1)))
    feat(doc, "배양조 — 36 큐브 유리 수조 (안 %g mm)" % X, glass, parent, "glass")
    pbox(doc, f"배지 — 멸균생리식염수 {fill:g} mm", (-X / 2, -Y / 2, 0), (X / 2, Y / 2, fill), parent, "bath")


def build_sc1(D, out, parts, being_shape=None):
    s, L = D["sc1"], D["sc1"]["layout"]
    C = D["const"]
    FX, FY, FZ = s["frame"]
    bz = s["build"][2]
    doc = new_doc("SC1_Sculptor", "조각가 SC-1 — 상온 수중 3D 펜 프린터")
    doc.saveAs(str(out / "SC1_Sculptor.FCStd"))  # 다른 문서(SC1_Parts)로 링크하려면 먼저 저장
    park = L["park"]
    z_tip, gz = L["z_tip"], L["gz"]
    sh = sheet(doc, [("PenX", park[0], "펜 X (주차 = 뒤쪽 가운데)"), ("PenY", park[1], "펜 Y"),
                     ("BedDrop", 72.0, f"받침 내림 mm (0 = 첫 층 · 최대 {bz:g}) — 지금은 서 있는 존재를 다 빚은 때"),
                     ("TurnTable", 0.0, "회전 받침 도 (HW 뷰포트 돌려 보기 · 빚는 동안 0)"),
                     ("ZTip", z_tip, "펜 끝 높이 (고정)"), ("GantryZ", gz, "갠트리 높이 (고정)"),
                     ("Fill", s["tank"]["fill_mm"], "배지 높이")])
    root = group(doc, "조각가 SC-1")
    _bath(doc, s["tank"]["inner_mm"], s["tank"]["fill_mm"], group(doc, "배양조 · 배지", root))
    fixed = group(doc, "고정 (프레임 · 정지 부품)", root)
    for b in L["boxes"]:
        if b["kind"] in ("frame", "static"):
            if b["name"].startswith("꼭짓점") or b["name"] == "전자 방수 통":
                continue  # 아래에서 출력 부품 링크로
            layout_obj(doc, b, fixed)
        elif b["kind"] == "gantry" and "(쓸림)" not in b["name"]:
            layout_obj(doc, b, fixed)  # Y 레일 · XY 모터 방수 통 (갠트리 높이에 고정)
    h = FX / 2 - 18
    pr = group(doc, "출력 부품 (SC1_Parts 링크)", root)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for zc in (18, FZ - 18):
                link(doc, parts["corner"], "프레임 꼭짓점", at(sx * h, sy * h, zc), fixed)
    pods = [(x, y, 0, "Z") for x, y in ((C["Z_SCREW"], -C["Z_SCREW"]), (C["Z_SCREW"], C["Z_SCREW"]), (-C["Z_SCREW"], -C["Z_SCREW"]))]
    pods += [(-118, y, 0, lab) for y, lab in ((-20, "GO"), (40, "SNSS"), (100, "PVA"))]
    pods += [(sx * 121, 121, gz - 70, "XY") for sx in (-1, 1)]
    for x, y, z, lab in pods:
        link(doc, parts["motor_pod"], f"모터 방수 통 ({lab})", at(x, y, z), pr)
        link(doc, parts["pod_lid"], f"방수 통 뚜껑 ({lab})", at(x, y, z + 44), pr)
    elec = next(b for b in L["boxes"] if b["name"] == "전자 방수 통")
    layout_obj(doc, elec, fixed, "petg_dark")
    link(doc, parts["level_probe"], "배지 전도도 전극 집게", at(-130, 160, s["tank"]["fill_mm"] - 30), pr)
    # 갠트리: X 빔은 Y 로, 캐리지 · 펜은 X 로 (표의 PenX · PenY)
    gant = apart(doc, "갠트리 — X 빔 (PenY 로 움직임)", root)
    gant.setExpression("Placement.Base.y", f"Params.PenY - {park[1]}")
    for b in L["parked"]:
        if b["name"].startswith("X 빔"):
            lo, hi = b["lo"], b["hi"]
            for dz in (-6, 6):
                pcyl(doc, "X 봉 (탄소섬유 Ø8)", (lo[0], (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2 + dz), 4, hi[0] - lo[0], 0, gant, "cf")
    for sx in (-1, 1):
        link(doc, parts["y_end"], "X 봉 끝단", at(sx * 121, park[1], gz - 15, R(V(0, 0, 1), 90)), gant)
    car = apart(doc, "캐리지 · 펜 (PenX 로 움직임)", gant)
    car.setExpression("Placement.Base.x", f"Params.PenX - {park[0]}")
    px, py = park
    body_z = z_tip + 40
    link(doc, parts["pen_carriage"], "펜 캐리지 (자석 키네마틱)", at(px, py, gz - 15), car)
    link(doc, parts["pen_body"], "SNSS 펜 몸체 (GO · SNSS · PVA → 혼합기)", at(px, py, body_z), car)
    link(doc, parts["mixer"], "나선형 혼합기", at(px, py, body_z + 10), car)
    link(doc, parts["led_ring"], "405 nm 빛 고리", at(px, py, body_z + 7), car)
    noz = doc.addObject("Part::Cone", "Cone")
    noz.Label = "PEEK 노즐 Ø0.41 (40 mm)"
    noz.Radius1, noz.Radius2, noz.Height = 0.205, 1.6, 40
    noz.Placement = at(px, py, z_tip)
    car.addObject(noz)
    paint(noz, "peek")
    for k, lab in enumerate(("GO", "SNSS", "PVA")):  # 원료 관 (실리콘) — 펜 위로
        a = k * 2 * math.pi / 3
        pcyl(doc, f"원료 관 {lab} (실리콘 Ø3)", (px + 6 * math.cos(a), py + 6 * math.sin(a), body_z + 66), 1.5, gz - body_z - 30, 2, car, "silicone")
    # 받침 (BedDrop 만큼 내려감): 배양 받침(흑연 패드) 바로 밑에 세 팔 너트 판 — 다 내려가도 Z 모터 방수 통 위 2 mm
    bed = apart(doc, "배양 받침 (BedDrop 으로 내려감)", root)
    bed.setExpression("Placement.Base.z", "-Params.BedDrop")
    top = z_tip  # BedDrop = 0 일 때 받침 윗면 = 펜 끝
    turn_h = D["console"]["turntable"]["disc_sc1_mm"]
    nz = top - 6 - turn_h - C["BED_CARRIAGE"]
    turn = apart(doc, "회전 받침 (TurnTable)", bed)
    turn.setExpression("Placement.Rotation.Angle", "Params.TurnTable * 1 deg")
    link(doc, parts["pad_holder"], "3D 프린팅 패드 — 배양 받침 (흑연 패드 2 · 수확 손잡이)", at(0, -2, top - 6), turn)
    link(doc, parts["turn_disc"], "회전 자석 원판", at(0, 0, nz + C["BED_CARRIAGE"]), turn)
    link(doc, parts["micro_pod"], "회전 받침 방수 통 (N20, 너트 판 밑)", at(0, 0, nz - 30), bed)
    pbox(doc, "너트 판 가운데 (받침 자리)", (-30, -30, nz), (30, 30, nz + C["BED_CARRIAGE"]), bed)
    for x, y in ((C["Z_SCREW"], -C["Z_SCREW"]), (C["Z_SCREW"], C["Z_SCREW"]), (-C["Z_SCREW"], -C["Z_SCREW"])):
        ang = math.degrees(math.atan2(y, x))
        arm = pbox(doc, "너트 판 팔", (0, -12, 0), (math.hypot(x, y), 12, C["BED_CARRIAGE"]), bed)
        rot = R(V(0, 0, 1), ang)
        arm.Placement = App.Placement(rot.multVec(V(0, -12, 0)) + V(0, 0, nz), rot)  # 상자 원점은 모서리 → 가운데 줄이 나사봉을 향하게
        pcyl(doc, "받침 너트 (나일론, 나사봉에 물림)", (x, y, nz), C["NUT_R"], C["BED_CARRIAGE"], 2, bed, "nylon")
    for sx in (-1, 1):
        pbox(doc, f"흑연 패드 {'+ (왼발)' if sx < 0 else '− (오른발)'}", (sx * 9.5 - 7, -11 + 0.5, top - 1.1), (sx * 9.5 + 7, 11 + 0.5, top - 0.6), turn, "graphite")
    if being_shape is not None:
        o = feat(doc, "빚는 존재 (Being_Shapes 의 모양)", being_shape.copy(), turn, "being")
        o.Placement = at(0, 0, top)
    _console(doc, D, parts, root, "sc1")
    # 비어 있어야 할 곳 · 쓸고 지나가는 범위 (투명, 숨김)
    zones = group(doc, "비어 있어야 할 곳 (layout.py zones)", root)
    for z in L["zones"]:
        layout_obj(doc, z, zones, "zone", hidden=True)
    sweep = group(doc, "움직이는 부품이 쓸고 지나가는 범위", root)
    for b in L["boxes"]:
        if b["kind"] in ("gantry", "bed") and "(쓸림)" in b["name"]:
            layout_obj(doc, b, sweep, "sweep", hidden=True)
    return doc, bed, save(doc, out, "SC1_Sculptor.FCStd")


def _console(doc, D, parts, root, machine):
    """수조 바로 밑에 붙는 방수 데스크톱 + 바닥에 놓는 IP68 키보드 · 마우스 · IP66 모니터 (snss_battery/console.py)."""
    k = D["console"]
    dk, ip = k["desktop"], k["inputs"]
    g = group(doc, "수조 콘솔 — 방수 데스크톱 · 키보드 · 마우스 (HW 뷰포트)", root)
    X, Y = dk["footprint_mm"]
    t0, tray_lo = -6.0, -6.0 - dk["tray_mm"]
    tray = prim.cut(prim.box_lohi((-X / 2 - 10, -Y / 2 - 10, tray_lo), (X / 2 + 10, Y / 2 + 10, t0 + 10)),
                    prim.box_lohi((-X / 2 - 1, -Y / 2 - 1, t0 - 2), (X / 2 + 1, Y / 2 + 1, t0 + 11)))
    feat(doc, "수조 받침 테 — PETG + EPDM 패킹 (수조가 앉는 턱)", tray, g, "petg_dark")
    top, bot = k["desktop_top_z"], k["desktop_bottom_z"]
    pbox(doc, f"XPS 단열 {dk['insulation_mm']:g} mm (본체 열 → 배지 약 {k['heat_into_bath_w']:.1f} W)", (-X / 2, -Y / 2, top), (X / 2, Y / 2, tray_lo), g, "xps")
    feat(doc, "방수 데스크톱 본체 — IP67 · 팬 없음", prim.box((0, 0, (top + bot) / 2), (X, Y, top - bot), 6), g, "pc")
    fins = [prim.box_lohi((X / 2 if sx > 0 else -X / 2 - dk["fin_mm"], -Y / 2 + 20 + i * (Y - 40) / 12 - 1.5, bot + 8),
                          (X / 2 + dk["fin_mm"] if sx > 0 else -X / 2, -Y / 2 + 20 + i * (Y - 40) / 12 + 1.5, top - 8)) for sx in (-1, 1) for i in range(13)]
    feat(doc, "방열 핀 (양 옆, 방 공기로)", Part.makeCompound(fins), g, "pc")
    feat(doc, "고무 다리 4", Part.makeCompound([prim.cyl((sx * (X / 2 - 30), sy * (Y / 2 - 30), bot - dk["feet_mm"] / 2), 15, dk["feet_mm"])
                                               for sx in (-1, 1) for sy in (-1, 1)]), g, "dark")
    fy = -Y / 2
    feat(doc, "앞판 IP67 단자 (M12 키보드 · 마우스 · USB-C · 예비)",
         Part.makeCompound([prim.cyl((-90 + i * 40, fy - 4, top - 30), 7, 8, 1) for i in range(4)]), g, "silicone")
    # 바닥에 놓고 쓰는 키보드 · 마우스 · 모니터 (데스크톱 고무 다리와 같은 바닥)
    fl = k["floor_z"]
    mw0, md0, mt = ip["mat_mm"]
    my = fy - ip["front_gap_mm"] - md0 / 2
    pbox(doc, "바닥 깔개 — IP68 실리콘", (-mw0 / 2, my - md0 / 2, fl), (mw0 / 2, my + md0 / 2, fl + mt), g, "dark")
    kw, kd, kh = ip["keyboard_mm"]
    kx = -mw0 / 2 + 20 + kw / 2
    feat(doc, "IP68 실리콘 키보드 — 바닥에 놓음", prim.box((kx, my, fl + mt + kh / 2), (kw, kd, kh), 4), g, "silicone")
    mw, md, mh = ip["mouse_mm"]
    feat(doc, "IP68 방수 마우스 — 바닥에 놓음", prim.ellipsoid((mw0 / 2 - 20 - mw / 2, my, fl + mt + mh / 2), (mw / 2, md / 2, mh / 2)), g, "silicone")
    W, H, T = dk["monitor_mm"]
    sw, sd_, sh = dk["monitor_stand_mm"]
    for n, ((side, col), m) in enumerate(zip([(1, 0), (-1, 0), (1, 1), (-1, 1)], dk["monitors"][: dk["monitor_count"]])):
        x, y = side * (X / 2 + 60 + W / 2 + col * (W + 40)), -Y / 2 + 40
        pbox(doc, f"모니터 {n + 1} 받침 발 — 바닥에 놓임", (x - sw / 2, y - sd_ / 2, fl), (x + sw / 2, y + sd_ / 2, fl + 12), g, "petg_dark")
        pbox(doc, f"모니터 {n + 1} 받침 기둥", (x - 15, y + sd_ / 2 - 40, fl + 12), (x + 15, y + sd_ / 2 - 20, fl + sh + H / 2), g, "pc")
        feat(doc, f"{m[0]} — IP66 방수 모니터", prim.box((x, y + sd_ / 2 - 52, fl + sh + H / 2), (W + 16, T, H + 16), 4), g, "pc")
    if machine == "sc1":
        link(doc, parts["port_panel"], "단자판 — 데스크톱 뒤 (아날로그 · 디지털 · 양자)", at(0, Y / 2 + 2, (top + bot) / 2, R(V(1, 0, 0), 90)), g)
    return g


# ---------- SC-2 도구 ----------
def _tool(doc, t, tool_len, parent):
    """자석 키네마틱 마운트 (Ø28 × 15, 쇠구슬 자리 3) + 몸체 40 + 끝 30 — 끝이 z 0, 위가 z tool_len."""
    p = apart(doc, f"{t['key']} {t['name']}", parent)
    tip, body = 30.0, tool_len - 45.0
    mount = prim.cut(prim.cyl((0, 0, tool_len - 7.5), 14, 15),
                     *[prim.sphere(c, 4.1) for c in prim.polar(3, 10, tool_len, math.pi / 2)])
    feat(doc, "자석 키네마틱 마운트 (쇠구슬 자리 3)", mount, p, "petg")
    k = t["key"]
    if k in ("T0", "T1", "T2"):
        feat(doc, "주사기 몸통 (PETG)", prim.cyl((0, 0, tip + body / 2), 9.5, body), p, "petg")
    else:
        feat(doc, "도구 자루 (PETG)", prim.cyl((0, 0, tip + body / 2), 6, body), p, "petg")
    if k == "T0":
        feat(doc, "PEEK 노즐 Ø0.41", Part.makeCone(0.205, 1.6, tip, V(0, 0, 0)), p, "peek")
        feat(doc, "나선 혼합기 자리 (Ø3.2)", prim.cyl((0, 0, tip - 6), 2.4, 12), p, "peek")
    elif k == "T1":
        feat(doc, "당겨 뽑은 유리 미세 피펫 (붕규산, 끝 Ø0.1)", Part.makeCone(0.05, 1.2, tip, V(0, 0, 0)), p, "pipette")
    elif k == "T2":
        feat(doc, "PEEK 흡입관 Ø1.0", prim.ring((0, 0, tip / 2), 0.8, 0.5, tip), p, "peek")
    elif k == "T3":
        bow = prim.union(prim.box((0, 0, tip - 2), (34, 4, 4)), prim.box((-15, 0, tip / 2), (4, 4, tip)), prim.box((15, 0, tip / 2), (4, 4, tip)))
        feat(doc, "PETG 활", bow, p, "petg")
        feat(doc, "나일론 낚싯줄 0.2 mm", prim.cyl((0, 0, 1), 0.1, 26, 0), p, "nylon")
    elif k == "T4":
        feat(doc, "누름판 자루", prim.cyl((0, 0, tip / 2 + 2), 3, tip - 4), p, "petg")
        feat(doc, "PETG 누름판 20 × 20", prim.box((0, 0, 2.5), (20, 20, 3), 1), p, "petg")
        feat(doc, "실리콘 패드", prim.box((0, 0, 0.5), (20, 20, 1), 0.4), p, "silicone")
    elif k == "T5":
        for sx in (-0.5, 0.5):
            feat(doc, "연필심 0.3 mm (흑연)", prim.cyl((sx, 0, tip / 2), 0.15, tip), p, "graphite")
        feat(doc, "실리콘 피복", prim.cut(prim.box((0, 0, tip / 2 + 3), (2.2, 1.2, tip - 6), 0.3),
                                         prim.cyl((-0.5, 0, tip / 2), 0.16, tip + 2), prim.cyl((0.5, 0, tip / 2), 0.16, tip + 2)), p, "silicone")
    return p


def build_tools(D, out):
    s = D["sc2"]
    th = s["tool_head"]
    doc = new_doc("SC2_Tools", "SC-2 조각 도구 T0–T5 (물속, 금속 없음)")
    sheet(doc, [("ToolLen", th["tool_len"], "도구 길이 (마운트 15 + 몸체 40 + 끝 30)"), ("TipZ", th["tip_z"], "도구 면 높이 (끝)"),
                ("GantryZ", th["gz"], "도구 갠트리 높이")])
    g = group(doc, "도구 (끝 = z 0)")
    tools = {}
    for i, t in enumerate(s["tools"]):
        p = _tool(doc, t, th["tool_len"], g)
        p.Placement = at(i * 40.0, 0, 0)
        tools[t["key"]] = p
    return doc, tools, save(doc, out, "SC2_Tools.FCStd")


# ---------- SC-2 빛 조각가 조립 ----------
def build_sc2(D, out, parts, tools, being_shape=None):
    s, L = D["sc2"], D["sc2"]["layout"]
    th, C = s["tool_head"], D["const"]
    FX, FY, FZ = s["frame"]
    fill, gz = s["fill"], L["gz"]
    doc = new_doc("SC2_LightSculptor", "빛 조각가 SC-2 — 배지가 모니터")
    doc.saveAs(str(out / "SC2_LightSculptor.FCStd"))
    px, py = th["park"]
    sheet(doc, [("ToolX", px, "도구 캐리지 X (주차 = 뒤쪽)"), ("ToolY", py, "도구 캐리지 Y"),
                ("BedDrop", 72.0, "받침 내림 mm (0 = 첫 층이 수면)"), ("TurnTable", 0.0, "회전 받침 도 (HW 뷰포트)"),
                ("Fill", fill, "배지 수면 = 노광면"),
                ("Throw", s["throw"], "수면 → 광엔진 렌즈"), ("InkDepth", s["ink"]["depth"], "잉크층 두께")])
    root = group(doc, "빛 조각가 SC-2")
    _bath(doc, s["tank_inner"], fill, group(doc, "배양조 · 배지", root))
    fixed = group(doc, "고정 (프레임 · 정지 부품)", root)
    for b in L["boxes"]:
        n = b["name"]
        if b["kind"] in ("frame", "static", "well"):
            if n.startswith("꼭짓점") or n.startswith("도구 걸이"):
                continue
            layout_obj(doc, b, fixed)
        elif b["kind"] == "gantry" and "(쓸림)" not in n and "(주차)" not in n:
            layout_obj(doc, b, fixed)
    h = FX / 2 - 18
    for sx in (-1, 1):
        for sy in (-1, 1):
            for zc in (18, FZ - 18):
                link(doc, parts["corner"], "프레임 꼭짓점", at(sx * h, sy * h, zc), fixed)
    w = s["ink"]["well"] / 2
    optic = group(doc, "빛 · 잉크 (점검에서 장애물 아님)", root)
    pbox(doc, f"잉크층 {s['ink']['depth']:g} mm (GO · 감광 PVA · NBD · 에오신 Y)", (-w + 0.5, -w + 0.5, fill - s["ink"]["depth"]),
         (w - 0.5, w - 0.5, fill), optic, "ink")
    # 광엔진 · 빛길
    pcyl(doc, "광엔진 렌즈 (405 + 530 nm, 이색 거울)", (0, 0, gz - 2.5), 12, 6, 2, fixed, "lens")
    bx, by = s["build"][0] / 2, s["build"][1] / 2
    beam = Part.makeLoft([Part.makePolygon([V(-bx, -by, fill), V(bx, -by, fill), V(bx, by, fill), V(-bx, by, fill), V(-bx, -by, fill)]),
                          Part.makePolygon([V(-8, -8, gz - 2.5), V(8, -8, gz - 2.5), V(8, 8, gz - 2.5), V(-8, 8, gz - 2.5), V(-8, -8, gz - 2.5)])], True, True)
    feat(doc, "빛길 (렌즈 → 수면 110 × 110)", beam, optic, "beam")
    # 도구 걸이 + 도구 (T1 은 캐리지에)
    ty = by + 16 + 31 + 16
    rack = group(doc, "도구 걸이 (뒤쪽)", fixed)
    pbox(doc, "도구 걸이 막대 (PETG)", (-90, ty + 12, th["gz"] - 30), (90, ty + 20, th["gz"] - 22), rack)
    for i, t in enumerate(s["tools"]):
        if t["key"] == "T1":
            continue
        link(doc, tools[t["key"]], f"걸이 {t['key']} {t['name']}", at(-75 + 30 * i, ty, th["tip_z"] + 2), rack)
    for y, lab in zip((-40, 7, 53, 100), th["pumps"][:4]):
        link(doc, parts["motor_pod"], f"주사기 펌프 방수 통 {lab}", at(-118, y, 0), fixed)
    link(doc, parts["motor_pod"], f"주사기 펌프 방수 통 {th['pumps'][4]}", at(118, 0, 0), fixed)
    for x, y in ((C["Z_SCREW"], -C["Z_SCREW"]), (C["Z_SCREW"], C["Z_SCREW"]), (-C["Z_SCREW"], -C["Z_SCREW"])):
        link(doc, parts["motor_pod"], "Z 모터 방수 통", at(x, y, 0), fixed)
    # 도구 갠트리 (ToolY · ToolX)
    gant = apart(doc, "도구 갠트리 — X 빔 (ToolY)", root)
    gant.setExpression("Placement.Base.y", f"Params.ToolY - {py}")
    g = th["gz"]
    for dz in (-6, 6):
        pcyl(doc, "X 봉 (탄소섬유 Ø8)", (-101, py, g + dz), 4, 202, 0, gant, "cf")
    car = apart(doc, "도구 캐리지 (ToolX)", gant)
    car.setExpression("Placement.Base.x", f"Params.ToolX - {px}")
    link(doc, parts["pen_carriage"], "도구 캐리지 (자석 키네마틱)", at(px, py, g - 21), car)
    link(doc, tools["T1"], "T1 주입 주사기 (장착)", at(px, py, th["tip_z"]), car)
    # 받침 (BedDrop)
    bed = apart(doc, "배양 받침 (BedDrop 으로 내려감)", root)
    bed.setExpression("Placement.Base.z", "-Params.BedDrop")
    top = fill
    pbox(doc, f"받침 기둥 ({C['RISER'] - 30:g} mm + 방수 통 30)", (-20, -20, top - 6 - C["RISER"]), (20, 20, top - 36), bed)
    link(doc, parts["micro_pod"], "회전 받침 방수 통 (N20, 기둥 위)", at(0, 0, top - 36), bed)
    turn = apart(doc, "회전 받침 (TurnTable)", bed)
    turn.setExpression("Placement.Rotation.Angle", "Params.TurnTable * 1 deg")
    link(doc, parts["turntable"], "3D 프린팅 패드 — 회전 받침 원판 Ø118", at(0, 0, top - 6), turn)
    nut = next(b for b in L["boxes"] if b["name"].startswith("받침 너트 판"))
    layout_obj(doc, nut, bed, "petg")
    for sx in (-1, 1):
        pbox(doc, f"흑연 패드 {'+' if sx < 0 else '−'}", (sx * 9.5 - 7, -8.7, top - 1.0), (sx * 9.5 + 7, 13.7, top - 0.2), turn, "graphite")
    if being_shape is not None:
        o = feat(doc, "빚는 존재 (Being_Shapes 의 모양)", being_shape.copy(), turn, "being")
        o.Placement = at(0, 0, top)
    _console(doc, D, parts, root, "sc2")
    zones = group(doc, "비어 있어야 할 곳 (layout.py zones)", root)
    for z in L["zones"]:
        layout_obj(doc, z, zones, "zone", hidden=True)
    sweep = group(doc, "움직이는 부품이 쓸고 지나가는 범위", root)
    for b in L["boxes"]:
        if b["kind"] in ("gantry", "bed") and "(쓸림)" in b["name"]:
            layout_obj(doc, b, sweep, "sweep", hidden=True)
    return doc, save(doc, out, "SC2_LightSculptor.FCStd")


# ---------- 존재 모양 ----------
def _prim_obj(doc, p, parent):
    k = p["kind"]
    if k == "ellipsoid":
        o = features.make_ellipsoid(doc, p["name"], p["c"], p["r"])
    elif k == "sphere":
        o = doc.addObject("Part::Sphere", "Sphere")
        o.Label = p["name"]
        o.Radius = p["r"]
        o.Placement = at(*p["c"])
    elif k == "capsule":
        o = features.make_capsule(doc, p["name"], p["a"], p["b"], p["r"])
    else:
        o = pbox(doc, p["name"], p["lo"], p["hi"])
    parent.addObject(o)
    return paint(o, "being")


def build_shapes(D, out):
    doc = new_doc("Being_Shapes", "존재 모양 — 고쳐서 조각가로 보냄")
    sheet(doc, [("Floor", 0.0, "바닥 (이 아래는 잘라 냄 — 받침에 붙는 면)")])
    shapes = {}
    for i, (key, sp) in enumerate(D["shapes"].items()):
        g = apart(doc, f"{sp['label']} — {key}")
        g.Placement = at((i - 1.5) * 110.0, 0, 0)
        prims = group(doc, "기본형 (끌어 고치기 · 더하기)", g)
        objs = [_prim_obj(doc, p, prims) for p in sp["prims"]]
        if len(objs) > 1:
            fu = doc.addObject("Part::MultiFuse", "Fusion")
            fu.Shapes = objs
            fu.Refine = True
            fu.Label = f"합 — {key}"
            g.addObject(fu)
        else:
            fu = objs[0]
        floor = pbox(doc, f"바닥 아래 — {key}", (-200, -200, -100), (200, 200, 0), g, "zone", hidden=True)
        floor.setExpression("Placement.Base.z", "Params.Floor - 100")
        cut = doc.addObject("Part::Cut", "Cut")
        cut.Base, cut.Tool = fu, floor
        cut.Refine = True
        cut.Label = f"모양 — {key}"
        g.addObject(cut)
        cut.addProperty("App::PropertyString", "SNSSShape", "SNSS", "조각가로 보낼 때 쓰는 이름").SNSSShape = key
        cut.addProperty("App::PropertyLength", "TargetHeight", "SNSS", "완성 높이 (0 = 이 모양 그대로)").TargetHeight = 0
        paint(cut, "being")
        shapes[key] = cut
    doc.recompute()
    return doc, shapes, save(doc, out, "Being_Shapes.FCStd")


def build_cells(D, out, reduce=0.9):
    """마지막 SC-1 작업의 세포 표면망 (sculpt_out/jobs/*/이름_pos · neg · mem.stl) 을 줄여서."""
    import Mesh

    job = D.get("jobs", {}).get("sc1")
    if not job:
        return None, None
    doc = new_doc("Being_Cells", "빚은 존재 — 양자 인공세포 (p · n · 막)")
    g = group(doc, f"마지막 작업 {Path(job['folder']).name}")
    for role, label, col in (("pos", "p 세포질 (+)", "pos"), ("neg", "n 세포질 (−)", "neg"), ("mem", "막 · 피부 (GO)", "mem")):
        f = job["stl"].get(role)
        if not f or not Path(f).exists():
            continue
        m = Mesh.Mesh(f)
        try:
            m.decimate(0.05, reduce)
        except Exception:
            pass
        o = doc.addObject("Mesh::Feature", "Mesh")
        o.Mesh = m
        o.Label = f"{label} — 삼각형 {m.CountFacets}"
        g.addObject(o)
        paint(o, col)
    return doc, save(doc, out, "Being_Cells.FCStd")


# ---------- 시험편 ----------
def build_coupons(D, out):
    cp = D["coupons"]
    doc = new_doc("Coupons", "시험편 — SC-1 정육면체 · SC-2 빛 상수 사다리")
    sheet(doc, [("Square", cp["square"], "사다리 한 칸"), ("Gap", cp["gap"], "칸 간격"), ("Dp", round(cp["dp"], 4), "침투 깊이 Dp (가정)"),
                ("Ec", cp["ec"], "굳는 문턱 Ec mJ/cm² (가정)"), ("Layer", cp["layer"], "층 두께")])
    pbox(doc, "SC-1 시험편 12 mm (잉크 · 용량 보정)", (-6, -6, 0), (6, 6, 12), group(doc, "SC-1"), "being")
    s, gp, cols = cp["square"], cp["gap"], cp["cols"]
    pitch = s + gp
    for li, (key, doses) in enumerate(cp["ladders"].items()):
        g = group(doc, f"SC-2 사다리 {key} — " + {"A": "굳힘 (굳은 두께 = Dp·ln(E/Ec) 예측)", "B": "광환원 (2단자 저항)",
                                                  "C": "초록 530 nm 접목 (개방 전위)"}[key])
        rows = math.ceil(len(doses) / cols)
        y0 = 40 + li * (rows * pitch + gp + 15)
        pbox(doc, f"받침 판 {key}", (20, y0, -2), (20 + cols * pitch + gp, y0 + rows * pitch + gp, 0), g, "petg")
        for i, e in enumerate(doses):
            r, c = divmod(i, cols)
            x, y = 20 + gp + c * pitch, y0 + gp + r * pitch
            if key == "A":
                hgt = max(cp["cd_A"][i], 0.01)
                o = pbox(doc, f"A{i + 1} — {e:g} mJ/cm²", (x, y, 0), (x + s, y + s, hgt), g, "crystal")
                cd = f"Params.Dp * log({e} / Params.Ec)"
                o.setExpression("Height", f"{cd} > 0.01 ? {cd} : 0.01")
            else:
                o = pbox(doc, f"{key}{i + 1} — {e:g} mJ/cm²", (x, y, 0), (x + s, y + s, cp["layer"] * 1.25), g,
                         "graphite" if key == "B" else "pos")
    return doc, save(doc, out, "Coupons.FCStd")


# ---------- 양자 모듈 SNSS-QB ----------
def build_qmodule(D, out):
    doc = new_doc("QModule", "SNSS-QB 양자 모듈 — 유기 미세공진기 Dicke 형")
    layers = D["quantum"]
    pairs = sum(1 for l in layers if l["name"].startswith("아래 거울 SiO2"))
    sheet(doc, [("Lambda", 590, "공진 파장 nm"), ("nSiO2", 1.46, "SiO2 굴절률"), ("nSiN", 2.00, "Si3N4 굴절률"),
                ("nAct", 1.49, "활성층 (PMMA + 페릴렌) 굴절률"), ("D", 24, "거울 · 활성층 지름"), ("Dsub", 25, "기판 · 덮개 지름"),
                ("Tsub", 1.0, "기판 두께"), ("Tcap", 0.5, "덮개 두께"), ("Pairs", pairs, "거울 쌍 수 (바꾸면 다시 짓기)")])
    g = group(doc, f"층 {len(layers)}개 (아래 → 위)")
    prev = None
    for l in layers:
        n, m = l["name"], l["material"]
        o = doc.addObject("Part::Cylinder", "Layer")
        o.Label = n
        if n == "기판":
            rexp, hexp, col = "Params.Dsub / 2", "Params.Tsub", "silica"
        elif n == "덮개":
            rexp, hexp, col = "Params.Dsub / 2", "Params.Tcap", "silica"
        elif n == "활성층":
            rexp, hexp, col = "Params.D / 2", "Params.Lambda / (2 * Params.nAct) * 1e-6", "active"
        elif m == "SiO2":
            rexp, hexp, col = "Params.D / 2", "Params.Lambda / (4 * Params.nSiO2) * 1e-6", "sio2"
        else:
            rexp, hexp, col = "Params.D / 2", "Params.Lambda / (4 * Params.nSiN) * 1e-6", "sin"
        o.Radius, o.Height = l["d"] / 2, l["t"]
        o.setExpression("Radius", rexp)
        o.setExpression("Height", hexp)
        if prev is not None:
            o.setExpression("Placement.Base.z", f"{prev.Name}.Placement.Base.z + {prev.Name}.Height")
        o.addProperty("App::PropertyString", "Material", "SNSS", "재질").Material = m
        g.addObject(o)
        paint(o, col)
        prev = o
    return doc, save(doc, out, "QModule.FCStd")


# ---------- 이전 방향: 병 · 결정 ----------
def build_bottle(D, out):
    b = D["bottle"]
    doc = new_doc("Bottle_Crystal", "SNSS 병 결정 (이전 방향) — 생리식염수 병 · 결정 블록")
    sheet(doc, [("OD", b["outer_diameter_mm"], "병 바깥 지름"), ("Wall", b["wall_mm"], "병 벽"), ("BodyH", b["body_height_mm"], "몸통 높이"),
                ("ShoulderH", b["shoulder_height_mm"], "어깨 높이"), ("NeckD", b["neck_diameter_mm"], "목 지름"),
                ("NeckH", b["neck_height_mm"], "목 높이"), ("CapD", b["cap_diameter_mm"], "뚜껑 지름"), ("CapH", b["cap_height_mm"], "뚜껑 높이"),
                ("GelR", round(b["gel_r"], 4), "결정 반지름"), ("GelBottom", b["gel_bottom"], "결정 바닥"),
                ("BlockH", round(b["block_h"], 4), "다듬은 결정 블록 높이"), ("CutZ", round(b["cut_z"], 4), "절단선 A 높이")])
    g = group(doc, "병 (PE · 약국 생리식염수 500 mL)")

    def stack(label, inset):
        ins = f" - {inset}" if inset else ""
        body = doc.addObject("Part::Cylinder", "Cyl")
        body.setExpression("Radius", f"Params.OD / 2{ins}")
        body.setExpression("Height", "Params.BodyH" + (f" - {inset}" if inset else ""))
        if inset:
            body.setExpression("Placement.Base.z", "Params.Wall")
        sh = doc.addObject("Part::Cone", "Cone")
        sh.setExpression("Radius1", f"Params.OD / 2{ins}")
        sh.setExpression("Radius2", f"Params.NeckD / 2{ins}")
        sh.setExpression("Height", "Params.ShoulderH")
        sh.setExpression("Placement.Base.z", "Params.BodyH")
        nk = doc.addObject("Part::Cylinder", "Cyl")
        nk.setExpression("Radius", f"Params.NeckD / 2{ins}")
        nk.setExpression("Height", "Params.NeckH" + (" + 1" if inset else ""))
        nk.setExpression("Placement.Base.z", "Params.BodyH + Params.ShoulderH")
        fu = doc.addObject("Part::MultiFuse", "Fusion")
        fu.Shapes = [body, sh, nk]
        fu.Refine = True
        fu.Label = label
        for o in (body, sh, nk):
            o.Visibility = False
        return fu

    outer = stack("병 바깥", 0)
    inner = stack("병 안", "Params.Wall")
    bottle = doc.addObject("Part::Cut", "Cut")
    bottle.Base, bottle.Tool = outer, inner
    bottle.Label = "생리식염수 병 (벽 0.8 mm)"
    g.addObject(bottle)
    for o in (outer, inner):
        g.addObject(o)
    paint(bottle, "bottle")
    cap = doc.addObject("Part::Cylinder", "Cyl")
    cap.Label = "뚜껑"
    cap.setExpression("Radius", "Params.CapD / 2")
    cap.setExpression("Height", "Params.CapH")
    cap.setExpression("Placement.Base.z", "Params.BodyH + Params.ShoulderH + Params.NeckH")
    g.addObject(paint(cap, "petg"))
    c = group(doc, "결정 · 절단")
    blk = doc.addObject("Part::Cylinder", "Cyl")
    blk.Label = "결정 블록 — 인공세포 약 1억 개 (통째 결정)"
    blk.setExpression("Radius", "Params.GelR")
    blk.setExpression("Height", "Params.BlockH")
    blk.setExpression("Placement.Base.z", "Params.GelBottom")
    c.addObject(paint(blk, "crystal"))
    ringA = feat(doc, "절단선 A (띠 2 mm)", prim.ring((0, 0, 0), b["outer_diameter_mm"] / 2 + 0.6, b["outer_diameter_mm"] / 2, 2), c, "red")
    ringA.setExpression("Placement.Base.z", "Params.CutZ")
    lineB = feat(doc, "절개선 B (세로)", prim.box((b["outer_diameter_mm"] / 2 + 0.3, 0, b["block_h"] / 2), (0.6, 2, b["block_h"])), c, "red")
    lineB.setExpression("Placement.Base.z", "Params.GelBottom")
    for z, col, lab in ((b["gel_bottom"] + b["block_h"], "red", "프로브 + (윗면)"), (b["gel_bottom"] - 40, "black", "프로브 − (아랫면)")):
        feat(doc, lab, prim.cyl((0, 0, z + 20), 1.0, 40), c, col)
    return doc, save(doc, out, "Bottle_Crystal.FCStd")
