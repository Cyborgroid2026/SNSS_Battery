"""머리 없이(또는 화면 없는 GUI 로) 모든 작품을 짓고 점검 — snss_battery/fcparams.py run_build 가 부름.

환경 변수: SNSS_DESIGN (design.json) · SNSS_OUT (출력 폴더) · SNSS_ADDON (이 폴더) · SNSS_ONLY (쉼표로 문서 고르기, 비면 전부)
"""

import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.environ.get("SNSS_ADDON", str(Path(__file__).resolve().parent)))

import FreeCAD as App  # noqa: E402

from snss_fc import runner  # noqa: E402


def main():
    D = json.loads(Path(os.environ["SNSS_DESIGN"]).read_text(encoding="utf-8"))
    only = [s for s in os.environ.get("SNSS_ONLY", "").split(",") if s]
    runner.run(D, Path(os.environ["SNSS_OUT"]), only, log=lambda m: print(m, flush=True))


try:
    main()
except Exception:
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(1)
if App.GuiUp:
    sys.stdout.flush()
    os._exit(0)
