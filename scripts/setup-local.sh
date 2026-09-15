#!/usr/bin/env bash
# 接手方一键安装本地运行依赖、初始化或恢复 SQLite 数据。
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
PYTHON_BIN="${UE_AGENT_SETUP_PYTHON:-python3}"
VENV_DIR="$ROOT/services/api/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 Python：$PYTHON_BIN" >&2
  exit 1
fi

if [ ! -x "$VENV_PYTHON" ]; then
  echo "[setup] 创建 Python 虚拟环境：$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
  echo "[setup] 修复 Python 虚拟环境中的 pip"
  "$VENV_PYTHON" -m ensurepip --upgrade >/dev/null
fi

echo "[setup] 安装 API 依赖"
"$VENV_PYTHON" -m pip install --upgrade pip >/dev/null
"$VENV_PYTHON" -m pip install -r <("$VENV_PYTHON" "$ROOT/scripts/_read_api_deps.py")

echo "[setup] 安装前端依赖"
if command -v pnpm >/dev/null 2>&1; then
  pnpm install --frozen-lockfile
elif command -v corepack >/dev/null 2>&1; then
  corepack pnpm install --frozen-lockfile
else
  echo "未找到 pnpm 或 corepack，请先安装 Node.js 20+。" >&2
  exit 1
fi

DATA_DIR="${UE_AGENT_DATA_DIR:-$ROOT/services/api/data}"
if [ ! -f "$DATA_DIR/ue-agent.sqlite3" ] && [ -f "$ROOT/handoff-data/ue-agent.sqlite3" ]; then
  echo "[setup] 恢复交付包内业务数据"
  PYTHONPATH="$ROOT/services/api:$ROOT" "$VENV_PYTHON" "$ROOT/scripts/restore_data.py" \
    --from "$ROOT/handoff-data" --data-dir "$DATA_DIR"
else
  echo "[setup] 初始化本地 SQLite"
  PYTHONPATH="$ROOT/services/api:$ROOT" "$VENV_PYTHON" "$ROOT/services/api/scripts/bootstrap.py" \
    --data-dir "$DATA_DIR"
fi

echo "[setup] 完成。启动：bash scripts/dev-all.sh"
