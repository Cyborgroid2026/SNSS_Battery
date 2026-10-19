#!/usr/bin/env bash
# 표준 시뮬레이션 도구 실행 — PHREEQC · PyBaMM · FEniCSx · eLabFTW
#
#   ./tools.sh chem          용액 화학 (PHREEQC): 활동도, 어는점, 막전위 보정
#   ./tools.sh pybamm        배터리 (PyBaMM): 충방전, 기존 모델과 비교
#   ./tools.sh fem           동결·해동 (FEniCSx, Docker) 다시 계산 — 약 2분
#   ./tools.sh fem-summary   저장된 동결·해동 결과만 보기 (Docker 없이)
#   ./tools.sh elab-up       eLabFTW 서버 켜기 → https://localhost:3148
#   ./tools.sh elab-push     공정을 eLabFTW 템플릿·실험으로 올림 (실행할 때마다 새로 만들어짐)
#   ./tools.sh elab-down     eLabFTW 서버 끄기
#   ./tools.sh all           chem → pybamm → fem 계산 (eLabFTW 는 건드리지 않음)
set -euo pipefail
cd "$(dirname "$0")"

PY=python3
VPY=.venv/bin/python
COMPOSE=(docker compose -f elab/docker-compose.yml --env-file elab/.env)

need_venv() {
    if [[ ! -x "$VPY" ]]; then
        echo "가상환경(.venv)이 없어 만듭니다: PyBaMM · phreeqpython 설치…"
        "$PY" -m venv --system-site-packages .venv
        "$VPY" -m pip install --quiet pybamm phreeqpython
    fi
}

need_elab_env() {
    if [[ ! -f elab/.env ]]; then
        echo "elab/.env 가 없습니다. 비밀값(DB 비밀번호, SECRET_KEY, API 키)이 있어야 eLabFTW 를 켤 수 있습니다." >&2
        exit 1
    fi
}

cmd_chem() { "$PY" -m snss_battery chem; }
cmd_pybamm() { need_venv; "$VPY" -m snss_battery pybamm; }
cmd_fem() { "$PY" -m snss_battery fem; }
cmd_fem_summary() { "$PY" -m snss_battery fem --summary; }

cmd_elab_up() {
    need_elab_env
    "${COMPOSE[@]}" up -d
    echo -n "eLabFTW 준비 중"
    for _ in $(seq 1 60); do
        [[ "$(curl -sk -o /dev/null -w '%{http_code}' https://localhost:3148/login.php)" == 200 ]] && break
        echo -n "."; sleep 2
    done
    echo
    echo "→ https://localhost:3148 (자체 서명 인증서라 경고가 뜨면 '계속')"
    echo "→ 로그인 ID: $(grep '^ELAB_ADMIN_EMAIL=' elab/.env | cut -d= -f2) / 비밀번호: elab/.env 의 ELAB_ADMIN_PASSWORD"
}
cmd_elab_push() { need_elab_env; "$PY" -m snss_battery elab; }
cmd_elab_down() { need_elab_env; "${COMPOSE[@]}" down; }

case "${1:-}" in
    chem) cmd_chem ;;
    pybamm) cmd_pybamm ;;
    fem) cmd_fem ;;
    fem-summary) cmd_fem_summary ;;
    elab-up) cmd_elab_up ;;
    elab-push) cmd_elab_push ;;
    elab-down) cmd_elab_down ;;
    all) cmd_chem; echo; cmd_pybamm; echo; cmd_fem ;;
    *) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
