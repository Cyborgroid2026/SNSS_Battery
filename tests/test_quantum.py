import math
import shutil
import tempfile
import unittest
from pathlib import Path

from snss_battery.quantum import QuantumModule, analytic_volume_mm3, charge, module_layers, scaling


class QuantumChargeTest(unittest.TestCase):
    def test_single_molecule_rabi(self):
        r = charge(1)  # 광자 1개 ↔ 분자 1개: 완전 전달 시간 π/2
        self.assertAlmostEqual(r.tau, math.pi / 2, delta=0.02)
        self.assertAlmostEqual(r.energy, 1.0, delta=1e-3)

    def test_collective_speedup(self):
        rows, a = scaling((4, 16, 64))
        self.assertGreater(rows[-1].advantage, rows[0].advantage)  # 분자가 많을수록 병렬 대비 이점 증가
        self.assertGreater(a, 0.3)  # 충전 시간이 N 에 따라 줄어듦

    def test_ergotropy_bounded(self):
        for n in (2, 8, 32):
            r = charge(n)
            self.assertLessEqual(r.ergotropy, r.energy + 1e-12)
            self.assertGreater(r.ergotropy, 0)

    def test_module_is_metal_free(self):
        from snss_battery.materials import NONMETALS
        from snss_battery.quantum import MODULE_ELEMENTS

        for name, mat, _, _ in module_layers():
            self.assertTrue(MODULE_ELEMENTS[mat] <= NONMETALS, f"{name}: {MODULE_ELEMENTS[mat]}")

    def test_module_geometry(self):
        layers = module_layers()
        self.assertEqual(len(layers), 35)
        act = [t for n, _, _, t in layers if n == "활성층"][0]
        self.assertAlmostEqual(act * 1e6, 590 / (2 * 1.49), places=6)  # 반파장 공진기
        self.assertGreater(QuantumModule().n_molecules, 1e14)


@unittest.skipUnless(shutil.which("cargo") and shutil.which("dotnet"), "Rust·.NET 도구 필요")
class QuantumCrossLanguageTest(unittest.TestCase):
    def test_quantum_three_way(self):
        from snss_battery.crosscheck import quantum_check

        for lang, r in quantum_check()["languages"].items():
            self.assertNotIn("error", r)
            self.assertTrue(r["ok"], lang)

    def test_step_generation(self):
        from snss_battery.cadcheck import generate

        with tempfile.TemporaryDirectory() as tmp:
            generate(Path(tmp))
            for name in ("qmodule_rust.step", "qmodule_csharp.step"):
                text = (Path(tmp) / name).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("ISO-10303-21;"))
                self.assertGreaterEqual(text.count("MANIFOLD_SOLID_BREP"), 35)
            self.assertAlmostEqual(analytic_volume_mm3(), 737.665424, places=5)


if __name__ == "__main__":
    unittest.main()
