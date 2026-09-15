#!/usr/bin/env bash
# 用可移植的本地 Python 环境启动 FastAPI 开发服务。
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
API_PORT="${API_PORT:-8000}"

PYTHON_BIN="${UE_AGENT_API_PYTHON:-}"
if [ -z "$PYTHON_BIN" ] && [ -x "$ROOT/services/api/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/services/api/.venv/bin/python"
fi
if [ -z "$PYTHON_BIN" ] && [ -x "$ROOT/.venv-publish/bin/python" ]; then
  PYTHON_BIN="$ROOT/.venv-publish/bin/python"
fi
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

if "$PYTHON_BIN" -c 'import uvicorn' >/dev/null 2>&1; then
  exec env PYTHONPATH="$ROOT/services/api" "$PYTHON_BIN" -m uvicorn app.main:app \
    --reload --host 127.0.0.1 --port "$API_PORT"
fi

if command -v uv >/dev/null 2>&1; then
  exec env PYTHONPATH="$ROOT/services/api" uv run --project services/api uvicorn app.main:app \
    --reload --host 127.0.0.1 --port "$API_PORT"
fi

echo "未找到 uvicorn。请先执行 bash scripts/setup-local.sh，或设置 UE_AGENT_API_PYTHON。" >&2
exit 1
