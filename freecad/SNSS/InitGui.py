# SNSS 설계 워크벤치 — FreeCAD 가 시작할 때 읽음 (Mod/SNSS → 저장소의 freecad/SNSS 링크)
import os

import FreeCADGui as Gui


class SNSSWorkbench(Gui.Workbench):
    MenuText = "SNSS 설계"
    ToolTip = "조각가 SC-1 · 빛 조각가 SC-2 · 존재 · 시험편 · 양자 모듈 · 병 결정 — 설계를 고쳐 조각가로 보냄"

    def __init__(self):
        import snss_fc

        self.__class__.Icon = os.path.join(os.path.dirname(snss_fc.__file__), "..", "icons", "snss.svg")

    def Initialize(self):
        from snss_fc import commands

        names = commands.register()
        self.appendToolbar("SNSS 설계", names)
        self.appendMenu("SNSS 설계", names)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(SNSSWorkbench())
