# Blender 설계 — 모든 작품을 Blender 안에서 직접 고치는 설계로

[FREECAD.md](FREECAD.md) 와 같은 일을 Blender 5.2 로 한다. 값은 같은 `design.json` (`snss_battery/fcparams.design()`),
작품도 같은 9가지. 이전의 `sim/blender_*.py` 는 마지막 작업을 **렌더**하는 장면이고, 이것은 **설계** 파일이다 —
치수를 바꾸면 드라이버 · 모디파이어로 모양과 위치가 다시 계산되고, 고친 존재 모양을 Blender 안에서 그대로 조각가로 보낸다.

코드: `snss_battery/bldesign.py` (값 · Blender 실행) · `blender/build_design.py` (머리 없이 짓기) · `blender/snss_design/` (짓기 · 점검 · 애드온) ·
CLI `python -m snss_battery blender-design [--no-render | --open]` · `./tools.sh blender-design` · `view-blender-design` · 시험 `tests/test_blender_design.py`.

## 1. 파일 하나, 장면 9개 — `cad_out/blender/SNSS_Design.blend`

| 장면 | 작품 | 직접 고치는 곳 (사이드바 N → SNSS 의 '설계 값', 또는 개체) |
|---|---|---|
| SC-1 조각가 | 수조 · 배지 · 프레임 · Z · 모터 방수 통 8 · 갠트리 · 펜(노즐 · 혼합기 · 빛 고리 · 원료 관) · 받침(세 팔 너트 판 · 흑연 패드) · 서 있는 존재 | PenX · PenY · BedDrop — 드라이버로 갠트리 · 캐리지 · 받침이 움직임 |
| SC-1 부품 | 출력 부품 20종 — 불리언(정확 풀이) · 베벨 · 비틀기(혼합기) 모디파이어, 비파괴 | 선으로 보이는 '재료' 기본형을 옮기거나 크기를 바꾸면 다시 계산. Rod · Lm8uu 는 나사봉 · 부싱 구멍에 드라이버로 묶임. 조립 장면은 이 부품 컬렉션의 **인스턴스** — 부품을 고치면 조립도 바뀜 |
| SC-2 빛 조각가 | 잉크 우물 · 잉크층 · 광엔진 · 빛길 · 받침 기둥 · 너트 판 · 도구 갠트리 · 도구 걸이 · 데스크톱 · IP68 키보드 · 마우스 | ToolX · ToolY · BedDrop |
| SC-2 도구 | T0–T5 (자석 키네마틱 마운트 + 몸체 + 끝) | 기본형 |
| 존재 모양 | being · seed · bud (메타볼) · coupon | 편집 모드(Tab)에서 메타볼 요소를 옮기고 키우고 더함 (패널 '+ 구 · 캡슐 · 타원체'). TargetHeight = 보낼 때 완성 높이 |
| 빚은 세포 | 마지막 작업의 p · n · 막 표면망 (1/10 로 줄임) | 조각가로 빚고 나면 새 작업으로 바뀜 |
| 시험편 | SC-1 12 mm · SC-2 사다리 A(높이 = Dp·ln(E/Ec) 드라이버) · B · C | Dp · Ec |
| 양자 모듈 | 35층 | Lambda (nSiO2 · nSiN · nAct) — 두께 λ/4n · λ/2n 와 위치가 드라이버 사슬 |
| 병 결정 | 병 · 뚜껑 · 결정 블록 · 절단선 A · 절개선 B · 프로브 | 기본형 |

드라이버는 모두 **단순 식**(Blender 가 파이썬 없이 계산) — 파일을 열 때 '스크립트 자동 실행'을 켜지 않아도 동작한다.
비어 있어야 할 곳 · 쓸고 지나가는 범위는 컬렉션으로 들어 있지만 화면에서 꺼 둠 (점검은 design.json 의 상자로).

### 왜 존재는 메타볼인가

`sculpt.SHAPES` 의 존재는 SDF 를 부드러운 합(smin)으로 이은 것이다. FreeCAD 는 이 부드러운 이음을 B-rep 으로 할 수 없어 그냥 합집합(부피 −3.3 %)이지만,
Blender 메타볼은 같은 방식(영향장을 더해 문턱에서 표면)으로 잇는다. 요소 하나의 표면 반지름 = 영향 반지름 × √(1 − (문턱/강성)^⅓) 이라
SDF 의 반지름을 그대로 넣고, 이음의 부드러움(강성)을 4 로 골라 서 있는 존재 부피를 SDF 와 0.2 % 안으로 맞췄다.

## 2. 점검 (`cad_out/blender/validation.json`)

| 점검 | 방법 | 지금 |
|---|---|---|
| 드라이버 · 모디파이어 | 장면마다 고장난 드라이버 · 재료 없는 불리언 | 0 |
| 출력 부품 | 평가된 메시 부피 ↔ `parts.mesh_part` SDF 부피 · 다양체 아닌 모서리 | 20종 모두 1.6 % 안 · 닫힌 고체 (전극 집게 걸이는 같은 평면 접합을 피하려 0.01 mm 좁힘) |
| 존재 모양 | 메타볼 → 메시 → z 0 에서 잘라 막음 → 부피 ↔ SDF | being −0.2 % · seed −0.0 % · bud −0.9 % · coupon 0 |
| 공간 점검 | 비어 있어야 할 곳 상자 ↔ 고정 부품(컬렉션 인스턴스까지 펼침) — BVH 겹침 + 꼭짓점 · 상자 면 표본 거리 | SC-1 · SC-2 통과 |
| 움직임 점검 | BedDrop 을 출력 높이까지 → 받침 무리 ↔ 고정 부품 · 수조 바닥 | 통과. 일부러 120 mm 내리면 너트 판 ↔ Z 모터 방수 통을 잡음 (FreeCAD 가 찾은 고침과 같은 것) |
| 양자 모듈 | 35층 꼭대기 높이 ↔ 해석값 | 일치 |

메시 거리라 원기둥은 48각 — B-rep(FreeCAD) 보다 0.1 mm 안팎 거칠다.

## 3. Blender 안에서 — 애드온 'SNSS 설계'

`./tools.sh view-blender-design` 이 애드온을 `~/.config/blender/5.2/scripts/addons/snss_design` 에 링크하고 켠 채로 연다. 3D 뷰 사이드바(N) → **SNSS**:

- **설계 값** — 지금 장면의 치수 (끌면 바로 움직임)
- **SC-1 로 빚기 · SC-2 로 빚기** — 고른 모양(없으면 being)을 `cad_out/blender/shapes/bl_이름.stl` 로 내보내고 `sculpt new` / `light` 를 따로 돌림
  (Blender 는 멈추지 않음, 패널에 진행). 끝나면 빚은 세포를 '빚은 세포' 장면으로. 기본 being: SC-1 세포 1255개 · 0.087 J (SDF 존재 1260 · 0.09 J)
- **공간 · 움직임 점검** — SC-1 · SC-2 장면에서
- **세포 SC-1 · SC-2** — 마지막 작업의 세포 다시 불러오기
- **프로젝트 값으로 다시 짓기** — snss_battery 를 바꾼 뒤 (이 파일에서 고친 것은 사라짐 — 확인 창)

## 4. 하지 않는 것

- 기계 배치(layout 상자)는 `layout.py` 가 기준 — Blender 에서 고정 부품을 옮겨도 layout.py 로 돌아가지 않는다. 움직이는 것만 설계 값으로.
- 출력 부품 STL 은 메시 불리언 결과 — 정밀 치수 · STEP 이 필요하면 FreeCAD 쪽(`cad_out/freecad/step/`)을 쓴다.
- 메타볼은 곡면이 해상도(0.3 mm 격자)를 따라 메시가 된다. 조각가의 칸(0.41 × 0.32 mm)보다 고우므로 충분.
