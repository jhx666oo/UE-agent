"""本地运行环境初始化。

一条命令完成：建数据目录、建库建表、只在目标库还没有项目时导入既有 JSON 数据。
重复执行只补齐缺失目录并确认表结构，不会覆盖或重复导入业务数据。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:  # 允许直接以脚本方式运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sqlite_repository import (
    DATABASE_NAME,
    default_data_dir,
    initialize_database,
)
from scripts.migrate_json_to_sqlite import migrate_json_to_sqlite


def bootstrap_local_data(data_dir: Path | None = None) -> dict[str, object]:
    root = Path(data_dir or default_data_dir())
    root.mkdir(parents=True, exist_ok=True)
    database = initialize_database(root / DATABASE_NAME)
    report = migrate_json_to_sqlite(root / "projects.json", database)
    return {
        "data_dir": root,
        "database": database,
        "report": report,
        "migratedProjects": report.projects if report.applied else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 UE Agent 本地数据目录与 SQLite 数据库")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="本地数据目录")
    arguments = parser.parse_args()

    result = bootstrap_local_data(arguments.data_dir)
    report = result["report"]
    print(f"数据目录：{result['data_dir']}")
    print(f"数据库：{result['database']}")
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
