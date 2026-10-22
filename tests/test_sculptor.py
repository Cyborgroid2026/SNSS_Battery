import math
import unittest

import numpy as np

from snss_battery.mesh import is_closed, read_stl, signed_volume, surface_nets, voxelize, write_stl
from snss_battery.printer import SculptorSpec, klipper_cfg
from snss_battery.qcap import QuantumCell, QuantumElectrode, cq_ideal, E, HBAR, V_F
from snss_battery import sculpt as S


class QuantumLayerTest(unittest.TestCase):
    def test_cq_low_temperature_limit(self):
        # T → 0: C_Q = 2e³|φ| / (π ħ² v_F²)
        phi = 0.3
        analytic = 2 * E ** 3 * phi / (math.pi * (HBAR * V_F) ** 2)
        self.assertAlmostEqual(float(cq_ideal(phi, 1.0)) / analytic, 1.0, places=6)

    def test_quantum_capacitance_limits_cell(self):
        cell = QuantumCell()
        self.assertLess(cell.c_area, cell.c_edl_series)  # 양자 커패시턴스가 직렬로 깎음
        self.assertGreater(cell.quantum_fraction, 0)

    def test_pn_doping_beats_symmetric(self):
        # 양극 p형 · 음극 n형 → 충전할 때 두 전극 다 디랙점에서 멀어짐
        x = 5.0
        sym = QuantumCell.symmetric(QuantumElectrode("PEI", x))
        pn = QuantumCell(QuantumElectrode("NBD", x), QuantumElectrode("PEI", x))
        self.assertGreater(pn.c_area, 1.5 * sym.c_area)
        self.assertGreater(pn.energy_area, sym.energy_area)

    def test_undoped_is_symmetric(self):
        c = QuantumCell.symmetric(QuantumElectrode("", 0.0))
        self.assertAlmostEqual(c.curve().e_pos[-1], c.u_max / 2, places=4)


class SculptorMachineTest(unittest.TestCase):
    def setUp(self):
        self.spec = SculptorSpec()

    def test_recipes_gel_at_pen_tip(self):
        # 세 원료가 펜 끝에서 섞이면 모두 굳고, 욕조보다 단단해야 함
        self.assertEqual(self.spec.check(), [])
        for r in self.spec.recipes.values():
            g = self.spec.gel_check(r)
            self.assertGreater(g["nacl_mm"], g["ccc_mm"])

    def test_premixed_saline_alone_does_not_gel(self):
        # PVA 가 많고 식염수가 적으면 CCC 를 못 넘어 굳지 않음 → 판정이 이를 잡아야 함
        from snss_battery.printer import Recipe

        r = Recipe("x", "식염수 적음", 0.5, 0.2, 0.3, "plain", False, "#000")
        self.assertFalse(self.spec.gel_check(r)["ok"])

    def test_room_temperature_only(self):
        cfg = klipper_cfg(self.spec)
        self.assertNotIn("cold_plate", cfg)
        self.assertNotIn("FREEZE", cfg)
        self.assertEqual(self.spec.chamber.temp_c, 25.0)
        for f in ("feed_go", "feed_snss", "feed_pva"):
            self.assertIn(f"[extruder_stepper {f}]", cfg)

    def test_mixer_does_not_clog(self):
        self.assertLess(self.spec.residence_s(), self.spec.pen.gel_time_s)


class MeshTest(unittest.TestCase):
    def test_surface_nets_sphere_closed_and_volume(self):
        h = 0.5
        x = np.arange(-12, 12.01, h)
        X, Y, Z = np.meshgrid(x, x, x, indexing="ij")
        v, t = surface_nets(np.sqrt(X ** 2 + Y ** 2 + Z ** 2) - 10, (h, h, h), (x[0],) * 3)
        self.assertTrue(is_closed(t))
        self.assertAlmostEqual(signed_volume(v, t) / (4 / 3 * math.pi * 1000), 1.0, delta=0.02)

    def test_stl_roundtrip_voxelize(self):
        import tempfile
        from pathlib import Path

        h = 0.5
        x = np.arange(-8, 8.01, h)
        X, Y, Z = np.meshgrid(x, x, x, indexing="ij")
        f = np.sqrt(X ** 2 + Y ** 2 + Z ** 2) - 6
        v, t = surface_nets(f, (h, h, h), (x[0],) * 3)
        with tempfile.TemporaryDirectory() as d:
            tri = read_stl(write_stl(Path(d) / "s.stl", v, t))
        inside = voxelize(tri, x, x, x)
        self.assertLess((inside != (f < 0)).sum(), 0.03 * (f < 0).sum())


class SculptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = SculptorSpec()
        cls.cp = S.CellParams(cell_mm=3.0)
        cls.p = S.design("seed", 30.0, cls.cp, cls.spec, "씨앗")

    def assertNoShort(self, mat):
        # p 세포질과 n 세포질이 맞닿는 칸이 없어야 함 (늘 막이 사이에 — 아니면 단락)
        for ax in range(3):
            a, b = np.moveaxis(mat, ax, 0)[:-1], np.moveaxis(mat, ax, 0)[1:]
            self.assertFalse((((a == S.POS) & (b == S.NEG)) | ((a == S.NEG) & (b == S.POS))).any())

    def test_quantum_cells_structure(self):
        p = self.p
        self.assertGreater(p.n_cells(), 100)
        mats = set(np.unique(p.material)) - {S.EMPTY}
        self.assertEqual(mats, {S.POS, S.NEG, S.MEM})
        self.assertNoShort(p.material)

    def test_feet_are_terminals(self):
        # 바닥: 왼쪽은 + 세포질만, 오른쪽은 − 세포질만 드러남
        bot = self.p.material[:, :, 0]
        ii = np.argwhere(bot != S.EMPTY)[:, 0]
        cx = ii.mean()
        left, right = bot[: int(cx) - 2], bot[int(cx) + 3:]
        self.assertFalse((left == S.NEG).any())
        self.assertFalse((right == S.POS).any())
        self.assertTrue((left == S.POS).any() and (right == S.NEG).any())

    def test_body_signs_wake_from_feet(self):
        pr = S.body_signs(self.p, self.spec)
        self.assertGreater(pr["energy_j"], 0)
        self.assertGreater(pr["awake_fraction"], 0.8)
        self.assertGreaterEqual(pr["wake_head_s"], 0.5 * pr["wake_median_s"])
        e = pr["series"]["energy_j"]
        self.assertTrue(all(b >= a - 1e-12 for a, b in zip(e, e[1:])))  # 충전 중 에너지는 줄지 않음

    def test_detach_then_attach_is_one_body(self):
        job = S.job_detach(self.p, 10.0, self.cp, self.spec)
        lower, upper = job.after
        self.assertEqual(job.ops[0].kind, "carve")
        joined = S.job_attach(lower, upper, self.spec)
        kinds = [o.kind for o in joined.ops]
        self.assertIn("pause", kinds)
        self.assertIn("heal", kinds)
        whole = joined.after[0]
        self.assertNoShort(whole.material)
        e0 = S.body_signs(self.p, self.spec)["energy_j"]
        e1 = S.body_signs(whole, self.spec)["energy_j"]
        self.assertAlmostEqual(e1 / e0, 1.0, delta=0.15)  # 다시 하나 — 에너지가 거의 그대로

    def test_add_layers_on_top(self):
        job = S.job_add(self.p, "bud", 10.0, self.cp, self.spec)
        after = job.after[0]
        self.assertNoShort(after.material)
        self.assertGreater(after.height_mm, self.p.height_mm + 5)
        self.assertGreater(after.n_cells(), self.p.n_cells())
        self.assertIn("add", [o.kind for o in job.ops])

    def test_strokes_touch_without_short(self):
        h = self.p.height_mm
        strokes = [{"material": "pos", "points": [[0, 0, h - 1], [3, 2, h + 6], [6, 4, h + 10]]},
                   {"material": "neg", "points": [[-4, 0, h - 2], [-8, 3, h + 5]]}]
        job = S.job_strokes(self.p, strokes, self.cp, self.spec)
        self.assertNoShort(job.after[0].material)
        self.assertIn("stroke", [o.kind for o in job.ops])

    def test_carve_reskins(self):
        h = self.p.height_mm
        job = S.job_carve(self.p, (0, -12, h / 2), 4.0, self.cp, self.spec)
        kinds = [o.kind for o in job.ops]
        self.assertEqual(kinds[:2], ["carve", "add"])  # 깎고 새 면에 피부

    def test_gcode_uses_three_feeds(self):
        import tempfile
        from pathlib import Path

        job = S.job_new(S.design("coupon", 6.0, self.cp, self.spec, "시험편"), self.spec)
        plan = S.plan_passes(job, self.spec)
        with tempfile.TemporaryDirectory() as d:
            g = S.write_gcode(job, plan, self.spec, Path(d) / "j.gcode").read_text(encoding="utf-8")
        self.assertIn("MIX GO=0.50 SNSS=0.40 PVA=0.10 VARIANT=p LIGHT=1", g)
        self.assertIn("VARIANT=n", g)
        self.assertIn("MIX GO=0.40 SNSS=0.45 PVA=0.15 VARIANT=plain LIGHT=0", g)
        self.assertIn("CURE S=", g)
        self.assertNotIn("FREEZE", g)


if __name__ == "__main__":
    unittest.main()
