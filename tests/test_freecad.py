import json
import shutil
import tempfile
import unittest
from pathlib import Path

from snss_battery import fcparams
from snss_battery.layout import BED_CARRIAGE, PLATE, POD_H, make_layout, make_light_layout
from snss_battery.printer import SculptorSpec


class TestDesignParams(unittest.TestCase):
    def test_design_json_has_every_work(self):
        d = fcparams.design()
        for k in ("sc1", "sc2", "parts", "shapes", "quantum", "bottle", "coupons"):
            self.assertIn(k, d)
        self.assertEqual(len(d["parts"]), 20)
        self.assertEqual({s for s in d["shapes"]}, {"being", "seed", "bud", "coupon"})
        self.assertEqual(len(d["quantum"]), 35)
        self.assertEqual(len(d["sc2"]["tools"]), 6)
        json.dumps(d, default=float)  # 직렬화 가능

    def test_sc1_nut_plate_clears_motor_pods(self):
        """FreeCAD 움직임 점검이 찾은 고침: 받침이 다 내려가도 너트 판이 Z 모터 방수 통(49 mm) 위 2 mm."""
        lay = make_layout()
        self.assertGreaterEqual(lay.bed_bottom_min, POD_H + 2)
        self.assertEqual(lay.z_tip, lay.bed_bottom_min + BED_CARRIAGE + PLATE + SculptorSpec().build_mm[2])
        self.assertEqual(lay.problems(), [])
        self.assertEqual(make_light_layout().problems(), [])

    def test_sc1_old_height_fails_new_checks(self):
        """출력 높이 100 이면 XY 모터 방수 통이 위 꼭짓점에 닿음 — 그래서 90."""
        from dataclasses import replace

        lay = make_layout(replace(SculptorSpec(), build_mm=(110.0, 110.0, 100.0)))
        self.assertTrue(any("꼭짓점 (위)" in p for p in lay.problems()))


@unittest.skipIf(fcparams.freecad_bin() is None, "FreeCAD 가 없음 (./tools.sh freecad 로 설치)")
class TestFreeCADBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())  # 저장소의 cad_out/freecad 는 건드리지 않음
        cls.v = fcparams.run_build(out=cls.tmp / "cad_out" / "freecad", only="sc1,small", gui=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_docs_recompute_clean(self):
        for d in self.v["docs"]:
            self.assertEqual(d["errors"], [], d["file"])
            self.assertEqual(d["invalid"], [], d["file"])

    def test_parts_match_sdf(self):
        self.assertEqual(len(self.v["parts"]), 20)
        for p in self.v["parts"]:
            self.assertTrue(p["valid"], p["key"])
            self.assertLess(abs(p["rel"]), 0.03, p["key"])

    def test_clearance_and_motion(self):
        self.assertTrue(all(x["gap"] >= 2.0 for x in self.v["clearance"]["SC-1"]))
        self.assertEqual(self.v["motion"]["SC-1"], [])

    def test_shapes_match_sdf(self):
        s = self.v["shapes"]
        self.assertLess(abs(s["being"]["rel"]), 0.05)
        self.assertAlmostEqual(s["coupon"]["volume_cm3"], 1.728, places=3)

    def test_quantum_stack(self):
        self.assertEqual(self.v["quantum"]["layers"], 35)
        from snss_battery.quantum import analytic_volume_mm3

        self.assertAlmostEqual(self.v["quantum"]["volume_mm3"], analytic_volume_mm3(), delta=1e-6 * analytic_volume_mm3())


if __name__ == "__main__":
    unittest.main()
