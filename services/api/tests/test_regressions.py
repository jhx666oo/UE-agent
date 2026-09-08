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
        self.assertAlmostEqual(metrics["max_cash_deficit"].value, -501000, places=6)
        self.assertAlmostEqual(metrics["platform_monthly_net_profit"].value, 220138554186.338, delta=1e-3)
        self.assertAlmostEqual(metrics["platform_net_margin"].value, 0.998178803388089, places=12)
        self.assertAlmostEqual(
            metrics["twenty_four_month_cumulative_net_profit"].value,
            48161870185060.4,
            delta=0.1,
        )
        self.assertEqual(metrics["break_even_customers"].value, 23)
        self.assertAlmostEqual(metrics["initial_investment"].value, 459000, places=6)

    def test_stage_summary_preserves_excel_div0_and_known_issue_set(self):
        self.assertEqual(self.result.stage_summary["筹备期"]["net_margin"].status, "formula_error")
        self.assertEqual(self.result.stage_summary["筹备期"]["net_margin"].error_code, "DIV0")
        self.assertEqual(
            {issue.code for issue in self.result.issues},
            {"SUSPECTED_CELL_REFERENCE", "DIV0_IN_SUMMARY", "CUMULATIVE_SERIES_SUM"},
        )

    def test_selected_months_match_workbook_cache(self):
        month_one, month_two, month_eight, month_twenty_four = (
            self.result.months[0],
            self.result.months[1],
            self.result.months[7],
            self.result.months[23],
        )
        self.assertAlmostEqual(month_one.cumulative_cash_flow.value, -501000, places=6)
        self.assertAlmostEqual(month_two.signed_customers.value, 18849589.8507394, places=6)
        self.assertAlmostEqual(month_eight.net_profit.value, 220138554186.338, delta=1e-3)
        self.assertEqual(month_twenty_four.cash_flow_positive_month.value, 24)
        self.assertEqual(month_twenty_four.break_even_customers.value, 23)


if __name__ == "__main__":
    unittest.main()
