#!/usr/bin/env bash
# 端到端验证脚本：模拟 WorkBuddy 的完整一轮回传流程。
# 用法：bash scripts/e2e-agent-flow.sh
#
# 覆盖：派活清单 → 抓取落档（SHA256 变更检测）→ 回传校验 → 建议值写入 → 候选来源入池
#
# 注意：本脚本依赖 UE_AGENT_E2E_ALLOW_PRIVATE=1 放行回环地址，仅供本机验证；
# 生产抓取路径默认拒绝私有网段（crawlers 模块的 SSRF 防护）。
# JSON 解析统一交给 scripts/e2e_assert.py，避免 shell 与 Python 的引号嵌套问题。
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
PORT="${E2E_PORT:-8123}"
FIXTURE_PORT="${E2E_FIXTURE_PORT:-8124}"
BASE="http://127.0.0.1:${PORT}"
ASSERT="$ROOT/scripts/e2e_assert.py"
PY="${E2E_PYTHON:-python3}"

export UE_AGENT_DATA_DIR="${UE_AGENT_DATA_DIR:-/tmp/ue-e2e-data}"
export UE_AGENT_E2E_ALLOW_PRIVATE=1

rm -rf "$UE_AGENT_DATA_DIR"
mkdir -p "$UE_AGENT_DATA_DIR"

cleanup() {
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null
  [ -n "${FIX_PID:-}" ] && kill "$FIX_PID" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT

echo "==> 启动假政策页服务（127.0.0.1:$FIXTURE_PORT）"
PYTHONPATH=services/api "$PY" services/api/scripts/e2e_fixture_server.py "$FIXTURE_PORT" &
FIX_PID=$!

echo "==> 启动 API（127.0.0.1:$PORT）"
PYTHONPATH=services/api uv run --project services/api --extra test \
  python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
API_PID=$!

for _ in $(seq 1 160); do
  if curl -s --noproxy '*' "$BASE/api/health" > /dev/null 2>&1; then break; fi
  sleep 0.5
done
HEALTH=$(curl -s --noproxy '*' "$BASE/api/health")
if [ -z "$HEALTH" ]; then
  echo "错误：API 未能在 80 秒内启动，请检查 services/api 依赖。"
  exit 1
fi
echo "健康检查：$HEALTH"

echo
echo "==> 1. 建项目 + 场景（长沙）"
PROJECT_ID=$(curl -s --noproxy '*' -X POST "$BASE/api/projects" \
  -H 'Content-Type: application/json' \
  -d '{"name":"长沙养老测算","city":"长沙","cityId":"changsha"}' \
  | "$PY" -c "import sys,json;print(json.load(sys.stdin)['id'])")
SCENARIO_ID=$(curl -s --noproxy '*' -X POST "$BASE/api/projects/$PROJECT_ID/scenarios" \
  -H 'Content-Type: application/json' -d '{"name":"基准情景"}' \
  | "$PY" -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "   projectId=$PROJECT_ID"
echo "   scenarioId=$SCENARIO_ID"

echo
echo "==> 2. 配置官网来源（长沙医保局）"
SOURCE_ID=$(curl -s --noproxy '*' -X POST "$BASE/api/policies/sources" \
  -H 'Content-Type: application/json' \
  -d "{\"cityId\":\"changsha\",\"name\":\"长沙医保局\",\"url\":\"http://127.0.0.1:${FIXTURE_PORT}/policy\"}" \
  | "$PY" -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "   sourceId=$SOURCE_ID"

echo
echo "==> 3. 派活：GET /policies/crawl-targets"
curl -s --noproxy '*' "$BASE/api/policies/crawl-targets" | "$PY" "$ASSERT" targets

echo
echo "==> 4. 抓取：POST /policies/fetch-requests（API 抓取并落档）"
curl -s --noproxy '*' -X POST "$BASE/api/policies/fetch-requests" \
  -H 'Content-Type: application/json' \
  -d "{\"requests\":[{\"url\":\"http://127.0.0.1:${FIXTURE_PORT}/policy\",\"cityId\":\"changsha\",\"sourceId\":\"$SOURCE_ID\",\"name\":\"长沙医保局\"}]}" \
  | "$PY" "$ASSERT" fetch

echo
echo "==> 4b. 再抓一次：内容未变应标记 unchanged（AI 成本省在源头）"
curl -s --noproxy '*' -X POST "$BASE/api/policies/fetch-requests" \
  -H 'Content-Type: application/json' \
  -d "{\"requests\":[{\"url\":\"http://127.0.0.1:${FIXTURE_PORT}/policy\",\"cityId\":\"changsha\",\"sourceId\":\"$SOURCE_ID\"}]}" \
  | "$PY" "$ASSERT" fetch

echo
echo "==> 5. 回传抽取结果（含故意构造的非法条目，验证 7 项校验）"
curl -s --noproxy '*' -X POST "$BASE/api/policies/extraction-submissions" \
  -H 'Content-Type: application/json' -d '{
  "cityId": "changsha",
  "agentRunId": "e2e-run-001",
  "agentVersion": "policy-ai-crawler@0.1.0",
  "submissions": [{
    "sourceId": "'"$SOURCE_ID"'",
    "facts": [
      {"fieldId":"P1","value":66,"unit":"元/小时","confidence":0.95,"quote":"单小时服务单价调整为 66 元"},
      {"fieldId":"P2","value":0.8,"unit":"%","confidence":0.93,"quote":"基金支付比例为 80%"},
      {"fieldId":"P8","value":2,"unit":"小时","confidence":0.9,"quote":"单次服务时长 2 小时"},
      {"fieldId":"P9","value":3,"confidence":0.88,"quote":"每月必选服务项数 3 项"},
      {"fieldId":"P10","value":"是","confidence":0.86,"quote":"辅具租赁纳入试点范围"},
      {"fieldId":"C2","value":"新一线","confidence":0.85,"quote":"长沙为新一线城市"},
      {"fieldId":"P1","value":999,"confidence":0.9},
      {"fieldId":"S1","value":3,"confidence":0.9,"quote":"试图写公式自动字段"},
      {"fieldId":"C6","value":12.5,"confidence":0.4,"quote":"试图估算失能率"},
      {"fieldId":"P2","value":80,"confidence":0.8,"quote":"基金支付比例为 80%（未换算成 0-1）"},
      {"fieldId":"C2","value":"超一线","confidence":0.7,"quote":"枚举外取值"}
    ],
    "notDisclosed": ["C7","C8"]
  }]
}' | "$PY" "$ASSERT" submission

echo
echo "==> 6. 校验写入城市公式页的灰色建议值"
curl -s --noproxy '*' "$BASE/api/cities/changsha/values" | "$PY" "$ASSERT" city-values

echo
echo "==> 7. 候选来源入池（含一条非法链接）"
CAND=$(curl -s --noproxy '*' -X POST "$BASE/api/policies/source-candidates" \
  -H 'Content-Type: application/json' -d '{
  "cityId":"changsha",
  "candidates":[
    {"url":"https://ylbzj.changsha.gov.cn/zwgk/zcfg/","name":"长沙市医保局政策法规","targetFields":["P1","P2","P8"],"relevance":0.91},
    {"url":"https://tjj.changsha.gov.cn/tjgb/","name":"长沙市统计局统计公报","targetFields":["C3","C4","C5"],"relevance":0.87},
    {"url":"javascript:alert(1)","name":"非法链接"}
  ]}')
echo "$CAND" | "$PY" "$ASSERT" candidates
CAND_ID=$(echo "$CAND" | "$PY" -c "import sys,json;print(json.load(sys.stdin)['created'][0]['id'])")

echo
echo "==> 7b. 人工确认：候选来源转为正式来源"
curl -s --noproxy '*' -X POST "$BASE/api/policies/source-candidates/$CAND_ID/promote" \
  | "$PY" -c "import sys,json;d=json.load(sys.stdin);print(f\"   {d['status']} → 正式来源 {d['promotedSourceId']}\")"

echo
echo "==> 8. 复查来源列表（新转正的来源已纳入后续抓取）"
curl -s --noproxy '*' "$BASE/api/policies/sources?cityId=changsha" | "$PY" "$ASSERT" sources

echo
echo "==> 9. 回传审计记录"
curl -s --noproxy '*' "$BASE/api/policies/extraction-submissions?cityId=changsha" | "$PY" "$ASSERT" submissions

echo
echo "端到端流程完成。"
