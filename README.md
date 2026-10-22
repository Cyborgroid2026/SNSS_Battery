# SNSS — 조각가 SC-1 · 양자 인공세포 존재

**지금 방향 (2026-10):** 화학적 SNSS 배터리 대신, **양자공학이 뒷받침하는 3D 프린팅**.
만드는 것은 출력물이 아니라 **프린터 — 자기 소재로 조각하는 조각가**입니다. 사실상 **3D 펜을 단 3D 프린터**이고,
GO · SNSS(멸균생리식염수) · PVA 가 따로 펜에 들어가 끝에서 하나가 되어, **양자 인공세포**로 구조화된 존재(Energetic Being)를 빚습니다.
**수중 환경**: 기계까지 통째로 멸균생리식염수(= 배지) 배양조에 잠겨 작업합니다 (젖는 쪽은 비금속, 모터 · 전자는 방수 통). 세포 배양하듯 결정체가 배지 속에서 자라고
(잉크가 배지에 닿으면 굳고, 밀도가 거의 같아 떠 있듯 버팀), 다 자라면 배양 받침째 들어 올려 배지에서 바로 꺼냅니다.
모든 공정은 **상온**, 층을 더하고 깎고 떼고 다시 붙일 수 있습니다. 기계 부품은 **3D 프린터로 뽑고**, 원료는 **시중에서** 삽니다.
**아날로그 · 디지털 · 양자 공학기기**와 모두 호환되고, **Blender** 와 이어집니다. 명세: [spec/SCULPTOR.md](spec/SCULPTOR.md).

| 해 보기 | 명령 |
|---|---|
| 기계 명세 · Klipper 설정 · 구매 목록 | `./tools.sh sculptor` |
| 존재 새로 빚기 (G-code · 생명 신호 · 메시) | `./tools.sh being` → `python -m snss_battery sculpt new being` |
| 이어 빚기 · 깎기 · 떼기 · 붙이기 · 허공 획 · 기억 | `python -m snss_battery sculpt add being --shape bud` · `carve` · `detach --z 24` · `attach 아래 위` · `draw --strokes …` · `show` · `list` |
| Blender 렌더 · 동영상 · 창으로 열기 | `./tools.sh blender` · `blender-anim` · `view-blender` |
| Blender 에서 그린 모양 · 획 보내기 | Blender 안에서 `sim/blender_export.py` → `sculpt new 이름 --shape sculpt_out/shape.stl` |
| 출력 부품 STL + 구매 목록 + 부품판 | `./tools.sh parts` |
| 호환 단자 · SCPI 다리 · C–V 되먹임 · 양자 난수 씨앗 | `./tools.sh ports` · `python -m snss_battery scpi` · `cv-fit 측정.csv` · `sculpt new … --qrng /dev/…` |
| 웹 뷰어 ('조각가 · 존재' 탭) | `./tools.sh web` |

서 있는 존재 (높이 71 mm, 기본값 예측): 양자 인공세포 1260개 (p 636 · n 624) · 간극연접 2355쌍 · 에너지 약 0.09 J (0.8 V) ·
발에 충전하면 세포 절반이 약 57 분에 깨어남. 빚는 데 작업 약 14.5 h + 배양 6 h, 배지(생리식염수) 40 L. 값의 근거와 가정은 명세 §2–5.

---

**아래는 이전 방향 — 화학적 SNSS 배터리 (생리식염수 결정 · 인공세포)** 입니다. 코드 · 시험 · 웹 탭은 그대로 남아 있습니다.

## SNSS Battery — 생리식염수 결정 · 인공세포

동네 약국에서 사는 **멸균생리식염수(0.9 % NaCl) 병** 안에 **그래핀 폴리머 액정(GO)**과 PVA를 섞고, 병 그대로 아래에서 위로 얼리면
식염수에서 바로 **얼음 결정**이 자랍니다. 결정 하나하나가 **인공세포**의 틀이 되고, GO·PVA는 결정 경계로 밀려나 **막**이 됩니다.
녹이면 세포 안(내강)은 묽고, 밀려난 소금은 막 사이에 진한 소금물로 모입니다. **비어 있는 인공세포에 에너지(농도차)만 담긴 상태**입니다.
**층도, 세포 극성도 없습니다.** 생물학·공학 요소는 아직 넣지 않았습니다. 금속 무함유.

이 저장소는 그 실험을 설계·예측·기록하는 시뮬레이터입니다.

## 지금 구조 — 통째 결정 · 인공세포 조직

| 항목 | 모델 예측 (`python3 -m snss_battery tissue`) |
|---|---|
| 결정 | Ø70.4 × 128 mm, 인공세포 약 1억 개 (세포 약 170 µm) |
| 만드는 법 | 비커에서 섞어 병에 다시 담기 → 저온실(+4 °C) 안 −20 °C 냉각판 위 방향성 동결 약 16 h ⇄ 25 °C 수조 해동, 3회 · 약 3.6일 ([RECIPE.md](RECIPE.md) 3절 공정표) |
| 인공세포 하나 | 막(GO/PVA) + 묽은 내강(약 2 mM) + 막 사이 진한 소금물(약 1.6 M) + 빈 결합 자리 · 저장 에너지 약 8 µJ |
| 병 전체 저장 에너지 | 약 900 J (잠겨 있음) |
| 윗면–아랫면 전압 | 약 2 mV — 층·극성이 없어 막전위(53 mV)가 사방으로 상쇄 → 사실상 0, LED 불가 |
| 다음 단계 | 빈 결합 자리에 공학 요소(채널·전극 연결)를 넣어 에너지를 꺼냄 — 결정화(동결)가 끝난 뒤에 넣음 |

**프랙탈 · 보로노이 연속성.** 3D 세포는 2D 보로노이·프랙탈 탭과 같은 생성 규칙을 씁니다.
- **결정핵:** 흔들린 격자 또는 Soneira–Peebles 규칙으로 만듭니다.
- **동결 전선:** Weierstrass–Mandelbrot 곡면으로, 같은 D와 같은 8 mm 장을 씁니다.
- **보로노이 원소가 그대로 구조:** 세포(3D)는 내강이고, 면(2D)은 막과 막 사이 소금물이고, 모서리(1D)는 소금물 통로입니다.

판정은 [EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md)의 E1~E3(에너지)과 S1~S4(구조)로 합니다.

---

**아래 절들은 이전 층 모델(묽은/진한 층이 번갈아 쌓인다고 가정)의 설명으로, 비교용으로 남겨 둡니다.** 웹 뷰어의 '비교 · 층 모델' 탭과 Python·Rust·C# 교차 검증이 이 모델을 씁니다.

## 과정

| 단계 | 내용 |
|---|---|
| 1 | 생리식염수 500 mL 통 개봉 |
| 2 | 그래핀 폴리머 액정(기본 5 mg/mL = 2.5 g) + 반응 화학물질을 부음 |
| 3 | 세워 둔 채 결정화 — 아래부터 세포형 도메인이 층을 이루며 자람. 이웃 도메인의 염 농도가 다른 채 굳음 → **충전된 상태로 태어남** |
| 4 | 절단선 A·절개선 B로 통을 잘라 결정을 꺼냄 |
| 5 | 결정 윗면(+)·아래면(-)에 멀티미터 프로브 → 개방전압 측정 |
| 6 | 다 쓰면 반대 방향 전류로 농도차를 다시 만들어 재사용 |

### 물리적 전제 (중요)

- **세포가 한 방향으로 줄지어야** 막전위가 직렬로 더해집니다(전기뱀장어 발전세포와 같은 원리).
  병 안에 캡슐이 무작위로 흩어져 있으면 전압이 서로 상쇄되어 0 V가 됩니다.
- 에너지원은 **결정화 때 생긴 농도차**뿐입니다. 아무것도 공급받지 않고 계속 에너지를 내는 구조는
  물리적으로 불가능합니다(실제 세포도 영양분을 씁니다). 그래서 첫 방전 후에는 충전해서 재사용합니다.
- 보관 중에는 막을 통한 염 확산으로 농도차가 서서히 줄어듭니다(기본값 기준 1/e 수명 약 72일).
- **별도 전극이 없으므로** 결정 표면 그래핀의 전기이중층이 꺼낼 수 있는 전기량을 제한합니다(기본 약 0.25 mAh).
  전압계(전류 ≈ 0)로 재는 개방전압은 이 제한과 무관합니다. 표면 그래핀은 `--surface-go`로 바꿀 수 있습니다.
- **결정화 시 농도비**(기본 20)가 이 배터리의 핵심 미지수입니다. 실제 겔에서 층별 전도도·막전위를 측정해 넣어야 합니다.
- "결정화"는 엄밀히는 염이 GO 판의 정전기적 반발을 가려서 생기는 정렬 겔화(자기조립)입니다.

## 기본값 예측 (500 mL 통, 출발값 기준)

| 항목 | 값 |
|---|---|
| 결정 블록 | Ø70.4 × 127.6 mm, 약 502 g |
| 세포형 도메인 | 252층 (126쌍, 층 0.5 mm) |
| 프로브로 바로 재는 개방전압 | 약 10.6 V |
| 내부저항 | 약 137 Ω |
| 첫 방전 (0.1 mA) | 약 0.22 mAh (표면 그래핀이 제한) |
| 재충전 후 | 약 0.44 mAh, 쿨롱효율 약 95 % |

막 선택도·저항·염 투과도, 전극 정전용량, CCC 등은 **문헌 범위의 출발값**입니다. 실측값으로 바꿔야 예측이 의미를 가집니다.

## 보로노이 · 프랙탈 (핵심 개념)

결정화는 결정핵(씨앗)에서 자란 도메인들이 만나는 곳에 벽이 생기는 과정이므로, 도메인 구조는 결정핵의
**보로노이 분할**입니다(Johnson–Mehl 성장). 여기에 프랙탈 두 가지를 얹습니다.

| 개념 | 모델 | 파라미터 |
|---|---|---|
| 세포형 도메인 | 결정핵의 보로노이 분할 (scipy.spatial.Voronoi) | `--grains` 층 두께당 결정핵 수 |
| 층 경계 프랙탈 | 묽은/진한 층 경계 = Weierstrass–Mandelbrot 곡선 | `--fractal-d` 차원 D, `--roughness`, `--correlation` |
| 결정핵 분포 프랙탈 | Soneira–Peebles 프랙탈 점집합 (크고 작은 도메인이 섞임) | `--seed-d` (2 = 고름) |
| 측정 | 박스 카운팅 차원 (코흐 곡선 1.26으로 검증) | 웹 뷰어에서 실험 사진에도 적용 |

**전기 회로망:** 각 보로노이 도메인을 노드, 도메인 벽을 간선(막 저항 + 막전위)으로 보고 개방전압·내부저항·내부 누설을 풉니다.
- 층 번호가 1 차이 나는 벽은 이온 선택막(막전위 ±E)입니다.
- 같은 층끼리의 벽은 저항만 있습니다.
- 층을 건너뛴 벽은 **결함 = 단락 경로**입니다.
- 층이 평평하면 기존 층 모델과 같은 전압(10.56 V)이 나옵니다.

예측된 경향 (출발값 기준):
- 프랙탈 차원 D가 클수록 막 면적이 늘어 내부저항이 조금 줄어듭니다.
- 경계 거칠기가 층 두께의 약 0.4배를 넘거나, 이웃 경계가 제각각 휘면(상관도↓) 결함 단락이 급증합니다. 그러면 전압이 떨어지고 내부 누설이 커집니다.
- 결정핵이 뭉치면(D_s↓) 큰 도메인이 여러 층을 가로질러 단락이 많아집니다.

```bash
python3 -m snss_battery fractal --sweep   # 현재 배합 해석 + D·거칠기 스윕
python3 -m snss_battery lighting          # LED·꼬마전구 점등 판정
python3 -m snss_battery crosscheck        # Python·Rust·C# 교차 검증 (결정 + 양자 모듈)
python3 -m snss_battery quantum           # 양자 모듈
python3 -m snss_battery cadcheck          # STEP 생성 + OpenCascade 검증
```

## 레시피

[RECIPE.md](RECIPE.md) — 통째 결정 (인공세포형) 하나만 있습니다. 층을 나눠 붓던 이전 레시피(연습판·LED판)는 뺐습니다.

```bash
python3 -m snss_battery recipe    # 재료량 + 동결 계산 + 인공세포 조직 예측 + 공정표 (수작업 / 기계작업)
```

## 대사 — 안에서 에너지를 만드는 방법

생명체처럼 결정 안에서 에너지를 계속 만들려면 "먹이"가 필요합니다. 에너지는 무에서 생기지 않습니다.
생물학적 요소(효소·생물)는 쓰지 않습니다 (`metabolism.py`).

| 먹이 | 방식 | 기본값 전력 |
|---|---|---|
| 빛 (광합성형) | 도메인 벽 속 금속 없는 광촉매(g-C3N4 등)가 이온을 퍼 올림 | 약 76 µW (낮) |
| 내장 연료 (소화형) | 포도당 등이 비효소 산화되며 이온 생성 + 접촉면이 연료전지처럼 반응 | 약 344 µW (시작) |
| 증발 (호흡형) | 윗면 증발로 생기는 기울기 — 번갈아 놓인 막 때문에 거의 상쇄 | 약 2 µW |
| 레시피 반응물 | 사용자가 넣는 화학물 (값 입력 대기) | 0 |

**전구 판정** (`python3 -m snss_battery lighting`):
- **빨강 LED + 470 Ω:** 처음에 약 14 mA로 밝게 켜집니다. 그 뒤 연료와 빛으로 약 93시간 희미하게 유지되다가, 연료가 줄면 꺼집니다.
- **백열 꼬마전구 2.5 V 0.3 A:** 결정을 6조각으로 잘라 병렬로 연결하면 처음 약 6분 동안 붉게 빛납니다. 대사 전력이 필요 전력의 1/267이라 계속 켜 둘 수는 없습니다.

## 교차 검증 — Python · Rust · C#

```bash
python3 -m snss_battery crosscheck
```

- **같은 명세:** [spec/SPEC.md](spec/SPEC.md)와 기준 사례 [spec/cases.json](spec/cases.json)을 세 언어가 따로 구현합니다.
- **같은 입력:** 난수 생성기(SplitMix64)까지 같게 맞췄습니다.
- **다른 알고리즘:** 보로노이를 Python은 Qhull로, Rust·C#은 직접 짠 반평면 절단으로 구합니다.
- **결과:** 4개 사례, 86개 값이 모두 상대오차 10⁻¹¹ 이하로 일치합니다.

| 구현 | 위치 | 역할 |
|---|---|---|
| Python | `snss_battery/` | 기준 구현, GUI, 웹 뷰어 |
| Rust | `rust/` (`cargo run --release -- crosscheck ../spec/cases.json`, `-- render <폴더>`) | 독립 구현, 웹용 SVG 그림 렌더링 |
| C# (.NET 10) | `csharp/Snss.Lab` (`dotnet run -c Release --project Snss.Lab -- crosscheck …` / `verify <log.jsonl>`) | 독립 구현, **실험 판정기** |

교차 검증이 증명하는 것은 **계산의 재현성**까지입니다. 실제로 전기가 나오는지는 실험만이 증명합니다.
[EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md)에 측정 전에 정한 가설 H1~H7과 판정 기준이 있고,
웹 뷰어의 **실험 기록**에 넣은 측정값을 C# 판정기가 **검증** 탭에서 자동으로 판정합니다.

## 표준 시뮬레이션 도구 — PHREEQC · PyBaMM · FEniCSx · eLabFTW

이 프로젝트 전체를 한 번에 다루는 공식 프로그램은 없으므로, 분야마다 표준 오픈소스 도구로 다시 계산해 자체 모델과 대조합니다.

| 영역 | 도구 | 명령 | 결과 |
|---|---|---|---|
| 용액 화학 (활동도, 어는점, 공정점) | **PHREEQC** (USGS) · pitzer.dat | `python3 -m snss_battery chem` (`--rebuild` 는 `.venv` 필요) | [spec/phreeqc_nacl.json](spec/phreeqc_nacl.json) |
| 배터리 (충방전, 확산, 농도 분극) | **PyBaMM** | `.venv/bin/python -m snss_battery pybamm` | [spec/pybamm_validation.json](spec/pybamm_validation.json) |
| 방향성 동결 · 해동 (열전달 + 상변화) | **FEniCSx** (Docker `dolfinx/dolfinx:v0.9.0`) | `python3 -m snss_battery fem` (`--summary` 는 Docker 없이) | [spec/fenicsx_freezing.json](spec/fenicsx_freezing.json) |
| 공정 · 시료 · 측정 기록 | **eLabFTW** (Docker, 로컬 http://localhost:3148) | `python3 -m snss_battery elab --setup` | [elab/](elab/) |

- **설치:** `python3 -m venv --system-site-packages .venv && .venv/bin/pip install pybamm phreeqpython` (`.venv` 는 git 제외).
- **PyBaMM 검증:** 같은 가정(농도 고름 · 이상 용액)으로 풀면 기존 모델과 방전 용량이 유효숫자 4자리까지 일치합니다. 확산 + 활동도를 넣으면 개방전압이 10.56 → 9.77 V 로 낮아집니다.
- **PHREEQC 검증:** NaCl 활동도계수가 Robinson & Stokes 값과 0.01 안, 공정점 5.21 mol/kg (문헌 5.2).

## 양자 모듈 (SNSS-QB) — 별도로 만든 진짜 양자 배터리

**생리식염수 결정 자체는 양자 배터리가 될 수 없습니다.** 에너지가 상온 물속 이온의 농도차로 저장되는데, 이 상태의 결맞음은 펨토초 안에 사라집니다.
대신 금속·생물 요소 없이 만들 수 있는 **유기 미세공진기 Dicke 형 양자 배터리**를 별도 모듈로 설계했습니다
(실증 연구: Quach 외, *Science Advances* 2022). 명세는 [spec/QUANTUM.md](spec/QUANTUM.md)에 있습니다.

| 항목 | 내용 |
|---|---|
| 구조 | 용융 실리카 / SiO₂·Si₃N₄ 유전체 거울 8쌍 / PMMA + 페릴렌 색소 활성층(198 nm, λ/2n) / 거울 8쌍 / 덮개 (Ø24–25 mm) |
| 양자 효과 | 분자 N개가 함께 충전 → 충전 시간 ∝ N^−0.40, N=128에서 따로 충전할 때보다 평균 전력 ×6.5 |
| 실제 소자 | 충전 약 34 fs (라비 분열 0.1 eV 가정) < 분자 결맞음 50 fs, 광자 수명 47 fs → 양자 이점 유효 범위 (여유가 작음) |
| 한계 | 최대 약 0.2 mJ를 약 4 ns 동안만 저장 — 전구를 켜는 장치가 아니라 빛으로 매우 빨리 충전·방출하는 장치 |

```bash
python3 -m snss_battery quantum     # 양자 모듈 계산
python3 -m snss_battery cadcheck    # Rust(truck)·C# 로 STEP 생성 + OpenCascade 검증 (pip install cadquery-ocp 필요)
```

### CAD (STEP, ISO 10303-21 AP214)

| 파일 | 만든 곳 | 고체 |
|---|---|---|
| `cad_out/step/qmodule_rust.step` | Rust — **truck** B-rep CAD 커널 (`rust_cad/`) | 35 |
| `cad_out/step/qmodule_csharp.step` | C# — 정확한 B-rep 을 STEP 으로 직접 작성 (`csharp/Snss.Lab/StepWriter.cs`) | 35 |
| `cad_out/step/crystal_block_rust.step` / `_csharp.step` | 결정 블록 도메인 층 252개 + 벽 252장 | 504 |

- **검증 방법:** 산업 표준 커널 OpenCascade로 STEP 파일을 읽어 고체 수, B-rep 유효성(BRepCheck), 층별 부피를 해석값과 대조했습니다.
- **결과:** 고체 539개가 모두 유효하고, 오차는 10⁻⁹ 이하입니다. Rust와 C#은 B-rep 위상이 다르지만(면 5개 대 3개) 기하는 일치합니다. 기록은 [spec/cad_validation.json](spec/cad_validation.json)에 있습니다.
- **열 수 있는 CAD:** FreeCAD, Fusion 360, SolidWorks, Onshape, CATIA 등에서 바로 열립니다.

## 실행

```bash
./run.sh                                  # 한 번에: 테스트·교차 검증·레시피·도면·STEP/OpenCascade 검증 → 웹 뷰어 (./run.sh web 은 뷰어만)
python3 -m snss_battery web --port 8765   # 웹 뷰어 → http://127.0.0.1:8765/ (VS Code 내장 브라우저)
python3 -m snss_battery tissue            # 통째 결정 · 인공세포 조직 (3D 보로노이 + 프랙탈 동결 전선, 층·극성 없음)
python3 -m snss_battery gui               # 데스크톱 GUI (Tkinter + matplotlib)
python3 -m snss_battery info              # 사양 + 금속 검사
python3 -m snss_battery cycle             # 프로브 연결 → 방전 → 재충전
python3 -m snss_battery cad --out cad_out # 도면·템플릿·3D 파일
python3 -m snss_battery assembly --go 5   # GO 액정 + 식염수 막 형성 판정
python3 -m unittest discover -s tests
```

주요 옵션: `--volume 500 --diameter 72 --go 5 --layer 0.5 --ratio 20 --shrink 0 --surface-go 0 --reactants "..." --age-days 0`

웹 뷰어 탭 (작업 · 검증 · 자료 · 비교(이전 층 모델) 네 묶음):
- **실험대:** 통째 결정의 실제 공정 19단계(`snss_battery/process.py`, RECIPE.md 3절)를 실험실 장비로 재생합니다. 단계마다 **수작업 / 기계작업**, 손이 드는 시간, 걸리는 시간이 표시됩니다. 계량·덜기 → 핫플레이트 교반기로 PVA 용해 → GO 응집 예비 시험 → 비커에서 섞고 기포 빼기 → 병에 다시 담기 → 저온실 냉각판 위 방향성 동결(얼음 전선이 올라가며 세포가 생김) ⇄ 항온수조 해동 → 꺼내기 → 윗면–아랫면 전압(≈0) → 액체질소 고정 · 동결건조 · SEM-EDS 순서입니다.
- **CAD 작업대:** 병 속 결정 → 상세도 A ×30(실제 계산한 3D 보로노이 세포 1152개, GO/PVA 막, 소금물 통로) → 인공세포 1개 ×200(막, 묽은 내강과 막 바깥 진한 소금물의 이온, 빈 결합 자리)을 한 화면에 이어서 보여 줍니다. 모델 트리, 속성, 시점, 투영, 표시 방식, 단면, 분해도, 치수, STL·PNG 내보내기를 제공합니다. 층·극성은 없습니다.
- **결정화 과정:** 붓기 → 섞임 → 얼음 결정핵 → 아래부터 보로노이 세포 성장 → 절단 → 프로브 측정을 2D 단면 애니메이션으로 보여 줍니다(층·극성 없음). 재생, 구간 이동, 단계 클릭이 됩니다. WebGL 없이 2D로 그립니다.
- **전구·대사:** 만드는 전력과 필요한 전력을 비교하고, LED 1주일 타임라인과 꼬마전구 점등 그래프를 보여 줍니다(Rust SVG).
- **양자 모듈:** 집단 충전 곡선, 모듈 단면, 교차 검증, STEP 다운로드와 OpenCascade 검증 표를 보여 줍니다.
- **검증:** 세 언어 교차 검증 표와 실험 가설 H1~H7의 자동 판정을 보여 줍니다.
- **보로노이·프랙탈:** 슬라이더(D, 거칠기, 상관도, 결정핵 분포)로 단면을 바로 다시 계산하고, 실시간 박스 카운팅과 지도 보간 전압·출력을 보여 줍니다. 회로망 계산 그림, D×거칠기 출력 지도, 실험 사진 프랙탈 분석도 있습니다.
- **실험 기록:** 경과 시간, 상태, 전압, 전류, 반응 화학물, 메모를 입력하면 `experiments/log.jsonl`에 저장됩니다(서버 실행 시). 모델 예측과 같은 그래프에 표시하고 CSV로 받을 수 있습니다.
- **나머지 탭:** 개요(시료 비교 표), 실물 도면, 시뮬레이션, 재료표, 파일. three.js 를 함께 넣어 두어 인터넷 없이도 동작합니다.
- **바로 열기:** 주소 `#lab`, `#cad`, `#process`, `#log` 등으로 해당 탭이 열립니다. `?lab=practice&labt=0.5#lab` 로 실험대 시료·위치를, `?sample=led&stage=200&explode=50#cad` 로 CAD 작업대 시료·단계·분해 정도를, `?t=0.6#process` 로 애니메이션 위치를 지정할 수 있습니다.

## 출력 파일 (`cad` 명령)

| 파일 | 용도 |
|---|---|
| `assembly_drawing.dxf/pdf/png` | 도면: ① 통 안 결정화(절단선 A·절개선 B) ② 꺼낸 결정 + 프로브 측정 ③ 상면도, 상세 C(도메인 구조), 재료표, 실험 순서 |
| `template_1to1.dxf/pdf` | 1:1 인쇄 템플릿: 통에 감는 절단 가이드 띠 (배율 100 % 인쇄) |
| `stl/*.stl` | 결정 블록, 절단된 통 |
| `battery.scad` | OpenSCAD 파라메트릭 모델 |
| `materials.csv` | 재료표 |

병 치수(`BottleSpec`)는 일반적인 500 mL 병의 근사값입니다. 실제 쓰는 병을 재서 `--diameter` 등으로 맞추세요.

## 구조

| 모듈 | 역할 |
|---|---|
| `bottle.py` | 통·결정화 조건 → 결정 블록, 세포형 도메인층, 태어날 때 상태, 보관 수명, 표면 그래핀 |
| `artificial_cell.py` | 도메인층 전기 모델 (막전위, 저항, 용량, 자가방전) |
| `assembly.py` | GO 액정 + 식염수 → 막 형성(결정화) 판정 |
| `electrolyte.py` / `materials.py` | 식염수 물성 / 막·전극 재료 DB, 금속 검사 |
| `simulation.py` | 탄생 방전 + 충방전 사이클, I-V |
| `tessellation.py` | 보로노이 + 프랙탈 도메인 회로망, 박스 카운팅, 스윕 (numpy·scipy) |
| `metabolism.py` | 대사(빛·연료·증발·반응물), LED·꼬마전구 부하, 1주일 시뮬레이션 |
| `recipe.py` | 레시피 재료량 계산, 모델 예측 |
| `process.py` | 실험 공정 19단계 — 수작업 / 기계작업, 손 시간, 장비, 넘어가는 조건, 해동 시간 계산 (RECIPE.md · 레시피 탭 · 실험대가 함께 씀) |
| `quantum.py` / `cadcheck.py` | 양자 모듈 (Tavis–Cummings), STEP 생성·검증 |
| `specrng.py` / `crosscheck.py` | 언어 독립 난수, 교차 검증 |
| `cad.py` / `drawing.py` | 실물 형상·3D 메쉬 / 도면 (DXF·PDF) |
| `plots.py`, `gui.py`, `web.py`, `cli.py` | 그래프, GUI, 웹 뷰어(애니메이션·실험 기록 API), 명령줄 |
| `vendor/three/` | three.js r160 (MIT) — 오프라인 3D 표시용 |

## 다음 단계

- 실제 레시피(고분자·첨가 화학물, 양, 결정화 시간·온도)를 `GelFormation`에 반영
- 결정화된 겔에서 층별 농도(전도도)·막전위를 측정해 농도비와 막 파라미터 보정
- 삼투에 의한 물 이동, 겔 수축, 온도 의존성 모델링
