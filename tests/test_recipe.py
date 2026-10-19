import unittest

from snss_battery.recipe import RECIPES, SALINE_M, Recipe


class RecipeTest(unittest.TestCase):
    def test_mean_concentration_is_normal_saline(self):
        r = Recipe()
        self.assertAlmostEqual((r.c_dilute_m + r.c_conc_m) / 2, SALINE_M, places=12)

    def test_mix_concentrations(self):
        r = Recipe()
        groups = dict(r.amounts())
        a = dict((n, v) for n, v, _ in groups["A액 — 묽은 층"])
        b = dict((n, v) for n, v, _ in groups["B액 — 진한 층"])
        vol_a = a["PVA 원액"] + a["약국 생리식염수"] + a["증류수"]
        self.assertAlmostEqual(a["약국 생리식염수"] * SALINE_M / vol_a, r.c_dilute_m, places=9)
        vol_b = b["PVA 원액"] + b["약국 생리식염수"]
        mol_b = b["약국 생리식염수"] / 1000 * SALINE_M + b["추가 소금 NaCl"] / 58.44
        self.assertAlmostEqual(mol_b / (vol_b / 1000), r.c_conc_m, places=9)

    def test_layer_volume_matches_geometry(self):
        r = Recipe()
        self.assertAlmostEqual(r.layer_ml, 3.14159265 * 3.52 ** 2 * 0.25, delta=0.01)

    def test_led_version_predicted_to_light(self):
        p = RECIPES["led"].predict()
        self.assertEqual(p["pairs"], 25)
        self.assertGreater(p["led_ma"], 0.5)

    def test_practice_version_too_low_for_led(self):
        p = RECIPES["practice"].predict()
        self.assertLess(p["ocv_v"], 1.0)  # H1~H3 확인용

    def test_exact_height_keeps_every_pair(self):
        # 높이 = 쌍 수 × 쌍 두께 딱 맞을 때 반올림 오차로 한 쌍을 잃지 않음
        for r in RECIPES.values():
            self.assertEqual(r.predict()["pairs"], r.pairs)

    def test_quantities_match_grouped_table(self):
        r = Recipe()
        q = r.quantities()
        total = dict((n, v) for n, v, _ in dict(r.amounts())["총 구매량 (여유 포함)"])
        self.assertEqual(total["약국 생리식염수"], q["buy_saline_ml"])
        self.assertEqual(total["NaCl"], q["extra_nacl_g"])


if __name__ == "__main__":
    unittest.main()
