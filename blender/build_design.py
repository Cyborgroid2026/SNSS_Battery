"""Blender(머리 없이)로 모든 작품을 짓고 점검 — snss_battery/bldesign.py 가 부름.

blender -b --factory-startup --python blender/build_design.py -- <design.json> <출력 폴더> [--no-render]
"""

import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402

from snss_design import build, check  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    D = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    V = {"blender": bpy.app.version_string, "scenes": [], "parts": [], "shapes": {}, "clearance": {}, "motion": {}, "renders": []}

    def step(m):
        print(f"[{time.time() - t0:6.1f} s] {m}", flush=True)

    for o in list(bpy.data.objects):  # 시작 파일의 Cube · 카메라 · 빛
        bpy.data.objects.remove(o)
    step("SC-1 부품")
    sp, parts = build.build_parts(D)
    step("존재 모양 (메타볼)")
    ss, shapes = build.build_shapes(D)
    step("SC-1 조각가")
    s1 = build.build_sc1(D, parts, shapes)
    step("SC-2 도구 · 빛 조각가")
    st, tools = build.build_tools(D)
    s2 = build.build_sc2(D, parts, tools, shapes)
    step("SC-3 솜사탕 조각가")
    s3 = build.build_sc3(D, parts, shapes)
    step("빚은 세포 · 시험편 · 양자 모듈 · 병 결정")
    sc_cells = build.build_cells(D)
    rest = [build.build_coupons(D), build.build_qmodule(D), build.build_bottle(D)]
    step("점검")
    V["parts"] = check.parts_report(sp, out)
    V["shapes"] = check.shapes_report(ss, out, D.get("shape_sdf_volume_cm3", {}))
    V["clearance"]["SC-1"] = check.clearance(s1, D["sc1"]["layout"])
    V["clearance"]["SC-2"] = check.clearance(s2, D["sc2"]["layout"])
    V["motion"]["SC-1"] = check.bed_motion(s1, D["sc1"]["build"][2])
    V["motion"]["SC-2"] = check.bed_motion(s2, D["sc2"]["build"][2])
    q = next(s for s in rest if s.name == "양자 모듈")
    dg = build.dg_of(q)
    layers = [o for o in q.objects if o.type == "MESH"]
    V["quantum"] = {"layers": len(layers), "top_z_mm": max(o.evaluated_get(dg).location.z + o.evaluated_get(dg).scale.z for o in layers)}
    order = [s3, s1, sp, s2, st, ss] + ([sc_cells] if sc_cells else []) + rest
    for sc in order:
        V["scenes"].append(check.scene_report(sc))
    if "--no-render" not in argv:
        step("미리보기 렌더")
        for i, sc in enumerate(order):
            V["renders"].append(check.render(sc, out / "preview" / f"{i + 1:02d}_{sc.name}.png"))
    bpy.context.window_manager.windows[0].scene = s1 if bpy.context.window_manager.windows else None
    step("뷰포트 기본값 — 처음 열면 SC-1 의 3D 프린팅 패드를 비춤")
    import math
    from mathutils import Euler

    pad = build.pad_view(s1)
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type != "VIEW_3D":
                continue
            sp = area.spaces[0]
            sp.clip_start, sp.clip_end = 0.5, 20000
            sp.shading.type, sp.shading.color_type, sp.shading.light = "SOLID", "MATERIAL", "STUDIO"
            r3 = sp.region_3d
            r3.view_location = pad + __import__("mathutils").Vector((0, 0, 25))
            r3.view_distance = 380
            r3.view_rotation = Euler((math.radians(65), 0, math.radians(30))).to_quaternion()
            r3.view_perspective = "PERSP"
    step("저장")
    bpy.context.preferences.filepaths.save_version = 0  # .blend1 백업을 남기지 않음
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "SNSS_Design.blend"), compress=True)
    V["seconds"] = round(time.time() - t0, 1)
    (out / "validation.json").write_text(json.dumps(V, ensure_ascii=False, indent=1), encoding="utf-8")
    step("끝 → validation.json")


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
