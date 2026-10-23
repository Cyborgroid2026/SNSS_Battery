"""B-rep 기본형 — snss_battery/parts.py 의 SDF 기본형(box · cyl · capsule · sphere · union · cut)과 같은 뜻.

SDF 의 둥근 상자 box(c, size, r) 는 '크기 size 인 상자의 모든 모서리를 반지름 r 로 둥글린 것' 과 같다 → makeFillet.
모든 치수 mm, 축 0 = X · 1 = Y · 2 = Z.
"""

from __future__ import annotations

import math

import FreeCAD as App
import Part

V = App.Vector
AX = {0: V(1, 0, 0), 1: V(0, 1, 0), 2: V(0, 0, 1)}


def box(c, size, r=0.0):
    sx, sy, sz = (float(s) for s in size)
    b = Part.makeBox(sx, sy, sz, V(c[0] - sx / 2, c[1] - sy / 2, c[2] - sz / 2))
    r = min(float(r), 0.49 * min(sx, sy, sz))
    if r > 0.05:
        b = b.makeFillet(r, b.Edges)
    return b


def box_lohi(lo, hi):
    return Part.makeBox(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], V(*lo))


def cyl(c, r, h, axis=2):
    d = AX[axis]
    return Part.makeCylinder(float(r), float(h), V(*c) - d * (h / 2), d)


def cyl_ab(a, b, r):
    a, b = V(*a), V(*b)
    return Part.makeCylinder(float(r), (b - a).Length, a, b - a)


def sphere(c, r):
    return Part.makeSphere(float(r), V(*c))


def capsule(a, b, r):
    return union(cyl_ab(a, b, r), sphere(a, r), sphere(b, r))


def ellipsoid(c, r):
    """반지름 (rx, ry, rz) 타원체 — 구를 축마다 늘림 (B-spline 고체)."""
    s = Part.makeSphere(1.0)
    m = App.Matrix()
    m.scale(V(*r))
    m.move(V(*c))
    return s.transformGeometry(m)


def union(*shapes):
    shapes = [s for s in shapes if s is not None]
    if len(shapes) == 1:
        return shapes[0]
    return shapes[0].fuse(shapes[1:]).removeSplitter()


def cut(a, *tools):
    tools = [t for t in tools if t is not None]
    if not tools:
        return a
    return a.cut(tools).removeSplitter()


def ring(c, r_out, r_in, h, axis=2):
    return cut(cyl(c, r_out, h, axis), cyl(c, r_in, h + 1, axis))


def polar(n, radius, z, start=0.0):
    return [(radius * math.cos(start + k * 2 * math.pi / n), radius * math.sin(start + k * 2 * math.pi / n), z) for k in range(n)]


def twisted_ribbon(z0, length, width, thick, a0, a1, sections=13):
    """z0 에서 length 만큼 올라가며 a0 → a1 로 비틀린 띠 (Kenics 혼합 요소)."""
    wires = []
    for i in range(sections):
        t = i / (sections - 1)
        a = a0 + (a1 - a0) * t
        ca, sa = math.cos(a), math.sin(a)
        z = z0 + length * t
        pts = [V(x * ca - y * sa, x * sa + y * ca, z) for x, y in
               ((-width / 2, -thick / 2), (width / 2, -thick / 2), (width / 2, thick / 2), (-width / 2, thick / 2))]
        wires.append(Part.makePolygon(pts + [pts[0]]))
    return Part.makeLoft(wires, True, False)
