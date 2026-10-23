# FreeCAD 설계 — 모든 작품을 직접 고치는 매개변수 CAD 로

이 저장소의 작품들(조각가 SC-1 · 빛 조각가 SC-2 · 조각 도구 · 존재 · 시험편 · 양자 모듈 · 병 결정)을 **FreeCAD 1.1** 문서로 짓는다.
지금까지는 모양이 코드 속 SDF · 상자 목록이었는데, 이제는 설계 프로그램 안에서 치수 표와 속성을 고쳐 바로 다시 계산하고,
고친 존재 모양을 그대로 조각가로 보내 빚을 수 있다.

코드: `snss_battery/fcparams.py` (값 모으기 · FreeCAD 실행) · `freecad/SNSS/` (FreeCAD 애드온 = 'SNSS 설계' 워크벤치) ·
CLI `python -m snss_battery freecad` · `./tools.sh freecad` · 시험 `tests/test_freecad.py`.

## 1. 흐름

```
snss_battery (명세 · layout · parts · sculpt · quantum · bottle)
   │  fcparams.design()  → cad_out/freecad/design.json      (FreeCAD 쪽은 snss_battery 를 import 하지 않음)
   ▼
FreeCAD 1.1.4 (화면 없는 GUI, 색 · 투명도까지 저장)  freecad/SNSS/build_all.py → snss_fc.runner
   │  문서 9개 *.FCStd · STEP 8개 · 부품 STL 20개 · 모양 STL 4개 · validation.json (점검)
   ▼
FreeCAD 창 (워크벤치 'SNSS 설계')  ── 치수 표 · 속성 고치기 → 다시 계산
   │  '→ 조각가 SC-1 로 빚기'  → python -m snss_battery sculpt new fc_being --shape cad_out/freecad/shapes/fc_being.stl
   │  '→ 빛 조각가 SC-2 로 빚기' → python -m snss_battery light …stl --name fc_being
   ▼
양자 인공세포 · G-code · 빛 그림 · 생명 신호 → Being_Cells.FCStd (다시 짓기 때 마지막 작업의 세포가 들어옴)
```

## 2. 문서

| 문서 | 작품 | 직접 고치는 곳 |
|---|---|---|
| `SC1_Parts.FCStd` | SC-1 출력 부품 20종 (B-rep — 모서리 둥글림 · 구멍 · 나선 혼합기까지 `parts.py` 와 같은 더하기 빼기) | 부품마다 속성 '설계 치수' (예: 꼭짓점 Size · 펜 몸체 Length · 혼합기 Elements). 표 `치수`의 Rod · Lm8uu 는 쓰는 부품 모두에 식으로 묶임 |
| `SC1_Sculptor.FCStd` | 조각가 SC-1 조립 — 유리 수조 · 배지 · 프레임 · Z 나사봉 · 모터 방수 통 8 · 갠트리 · 펜(노즐 · 혼합기 · 빛 고리 · 원료 관) · 원료 펌프 · 전자 방수 통 · 단자판 · 받침(세 팔 너트 판 · 흑연 패드) · 서 있는 존재 | 표 `치수`: PenX · PenY (갠트리가 움직임) · BedDrop (받침이 내려감). 출력 부품은 `SC1_Parts` 로 링크 — 부품을 고치면 조립이 따라옴 |
| `SC2_Tools.FCStd` | SC-2 조각 도구 T0–T5 — 자석 키네마틱 마운트 + 몸체 + 끝 (PEEK 노즐 · 유리 피펫 · PEEK 흡입관 · 나일론 줄 활 · 누름판 · 흑연 탐침) | 도구마다 기본형 |
| `SC2_LightSculptor.FCStd` | 빛 조각가 SC-2 조립 — 잉크 우물 · 잉크층 · 두 색 광엔진 · 빛길 · 받침 기둥 · 너트 판 · 물속 도구 갠트리 · 도구 걸이 · 주사기 펌프 · 데스크톱 받침대 · XPS 단열판 · IP68 키보드 · 마우스 | 표 `치수`: ToolX · ToolY · BedDrop |
| `Being_Shapes.FCStd` | 존재 모양 4가지 — being (몸통 · 머리 · 두 팔 · 두 다리 · 두 발) · seed · bud · coupon | 기본형(타원체 Center · Rx Ry Rz, 캡슐 A · B · Radius, 구)을 고치거나 워크벤치로 캡슐 · 타원체를 더함. `모양 — …` 의 TargetHeight 는 보낼 때 완성 높이 |
| `Being_Cells.FCStd` | 마지막으로 빚은 존재의 양자 인공세포 — p 세포질 · n 세포질 · 막 표면망 (삼각형을 1/10 로 줄임) | 보기용 |
| `Coupons.FCStd` | SC-1 12 mm 시험편 · SC-2 빛 상수 사다리 A(굳은 두께 = Dp·ln(E/Ec) 식) · B · C | 표 `치수`의 Dp · Ec — 사다리 A 칸 높이가 식으로 바뀜 (보정값을 넣어 예측을 봄) |
| `QModule.FCStd` | SNSS-QB 양자 모듈 — 기판 · 거울 8쌍 · 활성층 · 거울 8쌍 · 덮개 35층 | 표 `치수`의 Lambda 하나로 모든 층 두께가 λ/4n · λ/2n 식으로 바뀜 |
| `Bottle_Crystal.FCStd` | 이전 방향 — 생리식염수 병(PE, 벽 0.8) · 결정 블록 · 절단선 A · 절개선 B · 프로브 | 표 `치수`의 병 치수 (실제 병을 재서) |

모든 매개변수 개체는 애드온의 `snss_fc.features` (PrintedPart · Capsule · Ellipsoid) — 애드온이 없으면 모양은 열리지만 다시 계산은 안 된다.
`./tools.sh freecad` 가 `~/.local/share/FreeCAD/v1-1/Mod/SNSS` 에 링크를 건다.

## 3. 점검 (`validation.json`)

| 점검 | 방법 | 지금 결과 |
|---|---|---|
| 다시 계산 · 모양 유효성 | 문서마다 모든 개체 State · BRepCheck (`isValid`) | 문서 9개 · 오류 0 · 유효하지 않은 모양 0 |
| 출력 부품 부피 | B-rep 부피 ↔ `parts.mesh_part` SDF 표면망 부피 | 20종 모두 2.1 % 안 (표면망이 모서리를 깎음) |
| 공간 점검 | layout 의 '비어 있어야 할 곳' 상자 ↔ 고정 부품의 **실제 모양** (원기둥 · 출력 부품 링크) `distToShape` — layout.py 는 감싸는 상자로 봄 | SC-1 · SC-2 모두 통과 (가장 가까운 것: SC-1 펜 이동 공간 ↔ XY 모터 방수 통 4.0 mm, SC-2 빛길 ↔ 렌즈 2.5 mm) |
| 움직임 점검 | 표의 BedDrop 을 출력 높이까지 바꾸고 받침 무리 ↔ 고정 부품 · 수조 바닥 거리 | 통과 |
| 모양 | B-rep 부피 ↔ `sculpt.SHAPES` SDF 부피 | being −3.3 % (FreeCAD 는 부드러운 합 없이 합집합) · seed −0.2 % · bud −1.5 % · coupon 0 |

### 점검이 찾은 설계 고침 — SC-1 높이 예산

FreeCAD 조립에서 받침 밑에 나사봉을 타는 **너트 판**을 실제로 그려 보니, 이전 배치(펜 끝 118 mm · 출력 높이 100 mm)에서는
받침이 다 내려가면 너트 판(바닥 2 mm)이 나사봉 바로 밑의 **Z 모터 방수 통(통 44 + 뚜껑 5 = 49 mm)을 뚫고 지나갔다**.
layout.py 는 너트 판을 그리지 않아 놓쳤다. 고침 (`layout.py` · `printer.py`):

- 받침 최저 = 방수 통 49 + 2 = 51 mm → 펜 끝 = 51 + 너트 판 10 + 받침 6 + 출력 높이.
- 갠트리 = 펜 끝 + 125 (펜 높이). XY 모터 방수 통(갠트리 − 70 … − 24)이 위 프레임 꼭짓점(264 mm~) 아래 2 mm 에 들어야 하므로
  출력 높이 ≤ 94 mm → **90 mm** (서 있는 존재 71 mm + 머리 위 싹 18 mm 가 들어감). 펜 끝 157 mm · 갠트리 282 mm.
- layout.py 점검에 '받침 너트 (가장 낮을 때) ↔ 방수 통' 과 'XY 모터 방수 통 ↔ 위 꼭짓점' 을 더함. SC-2 도 방수 통 높이를 49 로 → 도구 높이 한도 82 → 79 mm.

## 4. 존재 모양 → 조각가

FreeCAD 에서 고친 모양은 STL (선 편차 0.05 mm) 로 나가 `sculpt new … --shape` · `light … .stl` 이 받는다 (STL 은 가운데 · 바닥 0 으로 옮겨지고
`--height` 를 주면 그 높이로 늘림). 기본 being 을 그대로 보내면:

| | SDF being (기존) | FreeCAD being |
|---|---|---|
| SC-1 | 세포 1260 · 0.09 J | 세포 1235 · 0.083 J · 절반이 59.5 분에 깨어남 |
| SC-2 | 세포 1258 · 0.024 J | 세포 1232 · 0.023 J · 243층 · 38.1 h |

차이는 부드러운 합(smin, 3 mm)이 없어서 팔 · 다리 이음이 조금 가늘기 때문 (부피 −3.3 %).

## 5. 하지 않는 것 (정직하게)

- 조립의 기계 배치(layout 상자)는 여전히 `layout.py` 가 기준 — FreeCAD 에서 고정 부품을 옮겨도 layout.py 로 돌아가지 않는다. 배치를 바꾸려면
  layout.py 를 고치고 '다시 짓기'. 움직이는 것(펜 · 도구 캐리지 · 받침)만 표로 움직인다.
- 출력 부품의 둥근 모서리는 FreeCAD 필렛 — SDF 의 둥근 상자와 같은 모양이지만, 반지름이 판 두께의 절반에 닿는 곳(예: 패드 받침 손잡이)은 0.49 배로 줄임.
- 전자 방수 통 · 원료 주사기 · 프로젝터 같은 산 부품은 감싸는 상자 · 원기둥으로만 그림.
- 세포 표면망(Being_Cells)은 메시 — B-rep 이 아니라 점검 · STEP 에서 빠짐.
