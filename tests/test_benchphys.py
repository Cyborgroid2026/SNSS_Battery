import json
import math
import unittest

from snss_battery import benchphys as B
from snss_battery.process import process


class TestProperties(unittest.TestCase):
    def test_water_viscosity(self):
        self.assertAlmostEqual(B.mu_water(20) * 1000, 1.002, delta=0.03)  # 1.00 mPa·s
        self.assertAlmostEqual(B.mu_water(90) * 1000, 0.315, delta=0.01)  # 0.31 mPa·s

    def test_vapor_pressure(self):
        self.assertAlmostEqual(B.p_sat(100) / 1000, 101.3, delta=2.0)
        self.assertAlmostEqual(B.p_sat(25) / 1000, 3.17, delta=0.1)

    def test_pva_viscosity_rises_with_c_and_falls_with_t(self):
        self.assertAlmostEqual(B.mu_pva(4, 20) * 1000, 28, delta=0.5)  # 규격 기준점
        self.assertGreater(B.mu_pva(15, 20), B.mu_pva(3, 20))
        self.assertLess(B.mu_pva(15, 90), B.mu_pva(15, 20))
        self.assertGreaterEqual(B.mu_pva(0.01, 90), B.mu_water(90))


class TestMechanics(unittest.TestCase):
    def test_reynolds_and_vortex(self):
        a = B.Stir(300, 40, 105, 58, 1005, 0.015)
        b = B.Stir(600, 40, 105, 58, 1005, 0.015)
        thick = B.Stir(300, 40, 105, 58, 1005, 1.5)
        self.assertGreater(b.re, a.re)
        self.assertGreater(b.vortex_mm(), a.vortex_mm())
        self.assertLess(thick.vortex_mm(), 0.1)  # 꿀처럼 진하면 소용돌이 없음
        self.assertEqual(thick.regime, "층흐름")
        self.assertTrue(math.isinf(thick.mix_s()))
        self.assertLess(b.mix_s(), a.mix_s())

    def test_heat_curve(self):
        lo = B.heat_curve(0.115, 22, 90, 150, 0.007, 0.0035, 2.0, cover_leak=0.05)
        hi = B.heat_curve(0.115, 22, 90, 150, 0.007, 0.0035, 2.0, cover_leak=0.5)
        self.assertLess(lo["reach_min"], 10)
        self.assertAlmostEqual(max(lo["T"]), 90, delta=1.0)
        self.assertGreater(hi["evap_g"], 5 * lo["evap_g"])
        c = B.cool_curve(0.11, 90, 40, 0.01, 0.0035)
        self.assertLess(c["T"][-1], 41)

    def test_aggregation_faster_above_ccc(self):
        mu = B.mu_pva(3)
        fast = B.go_aggregation(0.5, 135, 3, mu)
        slow = B.go_aggregation(0.5, 20, 3, mu)
        self.assertTrue(fast["aggregates"])
        self.assertFalse(slow["aggregates"])
        self.assertLess(fast["t_half_s"], slow["t_half_s"])
        self.assertGreater(fast["radius_um"], slow["radius_um"])


class TestSteps(unittest.TestCase):
    def test_all_steps(self):
        ph = B.bench_physics()
        self.assertEqual([p.id for p in ph], [s.id for s in process()])
        self.assertEqual(len(ph), 19)
        for p in ph:
            self.assertTrue(p.items, p.id)
            self.assertTrue(p.verdict, p.id)
            self.assertIn(p.engine, ("mantaflow", "bullet", "fenicsx", "해석식"))
            json.dumps(p.to_json(), allow_nan=False)  # 웹 DATA 로 그대로 나감
            if p.series:
                self.assertEqual(len(p.series["x"]), len(p.series["y"]))

    def test_findings(self):
        ph = {p.id: p for p in B.bench_physics()}
        self.assertGreater(ph["mix"].render["vortex_mm"], 1)
        r = ph["degas"].render["rise_mm_s"]
        self.assertGreater(r[0], r[1])  # 큰 기포가 빨리
        self.assertGreater(ph["demold"].render["strain"], 0.1)  # 무른 겔 — 처짐
        self.assertFalse(ph["pretest"].ok)  # 염 > CCC → 응집
        fr = ph["dfreeze"].render["front_mm"]
        self.assertEqual(fr, sorted(fr))


if __name__ == "__main__":
    unittest.main()
