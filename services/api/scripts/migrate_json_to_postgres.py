from __future__ import annotations

import os
from pathlib import Path

from app.repository import JsonProjectRepository, PostgresProjectRepository


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    source_path = Path(os.getenv("UE_AGENT_DATA_FILE", "services/api/data/projects.json"))
    source = JsonProjectRepository(source_path)
    target = PostgresProjectRepository(database_url)
    target._write(source._read())
    print(f"Migrated {source_path} into ue_agent_store")


if __name__ == "__main__":
    main()
