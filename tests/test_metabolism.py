import shutil
import unittest

from snss_battery import BottleGelBattery
from snss_battery.metabolism import (LED, FuelSupply, IncandescentBulb, LightPump, Metabolism, best_parallel,
                                     evaluate_lighting, operating_current, simulate)


class LoadTest(unittest.TestCase):
    def test_led_curve(self):
        led = LED()
        self.assertAlmostEqual(led.diode_voltage(1e-3), 1.85, delta=1e-6)
        self.assertAlmostEqual(led.voltage(1e-3), 1.85 + 0.47, delta=1e-6)

    def test_operating_point_balances(self):
        led = LED()
        i = operating_current(10.0, 150.0, led)
        self.assertAlmostEqual(10.0 - 150.0 * i, led.voltage(i), delta=1e-9)

    def test_bulb_hot_resistance(self):
        bulb = IncandescentBulb()
        self.assertAlmostEqual(bulb.voltage(0.3), 2.5, delta=0.05)  # 정격점
        self.assertLess(bulb.resistance(0.01), bulb.resistance(0.3))  # 차가우면 저항 작음


class MetabolismTest(unittest.TestCase):
    def setUp(self):
        self.bat = BottleGelBattery()

    def test_no_food_no_lasting_light(self):
        """먹이가 없으면(빛·연료 끔) 저장분이 바닥나 LED 가 꺼진다 — 에너지가 무에서 생기지 않음."""
        starving = Metabolism(light=LightPump(enabled=False), fuel=FuelSupply(enabled=False))
        run = simulate(self.bat, starving, LED(), hours=24, dt_s=60)
        self.assertIsNotNone(run.first_off_h())

    def test_food_extends_light(self):
        fed = simulate(self.bat, Metabolism(), LED(), hours=48, dt_s=60)
        starving = simulate(self.bat, Metabolism(light=LightPump(enabled=False), fuel=FuelSupply(enabled=False)),
                            LED(), hours=48, dt_s=60)
        self.assertGreater(fed.on_fraction(), starving.on_fraction())

    def test_light_pump_scales_with_irradiance(self):
        a = LightPump(irradiance_mw_cm2=1).pump_a(self.bat)
        b = LightPump(irradiance_mw_cm2=10).pump_a(self.bat)
        self.assertAlmostEqual(b / a, 10.0, places=9)

    def test_bulb_needs_parallel_slices(self):
        k = best_parallel(self.bat, Metabolism(), IncandescentBulb())
        self.assertGreater(k, 1)

    def test_power_balance_verdict(self):
        v = evaluate_lighting(self.bat, hours=24)
        sustain = sum(w for name, w in v.budget_w.items() if "증발" not in name)
        self.assertLess(sustain, v.bulb_need_w)  # 대사 전력으로 꼬마전구 지속 불가
        self.assertGreater(sustain, v.led_need_w)  # LED 희미한 점등은 가능


@unittest.skipUnless(shutil.which("cargo") and shutil.which("dotnet"), "Rust·.NET 도구 필요")
class CrossLanguageTest(unittest.TestCase):
    def test_three_implementations_agree(self):
        from snss_battery.crosscheck import run_all

        rep = run_all()
        for lang, r in rep["languages"].items():
            self.assertNotIn("error", r, f"{lang}: {r.get('error')}")
            self.assertTrue(r["ok"], f"{lang} 불일치")


if __name__ == "__main__":
    unittest.main()
