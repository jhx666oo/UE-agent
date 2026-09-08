import unittest

from app.domain.u1.engine import calculate_u1
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


if __name__ == "__main__":
    unittest.main()
