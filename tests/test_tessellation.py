import math
import unittest

import numpy as np

from snss_battery import BottleGelBattery, GelFormation
from snss_battery.tessellation import FractalVoronoiParams, analyze_battery, box_counting


class VoronoiNetworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bat = BottleGelBattery()

    def run_net(self, **kw):
        base = dict(window_layers=16, window_width_mm=5.0)
        base.update(kw)
        return analyze_battery(self.bat, FractalVoronoiParams(**base))

    def test_flat_layers_match_ideal_stack(self):
        r = self.run_net(interface_dimension=1.0, roughness=0.0)
        ideal = self.bat.stack.open_circuit_voltage()
        self.assertAlmostEqual(r.ocv_v / ideal, 1.0, delta=0.06)
        self.assertEqual(r.defect_fraction, 0.0)
        self.assertLess(r.leak_current_ma, 1e-6)

    def test_voronoi_topology(self):
        r = self.run_net()
        self.assertAlmostEqual(r.mean_neighbors, 6.0, delta=0.15)  # 평면 보로노이: 평균 6변
        self.assertGreater(r.n_cells, 100)

    def test_roughness_creates_defects_and_leak(self):
        smooth = self.run_net(roughness=0.1, correlation=0.0)
        rough = self.run_net(roughness=1.0, correlation=0.0)
        self.assertGreater(rough.defect_fraction, smooth.defect_fraction)
        self.assertGreater(rough.leak_current_ma, smooth.leak_current_ma)
        self.assertLess(rough.ocv_v, smooth.ocv_v)

    def test_fractal_dimension_increases_membrane_length(self):
        lo = self.run_net(interface_dimension=1.1, roughness=0.3, correlation=1.0)
        hi = self.run_net(interface_dimension=1.7, roughness=0.3, correlation=1.0)
        self.assertGreater(hi.interface_roughness, lo.interface_roughness)
        self.assertLessEqual(hi.resistance_ohm, lo.resistance_ohm * 1.02)

    def test_clustered_nuclei_are_heterogeneous(self):
        uniform = self.run_net(seed_dimension=2.0)
        clustered = self.run_net(seed_dimension=1.5)
        self.assertGreater(clustered.area_cv, 2 * uniform.area_cv)

    def test_formation_parameters_flow_through(self):
        b = BottleGelBattery(formation=GelFormation(interface_dimension=1.6, interface_roughness=0.2))
        p = b.fractal_params()
        self.assertEqual((p.interface_dimension, p.roughness), (1.6, 0.2))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            FractalVoronoiParams(interface_dimension=2.0)
        with self.assertRaises(ValueError):
            FractalVoronoiParams(correlation=1.5)


class BoxCountingTest(unittest.TestCase):
    def test_straight_line_is_one(self):
        seg = np.array([[[0.0, 0.5], [10.0, 0.5]]])
        self.assertAlmostEqual(box_counting(seg, 10, 10, 0.05)["dimension"], 1.0, delta=0.08)

    def test_koch_curve(self):
        def koch(a, b, n):
            if n == 0:
                return [(a, b)]
            a, b = np.array(a), np.array(b)
            d = (b - a) / 3
            p1, p2 = a + d, a + 2 * d
            rot = np.array([[0.5, -math.sqrt(3) / 2], [math.sqrt(3) / 2, 0.5]])
            peak = p1 + rot @ d
            out = []
            for u, v in ((a, p1), (p1, peak), (peak, p2), (p2, b)):
                out += koch(u, v, n - 1)
            return out
        seg = np.array(koch((0.0, 0.0), (10.0, 0.0), 6))
        d = box_counting(seg, 10, 10, 10 / 3 ** 6 * 2)["dimension"]
        self.assertAlmostEqual(d, math.log(4) / math.log(3), delta=0.12)  # 1.26


if __name__ == "__main__":
    unittest.main()
