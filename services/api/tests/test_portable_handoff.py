from __future__ import annotations

import json
import sqlite3
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from app.sqlite_repository import DATABASE_NAME, initialize_database
from scripts.handoff import copy_portable_source, package_handoff


REPO_ROOT = Path(__file__).resolve().parents[3]
AUTOMATION_TEMPLATE = REPO_ROOT / ".workbuddy/automations/policy-ai-sync.template.json"
PORTABLE_SCRIPTS = (
    "scripts/setup-local.sh",
    "scripts/api-python.sh",
    "scripts/api-dev.sh",
    "scripts/check-portable.sh",
    "scripts/package-handoff.sh",
)


class PortableSourceTests(unittest.TestCase):
    def test_copy_portable_source_keeps_delivery_assets_and_excludes_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            for relative, content in {
                "README.md": "portable",
                "apps/web/.env.example": "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000",
                "apps/web/.env.local": "VERCEL_OIDC_TOKEN=do-not-copy",
                ".git/config": "private",
                ".vercel/project.json": "private project state",
                ".arts/settings.json": "local tool state",
                ".codeartsdoer/settings.json": "local tool state",
                "node_modules/pkg/index.js": "dependency",
                ".next/cache": "build",
                ".workbuddy/memory/private.md": "private memory",
                ".workbuddy/session.json": "private session",
                ".workbuddy/skills/policy-ai-crawler/SKILL.md": "skill",
                ".workbuddy/automations/policy-ai-sync.template.json": "automation",
            }.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            copy_portable_source(source, target)

            self.assertEqual((target / "README.md").read_text(encoding="utf-8"), "portable")
            self.assertTrue((target / ".workbuddy/skills/policy-ai-crawler/SKILL.md").is_file())
            self.assertTrue((target / ".workbuddy/automations/policy-ai-sync.template.json").is_file())
            for excluded in (
                "apps/web/.env.local",
                ".git/config",
                ".vercel/project.json",
                ".arts/settings.json",
                ".codeartsdoer/settings.json",
                "node_modules/pkg/index.js",
                ".next/cache",
                ".workbuddy/memory/private.md",
                ".workbuddy/session.json",
            ):
                self.assertFalse((target / excluded).exists(), excluded)

    def test_package_handoff_contains_verified_data_and_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            data_dir = repo / "services/api/data"
            data_dir.mkdir(parents=True)
            (repo / ".workbuddy/skills/policy-ai-crawler").mkdir(parents=True)
            (repo / ".workbuddy/skills/policy-ai-crawler/SKILL.md").write_text("skill", encoding="utf-8")
            (repo / ".workbuddy/automations").mkdir(parents=True)
            (repo / ".workbuddy/automations/policy-ai-sync.template.json").write_text("{}", encoding="utf-8")
            (repo / "README.md").write_text("readme", encoding="utf-8")
            database = initialize_database(data_dir / DATABASE_NAME)
            connection = sqlite3.connect(str(database))
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO projects (id, name, city_id, city, district, base_month, station_mode, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        ("project-1", "长沙测算", "长沙", "长沙", "岳麓区", "2026-09", "自营", "T", "T"),
                    )
            finally:
                connection.close()
            (data_dir / "raw_sources").mkdir(exist_ok=True)
            (data_dir / "raw_sources/source.html").write_text("原文", encoding="utf-8")

            archive = package_handoff(repo, root / "dist")

            self.assertTrue(archive.is_file())
            with tarfile.open(archive, "r:gz") as package:
                if sys.version_info >= (3, 12):
                    package.extractall(root / "extracted", filter="data")
                else:
                    package.extractall(root / "extracted")
            package_root = next((root / "extracted").iterdir())
            backup = package_root / "handoff-data"
            self.assertTrue((backup / DATABASE_NAME).is_file())
            self.assertTrue((backup / "raw_sources/source.html").is_file())
            self.assertTrue((package_root / "HANDOFF.md").is_file())
            self.assertIn("bash scripts/setup-local.sh", (package_root / "HANDOFF.md").read_text(encoding="utf-8"))

            connection = sqlite3.connect(str(backup / DATABASE_NAME))
            try:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(connection.execute("SELECT name FROM projects").fetchone()[0], "长沙测算")
            finally:
                connection.close()

            self.assertFalse((package_root / "apps/web/.env.local").exists())
            self.assertFalse((package_root / ".workbuddy/memory").exists())


class PortableContractTests(unittest.TestCase):
    def test_workbuddy_automation_template_is_account_neutral(self) -> None:
        payload = json.loads(AUTOMATION_TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(payload["skill"], "policy-ai-crawler")
        self.assertEqual(payload["timezone"], "Asia/Shanghai")
        self.assertIn("FREQ=DAILY", payload["rrule"])
        self.assertIn("全城市", payload["prompt"])
        self.assertIn("/api/projects", payload["prompt"])
        self.assertNotIn("/Users/", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("UE_AGENT_AGENT_TOKEN=", json.dumps(payload, ensure_ascii=False))

    def test_portable_scripts_are_executable_and_account_neutral(self) -> None:
        for relative in PORTABLE_SCRIPTS:
            path = REPO_ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR, relative)
            self.assertNotIn("/Users/jhx", path.read_text(encoding="utf-8"))

    def test_startup_contract_uses_portable_api_script(self) -> None:
        package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(
            package["scripts"]["api:test"],
            "bash scripts/api-python.sh -m unittest discover -s services/api/tests -p 'test_*.py'",
        )
        self.assertEqual(package["scripts"]["api:dev"], "bash scripts/api-dev.sh")
        self.assertEqual(package["scripts"]["bootstrap"], "bash scripts/api-python.sh services/api/scripts/bootstrap.py")
        self.assertEqual(package["scripts"]["data:backup"], "bash scripts/api-python.sh scripts/backup_data.py")
        self.assertEqual(package["scripts"]["data:restore"], "bash scripts/api-python.sh scripts/restore_data.py")
        self.assertEqual(package["scripts"]["setup"], "bash scripts/setup-local.sh")
        self.assertEqual(package["scripts"]["handoff:check"], "bash scripts/check-portable.sh")
        self.assertEqual(package["scripts"]["handoff:package"], "bash scripts/package-handoff.sh")

    def test_setup_repairs_an_existing_virtualenv_without_pip(self) -> None:
        setup = (REPO_ROOT / "scripts/setup-local.sh").read_text(encoding="utf-8")
        self.assertIn("-m pip --version", setup)
        self.assertIn("-m ensurepip --upgrade", setup)

    def test_docs_explain_account_owned_task_boundary(self) -> None:
        document = (REPO_ROOT / "docs/deployment/portable-handoff.md").read_text(encoding="utf-8")
        self.assertIn("WorkBuddy", document)
        self.assertIn("定时任务", document)
        self.assertIn("一次", document)
        self.assertIn("不会包含", document)


if __name__ == "__main__":
    unittest.main()
