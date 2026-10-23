"""SD / microSD 굽기 — 이 컴퓨터가 계산해 굽고, 수조 밑 양자 아날로그 데스크톱이 재생한다 (명세: spec/CANDY.md §4).

굽기(burn)는 과정(candy.Process)을 **아날로그 제어 전압(CV) 표**로 펼친다: 봉 각도 · 팔 r · 팔 z · 주사기 넷 · 빛 · 트리거.
데스크톱은 계산하지 않는다 — SD 를 읽어 그 전압을 양자 기준 시계(10 MHz → 1 PPS)에 맞춰 내보내고, 모니터에는 구워 둔 화면을 띄운다.
키보드 · 마우스로 단계 표시점(cue) 사이를 오가며 반복 · 건너뛰기를 하고, 고친 것은 SD 의 edits.json 에 적는다 → 이 컴퓨터가 읽어 다시 굽는다.

SD 구조 (FAT32, 맨 위 SNSS/):
  manifest.json   형식 · 이름 · 표본 빠르기 · 채널 눈금 · 단계 표시점 · 파일마다 CRC32
  program.cv      int16 LE, 채널 엮음 (표본 × 채널) — ±10 V = ±32767
  process.json    고칠 수 있는 원본 (candy.Process)
  monitors/       모니터 화면: step_NN.png (그 단계까지 자란 모습) · timeline.png
  edits.json      데스크톱이 적는 고친 기록 (처음엔 빈 목록)
"""

from __future__ import annotations

import json
import struct
import time
import zlib
from pathlib import Path

import numpy as np

from .candy import Process, strokes
from .sculpt import MEM, NEG, POS

FORMAT = "SNSS-SD 1"
RATE_HZ = 50.0
# (이름, 단위, 0 V 일 때 값, 10 V 일 때 값)
CHANNELS = (("theta", "도", 0.0, 180.0), ("r", "mm", 0.0, 80.0), ("z", "mm", 0.0, 350.0),
            ("go_p", "몫", 0.0, 1.0), ("go_n", "몫", 0.0, 1.0), ("go_mem", "몫", 0.0, 1.0), ("pva", "몫", 0.0, 1.0),
            ("light405", "켬", 0.0, 1.0), ("trig", "단계", 0.0, 1.0))


def _crc(b: bytes) -> str:
    return f"{zlib.crc32(b) & 0xFFFFFFFF:08x}"


def _cv(name: str, v: np.ndarray) -> np.ndarray:
    _, _, lo, hi = next(c for c in CHANNELS if c[0] == name)
    volts = np.clip((v - lo) / (hi - lo) * 10.0, -10, 10)
    return np.round(volts / 10.0 * 32767).astype(np.int16)


def program(pl: dict, proc: Process, rate: float = RATE_HZ) -> tuple[np.ndarray, list[dict]]:
    """과정 → (표본 × 채널 int16, 단계 표시점). 반복은 펼치고 건너뛴 단계는 뺌; 흐름 배율은 시간을 늘이거나 줄임."""
    st = strokes(pl)
    shell = pl["shell"]
    sp = pl["spec"]
    ratio = sp.syringes.ratio
    rows, cues, n0 = [], [], 0
    for seg in proc.timeline():
        s = proc.steps[seg["step"]]
        a, b = np.searchsorted(shell, s["shells"][0]), np.searchsorted(shell, s["shells"][1])
        n = max(1, int(round((seg["t1"] - seg["t0"]) * rate)))
        idx = np.minimum(a + (np.arange(n) * (b - a) / n).astype(int), max(a, b - 1))
        th, r, z, m = st[idx, 0], st[idx, 1], st[idx, 2], st[idx, 3].astype(int)
        go = np.array([ratio.get(k, (0, 0))[0] for k in range(4)])[m]
        pva = np.array([ratio.get(k, (0, 0))[1] for k in range(4)])[m]
        ch = {"theta": th, "r": r, "z": z, "go_p": np.where(m == POS, go, 0), "go_n": np.where(m == NEG, go, 0),
              "go_mem": np.where(m == MEM, go, 0), "pva": pva * seg["flow"], "light405": (m != MEM).astype(float),
              "trig": np.r_[1.0, np.zeros(n - 1)]}
        rows.append(np.stack([_cv(c[0], ch[c[0]]) for c in CHANNELS], 1))
        cues.append({"step": seg["step"], "pass": seg["pass"], "sample0": n0, "sample1": n0 + n, "t0": seg["t0"], "t1": seg["t1"],
                     "r_mm": s["r_mm"]})
        n0 += n
    return (np.concatenate(rows) if rows else np.zeros((0, len(CHANNELS)), np.int16)), cues


def _monitor_frames(pl: dict, proc: Process, folder: Path) -> list[str]:
    """모니터 화면 (구워 둠): 단계마다 그때까지 자란 모습 위 · 옆 — 데스크톱은 그리지 않고 띄우기만."""
    from PIL import Image, ImageDraw, ImageFont

    folder.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    xyz, shell = pl["xyz"], pl["shell"]
    zx, zy, zz = pl["zero_mm"]
    S, W = 4.0, 420  # px/mm
    files = []
    for s in proc.steps:
        n = np.searchsorted(shell, s["shells"][1])
        img = Image.new("RGB", (2 * W, W), (24, 24, 28))
        d = ImageDraw.Draw(img)
        for panel, (u, v) in enumerate(((0, 1), (0, 2))):  # 위 · 옆
            g = np.zeros((W, W), np.uint8)
            pu = np.clip(((xyz[:n, u] - (zx if u == 0 else zy)) * S + W / 2).astype(int), 0, W - 1)
            pv = np.clip((W / 2 - (xyz[:n, v] - (zy if v == 1 else zz)) * S).astype(int), 0, W - 1)
            g[pv, pu] = 1
            rgb = np.zeros((W, W, 3), np.uint8)
            rgb[g > 0] = (240, 150, 80)
            img.paste(Image.fromarray(rgb), (panel * W, 0), Image.fromarray((g * 255).astype(np.uint8)))
            d.ellipse((panel * W + W / 2 - 3, W / 2 - 3, panel * W + W / 2 + 3, W / 2 + 3), fill=(255, 80, 60))  # 영점
        d.text((8, 8), f"{proc.name} · 단계 {s['i']} · r {s['r_mm'][1]:.1f} mm · 위", fill=(255, 220, 120), font=font)
        d.text((W + 8, 8), "옆 (봉은 위로)", fill=(255, 220, 120), font=font)
        f = folder / f"step_{s['i']:02d}.png"
        img.save(f)
        files.append(f.name)
    tl = proc.timeline()
    img = Image.new("RGB", (2 * W, 80), (24, 24, 28))
    d = ImageDraw.Draw(img)
    T = max(1.0, proc.total_s())
    for seg in tl:
        x0, x1 = seg["t0"] / T * (2 * W - 20) + 10, seg["t1"] / T * (2 * W - 20) + 10
        d.rectangle((x0, 30, max(x0 + 1, x1 - 1), 60), fill=(80, 140, 220) if seg["pass"] == 1 else (220, 140, 60))
    d.text((10, 8), f"시간표 {T / 3600:.1f} h · 파랑 = 처음 · 주황 = 반복", fill=(230, 230, 230), font=font)
    img.save(folder / "timeline.png")
    return files + ["timeline.png"]


def burn(pl: dict, proc: Process, target: str | Path, card_gb: float = 8.0) -> dict:
    """굽기 — target 은 SD 가 꽂힌 자리 (예: /media/…/SNSS_SD) 또는 연습용 폴더. 그 아래 SNSS/ 를 새로 씀."""
    root = Path(target) / "SNSS"
    if root.exists() and not (root / "manifest.json").exists():
        raise RuntimeError(f"{root} 에 SNSS 가 아닌 것이 있습니다 — 지우지 않음")
    root.mkdir(parents=True, exist_ok=True)
    prog, cues = program(pl, proc)
    raw = prog.astype("<i2").tobytes()
    (root / "program.cv").write_bytes(raw)
    proc.save(root / "process.json")
    if not (root / "edits.json").exists():
        (root / "edits.json").write_text("[]", encoding="utf-8")
    mons = _monitor_frames(pl, proc, root / "monitors")
    files = {"program.cv": _crc(raw), "process.json": _crc((root / "process.json").read_bytes())}
    for m in mons:
        files[f"monitors/{m}"] = _crc((root / "monitors" / m).read_bytes())
    size = sum((root / f).stat().st_size for f in files)
    if size > card_gb * 1e9 * 0.9:
        raise RuntimeError(f"묶음 {size / 1e9:.1f} GB 가 SD {card_gb:g} GB 에 들어가지 않음")
    man = {"format": FORMAT, "name": proc.name, "burned": time.strftime("%Y-%m-%d %H:%M:%S"), "rate_hz": RATE_HZ,
           "channels": [{"name": c[0], "unit": c[1], "at_0V": c[2], "at_10V": c[3]} for c in CHANNELS],
           "samples": int(len(prog)), "seconds": round(len(prog) / RATE_HZ, 1), "cues": cues, "files": files, "bytes": size,
           "clock": "외부 10 MHz → 1 PPS (Q1 · Q2) 에 표본 시계 맞춤", "zero_mm": list(pl["zero_mm"]),
           "monitors": {"1": "monitors/step_NN.png (지금 단계)", "2": "monitors/timeline.png + 진행 막대", "3": "카메라 (수조 앞)",
                        "4": "아날로그 계측 (CV · 배지 전도도 · 누설)"}}
    (root / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"root": str(root), "samples": len(prog), "seconds": man["seconds"], "bytes": size, "cues": len(cues), "monitors": len(mons)}


def verify(target: str | Path) -> dict:
    """다시 읽기 — CRC · 표본 수 · 채널 수가 맞는지 (굽고 나서, 또 데스크톱에 꽂기 전에)."""
    root = Path(target) / "SNSS"
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    bad = [f for f, c in man["files"].items() if _crc((root / f).read_bytes()) != c]
    n = (root / "program.cv").stat().st_size // (2 * len(man["channels"]))
    if n != man["samples"]:
        bad.append(f"표본 수 {n} ≠ {man['samples']}")
    return {"ok": not bad, "bad": bad, "format": man["format"], "samples": n, "cues": len(man["cues"])}


def play(target: str | Path, keys: list[tuple] | None = None) -> dict:
    """양자 아날로그 데스크톱 흉내 — SD 를 읽어 단계 표시점대로 재생. keys: ("repeat", 단계) · ("skip", 단계) · ("flow", 단계, 배율).
    고친 것은 edits.json 에 적음 (이 컴퓨터가 `candy reburn` 으로 받아 다시 구움). 실제 전압은 계산하지 않고 표에서 읽기만."""
    root = Path(target) / "SNSS"
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    raw = np.frombuffer((root / "program.cv").read_bytes(), "<i2").reshape(-1, len(man["channels"]))
    names = [c["name"] for c in man["channels"]]
    log, played = [], 0
    keys = list(keys or [])
    edits = json.loads((root / "edits.json").read_text(encoding="utf-8"))
    for k in keys:
        edits.append({"key": k[0], "step": int(k[1]), **({"to": float(k[2])} if len(k) > 2 else {}), "at": time.strftime("%H:%M:%S")})
    for c in man["cues"]:
        seg = raw[c["sample0"]:c["sample1"]]
        rep = sum(1 for k in keys if k[0] == "repeat" and k[1] == c["step"])
        skip = any(k[0] == "skip" and k[1] == c["step"] for k in keys)
        if skip:
            log.append(f"단계 {c['step']} 건너뜀 (키보드)")
            continue
        for _ in range(1 + rep):
            played += len(seg)
        trig = int((seg[:, names.index("trig")] > 16000).sum())
        log.append(f"단계 {c['step']} (회 {c['pass']}) {len(seg)} 표본 · 트리거 {trig} · r {c['r_mm'][1]} mm" + (f" · 다시 {rep}" if rep else ""))
    (root / "edits.json").write_text(json.dumps(edits, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"played_samples": played, "seconds": round(played / man["rate_hz"], 1), "log": log, "edits": edits}


def reburn_edits(target: str | Path) -> Process:
    """데스크톱이 SD 에 적은 고친 것 → 과정에 반영 (그다음 burn 으로 다시 굽기)."""
    root = Path(target) / "SNSS"
    proc = Process.load(root / "process.json")
    for e in json.loads((root / "edits.json").read_text(encoding="utf-8")):
        if e["key"] == "repeat":
            proc.edit(e["step"], repeat=proc.steps[e["step"]]["repeat"] + 1)
        elif e["key"] == "skip":
            proc.edit(e["step"], skip=True)
        elif e["key"] == "flow":
            proc.edit(e["step"], flow=e["to"])
    (root / "edits.json").write_text("[]", encoding="utf-8")
    return proc


def header(target: str | Path) -> str:
    man = json.loads((Path(target) / "SNSS" / "manifest.json").read_text(encoding="utf-8"))
    return (f"{man['format']} · {man['name']} · {man['samples']} 표본 ({man['seconds'] / 3600:.2f} h @ {man['rate_hz']:g} Hz) · "
            f"채널 {len(man['channels'])} · 단계 표시점 {len(man['cues'])} · {man['bytes'] / 1e6:.1f} MB · 구움 {man['burned']}")


_ = struct  # (형식 문서용)
