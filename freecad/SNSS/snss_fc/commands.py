"""SNSS 설계 워크벤치 명령 — FreeCAD 창 안에서 설계를 고치고, 그 모양을 조각가로 보낸다.

- 다시 짓기: snss_battery 의 값(design.json)을 새로 받아 모든 작품 문서를 다시 지음
- SC-1 로 빚기 · SC-2 로 빚기: 고른 모양(또는 Being_Shapes 의 '모양 — being')을 STL 로 내보내고
  `python3 -m snss_battery sculpt new 이름 --shape …stl` · `light …stl --name 이름` 을 돌림 (보고서 창에 결과)
- 점검: 지금 문서(SC1_Sculptor · SC2_LightSculptor)의 공간 · 움직임 점검
- 캡슐 · 타원체 더하기: 고른 모양의 합(MultiFuse)에 새 기본형을 넣음
"""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui

ADDON = Path(__file__).resolve().parent.parent
ROOT = ADDON.parent.parent  # 저장소 (freecad/SNSS → 위로 둘)
OUT = ROOT / "cad_out" / "freecad"
ICON = str(ADDON / "icons" / "snss.svg")
PY = os.environ.get("SNSS_PYTHON", "python3")
_procs = []


def _say(msg):
    App.Console.PrintMessage(msg.rstrip() + "\n")


def _run(args, title, done=None):
    """저장소에서 snss_battery 명령을 돌리고 출력은 보고서 창으로 (FreeCAD 가 멈추지 않게 QProcess)."""
    from PySide import QtCore

    p = QtCore.QProcess()
    p.setWorkingDirectory(str(ROOT))
    p.setProcessChannelMode(QtCore.QProcess.MergedChannels)
    p.readyReadStandardOutput.connect(lambda: _say(bytes(p.readAllStandardOutput()).decode("utf-8", "replace")))

    def fin(code, _status=None):
        _say(f"── {title}: {'끝' if code == 0 else f'실패 (코드 {code})'}")
        if done and code == 0:
            done()
        _procs.remove(p)

    p.finished.connect(fin)
    _say(f"── {title}: {PY} {' '.join(shlex.quote(a) for a in args)}")
    _procs.append(p)
    p.start(PY, args)


def _shape_obj():
    sel = Gui.Selection.getSelection()
    for o in sel:
        while o is not None and not getattr(o, "SNSSShape", None):
            o = next((p for p in o.InList if p.TypeId == "Part::Cut" or getattr(p, "SNSSShape", None)), None)
        if o is not None:
            return o
    if sel and hasattr(sel[0], "Shape") and sel[0].Shape.Solids:
        return sel[0]
    doc = App.listDocuments().get("Being_Shapes")
    if doc:
        return next((o for o in doc.Objects if getattr(o, "SNSSShape", "") == "being"), None)
    return None


def _export(o) -> tuple[str, Path]:
    import MeshPart

    name = getattr(o, "SNSSShape", "") or "".join(c for c in o.Name if c.isalnum()) or "shape"
    name = f"fc_{name}"
    (OUT / "shapes").mkdir(parents=True, exist_ok=True)
    f = OUT / "shapes" / f"{name}.stl"
    MeshPart.meshFromShape(Shape=o.Shape, LinearDeflection=0.05, AngularDeflection=0.25, Relative=False).write(str(f))
    return name, f


class _Cmd:
    menu = tip = ""

    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": self.menu, "ToolTip": self.tip}

    def IsActive(self):
        return True


class Rebuild(_Cmd):
    menu, tip = "프로젝트 값으로 모두 다시 짓기", "snss_battery 의 치수(design.json)를 새로 받아 9개 작품 문서를 다시 지음"

    def Activated(self):
        def build():
            from . import runner

            for d in list(App.listDocuments().values()):
                if d.FileName and Path(d.FileName).parent == OUT:
                    App.closeDocument(d.Name)
            D = json.loads((OUT / "design.json").read_text(encoding="utf-8"))
            V = runner.run(D, OUT, log=_say)
            bad = [e for d in V["docs"] for e in d["errors"] + d["invalid"]]
            _say(f"문서 {len(V['docs'])}개 · 오류 {len(bad)}" + (f": {bad[:5]}" if bad else ""))
            Gui.SendMsgToActiveView("ViewFit")

        _run(["-c", "from snss_battery import fcparams; print(fcparams.write_design())"], "치수 받기 (design.json)", build)


class SendSC1(_Cmd):
    menu, tip = "→ 조각가 SC-1 로 빚기", "고른 모양을 STL 로 내보내고 sculpt new 로 양자 인공세포 존재를 빚음 (G-code · 생명 신호 · 메시)"

    def Activated(self):
        o = _shape_obj()
        if o is None:
            _say("모양을 고르세요 (Being_Shapes 의 '모양 — …' 또는 고체)")
            return
        name, f = _export(o)
        h = getattr(o, "TargetHeight", None)
        args = ["-m", "snss_battery", "sculpt", "new", name, "--shape", str(f)]
        if h is not None and h.Value > 0:
            args += ["--height", f"{h.Value:g}"]
        _run(args, f"SC-1 로 빚기 ({o.Label})")


class SendSC2(_Cmd):
    menu, tip = "→ 빛 조각가 SC-2 로 빚기", "고른 모양을 STL 로 내보내고 light 로 층별 빛 그림 · 생명 신호를 만듦"

    def Activated(self):
        o = _shape_obj()
        if o is None:
            _say("모양을 고르세요")
            return
        name, f = _export(o)
        args = ["-m", "snss_battery", "light", str(f), "--name", name]
        h = getattr(o, "TargetHeight", None)
        if h is not None and h.Value > 0:
            args += ["--height", f"{h.Value:g}"]
        _run(args, f"SC-2 로 빚기 ({o.Label})")


class Check(_Cmd):
    menu, tip = "공간 · 움직임 점검", "비어 있어야 할 곳 ↔ 고정 부품의 실제 거리, 받침을 맨 아래까지 내렸을 때 부딪힘"

    def Activated(self):
        from . import check

        doc = App.ActiveDocument
        if doc is None or doc.getObject("Params") is None:
            _say("SC1_Sculptor 또는 SC2_LightSculptor 문서에서 쓰세요")
            return
        D = json.loads((OUT / "design.json").read_text(encoding="utf-8"))
        bz = D["sc1" if doc.Name.startswith("SC1") else "sc2"]["build"][2]
        cl = check.clearance(doc)
        for x in cl:
            if x["gap"] < 10:
                _say(f"  {x['zone']} ↔ {x['part']}: {x['gap']:.1f} mm{'  ← 2 mm 미만' if x['gap'] < 2 else ''}")
        mo = check.bed_motion(doc, bz)
        _say("공간 점검: " + ("통과" if all(x["gap"] >= 2 for x in cl) else "문제 있음") +
             " · 움직임 점검 (받침 " + f"{bz:g} mm 내림): " + ("통과" if not mo else "; ".join(f"{m['bed']} ↔ {m['part']} {m['gap']} mm" for m in mo)))


class _AddPrim(_Cmd):
    kind = ""

    def Activated(self):
        from . import features

        o = _shape_obj()
        doc = App.ActiveDocument
        fu = getattr(o, "Base", None) if o is not None else None
        if fu is None or fu.TypeId != "Part::MultiFuse":
            _say("'모양 — …' 을 고르세요 (기본형이 둘 이상인 모양)")
            return
        if self.kind == "capsule":
            p = features.make_capsule(doc, "새 캡슐", (0, 0, 40), (0, 12, 40), 3.0)
        else:
            p = features.make_ellipsoid(doc, "새 타원체", (0, 0, 40), (6, 6, 6))
        from .style import paint

        paint(p, "being")
        grp = next((g for g in fu.Shapes[0].InList if g.TypeId == "App::DocumentObjectGroup"), None)
        if grp is not None:
            grp.addObject(p)
        fu.Shapes = fu.Shapes + [p]
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(p)
        _say(f"{p.Label} 을(를) {o.Label} 에 더함 — 속성 창에서 위치 · 반지름을 고치세요")


class AddCapsule(_AddPrim):
    menu, tip, kind = "캡슐 더하기 (팔 · 다리 · 줄기)", "고른 모양에 캡슐 기본형을 더함", "capsule"


class AddEllipsoid(_AddPrim):
    menu, tip, kind = "타원체 더하기 (몸통 · 머리 · 발)", "고른 모양에 타원체 기본형을 더함", "ellipsoid"


class OpenAll(_Cmd):
    menu, tip = "모든 작품 문서 열기", "cad_out/freecad 의 FCStd 9개"

    def Activated(self):
        for f in sorted(OUT.glob("*.FCStd")):
            if not any(d.FileName == str(f) for d in App.listDocuments().values()):
                App.openDocument(str(f))


COMMANDS = {"SNSS_OpenAll": OpenAll(), "SNSS_Rebuild": Rebuild(), "SNSS_SendSC1": SendSC1(), "SNSS_SendSC2": SendSC2(),
            "SNSS_Check": Check(), "SNSS_AddCapsule": AddCapsule(), "SNSS_AddEllipsoid": AddEllipsoid()}


def register():
    for k, c in COMMANDS.items():
        Gui.addCommand(k, c)
    return list(COMMANDS)
