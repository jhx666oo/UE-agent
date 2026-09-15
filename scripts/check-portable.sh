#!/usr/bin/env bash
# 检查仓库是否具备可交付的源码、Skill、自动化模板和启动入口。
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
FAILED=0

required_files=(
  ".env.example"
  "AGENTS.md"
  "PROJECT_CONTEXT.md"
  ".workbuddy/skills/policy-ai-crawler/SKILL.md"
  ".workbuddy/skills/policy-city-onboarding/SKILL.md"
  ".workbuddy/automations/policy-ai-sync.template.json"
  "scripts/setup-local.sh"
  "scripts/api-python.sh"
  "scripts/api-dev.sh"
  "scripts/check-portable.sh"
  "scripts/package-handoff.sh"
)

for relative in "${required_files[@]}"; do
  if [ ! -f "$ROOT/$relative" ]; then
    echo "缺少交付文件：$relative" >&2
    FAILED=1
  fi
done

for relative in "${required_files[@]}"; do
  case "$relative" in
    scripts/*.sh)
      if [ -f "$ROOT/$relative" ] && [ ! -x "$ROOT/$relative" ]; then
        echo "脚本不可执行：$relative" >&2
        FAILED=1
      fi
      ;;
  esac
done

if command -v git >/dev/null 2>&1; then
  tracked_secrets="$(git -C "$ROOT" ls-files | grep -E '(^|/)\.env(\.|$)' | grep -vE '(^|/)\.env\.example$' || true)"
  if [ -n "$tracked_secrets" ]; then
    echo "Git 已跟踪疑似密钥文件：$tracked_secrets" >&2
    FAILED=1
  fi
fi

if command -v python3 >/dev/null 2>&1; then
  if ! python3 - "$ROOT/.workbuddy/automations/policy-ai-sync.template.json" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
assert payload["skill"] == "policy-ai-crawler"
assert "FREQ=" in payload["rrule"]
assert "全城市" in payload["prompt"]
assert "/Users/" not in json.dumps(payload, ensure_ascii=False)
PY
  then
    echo "WorkBuddy 自动化模板校验失败" >&2
    FAILED=1
  fi
fi

if [ "$FAILED" -ne 0 ]; then
  exit 1
fi

echo "可移植交付检查通过：源码、SQLite 交付入口、WorkBuddy Skill 和定时任务模板齐全。"
