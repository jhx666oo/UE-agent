#!/usr/bin/env bash
# 发布环境安装：一次装好 Python 与 Node 两侧依赖。
#
# 发布沙箱不包含任何预装依赖，因此这里显式安装：
#   1. Python：在仓库根建 .venv-publish，按 services/api/pyproject.toml 装 API 依赖
#   2. Node：用 pnpm 按 workspace 安装前端与共享包依赖
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

echo "[install] 准备 Python 虚拟环境 .venv-publish"
python3 -m venv "$ROOT/.venv-publish"
"$ROOT/.venv-publish/bin/python" -m pip install --upgrade pip >/dev/null

# 依赖清单的权威来源是 services/api/pyproject.toml。app/main.py 顶层就导入了
# PostgresProjectRepository / VercelBlobPolicyFileStore，缺 psycopg 或 vercel 会让
# uvicorn 在 import 阶段直接失败，所以这里从 pyproject 动态解析而不是手写列表。
DEPS_FILE="$ROOT/.publish-api-deps.txt"
"$ROOT/.venv-publish/bin/python" "$ROOT/scripts/_read_api_deps.py" > "$DEPS_FILE"
echo "[install] API 依赖："
cat "$DEPS_FILE"
# xargs 逐行转参数，兼容 bash 3.2（无 mapfile）
xargs -a "$DEPS_FILE" "$ROOT/.venv-publish/bin/python" -m pip install
rm -f "$DEPS_FILE"

echo "[install] 安装 Node 依赖（pnpm workspace）"
if command -v pnpm >/dev/null 2>&1; then
  pnpm install --frozen-lockfile
else
  # 沙箱没有 pnpm 时用 corepack 拉起锁定的包管理器版本
  corepack pnpm install --frozen-lockfile
fi

echo "[install] 完成"
