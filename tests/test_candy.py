import tempfile
import unittest
from pathlib import Path

from snss_battery import candy, sdcard


class TestZeroRod(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pl = candy.plan("bud")  # 작아서 빠름

    def test_grows_from_zero_point(self):
        sh = self.pl["shell"]
        self.assertTrue((sh[1:] >= sh[:-1]).all())  # 영점에서 가까운 껍질부터
        self.assertEqual(candy.check(self.pl), [])

    def test_process_repeat_and_edit(self):
        p = candy.Process.from_plan(self.pl, "bud")
        t0 = p.total_s()
        p.edit(1, repeat=2).edit(2, skip=True)
        tl = p.timeline()
        self.assertEqual(sum(1 for s in tl if s["step"] == 1), 2)
        self.assertFalse(any(s["step"] == 2 for s in tl))
        self.assertNotAlmostEqual(p.total_s(), t0)
        self.assertEqual(len(p.edits), 2)

    def test_burn_verify_play_reburn(self):
        p = candy.Process.from_plan(self.pl, "bud")
        with tempfile.TemporaryDirectory() as d:
            r = sdcard.burn(self.pl, p, d)
            self.assertTrue(sdcard.verify(d)["ok"])
            self.assertTrue((Path(r["root"]) / "monitors" / "timeline.png").exists())
            out = sdcard.play(d, [("repeat", 0)])
            self.assertGreater(out["played_samples"], r["samples"] - 1)
            q = sdcard.reburn_edits(d)
            self.assertEqual(q.steps[0]["repeat"], 2)
            (Path(r["root"]) / "program.cv").write_bytes(b"\0" * 10)  # 망가진 SD 는 다시 읽기에서 잡힘
            self.assertFalse(sdcard.verify(d)["ok"])


if __name__ == "__main__":
    unittest.main()
