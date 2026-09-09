import json
import tempfile
import unittest
from pathlib import Path

from app.repository import JsonProjectRepository


class JsonProjectRepositoryTests(unittest.TestCase):
    def test_project_and_scenario_round_trip_preserves_zero_and_null(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projects.json"
            repository = JsonProjectRepository(path)
            project = repository.create_project(
                {
                    "name": "长沙 U1 试算",
                    "city": "长沙",
                    "district": "岳麓区",
                    "baseMonth": "2026-09",
                    "stationMode": "自营",
                }
            )
            scenario = repository.create_scenario(
                project["id"],
                {"name": "基准", "inputs": {"A1": 0, "C11": None}},
            )
            updated = repository.update_scenario(
                project["id"],
                scenario["id"],
                {"inputs": {"A1": 0, "C11": None, "P1": 50}},
            )

            self.assertEqual(updated["inputs"]["A1"], 0)
            self.assertIsNone(updated["inputs"]["C11"])
            self.assertEqual(updated["inputs"]["P1"], 50)

            reloaded = JsonProjectRepository(path)
            loaded = reloaded.get_project(project["id"])
            self.assertEqual(loaded["scenarios"][0]["id"], scenario["id"])
            self.assertEqual(loaded["scenarios"][0]["inputs"]["A1"], 0)
            self.assertIsNone(loaded["scenarios"][0]["inputs"]["C11"])

            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(raw["projects"]), 1)

    def test_missing_records_raise_key_error(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonProjectRepository(Path(directory) / "projects.json")
            with self.assertRaises(KeyError):
                repository.get_project("missing-project")

    def test_calculating_same_scenario_creates_immutable_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonProjectRepository(Path(directory) / "projects.json")
            project = repository.create_project({"name": "快照测试", "city": "长沙"})
            scenario = repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})
            first = repository.save_calculation(
                project["id"],
                scenario["id"],
                {"modelVersion": "test-v1", "status": "ok", "headlineMetrics": {"x": 1}},
            )
            first_snapshot_id = first["resultSnapshotId"]
            second = repository.save_calculation(
                project["id"],
                scenario["id"],
                {"modelVersion": "test-v1", "status": "ok", "headlineMetrics": {"x": 2}},
            )

            self.assertNotEqual(first_snapshot_id, second["resultSnapshotId"])
            self.assertEqual(second["status"], "calculated")
            snapshots = repository.list_snapshots(project["id"], scenario["id"])
            self.assertEqual(len(snapshots), 2)
            self.assertEqual(snapshots[0]["resultSnapshot"]["headlineMetrics"]["x"], 1)
            self.assertEqual(snapshots[1]["resultSnapshot"]["headlineMetrics"]["x"], 2)

    def test_updating_inputs_marks_calculated_scenario_stale_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonProjectRepository(Path(directory) / "projects.json")
            project = repository.create_project({"name": "stale 测试", "city": "长沙"})
            scenario = repository.create_scenario(project["id"], {"name": "基准", "inputs": {"P1": 50}})
            calculated = repository.save_calculation(
                project["id"],
                scenario["id"],
                {"modelVersion": "test-v1", "status": "ok", "headlineMetrics": {"x": 1}},
            )

            updated = repository.update_scenario(project["id"], scenario["id"], {"inputs": {"P1": 60}})

            self.assertEqual(updated["status"], "stale")
            self.assertIsNone(updated["resultSnapshotId"])
            self.assertIsNone(updated["result"])
            self.assertEqual(repository.get_snapshot(calculated["resultSnapshotId"])["resultSnapshot"]["headlineMetrics"]["x"], 1)


if __name__ == "__main__":
    unittest.main()
