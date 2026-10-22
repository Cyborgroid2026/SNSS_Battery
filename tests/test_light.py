import math
import unittest

import numpy as np

from snss_battery.layout import make_light_layout
from snss_battery.lightsculpt import Ink, LightSculptorSpec, Projector, build_time_estimate_h, exposure_plan, light_job
from snss_battery.sculpt import EMPTY, MEM, POS, Piece


class TestLightSculptor(unittest.TestCase):
    def setUp(self):
        self.spec = LightSculptorSpec()

    def test_design_check_passes(self):
        self.assertEqual(self.spec.check(), [])

    def test_ink_floats_and_is_stable_until_it_sinks(self):
        s = self.spec
        self.assertLess(s.ink_density(), s.tank.density)  # 잉크층이 배지 위에 뜸
        self.assertLess(s.ink.nacl_mm, s.ccc_mm())  # 잉크 속 GO 는 엉기지 않음
        self.assertGreater(s.tank.saline_mm, s.ccc_mm())  # 내려가면 멸균생리식염수가 고정

    def test_dense_ink_sinks(self):
        s = LightSculptorSpec(ink=Ink(pva_wt=5.0))
        self.assertTrue(any("뜨지 않음" in b for b in s.check()))

    def test_room_temperature_limits_irradiance(self):
        self.assertLessEqual(self.spec.surface_rise_k(), 1.0)
        hot = LightSculptorSpec(projector=Projector(irradiance_mw_cm2=20.0))
        self.assertTrue(any("상온" in b for b in hot.check()))

    def test_go_vs_time_tradeoff(self):
        thin = LightSculptorSpec(ink=Ink(go_mg_ml=1.0))
        self.assertGreater(thin.dp_mm(), self.spec.dp_mm())
        self.assertLess(build_time_estimate_h(thin, 70), build_time_estimate_h(self.spec, 70))

    def test_column_doses(self):
        """세포질 기둥 아래 막 한 칸: 세포질은 E_red 이상, 막은 θ·E_red 아래, 빈 잉크는 굳지 않음."""
        s = self.spec
        mat = np.zeros((1, 1, 12), dtype=np.uint8)
        mat[0, 0, :4] = POS
        mat[0, 0, 4] = MEM
        mat[0, 0, 5:11] = POS
        mat[0, 0, 11] = MEM
        p = Piece("t", mat, np.zeros_like(mat, dtype=np.int32), np.array([1], dtype=np.int8), (0, 0), (0.41, s.layer_mm), 1.0)
        pl = exposure_plan(p, s)
        D = pl["D"][0, 0]
        self.assertTrue(np.all(D[mat[0, 0] == POS] >= s.photo.e_red_mj_cm2 * 0.999))
        self.assertTrue(np.all(D[mat[0, 0] == MEM] <= s.photo.theta_mem * s.photo.e_red_mj_cm2))
        self.assertEqual(pl["mem_leaky"], 0.0)

    def test_layout_clear(self):
        lay = make_light_layout(self.spec)
        self.assertEqual(lay.problems(), [])
        self.assertGreater(lay.gz, self.spec.tank.inner_mm[2])  # 프로젝터는 수조 밖

    def test_coupon_job(self):
        job = light_job("coupon", 6.0, self.spec)
        pl = job["plan"]
        self.assertGreater(pl["cyto_reduced"], 0.99)
        self.assertLess(pl["mem_leaky"], 0.01)
        self.assertGreater(job["prediction"]["energy_j"], 0)
        self.assertTrue(math.isfinite(pl["expose_s"]))


if __name__ == "__main__":
    unittest.main()
