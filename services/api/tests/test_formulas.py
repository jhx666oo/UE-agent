import unittest

from app.domain.u1.formulas import (
    safe_ratio,
    station_coverage_disabled_limit,
    station_daily_caregiver_hours,
)


class FormulaTests(unittest.TestCase):
    def test_station_coverage_limit_uses_c8_not_the_original_e12_reference(self):
        """S5 末项已按业务确认由 C9（区域人口密度）改为 C8（80岁以上失能率）。

        原公式沿用 E12 引用会得到 226,195,078（约 2.26 亿人），属量纲失配的数量级
        错误；修正后与 S3 同值 689.89，落在合理范围。
        """
        values = {
            "S1": 3,
            "C4": 0.2,
            "C6": 0.002,
            "C7": 0.008,
            "C8": 0.025,
            "C9": 20000,
        }
        self.assertAlmostEqual(station_daily_caregiver_hours(values), 689.893746728319, places=9)
        self.assertAlmostEqual(station_coverage_disabled_limit(values), 689.893746728319, places=9)

    def test_station_coverage_limit_no_longer_depends_on_population_density_weight(self):
        """回归护栏：把人口密度放大 100 倍不得使 S5 出现数量级跳变。

        原公式把 C9 作为末项时，C9 同时出现在公因子与加权项里，改动 C9 会产生
        二次放大的虚高结果。
        """
        base = {"S1": 3, "C4": 0.2, "C6": 0.002, "C7": 0.008, "C8": 0.025, "C9": 20000}
        inflated = {**base, "C9": 2_000_000}
        self.assertAlmostEqual(
            station_coverage_disabled_limit(inflated) / station_coverage_disabled_limit(base),
            100.0,
            places=6,
        )

    def test_zero_denominator_is_a_formula_error(self):
        result = safe_ratio(-48250, 0)
        self.assertEqual(result.status, "formula_error")
        self.assertEqual(result.error_code, "DIV0")
        self.assertIsNone(result.value)


if __name__ == "__main__":
    unittest.main()
