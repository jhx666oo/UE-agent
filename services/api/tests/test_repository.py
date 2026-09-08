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


if __name__ == "__main__":
    unittest.main()
