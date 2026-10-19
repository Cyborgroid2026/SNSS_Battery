#!/usr/bin/env bash
# 표준 시뮬레이션 도구 실행 — PHREEQC · PyBaMM · FEniCSx · eLabFTW
#
#   ./tools.sh chem          용액 화학 (PHREEQC): 활동도, 어는점, 막전위 보정
#   ./tools.sh pybamm        배터리 (PyBaMM): 충방전, 기존 모델과 비교
#   ./tools.sh fem           동결·해동 (FEniCSx, Docker) 다시 계산 — 약 2분
#   ./tools.sh fem-summary   저장된 동결·해동 결과만 보기 (Docker 없이)
#   ./tools.sh elab-up       eLabFTW 서버 켜기 → http://localhost:3148
#   ./tools.sh elab-push     공정을 eLabFTW 템플릿·실험으로 올림 (실행할 때마다 새로 만들어짐)
#   ./tools.sh elab-down     eLabFTW 서버 끄기
#   ./tools.sh all           chem → pybamm → fem 계산 (eLabFTW 는 건드리지 않음)
#   ./tools.sh view-freeze   ParaView 로 동결 애니메이션 보기 (새 레시피 · 저가 나란히)
#   ./tools.sh view-battery  PyBaMM 그래프 창으로 충방전 보기 (시간 슬라이더)
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
        "$VPY" -m pip install --quiet --ignore-installed matplotlib  # 시스템 matplotlib 은 NumPy 1 용이라 venv 안에 따로
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
        [[ "$(curl -sk -o /dev/null -w '%{http_code}' http://localhost:3148/login.php)" == 200 ]] && break
        echo -n "."; sleep 2
    done
    echo
    echo "→ http://localhost:3148"
    echo "→ 로그인 ID: $(grep '^ELAB_ADMIN_EMAIL=' elab/.env | cut -d= -f2) / 비밀번호: elab/.env 의 ELAB_ADMIN_PASSWORD"
}
# ParaView: PATH 에 있으면 그것, 없으면 ~/Applications 에 공식 배포판을 받아 씀 (sudo 불필요)
PV_VER=5.13.3
paraview_bin() {
    if command -v paraview >/dev/null; then command -v paraview; return; fi
    local d=~/Applications/ParaView-$PV_VER-MPI-Linux-Python3.10-x86_64
    if [[ ! -x $d/bin/paraview ]]; then
        echo "ParaView $PV_VER 을(를) ~/Applications 에 내려받습니다 (약 600 MB)…" >&2
        mkdir -p ~/Applications
        curl -L "https://www.paraview.org/files/v${PV_VER%.*}/ParaView-$PV_VER-MPI-Linux-Python3.10-x86_64.tar.gz" | tar xz -C ~/Applications
    fi
    echo "$d/bin/paraview"
}
cmd_view_freeze() {
    [[ -f results/freeze_A_new_recipe.xdmf && -f results/freeze_E_low_cost.xdmf ]] || cmd_fem_movie
    SNSS_ROOT="$PWD" "$(paraview_bin)" --script="$PWD/sim/view_freeze.py" >/dev/null 2>&1 &
    echo "ParaView 를 열었습니다. 위쪽 ▶ 단추로 재생 (파랑 = 얼음, 빨간 선 = 얼음 전선)."
}
cmd_fem_movie() { "$PY" -c "from snss_battery import fem; fem.run(xdmf=True)"; }
cmd_view_battery() { need_venv; "$VPY" -c "from snss_battery import pybamm_cell; pybamm_cell.view()"; }
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
    view-freeze) cmd_view_freeze ;;
    fem-movie) cmd_fem_movie ;;
    view-battery) cmd_view_battery ;;
    *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
