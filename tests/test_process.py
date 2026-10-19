import unittest
from pathlib import Path

from snss_battery.process import HAND, MACHINE, fem_hours, markdown, process, summary, thaw_hours
from snss_battery.tissue import TissueRecipe, freezing

ROOT = Path(__file__).resolve().parents[1]


class ProcessTest(unittest.TestCase):
    def setUp(self):
        self.steps = process()

    def test_modes_and_ids(self):
        ids = [x.id for x in self.steps]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(x.mode in (HAND, MACHINE) for x in self.steps))
        self.assertTrue(all(x.equipment and x.check for x in self.steps))
        # 실험대 장면이 쓰는 단계
        for k in ("chill", "weigh", "take", "stock", "cool", "pretest", "mix", "degas", "refill", "setup",
                  "dfreeze", "thaw", "ft", "demold", "meas", "section", "lyo", "cond"):
            self.assertIn(k, ids)

    def test_hands_fit_in_time(self):
        for x in self.steps:
            if x.mode == HAND:  # 수작업은 단계 시간 내내 사람이 붙어 있음
                self.assertLessEqual(x.hands_min, x.hours * 60 + 1e-9, x.id)
            else:
                self.assertLess(x.hands_min, max(x.hours * 60, 60) + 1e-9, x.id)

    def test_times_follow_model(self):
        rc = TissueRecipe()
        stefan = freezing(rc.battery().gel_height_mm, rc.plate_c)["hours"]
        by = {x.id: x for x in self.steps}
        fem = fem_hours()
        if fem:  # FEniCSx: 병 벽 · 처음 온도 · 주변 열 때문에 스테판보다 길고, 2배를 넘지 않음
            self.assertAlmostEqual(by["dfreeze"].hours, fem[0])
            self.assertTrue(stefan < fem[0] < 2 * stefan)
        else:
            self.assertAlmostEqual(by["dfreeze"].hours, stefan)
        self.assertAlmostEqual(by["ft"].hours, (rc.freeze_thaw - 1) * (fz + by["thaw"].hours))
        s = summary(self.steps)
        self.assertGreater(s["days"], 3)  # 이틀로는 안 됨
        self.assertGreater(s["machine_hours"], s["hand_hours"])

    def test_thaw(self):
        # 25 °C 수조는 몇 시간, 4 °C 는 ΔT 비율만큼 (약 5.6배) 오래 — 공기라면 더 느림
        self.assertTrue(1.0 < thaw_hours(35.2) < 3.0)
        self.assertGreater(thaw_hours(35.2, bath_c=4.0), 5 * thaw_hours(35.2))

    def test_recipe_md_matches(self):
        self.assertIn(markdown(self.steps), (ROOT / "RECIPE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
