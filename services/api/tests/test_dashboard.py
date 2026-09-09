import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.domain.dashboard.aggregator import (
    build_dashboard_overview,
    select_latest_valid_snapshot,
)
from app.main import create_app
from app.repository import JsonProjectRepository


def metric(value):
    return {"value": value, "status": "ok", "errorCode": None}


def snapshot(snapshot_id, calculated_at, status="calculated", payback=12, customers=100, revenue=1000, profit=200, investment=5000, issues=None):
    month = {
        "month": 12,
        "stage": "平台期",
        "signedCustomers": metric(customers),
        "totalRevenue": metric(revenue),
        "netProfit": metric(profit),
        "caregiverCost": metric(300),
        "salesCost": metric(100),
        "nurseCost": metric(50),
        "fixedCost": metric(150),
        "cumulativeCashFlow": metric(10000),
    }
    return {
        "snapshotId": snapshot_id,
        "projectId": "project-1",
        "scenarioId": "scenario-1",
        "calculatedAt": calculated_at,
        "status": status,
        "modelVersion": "test-v1",
        "resultSnapshot": {
            "status": "ok" if status in {"calculated", "confirmed"} else "blocked",
            "modelVersion": "test-v1",
            "headlineMetrics": {
                "payback_month": metric(payback),
                "platform_monthly_revenue": metric(revenue),
                "platform_monthly_net_profit": metric(profit),
                "initial_investment": metric(investment),
                "twenty_four_month_cumulative_net_profit": metric(profit * 24),
            },
            "months": [month],
            "issues": issues or [],
        },
    }


class DashboardAggregatorTests(unittest.TestCase):
    def test_selects_latest_calculated_or_confirmed_snapshot_by_calculated_at(self):
        city = {
            "cityId": "changsha",
            "cityName": "长沙",
            "snapshots": [
                snapshot("old-calculated", "2026-09-01T00:00:00+00:00"),
                snapshot("newest-calculated", "2026-09-02T00:00:00+00:00"),
                snapshot("blocked", "2026-09-03T00:00:00+00:00", status="blocked"),
            ],
        }

        selected = select_latest_valid_snapshot(city)

        self.assertEqual(selected.snapshot_id, "newest-calculated")
        self.assertTrue(select_latest_valid_snapshot({"snapshots": [snapshot("stale", "2026-09-02T00:00:00+00:00", status="stale")] }).has_valid_result is False)
        self.assertTrue(select_latest_valid_snapshot({"snapshots": [snapshot("blocked", "2026-09-02T00:00:00+00:00", status="blocked")] }).is_excluded)

    def test_aggregates_numeric_metrics_and_uses_payback_median(self):
        projects = [
            {"id": "project-1", "city": "长沙", "district": None, "scenarios": []},
            {"id": "project-2", "city": "株洲", "district": None, "scenarios": []},
        ]
        snapshots = [
            snapshot("changsha-result", "2026-09-02T00:00:00+00:00", customers=100, revenue=1000, profit=200, investment=5000, payback=12),
            {**snapshot("zhuzhou-result", "2026-09-03T00:00:00+00:00", customers=50, revenue=600, profit=100, investment=3000, payback=24), "projectId": "project-2", "scenarioId": "scenario-2"},
        ]

        overview = build_dashboard_overview(projects, snapshots, period=24)

        self.assertEqual(overview["summary"]["eligibleCityCount"], 2)
        self.assertEqual(overview["summary"]["targetCustomers"], 150)
        self.assertEqual(overview["summary"]["monthlyRevenue"], 1600)
        self.assertEqual(overview["summary"]["monthlyNetProfit"], 300)
        self.assertEqual(overview["summary"]["initialInvestment"], 8000)
        self.assertEqual(overview["summary"]["paybackMedian"], 18)
        self.assertNotEqual(overview["summary"].get("paybackTotal"), 36)


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.client = TestClient(create_app(repository))
        for city in ("长沙", "株洲"):
            project = repository.create_project({"name": f"{city} 项目", "city": city})
            scenario_record = repository.create_scenario(project["id"], {"name": "基准", "inputs": {}})
            repository.save_calculation(
                project["id"],
                scenario_record["id"],
                {
                    "modelVersion": "test-v1",
                    "status": "ok",
                    "headlineMetrics": {"payback_month": metric(12)},
                    "months": [],
                    "issues": [],
                },
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_global_city_and_compare_scopes_filter_server_side(self):
        global_response = self.client.get("/api/dashboard/overview?scope=global&period=12")
        city_response = self.client.get("/api/dashboard/overview?scope=city&cityIds=%E9%95%BF%E6%B2%99")
        compare_response = self.client.get("/api/dashboard/compare?cityIds=%E9%95%BF%E6%B2%99,%E6%A0%AA%E6%B4%B2&period=24")

        self.assertEqual(global_response.status_code, 200)
        self.assertEqual(len(global_response.json()["cities"]), 2)
        self.assertEqual(city_response.status_code, 200)
        self.assertEqual([city["cityName"] for city in city_response.json()["cities"]], ["长沙"])
        self.assertEqual(compare_response.status_code, 200)
        self.assertEqual(len(compare_response.json()["cities"]), 2)


if __name__ == "__main__":
    unittest.main()
