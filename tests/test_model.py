import unittest

from snss_battery import (
    ArtificialCellStack, CellGeometry, GrapheneLCDispersion, Phase, SalineSolution,
    assess, cycle_cc, max_power_point, sterile_normal_saline, suggest_limits,
)
from snss_battery.electrolyte import debye_length_nm, nacl_conductivity
from snss_battery.materials import Membrane, Selectivity, audit


class SalineTest(unittest.TestCase):
    def test_normal_saline(self):
        s = sterile_normal_saline()
        self.assertAlmostEqual(s.molarity, 0.154, delta=0.003)
        self.assertAlmostEqual(s.conductivity_s_per_m, 1.56, delta=0.05)
        self.assertAlmostEqual(s.debye_length_nm, 0.77, delta=0.02)

    def test_conductivity_monotonic(self):
        self.assertLess(nacl_conductivity(0.002), nacl_conductivity(0.154))
        self.assertGreater(nacl_conductivity(0.154, 37), nacl_conductivity(0.154, 25))
        self.assertGreater(debye_length_nm(0.001), debye_length_nm(0.1))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            SalineSolution(0)


class AssemblyTest(unittest.TestCase):
    def test_saline_crystallizes_lc_go(self):
        # 생리식염수(154 mM) > CCC(44 mM), 액정 농도 이상 → 정렬 막 형성
        rep = assess(GrapheneLCDispersion(go_mg_per_ml=5.0), 0.154)
        self.assertEqual(rep.phase, Phase.ALIGNED_GEL)
        self.assertTrue(rep.forms_membrane)

    def test_low_salt_stays_liquid_crystal(self):
        self.assertEqual(assess(GrapheneLCDispersion(5.0), 0.01).phase, Phase.NEMATIC)
        self.assertEqual(assess(GrapheneLCDispersion(0.05), 0.01).phase, Phase.ISOTROPIC)

    def test_dilute_go_aggregates_disordered(self):
        self.assertEqual(assess(GrapheneLCDispersion(0.1), 0.154).phase, Phase.AGGREGATED)

    def test_polymer_stabilization_raises_ccc(self):
        self.assertEqual(assess(GrapheneLCDispersion(5.0, ccc_mm=300), 0.154).phase, Phase.NEMATIC)


class StackTest(unittest.TestCase):
    def test_assembled_state_is_discharged(self):
        s = ArtificialCellStack()
        self.assertEqual(s.open_circuit_voltage(), 0.0)
        self.assertEqual(s.state_of_charge, 0.0)

    def test_charging_builds_gradient_and_voltage(self):
        s = ArtificialCellStack()
        for _ in range(100):
            s.step(-1e-4, 10)
        self.assertLess(s.c_dilute, s.c0)
        self.assertGreater(s.c_concentrated, s.c0)
        self.assertAlmostEqual(s.c_dilute + s.c_concentrated, 2 * s.c0)
        self.assertGreater(s.open_circuit_voltage(), 0)
        self.assertGreater(s.terminal_voltage(-1e-4), s.terminal_voltage(1e-4))

    def test_series_scaling(self):
        a, b = ArtificialCellStack(n_pairs=5), ArtificialCellStack(n_pairs=10)
        for s in (a, b):
            s.x, s.q = 0.1, 0.0
        self.assertAlmostEqual(b.open_circuit_voltage(), 2 * a.open_circuit_voltage())

    def test_self_discharge(self):
        s = ArtificialCellStack()
        s.x = 0.1
        s.step(0.0, 3600 * 24)
        self.assertLess(s.x, 0.1)

    def test_dilute_cell_resistance_grows(self):
        s = ArtificialCellStack()
        r0 = s.internal_resistance()
        s.x = s.max_shift
        self.assertGreater(s.internal_resistance(), 5 * r0)

    def test_capacity_scales_with_volume(self):
        small = ArtificialCellStack(geometry=CellGeometry(2.0, 0.5))
        big = ArtificialCellStack(geometry=CellGeometry(2.0, 1.0))
        self.assertAlmostEqual(big.ionic_capacity_c, 2 * small.ionic_capacity_c)

    def test_wrong_membrane_type(self):
        with self.assertRaises(ValueError):
            ArtificialCellStack(cation_membrane="go_pdda")

    def test_metal_free(self):
        self.assertTrue(all(line.ok for line in ArtificialCellStack().audit()))
        bad = audit([("은 전극", frozenset({"Ag", "Cl"}), False)])
        self.assertFalse(bad[0].ok)

    def test_selectivity_drops_with_salt(self):
        m = Membrane("t", "t", Selectivity.CATION, frozenset({"C"}), 0.9, 0.3, 5, 1e-11, 5)
        self.assertGreater(m.selectivity_at(0.01), m.selectivity_at(1.0))


class CyclingTest(unittest.TestCase):
    def test_rechargeable_cycles(self):
        s = ArtificialCellStack()
        v_max, v_min = suggest_limits(s, 1e-4)
        res = cycle_cc(s, 1e-4, v_max, v_min, n_cycles=3, dt_s=20)
        self.assertEqual(len(res.cycles), 3)
        for c in res.cycles[1:]:
            self.assertGreater(c.discharge_mah, 0.5 * s.capacity_mah)
            self.assertGreater(c.coulombic_efficiency, 0.95)
            self.assertLessEqual(c.coulombic_efficiency, 1.0 + 1e-9)

    def test_mpp(self):
        s = ArtificialCellStack()
        s.x, s.q = 0.1, 1.0
        i, p = max_power_point(s)
        self.assertAlmostEqual(p, s.open_circuit_voltage() ** 2 / (4 * s.internal_resistance()))


if __name__ == "__main__":
    unittest.main()
