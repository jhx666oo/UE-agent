from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.repository import JsonProjectRepository
from app.sqlite_repository import SqliteProjectRepository, connect_database, initialize_database
from scripts.bootstrap import bootstrap_local_data
from scripts.migrate_json_to_sqlite import migrate_json_to_sqlite


def _seed_json_repository(path: Path) -> dict:
    repository = JsonProjectRepository(path)
    project = repository.create_project(
        {
            "name": "长沙 U1 试算",
            "cityId": "changsha",
            "city": "长沙",
            "district": "岳麓区",
            "baseMonth": "2026-09",
            "stationMode": "自营",
        }
    )
    scenario = repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50, "A1": 0}})
    repository.save_calculation(
        project["id"],
        scenario["id"],
        {"modelVersion": "u1-excel-v2.1-parity", "status": "ok", "headlineMetrics": {"x": 1}},
    )
    repository.update_scenario(project["id"], scenario["id"], {"inputs": {"P1": 55, "A1": 0}})
    source = repository.create_data_source({"cityId": "changsha", "name": "长沙医保局", "url": "https://example.gov"})
    document = repository.create_policy_document(
        {"cityId": "changsha", "originalName": "通知.pdf", "mimeType": "application/pdf", "sha256": "abc", "source": "official"},
        b"policy!",
        ".pdf",
    )
    fact = repository.create_policy_fact(
        {"documentId": document["id"], "cityId": "changsha", "fieldId": "P1", "value": 55, "confidence": 0.8}
    )
    repository.update_policy_fact(fact["id"], {"status": "approved"})
    return {"project": project, "scenario": scenario, "source": source, "document": document, "fact": fact}


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


class MigrateJsonToSqliteTests(unittest.TestCase):
    def test_migration_preserves_ids_timestamps_and_nested_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seeded = _seed_json_repository(root / "projects.json")
            database = initialize_database(root / "ue-agent.sqlite3")

            report = migrate_json_to_sqlite(root / "projects.json", database)

            self.assertEqual(report.projects, 1)
            self.assertEqual(report.scenarios, 1)
            self.assertEqual(report.snapshots, 1)
            self.assertEqual(report.data_sources, 1)
            self.assertEqual(report.policy_documents, 1)
            self.assertEqual(report.policy_facts, 1)

            repository = SqliteProjectRepository(database)
            project = repository.get_project(seeded["project"]["id"])
            self.assertEqual(project["name"], "长沙 U1 试算")
            self.assertEqual(project["createdAt"], seeded["project"]["createdAt"])
            scenario = project["scenarios"][0]
            self.assertEqual(scenario["id"], seeded["scenario"]["id"])
            self.assertEqual(scenario["status"], "stale")
            self.assertEqual(scenario["inputs"], {"P1": 55, "A1": 0})
            self.assertIsNone(scenario["result"])
            snapshots = repository.list_snapshots(project["id"], scenario["id"])
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0]["resultSnapshot"]["headlineMetrics"]["x"], 1)
            self.assertEqual(snapshots[0]["modelVersion"], "u1-excel-v2.1-parity")
            self.assertTrue(snapshots[0]["calculatedAt"])
            self.assertIsNone(scenario["calculatedAt"])
            self.assertEqual(repository.list_data_sources("changsha")[0]["id"], seeded["source"]["id"])
            document = repository.get_policy_document(seeded["document"]["id"])
            self.assertEqual(document["status"], "uploaded")
            self.assertEqual(document["sha256"], "abc")
            fact = repository.get_policy_fact(seeded["fact"]["id"])
            self.assertEqual(fact["status"], "approved")
            self.assertEqual(fact["confidence"], 0.8)
            self.assertEqual(fact["value"], 55)

    def test_re_running_migration_does_not_duplicate_or_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "projects.json"
            _seed_json_repository(json_path)
            database = initialize_database(root / "ue-agent.sqlite3")

            first = migrate_json_to_sqlite(json_path, database)
            # 迁移后业务侧继续修改数据
            repository = SqliteProjectRepository(database)
            project = repository.list_projects()[0]
            repository.update_scenario(project["id"], project["scenarios"][0]["id"], {"name": "已改名"})

            second = migrate_json_to_sqlite(json_path, database)

            self.assertFalse(second.applied)
            self.assertEqual(second.skipped_reason, "target already contains projects")
            with connect_database(database) as connection:
                self.assertEqual(_count(connection, "projects"), 1)
                self.assertEqual(_count(connection, "scenarios"), 1)
                self.assertEqual(_count(connection, "calculation_snapshots"), 1)
            self.assertEqual(first.projects, 1)
            self.assertEqual(
                repository.get_project(project["id"])["scenarios"][0]["name"], "已改名"
            )

    def test_missing_json_file_is_reported_without_touching_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = initialize_database(root / "ue-agent.sqlite3")

            report = migrate_json_to_sqlite(root / "projects.json", database)

            self.assertFalse(report.applied)
            self.assertEqual(report.skipped_reason, "source file not found")
            with connect_database(database) as connection:
                self.assertEqual(_count(connection, "projects"), 0)

    def test_migration_skips_an_empty_store_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "projects.json").write_text(
                json.dumps({"projects": []}, ensure_ascii=False), encoding="utf-8"
            )
            database = initialize_database(root / "ue-agent.sqlite3")

            report = migrate_json_to_sqlite(root / "projects.json", database)

            self.assertFalse(report.applied)
            self.assertEqual(report.skipped_reason, "source contains no projects")


class BootstrapTests(unittest.TestCase):
    def test_bootstrap_creates_dirs_database_and_imports_existing_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            data_dir.mkdir()
            _seed_json_repository(data_dir / "projects.json")

            result = bootstrap_local_data(data_dir)

            self.assertTrue((data_dir / "ue-agent.sqlite3").exists())
            self.assertTrue((data_dir / "policy_files").is_dir())
            self.assertTrue((data_dir / "raw_sources").is_dir())
            self.assertEqual(result["migratedProjects"], 1)
            repository = SqliteProjectRepository(data_dir / "ue-agent.sqlite3")
            self.assertEqual(len(repository.list_projects()), 1)

    def test_bootstrap_is_idempotent_and_keeps_existing_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            data_dir.mkdir()
            _seed_json_repository(data_dir / "projects.json")

            first = bootstrap_local_data(data_dir)
            repository = SqliteProjectRepository(data_dir / "ue-agent.sqlite3")
            project = repository.list_projects()[0]
            repository.create_scenario(project["id"], {"name": "乐观"})
            second = bootstrap_local_data(data_dir)

            self.assertEqual(first["migratedProjects"], 1)
            self.assertEqual(second["migratedProjects"], 0)
            reopened = SqliteProjectRepository(data_dir / "ue-agent.sqlite3")
            self.assertEqual(len(reopened.list_projects()), 1)
            self.assertEqual([s["name"] for s in reopened.list_projects()[0]["scenarios"]], ["基准", "乐观"])

    def test_bootstrap_without_json_only_creates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"

            result = bootstrap_local_data(data_dir)

            self.assertEqual(result["migratedProjects"], 0)
            self.assertTrue(result["database"].exists())
            self.assertEqual(SqliteProjectRepository(result["database"]).list_projects(), [])


if __name__ == "__main__":
    unittest.main()
