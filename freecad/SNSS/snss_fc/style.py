"""색 · 투명도 — GUI 가 있을 때만 (머리 없이 지으면 회색으로 저장됨). 재질 이름은 Blender 장면과 같게."""

from __future__ import annotations

import FreeCAD as App

COLORS = {
    "petg": ((0.86, 0.89, 0.92), 0), "petg_dark": ((0.18, 0.19, 0.21), 0), "cf": ((0.12, 0.12, 0.13), 0),
    "nylon": ((0.95, 0.92, 0.82), 0), "graphite": ((0.27, 0.27, 0.29), 0), "cable": ((0.08, 0.08, 0.09), 0),
    "glass": ((0.70, 0.86, 0.90), 85), "bath": ((0.55, 0.75, 0.95), 90), "zone": ((1.0, 0.62, 0.2), 88),
    "sweep": ((0.6, 0.6, 1.0), 92), "pos": ((0.90, 0.32, 0.26), 0), "neg": ((0.26, 0.46, 0.90), 0),
    "mem": ((0.88, 0.86, 0.78), 55), "ink": ((0.36, 0.30, 0.24), 45), "dark": ((0.16, 0.16, 0.19), 0),
    "beam": ((0.55, 0.30, 1.0), 82), "lens": ((0.50, 0.30, 1.0), 20), "wood": ((0.70, 0.55, 0.38), 0),
    "xps": ((0.55, 0.75, 0.95), 0), "silicone": ((0.90, 0.90, 0.93), 0), "pc": ((0.15, 0.15, 0.17), 0),
    "pipette": ((0.85, 0.93, 1.0), 55), "peek": ((0.82, 0.70, 0.50), 0), "being": ((0.95, 0.55, 0.30), 0),
    "silica": ((0.80, 0.90, 0.98), 40), "sio2": ((0.70, 0.85, 1.0), 30), "sin": ((0.95, 0.80, 0.45), 30),
    "active": ((0.95, 0.25, 0.20), 0), "bottle": ((0.85, 0.92, 0.95), 75), "crystal": ((0.35, 0.55, 0.85), 15),
    "red": ((0.85, 0.15, 0.12), 0), "black": ((0.08, 0.08, 0.08), 0),
}


def paint(obj, key: str, hidden: bool = False):
    """색 이름을 개체 속성 SNSSColor 로 적어 둠 (머리 없이 지어도 남음) — GUI 가 있으면 바로, 없으면 문서를 열 때 워크벤치가 칠함."""
    if obj is None:
        return obj
    if "SNSSColor" not in obj.PropertiesList:
        obj.addProperty("App::PropertyString", "SNSSColor", "SNSS", "색 이름 (style.COLORS) — 열 때 칠함")
        obj.addProperty("App::PropertyBool", "SNSSHidden", "SNSS", "처음에 숨김")
        obj.setEditorMode("SNSSColor", 2)
        obj.setEditorMode("SNSSHidden", 2)
    obj.SNSSColor, obj.SNSSHidden = key, bool(hidden)
    if not App.GuiUp:
        return obj
    return apply(obj)


def apply(obj):
    key = getattr(obj, "SNSSColor", "") or "petg"
    hidden = getattr(obj, "SNSSHidden", False)
    rgb, tr = COLORS.get(key, COLORS["petg"])
    vo = obj.ViewObject
    if vo is None:
        return obj
    try:
        vo.ShapeAppearance = (App.Material(DiffuseColor=rgb, Transparency=tr / 100),)
    except Exception:
        try:
            vo.ShapeColor = rgb
        except Exception:
            pass
    try:
        vo.Transparency = tr
    except Exception:
        pass
    if hidden:
        vo.Visibility = False
    return obj


def apply_doc(doc):
    """머리 없이 지은 문서를 열었을 때 — SNSSColor 가 있는 개체를 칠함 (처음 한 번)."""
    if not App.GuiUp:
        return
    for o in doc.Objects:
        if "SNSSColor" in o.PropertiesList:
            try:
                apply(o)
            except Exception:
                pass
