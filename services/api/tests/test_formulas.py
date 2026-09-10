import unittest

from app.domain.u1.formulas import (
    CAREGIVER_DAILY_SHIFT_HOURS,
    safe_ratio,
    station_coverage_disabled_limit,
    station_daily_caregiver_hours,
)


class FormulaTests(unittest.TestCase):
    def test_station_daily_hours_is_shift_minus_round_trip_commute(self):
        """S3 = 日工作总时段 10 小时 − 往返通勤小时（S1/S2*2）。

        基准输入 S1=3km、S2=20km/h，单程 0.15h、往返 0.3h，S3 = 9.7 小时。
        原实现误与 S5 共用人口容量结构，得出 689.89（单位却是小时），量纲失配。
        """
        values = {"S1": 3, "S2": 20}
        self.assertAlmostEqual(station_daily_caregiver_hours(values), 9.7, places=9)
        self.assertLess(station_daily_caregiver_hours(values), CAREGIVER_DAILY_SHIFT_HOURS)

    def test_station_daily_hours_does_not_depend_on_population_or_disability_rates(self):
        """S3 只由通勤扣减决定，与人口密度、失能率无关（不再与 S5 同构）。"""
        base = {"S1": 3, "S2": 20, "C9": 20000, "C4": 0.2, "C6": 0.002, "C7": 0.008, "C8": 0.025}
        mutated = {**base, "C9": 2_000_000, "C4": 0.9, "C8": 0.5}
        self.assertAlmostEqual(
            station_daily_caregiver_hours(base),
            station_daily_caregiver_hours(mutated),
            places=9,
        )

    def test_station_daily_hours_rejects_non_positive_commute_speed(self):
        """S2（通勤时速）为 0 或负数时必须抛错，而不是静默兜底或崩溃。"""
        with self.assertRaises(ValueError):
            station_daily_caregiver_hours({"S1": 3, "S2": 0})
        with self.assertRaises(ValueError):
            station_daily_caregiver_hours({"S1": 3, "S2": -5})

    def test_station_coverage_limit_uses_c8_not_the_original_e12_reference(self):
        """S5 末项已按业务确认由 C9（区域人口密度）改为 C8（80岁以上失能率）。

        原公式沿用 E12 引用会得到 226,195,078（约 2.26 亿人），属量纲失配的数量级
        错误；修正后为 689.89，落在合理范围。
        """
        values = {
            "S1": 3,
            "C4": 0.2,
            "C6": 0.002,
            "C7": 0.008,
            "C8": 0.025,
            "C9": 20000,
        }
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
