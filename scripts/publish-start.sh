#!/usr/bin/env bash
# 单端口发布启动脚本。
#
# 发布环境只暴露一个公网端口（PORT），因此本脚本把前后端合并到同一入口：
#   1. 初始化 API 的 SQLite 数据目录（建库建表，不带任何本地业务数据）
#   2. 构建前端（单端口模式：API 走同源相对路径 /api/*）
#   3. 后台启动 FastAPI，监听 127.0.0.1:8000（仅本机，不直接对外）
#   4. 启动 Next.js，监听 0.0.0.0:$PORT（唯一的公网入口）
#   5. Next.js 通过 next.config.ts 的 rewrite 把 /api/* 代理到 FastAPI
#
# 前端把 NEXT_PUBLIC_API_BASE_URL 置空，使所有请求走同源相对路径（/api/...），
# 浏览器无需感知后端真实地址。
#
# Python 解释器优先级：PUBLISH_PYTHON > ./.venv-publish/bin/python > python3
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

PORT="${PORT:-3000}"
API_INTERNAL_PORT="${API_INTERNAL_PORT:-8000}"
export API_INTERNAL_ORIGIN="http://127.0.0.1:${API_INTERNAL_PORT}"
export UE_AGENT_SINGLE_PORT=1

# 数据写入项目内可写目录（不含本地业务数据）。
export UE_AGENT_DATA_DIR="${UE_AGENT_DATA_DIR:-$ROOT/runtime-data}"
mkdir -p "$UE_AGENT_DATA_DIR"

PYTHON_BIN="${PUBLISH_PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$ROOT/.venv-publish/bin/python" ]; then
    PYTHON_BIN="$ROOT/.venv-publish/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi
echo "[publish] 使用 Python：$PYTHON_BIN"

echo "[publish] 初始化 API 数据库目录：$UE_AGENT_DATA_DIR"
PYTHONPATH="$ROOT/services/api" "$PYTHON_BIN" - <<'PY'
from pathlib import Path
import os
from app.sqlite_repository import initialize_database, DATABASE_NAME

data_dir = Path(os.environ["UE_AGENT_DATA_DIR"])
initialize_database(data_dir / DATABASE_NAME)
print(f"[publish] 数据库就绪：{data_dir / DATABASE_NAME}")
PY

echo "[publish] 构建前端（单端口模式）"
cd "$ROOT/apps/web"
NEXT_PUBLIC_API_BASE_URL="" UE_AGENT_SINGLE_PORT=1 \
  API_INTERNAL_ORIGIN="$API_INTERNAL_ORIGIN" \
  ./node_modules/.bin/next build

echo "[publish] 启动 FastAPI（127.0.0.1:${API_INTERNAL_PORT}）"
PYTHONPATH="$ROOT/services/api" "$PYTHON_BIN" -m uvicorn app.main:app \
  --host 127.0.0.1 --port "$API_INTERNAL_PORT" --log-level warning &
API_PID=$!

cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "[publish] 等待 API 就绪…"
for _ in $(seq 1 60); do
  if curl -fsS --noproxy '*' "http://127.0.0.1:${API_INTERNAL_PORT}/api/health" >/dev/null 2>&1; then
    echo "[publish] API 已就绪"
    break
  fi
  sleep 1
done

echo "[publish] 启动前端（0.0.0.0:${PORT}）"
PORT="$PORT" NEXT_PUBLIC_API_BASE_URL="" ./node_modules/.bin/next start \
  --hostname 0.0.0.0 --port "$PORT"
