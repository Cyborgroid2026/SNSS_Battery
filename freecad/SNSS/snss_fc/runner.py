"""모든 작품 짓기 + 점검 — 머리 없는 build_all.py 와 워크벤치 '다시 짓기' 가 함께 씀."""

import json
import time
from pathlib import Path

import FreeCAD as App

from . import build, check


def run(D: dict, out: Path, only=(), log=print) -> dict:
    out = Path(out)
    only = set(only)
    want = lambda k: not only or k in only  # noqa: E731
    t0 = time.time()
    V = {"freecad": "FreeCAD " + ".".join(App.Version()[:3]), "gui": bool(App.GuiUp), "docs": [], "exports": [], "clearance": {},
         "motion": {}, "shapes": {}, "parts": []}

    def step(msg):
        log(f"[{time.time() - t0:6.1f} s] {msg}")

    step("SC-1 출력 부품")
    pdoc, parts, _ = build.build_parts(D, out)
    V["parts"] = check.parts_report(pdoc)
    V["exports"] += check.export_part_stls(pdoc, out)
    V["exports"].append(check.export_step(pdoc, out, "SC1_Parts.step", [o for o in pdoc.Objects if o.TypeId == "Part::FeaturePython"]))

    step("존재 모양")
    sdoc, shapes, _ = build.build_shapes(D, out)
    V["shapes"] = check.shape_report(sdoc, out, D.get("shape_sdf_volume_cm3", {}))
    V["exports"].append(check.export_step(sdoc, out, "Being_Shapes.step", list(shapes.values())))
    being = shapes["being"].Shape

    if want("sc1"):
        step("조각가 SC-1 조립")
        d1, _, _ = build.build_sc1(D, out, parts, being)
        V["clearance"]["SC-1"] = check.clearance(d1)
        V["motion"]["SC-1"] = check.bed_motion(d1, D["sc1"]["build"][2])
        V["exports"].append(check.export_step(d1, out, "SC1_Sculptor.step"))
        d1.save()
    tools = None
    if want("sc2"):
        step("SC-2 도구 · 빛 조각가 조립")
        tdoc, tools, _ = build.build_tools(D, out)
        V["exports"].append(check.export_step(tdoc, out, "SC2_Tools.step"))
        d2, _ = build.build_sc2(D, out, parts, tools, being)
        V["clearance"]["SC-2"] = check.clearance(d2)
        V["motion"]["SC-2"] = check.bed_motion(d2, D["sc2"]["build"][2])
        V["exports"].append(check.export_step(d2, out, "SC2_LightSculptor.step"))
        d2.save()
    if want("cells"):
        step("빚은 세포 (표면망)")
        build.build_cells(D, out)
    if want("small"):
        step("시험편 · 양자 모듈 · 병 결정")
        cdoc, _ = build.build_coupons(D, out)
        qdoc, _ = build.build_qmodule(D, out)
        bdoc, _ = build.build_bottle(D, out)
        V["exports"].append(check.export_step(cdoc, out, "Coupons.step"))
        V["exports"].append(check.export_step(qdoc, out, "QModule.step"))
        V["exports"].append(check.export_step(bdoc, out, "Bottle_Crystal.step"))
        q = [o for o in qdoc.Objects if o.TypeId == "Part::Cylinder"]
        V["quantum"] = {"layers": len(q), "volume_mm3": sum(o.Shape.Volume for o in q),
                        "top_z_mm": max(o.Shape.BoundBox.ZMax for o in q)}
    for doc in App.listDocuments().values():
        V["docs"].append(check.doc_report(doc))
    V["seconds"] = round(time.time() - t0, 1)
    (out / "validation.json").write_text(json.dumps(V, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in out.glob("*.FCBak"):  # FreeCAD 가 덮어쓸 때 남기는 백업
        f.unlink()
    step("끝 → validation.json")
    return V


