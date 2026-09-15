#!/usr/bin/env bash
# 统一选择 UE-Agent API 的 Python 运行环境，供 bootstrap、备份、恢复和测试使用。
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
PYTHON_BIN="${UE_AGENT_API_PYTHON:-}"

if [ -z "$PYTHON_BIN" ] && [ -x "$ROOT/services/api/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/services/api/.venv/bin/python"
fi
if [ -z "$PYTHON_BIN" ] && [ -x "$ROOT/.venv-publish/bin/python" ]; then
  PYTHON_BIN="$ROOT/.venv-publish/bin/python"
fi

if [ -n "$PYTHON_BIN" ]; then
  exec env PYTHONPATH="$ROOT/services/api:$ROOT" "$PYTHON_BIN" "$@"
fi

if command -v uv >/dev/null 2>&1; then
  exec env PYTHONPATH="$ROOT/services/api:$ROOT" uv run --project services/api "$@"
fi

exec env PYTHONPATH="$ROOT/services/api:$ROOT" python3 "$@"
