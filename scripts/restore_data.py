"""从备份目录恢复本地数据。

恢复属于覆盖性操作，因此顺序固定为：校验备份完整性 → 先把当前数据整体存成
一份带时间戳的安全副本 → 再写入恢复数据。任何一步失败都会保留现有数据库，
不做半覆盖。
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


def validate_backup(backup_dir: Path) -> Path:
    source = Path(backup_dir)
    database = source / DATABASE_NAME
    if not database.is_file():
        raise FileNotFoundError(f"备份缺少数据库文件：{database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        ok = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    if ok != "ok":
        raise RuntimeError("备份数据库完整性校验失败，已取消恢复")
    return database


def _checkpoint(database: Path) -> None:
    """把 WAL 内容合并回主库文件，避免恢复后留下错位的附属文件。"""
    if not database.is_file():
        return
    connection = sqlite3.connect(str(database))
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()


def restore_backup(backup_dir: Path, data_dir: Path | None = None) -> Path | None:
    """校验备份 → 现有数据整体移入安全副本 → 从备份复制回来。

    返回安全副本路径；恢复前没有数据时返回 None。
    """
    source = Path(backup_dir)
    validate_backup(source)
    root = Path(data_dir or default_data_dir())
    root.mkdir(parents=True, exist_ok=True)
    _checkpoint(root / DATABASE_NAME)

    sidecars = tuple(f"{DATABASE_NAME}{suffix}" for suffix in ("-wal", "-shm"))
    names = (DATABASE_NAME, *sidecars, *FOLDER_NAMES, "projects.json")
    current_items = [name for name in names if (root / name).exists()]
    if not current_items:
        for name in (DATABASE_NAME, *FOLDER_NAMES):
            item = source / name
            if item.is_file():
                shutil.copy2(item, root / name)
            elif item.is_dir():
                shutil.copytree(item, root / name)
        return None

    safety_copy = root.parent / "backups" / f"pre-restore-{_timestamp()}"
    safety_copy.mkdir(parents=True, exist_ok=False)
    for name in current_items:
        # 移动而不是删除：现有数据完整保留在安全副本里，同时腾出恢复位置。
        shutil.move(str(root / name), str(safety_copy / name))

    for name in (DATABASE_NAME, *FOLDER_NAMES):
        item = source / name
        if item.is_file():
            shutil.copy2(item, root / name)
        elif item.is_dir():
            shutil.copytree(item, root / name)

    (root / "RESTORE_SOURCE.txt").write_text(
        f"restored from {source}\nprevious data saved to {safety_copy}\n", encoding="utf-8"
    )
    return safety_copy


def main() -> int:
    parser = argparse.ArgumentParser(description="从备份目录恢复 UE Agent 本地数据")
    parser.add_argument("--from", dest="backup_dir", type=Path, required=True, help="备份目录路径")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="恢复到的数据目录")
    arguments = parser.parse_args()

    safety_copy = restore_backup(arguments.backup_dir, arguments.data_dir)
    print(f"恢复完成：{arguments.data_dir}")
    if safety_copy is not None:
        print(f"恢复前的数据已保存到：{safety_copy}")
    else:
        print("恢复前没有已存在的数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
