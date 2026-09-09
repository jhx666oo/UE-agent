from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.sqlite_repository import DATABASE_NAME, default_database_path, initialize_database
from scripts.backup_data import create_backup
from scripts.restore_data import restore_backup


def _seed(data_dir: Path) -> None:
    database = initialize_database(data_dir / DATABASE_NAME)
    connection = sqlite3.connect(str(database))
    try:
        with connection:
            connection.execute(
                "INSERT INTO projects (id, name, city_id, city, district, base_month, station_mode,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("project-1", "长沙 U1 试算", "changsha", "长沙", "岳麓区", "2026-09", "自营", "T", "T"),
            )
    finally:
        connection.close()
    (data_dir / "policy_files").mkdir(parents=True, exist_ok=True)
    (data_dir / "policy_files" / "政策原文.pdf").write_bytes(b"policy!")
    (data_dir / "raw_sources").mkdir(parents=True, exist_ok=True)
    (data_dir / "raw_sources" / "artifact.html").write_text("<p>原文</p>", encoding="utf-8")


class BackupDataTests(unittest.TestCase):
    def test_backup_contains_database_policy_files_and_raw_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            data_dir.mkdir()
            _seed(data_dir)

            destination = create_backup(data_dir, root / "backups")

            self.assertTrue((destination / DATABASE_NAME).is_file())
            self.assertEqual((destination / "policy_files" / "政策原文.pdf").read_bytes(), b"policy!")
            self.assertEqual(
                (destination / "raw_sources" / "artifact.html").read_text(encoding="utf-8"), "<p>原文</p>"
            )
            manifest = (destination / "MANIFEST.txt").read_text(encoding="utf-8")
            self.assertIn("integrity_check: ok", manifest)
            self.assertIn("policy_files: 1 个文件", manifest)
            self.assertIn("raw_sources: 1 个文件", manifest)

            connection = sqlite3.connect(str(destination / DATABASE_NAME))
            try:
                rows = connection.execute("SELECT id, name FROM projects").fetchall()
            finally:
                connection.close()
            self.assertEqual(rows, [("project-1", "长沙 U1 试算")])

    def test_backup_never_touches_running_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            data_dir.mkdir()
            _seed(data_dir)

            create_backup(data_dir, root / "backups")

            self.assertTrue((data_dir / DATABASE_NAME).is_file())
            self.assertEqual((data_dir / "policy_files" / "政策原文.pdf").read_bytes(), b"policy!")
            self.assertEqual((data_dir / "raw_sources" / "artifact.html").read_text(encoding="utf-8"), "<p>原文</p>")

    def test_two_backups_in_the_same_second_do_not_overwrite_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            data_dir.mkdir()
            _seed(data_dir)

            first = create_backup(data_dir, root / "backups")
            second = create_backup(data_dir, root / "backups")

            self.assertNotEqual(first, second)
            for destination in (first, second):
                self.assertTrue((destination / DATABASE_NAME).is_file())
                self.assertEqual((destination / "policy_files" / "政策原文.pdf").read_bytes(), b"policy!")

    def test_missing_database_is_reported_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                create_backup(root / "data", root / "backups")

    def test_default_path_stays_under_services_api(self) -> None:
        path = default_database_path()

        self.assertEqual(path.parent.parent.name, "api")


class RestoreDataTests(unittest.TestCase):
    @staticmethod
    def _project_names(database: Path) -> list[str]:
        connection = sqlite3.connect(str(database))
        try:
            return [row[0] for row in connection.execute("SELECT name FROM projects ORDER BY name")]
        finally:
            connection.close()

    def test_restore_returns_to_backup_and_keeps_pre_restore_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            data_dir.mkdir()
            _seed(data_dir)
            backup = create_backup(data_dir, root / "backups")
            database = data_dir / DATABASE_NAME
            connection = sqlite3.connect(str(database))
            try:
                with connection:
                    connection.execute("UPDATE projects SET name = '恢复后被改掉' WHERE id = 'project-1'")
            finally:
                connection.close()
            self.assertEqual(self._project_names(database), ["恢复后被改掉"])

            safety_copy = restore_backup(backup, data_dir)

            self.assertEqual(self._project_names(database), ["长沙 U1 试算"])
            self.assertIsNotNone(safety_copy)
            assert safety_copy is not None
            self.assertEqual(self._project_names(safety_copy / DATABASE_NAME), ["恢复后被改掉"])
            self.assertEqual((data_dir / "policy_files" / "政策原文.pdf").read_bytes(), b"policy!")
            self.assertIn(str(backup), (data_dir / "RESTORE_SOURCE.txt").read_text(encoding="utf-8"))

    def test_restore_into_empty_data_dir_reports_no_previous_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            data_dir.mkdir()
            _seed(root / "source-data")
            backup = create_backup(root / "source-data", root / "backups")

            safety_copy = restore_backup(backup, data_dir)

            self.assertIsNone(safety_copy)
            self.assertEqual(self._project_names(data_dir / DATABASE_NAME), ["长沙 U1 试算"])

    def test_invalid_backup_is_rejected_without_touching_current_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            data_dir.mkdir()
            _seed(data_dir)

            with self.assertRaises(FileNotFoundError):
                restore_backup(root / "backups" / "不存在", data_dir)

            self.assertEqual(self._project_names(data_dir / DATABASE_NAME), ["长沙 U1 试算"])
            self.assertEqual((data_dir / "policy_files" / "政策原文.pdf").read_bytes(), b"policy!")


if __name__ == "__main__":
    unittest.main()
