# ParaView 에서 방향성 동결 애니메이션 보기 — 왼쪽: 새 레시피(A), 오른쪽: 저가(E)
#   ./tools.sh view-freeze      (= paraview --script=sim/view_freeze.py)
# 파란색 = 얼음, 흰색 = 아직 물, 회색 = 병 · 단열재. 아래 재생(▶) 단추로 시간을 돌립니다 (단위 h).
# 축대칭 계산이라 병 반쪽 단면만 있으므로 가운데 축으로 뒤집어 붙여 단면 전체를 보여 줍니다.
import os

from paraview.simple import *  # noqa: F401,F403

# paraview --script 로 실행하면 __file__ 이 없음 → tools.sh 가 넘기는 SNSS_ROOT, 없으면 현재 폴더
ROOT = os.environ.get("SNSS_ROOT") or os.getcwd()
CASES = [("freeze_A_new_recipe.xdmf", "A · 새 레시피 (저온실 냉각판)"),
         ("freeze_E_low_cost.xdmf", "E · 저가 (냉동실 + 단열 8 cm)")]

# 한글 글꼴 (ParaView 기본 글꼴에는 한글이 없음): 나눔 글꼴이 없으면 기본 글꼴 (한글이 네모로 나옴)
# 나눔 TTF 는 첫 문자표가 Mac Roman 이라 VTK 가 한글을 못 그림 → 유니코드 문자표만 있는 Noto CJK 를 먼저
KO = next((f for f in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc")
           if os.path.exists(f)), None)


def korean(prop_owner, prefix=""):
    if KO:
        setattr(prop_owner, prefix + "FontFamily", "File")
        setattr(prop_owner, prefix + "FontFile", KO)


first = GetActiveViewOrCreate("RenderView")
layout = GetLayout(first)
views = []
for k, (name, title) in enumerate(CASES):
    path = os.path.join(ROOT, "results", name)
    if not os.path.exists(path):
        raise SystemExit(f"{path} 가 없습니다. 먼저 ./tools.sh fem-movie 를 실행하세요.")
    src = Xdmf3ReaderT(registrationName=name, FileName=[path])  # dolfinx XDMF 는 Xdmf3 리더 (옛 XDMFReader 는 죽음)
    # 시간 묶음이 둘 (fem.py 가 temperature_C → ice_fraction 순으로 씀) — 얼음 묶음만 써야 Contour 가 빈 배열을 안 만남
    ice = ExtractBlock(registrationName=f"얼음 묶음 {k}", Input=src, Selectors=["/Root/Block1"])
    full = Reflect(registrationName=f"단면 {k}", Input=ice)
    full.Plane = "X"  # r = 0 축으로 뒤집어 붙임
    view = first if k == 0 else CreateView("RenderView")
    if k:
        layout.SplitHorizontal(0, 0.5)
        layout.AssignView(2, view)
    # 바탕: 병 · 단열재 (회색 한 색)
    back = Show(full, view)
    back.ColorArrayName = ["POINTS", ""]
    back.DiffuseColor = back.AmbientColor = [0.62, 0.64, 0.67]
    # 겔만 (얼음 비율 0–1): 흰색 = 물 → 파랑 = 얼음
    gel = Threshold(registrationName=f"겔 {k}", Input=full)
    gel.Scalars = ["POINTS", "ice_fraction"]
    gel.LowerThreshold, gel.UpperThreshold = -0.5, 1.5
    disp = Show(gel, view)
    ColorBy(disp, ("POINTS", "ice_fraction"))
    lut = GetColorTransferFunction("ice_fraction")
    lut.RGBPoints = [0.0, 1.0, 1.0, 1.0, 1.0, 0.13, 0.4, 0.85]
    lut.RescaleTransferFunction(0.0, 1.0)
    lut.AutomaticRescaleRangeMode = "Never"
    bar = GetScalarBar(lut, view)
    bar.Title, bar.ComponentTitle, bar.Visibility = "얼음 비율 (0 물 · 1 얼음)", "", 1
    bar.AddRangeLabels, bar.RangeLabelFormat, bar.LabelFormat = 0, "%.1f", "%.1f"
    bar.UseCustomLabels, bar.CustomLabels = 1, [0.0, 0.5, 1.0]
    bar.WindowLocation, bar.Position, bar.ScalarBarLength = "Any Location", [0.86, 0.25], 0.4
    korean(bar, "Title")
    # 얼음 전선 = 얼음 비율 0.5 등치선
    front = Contour(registrationName=f"얼음 전선 {k}", Input=gel)
    front.ContourBy = ["POINTS", "ice_fraction"]
    front.Isosurfaces = [0.5]
    fd = Show(front, view)
    fd.ColorArrayName = ["POINTS", ""]  # 단색 (빨강)
    fd.DiffuseColor = fd.AmbientColor = [0.9, 0.1, 0.1]
    fd.LineWidth = 3
    label = Text(registrationName=f"제목 {k}")
    label.Text = title
    ld = Show(label, view)
    ld.FontSize = 14
    korean(ld)
    clock = AnnotateTimeFilter(registrationName=f"시각 {k}", Input=src)
    clock.Format = "경과 {time:.1f} h"
    cd = Show(clock, view)
    cd.WindowLocation, cd.FontSize = "Lower Left Corner", 18
    korean(cd)
    view.InteractionMode = "2D"
    view.OrientationAxesVisibility = 0
    ResetCamera(view)
    views.append(view)

AddCameraLink(views[0], views[1], "같은 시점")
scene = GetAnimationScene()
scene.UpdateAnimationUsingDataTimeSteps()
scene.GoToFirst()
Render()
