"""政策导出接口测试（PRD 16.7 / 11.12 / 22.3）。

重点：建议值、实际值与覆盖值分列导出，非法参数返回稳定错误码。
"""
from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

from fastapi.testclient import TestClient

from app.main import create_app
from app.sqlite_repository import SqliteProjectRepository, initialize_database


class PolicyExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = initialize_database(Path(self.temp_dir.name) / "ue-agent.sqlite3")
        self.repository = SqliteProjectRepository(self.path)
        self.client = TestClient(create_app(self.repository))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed(self) -> dict[str, object]:
        source = self.repository.create_data_source(
            {"cityId": "长沙", "name": "长沙医保局", "kind": "web", "url": "https://example.com"}
        )
        self.repository.create_crawl_artifact(
            {
                "sourceId": source["id"],
                "cityId": "长沙",
                "requestedUrl": "https://example.com",
                "finalUrl": "https://example.com",
                "httpStatus": 200,
                "contentType": "text/html",
                "contentLength": 12,
                "sha256": "abc123",
                "title": "测试政策",
                "changeStatus": "first_fetch",
                "status": "success",
            }
        )
        return source

    def test_csv_field_export_contains_suggestion_columns(self) -> None:
        response = self.client.get("/api/policies/export?format=csv&dataset=fields")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        body = response.content.decode("utf-8-sig")
        for column in ("当前实际值", "建议值", "值状态", "建议来源", "建议采集时间"):
            self.assertIn(column, body)

    def test_csv_source_export_lists_seeded_source(self) -> None:
        source = self._seed()
        response = self.client.get("/api/policies/export?format=csv&dataset=sources")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8-sig")
        self.assertIn(str(source["id"]), body)
        self.assertIn("长沙医保局", body)

    def test_csv_artifact_export_uses_artifact_id(self) -> None:
        source = self._seed()
        artifacts = self.repository.list_crawl_artifacts(source_id=str(source["id"]))
        self.assertEqual(len(artifacts), 1)
        artifact_id = artifacts[0]["artifactId"]
        response = self.client.get("/api/policies/export?format=csv&dataset=artifacts")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8-sig")
        self.assertIn(artifact_id, body)
        self.assertIn("测试政策", body)

    def test_json_export_returns_complete_structure(self) -> None:
        self._seed()
        response = self.client.get("/api/policies/export?format=json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("exportedAt", payload)
        self.assertEqual(len(payload["sources"]), 1)
        self.assertEqual(len(payload["artifacts"]), 1)
        self.assertIn("fieldValues", payload)

    def test_export_filters_by_city(self) -> None:
        self._seed()
        response = self.client.get("/api/policies/export?format=json&cityId=岳阳")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["sources"]), 0)

    def test_unsupported_format_returns_400(self) -> None:
        response = self.client.get("/api/policies/export?format=xlsx")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_EXPORT_FORMAT")

    def test_unsupported_dataset_returns_400(self) -> None:
        response = self.client.get("/api/policies/export?format=csv&dataset=unknown")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_EXPORT_DATASET")


if __name__ == "__main__":
    unittest.main()
