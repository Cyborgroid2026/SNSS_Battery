"""실험대 발표 자료 (report/report.pptx) — 웹 뷰어 '실험대' 스크린샷 + 단계 설명.

    ./tools.sh web &                              # 웹 뷰어가 떠 있어야 스크린샷을 찍음
    .venv/bin/python report/make_pptx.py          # 스크린샷 → report/img/bench/*.jpg → report/report.pptx
    .venv/bin/python report/make_pptx.py --no-shots   # 저장된 스크린샷으로 슬라이드만 다시
    .venv/bin/python report/make_pptx.py --no-shots --render   # 물리 엔진 렌더(Blender)를 새로 그리고 슬라이드로

단계 그림: report/img/physics/stepNN.png (sim/blender_bench.py — Mantaflow 유체 · Bullet 강체 · Cycles) 가 있으면 그것을,
없으면 웹 '실험대' 스크린샷을 씀 (--web 으로 스크린샷 강제). 단계마다 물리 칸 = snss_battery.benchphys.

필요: .venv/bin/pip install python-pptx playwright (브라우저는 설치된 google-chrome 을 씀).
단계 내용은 snss_battery/process.py (RECIPE.md 3절) 그대로.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pptx import Presentation  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN  # noqa: E402
from pptx.oxml.ns import qn  # noqa: E402
from pptx.util import Emu, Inches, Pt  # noqa: E402

from snss_battery.process import HAND, process, summary  # noqa: E402

SHOTS = ROOT / "report" / "img" / "bench"
PHYS = ROOT / "report" / "img" / "physics"
ENGINE = {"mantaflow": "Mantaflow 유체 (FLIP)", "bullet": "Bullet 강체", "fenicsx": "FEniCSx 열전달", "해석식": "해석식 (닫힌 식)"}
OUT = ROOT / "report" / "report.pptx"
URL = "http://127.0.0.1:8765/#lab"
FONT = "Malgun Gothic"  # 맑은 고딕 — Windows · Office 기본 한글 글꼴

INK, ICE, PAPER, WHITE = "16324F", "DCEBF7", "F4F7FA", "FFFFFF"
HANDC, MACHC, MUTED, LINE = "E07A1F", "2F6FD6", "5B6B7B", "C9D3DD"
W, H = 13.333, 7.5


# ---------- 스크린샷 ----------
def shoot() -> None:
    """실험대 탭을 단계마다 애니메이션 60 % 지점으로 옮겨 무대(.lab-stage)만 찍음."""
    from PIL import Image
    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(parents=True, exist_ok=True)
    width = "() => parseFloat(document.querySelector('#labBar').style.width) / 100"
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=2)
        pg.goto(URL)
        pg.wait_for_timeout(2500)
        pg.screenshot(path=SHOTS / "full.png")
        n = pg.locator("#labSteps li").count()
        starts = [0.0]
        for _ in range(n - 1):
            pg.click("#labNext")
            pg.wait_for_timeout(100)
            starts.append(pg.evaluate(width))
        starts.append(1.0)
        for k in range(n):
            pg.evaluate("u => window.__lab.seek(u)", starts[k] + 0.6 * (starts[k + 1] - starts[k]))
            pg.wait_for_timeout(700)
            pg.locator(".lab-stage").screenshot(path=SHOTS / f"step{k + 1:02d}.png")
        b.close()
    for f in SHOTS.glob("*.png"):  # 아래 빈 서랍장은 잘라 냄
        im = Image.open(f).convert("RGB")
        if f.stem != "full":
            im = im.crop((0, 0, im.width, int(im.width / 2.54)))
        im.save(f.with_suffix(".jpg"), quality=88)
        f.unlink()


def physics_json() -> list[dict]:
    import json

    from snss_battery.benchphys import bench_physics

    data = [s.to_json() for s in bench_physics()]
    PHYS.mkdir(parents=True, exist_ok=True)
    (PHYS / "physics.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return data


def render_physics() -> None:
    """Blender (Mantaflow · Bullet · Cycles) 로 19단계 그림 — 몇 분 (유체 굽기 포함)."""
    import subprocess

    physics_json()
    subprocess.run(["blender", "-b", "--factory-startup", "--python", str(ROOT / "sim" / "blender_bench.py"), "--",
                    str(PHYS / "physics.json"), str(PHYS)], check=True)


def step_image(k: int) -> tuple[Path, bool]:
    """물리 엔진 렌더가 있으면 (jpg 로 줄여) 그것, 없으면 웹 스크린샷."""
    png = PHYS / f"step{k:02d}.png"
    if not png.exists() and png.with_suffix(".jpg").exists() and "--web" not in sys.argv:  # git 에는 jpg 만
        return png.with_suffix(".jpg"), True
    if png.exists() and "--web" not in sys.argv:
        jpg = png.with_suffix(".jpg")
        if not jpg.exists() or jpg.stat().st_mtime < png.stat().st_mtime:
            from PIL import Image

            Image.open(png).convert("RGB").save(jpg, quality=88)
        return jpg, True
    return SHOTS / f"step{k:02d}.jpg", False


# ---------- 슬라이드 도우미 ----------
def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


def _font(run, size, color, bold=False):
    run.font.size, run.font.bold, run.font.color.rgb = Pt(size), bold, rgb(color)
    run.font.name = FONT
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):  # 한글은 ea 글꼴로 그려짐
        el = rpr.find(qn(tag))
        if el is None:
            el = rpr.makeelement(qn(tag), {})
            rpr.append(el)
        el.set("typeface", FONT)


def text(slide, x, y, w, h, runs, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         margin=0.0, space=6, name=None):
    """runs: 문자열, 또는 문단 목록 [[(글, {size,color,bold}), ...], ...]."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap, tf.vertical_anchor = True, anchor
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", Inches(margin))
    paras = [[(runs, {})]] if isinstance(runs, str) else runs
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        for t, o in para:
            r = p.add_run()
            r.text = t
            _font(r, o.get("size", size), o.get("color", color), o.get("bold", bold))
    return tb


def box(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08, name=None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb, s.line.width = rgb(line), Pt(1)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if name:
        s.name = name
    return s


def chip(slide, x, y, label, fill, w=None, size=13):
    w = w or 0.32 + 0.17 * len(label)
    s = box(slide, x, y, w, 0.38, fill, radius=0.5)
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    _font(r, size, WHITE, True)
    return w


def fit_size(paras, w_in: float, h_in: float, size: float, floor: float = 8.0, space: float = 3.0) -> float:
    """글자 크기를 칸에 들어갈 때까지 줄임 — 줄 수 어림: 한글 1 em, 그 밖 0.55 em, 줄 높이 1.2 em + 문단 간격."""
    def height(sz):
        tot = 0.0
        for para in paras:
            em = sum(sum(1.0 if ord(ch) > 0x2E80 else 0.55 for ch in t) * o.get("size", sz) / sz for t, o in para)
            lines = max(1, math.ceil(em * sz / (w_in * 72 * 0.94)))
            tot += lines * sz * 1.2 + space
        return tot / 72
    while size > floor and height(size) > h_in:
        size -= 0.5
    return size


def scaled(paras, base: float, size: float):
    """문단 안 글 크기를 같은 비율로."""
    k = size / base
    return [[(t, {**o, "size": o.get("size", base) * k}) for t, o in para] for para in paras]


def picture(slide, path, x, y, w=None, h=None, name=None):
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)
    pic.line.color.rgb, pic.line.width = rgb(LINE), Pt(0.75)
    if name:
        pic.name = name
    return pic


def bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = rgb(color)


def title(slide, t, sub=None):
    text(slide, 0.6, 0.38, W - 1.2, 0.7, t, size=30, bold=True, name="제목")
    if sub:
        text(slide, 0.6, 1.02, W - 1.2, 0.4, sub, size=14, color=MUTED, name="부제")


def dur(h: float) -> str:
    return f"{h:.1f} h" if h >= 1 else f"{h * 60:.0f} 분"


# ---------- 슬라이드 ----------
def build() -> None:
    steps = process()
    sm = summary(steps)
    phys = {p["id"]: p for p in physics_json()}
    from snss_battery.benchphys import engine_items

    for sid, rows_ in engine_items(PHYS / "engine.json").items():  # 엔진이 잰 값을 물리 칸 맨 위에
        if sid in phys:
            phys[sid]["items"] = rows_ + phys[sid]["items"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6]
    new = lambda: prs.slides.add_slide(blank)  # noqa: E731

    # 1. 표지
    s = new()
    bg(s, INK)
    text(s, 0.7, 0.75, 6.0, 0.4, "SNSS 생리식염수 결정 배터리", size=16, color="9EC3E6", bold=True)
    text(s, 0.7, 1.2, 6.0, 1.9, "통째 결정 실험 —\n실험대에서 보는 19단계", size=36, color=WHITE, bold=True, space=0)
    text(s, 0.7, 3.35, 5.6, 1.6, "약국 식염수병을 그릇 삼아 아래에서 위로 얼려, 얼음 결정 하나하나가 "
         "인공세포가 되게 하는 과정을 — 단계마다 실제 물성으로 계산한 물리와, 그 숫자로 움직인 물리 엔진 "
         "(Blender Mantaflow 유체 · Bullet 강체 · FEniCSx 열전달) 렌더로 따라갑니다.", size=15, color="D5E3F0")
    text(s, 0.7, 6.55, 6.0, 0.4, "웹 뷰어 http://127.0.0.1:8765/#lab · ./tools.sh bench-physics · 2026-10-31", size=12, color="8FA9C2")
    picture(s, SHOTS / "full.jpg", 6.75, 1.2, w=6.0, name="실험대 전체 화면")
    text(s, 6.75, 4.75, 6.0, 0.4, "웹 뷰어 '실험대' 탭 — 지금 화면", size=12, color="8FA9C2")
    s.notes_slide.notes_text_frame.text = (
        "웹 뷰어의 실험대 탭을 그대로 찍은 화면입니다. 왼쪽 무대에서 장비가 움직이고, 오른쪽에는 계기, 실험 노트, 절차가 나옵니다. "
        "이 자료의 단계 화면은 모두 같은 탭에서 각 단계의 60 % 지점을 찍은 것입니다.")

    # 2. 개요 — 숫자
    s = new()
    bg(s, WHITE)
    title(s, "한눈에 보는 실험", "500 mL 식염수병 하나 기준 · 동결 · 해동 시간은 FEniCSx 열전달 계산값")
    stats = [(f"{sm['days']:.1f}일", f"전체 약 {sm['hours']:.0f} h"), (f"{sm['hands_h']:.1f} h", "사람 손이 드는 시간"),
             ("19단계", f"수작업 {sm['hand_steps']} · 기계작업 {sm['machine_steps']}"), ("22 h", "방향성 동결 1회 (3회 반복)")]
    for i, (big, small) in enumerate(stats):
        x = 0.6 + i * 3.08
        box(s, x, 1.75, 2.82, 2.05, PAPER, name=f"숫자 {i + 1}")
        text(s, x + 0.25, 1.95, 2.4, 1.0, big, size=40, bold=True, color=INK if i else MACHC)
        text(s, x + 0.25, 3.0, 2.4, 0.6, small, size=14, color=MUTED)
    pts = [("결정 = 세포.", " 아래에서 위로 천천히 얼리면 얼음 결정 하나가 세포 하나의 틀이 되고, GO · PVA 는 결정 경계로 밀려나 막이 됩니다."),
           ("빈 세포에 에너지.", " 소금도 얼음에서 밀려나, 녹인 뒤 세포 안은 묽고(약 2 mM) 막 사이는 진합니다(약 1.6 M). 이 농도차가 담긴 에너지입니다."),
           ("전기는 아직 안 나옵니다.", " 층 · 극성이 없어 위아래가 대칭이라 윗면–아랫면 전압은 약 2 mV 가 정상입니다.")]
    text(s, 0.6, 4.2, W - 1.2, 2.8, [[(a, {"bold": True}), (b, {})] for a, b in pts], size=16, space=10)

    # 3. 재료표
    s = new()
    bg(s, WHITE)
    title(s, "재료표", "모두 금속 무함유 — 소금의 나트륨 이온은 체액 이온 · 500 mL 병 하나 기준")
    rows = [("재료", "규격", "쓰는 양"),
            ("멸균생리식염수", "0.9 %, 500 mL 나사 마개 병", "1병 (병은 그릇으로도 씀)"),
            ("그래핀 산화물(GO) 분산액", "4 mg/mL, 판 10 µm 이상", "62.5 mL → 병 안 0.5 mg/mL"),
            ("PVA (폴리비닐알코올)", "분자량 85,000–124,000, 가수분해 99 % 이상", "15.00 g → 병 전체 3 wt%"),
            ("증류수", "—", "증발한 만큼 보충"),
            ("접촉액", "30 % 에탄올 (−20 °C 에서 안 얾)", "몇 mL · 전지에 안 들어감")]
    tbl = s.shapes.add_table(len(rows), 3, Inches(0.6), Inches(1.65), Inches(8.1), Inches(4.2)).table
    for j, wd in enumerate((2.75, 3.05, 2.3)):
        tbl.columns[j].width = Inches(wd)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = tbl.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = rgb(INK if i == 0 else (PAPER if i % 2 else WHITE))
            c.margin_left = c.margin_right = Inches(0.12)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = c.text_frame
            tf.word_wrap = True
            r = tf.paragraphs[0].add_run()
            r.text = val
            _font(r, 14, WHITE if i == 0 else INK, i == 0 or j == 0)
    box(s, 9.05, 1.65, 3.68, 4.2, ICE, name="나눠 담기")
    text(s, 9.3, 1.85, 3.2, 3.9, [[("나눠 담는 양", {"bold": True, "size": 18})],
                                  [("① 식염수 100 mL 를 덜어 PVA 15 g 을 녹임 (15 wt%)", {})],
                                  [("② 식염수 62.5 mL 를 더 덜어 GO 자리를 비움", {})],
                                  [("③ 남은 337.5 + PVA 용액 100 + GO 62.5", {})],
                                  [("= 500 mL", {"bold": True, "size": 22, "color": MACHC})]], size=14, space=10)
    text(s, 0.6, 6.15, W - 1.2, 0.7, "대조군 A · C 는 같은 배합을 한 번에 만들어 나눠 담고, 대조군 B 는 GO 대신 식염수 62.5 mL 로 따로 만듭니다.",
         size=14, color=MUTED)

    # 4. 전체 흐름
    s = new()
    bg(s, WHITE)
    title(s, "네 묶음으로 보는 19단계", "단계 시간은 '걸리는 시간', 괄호는 그중 손이 드는 시간")
    groups = [("준비", "1–10", range(0, 10), "PVA 를 녹이고 GO 와 섞어 병에 다시 담기"),
              ("동결 · 해동", "11–14", range(10, 14), "냉각판에서 아래 → 위 방향성 동결, 수조 해동, 3회"),
              ("꺼내기 · 측정", "15–17", range(14, 17), "병을 자르고 전압 · 단면 사진 · 조각 고정"),
              ("분석", "18–19", range(17, 19), "동결건조 뒤 SEM-EDS 로 소금 분포")]
    for i, (name, rng, idx, desc) in enumerate(groups):
        x = 0.6 + i * 3.08
        hrs = sum(steps[k].hours for k in idx)
        hands = sum(steps[k].hands_min for k in idx) / 60
        box(s, x, 1.75, 2.82, 4.6, PAPER, name=f"묶음 {i + 1}")
        text(s, x + 0.25, 1.95, 2.4, 0.4, f"단계 {rng}", size=13, color=MUTED, bold=True)
        text(s, x + 0.25, 2.3, 2.4, 0.6, name, size=24, bold=True)
        text(s, x + 0.25, 3.0, 2.4, 0.6, f"{hrs:.1f} h", size=32, bold=True, color=MACHC)
        text(s, x + 0.25, 3.65, 2.4, 0.4, f"(손 {hands:.1f} h)", size=13, color=MUTED)
        text(s, x + 0.25, 4.2, 2.35, 2.0, desc, size=14)
        if i < 3:  # 묶음 사이 화살표
            arr = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + 2.86), Inches(3.82), Inches(0.18), Inches(0.3))
            arr.fill.solid()
            arr.fill.fore_color.rgb = rgb(MUTED)
            arr.line.fill.background()

    # 4b. 물리로 다시 본 실험 — 레시피와 어긋나는 곳
    s = new()
    bg(s, WHITE)
    title(s, "물리로 다시 본 실험 — 조심할 곳", "단계마다 실제 물성으로 계산 (snss_battery/benchphys.py · spec/PHYSICS.md) — ⚠ 는 레시피 그대로면 어긋날 수 있는 곳")
    warn = [(k, st, phys[st.id]) for k, st in enumerate(steps, 1) if not phys[st.id]["ok"]]
    for i, (k, st, p) in enumerate(warn[:8]):
        bh = min(1.3, (H - 1.75) / math.ceil(min(len(warn), 8) / 2) - 0.15)
        x, y = 0.6 + (i % 2) * 6.15, 1.6 + (i // 2) * (bh + 0.15)
        box(s, x, y, 5.95, bh, "FFF4E5", name=f"주의 {k}")
        paras = [[(f"{k}. {st.title}  ", {"bold": True, "color": HANDC, "size": 13}), (ENGINE.get(p["engine"], p["engine"]), {"color": MUTED, "size": 11})],
                 [(p["verdict"], {"size": 13})]]
        sz = fit_size(paras, 5.6, bh - 0.15, 13)
        text(s, x + 0.2, y + 0.08, 5.6, bh - 0.12, scaled(paras, 13, sz), size=sz, space=3)
    if not warn:
        text(s, 0.6, 1.8, W - 1.2, 1.0, "계산상 어긋나는 단계가 없습니다.", size=18)

    # 5. 단계별 — 왼쪽 물리 엔진 그림, 오른쪽 물리 칸
    for k, st in enumerate(steps, 1):
        s = new()
        bg(s, WHITE)
        hand = st.mode == HAND
        p = phys[st.id]
        text(s, 0.6, 0.3, 9.3, 0.6, [[(f"{k}. ", {"color": MUTED}), (st.title, {})]], size=28, bold=True, name="제목")
        cw = chip(s, W - 0.6 - 1.25, 0.4, "수작업" if hand else "기계작업", HANDC if hand else MACHC, w=1.25)
        text(s, W - 0.6 - cw - 3.1, 0.42, 3.0, 0.38, f"걸림 {dur(st.hours)} · 손 {st.hands_min:.0f} 분", size=14,
             color=MUTED, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
        img, rendered = step_image(k)
        pw = 8.6
        picture(s, img, 0.6, 1.05, w=pw, name=f"단계 그림 {k}")
        ph = pw / 2.54
        px = 0.6 + pw + 0.2
        box(s, px, 1.05, W - 0.6 - px, ph, PAPER if p["ok"] else "FFF4E5", name="물리")
        rows = [[("물리 ", {"bold": True, "color": INK}), ("✔" if p["ok"] else "⚠", {"bold": True, "color": "2F8A4F" if p["ok"] else HANDC}),
                 (f"  {ENGINE.get(p['engine'], p['engine'])}", {"color": MUTED, "size": 10})]]
        rows += [[(f"{a}  ", {"color": MUTED, "size": 10}), (b, {"bold": True, "size": 11})] for a, b in p["items"][:4]]
        rows += [[(p["verdict"], {"size": 10.5})]]
        sz = fit_size(rows, W - 0.6 - px - 0.3, ph - 0.14, 11)
        text(s, px + 0.15, 1.12, W - 0.6 - px - 0.3, ph - 0.14, scaled(rows, 11, sz), size=sz, space=3)
        if rendered:
            text(s, 0.6, 1.05 + ph + 0.02, pw, 0.25, "Blender Cycles 경로 추적 렌더 — 물리 엔진 · 계산값으로 움직임 (sim/blender_bench.py)",
                 size=9, color=MUTED)
        y = 1.05 + ph + 0.3
        box(s, 0.6, y, 7.45, H - y - 0.35, PAPER, name="할 일")
        text(s, 0.82, y + 0.12, 7.05, H - y - 0.55, [[("할 일  ", {"bold": True, "color": HANDC if hand else MACHC}),
                                                      (st.action, {})]], size=16, anchor=MSO_ANCHOR.MIDDLE)
        box(s, 8.25, y, W - 8.85, H - y - 0.35, ICE, name="넘어가는 조건")
        text(s, 8.47, y + 0.12, W - 9.29, H - y - 0.55, [[("넘어가는 조건  ", {"bold": True, "color": INK}),
                                                          (st.check, {})]], size=16, anchor=MSO_ANCHOR.MIDDLE)
        s.notes_slide.notes_text_frame.text = (f"장비: {' · '.join(st.equipment)}\n할 일: {st.action}\n넘어가는 조건: {st.check}\n"
                                               f"물리 ({p['engine']}): " + " · ".join(f"{a} {b}" for a, b in p["items"]) + f"\n→ {p['verdict']}")

    # 마지막 — 판정
    s = new()
    bg(s, INK)
    text(s, 0.7, 0.55, W - 1.4, 0.7, "측정 뒤 무엇을 보나 — 미리 정한 판정 기준", size=30, color=WHITE, bold=True)
    crit = [("E1", "빈 세포에 에너지", "벽 / 칸 Cl 신호 비 10배 이상"), ("E2", "위아래 대칭", "윗면–아랫면 |V| < 50 mV (예측 약 2 mV)"),
            ("S1", "세포와 막", "닫힌 칸, 칸 폭 50–500 µm"), ("S4", "동결이 막을 안 깸", "1회 → 3회 사이 E1 비가 절반 아래로 안 떨어짐")]
    for i, (code, what, rule) in enumerate(crit):
        x, y = 0.7 + (i % 2) * 6.1, 1.65 + (i // 2) * 2.05
        box(s, x, y, 5.85, 1.8, "1F4466", name=f"기준 {code}")
        text(s, x + 0.3, y + 0.22, 1.2, 0.8, code, size=36, color="9EC3E6", bold=True)
        text(s, x + 1.55, y + 0.25, 4.1, 0.5, what, size=20, color=WHITE, bold=True)
        text(s, x + 1.55, y + 0.85, 4.1, 0.8, rule, size=15, color="D5E3F0")
    text(s, 0.7, 6.0, W - 1.4, 1.0, "기준은 측정 전에 정한 것이라 결과를 보고 바꾸지 않습니다. 전체 기준(E1–E3, S1–S4)과 기록 칸은 "
         "인쇄용 기록지 report/report.pdf 와 EXPERIMENT_PROTOCOL.md 에 있습니다.", size=14, color="B9CCDF")

    prs.save(OUT)
    print(f"{OUT} — 슬라이드 {len(prs.slides)}장")


if __name__ == "__main__":
    if "--no-shots" not in sys.argv:
        shoot()
    if "--render" in sys.argv:
        render_physics()
    build()
    import shutil

    shutil.copy2(OUT, ROOT / "report.pptx")  # 프로젝트 맨 위의 발표 자료도 같은 것으로
    print(f"복사: {ROOT / 'report.pptx'}")
