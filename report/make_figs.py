"""report.md 그림 + 인쇄용 PDF 만들기 — 실험대 인쇄용 (흑백 인쇄에서도 읽히게 선 · 글자 위주).

    .venv/bin/python report/make_figs.py      # report/img/*.png → report/report.html → report/report.pdf (A4)

PDF 는 report.md 를 HTML 로 바꿔 Chrome(headless)으로 인쇄 (.venv 에 markdown 필요: .venv/bin/pip install markdown).

동결 진행 그림은 ./tools.sh fem-movie 가 만든 results/frames 를 씀 (A · 새 레시피 쪽 절반).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "report" / "img"
plt.rcParams.update({"font.family": "Noto Sans CJK JP", "font.size": 10, "savefig.dpi": 200})

ICE, BRINE, FOAM, PLATE = "#cfe3f5", "#a8c8e8", "#f3ecd9", "#9aa3ab"


def _box(ax, x, y, w, h, fc, ec="black", lw=1.0, **kw):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, **kw))


def _bottle(ax, x0, y0, w=72, body=150, fill=None, fc=BRINE, cap_loose=True):
    """500 mL 병 단면 (mm 축척). fill = 액면 높이."""
    _box(ax, x0, y0, w, body, "none", lw=1.4)
    if fill:
        _box(ax, x0 + 0.8, y0 + 0.8, w - 1.6, fill, fc, ec="none")
    sx = [x0, x0 + w / 2 - 14, x0 + w / 2 - 14]
    ax.plot([x0, x0 + w / 2 - 14, x0 + w / 2 - 14], [y0 + body, y0 + body + 25, y0 + body + 40], "k", lw=1.4)
    ax.plot([x0 + w, x0 + w / 2 + 14, x0 + w / 2 + 14], [y0 + body, y0 + body + 25, y0 + body + 40], "k", lw=1.4)
    lift = 4 if cap_loose else 0
    _box(ax, x0 + w / 2 - 16, y0 + body + 40 + lift, 32, 18, "#dddddd", lw=1.2)
    return sx


def fig_setup():
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    ax.set_xlim(-60, 200), ax.set_ylim(-45, 262), ax.set_aspect("equal"), ax.axis("off")
    _box(ax, -55, -40, 243, 300, "none", ec="#888888", lw=0.8, ls="--")
    ax.text(183, 250, "저온실 +4 °C", ha="right", color="#555555")
    _box(ax, -20, -30, 150, 14, "#666666")
    ax.text(55, -23, "순환식 냉각기 → 냉각판", ha="center", va="center", color="white", fontsize=9)
    _box(ax, -20, -16, 150, 12, PLATE)
    ax.text(-24, -10, "알루미늄 냉각판 −20 °C", ha="right", va="center")
    _box(ax, 18, -4, 76, 2.5, "#f4d35e", ec="none")
    ax.annotate("접촉액 (30 % 에탄올) 몇 mL", (90, -3), (140, -2), arrowprops=dict(arrowstyle="-", lw=0.8))
    _box(ax, -14, -1.5, 30, 230, FOAM), _box(ax, 96, -1.5, 30, 230, FOAM), _box(ax, -14, 228.5, 140, 14, FOAM)
    ax.text(1, 110, "스티로폼 3 cm", rotation=90, ha="center", va="center")
    ax.text(111, 110, "스티로폼 3 cm", rotation=90, ha="center", va="center")
    ax.text(56, 235.5, "윗면 단열", ha="center", va="center", fontsize=9)
    _bottle(ax, 20, 1, fill=128.5)
    ax.plot([21, 91], [129.5, 129.5], color="#1f5fa8", lw=1.2)
    ax.text(56, 136, "액면 = 어깨 아래", ha="center", fontsize=9, color="#1f5fa8")
    ax.text(42, 95, "겔 용액\n500 mL", ha="center", va="center")
    ax.annotate("", (78, 100), (78, 20), arrowprops=dict(arrowstyle="->", lw=2, color="#1f5fa8"))
    ax.text(74, 40, "얼음이\n아래 → 위", ha="right", fontsize=9, color="#1f5fa8")
    for y, lab in ((14, "열전대 1 (아래)"), (122, "열전대 2 (위) · 끝: < −3 °C")):
        ax.plot(92, y, "o", ms=6, mfc="#c0392b", mec="black")
        ax.annotate(lab, (92, y), (140, y + 14), arrowprops=dict(arrowstyle="-", lw=0.8))
    ax.annotate("뚜껑 반 바퀴 풀어 얹음", (72, 205), (140, 200), arrowprops=dict(arrowstyle="-", lw=0.8))
    ax.set_title("그림 1. 방향성 동결 세팅 (단계 11–12, 단면 · 대략 축척)", loc="left", fontsize=11)
    fig.savefig(IMG / "setup.png", bbox_inches="tight"), plt.close(fig)


def fig_freeze():
    fr = ROOT / "results" / "frames"
    times = json.loads((fr / "frames.json").read_text())["times_h"]
    pick = (0, 8, 16, 30, 44)
    fig, axs = plt.subplots(1, len(pick), figsize=(7.4, 2.9))
    for ax, k in zip(axs, pick):
        im = plt.imread(fr / f"freeze_{k:03d}.png")
        ax.imshow(im[70:580, 80:470]), ax.axis("off")
        ax.set_title(f"{times[k]:.0f} h", fontsize=10)
    fig.suptitle("그림 2. 동결 진행 — A · 새 레시피 (FEniCSx). 파랑 = 얼음, 빨간 선 = 얼음 전선. 약 22 h 에 다 얾",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(IMG / "freeze.png", bbox_inches="tight"), plt.close(fig)


def fig_measure():
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 3.9), gridspec_kw={"width_ratios": [1, 1.15]})
    for ax in (a, b):
        ax.set_aspect("equal"), ax.axis("off")
    # 왼쪽: E2 전압
    a.set_xlim(-30, 150), a.set_ylim(-40, 175)
    _box(a, 0, 0, 70.4, 128.5, ICE, lw=1.4)
    a.text(35, 64, "겔\nØ70 × 128 mm", ha="center", va="center", fontsize=9)
    for y0, y1, lab in ((128.5, 150, "윗면"), (0, -22, "아랫면")):
        _box(a, 31, min(y0, y1), 8, abs(y1 - y0), "#333333")
        a.text(44, (y0 + y1) / 2, f"흑연 막대 ({lab})", va="center", fontsize=8.5)
    a.plot([35, 35, 120, 120], [150, 162, 162, 92], "k", lw=1), a.plot([35, 35, 120, 120], [-22, -32, -32, 52], "k", lw=1)
    a.add_patch(FancyBboxPatch((103, 52), 34, 40, boxstyle="round,pad=2", fc="white", ec="black"))
    a.text(120, 78, "V", ha="center", fontsize=14, weight="bold"), a.text(120, 62, "DC mV", ha="center", fontsize=8)
    a.text(120, 40, "10 MΩ 이상", ha="center", fontsize=8)
    a.set_title("그림 3. 윗면–아랫면 전압 (단계 16, E2)\n정 3번 → 막대 바꿔 역 3번", loc="left", fontsize=10)
    # 오른쪽: 단면 채취
    b.set_xlim(-10, 170), b.set_ylim(-20, 175)
    _box(b, 0, 0, 70.4, 128.5, ICE, lw=1.4)
    b.plot([35.2, 35.2], [-6, 134], color="#c0392b", lw=1.4, ls="--")
    b.text(35.2, 140, "세로로 자름 (면도칼)", ha="center", fontsize=8.5, color="#c0392b")
    for y, lab in ((112, "위"), (62, "가운데"), (12, "아래")):
        _box(b, 38, y, 6, 6, "#333333")
        b.annotate(f"{lab} 2 mm 조각", (44, y + 3), (85, y + 3), va="center", fontsize=9,
                   arrowprops=dict(arrowstyle="->", lw=0.8))
    b.text(85, -12, "→ 액체질소 10초 → 동결건조 24 h\n→ SEM-EDS Cl 지도 (E1 · S1 · S2)", fontsize=8.5)
    b.set_title("그림 4. 단면 사진 · 조각 채취 (단계 17)\n사진은 자를 함께 찍음", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(IMG / "measure.png", bbox_inches="tight"), plt.close(fig)


CSS = """
@page { size: A4; margin: 14mm 13mm; }
body { font-family: 'Noto Sans CJK KR', 'Noto Sans CJK JP', sans-serif; font-size: 10pt; line-height: 1.45; color: #000; }
h1 { font-size: 17pt; margin: 0 0 6pt; }
h2 { font-size: 13pt; border-bottom: 1.5px solid #000; padding-bottom: 2pt; margin-top: 16pt; break-after: avoid; }
h3 { font-size: 11pt; margin: 12pt 0 3pt; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt; break-inside: avoid; }
th, td { border: 1px solid #555; padding: 4pt 5pt; vertical-align: top; } th { background: #eee; }
tr { height: 20pt; }
img { max-width: 100%; max-height: 88mm; display: block; margin: 4pt auto; }
p:has(img) { break-inside: avoid; break-after: avoid; }
blockquote { border-left: 3px solid #888; margin: 6pt 0; padding: 2pt 8pt; color: #333; }
hr { border: none; border-top: 1px solid #999; margin: 10pt 0; }
ul { margin: 2pt 0; padding-left: 16pt; } code { font-size: 9pt; }
"""


def pdf():
    import markdown

    body = markdown.markdown((ROOT / "report" / "report.md").read_text(encoding="utf-8"), extensions=["tables"])
    html = ROOT / "report" / "report.html"
    html.write_text(f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>SNSS 실험대 기록지</title>"
                    f"<style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
    subprocess.run(["google-chrome", "--headless=new", "--no-pdf-header-footer",
                    f"--print-to-pdf={ROOT / 'report' / 'report.pdf'}", html.as_uri()],
                   check=True, stderr=subprocess.DEVNULL)


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    fig_setup(), fig_freeze(), fig_measure()
    shutil.copy(ROOT / "web_out" / "cad" / "template_1to1.png", IMG / "cut_guide.png")
    pdf()
    print(*sorted(p.name for p in IMG.glob("*.png")), "→ report/report.pdf")


if __name__ == "__main__":
    main()
