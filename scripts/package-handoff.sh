#!/usr/bin/env bash
# 生成源码 + 本地 SQLite/政策原文的可移植交付包。
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHONPATH="$PWD/services/api:$PWD" python3 scripts/handoff.py "$@"
