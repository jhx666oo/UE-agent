from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.repository import JsonProjectRepository
from app.sqlite_repository import (
    SqliteProjectRepository,
    default_database_path,
    initialize_database,
)


def _seed_project(repository: JsonProjectRepository | SqliteProjectRepository, name: str = "长沙 U1 试算") -> dict:
    return repository.create_project(
        {
            "name": name,
            "cityId": "changsha",
            "city": "长沙",
            "district": "岳麓区",
            "baseMonth": "2026-09",
            "stationMode": "自营",
        }
    )


class SqliteRepositoryPersistenceTests(unittest.TestCase):
    def test_project_and_scenario_survive_close_and_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ue-agent.sqlite3"
            initialize_database(path)
            repository = SqliteProjectRepository(path)
            project = _seed_project(repository)
            scenario = repository.create_scenario(
                project["id"], {"name": "基准", "inputs": {"A1": 0, "C11": None}}
            )
            repository.update_scenario(
                project["id"], scenario["id"], {"inputs": {"A1": 0, "C11": None, "P1": 50}}
            )

            reopened = SqliteProjectRepository(path)
            loaded = reopened.get_project(project["id"])

            self.assertEqual(loaded["city"], "长沙")
            self.assertEqual(loaded["district"], "岳麓区")
            self.assertEqual(loaded["stationMode"], "自营")
            self.assertEqual(loaded["scenarios"][0]["id"], scenario["id"])
            self.assertEqual(loaded["scenarios"][0]["inputs"]["A1"], 0)
            self.assertIsNone(loaded["scenarios"][0]["inputs"]["C11"])
            self.assertEqual(loaded["scenarios"][0]["inputs"]["P1"], 50)

    def test_zero_and_null_stay_distinct_from_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = initialize_database(Path(directory) / "ue-agent.sqlite3")
            repository = SqliteProjectRepository(path)
            project = _seed_project(repository)
            scenario = repository.create_scenario(
                project["id"], {"name": "基准", "inputs": {"A1": 0, "C11": None}}
            )

            inputs = SqliteProjectRepository(path).get_scenario(project["id"], scenario["id"])[
                "inputs"
            ]

            self.assertEqual(inputs["A1"], 0)
            self.assertIsNone(inputs["C11"])
            self.assertNotIn("B1", inputs)

    def test_initialize_database_is_idempotent_and_keeps_existing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ue-agent.sqlite3"
            initialize_database(path)
            repository = SqliteProjectRepository(path)
            project = _seed_project(repository, "首次初始化")

            second = initialize_database(path)
            third = initialize_database(path)

            self.assertEqual(second, path)
            self.assertEqual(third, path)
            self.assertEqual(SqliteProjectRepository(path).get_project(project["id"])["name"], "首次初始化")
            self.assertEqual(len(SqliteProjectRepository(path).list_projects()), 1)

    def test_schema_contains_required_tables_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = initialize_database(Path(directory) / "ue-agent.sqlite3")
            with sqlite3.connect(path) as connection:
                names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table','index')"
                    )
                }

        for table in (
            "projects",
            "scenarios",
            "calculation_snapshots",
            "data_sources",
            "policy_documents",
            "policy_facts",
            "crawl_artifacts",
            "schema_migrations",
        ):
            self.assertIn(table, names)
        self.assertIn("idx_scenarios_project_id", names)
        self.assertIn("idx_calculation_snapshots_scenario_id", names)
        self.assertIn("idx_policy_facts_field_id", names)


class SqliteRepositoryBehaviourTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = initialize_database(Path(self.temp_dir.name) / "ue-agent.sqlite3")
        self.repository = SqliteProjectRepository(self.path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_missing_records_raise_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.repository.get_project("missing-project")
        project = _seed_project(self.repository)
        with self.assertRaises(KeyError):
            self.repository.get_scenario(project["id"], "missing-scenario")
        with self.assertRaises(KeyError):
            self.repository.update_data_source("missing-source", {"name": "x"})
        with self.assertRaises(KeyError):
            self.repository.get_policy_document("missing-document")
        with self.assertRaises(KeyError):
            self.repository.get_policy_fact("missing-fact")
        with self.assertRaises(KeyError):
            self.repository.get_snapshot("missing-snapshot")

    def test_repeated_calculation_creates_immutable_snapshot_history(self) -> None:
        project = _seed_project(self.repository)
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})
        first = self.repository.save_calculation(
            project["id"], scenario["id"], {"modelVersion": "test-v1", "status": "ok", "headlineMetrics": {"x": 1}}
        )
        second = self.repository.save_calculation(
            project["id"], scenario["id"], {"modelVersion": "test-v1", "status": "ok", "headlineMetrics": {"x": 2}}
        )

        self.assertNotEqual(first["resultSnapshotId"], second["resultSnapshotId"])
        self.assertEqual(second["status"], "calculated")
        snapshots = self.repository.list_snapshots(project["id"], scenario["id"])
        self.assertEqual([s["resultSnapshot"]["headlineMetrics"]["x"] for s in snapshots], [1, 2])
        self.assertEqual(snapshots[0]["status"], "calculated")
        self.assertEqual(snapshots[0]["projectId"], project["id"])
        self.assertEqual(snapshots[0]["issues"], [])

        reopened = SqliteProjectRepository(self.path)
        self.assertEqual(
            reopened.get_snapshot(first["resultSnapshotId"])["resultSnapshot"]["headlineMetrics"]["x"], 1
        )

    def test_blocked_calculation_is_recorded_as_blocked_snapshot(self) -> None:
        project = _seed_project(self.repository)
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": None}})
        saved = self.repository.save_calculation(
            project["id"],
            scenario["id"],
            {"modelVersion": "test-v1", "status": "blocked", "issues": [{"code": "MISSING_REQUIRED_INPUT"}]},
        )

        self.assertEqual(saved["status"], "failed")
        snapshot = self.repository.list_snapshots(project["id"], scenario["id"])[0]
        self.assertEqual(snapshot["status"], "blocked")
        self.assertEqual(snapshot["issues"][0]["code"], "MISSING_REQUIRED_INPUT")

    def test_input_update_marks_stale_without_deleting_history(self) -> None:
        project = _seed_project(self.repository)
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})
        calculated = self.repository.save_calculation(
            project["id"], scenario["id"], {"modelVersion": "test-v1", "status": "ok", "headlineMetrics": {"x": 1}}
        )

        updated = self.repository.update_scenario(project["id"], scenario["id"], {"inputs": {"P1": 60}})

        self.assertEqual(updated["status"], "stale")
        self.assertIsNone(updated["resultSnapshotId"])
        self.assertIsNone(updated["result"])
        self.assertIsNone(updated["calculatedAt"])
        self.assertEqual(
            self.repository.get_snapshot(calculated["resultSnapshotId"])["resultSnapshot"]["headlineMetrics"]["x"], 1
        )
        self.assertEqual(len(self.repository.list_snapshots(project["id"], scenario["id"])), 1)

    def test_update_on_draft_scenario_without_previous_result_stays_draft(self) -> None:
        project = _seed_project(self.repository)
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})
        updated = self.repository.update_scenario(project["id"], scenario["id"], {"inputs": {"P1": 60}})

        self.assertEqual(updated["status"], "draft")

    def test_only_calculated_scenario_can_be_confirmed(self) -> None:
        project = _seed_project(self.repository)
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})
        with self.assertRaises(ValueError):
            self.repository.confirm_scenario(project["id"], scenario["id"])

        self.repository.save_calculation(
            project["id"], scenario["id"], {"modelVersion": "test-v1", "status": "ok", "headlineMetrics": {}}
        )
        confirmed = self.repository.confirm_scenario(project["id"], scenario["id"])

        self.assertEqual(confirmed["status"], "confirmed")
        self.assertIsNotNone(confirmed["confirmedAt"])
        self.assertTrue(SqliteProjectRepository(self.path).get_scenario(project["id"], scenario["id"])["confirmedAt"])

    def test_list_projects_sorted_by_updated_at_descending(self) -> None:
        first = _seed_project(self.repository, "先建")
        second = _seed_project(self.repository, "后建")
        self.repository.update_scenario(
            second["id"],
            self.repository.create_scenario(second["id"], {"name": "基准"})["id"],
            {"name": "改名"},
        )

        ordered = [project["id"] for project in self.repository.list_projects()]

        self.assertEqual(ordered, [second["id"], first["id"]])

    def test_data_source_and_policy_records_round_trip(self) -> None:
        source = self.repository.create_data_source(
            {"cityId": "changsha", "name": "长沙医保局", "kind": "web", "url": "https://example.gov.cn"}
        )
        updated_source = self.repository.update_data_source(source["id"], {"status": "disabled", "url": None})
        self.assertEqual(updated_source["status"], "disabled")
        self.assertEqual(updated_source["url"], "https://example.gov.cn")
        self.assertEqual(self.repository.list_data_sources("changsha")[0]["id"], source["id"])
        self.assertEqual(self.repository.list_data_sources("yueyang"), [])

        document = self.repository.create_policy_document(
            {
                "cityId": "changsha",
                "originalName": "政策原文.pdf",
                "mimeType": "application/pdf",
                "size": 7,
                "sha256": "abc",
                "source": "official",
            },
            b"policy!",
            ".pdf",
        )
        self.assertEqual(
            document["storedPath"], f"policy_files/{document['id']}.pdf"
        )
        self.assertTrue((self.path.parent / document["storedPath"]).exists())
        self.assertEqual(self.repository.read_policy_document(document), b"policy!")
        self.assertEqual(
            self.repository.update_policy_document(document["id"], {"status": "approved"})["status"], "approved"
        )

        fact = self.repository.create_policy_fact(
            {
                "documentId": document["id"],
                "cityId": "changsha",
                "fieldId": "P1",
                "value": 50,
                "unit": "元/小时",
                "source": "official",
            }
        )
        self.assertEqual(fact["status"], "candidate")
        self.assertEqual(
            self.repository.update_policy_fact(fact["id"], {"status": "approved", "reviewedAt": None})["status"],
            "approved",
        )
        self.assertIsNone(self.repository.get_policy_fact(fact["id"])["reviewedAt"])
        self.assertEqual(len(self.repository.list_policy_facts(city_id="changsha", document_id=document["id"])), 1)

    def test_policy_document_suffix_and_content_type_are_persisted(self) -> None:
        document = self.repository.create_policy_document(
            {
                "cityId": "yueyang",
                "originalName": "通知.docx",
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "sha256": "def",
                "source": "official",
            },
            b"word",
            ".docx",
        )

        self.assertTrue(document["storedPath"].endswith(".docx"))
        self.assertEqual(
            SqliteProjectRepository(self.path).get_policy_document(document["id"])["mimeType"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def test_concurrent_instances_share_the_same_database_file(self) -> None:
        project = _seed_project(self.repository)
        other = SqliteProjectRepository(self.path)
        other.create_scenario(project["id"], {"name": "对方新建"})

        self.assertEqual([s["name"] for s in self.repository.get_project(project["id"])["scenarios"]], ["对方新建"])

    def test_field_suggestion_lifecycle_persists_and_records_history(self) -> None:
        project = _seed_project(self.repository)
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"C3": 1000}})
        source = {"sourceName": "长沙市统计局", "url": "https://example.gov.cn"}

        row = self.repository.save_field_suggestion(scenario["id"], "C3", 820, source)
        self.assertEqual(row["valueState"], "suggestion_ready")
        self.assertEqual(row["suggestedValue"], 820)

        # 建议值不写当前输入，计算引擎继续使用 currentValue
        inputs = self.repository.get_scenario(project["id"], scenario["id"])["inputs"]
        self.assertEqual(inputs["C3"], 1000)

        accepted = self.repository.accept_field_suggestion(project["id"], scenario["id"], "C3")
        self.assertEqual(accepted["valueState"], "accepted")
        scenario_after = self.repository.get_scenario(project["id"], scenario["id"])
        self.assertEqual(scenario_after["inputs"]["C3"], 820)
        self.assertEqual(scenario_after["status"], "draft")

        self.repository.set_field_value(project["id"], scenario["id"], "C3", 850)
        overridden = {r["fieldId"]: r for r in self.repository.list_field_values(scenario["id"])}["C3"]
        self.assertEqual(overridden["valueState"], "overridden")
        self.assertEqual(overridden["suggestedValue"], 820)

        # 重开数据库后建议值、状态与历史仍然完整
        reopened = SqliteProjectRepository(self.path)
        history = reopened.list_field_value_history(scenario["id"], "C3")
        self.assertEqual(
            [(entry["action"], entry["newValue"]) for entry in history],
            [("suggestion_updated", 820), ("accepted", 820), ("overridden", 850)],
        )
        with self.assertRaises(ValueError):
            reopened.accept_field_suggestion(project["id"], scenario["id"], "C10")

    def test_plain_scenario_input_update_marks_crawler_suggestion_overridden(self) -> None:
        project = _seed_project(self.repository)
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"C3": 1000}})
        self.repository.save_field_suggestion(scenario["id"], "C3", 820, {"sourceName": "统计局"})

        self.repository.update_scenario(project["id"], scenario["id"], {"inputs": {"C3": 900}})
        self.repository.mark_field_overridden(scenario["id"], "C3", 1000, 900)

        row = {r["fieldId"]: r for r in self.repository.list_field_values(scenario["id"])}["C3"]
        self.assertEqual(row["valueState"], "overridden")
        self.assertEqual(row["suggestedValue"], 820)
        self.assertEqual(self.repository.get_scenario(project["id"], scenario["id"])["inputs"]["C3"], 900)


class SqliteRepositoryParityTests(unittest.TestCase):
    """The SQLite repository must behave like the JSON repository it replaces."""

    def _run(self, repository: JsonProjectRepository | SqliteProjectRepository) -> list[object]:
        project = repository.create_project({"name": "对照", "city": "长沙", "cityId": "changsha"})
        scenario = repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50, "A1": 0}})
        repository.save_calculation(
            project["id"], scenario["id"], {"modelVersion": "v", "status": "ok", "headlineMetrics": {"x": 1}}
        )
        updated = repository.update_scenario(project["id"], scenario["id"], {"inputs": {"P1": 60}})
        source = repository.create_data_source({"cityId": "changsha", "name": "来源"})
        document = repository.create_policy_document(
            {"cityId": "changsha", "originalName": "a.txt", "sha256": "s", "source": "official"}, b"x", ".txt"
        )
        fact = repository.create_policy_fact(
            {"documentId": document["id"], "cityId": "changsha", "fieldId": "P1", "value": 55}
        )
        repository.update_policy_fact(fact["id"], {"status": "approved"})
        return [
            sorted(project.keys()),
            sorted(scenario.keys()),
            updated["status"],
            source["kind"],
            document["status"],
            repository.get_policy_fact(fact["id"])["status"],
        ]

    def test_key_shapes_and_status_match_json_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            json_result = self._run(JsonProjectRepository(Path(directory) / "projects.json"))
            sqlite_result = self._run(SqliteProjectRepository(initialize_database(Path(directory) / "db.sqlite3")))

        self.assertEqual(json_result[2:], sqlite_result[2:])
        self.assertEqual(set(sqlite_result[0]) - set(json_result[0]), set())
        self.assertIn("scenarios", sqlite_result[0])


class DefaultDatabasePathTests(unittest.TestCase):
    def test_default_path_is_under_services_api_data(self) -> None:
        path = default_database_path()

        self.assertEqual(path.name, "ue-agent.sqlite3")
        self.assertEqual(path.parent.name, "data")
        self.assertEqual(path.parent.parent.name, "api")

    def test_default_path_honours_environment_override(self) -> None:
        import os

        original = os.environ.get("UE_AGENT_DB_FILE")
        os.environ["UE_AGENT_DB_FILE"] = "/tmp/ue-agent-custom/ue-agent.sqlite3"
        try:
            self.assertEqual(default_database_path(), Path("/tmp/ue-agent-custom/ue-agent.sqlite3"))
        finally:
            if original is None:
                del os.environ["UE_AGENT_DB_FILE"]
            else:
                os.environ["UE_AGENT_DB_FILE"] = original


if __name__ == "__main__":
    unittest.main()
