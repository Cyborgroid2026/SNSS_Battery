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
        # 세 원료가 펜 끝에서 섞이면 모두 굳고, 식염수 수조 속에서 출력 높이보다 높이 서야 함
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


class CompatibilityTest(unittest.TestCase):
    """아날로그 · 디지털 · 양자 공학기기 호환."""

    def test_all_three_domains_have_ports(self):
        from snss_battery.interfaces import ANALOG, DIGITAL, PORTS, QUANTUM

        doms = {p.domain for p in PORTS}
        self.assertEqual(doms, {ANALOG, DIGITAL, QUANTUM})

    def test_analog_scaling(self):
        from snss_battery.interfaces import ma_to_value, value_to_ma, volts_to_share

        self.assertEqual(volts_to_share(5.0), 0.5)
        self.assertEqual(volts_to_share(12.0), 1.0)
        self.assertAlmostEqual(ma_to_value(value_to_ma(60.0, 0, 100), 0, 100), 60.0)
        with self.assertRaises(ValueError):
            ma_to_value(1.0, 0, 100)  # 선 끊김

    def test_scpi_drives_gcode(self):
        from snss_battery.interfaces import Scpi

        s = Scpi(measure=lambda w: 0.42)
        self.assertIn("SC-1", s.send("*IDN?")[1])
        g, _ = s.send("MIX:RAT 0.5,0.4,0.1,p,1")
        self.assertEqual(g, ["MIX GO=0.500 SNSS=0.400 PVA=0.100 VARIANT=p LIGHT=1"])
        self.assertEqual(s.send("MIX:RAT?")[1], "0.500,0.400,0.100,p,1")
        self.assertEqual(s.send("CARV ON")[0], ["CARVE ON=1"])
        self.assertEqual(s.send("MEAS:CQ?")[1], "0.42")
        with self.assertRaises(ValueError):
            s.send("MIX:RAT 0.5,0.5,0.5")

    def test_quantum_cv_inversion_and_feedback(self):
        from snss_battery.interfaces import doping_feedback, fit_carrier

        e = np.linspace(-0.4, 0.4, 21)
        c = QuantumElectrode("PEI", 7.0).c_total(e) * 100
        r = fit_carrier(list(zip(e, c)), "PEI")
        self.assertAlmostEqual(r["carrier_1e12"], 7.0, delta=0.05)
        self.assertLess(doping_feedback(r["carrier_1e12"], 5.0, 0.5), 0.5)  # 너무 많이 도핑 → 몫을 줄임

    def test_qrng_seed_from_file(self):
        import tempfile

        from snss_battery.interfaces import qrng_seed

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(bytes(range(16)))
        seed, src = qrng_seed(f.name)
        self.assertEqual(seed, int.from_bytes(bytes(range(8)), "big"))
        self.assertIn("양자 난수", src)

    def test_gcode_emits_triggers(self):
        import tempfile
        from pathlib import Path

        spec = SculptorSpec()
        job = S.job_new(S.design("coupon", 4.0, S.CellParams(), spec, "t"), spec)
        with tempfile.TemporaryDirectory() as d:
            g = S.write_gcode(job, S.plan_passes(job, spec), spec, Path(d) / "j.gcode").read_text(encoding="utf-8")
        self.assertIn("TRIG EVENT=add", g)
        self.assertIn("[gcode_macro TRIG]", klipper_cfg(spec))


class PrintedPartsTest(unittest.TestCase):
    """기계 부품은 출력, 원료는 시중 구매."""

    def test_parts_fit_common_printer(self):
        from snss_battery.parts import printed_parts

        parts = printed_parts()
        self.assertGreaterEqual(len(parts), 10)
        for p in parts:
            self.assertTrue(p.fits(), p.name)

    def test_part_meshes_have_volume(self):
        from snss_battery.parts import ROD, mesh_part, printed_parts

        corner = next(p for p in printed_parts() if p.key == "corner")
        v, t, vol = mesh_part(corner)
        self.assertTrue(is_closed(t))
        # 36 mm 정육면체 − 봉 구멍 3개 − 모서리 둥글림(r 3) 12개
        analytic = 36 ** 3 - 3 * math.pi * (ROD / 2) ** 2 * 36 - 12 * (1 - math.pi / 4) * 9 * 30
        self.assertAlmostEqual(vol * 1000 / analytic, 1.0, delta=0.03)
        for p in printed_parts():
            if p.key in ("port_panel", "pinch_valve"):
                self.assertTrue(is_closed(mesh_part(p)[1]), p.name)

    def test_feedstock_is_bought(self):
        from snss_battery.printer import bom

        raw = {b.part: b.where for b in bom() if b.group == "원료"}
        self.assertTrue(any("약국" in w for w in raw.values()))  # 생리식염수
        self.assertTrue(all(w for w in raw.values()))  # 모두 구입처가 있음
        self.assertFalse(any("알루미늄" in b.part for b in bom()))  # 프레임은 출력 + 철물점 봉


class SalineTankTest(unittest.TestCase):
    """프린터 자체가 멸균생리식염수 수조 — 그 안에서 작업."""

    def setUp(self):
        self.spec = SculptorSpec()

    def test_neutral_buoyancy_holds_shape(self):
        for r in self.spec.recipes.values():
            g = self.spec.gel_check(r)
            self.assertLess(abs(g["drho"]), 5.0)  # 잉크 ≈ 식염수 밀도
            self.assertLess(g["free_height_air_mm"], 10.0)  # 공기 중이면 몇 mm 에서 무너짐
            self.assertGreater(g["free_height_mm"], self.spec.build_mm[2])  # 식염수 속에서는 출력 높이 이상
            self.assertTrue(g["bath_gels"])  # 수조 식염수가 겉을 엉기게 함

    def test_level_follows_the_work(self):
        p = S.design("seed", 20.0, S.CellParams(), self.spec, "씨앗")
        job = S.job_new(p, self.spec)
        plan = S.plan_passes(job, self.spec)
        start, doses, total = S.level_doses(job, plan, self.spec)
        tk = self.spec.tank
        self.assertAlmostEqual(start, tk.fill_ml(tk.margin_mm))
        printed_ml = sum(float(ps.segs[:, 4].sum()) for _, pp in plan for ps in pp if ps.kind == "add") \
            * self.spec.line_mm ** 2 * self.spec.layer_mm / 1000
        top = max(ps.z for _, pp in plan for ps in pp)
        final_level = (total + printed_ml) * 1000 / tk.area_mm2  # 부은 식염수 + 젤 = 면적 × 수위
        self.assertGreaterEqual(final_level, top + tk.margin_mm - tk.dose_every_mm - 1e-6)  # 늘 2 mm 이상 잠겨 있음
        self.assertLess(final_level, top + tk.margin_mm + 2 * tk.dose_every_mm + 0.5)

    def test_gcode_doses_saline_and_ends_in_tank(self):
        import tempfile
        from pathlib import Path

        job = S.job_new(S.design("coupon", 6.0, S.CellParams(), self.spec, "t"), self.spec)
        with tempfile.TemporaryDirectory() as d:
            g = S.write_gcode(job, S.plan_passes(job, self.spec), self.spec, Path(d) / "j.gcode").read_text(encoding="utf-8")
        self.assertIn("LEVEL ML=", g)
        self.assertIn("CHARGE ON=1", g)  # 다 빚으면 수조 안에서 그대로 충전할 수 있음
        self.assertIn("[gcode_macro LEVEL]", klipper_cfg(self.spec))

    def test_tank_is_bought_not_carbomer(self):
        from snss_battery.printer import bom

        items = " ".join(b.part + b.spec for b in bom())
        self.assertNotIn("카보머", items)
        self.assertTrue(any(b.group == "수조" and "마트" in b.where for b in bom()))
