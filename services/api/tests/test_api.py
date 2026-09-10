import tempfile
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import JsonProjectRepository


class U1ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.client = TestClient(create_app(repository))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_health_and_model_catalog(self):
        health = self.client.get("/api/health")
        model = self.client.get("/api/model/u1")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["modelVersion"], "u1-excel-v2.1-parity")
        self.assertEqual(model.status_code, 200)
        self.assertEqual(len(model.json()["parameters"]), 75)
        self.assertEqual(model.json()["baselineInputs"]["P1"], 50)

    def test_error_payload_includes_field_and_request_id(self):
        """PRD 16.8：错误返回 code / message / field / requestId。"""
        invalid = self.client.get("/api/dashboard/overview?period=99")
        self.assertEqual(invalid.status_code, 400)
        error = invalid.json()["error"]
        self.assertEqual(error["code"], "INVALID_QUERY")
        self.assertEqual(error["field"], "period")
        self.assertTrue(error["requestId"])

        missing = self.client.get("/api/projects/not-exist")
        self.assertEqual(missing.status_code, 404)
        not_found = missing.json()["error"]
        self.assertEqual(not_found["code"], "NOT_FOUND")
        self.assertTrue(not_found["requestId"])
        self.assertNotIn("field", not_found)

    def test_create_calculate_and_reload_scenario(self):
        project_response = self.client.post(
            "/api/projects",
            json={"name": "长沙 U1 试算", "city": "长沙", "baseMonth": "2026-09", "stationMode": "自营"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        scenario_response = self.client.post(
            f"/api/projects/{project_id}/scenarios",
            json={"name": "基准"},
        )
        self.assertEqual(scenario_response.status_code, 201)
        scenario_id = scenario_response.json()["id"]

        calculation = self.client.post(f"/api/projects/{project_id}/scenarios/{scenario_id}/calculate")
        self.assertEqual(calculation.status_code, 200)
        self.assertEqual(calculation.json()["status"], "ok")
        self.assertEqual(calculation.json()["headlineMetrics"]["payback_month"]["value"], 24)
        self.assertEqual(
            {issue["code"] for issue in calculation.json()["issues"]},
            {
                "SUSPECTED_CELL_REFERENCE",
                "SHARED_FORMULA_STRUCTURE",
                "DIV0_IN_SUMMARY",
                "CUMULATIVE_SERIES_SUM",
            },
        )

        reloaded = self.client.get(f"/api/projects/{project_id}/scenarios/{scenario_id}")
        self.assertEqual(reloaded.status_code, 200)
        self.assertEqual(reloaded.json()["result"]["modelVersion"], "u1-excel-v2.1-parity")

        second_calculation = self.client.post(f"/api/projects/{project_id}/scenarios/{scenario_id}/calculate")
        self.assertEqual(second_calculation.status_code, 200)
        snapshots = self.client.get(f"/api/projects/{project_id}/scenarios/{scenario_id}/snapshots")
        self.assertEqual(snapshots.status_code, 200)
        self.assertEqual(len(snapshots.json()), 2)
        self.assertNotEqual(snapshots.json()[0]["snapshotId"], snapshots.json()[1]["snapshotId"])

    def test_input_update_exposes_stale_state_and_preserves_snapshot_history(self):
        project = self.client.post("/api/projects", json={"name": "stale API 测试", "city": "长沙"}).json()
        scenario = self.client.post(f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}).json()
        calculation = self.client.post(f"/api/projects/{project['id']}/scenarios/{scenario['id']}/calculate")
        self.assertEqual(calculation.status_code, 200)

        updated = self.client.put(
            f"/api/projects/{project['id']}/scenarios/{scenario['id']}",
            json={"inputs": {"P1": 55}},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "stale")
        self.assertIsNone(updated.json()["resultSnapshotId"])
        self.assertIsNone(updated.json()["result"])
        snapshots = self.client.get(f"/api/projects/{project['id']}/scenarios/{scenario['id']}/snapshots")
        self.assertEqual(len(snapshots.json()), 1)

    def test_missing_project_and_required_input_are_explicit(self):
        missing = self.client.get("/api/projects/not-found")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "NOT_FOUND")

        project = self.client.post("/api/projects", json={"name": "缺失测试", "city": "长沙"}).json()
        scenario = self.client.post(
            f"/api/projects/{project['id']}/scenarios",
            json={"name": "缺 P1", "inputs": {"P1": None}},
        ).json()
        result = self.client.post(f"/api/projects/{project['id']}/scenarios/{scenario['id']}/calculate")
        self.assertEqual(result.status_code, 422)
        self.assertIn("MISSING_REQUIRED_INPUT", {issue["code"] for issue in result.json()["issues"]})


if __name__ == "__main__":
    unittest.main()
