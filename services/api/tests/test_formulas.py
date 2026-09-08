import unittest

from app.domain.u1.formulas import (
    safe_ratio,
    station_coverage_disabled_limit,
    station_daily_caregiver_hours,
)


class FormulaTests(unittest.TestCase):
    def test_excel_parity_helpers_preserve_the_suspected_e32_reference(self):
        values = {
            "S1": 3,
            "C4": 0.2,
            "C6": 0.002,
            "C7": 0.008,
            "C8": 0.025,
            "C9": 20000,
        }
        self.assertAlmostEqual(station_daily_caregiver_hours(values), 689.893746728319, places=9)
        self.assertAlmostEqual(station_coverage_disabled_limit(values), 226195078.208873, places=6)

    def test_zero_denominator_is_a_formula_error(self):
        result = safe_ratio(-48250, 0)
        self.assertEqual(result.status, "formula_error")
        self.assertEqual(result.error_code, "DIV0")
        self.assertIsNone(result.value)


if __name__ == "__main__":
    unittest.main()
