import unittest

import numpy as np

from snss_battery.eit import EIT, EITSpec, Scene, eit_report

COARSE = EITSpec(fine_mm=12.5)  # 시험용 굵은 칸 (가운데 12.5 mm)


class TestEITForward(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eit = EIT(COARSE)
        cls.homo = cls.eit.frame(Scene(bed=False))

    def test_reciprocity(self):
        """구동 d · 측정 p 를 바꿔도 같은 전압 (상반 정리) — 측정 쌍과 구동 쌍이 같은 묶음."""
        z = self.homo.z
        self.assertLess(np.max(np.abs(z - z.T)) / np.max(np.abs(z)), 1e-8)

    def test_current_conservation(self):
        cur = self.homo.fw.electrode_currents(self.homo.u)  # 단위 전류 (1 A)
        self.assertLess(np.max(np.abs(cur.sum(axis=0))), 1e-9)
        for c, (a, b) in enumerate(self.eit.pairs):
            self.assertAlmostEqual(cur[a, c], 1.0, places=9)
            self.assertAlmostEqual(cur[b, c], -1.0, places=9)

    def test_homogeneous_four_fold_symmetry(self):
        """받침 없는 배지 · 정사각 소매 · 정사각 잉크 우물 → 한 면 돌리면 (전극 4개 밀기) 같은 전압."""
        z = self.homo.z
        n = len(self.eit.pairs)
        rot = np.array([(i // 16) * 16 + (i % 16 + 4) % 16 for i in range(n)])
        self.assertLess(np.max(np.abs(z - z[np.ix_(rot, rot)])) / np.max(np.abs(z)), 1e-6)

    def test_voltages_far_below_carbon_window(self):
        f = self.homo
        self.assertLessEqual(f.drive_v, COARSE.v_cap_mv * 1e-3)
        self.assertLess(np.max(np.abs(f.v)), 0.8)
        self.assertLess(f.current_a, 5e-3)


class TestEITInverse(unittest.TestCase):
    def test_blob_localized(self):
        eit = EIT(COARSE)
        a = Scene(bed=False)
        c = np.array([40.0, 0.0, 305.0])
        b = Scene(bed=False, blobs=[(tuple(c), 6.0, 3.5)])  # 덧굳은 rGO 덩어리
        ref, meas = eit.frame(a), eit.frame(b)
        img, info = eit.reconstruct(ref, eit.noisy(meas, 500, seed=1), 500)
        centre, _ = eit.locate(img, 1.0)
        self.assertGreater(info["snr"], 3)
        self.assertLess(np.linalg.norm(centre - c), 15.0)

    def test_report_runs(self):
        r = eit_report("coupon", es=COARSE, compare_walls=False)
        self.assertEqual(r["n_electrodes"], 32)
        self.assertEqual(r["n_meas"], 32 * 29)
        self.assertIn("전극", r["text"])
        self.assertLess(r["current_sum_a"], 1e-9)
        self.assertGreater(r["scenarios"][2]["snr"], 3)  # 10 층 자람은 보임


if __name__ == "__main__":
    unittest.main()
