import math
import unittest

import numpy as np

from snss_battery import candy, sc3_build, sdcard
from snss_battery.console import Console


class TestSc3Assembly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pl = candy.plan("being")
        cls.items = sc3_build.layout()
        cls.rep = sc3_build.check(cls.items, cls.pl)

    def test_assembly_check_passes(self):
        self.assertTrue(self.rep["ok"], self.rep["fail"])

    def test_every_printed_part_fits_common_printer(self):
        for p in sc3_build.printed():
            self.assertTrue(p.fits(), p.name)

    def test_nothing_floats_and_floor_items_sit_on_floor(self):
        by = {it.name: it for it in self.items}
        fl = Console().desktop.floor_z
        for it in self.items:
            if it.on == "바닥":
                self.assertAlmostEqual(it.lo[2], fl, delta=0.6, msg=it.name)
            else:
                self.assertIn(it.on, by, it.name)
        for name in ("IP68 실리콘 키보드", "IP68 방수 마우스", "IP66 방수 모니터 1"):
            self.assertIn(name, by)

    def test_wet_parts_have_no_metal(self):
        for it in self.items:
            if it.wet:
                self.assertNotIn(it.mat, ("steel", "alu", "dark"), it.name)

    def test_separate_nozzle_per_material_and_clearance(self):
        names = [it.name for it in self.items if it.name.startswith("PEEK 노즐")]
        self.assertEqual(len(names), 3)
        nc = sc3_build.nozzle_clearance(self.pl)
        self.assertGreater(nc["inactive_tip_mm"], 2 * nc["shell_mm"])

    def test_injection_grouped_by_material_per_shell(self):
        sh, m = self.pl["shell"], self.pl["mat"]
        change = np.r_[True, (m[1:] != m[:-1]) | (sh[1:] != sh[:-1])]
        per_shell = np.bincount(sh[change])
        self.assertLessEqual(per_shell.max(), 3)

    def test_theta_brings_voxel_to_nozzle(self):
        st = candy.strokes(self.pl)
        rel = self.pl["xyz"] - np.array(self.pl["zero_mm"])
        a = np.radians(st[:, 0])
        x = rel[:, 0] * np.cos(a) - rel[:, 1] * np.sin(a)
        y = rel[:, 0] * np.sin(a) + rel[:, 1] * np.cos(a)
        self.assertLess(np.abs(y).max(), 1e-6)  # 돌린 뒤 칸이 +x 축 (노즐 쪽) 위에
        self.assertGreaterEqual(x.min(), -1e-6)

    def test_program_has_nozzle_channel_and_purges(self):
        pl = candy.plan("bud")
        prog, _ = sdcard.program(pl, candy.Process.from_plan(pl, "bud"))
        names = [c[0] for c in sdcard.CHANNELS]
        noz = prog[:, names.index("nozzle")]
        self.assertEqual(len(set(np.unique(noz)) - {-32767, 0, 32767}), 0)  # −30 · 0 · +30° = −10 · 0 · +10 V
        self.assertGreater(len(prog), candy.Process.from_plan(pl, "bud").total_s() * sdcard.RATE_HZ * 0.99)
        self.assertTrue(math.isclose(sc3_build.G.belt_center_mm(), 52.45, abs_tol=0.1))


if __name__ == "__main__":
    unittest.main()
