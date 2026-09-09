from __future__ import annotations

import http.server
import tempfile
import threading
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import JsonProjectRepository


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/policy":
            body = (
                "<html><head><title>长期护理保险政策</title></head>"
                "<body>单小时服务单价为 60 元，基金支付比例 80%。</body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()


class PolicyApiTests(unittest.TestCase):
    """政策域按 PRD v1.1 运行：官网来源 + 一键抓取 + 建议值；Demo 不提供手动上传。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        app = create_app(self.repository)
        app.state.crawl_allow_private = True
        self.client = TestClient(app)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def _make_source(self, url: str) -> dict:
        response = self.client.post(
            "/api/policies/sources",
            json={"cityId": "city-a", "name": "官方来源", "kind": "government", "url": url},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_manual_upload_endpoint_is_removed_in_demo(self) -> None:
        response = self.client.post(
            "/api/policies/documents/upload",
            data={"cityId": "city-a", "source": "local-review"},
            files={"file": ("policy.pdf", b"local policy", "application/pdf")},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "UPLOAD_NOT_AVAILABLE")

    def test_crawl_suggestions_stay_out_of_inputs_until_accepted(self) -> None:
        source = self._make_source(f"{self.base}/policy")
        project = self.repository.create_project({"name": "City A", "city": "城市A", "cityId": "city-a"})
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})

        artifact = self.client.post(f"/api/policies/sources/{source['id']}/crawl")
        self.assertEqual(artifact.status_code, 200, artifact.text)

        overview = self.client.get("/api/policies/overview")
        self.assertEqual(overview.status_code, 200)
        # 建议值不影响城市输入（PRD 15.2：suggestion_ready 计入建议值数量）
        unchanged = self.repository.get_scenario(project["id"], scenario["id"])
        self.assertEqual(unchanged["inputs"]["P1"], 50)
        values = {row["fieldId"]: row for row in self.repository.list_field_values(scenario["id"])}
        self.assertEqual(values["P1"]["suggestedValue"], 60)
        self.assertEqual(values["P1"]["valueState"], "suggestion_ready")

    def test_city_detail_lists_sources_and_artifacts(self) -> None:
        source = self._make_source(f"{self.base}/policy")
        self.client.post(f"/api/policies/sources/{source['id']}/crawl")

        detail = self.client.get("/api/policies/cities/city-a")

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["dataSources"][0]["id"], source["id"])
        self.assertEqual(detail.json()["dataSources"][0]["lastHttpStatus"], 200)

    def test_source_url_must_be_public_http(self) -> None:
        source = self._make_source("http://192.168.0.10/policy")
        response = self.client.post(f"/api/policies/sources/{source['id']}/crawl")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "POLICY_SOURCE_FETCH_FAILED")
        # 失败记录保留，来源标记 error，不删除任何已有数据
        artifacts = self.repository.list_crawl_artifacts(source_id=source["id"])
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["status"], "failed")
        self.assertEqual(self.client.get("/api/policies/sources").json()[0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
