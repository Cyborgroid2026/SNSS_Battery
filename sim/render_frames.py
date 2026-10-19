# ParaView 로 동결 애니메이션 프레임을 PNG 로 뽑음 → 웹 뷰어 '표준 도구' 탭에서 재생 (VS Code 통합 브라우저에서 보임)
#   ./tools.sh fem-movie   (= pvbatch sim/render_frames.py, SNSS_ROOT 필요)
# 화면 구성은 sim/view_freeze.py 와 같음 (왼쪽 새 레시피 · 오른쪽 저가, 파랑 = 얼음, 빨간 선 = 얼음 전선).
import json
import os

ROOT = os.environ["SNSS_ROOT"]
exec(open(os.path.join(ROOT, "sim", "view_freeze.py"), encoding="utf-8").read())

out = os.path.join(ROOT, "results", "frames")
os.makedirs(out, exist_ok=True)
# 더 오래 걸리는 쪽(A, 새 레시피)의 시간 단계 (15분 간격). 먼저 끝난 E 는 마지막 모습으로 남음
times = list(FindSource("freeze_A_new_recipe.xdmf").TimestepValues)  # noqa: F405
times = times[::2]  # 30분 간격
for k, t in enumerate(times):
    scene.AnimationTime = t  # noqa: F821
    SaveScreenshot(os.path.join(out, f"freeze_{k:03d}.png"), layout, ImageResolution=[1100, 640])  # noqa: F405,F821
json.dump({"times_h": [round(float(t), 2) for t in times], "pattern": "freeze_{:03d}.png", "tool": "ParaView 5.13 (pvbatch)"},
          open(os.path.join(out, "frames.json"), "w"))
print(f"프레임 {len(times)}장 → {out}")
