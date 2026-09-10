import unittest

from app.domain.u1.engine import calculate_u1
from app.domain.u1.spec import load_json_spec


class BaselineRegressionTests(unittest.TestCase):
    def setUp(self):
        self.values = dict(load_json_spec("fixtures/u1-baseline.json")["inputs"])
        self.result = calculate_u1(self.values)

    def test_headline_metrics_match_selected_workbook_cache(self):
        metrics = self.result.headline_metrics
        self.assertEqual(metrics["payback_month"].value, 24)
        self.assertAlmostEqual(metrics["max_cash_deficit"].value, -556639.6098248562, places=6)
        self.assertAlmostEqual(metrics["platform_monthly_net_profit"].value, 516361.56244001834, delta=1e-6)
        self.assertAlmostEqual(metrics["platform_net_margin"].value, 0.7676567660079704, places=12)
        self.assertAlmostEqual(
            metrics["twenty_four_month_cumulative_net_profit"].value,
            102744139.8594375,
            delta=0.1,
        )
        self.assertEqual(metrics["break_even_customers"].value, 23)
        self.assertAlmostEqual(metrics["initial_investment"].value, 459000, places=6)

    def test_stage_summary_preserves_excel_div0_and_known_issue_set(self):
        self.assertEqual(self.result.stage_summary["筹备期"]["net_margin"].status, "formula_error")
        self.assertEqual(self.result.stage_summary["筹备期"]["net_margin"].error_code, "DIV0")
        self.assertEqual(
            {issue.code for issue in self.result.issues},
            {
                "SUSPECTED_CELL_REFERENCE",
                "SHARED_FORMULA_STRUCTURE",
                "DIV0_IN_SUMMARY",
                "CUMULATIVE_SERIES_SUM",
            },
        )

    def test_selected_months_match_workbook_cache(self):
        month_one, month_two, month_eight, month_twenty_four = (
            self.result.months[0],
            self.result.months[1],
            self.result.months[7],
            self.result.months[23],
        )
        self.assertAlmostEqual(month_one.cumulative_cash_flow.value, -501000, places=6)
        self.assertAlmostEqual(month_two.signed_customers.value, 57.491145560693234, places=6)
        self.assertAlmostEqual(month_eight.net_profit.value, 516361.5624400183, delta=1e-6)
        self.assertEqual(month_twenty_four.cash_flow_positive_month.value, 24)
        self.assertEqual(month_twenty_four.break_even_customers.value, 23)

    def test_station_coverage_limit_uses_c8_and_stays_in_a_sane_order_of_magnitude(self):
        """S5 末项必须用 C8（80岁以上失能率），而不是原 Excel 误抄的 C9（人口密度）。

        修正前 S5 约 2.26 亿，站点覆盖客户 1.13 亿人、平台期月收入 2205 亿元，
        属量纲失配造成的数量级错误；修正后单站点覆盖客户应落在数百人量级。
        """
        platform_customers = self.result.months[23].signed_customers.value
        self.assertAlmostEqual(platform_customers, 344.9468733641594, places=6)
        self.assertLess(platform_customers, 1000)  # 单站点覆盖客户数不应超过千人量级

    def test_s3_uses_commute_deduction_not_the_population_capacity_formula(self):
        """S3（护理员日工作时段）应为「10 小时 − 往返通勤」，不再与 S5 共用公式。

        基准输入 S1=3、S2=20 → S3 = 10 - 3/20*2 = 9.7 小时。
        原实现误与 S5 同构算出 689.89，单位是小时，量纲失配。
        """
        self.assertAlmostEqual(self.result.parameters["S3"], 9.7, places=9)
        self.assertAlmostEqual(self.result.parameters["S5"], 689.8937467283188, places=6)
        # 两字段不再同值，确认 S3/S5 共用公式疑点已消除
        self.assertNotAlmostEqual(self.result.parameters["S3"], self.result.parameters["S5"], places=3)


if __name__ == "__main__":
    unittest.main()
