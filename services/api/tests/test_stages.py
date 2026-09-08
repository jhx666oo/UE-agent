import unittest

from app.domain.u1.stages import build_stage_sequence, stage_for_month


class StageTests(unittest.TestCase):
    def test_baseline_has_one_preparation_six_startup_and_seventeen_platform_months(self):
        sequence = build_stage_sequence(1, 6, 17)
        self.assertEqual(
            sequence,
            ("筹备期", "启动期", "启动期", "启动期", "启动期", "启动期", "启动期", *(["平台期"] * 17)),
        )

    def test_stage_boundaries_match_excel_month_numbers(self):
        self.assertEqual(stage_for_month(1, 1, 6), "筹备期")
        self.assertEqual(stage_for_month(2, 1, 6), "启动期")
        self.assertEqual(stage_for_month(7, 1, 6), "启动期")
        self.assertEqual(stage_for_month(8, 1, 6), "平台期")


if __name__ == "__main__":
    unittest.main()
