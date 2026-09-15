import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.domain.policy.discovery import classify_source
from app.domain.policy.onboarding_service import CityOnboardingService
from app.domain.policy.service import CrawlServiceError, parse_suggestions
from app.main import create_app
from app.repository import JsonProjectRepository
from app.sqlite_repository import SqliteProjectRepository


POLICY_TEXT = (
    "成都为新一线城市；常住人口 2140 万人；60岁以上人口占比 20.58%；"
    "80岁以上人口占比 3.2%；职工医保参保人数 210 万人；医保基金净结余 12.6 亿元；"
    "区域总面积 14335 平方公里；单小时服务单价 66 元；基金支付比例 80%；"
    "最低护理员纳保数 20 人；最低护士配置数 2 人；失能状态持续时长要求 6 个月；"
    "评估通过率门槛 70%；单次服务时长 2 小时；每月必选服务项数 3 项；"
    "辅具政策纳入试点，支持亲情照护模式。"
)


class StaticDiscoveryProvider:
    def __init__(self, results):
        self.results = results

    def discover(self, city_name, field_families):
        return self.results


class FakePolicyService:
    def __init__(self, repository):
        self.repository = repository

    def crawl_source_now(self, source_id, *, raw_dir):
        source = self.repository.update_data_source(source_id, {})
        if "bad" in str(source.get("url")):
            raise CrawlServiceError("FETCH_FAILED", "来源暂时不可达", 502)
        return {
            "artifactId": f"artifact-{source_id}",
            "sourceId": source_id,
            "cityId": source["cityId"],
            "status": "success",
            "finalUrl": source["url"],
            "suggestions": parse_suggestions(POLICY_TEXT),
        }


def make_json_fixture():
    temp_dir = tempfile.TemporaryDirectory()
    repository = JsonProjectRepository(Path(temp_dir.name) / "projects.json")
    project = repository.create_project({"name": "成都测算", "city": "成都", "cityId": "chengdu"})
    scenario = repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})
    return temp_dir, repository, project, scenario


class DiscoveryRuleTests(unittest.TestCase):
    def test_classify_source_prefers_government_and_bureau_domains(self):
        self.assertEqual(classify_source("https://ybj.chengdu.gov.cn/a", "医保局政策"), "official")
        self.assertEqual(classify_source("https://www.chengdu.gov.cn/a", "政府公开信息"), "official")
        self.assertEqual(classify_source("https://example.com/a", "政策整理"), "candidate")
        self.assertEqual(classify_source("javascript:alert(1)", "bad"), "rejected")


class CityOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir, self.repository, self.project, self.scenario = make_json_fixture()

    def tearDown(self):
        self.temp_dir.cleanup()

    def service(self, results):
        return CityOnboardingService(
            self.repository,
            discovery_provider=StaticDiscoveryProvider(results),
            policy_service=FakePolicyService(self.repository),
        )

    def test_discovery_classifies_official_sources_and_keeps_other_sources_as_candidates(self):
        result = self.service([
            {"url": "https://ybj.chengdu.gov.cn/policy", "title": "成都医保局长护险办法"},
            {"url": "https://example.com/chengdu-care", "title": "成都养老政策整理"},
        ]).run_for_project(self.project["id"])
        self.assertEqual(result["officialSourceCount"], 1)
        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(len(self.repository.list_data_sources(city_id="chengdu")), 1)
        self.assertEqual(len(self.repository.list_candidate_sources(city_id="chengdu")), 1)
        self.assertEqual(result["suggestionCount"], 17)

    def test_running_city_onboarding_is_reused_instead_of_started_twice(self):
        service = self.service([])
        first = service.start(self.project["id"])
        second = service.start(self.project["id"])
        self.assertEqual(first["id"], second["id"])

    def test_failed_source_does_not_stop_other_sources(self):
        result = self.service([
            {"url": "https://ybj.chengdu.gov.cn/good", "title": "可抓取政策"},
            {"url": "https://ybj.chengdu.gov.cn/bad", "title": "不可抓取政策"},
        ]).run_for_project(self.project["id"])
        self.assertEqual(result["status"], "partial_failed")
        self.assertEqual(result["errorCount"], 1)
        self.assertEqual(result["crawledCount"], 1)
        self.assertEqual(result["suggestionCount"], 17)

    def test_onboarding_writes_suggestions_without_overwriting_current_inputs(self):
        result = self.service([
            {"url": "https://ybj.chengdu.gov.cn/policy", "title": "长护险政策"},
        ]).run_for_project(self.project["id"])
        values = self.repository.list_field_values(self.scenario["id"])
        p1 = next(row for row in values if row["fieldId"] == "P1")
        self.assertEqual(result["suggestionCount"], 17)
        self.assertEqual(p1["valueState"], "suggestion_ready")
        self.assertEqual(self.repository.get_scenario(self.project["id"], self.scenario["id"])["inputs"]["P1"], 50)


class SqliteOnboardingRepositoryTests(unittest.TestCase):
    def test_onboarding_job_survives_repository_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ue-agent.sqlite3"
            repository = SqliteProjectRepository(path)
            project = repository.create_project({"name": "成都测算", "city": "成都", "cityId": "chengdu"})
            job = repository.create_onboarding_job({
                "projectId": project["id"], "cityId": "chengdu", "cityName": "成都",
                "status": "queued", "phase": "queued",
            })
            updated = repository.update_onboarding_job(job["id"], {
                "status": "completed", "phase": "completed", "suggestionCount": 4,
            })
            self.assertEqual(updated["suggestionCount"], 4)
            reloaded = SqliteProjectRepository(path)
            self.assertEqual(reloaded.get_onboarding_job(job["id"])["status"], "completed")


class CityOnboardingApiTests(unittest.TestCase):
    def test_create_project_triggers_onboarding_and_status_can_be_read(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonProjectRepository(Path(directory) / "projects.json")
            app = create_app(
                repository,
                discovery_provider=StaticDiscoveryProvider([
                    {"url": "https://example.com/chengdu-policy", "title": "成都养老政策整理"},
                ]),
            )
            client = TestClient(app)
            created = client.post("/api/projects", json={"name": "成都自动入场", "city": "成都"})
            self.assertEqual(created.status_code, 201)
            body = created.json()
            self.assertEqual(body["project"]["scenarios"][0]["name"], "基准")
            status = client.get(f"/api/projects/{body['project']['id']}/onboarding")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "completed")
            self.assertEqual(status.json()["candidateCount"], 1)


if __name__ == "__main__":
    unittest.main()
