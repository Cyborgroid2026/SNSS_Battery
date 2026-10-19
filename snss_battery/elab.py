"""eLabFTW (오픈소스 전자 실험노트) 연동 — 공정 19단계를 실험 템플릿과 실험으로 올림.

로컬 서버: elab/docker-compose.yml (http://localhost:3148).
비밀값(API 키 등)은 elab/.env 에만 있습니다 (git 제외).

    python3 -m snss_battery elab              # 템플릿 + 실험 만들기 (서버가 떠 있어야 함)
    docker compose -f elab/docker-compose.yml --env-file elab/.env up -d     # 서버 켜기
"""

from __future__ import annotations

import html
import json
import urllib.request
from pathlib import Path

from .process import MODE_KO, process, summary

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "elab" / ".env"
URL = "http://localhost:3148/api/v2"


def _env() -> dict[str, str]:
    return dict(line.split("=", 1) for line in ENV.read_text().splitlines() if "=" in line)


def _call(method: str, path: str, body: dict | None = None) -> tuple[int, dict | None, str]:
    req = urllib.request.Request(URL + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": _env()["ELAB_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        raw = r.read().decode() or "null"
        return r.status, json.loads(raw) if raw.strip().startswith(("{", "[")) else None, r.headers.get("Location", "")


def body_html() -> str:
    steps = process()
    s = summary(steps)
    rows = "".join(
        f"<tr><td>{k}</td><td><b>{html.escape(x.title)}</b></td><td>{MODE_KO[x.mode]}</td><td>{x.hands_min:.0f} 분</td>"
        f"<td>{x.hours:.1f} h</td><td>{html.escape(' · '.join(x.equipment))}</td><td>{html.escape(x.action)}</td>"
        f"<td>{html.escape(x.check)}</td></tr>" for k, x in enumerate(steps, 1))
    return (f"<h2>통째 결정 (인공세포형) — 실험 공정</h2>"
            f"<p>전체 약 {s['hours']:.0f} h ({s['days']:.1f} 일), 손이 드는 시간 약 {s['hands_h']:.1f} h. "
            f"원본: RECIPE.md 3절 · snss_battery/process.py. 판정 기준: EXPERIMENT_PROTOCOL.md (E1–E3, S1–S4).</p>"
            "<table><thead><tr><th>#</th><th>단계</th><th>구분</th><th>손</th><th>걸림</th><th>장비</th><th>할 일</th><th>넘어가는 조건</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            "<h3>측정 기록</h3><table><tbody><tr><td>E2 윗면–아랫면 전압 (정·역 3번)</td><td></td></tr>"
            "<tr><td>E1 벽/칸 Cl 신호 비 (SEM-EDS)</td><td></td></tr><tr><td>S1 칸 폭 µm</td><td></td></tr>"
            "<tr><td>동결 완료 시각 (위쪽 열전대 &lt; −3 °C)</td><td></td></tr></tbody></table>")


def _new(kind: str, title: str, extra: dict | None = None) -> int:
    _, _, loc = _call("POST", f"/{kind}", {"title": title, **(extra or {})})
    return int(loc.rstrip("/").rsplit("/", 1)[-1])


def push(samples: tuple[str, ...] = ("본 시료 — 1회 (S4)", "본 시료 — 3회")) -> dict:
    """템플릿 하나 + 시료마다 실험 하나. 단계는 eLabFTW 의 체크할 수 있는 단계(steps)로 들어감."""
    title = "SNSS 통째 결정 — 실험 공정 (수작업 / 기계작업)"
    tid = _new("experiments_templates", title)
    _call("PATCH", f"/experiments_templates/{tid}", {"body": body_html()})
    for x in process():
        _call("POST", f"/experiments_templates/{tid}/steps", {"body": f"[{MODE_KO[x.mode]}] {x.title} — {x.check}"})
    exps = []
    for name in samples:
        eid = _new("experiments", f"SNSS {name}", {"template": tid})
        exps.append(eid)
    return {"template": tid, "experiments": exps, "url": URL.replace("/api/v2", "")}
