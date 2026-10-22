import shutil
import unittest

from snss_battery.crosscheck import light_python


class LightReferenceTest(unittest.TestCase):
    def test_reference_matches_light_tests(self):
        import json

        from snss_battery.crosscheck import LIGHT_CASES

        case = json.loads(LIGHT_CASES.read_text(encoding="utf-8"))["cases"][0]
        r = light_python(case)
        self.assertAlmostEqual(r["layer_mm"], 0.301, places=3)
        self.assertLess(r["membrane_leak"], 0.3)
        # 첫 기둥: 막 칸(4, 11) 은 θ·E_red 아래, 세포질은 E_red 이상
        for k in range(12):
            d = r[f"col0.D405.{k}"]
            if k in (4, 11):
                self.assertLessEqual(d, 300.0)
            else:
                self.assertGreaterEqual(d, 999.0)


@unittest.skipUnless(shutil.which("cargo") and shutil.which("dotnet"), "Rust·.NET 도구 필요")
class LightCrossLanguageTest(unittest.TestCase):
    def test_light_three_way(self):
        from snss_battery.crosscheck import light_check

        for lang, r in light_check()["languages"].items():
            self.assertNotIn("error", r)
            self.assertTrue(r["ok"], f"{lang}: {r['bad'][:5]}")


if __name__ == "__main__":
    unittest.main()
