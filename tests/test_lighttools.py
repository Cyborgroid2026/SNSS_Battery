import json
import tempfile
import unittest
from pathlib import Path

from snss_battery.layout import make_light_layout
from snss_battery.lightrun import export_job
from snss_battery.lightsculpt import LightSculptorSpec, light_job
from snss_battery.lighttools import ToolSpec, plan_tools, syringe_job, write_syringe_job


class TestTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = LightSculptorSpec()
        cls.job = light_job("coupon", 6.0, cls.spec)

    def test_layout_with_gantry_clear(self):
        lay = make_light_layout(self.spec, tools=True)
        self.assertEqual(lay.problems(), [])
        names = [b.name for b in lay.boxes]
        self.assertTrue(any(n.startswith("도구 걸이 T1") for n in names))
        self.assertTrue(lay.parked())  # 빛을 쬘 때 주차한 갠트리

    def test_tools_metal_free(self):
        self.assertEqual(ToolSpec().wet_metals(), [])

    def test_injection_dopes_n_cells(self):
        r = plan_tools(self.job)
        self.assertEqual(r["problems"], [])
        self.assertGreater(r["n_eff"], 0)
        self.assertGreater(r["prediction"]["energy_j"], self.job["prediction"]["energy_j"])
        self.assertEqual(sum(p["cells"] for p in r["phases"]), r["n_inject"])

    def test_syringe_carve_gcode(self):
        sj = syringe_job(self.job["piece"], "carve", self.spec, center=(0, 0, 3), radius=1.5)
        with tempfile.TemporaryDirectory() as d:
            res = write_syringe_job(sj, self.spec, d)
            g = Path(res["gcode"]).read_text(encoding="utf-8").splitlines()
        self.assertIn("TOOL_PICK T=T2  ; 흡입 주사기 (깎기)", g)
        self.assertNotIn("G28", g)
        self.assertFalse(any(x.startswith("FILL ") for x in g))
        self.assertEqual(g[-1], "SC2_LIGHT_PLANE  ; 받침을 다시 빛 면으로")

    def test_height_limit_guard(self):
        ts = ToolSpec()
        ts.head.tool_len = 200.0  # 도구 면이 너무 낮으면 쿠폰도 못 다룸
        sj = syringe_job(self.job["piece"], "carve", self.spec, center=(0, 0, 3), radius=1.0)
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            write_syringe_job(sj, self.spec, d, ts)

    def test_export_includes_injection(self):
        r = plan_tools(self.job)
        with tempfile.TemporaryDirectory() as d:
            meta = export_job(self.job, d, slices=False, tools=r)
            files = sorted(p.name for p in (Path(d) / "tools").glob("inject_*.gcode"))
            done = sum(x["tool_before"]["cells"] for x in meta["layers"] if x.get("tool_before")) + \
                sum(x["cells"] for x in meta["tool_after"])
            self.assertEqual(len(files), len(r["phases"]))
            self.assertEqual(done, r["n_inject"])
            self.assertIn("INJECT UL=", (Path(d) / "tools" / files[0]).read_text(encoding="utf-8"))
            self.assertTrue(json.loads((Path(d) / "job.json").read_text(encoding="utf-8"))["layers"])


if __name__ == "__main__":
    unittest.main()
