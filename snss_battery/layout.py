"""공간 배치 — 기계가 통째로 물에 잠겨도 출력 공간과 작업 공간이 늘 비어 있음을 계산으로 보장 (명세: spec/SCULPTOR.md §1).

구조: CoreXY 갠트리는 맨 위 일정한 높이에 고정, 배양 받침(바닥)이 나일론 나사봉 3개를 타고 층마다 내려감.
그래서 펜 끝 높이(z_tip)는 늘 같고, 그 아래 출력 공간 · 받침 기둥과 위쪽 손 · 수확 통로가 비어 있어야 한다.

좌표: 프레임 바닥 가운데 = 원점 (mm), Z 위. 부품은 축에 나란한 상자로 다룬다 (원기둥은 감싸는 상자 — 보수적).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .printer import SculptorSpec


@dataclass(frozen=True)
class Box:
    name: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    kind: str  # frame · static · gantry · bed · zone
    shape: str = "box"  # box · cyl_z (Blender 표시)

    def gap(self, o: "Box") -> float:
        """두 상자 사이 틈 (mm). 음수면 그만큼 겹침."""
        seps = [max(o.lo[i] - self.hi[i], self.lo[i] - o.hi[i]) for i in range(3)]
        return max(seps)


def _cyl(name, x, y, r, z0, z1, kind="static"):
    return Box(name, (x - r, y - r, z0), (x + r, y + r, z1), kind, "cyl_z")


@dataclass
class Layout:
    spec: SculptorSpec
    z_tip: float  # 펜 끝 높이 (고정)
    gz: float  # 갠트리 높이 (고정)
    bed_bottom_min: float  # 받침이 가장 내려갔을 때 바닥
    travel: tuple[float, float]  # 펜 XY 이동 반폭
    park: tuple[float, float]  # 주차 (펜 XY)
    boxes: list[Box] = field(default_factory=list)
    zones: list[Box] = field(default_factory=list)

    # ---------- 점검 ----------
    def problems(self) -> list[str]:
        bad = []
        frame_static = [b for b in self.boxes if b.kind in ("frame", "static")]
        for z in self.zones:
            for b in frame_static:
                g = z.gap(b)
                if g < 2.0:
                    bad.append(f"{z.name} ↔ {b.name}: {'겹침 ' + format(-g, '.1f') if g < 0 else '틈 ' + format(g, '.1f')} mm (2 mm 이상 필요)")
        hand = next(z for z in self.zones if z.name.startswith("손"))
        for b in self.parked():
            if hand.gap(b) < 2.0:
                bad.append(f"주차한 {b.name} 이(가) 손 · 수확 통로를 막음")
        # 움직이는 갠트리 ↔ 고정 부품
        for g in (b for b in self.boxes if b.kind == "gantry"):
            for b in frame_static:
                if b.kind == "frame" and b.name.startswith("탄소섬유 봉 (가로, 위"):
                    if g.gap(b) < 2.0:
                        bad.append(f"{g.name} ↔ {b.name}: 갠트리가 프레임 위 봉에 닿음")
                elif b.kind == "static" and g.gap(b) < 2.0:
                    bad.append(f"{g.name} ↔ {b.name}: {g.gap(b):.1f} mm")
        sp = self.spec
        if self.travel[0] < sp.build_mm[0] / 2 or self.travel[1] < sp.build_mm[1] / 2:
            bad.append("펜 XY 이동이 출력 공간을 다 덮지 못함")
        if self.bed_bottom_min < 2.0:
            bad.append(f"받침이 프레임 바닥까지 내려감 (여유 {self.bed_bottom_min:.1f} mm)")
        if sp.tank.fill_mm < sp.frame_mm[2] + 10:
            bad.append("기계 위로 배지가 10 mm 넘게 덮지 않음")
        return bad

    def parked(self) -> list[Box]:
        """주차 위치(펜 뒤쪽 구석)에 있을 때 움직이는 갠트리 부품."""
        px, py = self.park
        gz = self.gz
        return [Box("캐리지 (주차)", (px - 35, py - 31, gz - 21), (px + 35, py + 31, gz + 9), "gantry"),
                Box("X 빔 (주차)", (-101, py - 12, gz - 12), (101, py + 12, gz + 12), "gantry"),
                Box("펜 (주차)", (px - 11, py - 11, self.z_tip), (px + 11, py + 11, gz - 21), "gantry")]

    def clearances(self) -> list[tuple[str, str, float]]:
        out = []
        frame_static = [b for b in self.boxes if b.kind in ("frame", "static")]
        for z in self.zones:
            b = min(frame_static, key=z.gap)
            out.append((z.name, b.name, z.gap(b)))
        return out

    def describe(self) -> str:
        sp = self.spec
        lines = [f"[공간 배치 — 기계가 통째로 잠겨도 비어 있어야 할 곳] 프레임 {sp.frame_mm[0]:g}×{sp.frame_mm[1]:g}×{sp.frame_mm[2]:g} · "
                 f"배지 {sp.tank.fill_mm:g} mm",
                 f"  고정 갠트리 높이 {self.gz:g} mm · 펜 끝 {self.z_tip:g} mm (늘 같음) · 받침은 층마다 내려감 "
                 f"(가장 낮을 때 바닥 {self.bed_bottom_min:g} mm)",
                 f"  펜 XY 이동 ±{self.travel[0]:g} × ±{self.travel[1]:g} mm · 주차 ({self.park[0]:g}, {self.park[1]:g})"]
        for zone, nearest, gap in self.clearances():
            lines.append(f"  {zone:<28} 가장 가까운 고정 부품: {nearest} — 틈 {gap:.1f} mm")
        bad = self.problems()
        lines.append("  공간 점검: " + ("통과 — 출력 · 작업 · 수확 공간이 모두 비어 있음" if not bad else "; ".join(bad)))
        return "\n".join(lines)

    def to_json(self) -> dict:
        def j(b):
            return {"name": b.name, "lo": b.lo, "hi": b.hi, "kind": b.kind, "shape": b.shape}

        return {"z_tip": self.z_tip, "gz": self.gz, "park": self.park, "travel": self.travel,
                "boxes": [j(b) for b in self.boxes], "zones": [j(z) for z in self.zones], "problems": self.problems()}


PEN_STACK = 125.0  # 펜 끝 → 갠트리: 바늘 40 + 몸체 70 + 마운트 15
PLATE = 6.0  # 배양 받침 두께
BED_CARRIAGE = 10.0  # 받침 아래 나사봉 너트 판


def make_layout(spec: SculptorSpec | None = None) -> Layout:
    sp = spec or SculptorSpec()
    FX, FY, FZ = sp.frame_mm
    bx, by, bz = (v / 2 for v in sp.build_mm[:2]) + (sp.build_mm[2],) if False else (sp.build_mm[0] / 2, sp.build_mm[1] / 2, sp.build_mm[2])
    h = FX / 2 - 18  # 세로 봉 중심
    bed_bottom_min = 2.0
    z_tip = bed_bottom_min + BED_CARRIAGE + PLATE + bz
    gz = z_tip + PEN_STACK
    travel = (bx + 15, FY / 2 - 18 - 36 - 16 - 31 + 10)  # X: 출력 + 15 · Y: X 봉 끝단·캐리지 여유 안
    park = (travel[0], travel[1])
    boxes: list[Box] = []
    # 프레임: PETG 꼭짓점 8 · 탄소섬유 봉 12 (금속 없음)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for zc, lab in ((18, "아래"), (FZ - 18, "위")):
                boxes.append(Box(f"꼭짓점 ({lab})", (sx * h - 18, sy * h - 18, zc - 18), (sx * h + 18, sy * h + 18, zc + 18), "frame"))
            boxes.append(_cyl("탄소섬유 봉 (세로)", sx * h, sy * h, 4, 0, FZ, "frame"))
    for zc, lab in ((26, "아래"), (FZ - 26, "위")):
        for s in (-1, 1):
            boxes.append(Box(f"탄소섬유 봉 (가로, {lab}, X)", (-h, s * h - 4, zc - 4), (h, s * h + 4, zc + 4), "frame"))
            boxes.append(Box(f"탄소섬유 봉 (가로, {lab}, Y)", (s * h - 4, -h, zc - 4), (s * h + 4, h, zc + 4), "frame"))
    # Z: 나일론 나사봉 3 + 모터 방수 통 (바닥) — 받침 기둥 밖
    z_screw_top = z_tip - PLATE - BED_CARRIAGE + 8
    for x, y in ((95, -95), (95, 95), (-95, -95)):
        boxes.append(_cyl("Z 나일론 나사봉", x, y, 4, 0, z_screw_top))
        boxes.append(_cyl("Z 모터 방수 통", x, y, 28, 0, 46))
    # 원료 펌프 3 (왼쪽 벽, 세로: 방수 통 아래 · 주사기 위)
    for i, (y, lab) in enumerate(((-20, "GO"), (40, "SNSS"), (100, "PVA"))):
        boxes.append(_cyl(f"원료 펌프 방수 통 {lab}", -118, y, 28, 0, 46))
        boxes.append(_cyl(f"원료 주사기 {lab}", -118, y, 11, 46, 156))
    # 전자 방수 통 (오른쪽 벽) · 전극 (뒤 왼쪽 구석) · 방수 케이블 (프레임 밖)
    boxes.append(Box("전자 방수 통", (93, -60, 0), (143, 60, 90), "static"))
    boxes.append(Box("배지 전도도 · 누설 전극", (-133, 132, 60), (-127, 141, 100), "static"))
    boxes.append(Box("방수 케이블", (152, -8, 0), (160, 8, sp.tank.fill_mm + 20), "static"))
    # 고정 갠트리 (위): Y 레일 · XY 모터 방수 통 — 움직이는 것은 쓸고 지나가는 범위로
    for s in (-1, 1):
        boxes.append(Box("Y 레일 (탄소섬유)", (s * 121 - 4, -127, gz - 4), (s * 121 + 4, 127, gz + 4), "gantry"))
        boxes.append(_cyl("XY 모터 방수 통", s * 121, 121, 28, gz - 58, gz - 12, "gantry"))
        boxes.append(Box("X 봉 끝단 (쓸림)", (s * 121 - 20, -127, gz - 15), (s * 121 + 20, 127, gz + 15), "gantry"))
    boxes.append(Box("X 빔 · 캐리지 (쓸림)", (-101, -travel[1] - 31, gz - 21), (101, travel[1] + 31, gz + 12), "gantry"))
    # 배양 받침 (Z 로 오르내림)
    boxes.append(Box("배양 받침 기둥 (쓸림)", (-60, -60, bed_bottom_min), (60, 60, z_tip), "bed"))
    # 비어 있어야 할 곳
    zones = [
        Box("출력 공간", (-bx, -by, z_tip - bz), (bx, by, z_tip), "zone"),
        Box("펜 작업 공간 (출력 중)", (-bx - 16, -by - 16, z_tip - bz), (bx + 16, by + 16, gz - 21), "zone"),
        Box("펜 이동 공간 (끝 높이 위)", (-travel[0] - 16, -travel[1] - 16, z_tip), (travel[0] + 16, travel[1] + 16, gz - 21), "zone"),
        Box("배양 받침 기둥", (-62, -62, bed_bottom_min), (62, 62, z_tip), "zone"),
        Box("손 · 수확 통로 (주차 때)", (-70, -70, z_tip - bz - PLATE), (70, 70, sp.tank.inner_mm[2]), "zone"),
    ]
    return Layout(sp, z_tip, gz, bed_bottom_min, travel, park, boxes, zones)
