from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.domain.policy.research_service import PolicyResearchService
from app.main import create_app
from app.repository import JsonProjectRepository
from app.sqlite_repository import SqliteProjectRepository


class JsonResearchRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_active_research_run_is_unique_and_round_trips_payload(self):
        first = self.repository.create_research_run(
            {"cityId": "长沙", "trigger": "ui", "scope": "all", "fields": ["P1"]}
        )
        second = self.repository.create_research_run(
            {"cityId": "长沙", "trigger": "workbuddy", "scope": "policy", "fields": ["P2"]}
        )

        self.assertEqual(second["id"], first["id"])
        self.assertEqual(self.repository.get_active_research_run("长沙")["scope"], "all")
        self.assertEqual(self.repository.get_research_run(first["id"])["fields"], ["P1"])

    def test_finished_run_allows_a_new_active_run(self):
        first = self.repository.create_research_run(
            {"cityId": "长沙", "trigger": "ui", "scope": "all"}
        )
        self.repository.update_research_run(
            first["id"], {"status": "completed", "finishedAt": "2026-09-15T00:00:00Z"}
        )

        second = self.repository.create_research_run(
            {"cityId": "长沙", "trigger": "workbuddy", "scope": "policy"}
        )

        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(len(self.repository.list_research_runs("长沙")), 2)

    def test_research_queries_are_listed_in_creation_order(self):
        run = self.repository.create_research_run({"cityId": "长沙", "trigger": "ui", "scope": "all"})
        first = self.repository.create_research_query(
            {"runId": run["id"], "family": "政策准入", "query": "长沙 长护险", "status": "queued"}
        )
        self.repository.create_research_query(
            {"runId": run["id"], "family": "城市人口", "query": "长沙 统计公报", "status": "queued"}
        )
        self.assertEqual(self.repository.list_research_queries(run["id"])[0]["id"], first["id"])


class SqliteResearchRepositoryTests(unittest.TestCase):
    def test_research_run_survives_repository_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ue-agent.sqlite3"
            repository = SqliteProjectRepository(path)
            created = repository.create_research_run(
                {
                    "cityId": "长沙",
                    "projectId": "project-1",
                    "trigger": "ui",
                    "scope": "all",
                    "fields": ["P1", "P2"],
                    "taskPrompt": "更新长沙政策",
                }
            )
            repository.update_research_run(
                created["id"], {"status": "completed", "suggestionCount": 3}
            )

            reloaded = SqliteProjectRepository(path)
            result = reloaded.get_research_run(created["id"])
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["suggestionCount"], 3)
            self.assertEqual(result["fields"], ["P1", "P2"])

    def test_research_run_correlation_is_preserved_on_crawl_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SqliteProjectRepository(Path(directory) / "ue-agent.sqlite3")
            run = repository.create_research_run(
                {"cityId": "长沙", "trigger": "workbuddy", "scope": "all"}
            )
            repository.create_crawl_artifact(
                {
                    "sourceId": "source-1",
                    "cityId": "长沙",
                    "requestedUrl": "https://example.test/policy",
                    "status": "success",
                    "researchRunId": run["id"],
                }
            )

            artifact = repository.list_crawl_artifacts(city_id="长沙")[0]

            self.assertEqual(artifact["researchRunId"], run["id"])


class PolicyResearchServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.catalog = {
            "P1": {"id": "P1", "name": "单小时服务单价", "sourceType": "自动爬虫", "unit": "元/小时"},
            "P2": {"id": "P2", "name": "基金支付比例", "sourceType": "自动爬虫", "unit": "比例"},
            "C3": {"id": "C3", "name": "常住总人口", "sourceType": "自动爬虫", "unit": "万人"},
            "C6": {"id": "C6", "name": "失能率", "sourceType": "自动爬虫", "unit": "%"},
            "S1": {"id": "S1", "name": "护理员月薪", "sourceType": "内部填写", "unit": "元"},
            "B12": {"id": "B12", "name": "公关费用", "sourceType": "公式自动", "unit": "元"},
        }
        self.service = PolicyResearchService(self.repository, self.catalog)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_brief_uses_current_year_and_excludes_manual_and_formula_fields(self):
        run = self.service.create_run(
            city_id="长沙", project_id=None, trigger="workbuddy", scope="all", fields=[]
        )
        brief = self.service.build_brief(run["id"])

        queries = " ".join(item["query"] for item in brief["queries"])
        catalog_ids = {item["id"] for item in brief["fieldCatalog"]}
        self.assertIn(str(datetime.now(timezone.utc).year), queries)
        self.assertTrue(catalog_ids.isdisjoint({"S1", "B12"}))
        self.assertEqual(brief["neverEstimateFields"], ["C6", "C7", "C8"])
        self.assertEqual(len(self.repository.list_research_queries(run["id"])), 3)

    def test_retry_only_requeues_failed_or_partial_run(self):
        run = self.service.create_run(
            city_id="长沙", project_id=None, trigger="ui", scope="all", fields=[]
        )
        self.repository.update_research_run(run["id"], {"status": "completed"})

        with self.assertRaisesRegex(ValueError, "RESEARCH_RUN_NOT_RETRYABLE"):
            self.service.retry(run["id"])


class PolicyResearchApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.repository = repository
        project = repository.create_project({"name": "长沙测算", "city": "长沙", "cityId": "长沙"})
        repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})
        self.client = TestClient(create_app(repository))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_research_run_returns_prompt_and_reuses_active_run(self):
        first = self.client.post(
            "/api/policies/research-runs",
            json={"cityId": "长沙", "trigger": "ui", "scope": "all"},
        )
        second = self.client.post(
            "/api/policies/research-runs",
            json={"cityId": "长沙", "trigger": "workbuddy", "scope": "all"},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertIn("更新长沙", first.json()["taskPrompt"])
        self.assertEqual(first.json()["queryCount"], 3)

    def test_brief_has_dynamic_queries_and_completion_is_idempotent(self):
        created = self.client.post(
            "/api/policies/research-runs",
            json={"cityId": "长沙", "trigger": "workbuddy", "scope": "all"},
        ).json()
        brief = self.client.get(f"/api/policies/research-runs/{created['id']}/brief")
        self.assertEqual(brief.status_code, 200)
        self.assertTrue(any("site:gov.cn" in item["query"] for item in brief.json()["queries"]))

        rejected = self.client.post(
            f"/api/policies/research-runs/{created['id']}/complete",
            json={"status": "completed", "agentRunId": "agent-1"},
        )
        self.assertEqual(rejected.status_code, 409)

        self.repository.update_research_run(
            created["id"], {"status": "researching", "phase": "researching"}
        )

        body = {
            "status": "completed",
            "agentRunId": "agent-1",
            "agentVersion": "policy-ai-crawler@2",
            "errors": [],
        }
        completed = self.client.post(
            f"/api/policies/research-runs/{created['id']}/complete", json=body
        )
        repeated = self.client.post(
            f"/api/policies/research-runs/{created['id']}/complete", json=body
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["status"], "completed")

    def test_city_run_list_returns_latest_run_first(self):
        first = self.client.post(
            "/api/policies/research-runs",
            json={"cityId": "长沙", "trigger": "workbuddy", "scope": "all"},
        ).json()
        self.repository.update_research_run(
            first["id"], {"status": "researching", "phase": "researching"}
        )
        self.client.post(
            f"/api/policies/research-runs/{first['id']}/complete",
            json={"status": "completed", "agentRunId": "agent-old"},
        )
        second = self.client.post(
            "/api/policies/research-runs",
            json={"cityId": "长沙", "trigger": "ui", "scope": "all"},
        ).json()

        response = self.client.get("/api/policies/research-runs?cityId=%E9%95%BF%E6%B2%99&limit=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [second["id"], first["id"]])

    def test_results_delegate_validation_and_mark_run_awaiting_review(self):
        created = self.client.post(
            "/api/policies/research-runs",
            json={"cityId": "长沙", "trigger": "workbuddy", "scope": "all"},
        ).json()
        result = self.client.post(
            f"/api/policies/research-runs/{created['id']}/results",
            json={
                "agentRunId": "agent-2",
                "agentVersion": "policy-ai-crawler@2",
                "candidates": [
                    {
                        "url": "https://ybj.changsha.gov.cn/policy-2026",
                        "title": "长沙市长期护理保险实施办法",
                        "targetFields": ["P1", "P2"],
                        "relevance": 0.95,
                    }
                ],
                "submissions": [
                    {
                        "sourceId": "source-1",
                        "artifactId": "artifact-1",
                        "facts": [
                            {
                                "fieldId": "P1",
                                "value": 66,
                                "unit": "元/小时",
                                "confidence": 0.92,
                                "quote": "单小时服务单价调整为66元",
                            }
                        ],
                        "notDisclosed": ["C6", "C7", "C8"],
                    }
                ],
            },
        )

        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertEqual(body["candidateResult"]["createdCount"], 1)
        self.assertEqual(body["extractionResult"]["acceptedCount"], 1)
        self.assertEqual(body["run"]["status"], "awaiting_review")
        self.assertEqual(body["run"]["suggestionCount"], 1)


if __name__ == "__main__":
    unittest.main()
