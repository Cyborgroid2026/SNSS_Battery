import unittest

import numpy as np

from snss_battery.eit import EIT, EITSpec, Scene, eit_report, electrode_sites

COARSE = EITSpec(fine_mm=12.5)  # 시험용 굵은 칸 (가운데 12.5 mm)


class TestEITForward(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eit = EIT(COARSE)
        cls.homo = cls.eit.frame(Scene(bed=False, gantry=False))

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
        """받침 · 갠트리 없는 배지 · 정사각 잉크 우물 테 · 두 정사각 링 → 한 면 돌리면 (전극 4개 밀기) 같은 전압."""
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
        """역문제 자체: 충분히 평균하면 받침 옆 덧굳은 덩어리 자리를 맞힘 (검출 한계는 보고서에서)."""
        eit = EIT(COARSE)
        a = Scene(bed=False)
        c = np.array([40.0, 0.0, 305.0])
        b = Scene(bed=False, blobs=[(tuple(c), 6.0, 3.5)])  # 덧굳은 rGO 덩어리
        ref, meas = eit.frame(a), eit.frame(b)
        n = 20000
        img, _ = eit.reconstruct(ref, eit.noisy(meas, n, seed=1), n)
        centre, _ = eit.locate(img, 1.0)
        self.assertGreater(np.linalg.norm(meas.v - ref.v) / np.linalg.norm(eit.noise_std(ref, n)), 3)
        self.assertLess(np.linalg.norm(centre - c), 15.0)

    def test_sleeve_sees_more_than_walls(self):
        c = (40.0, 0.0, 305.0)
        snr = {}
        for place in ("sleeve", "walls"):
            e = EIT(EITSpec(fine_mm=12.5, place=place, rings_z_mm=(313.0, 296.0) if place == "sleeve" else (300.0, 265.0)))
            r, m = e.frame(Scene(bed=False)), e.frame(Scene(bed=False, blobs=[(c, 6.0, 3.5)]))
            snr[place] = np.linalg.norm(m.v - r.v) / np.linalg.norm(e.noise_std(r))
        self.assertGreater(snr["sleeve"], 5 * snr["walls"])

    def test_report_runs(self):
        r = eit_report("coupon", es=COARSE)
        self.assertEqual(r["n_electrodes"], 32)
        self.assertEqual(r["n_meas"], 32 * 29)
        self.assertIn("전극", r["text"])
        self.assertLess(r["current_sum_a"], 1e-9)
        self.assertGreater(r["scenarios"][2]["snr"], 3)  # 10 층 자람은 보임


class TestGantrySafe(unittest.TestCase):
    def test_electrodes_clear_of_tool_gantry(self):
        """A 줄은 치마 끝(318) 위 → 갠트리 빔 윗면(316) 위. B 줄은 받침 기둥(±62) 안에서 받침과 함께 움직임."""
        from snss_battery.layout import make_light_layout

        lay = make_light_layout()
        top = max(b.hi[2] for b in lay.boxes if b.kind == "gantry" and "빔" in b.name)
        col = next(z for z in lay.zones if z.name.startswith("배양 받침 기둥"))
        es = EITSpec()
        for layer in (0, 100, 240):
            sc_dz = 330.0 - (layer + 1) * 0.301
            pos, ring, zc = electrode_sites(es, _FixedDz(sc_dz), 350.0)
            a = [p for p, r in zip(pos, ring) if r == 0]
            b = [p for p, r in zip(pos, ring) if r == 1]
            self.assertTrue(all(p[2] >= es.skirt_bottom_mm > top for p in a))
            self.assertTrue(all(abs(p[0]) <= col.hi[0] and abs(p[1]) <= col.hi[1] for p in b))
            self.assertTrue(all(abs(p[2] - (sc_dz - es.bed_drop_mm)) < 1e-9 for p in b))
            self.assertTrue(np.all(zc > 0))


class _FixedDz:
    def __init__(self, dz):
        self.dz = dz


if __name__ == "__main__":
    unittest.main()
