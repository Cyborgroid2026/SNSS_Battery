"""FEniCSx 동결 · 해동 시뮬레이션 (sim/freeze_fenicsx.py) 실행 · 결과 요약.

FEniCSx 는 Docker 이미지로 돌립니다 (설치 없이): dolfinx/dolfinx:v0.9.0.
결과 spec/fenicsx_freezing.json 은 저장소에 함께 두어 Docker 없이도 요약·웹에서 씁니다.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "dolfinx/dolfinx:v0.9.0"
OUT = ROOT / "spec" / "fenicsx_freezing.json"


def run(cell_m: float = 0.0008, xdmf: bool = False) -> None:
    """xdmf=True: ParaView 애니메이션(results/*.xdmf)만 만듦. 결과 파일이 내 소유가 되도록 현재 사용자로 실행."""
    user = f"{os.getuid()}:{os.getgid()}"
    subprocess.run(["docker", "run", "--rm", "-v", f"{ROOT}:/work", "-w", "/work", "--user", user, "-e", "HOME=/tmp", IMAGE,
                    "python3", "sim/freeze_fenicsx.py", str(cell_m), *(["--xdmf"] if xdmf else [])], check=True)


def load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8"))


def describe(r: dict | None = None) -> str:
    r = r or load()
    lines = [f"FEniCSx 동결 · 해동 ({r['tool']}) — 어는점 {r['melt_c']:.2f} °C (PHREEQC)"]
    for c in r["cases"]:
        done = f"{c['t_all_h']:.1f} h" if c["t_all_h"] else f"40 h 안에 {100 * c['done_fraction']:.0f} % 만"
        line = f"  {c['name']}\n    전부 {'녹음' if 'side_lead_mid' not in c else '얾'}: {done}"
        if "side_lead_mid" in c:
            line += (f" · 아래→위로 언 비율 {100 * c.get('bottom_up_fraction', float('nan')):.0f} % · "
                     f"가운데 높이에서 벽이 가운데보다 {100 * c['side_lead_mid']:+.0f} % 먼저 얾")
        lines.append(line)
    return "\n".join(lines)
