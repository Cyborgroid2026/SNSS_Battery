import unittest

from snss_battery.console import HW_KEYMAP, Console
from snss_battery.layout import TURN_POD, make_layout


class TestConsole(unittest.TestCase):
    def test_desktop_under_tank(self):
        c = Console()
        d = c.desktop
        self.assertAlmostEqual(d.top_z, -6 - d.tray_mm - d.insulation_mm)  # 수조 바깥 바닥 바로 밑
        self.assertEqual(d.footprint_mm, (358.0, 358.0))
        self.assertLess(c.heat_into_bath_w(), 1.0)  # XPS 너머 배지로 1 W 아래

    def test_keymap_and_gcode(self):
        c = Console()
        self.assertTrue(any("돌려 보기" in r[1] for r in HW_KEYMAP))
        self.assertEqual(c.gcode("turn", deg=400), ["TURN A=180.0"])  # 전선 꼬임 한도
        self.assertEqual(c.gcode("view_light", x=1, y=2, r=6), ["VIEW_LIGHT X=1.0 Y=2.0 R=6.0"])
        self.assertIn("[gcode_macro TURN]", c.klipper_macros())

    def test_turntable_pod_in_layout(self):
        lay = make_layout()
        pod = next(b for b in lay.boxes if "회전 받침 방수 통" in b.name)
        self.assertGreaterEqual(pod.lo[2], 0)  # 다 내려가도 수조 바닥 위
        self.assertEqual(pod.hi[2] - pod.lo[2], TURN_POD[1])
        self.assertEqual(lay.problems(), [])

    def test_klipper_cfgs_have_turn(self):
        from snss_battery.printer import klipper_cfg

        self.assertIn("[manual_stepper turn]", klipper_cfg())


if __name__ == "__main__":
    unittest.main()
