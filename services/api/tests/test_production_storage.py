from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from app.main import allowed_origins, create_repository
from app.repository import JsonProjectRepository, VercelBlobPolicyFileStore
from app.sqlite_repository import SqliteProjectRepository


class FakeBlobClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, pathname: str, content: bytes, **_: object) -> SimpleNamespace:
        self.objects[pathname] = content
        return SimpleNamespace(pathname=pathname, url=f"https://blob.test/{pathname}")

    def get(self, pathname: str, **_: object) -> SimpleNamespace:
        return SimpleNamespace(content=self.objects[pathname])


class ProductionStorageTests(TestCase):
    def test_allowed_origins_reads_comma_separated_environment_value(self) -> None:
        with patch.dict(os.environ, {"UE_AGENT_ALLOWED_ORIGINS": "https://ue.vercel.app, https://ue.example.com"}, clear=False):
            self.assertEqual(
                allowed_origins(),
                ["https://ue.vercel.app", "https://ue.example.com"],
            )

    def test_database_url_selects_postgres_repository(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=False):
            with patch("app.main.PostgresProjectRepository") as repository_class:
                repository = create_repository()

        repository_class.assert_called_once()
        self.assertIs(repository, repository_class.return_value)

    def test_local_default_selects_sqlite_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "ue-agent.sqlite3"
            with patch.dict(
                os.environ,
                {"DATABASE_URL": "", "UE_AGENT_DB_FILE": str(database)},
                clear=False,
            ):
                repository = create_repository()

            self.assertIsInstance(repository, SqliteProjectRepository)
            self.assertTrue(database.exists())
            self.assertTrue((Path(directory) / "policy_files").is_dir())
            self.assertTrue((Path(directory) / "raw_sources").is_dir())

    def test_policy_document_can_use_blob_file_store_without_local_filesystem(self) -> None:
        blob_client = FakeBlobClient()
        file_store = VercelBlobPolicyFileStore(client_factory=lambda: blob_client)
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonProjectRepository(Path(directory) / "projects.json", file_store=file_store)
            document = repository.create_policy_document(
                {
                    "cityId": "changsha",
                    "originalName": "policy.pdf",
                    "mimeType": "application/pdf",
                    "size": 7,
                    "sha256": "abc",
                    "source": "official",
                },
                b"policy!",
                ".pdf",
            )

            self.assertEqual(document["storedPath"], f"policy_files/{document['id']}.pdf")
            self.assertFalse((Path(directory) / document["storedPath"]).exists())
            self.assertEqual(repository.read_policy_document(document), b"policy!")
