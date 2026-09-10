"""项目删除功能测试（需求待办 2026-09-10 需求一）。

重点：级联删除场景/快照/字段值/历史，政策来源与抓取记录按城市保留；不存在返回 404。
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import JsonProjectRepository
from app.sqlite_repository import SqliteProjectRepository, initialize_database

SAMPLE_SOURCE = {
    "sourceName": "长沙市统计局",
    "url": "https://example.gov.cn/tjj",
    "documentId": None,
    "artifactId": None,
    "quote": "2025 年末全市常住人口 820 万人",
}


class DeleteProjectSqliteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = initialize_database(Path(self.temp_dir.name) / "ue-agent.sqlite3")
        self.repository = SqliteProjectRepository(self.path)
        self.client = TestClient(create_app(self.repository))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed(self) -> tuple[str, str]:
        project = self.client.post(
            "/api/projects", json={"name": "待删城市", "city": "株洲", "cityId": "zhuzhou"}
        ).json()
        scenario = self.client.post(f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}).json()
        self.client.post(f"/api/projects/{project['id']}/scenarios/{scenario['id']}/calculate")
        self.repository.save_field_suggestion(scenario["id"], "C3", 820, SAMPLE_SOURCE)
        # 同城数据来源与抓取记录应保留
        self.repository.create_data_source(
            {"cityId": "株洲", "name": "株洲统计局", "kind": "web", "url": "https://example.com"}
        )
        return str(project["id"]), str(scenario["id"])

    def _counts(self, table: str) -> int:
        with sqlite3.connect(self.path) as connection:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_delete_project_cascades_and_keeps_city_policy_sources(self) -> None:
        project_id, scenario_id = self._seed()

        response = self.client.delete(f"/api/projects/{project_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], True)
        # 项目与场景数据全部清理
        self.assertEqual(self._counts("projects"), 0)
        self.assertEqual(self._counts("scenarios"), 0)
        self.assertEqual(self._counts("calculation_snapshots"), 0)
        self.assertEqual(self._counts("scenario_field_values"), 0)
        self.assertEqual(self._counts("scenario_field_value_history"), 0)
        # 政策来源按城市保留
        self.assertEqual(self._counts("data_sources"), 1)
        sources = self.repository.list_data_sources("株洲")
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["name"], "株洲统计局")

    def test_delete_missing_project_returns_404(self) -> None:
        response = self.client.delete("/api/projects/project-not-exists")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    def test_deleted_project_disappears_from_dashboard(self) -> None:
        project_id, _ = self._seed()
        self.client.delete(f"/api/projects/{project_id}")

        overview = self.client.get("/api/dashboard/overview").json()
        city_names = [city["cityName"] for city in overview["cities"]]
        self.assertNotIn("株洲", city_names)


class DeleteProjectJsonRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.client = TestClient(create_app(self.repository))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_delete_project_removes_scenario_and_value_rows(self) -> None:
        project = self.client.post(
            "/api/projects", json={"name": "待删城市", "city": "长沙", "cityId": "changsha"}
        ).json()
        scenario = self.client.post(f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}).json()
        self.repository.save_field_suggestion(scenario["id"], "C3", 820, SAMPLE_SOURCE)

        response = self.client.delete(f"/api/projects/{project['id']}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repository.list_projects(), [])
        self.assertEqual(self.repository.list_field_values(scenario["id"]), [])
        self.assertEqual(self.repository.list_snapshots(project_id=project["id"]), [])
        with self.assertRaises(KeyError):
            self.repository.get_project(project["id"])

    def test_delete_missing_project_returns_404(self) -> None:
        response = self.client.delete("/api/projects/project-not-exists")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
