import unittest

from app.domain.u1.engine import DEFAULT_GOVERNMENT_RELATIONS_COST, calculate_u1
from app.domain.u1.spec import load_json_spec


def load_baseline_inputs() -> dict[str, object]:
    payload = load_json_spec("fixtures/u1-baseline.json")
    return dict(payload["inputs"])


class BaselineEngineTests(unittest.TestCase):
    def test_calculates_24_months_and_preserves_baseline_stage_transition(self):
        result = calculate_u1(load_baseline_inputs())
        self.assertEqual(len(result.months), 24)
        self.assertEqual(result.months[0].stage, "筹备期")
        self.assertEqual(result.months[1].stage, "启动期")
        self.assertEqual(result.months[7].stage, "平台期")
        self.assertEqual(result.months[0].signed_customers.value, 0)
        self.assertAlmostEqual(result.months[1].single_customer_month_revenue.value, 1950)

    def test_required_missing_input_blocks_only_when_a_used_driver_is_missing(self):
        values = load_baseline_inputs()
        values["P1"] = None
        result = calculate_u1(values)
        self.assertEqual(result.status, "blocked")
        self.assertIn("MISSING_REQUIRED_INPUT", {issue.code for issue in result.issues})
        missing_issue = next(issue for issue in result.issues if issue.code == "MISSING_REQUIRED_INPUT")
        self.assertEqual(missing_issue.excelCell, "控制台!E17")

    def test_b12_is_a_default_constant_and_never_blocks_the_calculation(self):
        """B12 是只读常量参数，缺省时必须走默认值 5000，而不是把整个测算卡住。"""
        values = load_baseline_inputs()
        values["B12"] = None
        result = calculate_u1(values)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.parameters["B12"], DEFAULT_GOVERNMENT_RELATIONS_COST)
        self.assertNotIn("MISSING_REQUIRED_INPUT", {issue.code for issue in result.issues})

    def test_b12_default_matches_an_explicit_5000_input(self):
        """显式传 5000 与走默认值必须得到完全一致的结果，保证 parity 不被破坏。"""
        explicit = load_baseline_inputs()
        explicit["B12"] = 5000
        defaulted = load_baseline_inputs()
        defaulted["B12"] = None
        explicit_result = calculate_u1(explicit)
        defaulted_result = calculate_u1(defaulted)
        self.assertEqual(explicit_result.status, "ok")
        for explicit_month, defaulted_month in zip(explicit_result.months, defaulted_result.months):
            self.assertAlmostEqual(
                explicit_month.fixed_cost.value,
                defaulted_month.fixed_cost.value,
                places=9,
            )
            self.assertAlmostEqual(
                explicit_month.net_profit.value,
                defaulted_month.net_profit.value,
                places=6,
            )

    def test_b12_explicit_value_still_overrides_the_default(self):
        """用户/上游显式给值时应优先，默认值只用于补齐缺失。"""
        values = load_baseline_inputs()
        values["B12"] = 8000
        result = calculate_u1(values)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.parameters["B12"], 8000)


if __name__ == "__main__":
    unittest.main()
