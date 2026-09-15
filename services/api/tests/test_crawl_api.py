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


class _PolicyHandler(http.server.BaseHTTPRequestHandler):
    hits = 0

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):  # noqa: N802
        type(self).hits += 1
        if self.path == "/policy":
            body = (
                "<html><head><title>长沙市长期护理保险实施办法</title></head>"
                "<body>单小时服务单价为 60 元，基金支付比例 80%。</body></html>"
            ).encode("utf-8")
        elif self.path == "/policy-v2":
            body = (
                "<html><head><title>长沙市长期护理保险实施办法（修订）</title></head>"
                "<body>单小时服务单价调整为 66 元。</body></html>"
            ).encode("utf-8")
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve() -> tuple[str, int, http.server.ThreadingHTTPServer]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PolicyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server.server_address[0], server.server_address[1], server


class CrawlApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.repository = JsonProjectRepository(root / "projects.json")
        app = create_app(self.repository)
        # 测试用本地 HTTP 服务（127.0.0.1），显式放行本机地址；生产默认拒绝。
        app.state.crawl_allow_private = True
        self.client = TestClient(app)
        self.host, self.port, self.server = _serve()
        self.base = f"http://{self.host}:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def _make_source(self, url: str, **extra) -> dict:
        payload = {"cityId": "changsha", "name": "长沙市医保局", "url": url, "kind": "government"}
        payload.update(extra)
        response = self.client.post("/api/policies/sources", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_crawl_creates_artifact_with_fingerprint_and_first_fetch_mark(self):
        source = self._make_source(f"{self.base}/policy")

        response = self.client.post(f"/api/policies/sources/{source['id']}/crawl")

        self.assertEqual(response.status_code, 200, response.text)
        artifact = response.json()
        self.assertEqual(artifact["status"], "success")
        self.assertEqual(artifact["changeStatus"], "first_fetch")
        self.assertEqual(artifact["httpStatus"], 200)
        self.assertEqual(artifact["title"], "长沙市长期护理保险实施办法")
        self.assertEqual(artifact["contentType"], "text/html; charset=utf-8")
        self.assertTrue(artifact["storedPath"].startswith("raw_sources/"))
        self.assertTrue((Path(self.temp_dir.name) / artifact["storedPath"]).is_file())
        self.assertIsNotNone(artifact["sha256"])
        self.assertEqual(artifact["requestedUrl"], f"{self.base}/policy")
        # 来源状态更新
        updated_source = self.client.get("/api/policies/sources").json()[0]
        self.assertEqual(updated_source["status"], "active")
        self.assertIsNotNone(updated_source.get("lastFetchedAt"))
        self.assertEqual(updated_source.get("lastHttpStatus"), 200)

    def test_same_content_second_fetch_is_marked_unchanged_without_new_file(self):
        source = self._make_source(f"{self.base}/policy")
        first = self.client.post(f"/api/policies/sources/{source['id']}/crawl").json()

        second = self.client.post(f"/api/policies/sources/{source['id']}/crawl").json()

        self.assertEqual(second["changeStatus"], "unchanged")
        self.assertEqual(second["sha256"], first["sha256"])
        # 相同指纹不重复保存文件实体，但保留抓取记录
        self.assertEqual(second["storedPath"], first["storedPath"])
        artifacts = self.repository.list_crawl_artifacts(source_id=source["id"])
        self.assertEqual(len(artifacts), 2)

    def test_changed_content_is_marked_new_version(self):
        source = self._make_source(f"{self.base}/policy")
        self.client.post(f"/api/policies/sources/{source['id']}/crawl")

        self.repository.update_data_source(source["id"], {"url": f"{self.base}/policy-v2"})
        second = self.client.post(f"/api/policies/sources/{source['id']}/crawl").json()

        self.assertEqual(second["changeStatus"], "new_version")
        self.assertNotEqual(second["sha256"], second.get("previousSha256"))
        self.assertEqual(second["title"], "长沙市长期护理保险实施办法（修订）")

    def test_crawl_failure_saves_error_record_and_keeps_previous_success(self):
        source = self._make_source(f"{self.base}/policy")
        first = self.client.post(f"/api/policies/sources/{source['id']}/crawl").json()

        self.repository.update_data_source(source["id"], {"url": f"{self.base}/missing"})
        failed = self.client.post(f"/api/policies/sources/{source['id']}/crawl")

        self.assertEqual(failed.status_code, 502)
        body = failed.json()
        self.assertEqual(body["error"]["code"], "POLICY_SOURCE_FETCH_FAILED")
        # 失败也留抓取记录，且不删除上一次成功结果
        artifacts = self.repository.list_crawl_artifacts(source_id=source["id"])
        self.assertEqual(len(artifacts), 2)
        self.assertEqual(artifacts[-1]["status"], "failed")
        self.assertIsNone(artifacts[-1]["sha256"])
        self.assertIn("404", artifacts[-1]["errorMessage"])
        self.assertTrue((Path(self.temp_dir.name) / first["storedPath"]).is_file())

    def test_crawl_rejects_unknown_or_disabled_source(self):
        missing = self.client.post("/api/policies/sources/missing/crawl")
        self.assertEqual(missing.status_code, 404)

        source = self._make_source(f"{self.base}/policy", status="paused")
        disabled = self.client.post(f"/api/policies/sources/{source['id']}/crawl")
        self.assertEqual(disabled.status_code, 409)
        self.assertEqual(disabled.json()["error"]["code"], "POLICY_SOURCE_DISABLED")

    def test_crawl_rejects_source_without_url(self):
        source = self._make_source(None)
        response = self.client.post(f"/api/policies/sources/{source['id']}/crawl")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "POLICY_SOURCE_URL_REQUIRED")

    def test_crawl_generates_suggestions_bound_to_field_ids(self):
        source = self._make_source(f"{self.base}/policy")
        project = self.client.post(
            "/api/projects", json={"name": "建议值联动", "city": "长沙", "cityId": "changsha"}
        ).json()
        scenario = self.client.post(
            f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}
        ).json()

        response = self.client.post(f"/api/policies/sources/{source['id']}/crawl")

        artifact = response.json()
        suggestions = self.repository.list_field_values(scenario["id"])
        by_field = {row["fieldId"]: row for row in suggestions}
        # 页面包含“单小时服务单价为 60 元”与“基金支付比例 80%”
        self.assertIn("P1", by_field)
        self.assertEqual(by_field["P1"]["suggestedValue"], 60)
        self.assertIn("P2", by_field)
        self.assertEqual(by_field["P2"]["suggestedValue"], 0.8)
        self.assertEqual(by_field["P1"]["valueState"], "suggestion_ready")
        self.assertEqual(by_field["P1"]["suggestedSource"]["artifactId"], artifact["artifactId"])
        self.assertEqual(by_field["P1"]["suggestedSource"]["sourceName"], "长沙市医保局")
        # 建议值未采用前不写当前输入
        scenario_now = self.client.get(
            f"/api/projects/{project['id']}/scenarios/{scenario['id']}"
        ).json()
        self.assertEqual(scenario_now["inputs"]["P1"], 50)

    def test_regex_fallback_never_overwrites_existing_suggestion(self):
        """正则兜底只在字段没有建议值时写入，绝不覆盖已有结果。

        背景：正则只取第一处匹配、不看上下文，实测曾把统计公报里的
        「目录范围内基金支付比例 80.23%」（住院报销比例）当成 P2 写进去，
        并覆盖掉 AI 正确抽出的 0.7。夹具页写的是「基金支付比例 80%」，
        这里先放一个 0.7，抓取后必须仍是 0.7。
        """
        source = self._make_source(f"{self.base}/policy")
        project = self.client.post(
            "/api/projects", json={"name": "不覆盖", "city": "长沙", "cityId": "changsha"}
        ).json()
        scenario = self.client.post(
            f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}
        ).json()

        self.repository.save_field_suggestion(
            str(scenario["id"]),
            "P2",
            0.7,
            {"sourceName": "AI 抽取", "quote": "按单位职工参保政策参保的，基金支付比例为 70% 左右"},
        )

        self.client.post(f"/api/policies/sources/{source['id']}/crawl")

        by_field = {row["fieldId"]: row for row in self.repository.list_field_values(scenario["id"])}
        # P2 已有建议值 → 正则不得覆盖
        self.assertEqual(by_field["P2"]["suggestedValue"], 0.7)
        self.assertEqual(by_field["P2"]["suggestedSource"]["sourceName"], "AI 抽取")
        # P1 原本没有建议值 → 正则兜底仍可写入
        self.assertEqual(by_field["P1"]["suggestedValue"], 60)
        # 正则路径的写入现在会留审计记录，便于追溯来源
        runs = [
            row["agentRunId"]
            for row in self.repository.list_extraction_submissions(city_id="changsha")
        ]
        self.assertIn("regex-fallback", runs)

    def test_crawl_all_covers_active_sources_and_skips_paused(self):
        """一键全部抓取：覆盖启用来源、跳过停用来源、单条失败不中断整批。"""
        self._make_source(f"{self.base}/policy", name="甲")
        self._make_source(f"{self.base}/policy", name="乙")
        self._make_source(f"{self.base}/policy", name="丙", status="paused")
        self._make_source(f"{self.base}/missing", name="丁")

        response = self.client.post("/api/policies/cities/changsha/crawl-all")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["succeeded"], 2)
        self.assertEqual(body["failed"], 1)
        self.assertEqual(body["skipped"], 1)
        by_name = {item["name"]: item for item in body["results"]}
        self.assertEqual(by_name["甲"]["status"], "success")
        self.assertEqual(by_name["丙"]["status"], "skipped")
        self.assertEqual(by_name["丁"]["status"], "failed")

    def test_source_freshness_flags_stale_annual_document(self):
        """年度文档长期无内容变更 → 判「疑似过期」；非年度来源只判「长期未变」。"""
        from app.api import routes as routes_module

        annual = self._make_source(f"{self.base}/policy", name="长沙市2025年统计公报")
        plain = self._make_source(f"{self.base}/policy", name="长沙医保局")
        self.client.post(f"/api/policies/sources/{annual['id']}/crawl")
        self.client.post(f"/api/policies/sources/{plain['id']}/crawl")

        original = routes_module.SOURCE_STALE_DAYS
        routes_module.SOURCE_STALE_DAYS = 0
        try:
            body = self.client.get("/api/policies/cities/changsha/source-freshness").json()
        finally:
            routes_module.SOURCE_STALE_DAYS = original

        self.assertEqual(body["counts"]["total"], 2)
        self.assertEqual(body["counts"]["stale"], 1)
        by_name = {item["name"]: item for item in body["sources"]}
        self.assertTrue(by_name["长沙市2025年统计公报"]["looksAnnual"])
        self.assertEqual(by_name["长沙市2025年统计公报"]["level"], "stale")
        self.assertIn("新年度版本", by_name["长沙市2025年统计公报"]["reason"])
        # 名称里没有年份的来源只算「长期未变」，避免误报
        self.assertFalse(by_name["长沙医保局"]["looksAnnual"])
        self.assertEqual(by_name["长沙医保局"]["level"], "aging")

    def test_bulk_sources_verifies_and_disables_unreachable(self):
        """批量预置来源：可达的留用并落档；不可达的自动停用（本仓库没有删除来源的接口）。"""
        response = self.client.post(
            "/api/policies/cities/changsha/sources/bulk",
            json={
                "sources": [
                    {"name": "可用来源", "url": f"{self.base}/policy"},
                    {"name": "不可达", "url": f"{self.base}/missing"},
                    {"name": "非法协议", "url": "ftp://example.test/x"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["verified"], 1)
        self.assertEqual(body["unreachable"], 1)
        self.assertEqual(body["rejected"], 1)

        by_name = {item["name"]: item for item in body["results"]}
        self.assertEqual(by_name["可用来源"]["status"], "verified")
        self.assertEqual(by_name["可用来源"]["httpStatus"], 200)
        self.assertTrue(by_name["可用来源"]["title"])

        sources = {source["name"]: source for source in self.repository.list_data_sources()}
        # 不可达的被停用，而不是留成会反复失败的活跃来源
        self.assertEqual(sources["不可达"]["status"], "paused")
        self.assertIn("不可达", sources["不可达"]["note"])
        # 非法协议根本不建来源
        self.assertNotIn("非法协议", sources)
        # 成功的会留下抓取记录（原文已落档）
        self.assertEqual(len(self.repository.list_crawl_artifacts(source_id=by_name["可用来源"]["sourceId"])), 1)

    def test_bulk_sources_reports_duplicates_without_recreating(self):
        self._make_source(f"{self.base}/policy")

        response = self.client.post(
            "/api/policies/cities/changsha/sources/bulk",
            json={"sources": [{"name": "重复", "url": f"{self.base}/policy"}]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["duplicate"], 1)
        self.assertEqual(body["verified"], 0)
        # 没有多建出来
        self.assertEqual(len(self.repository.list_data_sources()), 1)

    def test_source_config_fields_round_trip(self):
        source = self._make_source(
            f"{self.base}/policy",
            timeoutSeconds=30,
            maxBytes=1024 * 1024,
            note="长沙医保局政策栏目",
        )

        listed = self.client.get("/api/policies/sources").json()[0]
        self.assertEqual(listed["timeoutSeconds"], 30)
        self.assertEqual(listed["maxBytes"], 1024 * 1024)
        self.assertEqual(listed["note"], "长沙医保局政策栏目")

        updated = self.client.put(
            f"/api/policies/sources/{source['id']}",
            json={"timeoutSeconds": 45, "note": "更新备注"},
        ).json()
        self.assertEqual(updated["timeoutSeconds"], 45)
        self.assertEqual(updated["note"], "更新备注")

    def test_artifact_listing_and_detail(self):
        source = self._make_source(f"{self.base}/policy")
        artifact = self.client.post(f"/api/policies/sources/{source['id']}/crawl").json()

        listed = self.client.get(f"/api/policies/sources/{source['id']}/artifacts").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["artifactId"], artifact["artifactId"])

        detail = self.client.get(f"/api/policies/artifacts/{artifact['artifactId']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["artifactId"], artifact["artifactId"])

        content = self.client.get(f"/api/policies/artifacts/{artifact['artifactId']}/content")
        self.assertEqual(content.status_code, 200)
        self.assertIn("单小时服务单价", content.text)
        self.assertEqual(content.headers["content-type"].split(";")[0], "text/html")


if __name__ == "__main__":
    unittest.main()
