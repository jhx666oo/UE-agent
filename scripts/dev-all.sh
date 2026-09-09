#!/usr/bin/env bash
# 一条命令同时启动本地 API 与前端，供业务侧自测和交付演示使用。
# 不读取也不打印任何密钥；任一子进程退出即整体退出。
set -euo pipefail

cd "$(dirname "$0")/.."

api_pid=""
web_pid=""

shutdown() {
  trap - INT TERM EXIT
  for pid in "$api_pid" "$web_pid"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}

trap shutdown INT TERM EXIT

echo "启动本地 API（http://localhost:8000）…"
pnpm api:dev &
api_pid=$!

echo "启动前端（http://localhost:3000）…"
pnpm dev &
web_pid=$!

# 任一进程退出就停止另一个，避免留下半死不活的服务。
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 1
done

for pid in "$api_pid" "$web_pid"; do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "进程 $pid 已退出，正在停止其余服务。"
  fi
done
