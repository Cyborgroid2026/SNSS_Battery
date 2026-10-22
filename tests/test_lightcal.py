import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from snss_battery import lightcal as C
from snss_battery.lightrun import PX_MM, export_job, layer_images, run_job, schedule
from snss_battery.lightsculpt import LightSculptorSpec, Photo, light_job


class TestCalibration(unittest.TestCase):
    def test_fit_recovers_truth(self):
        truth = Photo(eps_go=12.0, ec_mj_cm2=28.0, e_red_mj_cm2=1400.0, e_graft_mj_cm2=380.0, n_graft_max=4.0)
        with tempfile.TemporaryDirectory() as d:
            cal = C.fit_calibration(C.synthetic_measurements(Path(d) / "m.csv", truth, noise=0.0))
        ph = cal["photo"]
        self.assertAlmostEqual(ph["ec_mj_cm2"], 28.0, delta=0.5)
        self.assertAlmostEqual(ph["eps_go"], 12.0, delta=0.2)
        self.assertAlmostEqual(ph["e_red_mj_cm2"], 1400.0, delta=20)
        self.assertAlmostEqual(ph["e_graft_mj_cm2"], 380.0, delta=8)
        self.assertAlmostEqual(ph["n_graft_max"], 4.0, delta=0.1)
        self.assertAlmostEqual(ph["theta_mem"], 0.301, delta=0.005)  # 로그 상승 50 % 기준의 정의

    def test_calibrated_spec_changes_layer(self):
        cal = {"photo": {"eps_go": 7.5}}
        s0, s1 = LightSculptorSpec(), C.calibrated_spec(cal)
        self.assertGreater(s1.dp_mm(), s0.dp_mm())  # GO 가 덜 검으면 빛이 깊이 → 층이 두꺼워짐
        self.assertGreater(s1.layer_mm, s0.layer_mm)

    def test_coupon_files(self):
        with tempfile.TemporaryDirectory() as d:
            f = C.write_coupon(d)
            for k in "ABC":
                self.assertTrue((f / f"coupon_{k}.png").exists())
            rows = (f / "measurements.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1 + 3 * 12)

    def test_empty_measurements_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = C.write_coupon(d)
            with self.assertRaises(ValueError):
                C.fit_calibration(f / "measurements.csv")


class TestMachinePackage(unittest.TestCase):
    def test_pixel_orientation(self):
        """+y 끝 칸은 그림 위쪽 행, +x 끝 칸은 오른쪽 열."""
        E = np.zeros((10, 10, 1), dtype=np.float32)
        E[9, 9, 0] = 100.0  # +x, +y 구석
        _, a, _, ma, _ = next(layer_images(E, np.zeros_like(E), (-5, -5), 1.0))
        ys, xs = np.nonzero(a)
        n = a.shape[0]
        self.assertEqual(ma, 100.0)
        self.assertLess(ys.mean(), n / 2)
        self.assertGreater(xs.mean(), n / 2)
        self.assertAlmostEqual(len(xs), (1.0 / PX_MM) ** 2, delta=60)  # 1 mm 칸 = 20×20 픽셀

    def test_schedule_swaps_ink_before_life(self):
        spec = LightSculptorSpec()
        rows = schedule([3600.0] * 40, [0.0] * 40, spec)
        life = spec.ink_life_h() * 3600 * 0.95
        starts = [0] + [i for i, r in enumerate(rows) if r["swap_ink"]] + [len(rows)]
        for a, b in zip(starts, starts[1:]):  # 잉크 한 통으로 하는 층들이 수명 안에 끝남
            self.assertLessEqual(sum(r["t405_s"] + r["t530_s"] + r["recoat_s"] for r in rows[a:b]), life)
        self.assertGreater(len(starts), 3)
        self.assertTrue(all(b["z_drop_mm"] > a["z_drop_mm"] for a, b in zip(rows, rows[1:])))

    def test_export_and_dry_run(self):
        job = light_job("coupon", 6.0, LightSculptorSpec())
        with tempfile.TemporaryDirectory() as d:
            meta = export_job(job, d)
            self.assertTrue((Path(d) / "job.gcode").read_text(encoding="utf-8").startswith("; SNSS 빛 조각가"))
            self.assertIn("[z_tilt]", (Path(d) / "printer_light.cfg").read_text(encoding="utf-8"))
            n405 = len(list((Path(d) / "slices" / "405").glob("*.png")))
            self.assertEqual(n405, len(meta["layers"]))
            self.assertEqual(json.loads((Path(d) / "job.json").read_text(encoding="utf-8"))["px_mm"], PX_MM)
            self.assertIn("실행 시간표", run_job(d)["text"])


if __name__ == "__main__":
    unittest.main()
