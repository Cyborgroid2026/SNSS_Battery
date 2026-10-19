"""정적 웹 사이트: 서버 없이 동작하는 웹 뷰어 (index.html 더블클릭 · GitHub Pages · 아무 정적 호스팅).

    python -m snss_battery static            # web_out → web_static
    python -m snss_battery static --zip      # web_static.zip 도 만듦

web 명령이 만든 사이트(web_out)를 바꿔 쓴다.
- model.json · model_tissue.json → data/*.js 로 내장 (file:// 에서는 fetch 가 막힘)
- workbench.js → index.html 안의 인라인 모듈 (file:// 에서는 외부 모듈 스크립트가 막힘)
- three.js → CDN (jsDelivr, 같은 r160) — 3D 작업대는 인터넷 연결 필요
- 실험 기록 → 브라우저 localStorage, 판정 → 브라우저 안 JS (C# 판정기와 같은 규칙)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

THREE_CDN = "https://cdn.jsdelivr.net/npm/three@0.160.0"
_IMPORTMAP_LOCAL = '{ "imports": { "three": "./vendor/three/three.module.js", "three/addons/": "./vendor/three/" } }'
_IMPORTMAP_CDN = ('{ "imports": { "three": "%s/build/three.module.js", '
                  '"three/addons/OrbitControls.js": "%s/examples/jsm/controls/OrbitControls.js" } }' % (THREE_CDN, THREE_CDN))
_WORKBENCH_TAG = '<script type="module" src="ui/workbench.js"></script>'


def export_static(src: str | Path = "web_out", out: str | Path = "web_static", make_zip: bool = False) -> Path:
    src, out = Path(src), Path(out)
    if not (src / "index.html").exists():
        raise FileNotFoundError(f"{src}/index.html 이 없습니다 — 먼저 python -m snss_battery web --no-serve")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out, ignore=shutil.ignore_patterns("vendor", "model.json", "model_tissue.json", "workbench.js"))

    (out / "data").mkdir(exist_ok=True)
    for name, var in (("model.json", "SNSS_MODEL"), ("model_tissue.json", "SNSS_TISSUE")):
        if (src / name).exists():
            body = json.dumps(json.loads((src / name).read_text(encoding="utf-8")), ensure_ascii=False, separators=(",", ":"))
            (out / "data" / name.replace(".json", ".js")).write_text(f"window.{var}={body};\n", encoding="utf-8")

    html = (src / "index.html").read_text(encoding="utf-8")
    workbench = (src / "ui" / "workbench.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    for old in (_IMPORTMAP_LOCAL, _WORKBENCH_TAG):
        if old not in html:
            raise ValueError(f"index.html 에서 바꿀 부분을 찾지 못했습니다: {old[:40]}…")
    data_tags = "".join(f'<script src="data/{n}"></script>\n' for n in ("model.js", "model_tissue.js")
                        if (out / "data" / n).exists())
    html = html.replace(_IMPORTMAP_LOCAL, _IMPORTMAP_CDN)
    html = html.replace(_WORKBENCH_TAG, data_tags + '<script type="module">\n' + workbench + "\n</script>")
    (out / "index.html").write_text(html, encoding="utf-8")

    if make_zip:
        shutil.make_archive(str(out), "zip", out)
    return out / "index.html"
