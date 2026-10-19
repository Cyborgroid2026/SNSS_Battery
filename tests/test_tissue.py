import math
import unittest
from dataclasses import replace

from snss_battery.tissue import (SALINE_M, TissueParams, TissueRecipe, build_tissue, freezing, k_eff, tissue_for)


class TissueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bat = TissueRecipe().battery()
        cls.r = tissue_for(cls.bat)

    def test_cells_fill_window_exactly(self):
        p = self.r.params
        self.assertAlmostEqual(sum(c.volume_mm3 for c in self.r.cells), p.window_mm ** 2 * p.height_mm, places=6)

    def test_no_layers_no_polarity(self):
        # 모든 세포가 같은 종류, 모든 벽이 같은 막 (종류 구분 없음)
        self.assertEqual({f.kind for f in self.r.faces}, {"wall", "boundary"})
        self.assertFalse(hasattr(self.r.cells[0], "band"))

    def test_salt_is_conserved(self):
        film = self.r.params.film_um / 1000
        v_f = sum(f.area_mm2 * film for f in self.r.faces if f.b >= 0)
        v = sum(c.volume_mm3 for c in self.r.cells)
        salt = sum(c.conc_m * c.volume_mm3 for c in self.r.cells) * (v - v_f) / v + self.r.c_brine * v_f
        self.assertAlmostEqual(salt / v, SALINE_M, places=9)

    def test_empty_cells_hold_energy(self):
        self.assertLess(self.r.c_lumen[1], SALINE_M)  # 얼음이 녹은 내강은 묽음
        self.assertGreater(self.r.c_brine, SALINE_M)  # 막 사이 소금물은 진함
        for c in self.r.cells:
            self.assertGreater(c.energy_j, 0)
        self.assertGreater(self.r.full["energy_j"], 100)

    def test_symmetric_tissue_gives_almost_no_voltage(self):
        # 극성·층이 없으면 막전위가 상쇄 → 윗면–아랫면 전압은 막 하나의 전위보다 훨씬 작음
        self.assertLess(abs(self.r.ocv_window_v), 0.01 * self.r.wall_mv / 1000)
        self.assertLess(abs(self.r.full["ocv_v"]), self.r.full["gradient_bound_v"] + 1e-9)

    def test_uniform_salt_gives_zero_voltage(self):
        import snss_battery.tissue as T

        old = T.k_eff
        T.k_eff = lambda v: 0.01  # 속도와 무관 → 기울기 없음
        try:
            r = tissue_for(self.bat)
        finally:
            T.k_eff = old
        self.assertLess(abs(r.ocv_window_v), 1e-9)

    def test_fractal_front_dimension_follows_setting(self):
        lo = tissue_for(self.bat, fp=replace(self.bat.fractal_params(), interface_dimension=1.1)).continuity["d_front"]
        hi = tissue_for(self.bat, fp=replace(self.bat.fractal_params(), interface_dimension=1.6)).continuity["d_front"]
        self.assertLess(lo, hi)
        self.assertLess(abs(self.r.continuity["d_front"] - 1.25), 0.2)

    def test_voronoi_elements_are_one_network(self):
        # 세포(3D) · 막(2D) · 소금물 통로(1D, 보로노이 모서리)
        self.assertGreater(len(self.r.veins), len(self.r.cells))

    def test_partition_coefficient_rises_with_speed(self):
        self.assertLess(k_eff(1e-6), k_eff(1e-4))
        self.assertTrue(0 < k_eff(0) < k_eff(1e-3) <= 1)

    def test_freezing_time_scales_with_height_squared(self):
        self.assertAlmostEqual(freezing(100)["hours"] / freezing(50)["hours"], 4.0, places=9)

    def test_recipe_keeps_bottle_volume(self):
        back = dict((n, v) for n, v, _ in dict(TissueRecipe().amounts())["병에 다시 넣기"])
        self.assertTrue(math.isclose(back["최종 부피"], 500.0))

    def test_params_validate(self):
        with self.assertRaises(ValueError):
            TissueParams(cell_um=0)
        build_tissue(self.bat.fractal_params(), TissueParams(height_mm=1.0, window_mm=0.8))


if __name__ == "__main__":
    unittest.main()
