from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import JsonProjectRepository


SAMPLE_SOURCE = {
    "sourceName": "长沙市统计局",
    "url": "https://example.gov.cn/tjj",
    "documentId": None,
    "artifactId": None,
    "quote": "2025 年末全市常住人口 820 万人",
}


def _make_scenario(client: TestClient) -> tuple[str, str]:
    project = client.post("/api/projects", json={"name": "字段值测试", "city": "长沙", "cityId": "changsha"}).json()
    scenario = client.post(f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}).json()
    return project["id"], scenario["id"]


class FieldValueApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.client = TestClient(create_app(self.repository))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _seed_suggestion(self, project_id: str, scenario_id: str, field_id: str = "C3", value=820):
        return self.repository.save_field_suggestion(
            scenario_id, field_id, value, SAMPLE_SOURCE
        )

    def test_get_values_merges_current_value_and_suggestion(self):
        project_id, scenario_id = _make_scenario(self.client)
        self._seed_suggestion(project_id, scenario_id)

        response = self.client.get(f"/api/projects/{project_id}/scenarios/{scenario_id}/values")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["scenarioId"], scenario_id)
        by_id = {field["fieldId"]: field for field in body["fields"]}
        # 自动爬虫字段：有建议值，当前值仍是基准值
        self.assertEqual(by_id["C3"]["valueState"], "suggestion_ready")
        self.assertEqual(by_id["C3"]["suggestedValue"], 820)
        self.assertEqual(by_id["C3"]["suggestedSource"]["sourceName"], "长沙市统计局")
        self.assertIsNotNone(by_id["C3"]["suggestedAt"])
        self.assertEqual(by_id["C3"]["currentValue"], 1000)
        # valueType 必须透传：前端依赖它区分文本/数字控件。
        # C1 城市名称是 string，若缺失会退化成数字输入框并把文本值当数字处理（历史缺陷）。
        self.assertEqual(by_id["C1"]["valueType"], "string")
        self.assertEqual(by_id["C3"]["valueType"], "number")
        for field in body["fields"]:
            self.assertIn("valueType", field, field["fieldId"])
        # 无建议值的爬虫字段状态为 empty
        self.assertEqual(by_id["C10"]["valueState"], "empty")
        self.assertIsNone(by_id["C10"]["suggestedValue"])
        # 内部填写字段不展示建议值状态
        self.assertEqual(by_id["C12"]["valueState"], "manual")
        # 公式字段只读且无建议值
        self.assertEqual(by_id["C9"]["valueState"], "formula")
        self.assertTrue(by_id["C9"]["readOnly"])

    def test_accept_suggestion_writes_value_marks_accepted_and_stales_scenario(self):
        project_id, scenario_id = _make_scenario(self.client)
        self.client.post(f"/api/projects/{project_id}/scenarios/{scenario_id}/calculate")
        self._seed_suggestion(project_id, scenario_id)

        response = self.client.post(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/C3/accept-suggestion"
        )

        self.assertEqual(response.status_code, 200)
        accepted = response.json()
        self.assertEqual(accepted["valueState"], "accepted")
        self.assertEqual(accepted["currentValue"], 820)
        self.assertEqual(accepted["suggestedValue"], 820)
        scenario = self.client.get(f"/api/projects/{project_id}/scenarios/{scenario_id}").json()
        self.assertEqual(scenario["inputs"]["C3"], 820)
        self.assertEqual(scenario["status"], "stale")

    def test_unaccepted_suggestion_never_participates_in_calculation(self):
        project_id, scenario_id = _make_scenario(self.client)
        self._seed_suggestion(project_id, scenario_id, "P1", 88)

        calculation = self.client.post(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/calculate"
        )

        self.assertEqual(calculation.status_code, 200)
        parameters = calculation.json()["parameters"]
        # 建议值 88 未被采用，计算仍使用基准值 50
        self.assertEqual(parameters["P1"], 50)

    def test_manual_patch_on_crawler_field_marks_overridden_and_keeps_suggestion(self):
        project_id, scenario_id = _make_scenario(self.client)
        self._seed_suggestion(project_id, scenario_id)

        response = self.client.patch(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/C3",
            json={"value": 850},
        )

        self.assertEqual(response.status_code, 200)
        field = response.json()
        self.assertEqual(field["valueState"], "overridden")
        self.assertEqual(field["currentValue"], 850)
        # 建议值与来源继续保留
        self.assertEqual(field["suggestedValue"], 820)
        self.assertEqual(field["suggestedSource"]["sourceName"], "长沙市统计局")
        scenario = self.client.get(f"/api/projects/{project_id}/scenarios/{scenario_id}").json()
        self.assertEqual(scenario["inputs"]["C3"], 850)

    def test_manual_patch_allows_empty_value_for_fieldwork_fields(self):
        project_id, scenario_id = _make_scenario(self.client)

        response = self.client.patch(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/S1",
            json={"value": None},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["valueState"], "manual")
        scenario = self.client.get(f"/api/projects/{project_id}/scenarios/{scenario_id}").json()
        self.assertIsNone(scenario["inputs"]["S1"])

    def test_patch_rejects_formula_and_unknown_and_enum_violations(self):
        project_id, scenario_id = _make_scenario(self.client)

        formula = self.client.patch(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/P3", json={"value": 0.5}
        )
        self.assertEqual(formula.status_code, 400)
        self.assertEqual(formula.json()["error"]["code"], "FORMULA_FIELD_READ_ONLY")

        unknown = self.client.patch(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/X1", json={"value": 1}
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unknown.json()["error"]["code"], "UNKNOWN_FIELD")

        enum = self.client.patch(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/Z5", json={"value": "理想"}
        )
        self.assertEqual(enum.status_code, 400)
        self.assertEqual(enum.json()["error"]["code"], "INVALID_FIELD_VALUE")

    def test_accept_without_suggestion_is_reported(self):
        project_id, scenario_id = _make_scenario(self.client)

        response = self.client.post(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/C3/accept-suggestion"
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "SUGGESTION_NOT_AVAILABLE")

    def test_history_records_suggestion_accept_and_override_in_order(self):
        project_id, scenario_id = _make_scenario(self.client)
        self._seed_suggestion(project_id, scenario_id, "C3", 820)
        self.client.post(f"/api/projects/{project_id}/scenarios/{scenario_id}/values/C3/accept-suggestion")
        self.client.patch(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/C3", json={"value": 850}
        )

        history = self.repository.list_field_value_history(scenario_id, "C3")

        self.assertEqual(
            [(entry["action"], entry["newValue"]) for entry in history],
            [
                ("suggestion_updated", 820),
                ("accepted", 820),
                ("overridden", 850),
            ],
        )

    def test_new_suggestion_after_override_resets_state_to_ready(self):
        project_id, scenario_id = _make_scenario(self.client)
        self._seed_suggestion(project_id, scenario_id, "C3", 820)
        self.client.patch(
            f"/api/projects/{project_id}/scenarios/{scenario_id}/values/C3", json={"value": 850}
        )

        self.repository.save_field_suggestion(scenario_id, "C3", 831, SAMPLE_SOURCE)

        values = self.client.get(f"/api/projects/{project_id}/scenarios/{scenario_id}/values").json()
        by_id = {field["fieldId"]: field for field in values["fields"]}
        self.assertEqual(by_id["C3"]["valueState"], "suggestion_ready")
        self.assertEqual(by_id["C3"]["suggestedValue"], 831)
        # 手工值不被新建议值覆盖
        self.assertEqual(by_id["C3"]["currentValue"], 850)

    def test_city_values_alias_resolves_main_scenario(self):
        project_id, scenario_id = _make_scenario(self.client)

        response = self.client.get("/api/cities/changsha/values")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["cityId"], "changsha")
        self.assertEqual(body["scenarioId"], scenario_id)
        field_ids = {field["fieldId"] for field in body["fields"]}
        self.assertIn("C3", field_ids)
        self.assertIn("P1", field_ids)

    def test_city_values_alias_unknown_city_returns_404(self):
        response = self.client.get("/api/cities/unknown-city/values")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    def test_city_patch_alias_updates_main_scenario_value(self):
        _make_scenario(self.client)

        response = self.client.patch("/api/cities/changsha/values/C3", json={"value": 850})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["currentValue"], 850)
        values = self.client.get("/api/cities/changsha/values").json()
        by_id = {field["fieldId"]: field for field in values["fields"]}
        self.assertEqual(by_id["C3"]["currentValue"], 850)


if __name__ == "__main__":
    unittest.main()
