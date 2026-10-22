"""격자 → 삼각형 면, 삼각형 면 → 격자 (외부 라이브러리 없이 numpy 만).

- surface_nets: 부호 있는 장(음수 = 안) 의 0 등위면을 닫힌 삼각형 망으로 (Gibson 1998 표면망)
- voxelize: 닫힌 STL 을 Z 방향 광선 홀짝으로 채움 (Blender 에서 보낸 모양을 슬라이서에 넣을 때)
- STL 읽기·쓰기
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

# 정육면체 꼭짓점 (dx,dy,dz) 와 모서리 12개
_CORNERS = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]])
_EDGES = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]


def surface_nets(field: np.ndarray, spacing, origin=(0.0, 0.0, 0.0)) -> tuple[np.ndarray, np.ndarray]:
    """field[i,j,k] 의 0 등위면 → (꼭짓점 V×3, 삼각형 F×3). 바깥 법선. 장 둘레는 바깥(양수)으로 채워 닫힘 보장."""
    f = np.pad(np.asarray(field, dtype=np.float32), 1, constant_values=1.0)
    sp = np.asarray(spacing, dtype=float)
    org = np.asarray(origin, dtype=float) - sp
    inside = f < 0
    nx, ny, nz = f.shape
    # 칸(정육면체) 마다 꼭짓점 8개 값
    c = [f[dx:nx - 1 + dx, dy:ny - 1 + dy, dz:nz - 1 + dz] for dx, dy, dz in _CORNERS]
    s = [ci < 0 for ci in c]
    count = sum(s[i].astype(np.int8) for i in range(8))
    active = (count > 0) & (count < 8)
    idx = np.full(active.shape, -1, dtype=np.int64)
    ai = np.nonzero(active)
    idx[ai] = np.arange(len(ai[0]))
    # 꼭짓점 = 부호가 바뀌는 모서리 교점들의 평균
    acc = np.zeros((len(ai[0]), 3))
    n = np.zeros(len(ai[0]))
    for a, b in _EDGES:
        va, vb = c[a][ai], c[b][ai]
        m = (va < 0) != (vb < 0)
        t = np.where(m, va / np.where(m, va - vb, 1.0), 0.0)
        p = _CORNERS[a] + t[:, None] * (_CORNERS[b] - _CORNERS[a])
        acc += p * m[:, None]
        n += m
    local = acc / n[:, None]
    verts = (np.stack(ai, axis=1) + local) * sp + org
    # 면: 부호가 바뀌는 격자 모서리마다 그 모서리를 둘러싼 칸 4개로 사각형
    quads = []
    for axis in range(3):
        sl0 = [slice(0, -1) if d == axis else slice(None) for d in range(3)]
        sl1 = [slice(1, None) if d == axis else slice(None) for d in range(3)]
        a_in, b_in = inside[tuple(sl0)], inside[tuple(sl1)]
        cross = a_in != b_in
        u, v = [d for d in range(3) if d != axis]
        # 둘레 모서리는 이웃 칸이 없음
        valid = np.zeros_like(cross)
        sel = [slice(None)] * 3
        sel[u] = slice(1, None)
        sel[v] = slice(1, None)
        valid[tuple(sel)] = True
        lim = list(cross.shape)
        cross &= valid
        e = np.nonzero(cross)
        if not len(e[0]):
            continue
        base = np.stack(e, axis=1)
        cells = []
        for du, dv in ((0, 0), (-1, 0), (-1, -1), (0, -1)):
            q = base.copy()
            q[:, u] += du
            q[:, v] += dv
            q[:, axis] = np.minimum(q[:, axis], lim[axis] - 1)
            cells.append(idx[q[:, 0], q[:, 1], q[:, 2]])
        quad = np.stack(cells, axis=1)
        flip = a_in[e]  # 안 → 밖 이 +axis 방향이면 그대로
        if (u, v) == (0, 2):  # 오른손 순서 (u,v,axis) 맞춤
            flip = ~flip
        quad[flip] = quad[flip][:, ::-1]
        quads.append(quad)
    if not quads:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    q = np.concatenate(quads)
    tris = np.concatenate([q[:, [0, 2, 1]], q[:, [0, 3, 2]]])
    return verts, tris


def signed_volume(verts: np.ndarray, tris: np.ndarray) -> float:
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)


def is_closed(tris: np.ndarray) -> bool:
    """모든 모서리가 정확히 두 삼각형에 (반대 방향으로) 쓰이면 닫힌 다양체."""
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    fwd = {tuple(x) for x in e.tolist()}
    return len(fwd) == len(e) and all((b, a) in fwd for a, b in fwd)


def write_stl(path: str | Path, verts: np.ndarray, tris: np.ndarray, header: str = "SNSS QFP-1") -> Path:
    path = Path(path)
    t = verts[tris].astype(np.float32)
    nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = nrm, t
    with open(path, "wb") as fp:
        fp.write(header.encode()[:80].ljust(80, b" "))
        fp.write(struct.pack("<I", len(t)))
        fp.write(rec.tobytes())
    return path


def read_stl(path: str | Path) -> np.ndarray:
    """삼각형 (T×3×3) — 이진·ASCII 모두."""
    data = Path(path).read_bytes()
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            rec = np.frombuffer(data, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")], count=n, offset=84)
            return rec["v"].astype(float)
    nums = [float(x) for line in data.decode(errors="ignore").splitlines()
            if line.strip().startswith("vertex") for x in line.split()[1:4]]
    return np.array(nums).reshape(-1, 3, 3)


def voxelize(tris: np.ndarray, xs: np.ndarray, ys: np.ndarray, zs: np.ndarray) -> np.ndarray:
    """닫힌 삼각형 망의 안쪽 → bool[x,y,z]. 칸 중심에서 +Z 광선을 쏘아 교차 홀짝으로 판정."""
    inside = np.zeros((len(xs), len(ys), len(zs)), dtype=bool)
    hits: dict[tuple[int, int], list[float]] = {}
    x0, dx = xs[0], xs[1] - xs[0]
    y0, dy = ys[0], ys[1] - ys[0]
    ex, ey = dx * 1.234567e-6, dy * 2.718281e-6  # 광선이 모서리·꼭짓점을 정확히 지나지 않도록 살짝 비킴
    for a, b, c in tris:
        lo = np.minimum(np.minimum(a, b), c)
        hi = np.maximum(np.maximum(a, b), c)
        i0, i1 = int(np.ceil((lo[0] - x0) / dx)), int(np.floor((hi[0] - x0) / dx))
        j0, j1 = int(np.ceil((lo[1] - y0) / dy)), int(np.floor((hi[1] - y0) / dy))
        if i1 < i0 or j1 < j0:
            continue
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1, len(xs) - 1), min(j1, len(ys) - 1)
        if i1 < i0 or j1 < j0:
            continue
        gx, gy = np.meshgrid(xs[i0:i1 + 1] + ex, ys[j0:j1 + 1] + ey, indexing="ij")
        # 무게중심 좌표 (XY 투영)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-14:
            continue
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / d
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / d
        l3 = 1 - l1 - l2
        m = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        z = l1 * a[2] + l2 * b[2] + l3 * c[2]
        for ii, jj in zip(*np.nonzero(m)):
            hits.setdefault((i0 + ii, j0 + jj), []).append(float(z[ii, jj]))
    for (i, j), zl in hits.items():
        if len(zl) % 2:
            continue  # 열린 망이거나 수치 문제 — 그 기둥은 비움
        zl = np.sort(zl)
        for k in range(0, len(zl) - 1, 2):
            inside[i, j] |= (zs > zl[k]) & (zs < zl[k + 1])
    return inside
