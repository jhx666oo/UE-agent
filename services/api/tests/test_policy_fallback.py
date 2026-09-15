from __future__ import annotations

import http.server
import os
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.crawlers.runner import CrawlError, crawl_source
from app.main import create_app
from app.repository import JsonProjectRepository
from app.sqlite_repository import SqliteProjectRepository


class _FallbackHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/challenge":
            body = b"<html><body>please enable javascript</body></html>"
            self.send_response(412)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _serve() -> tuple[str, int, http.server.ThreadingHTTPServer]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    return str(host), int(port), server


class BrowserFallbackCrawlerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.raw_dir = Path(self.temp_dir.name) / "raw_sources"
        self.host, self.port, self.server = _serve()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def test_http_412_exposes_browser_fallback_metadata(self):
        with self.assertRaises(CrawlError) as context:
            crawl_source(
                f"http://{self.host}:{self.port}/challenge",
                self.raw_dir,
                allow_private=True,
            )

        error = context.exception
        self.assertEqual(error.http_status, 412)
        self.assertEqual(error.error_code, "HTTP_412_BROWSER_REQUIRED")
        self.assertEqual(error.fallback_action, "browser_search")
        self.assertEqual(error.fallback_reason, "js_challenge")

    def test_private_url_does_not_expose_browser_fallback(self):
        with self.assertRaises(CrawlError) as context:
            crawl_source("http://127.0.0.1/policy", self.raw_dir)

        self.assertIsNone(context.exception.fallback_action)


class BrowserFallbackApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.host, self.port, self.server = _serve()
        self.source = self.repository.create_data_source(
            {
                "cityId": "成都",
                "name": "成都医保局",
                "url": f"http://{self.host}:{self.port}/challenge",
            }
        )
        self.previous_token = os.environ.get("UE_AGENT_AGENT_TOKEN")
        os.environ["UE_AGENT_AGENT_TOKEN"] = "test-token"
        app = create_app(self.repository)
        app.state.crawl_allow_private = True
        self.client = TestClient(app)

    def tearDown(self):
        if self.previous_token is None:
            os.environ.pop("UE_AGENT_AGENT_TOKEN", None)
        else:
            os.environ["UE_AGENT_AGENT_TOKEN"] = self.previous_token
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def _browser_payload(self) -> dict[str, object]:
        return {
            "cityId": "成都",
            "sourceId": self.source["id"],
            "requestedUrl": self.source["url"],
            "finalUrl": "https://www.chengdu.gov.cn/policy/mirror",
            "title": "成都市长期护理保险政策",
            "content": "成都市长期护理保险政策正文。基金支付比例为80%。",
            "contentType": "text/plain; charset=utf-8",
            "fetchMode": "workbuddy_browser",
        }

    def test_agent_fetch_failure_returns_structured_browser_fallback(self):
        response = self.client.post(
            "/api/policies/fetch-requests",
            headers={"x-ue-agent-token": "test-token"},
            json={
                "requests": [
                    {
                        "url": self.source["url"],
                        "cityId": "成都",
                        "sourceId": self.source["id"],
                        "name": self.source["name"],
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()["results"][0]
        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["httpStatus"], 412)
        self.assertEqual(item["errorCode"], "HTTP_412_BROWSER_REQUIRED")
        self.assertEqual(item["fallbackAction"], "browser_search")
        self.assertEqual(item["fallbackReason"], "js_challenge")
        source = self.client.get("/api/policies/sources").json()[0]
        self.assertEqual(source["fallbackAction"], "browser_search")

    def test_browser_artifact_is_saved_and_idempotent(self):
        headers = {"x-ue-agent-token": "test-token"}
        first = self.client.post(
            "/api/policies/browser-artifacts",
            headers=headers,
            json=self._browser_payload(),
        )
        second = self.client.post(
            "/api/policies/browser-artifacts",
            headers=headers,
            json=self._browser_payload(),
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        first_artifact = first.json()["artifact"]
        second_artifact = second.json()["artifact"]
        self.assertEqual(first_artifact["status"], "success")
        self.assertEqual(first_artifact["fetchMode"], "workbuddy_browser")
        self.assertEqual(first_artifact["changeStatus"], "first_fetch")
        self.assertTrue((Path(self.temp_dir.name) / first_artifact["storedPath"]).is_file())
        self.assertEqual(first_artifact["artifactId"], second_artifact["artifactId"])
        self.assertTrue(second.json()["idempotent"])
        content = self.client.get(
            f"/api/policies/artifacts/{first_artifact['artifactId']}/content"
        )
        self.assertIn("基金支付比例为80%", content.text)
        source = self.client.get("/api/policies/sources").json()[0]
        self.assertEqual(source["status"], "active")
        self.assertIsNone(source.get("fallbackAction"))

    def test_browser_artifact_requires_agent_token(self):
        response = self.client.post(
            "/api/policies/browser-artifacts",
            json=self._browser_payload(),
        )

        self.assertEqual(response.status_code, 401)


class BrowserFallbackSqliteApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = SqliteProjectRepository(Path(self.temp_dir.name) / "ue-agent.sqlite3")
        self.source = repository.create_data_source(
            {
                "cityId": "成都",
                "name": "成都医保局",
                "url": "https://ybj.chengdu.gov.cn/policy",
            }
        )
        self.previous_token = os.environ.get("UE_AGENT_AGENT_TOKEN")
        os.environ["UE_AGENT_AGENT_TOKEN"] = "test-token"
        self.client = TestClient(create_app(repository))

    def tearDown(self):
        if self.previous_token is None:
            os.environ.pop("UE_AGENT_AGENT_TOKEN", None)
        else:
            os.environ["UE_AGENT_AGENT_TOKEN"] = self.previous_token
        self.temp_dir.cleanup()

    def test_browser_artifact_round_trips_through_sqlite(self):
        response = self.client.post(
            "/api/policies/browser-artifacts",
            headers={"x-ue-agent-token": "test-token"},
            json={
                "cityId": "成都",
                "sourceId": self.source["id"],
                "requestedUrl": self.source["url"],
                "finalUrl": "https://www.chengdu.gov.cn/policy/mirror",
                "content": "官方政策正文：基金支付比例为80%。",
                "fetchMode": "workbuddy_browser",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        artifact = response.json()["artifact"]
        self.assertEqual(artifact["fetchMode"], "workbuddy_browser")
        persisted = self.client.get(f"/api/policies/artifacts/{artifact['artifactId']}").json()
        self.assertEqual(persisted["sha256"], artifact["sha256"])
        source = self.client.get("/api/policies/sources").json()[0]
        self.assertEqual(source["lastFetchMode"], "workbuddy_browser")
        self.assertIsNone(source["fallbackAction"])


if __name__ == "__main__":
    unittest.main()
