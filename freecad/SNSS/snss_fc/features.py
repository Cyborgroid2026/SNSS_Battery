"""매개변수 개체 (FeaturePython) — FreeCAD 속성 창에서 치수를 바꾸면 모양이 다시 계산된다.

- PrintedPart: SC-1 출력 부품 (printed.PARTS) — 설계 치수 속성 + 수량 · 재료 · 쓰임
- Capsule: 존재 모양의 기본형 (두 끝점 A · B 와 반지름) — 팔 · 다리 · 줄기
- Ellipsoid: 반지름 Rx · Ry · Rz 타원체 — 몸통 · 발 · 봉오리 (Part::Ellipsoid 은 축 하나가 늘 Z 라 따로 둠)
파일을 열 때 FreeCAD 가 이 모듈을 import 하므로 애드온(Mod/SNSS)이 설치되어 있어야 다시 계산된다 (모양 자체는 파일에 저장됨).
"""

from __future__ import annotations

import FreeCAD as App

from . import prim, printed


class _Base:
    def __init__(self, obj):
        obj.Proxy = self

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def onDocumentRestored(self, obj):
        obj.Proxy = self


class PrintedPart(_Base):
    def __init__(self, obj, key: str, info: dict | None = None):
        super().__init__(obj)
        info = info or {}
        obj.addProperty("App::PropertyString", "Key", "SNSS", "부품 열쇠 (snss_battery/parts.py)").Key = key
        obj.setEditorMode("Key", 1)
        obj.addProperty("App::PropertyInteger", "Qty", "SNSS", "수량 (기계 하나)").Qty = int(info.get("qty", 1))
        obj.addProperty("App::PropertyString", "Material", "SNSS", "재료").Material = info.get("material", "PETG")
        obj.addProperty("App::PropertyString", "Role", "SNSS", "쓰임").Role = info.get("role", "")
        obj.addProperty("App::PropertyFloat", "SdfVolume", "SNSS", "SDF 표면망 부피 cm³ (parts.py — 대조용)").SdfVolume = \
            float(info.get("sdf_volume_cm3") or 0.0)
        obj.setEditorMode("SdfVolume", 1)
        for name, (default, doc) in printed.PARTS[key][1].items():
            obj.addProperty("App::PropertyFloat", name, "설계 치수", doc)
            setattr(obj, name, float(default))

    def execute(self, obj):
        P = {name: getattr(obj, name) for name in printed.PARTS[obj.Key][1]}
        obj.Shape = printed.build(obj.Key, P)


class Capsule(_Base):
    def __init__(self, obj, a=(0, 0, 0), b=(0, 0, 10), r=2.0):
        super().__init__(obj)
        obj.addProperty("App::PropertyVector", "A", "캡슐", "한 끝 (mm)").A = App.Vector(*a)
        obj.addProperty("App::PropertyVector", "B", "캡슐", "다른 끝 (mm)").B = App.Vector(*b)
        obj.addProperty("App::PropertyLength", "Radius", "캡슐", "반지름").Radius = r

    def execute(self, obj):
        a, b = obj.A, obj.B
        if (b - a).Length < 1e-6:
            obj.Shape = prim.sphere(a, obj.Radius.Value)
        else:
            obj.Shape = prim.capsule(tuple(a), tuple(b), obj.Radius.Value)


class Ellipsoid(_Base):
    def __init__(self, obj, c=(0, 0, 0), r=(5, 5, 5)):
        super().__init__(obj)
        obj.addProperty("App::PropertyVector", "Center", "타원체", "가운데 (mm)").Center = App.Vector(*c)
        for k, v in zip(("Rx", "Ry", "Rz"), r):
            obj.addProperty("App::PropertyLength", k, "타원체", f"{k[1]} 반지름")
            setattr(obj, k, v)

    def execute(self, obj):
        obj.Shape = prim.ellipsoid(tuple(obj.Center), (obj.Rx.Value, obj.Ry.Value, obj.Rz.Value))


class ViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def dumps(self):
        return None

    def loads(self, state):
        return None


def make_part(doc, key, info=None, name=None):
    obj = doc.addObject("Part::FeaturePython", name or key)
    PrintedPart(obj, key, info)
    if App.GuiUp:
        ViewProvider(obj.ViewObject)
    return obj


def make_capsule(doc, name, a, b, r):
    obj = doc.addObject("Part::FeaturePython", "Capsule")
    obj.Label = name
    Capsule(obj, a, b, r)
    if App.GuiUp:
        ViewProvider(obj.ViewObject)
    return obj


def make_ellipsoid(doc, name, c, r):
    obj = doc.addObject("Part::FeaturePython", "Ellipsoid")
    obj.Label = name
    Ellipsoid(obj, c, r)
    if App.GuiUp:
        ViewProvider(obj.ViewObject)
    return obj
