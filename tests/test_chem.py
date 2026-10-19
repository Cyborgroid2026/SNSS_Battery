import importlib.util
import unittest

from snss_battery import chem


class ChemTest(unittest.TestCase):
    """spec/phreeqc_nacl.json (PHREEQC · pitzer.dat) 을 문헌값과 대조."""

    def test_gamma_literature(self):
        # NaCl γ± (25 °C, Robinson & Stokes): 0.1 m 0.778, 1 m 0.657, 3 m 0.714
        for m, ref in ((0.1, 0.778), (1.0, 0.657), (3.0, 0.714)):
            self.assertAlmostEqual(chem.gamma(m), ref, delta=0.01)

    def test_freezing(self):
        self.assertAlmostEqual(chem.freezing_point_c(0.154), -0.53, delta=0.05)
        self.assertAlmostEqual(chem.brine_at(-21.1), 5.2, delta=0.15)  # 공정점

    def test_membrane_potential_activity_lower(self):
        ideal, real = chem.membrane_potential(1.63, 0.0018, 0.3)
        self.assertLess(real, ideal)
        self.assertGreater(real, 0.9 * ideal)


@unittest.skipUnless(importlib.util.find_spec("pybamm"), "pybamm 없음 (.venv/bin/python 으로 실행)")
class PybammTest(unittest.TestCase):
    def test_matches_lumped_model(self):
        from snss_battery import pybamm_cell as P
        from snss_battery.bottle import BottleGelBattery
        from snss_battery.simulation import cycle_cc, suggest_limits

        i = 1e-4
        v_max, v_min = suggest_limits(BottleGelBattery().stack, i)
        ref = cycle_cc(BottleGelBattery().stack, i, v_max, v_min, 1, dt_s=2.0, born_charged=True)
        r = P.cycle(BottleGelBattery().stack, i, v_max, v_min, 1, P.Physics.lumped())
        got = [x["mah"] for x in r["phases"] if x["phase"] == "discharge"]
        for a, b in zip([c.discharge_mah for c in ref.cycles], got):
            self.assertAlmostEqual(a, b, delta=0.002 * a + 1e-4)


if __name__ == "__main__":
    unittest.main()
