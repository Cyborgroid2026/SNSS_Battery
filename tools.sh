#!/usr/bin/env bash
# 표준 시뮬레이션 도구 실행 — PHREEQC · PyBaMM · FEniCSx · eLabFTW
#
#   ./tools.sh web           웹 뷰어 → http://127.0.0.1:8765/#tools (VS Code: Browser: Open Integrated Browser 에 붙여 넣기)
#   ./tools.sh chem          용액 화학 (PHREEQC): 활동도, 어는점, 막전위 보정
#   ./tools.sh pybamm        배터리 (PyBaMM): 충방전, 기존 모델과 비교
#   ./tools.sh fem           동결·해동 (FEniCSx, Docker) 다시 계산 — 약 2분
#   ./tools.sh fem-summary   저장된 동결·해동 결과만 보기 (Docker 없이)
#   ./tools.sh elab-up       eLabFTW 서버 켜기 → http://localhost:3148
#   ./tools.sh elab-push     공정을 eLabFTW 템플릿·실험으로 올림 (실행할 때마다 새로 만들어짐)
#   ./tools.sh elab-down     eLabFTW 서버 끄기
#   ./tools.sh all           chem → pybamm → fem 계산 (eLabFTW 는 건드리지 않음)
#   ./tools.sh fem-movie     동결 애니메이션 다시 만들기 (FEniCSx → ParaView 프레임, 웹 '표준 도구' 탭에 나옴)
#   ./tools.sh view-freeze   (데스크톱 창) ParaView 로 동결 애니메이션
#   ./tools.sh view-battery  (데스크톱 창) PyBaMM 그래프 창
set -euo pipefail
cd "$(dirname "$0")"
ARGS=("$@")

PY=python3
VPY=.venv/bin/python
COMPOSE=(docker compose -f elab/docker-compose.yml --env-file elab/.env)

need_venv() {
    # 설치까지 끝나면 .venv/.ok 를 남김 — 중간에 실패한 반쪽 .venv 는 지우고 다시 만듦
    if [[ ! -f .venv/.ok ]]; then
        rm -rf .venv
        echo "가상환경(.venv)이 없어 만듭니다: PyBaMM · phreeqpython 설치…"
        if ! "$PY" -m venv --system-site-packages .venv; then
            rm -rf .venv
            echo "python3-venv 가 없습니다: sudo apt install python3-venv 뒤 다시 실행하세요." >&2
            exit 1
        fi
        "$VPY" -m pip install --quiet pybamm phreeqpython
        "$VPY" -m pip install --quiet --ignore-installed matplotlib  # 시스템 matplotlib 은 NumPy 1 용이라 venv 안에 따로
        touch .venv/.ok
    fi
}

need_docker() {
    if ! command -v docker >/dev/null; then
        echo "docker 가 없습니다. 설치: https://docs.docker.com/engine/install/ubuntu/ → sudo usermod -aG docker \$USER → 다시 로그인" >&2
        exit 1
    fi
    # docker 그룹에 막 들어가 아직 다시 로그인 전이면, 그룹을 붙여 이 명령을 다시 실행
    if ! docker info >/dev/null 2>&1 && ! id -nG | grep -qw docker && id -nG "$USER" | grep -qw docker; then
        exec sg docker -c "$(printf '%q ' "$PWD/tools.sh" "${ARGS[@]}")"
    fi
}

need_elab_env() {
    if [[ ! -f elab/.env ]]; then
        echo "elab/.env 가 없어 새로 만듭니다 (비밀값 무작위 생성)."
        "$PY" -m snss_battery elab --setup
    fi
}

cmd_chem() { "$PY" -m snss_battery chem; }
cmd_pybamm() { need_venv; "$VPY" -m snss_battery pybamm; }
cmd_fem() { need_docker; "$PY" -m snss_battery fem; }
cmd_fem_summary() { "$PY" -m snss_battery fem --summary; }

cmd_elab_up() {
    need_docker
    need_elab_env
    "${COMPOSE[@]}" up -d
    # 처음 한 번: DB 표 만들기 (MySQL 이 뜰 때까지 기다림). 끝나면 표시 파일을 남김
    if [[ ! -f elab/data/.installed ]]; then
        echo -n "DB 준비 중"
        until docker exec snss-elabftw-db mysqladmin ping -s >/dev/null 2>&1; do echo -n "."; sleep 2; done
        echo
        docker exec snss-elabftw bin/init db:install && touch elab/data/.installed
        echo "→ 처음이면 http://localhost:3148 에서 계정을 만드세요 (첫 가입자 = 관리자), 그다음 API 키를 elab/.env 에."
    fi
    echo -n "eLabFTW 준비 중"
    for _ in $(seq 1 60); do
        [[ "$(curl -sk -o /dev/null -w '%{http_code}' http://localhost:3148/login.php)" == 200 ]] && break
        echo -n "."; sleep 2
    done
    echo
    echo "→ http://localhost:3148"
    local id; id=$(grep '^ELAB_ADMIN_EMAIL=' elab/.env | cut -d= -f2)
    [[ -n "$id" ]] && echo "→ 로그인 ID: $id"
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
cmd_fem_movie() {  # FEniCSx 로 애니메이션 데이터 → ParaView(pvbatch) 로 웹용 프레임
    need_docker
    "$PY" -c "from snss_battery import fem; fem.run(xdmf=True)"
    SNSS_ROOT="$PWD" "$(dirname "$(paraview_bin)")/pvbatch" sim/render_frames.py 2>&1 | grep -v "hwloc\|^\*\|^$" || true
}
cmd_view_battery() { need_venv; "$VPY" -c "from snss_battery import pybamm_cell; pybamm_cell.view()"; }
cmd_web() {
    echo "웹 뷰어 → http://127.0.0.1:8765/#tools  (VS Code: Ctrl+Shift+P → 'Browser: Open Integrated Browser' → 주소 붙여 넣기)"
    "$PY" -m snss_battery web --port 8765
}
cmd_elab_push() { need_elab_env; "$PY" -m snss_battery elab; }
cmd_elab_down() { need_docker; need_elab_env; "${COMPOSE[@]}" down; }

case "${1:-}" in
    web) cmd_web ;;
    chem) cmd_chem ;;
    pybamm) cmd_pybamm ;;
    fem) cmd_fem ;;
    fem-summary) cmd_fem_summary ;;
    elab-up) cmd_elab_up ;;
    elab-push) cmd_elab_push ;;
    elab-down) cmd_elab_down ;;
    all) need_docker; cmd_chem; echo; cmd_pybamm; echo; cmd_fem ;;
    view-freeze) cmd_view_freeze ;;
    fem-movie) cmd_fem_movie ;;
    view-battery) cmd_view_battery ;;
    *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
