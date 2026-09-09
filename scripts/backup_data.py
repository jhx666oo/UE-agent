"""手动备份本地运行数据。

把 SQLite 数据库、政策原文目录和抓取原文目录整体复制到一个带时间戳的备份目录。
数据库使用 SQLite 在线备份接口复制，避免直接拷贝正在写入的文件；
备份过程只读取源数据，绝不删除或修改当前运行数据。
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "services" / "api") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from app.sqlite_repository import DATABASE_NAME, default_data_dir

FOLDER_NAMES = ("policy_files", "raw_sources")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _copy_folder(source: Path, target: Path) -> int:
    if not source.is_dir():
        return 0
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in sorted(source.rglob("*")):
        if item.is_file():
            destination = target / item.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
            copied += 1
    return copied


def create_backup(data_dir: Path | None = None, backups_dir: Path | None = None) -> Path:
    root = Path(data_dir or default_data_dir())
    database = root / DATABASE_NAME
    if not database.is_file():
        raise FileNotFoundError(f"未找到数据库，请先执行 pnpm bootstrap：{database}")

    base = Path(backups_dir or root.parent / "backups") / _timestamp()
    destination = base
    suffix = 1
    while destination.exists():
        destination = base.parent / f"{base.name}-{suffix}"
        suffix += 1
    destination.mkdir(parents=True)

    backup_database = destination / DATABASE_NAME
    source_connection = sqlite3.connect(str(database))
    target_connection = sqlite3.connect(str(backup_database))
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()

    integrity_connection = sqlite3.connect(str(backup_database))
    try:
        ok = integrity_connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        integrity_connection.close()
    if ok != "ok":
        raise RuntimeError("备份数据库完整性校验失败")

    manifest_lines = [f"database: {DATABASE_NAME}", "integrity_check: ok"]
    for folder in FOLDER_NAMES:
        copied = _copy_folder(root / folder, destination / folder)
        manifest_lines.append(f"{folder}: {copied} 个文件")

    legacy_json = root / "projects.json"
    if legacy_json.is_file():
        shutil.copy2(legacy_json, destination / legacy_json.name)
        manifest_lines.append("projects.json: 已复制迁移源文件")

    (destination / "MANIFEST.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="备份 UE Agent 本地数据")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="本地数据目录")
    parser.add_argument(
        "--backups-dir",
        type=Path,
        default=default_data_dir().parent / "backups",
        help="备份存放目录",
    )
    arguments = parser.parse_args()

    destination = create_backup(arguments.data_dir, arguments.backups_dir)
    print(f"备份完成：{destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
