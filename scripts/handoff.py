"""Build a portable UE-Agent handoff archive.

The archive contains the current source tree and a verified copy of local
SQLite data, but never copies credentials, dependencies, build output, or
private WorkBuddy account memory.
"""

from __future__ import annotations

import argparse
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.backup_data import create_backup
from app.sqlite_repository import DATABASE_NAME


EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".arts",
    ".codeartsdoer",
    ".next",
    ".turbo",
    ".vercel",
    ".venv",
    ".venv-publish",
    "__pycache__",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "runtime-data",
}


def _is_excluded(relative: Path, *, is_dir: bool) -> bool:
    parts = relative.parts
    if not parts:
        return False
    if any(part in EXCLUDED_DIRECTORY_NAMES for part in parts):
        return True
    if parts[0] == ".workbuddy" and len(parts) >= 2 and parts[1] not in {"skills", "automations"}:
        return True
    if len(parts) >= 2 and parts[0:2] == ("services", "api") and parts[2:3] in (("data",), ("backups",)):
        return True
    if parts[0] == "handoff-data":
        return True
    if not is_dir and relative.name != ".env.example":
        if relative.name == ".env" or relative.name.startswith(".env."):
            return True
    return False


def copy_portable_source(repo_root: Path, target: Path) -> None:
    """Copy source files while applying the handoff exclusion policy."""

    source_root = Path(repo_root).resolve()
    target_root = Path(target).resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"仓库目录不存在：{source_root}")
    target_root.mkdir(parents=True, exist_ok=True)

    for current, directories, filenames in os.walk(source_root, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(source_root)
        directories[:] = [
            name
            for name in directories
            if not (current_path / name).is_symlink()
            and not _is_excluded(relative_current / name, is_dir=True)
        ]
        destination_current = target_root / relative_current
        destination_current.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            source_file = current_path / name
            relative_file = relative_current / name
            if source_file.is_symlink() or _is_excluded(relative_file, is_dir=False):
                continue
            destination_file = target_root / relative_file
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination_file)


def _data_dir(repo_root: Path) -> Path:
    configured = os.getenv("UE_AGENT_DATA_DIR", "").strip()
    if not configured:
        return repo_root / "services" / "api" / "data"
    configured_path = Path(configured).expanduser()
    return configured_path if configured_path.is_absolute() else repo_root / configured_path


def _next_archive_path(output_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = output_dir / f"ue-agent-handoff-{stamp}"
    candidate = base.with_suffix(".tar.gz")
    suffix = 1
    while candidate.exists():
        candidate = output_dir / f"{base.name}-{suffix}.tar.gz"
        suffix += 1
    return candidate


def _write_handoff_readme(path: Path, *, has_data: bool) -> None:
    data_note = (
        "本包包含 `handoff-data/`：当前 SQLite 数据库、政策原文和抓取原文，安装脚本会在空数据目录中自动恢复。"
        if has_data
        else "本包未包含业务数据；安装脚本会创建空的 SQLite 数据库，可再使用 `pnpm data:restore` 恢复备份。"
    )
    path.write_text(
        f"""# UE-Agent 交付包\n\n"
        "这是可继续开发的本地 Demo 交付包，包含源码、模型契约、前端、FastAPI、SQLite 数据结构、WorkBuddy 项目级 Skill 和定时任务模板。\n\n"
        f"{data_note}\n\n"
        "## 接手方启动\n\n"
        "```bash\n"
        "bash scripts/setup-local.sh\n"
        "bash scripts/dev-all.sh\n"
        "```\n\n"
        "浏览器打开 `http://localhost:3000`，API 文档为 `http://localhost:8000/docs`。\n\n"
        "## WorkBuddy 政策同步\n\n"
        "`.workbuddy/skills/` 中的两个 Skill 会随仓库一起交付。请在同一台电脑上打开这个工作区，并让 WorkBuddy 根据 `.workbuddy/automations/policy-ai-sync.template.json` 创建一次名为“UE-Agent 全城市政策同步”的定时任务。\n\n"
        "WorkBuddy 的定时任务记录属于接手人的账号，不会携带原账号 ID、登录态或令牌导出；这是唯一需要在接手方 WorkBuddy 中执行一次的初始化动作。任务运行时通过 `http://127.0.0.1:8000` 回写本地 API。\n\n"
        "## 数据与安全\n\n"
        "- `.env.local`、Vercel OIDC token、依赖目录、构建缓存和 WorkBuddy 私有 memory 不在交付包内。\n"
        "- `C6/C7/C8` 不允许估算。政策建议值只进入灰色待采用状态，不自动覆盖人工值。\n"
        "- 接手人如果要在另一台电脑运行 WorkBuddy，必须确认 WorkBuddy 能访问该电脑的 `127.0.0.1:8000`；云端任务不能直接访问本机地址。\n"
        """,
        encoding="utf-8",
    )


def package_handoff(
    repo_root: Path,
    output_dir: Path | None = None,
    *,
    include_data: bool = True,
) -> Path:
    """Create a source-plus-data handoff archive and return its path."""

    root = Path(repo_root).resolve()
    destination_dir = Path(output_dir or root / "dist").resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    archive_path = _next_archive_path(destination_dir)
    package_name = archive_path.name.removesuffix(".tar.gz")

    with tempfile.TemporaryDirectory(prefix=".ue-agent-handoff-", dir=str(destination_dir)) as staging_name:
        package_root = Path(staging_name) / package_name
        copy_portable_source(root, package_root)

        has_data = False
        data_root = _data_dir(root)
        database = data_root / DATABASE_NAME
        if include_data and database.is_file():
            backup_root = Path(staging_name) / "backup"
            backup = create_backup(data_root, backup_root)
            shutil.copytree(backup, package_root / "handoff-data")
            has_data = True

        _write_handoff_readme(package_root / "HANDOFF.md", has_data=has_data)
        temporary_archive = Path(staging_name) / archive_path.name
        with tarfile.open(temporary_archive, "w:gz") as package:
            package.add(package_root, arcname=package_name, recursive=True)
        os.replace(temporary_archive, archive_path)

    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 UE-Agent 可移植交付包")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--without-data", action="store_true", help="只打包源码，不带本地业务数据")
    arguments = parser.parse_args()
    archive = package_handoff(
        arguments.repo_root,
        arguments.output_dir,
        include_data=not arguments.without_data,
    )
    print(f"交付包已生成：{archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
