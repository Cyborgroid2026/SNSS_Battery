#!/usr/bin/env bash
# SNSS 생리식염수 결정 배터리 — 한 번에 실행
#
#   ./run.sh          (기본 = full) 검증 + STEP CAD/OpenCascade 검증 + 웹 뷰어
#   ./run.sh all      검증(테스트·교차검증·레시피·도면) 후 웹 뷰어 실행
#   ./run.sh web      웹 뷰어만 (예전 서버는 끄고 새로 띄움)
#   ./run.sh check    검증만 (서버 안 띄움)
#   ./run.sh full     검증 + STEP CAD/OpenCascade 검증 + 웹 뷰어
#   ./run.sh gui      Tkinter GUI
#   ./run.sh static   서버 없이 동작하는 정적 웹 사이트 (web_static/, 더블클릭으로 열림)
#
# 포트 바꾸기: PORT=9000 ./run.sh
set -euo pipefail

cd "$(dirname "$0")"
# rustup 툴체인 우선 (apt 의 /usr/bin/cargo 1.75 는 Cargo.lock v4·edition2024 를 못 읽음)
[ -d "$HOME/.cargo/bin" ] && export PATH="$HOME/.cargo/bin:$PATH"
PORT="${PORT:-8765}"
PY="${PYTHON:-python3}"
MODE="${1:-full}"

step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }

check() {
    step "단위 테스트"
    "$PY" -m unittest discover -s tests -q
    step "Python · Rust · C# 교차 검증"
    "$PY" -m snss_battery crosscheck
    step "양자 모듈"
    "$PY" -m snss_battery quantum
    step "통째 결정 · 인공세포 조직 (3D 보로노이 + 프랙탈 동결 전선, 층·극성 없음)"
    "$PY" -m snss_battery tissue
    step "실물 도면 (cad_out/)"
    "$PY" -m snss_battery cad --out cad_out >/dev/null && echo "cad_out/ 갱신 완료"
}

cadcheck() {
    step "STEP CAD 생성 + OpenCascade 검증 (첫 빌드는 오래 걸림)"
    # OpenCascade 바인딩: SNSS_OCP_PATH → 프로젝트 .ocplib → 없으면 .ocplib 에 설치
    if [[ -z "${SNSS_OCP_PATH:-}" ]] && ! "$PY" -c "import OCP" 2>/dev/null; then
        if [[ ! -d .ocplib/OCP ]]; then
            echo "OpenCascade(cadquery-ocp) 를 .ocplib 에 설치합니다 (약 1.3 GB)…"
            "$PY" -m pip install --quiet --target .ocplib cadquery-ocp
        fi
        export SNSS_OCP_PATH="$PWD/.ocplib"
    fi
    "$PY" -m snss_battery cadcheck || echo "cadcheck 실패 — 위 메시지를 확인하세요"
}

web() {
    # 같은 포트에 떠 있는 예전 서버(옛 코드)를 끈다
    local pids
    pids="$(ss -ltnpH "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u || true)"
    if [[ -n "$pids" ]]; then
        echo "포트 $PORT 의 예전 서버 종료: $pids"
        kill $pids 2>/dev/null || true
        sleep 1
    fi
    step "웹 뷰어 → http://127.0.0.1:$PORT  (끄기: Ctrl+C)"
    exec "$PY" -m snss_battery web --port "$PORT"
}

case "$MODE" in
    all)   check; web ;;
    web)   web ;;
    check) check ;;
    full)  check; cadcheck; web ;;
    gui)   exec "$PY" -m snss_battery gui ;;
    static)
        step "정적 웹 사이트 (web_static/)"
        "$PY" -m snss_battery web --port "$PORT" --no-serve >/dev/null
        "$PY" -m snss_battery static --zip ;;
    *)     sed -n '2,13p' "$0"; exit 1 ;;
esac
