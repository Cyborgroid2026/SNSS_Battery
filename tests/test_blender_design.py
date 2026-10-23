import shutil
import tempfile
import unittest
from pathlib import Path

from snss_battery import bldesign


@unittest.skipIf(bldesign.blender_bin() is None, "Blender 가 없음")
class TestBlenderDesign(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())  # 저장소의 cad_out/blender 는 건드리지 않음
        cls.v = bldesign.run_build(out=cls.tmp / "cad_out" / "blender", render=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_scenes_drivers_modifiers(self):
        names = {s["scene"] for s in self.v["scenes"]}
        for n in ("SC-1 조각가", "SC-1 부품", "SC-2 빛 조각가", "SC-2 도구", "존재 모양", "시험편", "양자 모듈", "병 결정"):
            self.assertIn(n, names)
        for s in self.v["scenes"]:
            self.assertEqual(s["bad_drivers"], [], s["scene"])
            self.assertEqual(s["bad_modifiers"], [], s["scene"])

    def test_parts_closed_and_match_sdf(self):
        self.assertEqual(len(self.v["parts"]), 23)
        for p in self.v["parts"]:
            self.assertEqual(p["nonmanifold_edges"], 0, p["key"])
            self.assertLess(abs(p["rel"]), 0.03, p["key"])

    def test_metaball_shapes_match_sdf(self):
        for k, s in self.v["shapes"].items():
            self.assertLess(abs(s["rel"]), 0.02, k)  # 메타볼 = SDF 의 부드러운 합
            self.assertEqual(s["nonmanifold_edges"], 0, k)

    def test_clearance_and_motion(self):
        for k in ("SC-1", "SC-2"):
            self.assertTrue(all(x["gap"] >= 2.0 for x in self.v["clearance"][k]), k)
            self.assertEqual(self.v["motion"][k], [], k)

    def test_quantum_stack(self):
        from snss_battery.quantum import module_layers

        self.assertEqual(self.v["quantum"]["layers"], 35)
        self.assertAlmostEqual(self.v["quantum"]["top_z_mm"], sum(t for *_, t in module_layers()), places=4)


if __name__ == "__main__":
    unittest.main()
