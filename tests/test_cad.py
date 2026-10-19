import math
import struct
import tempfile
import unittest
from pathlib import Path

from snss_battery import BottleGelBattery, BottleSpec, GelFormation, cycle_cc, suggest_limits
from snss_battery.cad import BottleDesign, BottleDesignParams
from snss_battery.drawing import assembly_sheet, cut_sheet, export_all


def _stl_volume(path: Path) -> float:
    data = path.read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    vol = 0.0
    for k in range(n):
        v = struct.unpack("<12f", data[84 + 50 * k: 84 + 50 * k + 48])[3:]
        a, b, c = v[0:3], v[3:6], v[6:9]
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    return vol


class BottleTest(unittest.TestCase):
    def setUp(self):
        self.b = BottleGelBattery()

    def test_geometry_from_500ml_bottle(self):
        self.assertAlmostEqual(self.b.bottle.fill_height_mm * self.b.bottle.inner_area_cm2 / 10, 500, places=6)
        self.assertLessEqual(self.b.active_height_mm, self.b.gel_height_mm)
        self.assertEqual(self.b.stack.n_pairs, int(self.b.gel_height_mm // (1.0 + 0.013)))

    def test_born_charged(self):
        s = self.b.stack
        self.assertAlmostEqual(s.c_concentrated / s.c_dilute, 20, places=6)
        self.assertAlmostEqual(s.c_dilute + s.c_concentrated, 2 * s.c0)
        self.assertGreater(s.open_circuit_voltage(), 1.0)
        no_gradient = BottleGelBattery(formation=GelFormation(concentration_ratio=1))
        self.assertAlmostEqual(no_gradient.stack.open_circuit_voltage(), 0.0)

    def test_shelf_aging(self):
        v0 = self.b.stack.open_circuit_voltage()
        self.b.age(self.b.shelf_time_constant_days)
        self.assertLess(self.b.stack.open_circuit_voltage(), v0)

    def test_shrinkage_reduces_gel(self):
        shrunk = BottleGelBattery(formation=GelFormation(shrinkage=0.1))
        self.assertLess(shrunk.gel_diameter_mm, self.b.gel_diameter_mm)
        self.assertLess(shrunk.stack.n_pairs, self.b.stack.n_pairs)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            GelFormation(concentration_ratio=0.5)
        with self.assertRaises(ValueError):
            BottleSpec(fill_volume_ml=900)  # 몸통보다 높음

    def test_connect_then_recharge(self):
        s = self.b.stack
        v_max, v_min = suggest_limits(s, 1e-4)
        self.assertLess(v_min, s.open_circuit_voltage())
        self.assertGreater(v_max, s.open_circuit_voltage())
        res = cycle_cc(s, 1e-4, v_max, v_min, n_cycles=1, dt_s=10, born_charged=True)
        self.assertTrue(res.cycles[0].born)
        self.assertGreater(res.cycles[0].discharge_mah, 0.1)  # 충전 없이 바로 방전
        self.assertGreater(res.cycles[1].coulombic_efficiency, 0.9)

    def test_no_separate_electrode(self):
        # 별도 전극 없음: 접촉면 그래핀 = 결정 안 GO 의 도메인 벽 한 장 분량
        b, s = self.b, self.b.stack
        expect = b.go_mass_g * 1000 / (2 * s.n_pairs)
        self.assertAlmostEqual(s.electrode_mass_mg, expect, places=6)
        more = BottleGelBattery(formation=GelFormation(surface_go_mg_cm2=5.0))
        self.assertGreater(more.stack.capacity_mah, s.capacity_mah)


class DesignTest(unittest.TestCase):
    def setUp(self):
        self.d = BottleDesign(BottleGelBattery())

    def test_cut_line_above_gel_below_shoulder(self):
        self.assertGreater(self.d.cut_z, self.d.gel_top_z)
        self.assertLess(self.d.cut_z, self.d.battery.bottle.body_height_mm)
        with self.assertRaises(ValueError):
            BottleDesign(BottleGelBattery(), BottleDesignParams(cut_margin_mm=40))

    def test_layer_bands(self):
        bands = self.d.layer_bands()
        self.assertEqual(len(bands), 2 * self.d.battery.stack.n_pairs)
        self.assertAlmostEqual(bands[-1][1] + self.d.battery.stack.aem.thickness_um / 1000, self.d.block_height,
                               places=6)

    def test_metal_free(self):
        self.assertTrue(all(a.ok for a in self.d.audit()))

    def test_export_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            names = {f.name for f in export_all(self.d, tmp)}
            for n in ("assembly_drawing.dxf", "assembly_drawing.pdf", "template_1to1.dxf", "template_1to1.pdf",
                      "crystal_block.stl", "saline_bottle_cut.stl", "battery.scad", "materials.csv"):
                self.assertIn(n, names)
            dxf = (Path(tmp) / "assembly_drawing.dxf").read_text(encoding="ascii")
            self.assertIn("AC1009", dxf)
            self.assertTrue(dxf.rstrip().endswith("EOF"))
            r, h = self.d.gel_radius, self.d.block_height
            polygon_area = 0.5 * 64 * r * r * math.sin(2 * math.pi / 64)
            self.assertAlmostEqual(_stl_volume(Path(tmp) / "stl" / "crystal_block.stl"), polygon_area * h, delta=1.0)

    def test_drawings_fit_sheet(self):
        for vol, dia in ((100, 45), (500, 72), (1000, 90)):
            d = BottleDesign(BottleGelBattery(BottleSpec(fill_volume_ml=vol, outer_diameter_mm=dia,
                                                         body_height_mm=200 if vol > 500 else 150)))
            for sh in (assembly_sheet(d), cut_sheet(d)):
                for p in sh.prims:
                    if p.kind == "line":
                        x1, y1, x2, y2 = p.data
                        for x, y in ((x1, y1), (x2, y2)):
                            self.assertTrue(-1 <= x <= sh.width + 1 and -1 <= y <= sh.height + 1,
                                            f"{vol} mL: ({x:.1f},{y:.1f}) 용지 밖")


class WebTest(unittest.TestCase):
    def test_build_site(self):
        import json

        from snss_battery.web import build_site

        bat = BottleGelBattery(BottleSpec(fill_volume_ml=100, outer_diameter_mm=45))
        with tempfile.TemporaryDirectory() as tmp:
            index = build_site(bat, BottleDesign(bat), tmp, n_cycles=1, dt_s=60)
            self.assertNotIn("__DATA__", index.read_text(encoding="utf-8"))
            model = json.loads((Path(tmp) / "model.json").read_text(encoding="utf-8"))
            self.assertEqual(len(model["gel"]["bands"]), 2 * bat.stack.n_pairs)
            for f in ("img/cycles.png", "img/structure.png", "cad/assembly_drawing.png", "cad/template_1to1.png",
                      "vendor/three/three.module.js", "vendor/three/OrbitControls.js"):
                self.assertTrue((Path(tmp) / f).exists(), f)


class ExperimentLogTest(unittest.TestCase):
    def test_add_read_delete(self):
        from snss_battery.web import add_experiment, delete_experiment, read_experiments

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "exp" / "log.jsonl"
            rec = add_experiment(log, {"elapsed_h": "12", "voltage_v": "0.8", "state": "일부 결정", "note": "갈색"})
            self.assertEqual(rec["elapsed_h"], 12.0)
            self.assertIsNone(rec["current_ma"])
            self.assertEqual(len(read_experiments(log)), 1)
            with self.assertRaises(ValueError):
                add_experiment(log, {"voltage_v": "abc"})
            self.assertTrue(delete_experiment(log, rec["id"]))
            self.assertEqual(read_experiments(log), [])

    def test_server_api(self):
        import json
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen

        from snss_battery.web import _make_handler

        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir()
            (site / "index.html").write_text("SNSS", encoding="utf-8")
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(site, Path(tmp) / "log.jsonl"))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                req = Request(base + "/api/experiments", data=json.dumps({"elapsed_h": 1, "voltage_v": 2}).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(req) as r:
                    self.assertEqual(r.status, 201)
                with urlopen(base + "/api/experiments") as r:
                    self.assertEqual(json.loads(r.read())[0]["voltage_v"], 2.0)
                with urlopen(base + "/") as r:
                    self.assertIn("SNSS", r.read().decode())
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
