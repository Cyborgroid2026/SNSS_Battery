"""브라우저 속 Blender — Blender(머리 없이)가 웹 서버가 되어 장면을 보내고 · 고치고 · 점검하고 · 조각가로 보냄.

브라우저(VS Code 통합 브라우저)는 Blender 가 계산한 메시(평가된 모디파이어 · 드라이버 · 메타볼)를 three.js 로 그리고,
Blender 키맵(가운데 끌기 돌려 보기 · Shift 옮겨 보기 · 휠 · 숫자판 1 3 7 · Home)으로 살핀다.
'HW 뷰포트' 로 바꾸면 같은 입력이 수조 콘솔(console.py)의 기계 동작이 된다 — 회전 받침 · 받침 오르내림 · 보기 빛, G-code 로 기록.

bpy 는 주 실에서만: HTTP 실은 일을 줄(queue)에 넣고, serve_web.py 의 주 고리가 꺼내 처리한다.
"""

from __future__ import annotations

import json
import math
import struct
import subprocess
import threading
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from . import build, check

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "cad_out" / "blender"
UI = Path(__file__).resolve().parent / "webui"
VENDOR = ROOT / "snss_battery" / "vendor" / "three"
GEOMETRY_KEYS = {"Rod", "Lm8uu", "Grow"}  # 이 값은 부품 모양을 바꿈 → 메시를 다시 보냄
HW_SCENES = {"SC-3 솜사탕 조각가": "sc3", "SC-1 조각가": "sc1", "SC-2 빛 조각가": "sc2"}


class State:
    def __init__(self):
        self.design = json.loads((OUT / "design.json").read_text(encoding="utf-8"))
        self.proc = None
        self.lines: list[str] = []
        self.title = ""
        self.hw_log: list[str] = []
        self._parent = {}
        for c in bpy.data.collections:
            for ch in c.children:
                self._parent[ch.name] = c.name


S: State | None = None


def state() -> State:
    global S
    if S is None:
        S = State()
    return S


# ---------- 장면 → 브라우저 ----------
def _path(o) -> list[str]:
    c = o.users_collection[0] if o.users_collection else None
    out = []
    while c is not None:
        out.append(c.name)
        p = state()._parent.get(c.name)
        c = bpy.data.collections.get(p) if p else None
    return list(reversed(out))


def _color(ob) -> list[float]:
    for slot in ob.material_slots:
        if slot.material is not None:
            return list(slot.material.diffuse_color)
    return [0.8, 0.8, 0.8, 1.0]


def _key(inst) -> str:
    src = inst.parent.original.name if inst.is_instance and inst.parent else ""
    return f"{src}/{inst.object.original.name}/{','.join(str(i) for i in inst.persistent_id)}"


def _items(sc, dg):
    for inst in dg.object_instances:
        ob = inst.object
        if ob.type not in ("MESH", "META", "FONT"):
            continue
        if ob.original.display_type in ("WIRE", "BOUNDS"):
            continue  # CSG 재료
        yield inst, ob


def geometry(scene_name: str) -> bytes:
    """[JSON 길이 u32][JSON][0 채움 → 4 배수][float32 위치 · 법선 …] — 메시는 같은 원본끼리 함께 씀 (인스턴스)."""
    sc = bpy.data.scenes[scene_name]
    dg = build.dg_of(sc)
    meshes, items, bufs, off = {}, [], [], 0
    for inst, ob in _items(sc, dg):
        mk = f"{ob.original.name}|{ob.data.name if ob.data else ''}"
        if mk not in meshes:
            me = ob.to_mesh()
            me.calc_loop_triangles()
            nt = len(me.loop_triangles)
            if nt == 0:
                ob.to_mesh_clear()
                meshes[mk] = None
                continue
            loops = np.empty(nt * 3, np.int32)
            me.loop_triangles.foreach_get("loops", loops)
            vidx = np.empty(len(me.loops), np.int32)
            me.loops.foreach_get("vertex_index", vidx)
            co = np.empty(len(me.vertices) * 3, np.float32)
            me.vertices.foreach_get("co", co)
            pos = co.reshape(-1, 3)[vidx[loops]].astype(np.float32)
            try:
                cn = np.empty(len(me.loops) * 3, np.float32)
                me.corner_normals.foreach_get("vector", cn)
                nor = cn.reshape(-1, 3)[loops].astype(np.float32)
            except Exception:  # noqa: BLE001
                nor = np.zeros_like(pos)
            ob.to_mesh_clear()
            b = pos.tobytes() + nor.tobytes()
            meshes[mk] = {"id": len([m for m in meshes.values() if m]), "off": off, "n": nt * 3}
            bufs.append(b)
            off += len(b)
        m = meshes[mk]
        if m is None:
            continue
        orig = inst.parent.original if inst.is_instance and inst.parent else ob.original
        mw = inst.matrix_world
        items.append({"key": _key(inst), "mesh": m["id"], "name": orig.name, "part": ob.original.name if inst.is_instance else "",
                      "m": [mw[r][c] for c in range(4) for r in range(4)], "color": _color(ob), "path": _path(orig)})
    head = json.dumps({"scene": sc.name, "meshes": sorted((v for v in meshes.values() if v), key=lambda v: v["id"]), "items": items},
                      ensure_ascii=False).encode("utf-8")
    pad = (-(4 + len(head))) % 4
    return struct.pack("<I", len(head)) + head + b" " * pad + b"".join(bufs)


def frame(scene_name: str) -> dict:
    sc = bpy.data.scenes[scene_name]
    dg = build.dg_of(sc)
    return {"m": {_key(i): [i.matrix_world[r][c] for c in range(4) for r in range(4)] for i, _ in _items(sc, dg)}}


def info() -> dict:
    out = []
    for sc in bpy.data.scenes:
        d = bpy.data.objects.get(sc.get("snss_dims", "")) if sc.get("snss_dims") else None
        dims = []
        if d is not None:
            for k in d.keys():
                ui = d.id_properties_ui(k).as_dict()
                dims.append({"key": k, "value": float(d[k]), "min": ui.get("min", 0), "max": ui.get("max", 1), "desc": ui.get("description", "")})
        view = build.pad_view(sc) if sc.name in HW_SCENES else None
        out.append({"name": sc.name, "dims": dims, "hw": HW_SCENES.get(sc.name), "pad": list(view) if view else None})
    order = ["SC-3 솜사탕 조각가", "SC-1 조각가", "SC-2 빛 조각가", "존재 모양", "빚은 세포", "SC-1 부품", "SC-2 도구", "시험편", "양자 모듈", "병 결정"]
    out.sort(key=lambda s: order.index(s["name"]) if s["name"] in order else 99)
    c = state().design.get("console", {})
    return {"scenes": out, "keymap": c.get("keymap", []), "turn_limit": c.get("turntable", {}).get("limit_deg", 180),
            "blender": bpy.app.version_string, "file": bpy.data.filepath}


def set_dim(scene_name: str, key: str, value: float) -> dict:
    sc = bpy.data.scenes[scene_name]
    d = bpy.data.objects[sc["snss_dims"]]
    ui = d.id_properties_ui(key).as_dict()
    v = max(ui.get("min", -1e9), min(ui.get("max", 1e9), float(value)))
    d[key] = v
    d.update_tag()
    build.dg_of(sc)
    return {"value": v, "geometry": key in GEOMETRY_KEYS}


# ---------- 메타볼 (존재 모양) ----------
def meta_get(name: str) -> dict:
    o = bpy.data.objects[name]
    if o.type != "META":
        return {"elements": []}
    els = []
    for i, e in enumerate(o.data.elements):
        els.append({"i": i, "type": e.type, "co": list(e.co), "r": e.radius * build.K_META, "size_x": e.size_x,
                    "size_y": e.size_y, "size_z": e.size_z})
    return {"name": o.name, "shape": o.get("SNSSShape"), "elements": els}


def meta_set(name: str, i: int, co=None, r=None, size=None, add=None, remove=False) -> dict:
    o = bpy.data.objects[name]
    mb = o.data
    if add:
        e = mb.elements.new(type=add)
        e.co, e.radius, e.stiffness = (0, 0, 40), 4.0 / build.K_META, build.STIFF
        if add == "CAPSULE":
            e.size_x = 6.0
    elif remove:
        mb.elements.remove(mb.elements[i])
    else:
        e = mb.elements[i]
        if co is not None:
            e.co = co
        if r is not None:
            e.radius = max(0.2, float(r)) / build.K_META
        if size is not None:
            e.size_x, e.size_y, e.size_z = size
    sc = bpy.data.scenes["존재 모양"]
    build.bake_shape(o, build.dg_of(sc))  # 조립 속 존재 메시도 함께
    return meta_get(name)


# ---------- 점검 · 조각가 · 렌더 · 저장 ----------
def run_check(scene_name: str) -> dict:
    key = HW_SCENES.get(scene_name)
    if key is None or key == "sc3":
        return {"error": "공간 점검은 SC-1 · SC-2 장면에서 (SC-3 은 `candy new` 의 점검)"}
    sc = bpy.data.scenes[scene_name]
    D = state().design
    return {"clearance": check.clearance(sc, D[key]["layout"]), "motion": check.bed_motion(sc, D[key]["build"][2])}


def send(machine: str, obj_name: str | None) -> dict:
    st = state()
    if st.proc is not None and st.proc.poll() is None:
        return {"error": "이전 작업이 아직 돌고 있음"}
    sc = bpy.data.scenes["존재 모양"]
    o = bpy.data.objects.get(obj_name) if obj_name else None
    if o is None or not o.get("SNSSShape"):
        o = next(x for x in sc.objects if x.get("SNSSShape") == "being")
    dg = build.dg_of(sc)
    if o.type == "META":
        build.bake_shape(o, dg)
    bm = check.shape_mesh(o, dg)
    name = f"web_{o['SNSSShape']}"
    f = OUT / "shapes" / f"{name}.stl"
    check.write_stl(f, bm)
    bm.free()
    args = ["-m", "snss_battery", "sculpt", "new", name, "--shape", str(f)] if machine == "sc1" else \
        ["-m", "snss_battery", "light", str(f), "--name", name]
    h = float(o.get("TargetHeight", 0) or 0)
    if h > 0:
        args += ["--height", f"{h:g}"]
    st.lines, st.title = [], f"{'SC-1' if machine == 'sc1' else 'SC-2'} 로 빚기 ({o.name})"
    st.machine = machine
    st.proc = subprocess.Popen(["python3", *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def read(p=st.proc):
        for line in p.stdout:
            st.lines.append(line.rstrip())

    threading.Thread(target=read, daemon=True).start()
    return {"started": st.title, "stl": str(f.relative_to(ROOT))}


def log() -> dict:
    st = state()
    running = st.proc is not None and st.proc.poll() is None
    done = st.proc is not None and not running
    if done and not getattr(st, "loaded", False) and st.proc.returncode == 0:
        jobs = ROOT / "sculpt_out" / ("jobs" if st.machine == "sc1" else "light_jobs")
        last = sorted((p for p in jobs.glob("*") if p.is_dir()), key=lambda p: p.stat().st_mtime)
        if last:
            build.load_cells(last[-1])
        st.loaded = True
    if running:
        st.loaded = False
    return {"title": st.title, "running": running, "code": None if st.proc is None or running else st.proc.returncode,
            "lines": st.lines[-400:]}


def render(scene_name: str, eye, target, fov_deg: float, w: int, h: int, engine: str = "BLENDER_EEVEE") -> bytes:
    sc = bpy.data.scenes[scene_name]
    cam_data = bpy.data.cameras.get("웹 보기 카메라") or bpy.data.cameras.new("웹 보기 카메라")
    cam = bpy.data.objects.get("웹 보기 카메라") or bpy.data.objects.new("웹 보기 카메라", cam_data)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cam.location = Vector(eye)
    cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()
    cam_data.sensor_fit, cam_data.angle_y = "VERTICAL", math.radians(fov_deg)
    cam_data.clip_start, cam_data.clip_end = 0.5, 20000
    old = sc.camera, sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage
    sc.camera, sc.render.engine = cam, engine
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = int(w), int(h), 100
    f = OUT / "web_render.png"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(f)
    try:
        bpy.ops.render.render(write_still=True, scene=sc.name)
    finally:
        sc.camera, sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = old
        sc.collection.objects.unlink(cam)
    return f.read_bytes()


def save() -> dict:
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_mainfile(filepath=bpy.data.filepath or str(OUT / "SNSS_Design.blend"), compress=True)
    return {"saved": bpy.data.filepath}


# ---------- HW 뷰포트: 같은 키 · 마우스 → 수조 콘솔 기계 동작 ----------
def hw(scene_name: str, action: str, **kw) -> dict:
    """console.py HW_KEYMAP 과 같은 규칙. 설계 값(TurnTable · BedDrop · View*)을 바꾸고 G-code 를 기록."""
    key = HW_SCENES.get(scene_name)
    if key is None:
        return {"error": "HW 뷰포트는 SC-1 · SC-2 장면에서"}
    sc = bpy.data.scenes[scene_name]
    d = bpy.data.objects[sc["snss_dims"]]
    lim = state().design.get("console", {}).get("turntable", {}).get("limit_deg", 180)
    bz = state().design.get(key, {}).get("build", [0, 0, 90])[2]
    g = []

    def put(k, v):
        if k in d.keys():
            ui = d.id_properties_ui(k).as_dict()
            d[k] = max(ui.get("min", -1e9), min(ui.get("max", 1e9), float(v)))

    if key == "sc3" and action in ("bed", "zoom"):  # SC-3: 받침 대신 자람 반지름
        g_ = max(0.0, min(float(d.id_properties_ui("Grow").as_dict().get("max", 40)), float(d["Grow"]) + float(kw.get("delta", 0))))
        put("Grow", g_)
        g.append(f"; 시뮬레이션: 영점에서 r {g_:.1f} mm 까지 (SD 단계 표시점으로 가기)")
        d.update_tag()
        build.dg_of(sc)
        state().hw_log = (state().hw_log + g)[-60:]
        return {"gcode": g, "log": state().hw_log, "dims": {k: float(d[k]) for k in d.keys()}, "geometry": True}
    if action == "turn":
        a = max(-lim, min(lim, float(d["TurnTable"]) + float(kw.get("delta", 0)))) if "delta" in kw else max(-lim, min(lim, float(kw["deg"])))
        put("TurnTable", a)
        g.append(f"TURN A={a:.1f}")
    elif action == "bed":
        z = max(0.0, min(bz, float(d["BedDrop"]) + float(kw.get("delta", 0))))
        put("BedDrop", z)
        g.append(f"G1 Z{z:.2f} F180  ; 받침 내림 {z:.1f} mm")
    elif action == "look":
        if key == "sc2":
            put("ViewX", kw["x"])
            put("ViewY", kw["y"])
            put("ViewR", kw.get("r", 6.0))
            g.append(f"VIEW_LIGHT X={float(kw['x']):.1f} Y={float(kw['y']):.1f} R={float(d['ViewR']):.1f}")
        else:
            g.append(f"; SC-1 은 보기 빛 없음 — 화면에서만 고름 ({float(kw['x']):.1f}, {float(kw['y']):.1f})")
    elif action == "zoom":
        if key == "sc2":
            r = max(0.0, min(55.0, float(d["ViewR"]) + float(kw.get("delta", 0))))
            put("ViewR", r)
            g.append(f"VIEW_LIGHT R={r:.1f}")
    elif action == "view":
        v = kw.get("view")
        put("TurnTable", {"front": 0, "side": 90, "top": float(d["TurnTable"])}.get(v, 0))
        if v == "top":
            put("BedDrop", 0.0)
        g.append(f"TURN A={float(d['TurnTable']):.1f}" + ("  ·  G1 Z0 F180  ; 수면 바로 아래" if v == "top" else ""))
    elif action == "home":
        put("TurnTable", 0)
        put("BedDrop", 72.0)
        put("ViewR", 0)
        g += ["VIEW_LIGHT R=0", "TURN A=0", "G1 Z72.00 F180"]
    d.update_tag()
    build.dg_of(sc)
    state().hw_log = (state().hw_log + g)[-60:]
    return {"gcode": g, "log": state().hw_log, "dims": {k: float(d[k]) for k in d.keys()}}


# ---------- SC-3 과정 (SD 에 구운 것) — 단계로 가기 · 반복 · 건너뛰기 ----------
def process_get() -> dict:
    root = ROOT / state().design.get("candy", {}).get("sd", "cad_out/sd/being") / "SNSS"
    if not (root / "process.json").exists():
        return {"error": "SD 가 아직 없음 — python3 -m snss_battery candy new being"}
    p = json.loads((root / "process.json").read_text(encoding="utf-8"))
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    edits = json.loads((root / "edits.json").read_text(encoding="utf-8"))
    return {"name": p["name"], "steps": p["steps"], "total_s": p["total_s"], "burned": man["burned"], "edits": edits, "sd": str(root.relative_to(ROOT))}


def process_set(op: str, step: int, to: float | None = None) -> dict:
    """데스크톱 키보드와 같은 길: SD 의 edits.json 에 적음 → 지금 컴퓨터가 `candy reburn` 으로 다시 굽기."""
    import time as _t

    root = ROOT / state().design.get("candy", {}).get("sd", "cad_out/sd/being") / "SNSS"
    f = root / "edits.json"
    e = json.loads(f.read_text(encoding="utf-8"))
    e.append({"key": op, "step": int(step), **({"to": float(to)} if to is not None else {}), "at": _t.strftime("%H:%M:%S"), "from": "브라우저"})
    f.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    return process_get()


def static(path: str):
    """→ (바이트, 종류) — 웹 화면 파일 · three.js."""
    if path in ("/", "/index.html"):
        return (UI / "index.html").read_bytes(), "text/html; charset=utf-8"
    if path.startswith("/ui/"):
        f = (UI / path[4:]).resolve()
        if UI.resolve() in f.parents and f.exists():
            return f.read_bytes(), "text/javascript; charset=utf-8" if f.suffix == ".js" else "text/css; charset=utf-8"
    if path.startswith("/vendor/"):
        f = (VENDOR / path[8:]).resolve()
        if VENDOR.resolve() in f.parents and f.exists():
            return f.read_bytes(), "text/javascript; charset=utf-8"
    if path.startswith("/preview/"):
        f = (OUT / "preview" / path[9:]).resolve()
        if (OUT / "preview").resolve() in f.parents and f.exists():
            return f.read_bytes(), "image/png"
    return None, None
