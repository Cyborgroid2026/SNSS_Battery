"""SNSS 설계 — Blender 애드온 (3D 뷰 사이드바 N → 'SNSS' 탭).

- 지금 장면의 설계 값 (치수 빈 개체의 속성: PenX · BedDrop · Rod · Lambda …) 을 바로 고침 — 드라이버로 모양 · 위치가 따라옴
- 고른 모양(존재 모양 장면의 메타볼 · 메시)을 '조각가 SC-1 로 빚기' · '빛 조각가 SC-2 로 빚기' — STL 로 내보내고
  python3 -m snss_battery sculpt new … / light … 을 돌린 뒤, 빚은 양자 인공세포를 '빚은 세포' 장면으로 불러옴
- 공간 · 움직임 점검 (SC-1 · SC-2 장면) · 메타볼 요소 더하기 · 프로젝트 값으로 다시 짓기
머리 없는 짓기(blender/build_design.py)도 이 패키지의 build · check 를 씀.
"""

bl_info = {
    "name": "SNSS 설계",
    "author": "SNSS",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D 뷰 › 사이드바 › SNSS",
    "description": "조각가 SC-1 · 빛 조각가 SC-2 · 존재 · 시험편 · 양자 모듈 · 병 결정 — 설계를 고쳐 조각가로 보냄",
    "category": "Object",
}

import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
from pathlib import Path  # noqa: E402

import bpy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent  # 저장소 (blender/snss_design → 위로 둘)
OUT = ROOT / "cad_out" / "blender"
PY = os.environ.get("SNSS_PYTHON", "python3")
_job = {"proc": None, "lines": [], "title": "", "after": None}


def _dims(sc):
    name = sc.get("snss_dims")
    return bpy.data.objects.get(name) if name else None


def _shape_obj(context):
    o = context.active_object
    if o is not None and o.type in ("META", "MESH"):
        return o
    sc = bpy.data.scenes.get("존재 모양")
    return next((x for x in sc.objects if x.get("SNSSShape") == "being"), None) if sc else None


def _export(context, o):
    from . import check
    from .build import dg_of

    key = o.get("SNSSShape") or "".join(ch for ch in o.name if ch.isalnum()) or "shape"
    name = f"bl_{key}"
    bm = check.shape_mesh(o, dg_of(context.scene))
    f = OUT / "shapes" / f"{name}.stl"
    check.write_stl(f, bm)
    bm.free()
    return name, f


def _run(args, title, after=None):
    """저장소에서 snss_battery 명령을 따로 돌림 — Blender 가 멈추지 않게 실, 결과는 타이머가 읽음."""
    if _job["proc"] is not None:
        return False
    _job.update(lines=[], title=title, after=after)
    p = subprocess.Popen([PY, *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    _job["proc"] = p

    def read():
        for line in p.stdout:
            _job["lines"].append(line.rstrip())
            print(line.rstrip())

    threading.Thread(target=read, daemon=True).start()
    bpy.app.timers.register(_poll, first_interval=1.0)
    print(f"── {title}: {PY} {' '.join(args)}")
    return True


def _poll():
    p = _job["proc"]
    if p is None:
        return None
    if p.poll() is None:
        return 1.0
    _job["proc"] = None
    ok = p.returncode == 0
    print(f"── {_job['title']}: {'끝' if ok else f'실패 (코드 {p.returncode})'}")
    if ok and _job["after"]:
        try:
            _job["after"]()
        except Exception as e:  # noqa: BLE001
            print("불러오기 실패:", e)
    for a in bpy.context.window_manager.windows:
        for ar in a.screen.areas:
            ar.tag_redraw()
    return None


def _newest(folder: Path):
    js = sorted((p for p in folder.glob("*") if p.is_dir()), key=lambda p: p.stat().st_mtime) if folder.exists() else []
    return js[-1] if js else None


def _load_cells(kind):
    from .build import load_cells

    job = _newest(ROOT / "sculpt_out" / ("jobs" if kind == "sc1" else "light_jobs"))
    if job is not None and load_cells(job) is not None:
        print(f"빚은 세포를 '빚은 세포' 장면으로: {job.name}")


class SNSS_OT_send(bpy.types.Operator):
    bl_idname = "snss.send"
    bl_label = "조각가로 빚기"
    bl_description = "고른 모양을 STL 로 내보내고 조각가 계산(양자 인공세포 · G-code · 생명 신호)을 돌림 — 끝나면 '빚은 세포' 장면"
    machine: bpy.props.EnumProperty(items=[("sc1", "SC-1", "펜 조각가"), ("sc2", "SC-2", "빛 조각가")])

    def execute(self, context):
        o = _shape_obj(context)
        if o is None:
            self.report({"WARNING"}, "모양(메타볼 · 메시)을 고르세요")
            return {"CANCELLED"}
        name, f = _export(context, o)
        h = float(o.get("TargetHeight", 0) or 0)
        if self.machine == "sc1":
            args = ["-m", "snss_battery", "sculpt", "new", name, "--shape", str(f)]
        else:
            args = ["-m", "snss_battery", "light", str(f), "--name", name]
        if h > 0:
            args += ["--height", f"{h:g}"]
        if not _run(args, f"{'SC-1' if self.machine == 'sc1' else 'SC-2'} 로 빚기 ({o.name})", lambda: _load_cells(self.machine)):
            self.report({"WARNING"}, "이전 작업이 아직 돌고 있습니다")
            return {"CANCELLED"}
        self.report({"INFO"}, f"{f.name} → 조각가 계산 시작 (콘솔 · 패널에 진행)")
        return {"FINISHED"}


class SNSS_OT_check(bpy.types.Operator):
    bl_idname = "snss.check"
    bl_label = "공간 · 움직임 점검"
    bl_description = "비어 있어야 할 곳 ↔ 고정 부품 거리, 받침을 맨 아래까지 내렸을 때 부딪힘"

    def execute(self, context):
        from . import check

        sc = context.scene
        D = json.loads((OUT / "design.json").read_text(encoding="utf-8"))
        key = "sc1" if sc.name.startswith("SC-1 조각가") else "sc2" if sc.name.startswith("SC-2 빛") else None
        if key is None:
            self.report({"WARNING"}, "SC-1 조각가 · SC-2 빛 조각가 장면에서 쓰세요")
            return {"CANCELLED"}
        cl = check.clearance(sc, D[key]["layout"])
        mo = check.bed_motion(sc, D[key]["build"][2])
        bad = [x for x in cl if x["gap"] < 2]
        for x in cl:
            if x["gap"] < 10:
                print(f"  {x['zone']} ↔ {x['part']}: {x['gap']:.1f} mm")
        for m in mo:
            print(f"  움직임: {m['bed']} ↔ {m['part']} {m['gap']} mm (받침 {m['drop']:g} mm 내림)")
        msg = f"공간 점검 {'통과' if not bad else f'문제 {len(bad)}'} · 움직임 점검 {'통과' if not mo else f'부딪힘 {len(mo)}'}"
        self.report({"INFO"} if not bad and not mo else {"WARNING"}, msg)
        return {"FINISHED"}


class SNSS_OT_add_element(bpy.types.Operator):
    bl_idname = "snss.add_element"
    bl_label = "메타볼 요소 더하기"
    bl_description = "고른 존재 모양(메타볼)에 요소를 더함 — 편집 모드에서 옮기고 키움"
    kind: bpy.props.EnumProperty(items=[("BALL", "구", ""), ("CAPSULE", "캡슐", ""), ("ELLIPSOID", "타원체", "")])

    def execute(self, context):
        from .build import K_META, STIFF

        o = context.active_object
        if o is None or o.type != "META":
            self.report({"WARNING"}, "존재 모양 장면의 메타볼을 고르세요")
            return {"CANCELLED"}
        el = o.data.elements.new(type=self.kind)
        el.co, el.radius, el.stiffness = (0, 0, 40), 4.0 / K_META, STIFF
        if self.kind == "CAPSULE":
            el.size_x = 6.0
        self.report({"INFO"}, f"{o.name} 에 {self.kind} 더함 (z 40 mm, 반지름 4 mm) — Tab 으로 편집 모드")
        return {"FINISHED"}


class SNSS_OT_rebuild(bpy.types.Operator):
    bl_idname = "snss.rebuild"
    bl_label = "프로젝트 값으로 다시 짓기"
    bl_description = "snss_battery 의 치수로 SNSS_Design.blend 를 새로 짓고 다시 엶 (이 파일에서 고친 것은 사라짐)"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        def reopen():
            bpy.ops.wm.open_mainfile(filepath=str(OUT / "SNSS_Design.blend"))

        _run(["-m", "snss_battery", "blender-design", "--no-render"], "다시 짓기", reopen)
        return {"FINISHED"}


class SNSS_OT_cells(bpy.types.Operator):
    bl_idname = "snss.cells"
    bl_label = "마지막 빚은 세포 불러오기"
    machine: bpy.props.EnumProperty(items=[("sc1", "SC-1", ""), ("sc2", "SC-2", "")])

    def execute(self, context):
        _load_cells(self.machine)
        return {"FINISHED"}


class SNSS_PT_panel(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category, bl_label = "VIEW_3D", "UI", "SNSS", "SNSS 설계"

    def draw(self, context):
        lay = self.layout
        sc = context.scene
        d = _dims(sc)
        if d is not None:
            box = lay.box()
            box.label(text=f"설계 값 — {sc.name}")
            for k in d.keys():
                if not k.startswith("_"):
                    box.prop(d, f'["{k}"]', text=k)
        col = lay.column(align=True)
        col.label(text="존재 모양 → 조각가")
        o = _shape_obj(context)
        col.label(text=f"모양: {o.name if o else '없음'}")
        if o is not None and "TargetHeight" in o:
            col.prop(o, '["TargetHeight"]', text="완성 높이 (0 = 그대로)")
        row = col.row(align=True)
        row.operator("snss.send", text="SC-1 로 빚기").machine = "sc1"
        row.operator("snss.send", text="SC-2 로 빚기").machine = "sc2"
        if context.active_object is not None and context.active_object.type == "META":
            row = col.row(align=True)
            for k, t in (("BALL", "구"), ("CAPSULE", "캡슐"), ("ELLIPSOID", "타원체")):
                row.operator("snss.add_element", text=f"+ {t}").kind = k
        lay.operator("snss.check", icon="CHECKMARK")
        row = lay.row(align=True)
        row.operator("snss.cells", text="세포 SC-1").machine = "sc1"
        row.operator("snss.cells", text="세포 SC-2").machine = "sc2"
        lay.operator("snss.rebuild", icon="FILE_REFRESH")
        if _job["proc"] is not None or _job["lines"]:
            b = lay.box()
            b.label(text=f"{_job['title']} {'— 도는 중' if _job['proc'] is not None else ''}")
            for line in _job["lines"][-8:]:
                b.label(text=line[:80])


CLASSES = (SNSS_OT_send, SNSS_OT_check, SNSS_OT_add_element, SNSS_OT_rebuild, SNSS_OT_cells, SNSS_PT_panel)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
