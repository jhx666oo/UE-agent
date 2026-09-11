"""AI 回传链路测试（WorkBuddy 驱动架构）。

重点覆盖 7 项回传校验 —— 这是防止 AI 幻觉污染参数的核心防线。
"""

from __future__ import annotations

import http.server
import tempfile
import threading
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

from fastapi.testclient import TestClient

from app.domain.policy.agent_service import AgentSubmissionService
from app.domain.u1.spec import load_parameter_catalog
from app.main import create_app
from app.repository import JsonProjectRepository


class _PolicyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):  # noqa: N802
        body = (
            "<html><head><title>长沙市长期护理保险实施办法</title></head>"
            "<body>调整后单小时服务单价为 66 元，基金支付比例 80%。</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AgentSubmissionUnitTests(unittest.TestCase):
    """直接测领域服务，不经过 HTTP 层。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.service = AgentSubmissionService(self.repository)
        self.catalog = load_parameter_catalog()
        project = self.repository.create_project(
            {"name": "长沙测算", "city": "长沙", "cityId": "changsha"}
        )
        self.project_id = project["id"]
        scenario = self.repository.create_scenario(self.project_id, {"name": "基准"})
        self.scenario_id = scenario["id"]

    def _submit(self, facts, **kwargs):
        payload = {
            "city_id": "changsha",
            "catalog": self.catalog,
            "submissions": [{"sourceId": "src_1", "artifactId": "art_1", "facts": facts}],
        }
        payload.update(kwargs)
        return self.service.submit_extraction(**payload)

    # ---------- 校验 1：字段必须存在且为自动爬虫 ----------

    def test_unknown_field_rejected(self):
        result = self._submit(
            [{"fieldId": "ZZ9", "value": 1, "quote": "原文"}]
        )
        self.assertEqual(result["acceptedCount"], 0)
        self.assertEqual(result["rejectedCount"], 1)
        self.assertIn("不在参数字典", result["rejected"][0]["reason"])

    def test_formula_field_rejected(self):
        """公式自动字段不允许 AI 写入。"""
        formula_field = next(
            fid for fid, entry in self.catalog.items() if entry["sourceType"] == "公式自动"
        )
        result = self._submit([{"fieldId": formula_field, "value": 1, "quote": "原文"}])
        self.assertEqual(result["acceptedCount"], 0)
        self.assertIn("不可写入", result["rejected"][0]["reason"])

    def test_internal_field_rejected(self):
        """内部填写字段不允许 AI 写入。"""
        internal = next(
            fid for fid, entry in self.catalog.items() if entry["sourceType"] == "内部填写"
        )
        result = self._submit([{"fieldId": internal, "value": 1, "quote": "原文"}])
        self.assertEqual(result["acceptedCount"], 0)

    # ---------- 校验 2：valueType 匹配 ----------

    def test_number_field_rejects_text(self):
        result = self._submit([{"fieldId": "P1", "value": "六十六", "quote": "原文"}])
        self.assertEqual(result["acceptedCount"], 0)
        self.assertIn("要求数值", result["rejected"][0]["reason"])

    def test_text_field_rejects_number(self):
        result = self._submit([{"fieldId": "C2", "value": 1, "quote": "原文"}])
        self.assertEqual(result["acceptedCount"], 0)
        self.assertIn("要求文本", result["rejected"][0]["reason"])

    # ---------- 校验 3：枚举值 ----------

    def test_enum_option_enforced(self):
        """C2 只允许 一线/新一线/二线/三线。"""
        result = self._submit([{"fieldId": "C2", "value": "超一线", "quote": "原文"}])
        self.assertEqual(result["acceptedCount"], 0)
        self.assertIn("不在允许选项", result["rejected"][0]["reason"])

    def test_enum_option_accepted(self):
        result = self._submit([{"fieldId": "C2", "value": "新一线", "quote": "长沙为新一线城市"}])
        self.assertEqual(result["acceptedCount"], 1)

    # ---------- 校验 4：confidence 区间 ----------

    def test_confidence_out_of_range_rejected(self):
        result = self._submit(
            [{"fieldId": "P1", "value": 66, "confidence": 1.5, "quote": "原文"}]
        )
        self.assertEqual(result["acceptedCount"], 0)

    # ---------- 校验 5：quote 非空（防幻觉核心闸门） ----------

    def test_missing_quote_rejected(self):
        result = self._submit([{"fieldId": "P1", "value": 66}])
        self.assertEqual(result["acceptedCount"], 0)
        self.assertIn("缺少原文引用", result["rejected"][0]["reason"])

    def test_blank_quote_rejected(self):
        result = self._submit([{"fieldId": "P1", "value": 66, "quote": "   "}])
        self.assertEqual(result["acceptedCount"], 0)

    # ---------- 校验 6：D 档字段禁止估算 ----------

    def test_never_estimate_fields_rejected(self):
        """C6/C7/C8 官方无公开数据，AI 提供值一律拒绝。"""
        for field_id in ("C6", "C7", "C8"):
            with self.subTest(field_id=field_id):
                result = self._submit(
                    [{"fieldId": field_id, "value": 12.5, "quote": "估算"}]
                )
                self.assertEqual(result["acceptedCount"], 0)
                self.assertIn("禁止估算", result["rejected"][0]["reason"])

    def test_never_estimate_allowed_in_not_disclosed(self):
        """声明为「未披露」是正确做法，应被接受并单独记录。"""
        result = self.service.submit_extraction(
            city_id="changsha",
            catalog=self.catalog,
            submissions=[
                {"sourceId": "src_1", "facts": [], "notDisclosed": ["C6", "C7", "C8"]}
            ],
        )
        self.assertEqual(sorted(result["notDisclosed"]), ["C6", "C7", "C8"])
        self.assertEqual(result["rejectedCount"], 0)

    # ---------- 校验 7：数值区间警告 ----------

    def test_out_of_bounds_warns_but_accepts(self):
        result = self._submit(
            [{"fieldId": "P2", "value": 80, "quote": "基金支付比例 80%"}]
        )
        # P2 存储为 0-1，80 明显是没换算，超出区间 → 接收但警告
        self.assertEqual(result["acceptedCount"], 1)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("超出预期区间", result["warnings"][0]["warning"])

    # ---------- 正常写入 ----------

    def test_valid_fact_writes_suggestion(self):
        result = self._submit(
            [
                {
                    "fieldId": "P1",
                    "value": 66,
                    "unit": "元/小时",
                    "confidence": 0.92,
                    "quote": "调整后单小时服务单价为 66 元",
                }
            ]
        )
        self.assertEqual(result["acceptedCount"], 1)
        self.assertEqual(result["resultStatus"], "accepted")
        rows = {
            row["fieldId"]: row
            for row in self.repository.list_field_values(self.scenario_id)
        }
        self.assertIn("P1", rows)
        self.assertEqual(rows["P1"]["valueState"], "suggestion_ready")
        self.assertEqual(rows["P1"]["suggestedValue"], 66)
        # confidence 与 quote 应随建议来源一并保留
        self.assertEqual(rows["P1"]["suggestedSource"]["confidence"], 0.92)
        self.assertIn("66 元", rows["P1"]["suggestedSource"]["quote"])

    def test_partial_rejection_keeps_valid_ones(self):
        """单条被拒不应影响同批其他条目。"""
        result = self._submit(
            [
                {"fieldId": "P1", "value": 66, "quote": "单价 66 元"},
                {"fieldId": "P8", "value": 2, "quote": ""},
                {"fieldId": "P9", "value": 3, "quote": "每月必选 3 项"},
            ]
        )
        self.assertEqual(result["acceptedCount"], 2)
        self.assertEqual(result["rejectedCount"], 1)
        self.assertEqual(result["resultStatus"], "partially_rejected")

    def test_same_batch_duplicate_prefers_in_range_value(self):
        """同批次重复回传同一字段时，落在合理区间的那条应胜出。

        回归：曾因后一条静默覆盖前一条，让未换算的 P2=80 覆盖掉正确的 0.8。
        """
        self._submit(
            [
                {"fieldId": "P2", "value": 0.8, "confidence": 0.93, "quote": "基金支付比例为 80%"},
                {"fieldId": "P2", "value": 80, "confidence": 0.8, "quote": "基金支付比例为 80%（未换算）"},
            ]
        )
        rows = {row["fieldId"]: row for row in self.repository.list_field_values(self.scenario_id)}
        self.assertEqual(rows["P2"]["suggestedValue"], 0.8)

    def test_same_batch_duplicate_prefers_higher_confidence(self):
        """都在区间内时，置信度更高者胜出。"""
        result = self._submit(
            [
                {"fieldId": "P1", "value": 66, "confidence": 0.7, "quote": "单价 66 元"},
                {"fieldId": "P1", "value": 68, "confidence": 0.95, "quote": "单价 68 元"},
            ]
        )
        self.assertEqual(result["acceptedCount"], 1)
        rows = {row["fieldId"]: row for row in self.repository.list_field_values(self.scenario_id)}
        self.assertEqual(rows["P1"]["suggestedValue"], 68)
        self.assertEqual(len(result["conflicts"]), 1)

    def test_same_field_across_submissions_deduped(self):
        """跨 submission 回传同一字段同样去重。"""
        result = self.service.submit_extraction(
            city_id="changsha",
            catalog=self.catalog,
            submissions=[
                {"sourceId": "s1", "facts": [{"fieldId": "P1", "value": 66, "confidence": 0.6, "quote": "甲"}]},
                {"sourceId": "s2", "facts": [{"fieldId": "P1", "value": 70, "confidence": 0.9, "quote": "乙"}]},
            ],
        )
        self.assertEqual(result["acceptedCount"], 1)
        rows = {row["fieldId"]: row for row in self.repository.list_field_values(self.scenario_id)}
        self.assertEqual(rows["P1"]["suggestedValue"], 70)

    def test_submission_audit_recorded(self):
        self._submit(
            [{"fieldId": "P1", "value": 66, "quote": "单价 66 元"}],
            agent_run_id="wb-2026-09-10",
            agent_version="policy-ai-crawler@0.1.0",
        )
        records = self.repository.list_extraction_submissions(city_id="changsha")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["agentRunId"], "wb-2026-09-10")
        self.assertEqual(records[0]["acceptedCount"], 1)

    # ---------- 派活清单 ----------

    def test_crawl_targets_exposes_catalog_and_difficulty(self):
        targets = self.service.crawl_targets(self.catalog)
        catalog_ids = [item["id"] for item in targets["fieldCatalog"]]
        self.assertEqual(len(catalog_ids), 20)
        self.assertNotIn("S1", catalog_ids)
        by_id = {item["id"]: item for item in targets["fieldCatalog"]}
        self.assertEqual(by_id["P1"]["difficulty"], "A")
        self.assertEqual(by_id["C3"]["difficulty"], "C")
        self.assertTrue(by_id["C6"]["neverEstimate"])
        self.assertFalse(by_id["P1"]["neverEstimate"])
        self.assertIn("C6", targets["neverEstimateFields"])

    def test_crawl_targets_lists_configured_sources(self):
        self.repository.create_data_source(
            {"cityId": "changsha", "name": "长沙医保局", "url": "https://example.gov.cn/x"}
        )
        targets = self.service.crawl_targets(self.catalog)
        city = next(item for item in targets["cities"] if item["cityId"] == "changsha")
        self.assertEqual(len(city["sources"]), 1)
        source = city["sources"][0]
        self.assertEqual(source["name"], "长沙医保局")
        # 场景虽被基准输入整表填充，但尚无任何已采用/已覆盖的爬虫值，
        # 因此全部 20 个字段都应列入待填清单。
        self.assertEqual(len(source["fieldsToFill"]), 20)
        self.assertEqual(source["alreadyFilled"], [])

    def test_crawl_targets_marks_filled_fields(self):
        """已采用建议值的字段不应重复要求抽取。

        回归：判据不能用 inputs 是否非空 —— 基准输入会整表填充，
        那样 fieldsToFill 永远为空，增量感知形同虚设。
        """
        self.repository.create_data_source(
            {"cityId": "changsha", "name": "长沙医保局", "url": "https://example.gov.cn/x"}
        )
        # 基准输入本身已给 P1 赋值，但未采用爬虫建议 → 仍应列入待填。
        before = self.service.crawl_targets(self.catalog)
        city = next(item for item in before["cities"] if item["cityId"] == "changsha")
        self.assertIn("P1", city["sources"][0]["fieldsToFill"])

        # 采用一条爬虫建议值后，该字段才有可信来源，应从待填清单移除。
        self.repository.save_field_suggestion(
            self.scenario_id, "P1", 66, {"sourceName": "长沙医保局"}
        )
        self.repository.accept_field_suggestion(self.project_id, self.scenario_id, "P1")

        after = self.service.crawl_targets(self.catalog)
        city = next(item for item in after["cities"] if item["cityId"] == "changsha")
        source = city["sources"][0]
        self.assertNotIn("P1", source["fieldsToFill"])
        self.assertIn("P1", source["alreadyFilled"])
        self.assertEqual(len(source["fieldsToFill"]), 19)

    def test_crawl_targets_skips_overridden_fields(self):
        """人工覆盖过的字段不应被爬虫反复打扰。"""
        self.repository.create_data_source(
            {"cityId": "changsha", "name": "长沙医保局", "url": "https://example.gov.cn/x"}
        )
        self.repository.save_field_suggestion(
            self.scenario_id, "C3", 820, {"sourceName": "统计局"}
        )
        self.repository.mark_field_overridden(self.scenario_id, "C3", 820, 900)
        targets = self.service.crawl_targets(self.catalog)
        city = next(item for item in targets["cities"] if item["cityId"] == "changsha")
        source = city["sources"][0]
        self.assertNotIn("C3", source["fieldsToFill"])
        self.assertIn("C3", source["alreadyFilled"])

    # ---------- 候选来源 ----------

    def test_candidate_source_dedup_by_url(self):
        first = self.service.submit_candidate_sources(
            city_id="changsha",
            candidates=[{"url": "https://ylbzj.changsha.gov.cn/a", "name": "长沙医保局"}],
        )
        second = self.service.submit_candidate_sources(
            city_id="changsha",
            candidates=[{"url": "https://ylbzj.changsha.gov.cn/a", "name": "长沙医保局（改名）"}],
        )
        self.assertEqual(first["created"][0]["id"], second["created"][0]["id"])
        self.assertEqual(len(self.repository.list_candidate_sources(city_id="changsha")), 1)

    def test_candidate_source_rejects_bad_url(self):
        result = self.service.submit_candidate_sources(
            city_id="changsha", candidates=[{"url": "javascript:alert(1)"}]
        )
        self.assertEqual(result["createdCount"], 0)
        self.assertEqual(result["skippedCount"], 1)

    def test_promote_candidate_creates_data_source(self):
        created = self.service.submit_candidate_sources(
            city_id="changsha",
            candidates=[{"url": "https://ylbzj.changsha.gov.cn/b", "name": "长沙医保局"}],
        )
        candidate_id = created["created"][0]["id"]
        promoted = self.service.promote_candidate_source(candidate_id)
        self.assertEqual(promoted["status"], "promoted")
        self.assertIsNotNone(promoted["promotedSourceId"])
        sources = self.repository.list_data_sources(city_id="changsha")
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["url"], "https://ylbzj.changsha.gov.cn/b")

    def test_reject_candidate_does_not_create_source(self):
        created = self.service.submit_candidate_sources(
            city_id="changsha", candidates=[{"url": "https://spam.example.com/x"}]
        )
        self.service.reject_candidate_source(created["created"][0]["id"], "非权威站点")
        self.assertEqual(self.repository.list_data_sources(city_id="changsha"), [])


class AgentApiTests(unittest.TestCase):
    """HTTP 层：抓取接口与 token 鉴权。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PolicyHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        app = create_app(repository=self.repository)
        app.state.crawl_allow_private = True
        self.client = TestClient(app)
        project = self.repository.create_project(
            {"name": "长沙测算", "city": "长沙", "cityId": "changsha"}
        )
        self.project_id = project["id"]
        self.scenario_id = self.repository.create_scenario(self.project_id, {"name": "基准"})["id"]

    def test_fetch_requests_returns_text_and_artifact(self):
        source = self.repository.create_data_source(
            {"cityId": "changsha", "name": "长沙医保局", "url": f"http://127.0.0.1:{self.port}/policy"}
        )
        response = self.client.post(
            "/api/policies/fetch-requests",
            json={
                "requests": [
                    {
                        "url": f"http://127.0.0.1:{self.port}/policy",
                        "cityId": "changsha",
                        "sourceId": source["id"],
                        "name": "长沙医保局",
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["succeeded"], 1)
        item = body["results"][0]
        self.assertEqual(item["changeStatus"], "first_fetch")
        self.assertIsNotNone(item["artifactId"])
        self.assertIn("单小时服务单价", item["text"])
        # 原文应落档，供人工回溯
        self.assertTrue(len(self.repository.list_crawl_artifacts(source_id=source["id"])) == 1)

    def test_fetch_requests_second_call_marks_unchanged(self):
        source = self.repository.create_data_source(
            {"cityId": "changsha", "name": "长沙医保局", "url": f"http://127.0.0.1:{self.port}/policy"}
        )
        payload = {
            "requests": [
                {"url": f"http://127.0.0.1:{self.port}/policy", "cityId": "changsha", "sourceId": source["id"]}
            ]
        }
        self.client.post("/api/policies/fetch-requests", json=payload)
        second = self.client.post("/api/policies/fetch-requests", json=payload).json()
        self.assertEqual(second["results"][0]["changeStatus"], "unchanged")
        self.assertEqual(second["unchanged"], 1)

    def test_fetch_requests_without_source_id_skips_archiving(self):
        response = self.client.post(
            "/api/policies/fetch-requests",
            json={"requests": [{"url": f"http://127.0.0.1:{self.port}/policy"}]},
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertEqual(item["status"], "success")
        self.assertIsNone(item["sourceId"])

    def test_fetch_requests_reports_failure(self):
        response = self.client.post(
            "/api/policies/fetch-requests",
            json={"requests": [{"url": "http://127.0.0.1:1/nope", "cityId": "changsha"}]},
        )
        body = response.json()
        self.assertEqual(body["failed"], 1)
        self.assertEqual(body["results"][0]["status"], "failed")

    def test_submission_endpoint_writes_suggestion(self):
        response = self.client.post(
            "/api/policies/extraction-submissions",
            json={
                "cityId": "changsha",
                "agentRunId": "wb-test",
                "submissions": [
                    {
                        "sourceId": "src_1",
                        "facts": [
                            {
                                "fieldId": "P1",
                                "value": 66,
                                "confidence": 0.9,
                                "quote": "单小时服务单价为 66 元",
                            }
                        ],
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["acceptedCount"], 1)
        city_values = self.client.get("/api/cities/changsha/values").json()
        p1 = next(f for f in city_values["fields"] if f["fieldId"] == "P1")
        self.assertEqual(p1["suggestedValue"], 66)
        self.assertEqual(p1["valueState"], "suggestion_ready")

    def test_token_enforced_when_configured(self):
        import os

        os.environ["UE_AGENT_AGENT_TOKEN"] = "secret-token"
        self.addCleanup(os.environ.pop, "UE_AGENT_AGENT_TOKEN", None)
        denied = self.client.post(
            "/api/policies/extraction-submissions",
            json={
                "cityId": "changsha",
                "submissions": [{"facts": [{"fieldId": "P1", "value": 1, "quote": "x"}]}],
            },
        )
        self.assertEqual(denied.status_code, 401)
        allowed = self.client.post(
            "/api/policies/extraction-submissions",
            headers={"X-UE-Agent-Token": "secret-token"},
            json={
                "cityId": "changsha",
                "submissions": [{"facts": [{"fieldId": "P1", "value": 66, "quote": "单价 66"}]}],
            },
        )
        self.assertEqual(allowed.status_code, 200)

    def test_crawl_targets_endpoint(self):
        self.repository.create_data_source(
            {"cityId": "changsha", "name": "长沙医保局", "url": "https://example.gov.cn/x"}
        )
        response = self.client.get("/api/policies/crawl-targets")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["fieldCatalog"]), 20)
        self.assertIn("C6", body["neverEstimateFields"])

    def test_source_candidate_lifecycle_via_api(self):
        created = self.client.post(
            "/api/policies/source-candidates",
            json={
                "cityId": "changsha",
                "candidates": [
                    {
                        "url": "https://ylbzj.changsha.gov.cn/zc",
                        "name": "长沙医保局政策页",
                        "targetFields": ["P1", "P2"],
                        "relevance": 0.88,
                    }
                ],
            },
        )
        self.assertEqual(created.status_code, 201)
        candidate_id = created.json()["created"][0]["id"]
        listed = self.client.get("/api/policies/source-candidates?cityId=changsha").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["targetFields"], ["P1", "P2"])
        promoted = self.client.post(f"/api/policies/source-candidates/{candidate_id}/promote")
        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(promoted.json()["status"], "promoted")


if __name__ == "__main__":
    unittest.main()
