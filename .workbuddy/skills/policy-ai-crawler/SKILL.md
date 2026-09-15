---
name: policy-ai-crawler
description: "养老业务政策资料 AI 抓取与字段抽取。WorkBuddy 承担联网检索、网页理解、20 个自动爬虫字段的抽取，通过 HTTP 接口把结果回传给 UE Agent API 落库。收到「政策抓取」「政策爬取」「更新城市参数」「更新某城市政策」「跑一次 AI 抓取」「长护险政策抽取」等请求时触发。"
metadata: {"workbuddy":{"emoji":"🏛️","agent_created":true,"requires":{"commands":["curl","python3"]}}}
---

# 政策资料 AI 抓取与字段抽取（WorkBuddy 执行手册）

## 定时任务模式：全城市同步

当触发词是“全城市政策同步”“运行 UE-Agent 政策定时任务”或来自
`.workbuddy/automations/policy-ai-sync.template.json` 的定时任务时，执行全局编排，
不要要求业务人员逐城复制提示词：

1. 用 `BASE_URL`（默认 `http://127.0.0.1:8000`）调用 `/api/health`，不可达就停止并报告，
   不得伪造完成；
2. 调用 `GET /api/projects` 获取项目城市，按 `cityId` 或城市名去重；
3. 对没有启用政策来源的城市，先按 `policy-city-onboarding` Skill 找到并验证城市级、
   必要的省级官方入口，再继续本 Skill；
4. 对每个城市创建或复用一个 `trigger=workbuddy`、`scope=all` 的 research run，读取它的
   brief，使用当前年份查询词主动检索新一期具体政策页、统计公报和政府文件；
5. 严格按本 Skill 的 Step 2 到 Step 5 回传候选来源、原文抓取和字段建议。SQLite 是单机
   交付模式，默认逐城完成并回传，避免多个城市同时写入产生不可读的中间状态；
6. 只有实际进入 `researching`、`fetching` 或 `extracting` 后，才允许调用 `complete`。
   对仍是 `queued` 的任务不能直接关闭为 `completed`；
7. 最终汇总必须分别报告：正式来源、候选来源、`unchanged` 跳过数、灰色建议值、
   `notDisclosed` 字段、错误，以及需要业务采用的内容。不要覆盖人工采用或人工覆盖的参数，
   也不要把“回传成功”写成“参数已生效”。

该模式由一个全局定时任务覆盖所有城市；新增城市后无需新建 WorkBuddy 任务。接手方只需
在自己的 WorkBuddy 账号中根据仓库内的自动化模板创建一次任务，详见
`.workbuddy/automations/README.md`。

## 这个 skill 在做什么

UE Agent 的城市参数里有 **20 个字段**来源标为「自动爬虫」，需要定期从各地政府网站抓取并抽成结构化数值。本 skill 让 WorkBuddy 承担其中的 **AI 部分**（检索、读网页、抽字段），**抓取落盘留在 API**（防 SSRF、原文存档、SHA256 变更检测）。

一句话职责划分：

> **WorkBuddy 决定读什么、理解内容；API 负责下载、存档、校验、落库。**

设计依据：`docs/superpowers/specs/2026-09-15-policy-realtime-workbuddy-design.md`；固定来源兼容规则见 `docs/superpowers/specs/2026-09-10-policy-ai-crawl-design.md`。

> **新城市第一次怎么配来源？** 那是另一个 skill 的职责：
> **`policy-city-onboarding`**（同目录 `../policy-city-onboarding/SKILL.md`）——
> 按城市名检索定位权威来源、批量入库并验证。本 skill 假定来源已经配好，只管「跑一轮抓取 + 抽字段」。

---

## 前置条件（每次运行先确认）

| 项 | 说明 |
| --- | --- |
| `BASE_URL` | API 地址。本地默认 `http://127.0.0.1:8000`；也可由交接方配置为可访问的 API 地址 |
| `TOKEN` | 环境变量 `UE_AGENT_AGENT_TOKEN`。**未配置时 API 放行（仅本地开发）**；配置后回传类接口必须带 |
| 鉴权头 | `x-ue-agent-token: $TOKEN`，或 `Authorization: Bearer $TOKEN` |

> **别把线上演示站当正式库。** 公网演示地址是
> `https://7957916747044094b3414209e003bafc.app.workbuddy.link`，里面只有演示数据。
> 实测沙箱复用会让数据跨发布保留，但**这不可靠**（沙箱回收即丢），不能当系统的正式存储。
> 它可以用来快速验证接口是否通（只读），但**正式抓取必须回写本地/正式的 API**。

连通性自检（返回 `cities` 即为通）：

```bash
curl -s "$BASE_URL/api/policies/crawl-targets" | head -c 300
```

> 若返回 401 `UNAUTHORIZED`，说明 API 配了 token 而你没带；检查 `UE_AGENT_AGENT_TOKEN`。

> **本机 curl 必加 `--noproxy '*'`**：这台机器环境变量里有 `HTTP_PROXY`，不加会被系统代理劫持，
> 连 `127.0.0.1` 都会返回空（`HTTP=000`）。这是本地联调最常踩的坑。

> **跨域限制**：API 默认只放行 `http://localhost:3000` 与 `http://127.0.0.1:3000`
> （见 `UE_AGENT_ALLOWED_ORIGINS`）。从浏览器页面调回传接口时，
> 若前端跑在其他端口，响应会被 CORS 拦掉（服务端只回 `access-control-allow-credentials`
> 而不回 `access-control-allow-origin`）。用 curl 直连不受影响。

### 本地 API 没在跑怎么办

`crawl-targets` 返回 `HTTP=000` 时，先确认是没启动（而不是被代理劫持）。
需要在项目根目录自己拉起来 —— **用 venv 的 python，不要用 `uv`**（避免依赖解析）：

```bash
PYTHONPATH=services/api services/api/.venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --log-level warning
```

后台方式启动后轮询最多 60 秒等 `/api/health` 返回 200（实测约 2 秒就绪）。
**不要设 `UE_AGENT_DATA_DIR`** —— 让它用默认的正式本地库
`services/api/data/ue-agent.sqlite3`（同目录那个 0 字节的 `ue_agent.sqlite3` 是历史残留，别用）。
跑完若服务是本轮自己拉起的，关掉它；若本来就在跑，保持原样。

---

## 默认入口：按需实时 research run

收到“更新长沙政策”“找一下某城市最新长护险政策”等请求时，先创建或复用一个城市 research run，再按 brief 执行。这里的“实时”是**本次运行时使用联网检索和当前年份查询词**，不是定时器保证 24 小时监听。

```bash
RUN_JSON=$(curl -s --noproxy '*' -X POST "$BASE_URL/api/policies/research-runs" \
  -H 'content-type: application/json' -H "x-ue-agent-token: $TOKEN" \
  -d '{"cityId":"长沙","trigger":"workbuddy","scope":"all"}')
RUN_ID=$(printf '%s' "$RUN_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -s --noproxy '*' "$BASE_URL/api/policies/research-runs/$RUN_ID/brief"
```

如果任务是由政策页按钮创建的，初始状态为 `queued`，只表示**等待 WorkBuddy 执行**，不能在页面或汇总中写成“已完成”。页面会展示同一个 `taskPrompt`；没有桥接器时，把该提示复制到 WorkBuddy 对话里继续执行即可。WorkBuddy 对话触发时直接创建 `trigger=workbuddy` 的任务。

按 brief 执行下面的统一顺序：

1. 读取 `GET /api/policies/research-runs/{runId}/brief`，必须使用 brief 里的当前年份查询词；不要只使用固定来源 URL。
2. 联网检索政策、统计公报、政府数据发布页和 PDF，优先具体文章/文件页，记录候选来源；来源通过 `POST /api/policies/source-candidates` 回传并带 `researchRunId`，非官方页面只入候选池。
3. 将需要阅读的链接通过 `POST /api/policies/fetch-requests` 回传并带 `researchRunId`，由 API 下载、保存原文、计算 SHA256。只处理 `first_fetch` 或 `new_version`，`unchanged` 跳过抽取。
4. 阅读 API 返回的原文文本，只抽取 brief 中的自动爬虫字段；每条 fact 必须带 `artifactId`、逐字 `quote`、单位、置信度和有效日期。
5. 通过 `POST /api/policies/extraction-submissions` 回传并带 `researchRunId`，或使用 `POST /api/policies/research-runs/{runId}/results` 一次回传候选来源和抽取结果。
6. 全部处理完调用 `POST /api/policies/research-runs/{runId}/complete`，请求体
   `{"status":"completed|partial_failed|failed","agentRunId":"...","agentVersion":"...","errors":[]}`
   （**没有 `summary` 字段**，传了会被 422 拒绝；运行摘要写在对话里，不进接口）；
   不要把未执行的 queued 任务直接关闭为 completed。

最小回传示例：

```bash
curl -s --noproxy '*' -X POST "$BASE_URL/api/policies/extraction-submissions" \
  -H 'content-type: application/json' -H "x-ue-agent-token: $TOKEN" \
  -d '{"cityId":"长沙","researchRunId":"research-xxx","agentRunId":"wb-xxx","agentVersion":"policy-ai-crawler@2","submissions":[{"sourceId":"source-xxx","artifactId":"artifact-xxx","facts":[{"fieldId":"P1","value":45,"unit":"元/小时","confidence":0.92,"quote":"逐字摘录的原文片段"}],"notDisclosed":["C6","C7","C8"]}]}'
```

上面示例中的 `sourceId`、`artifactId` 和 quote 需要替换成 API 实际返回的值；如果没有任何新原文，仍需按实际结果调用 complete，并在汇总中说明 `unchanged` 或未披露原因。

## 执行流程（固定来源兼容六步）

### Step 1 · 拉取派活清单

```bash
curl -s "$BASE_URL/api/policies/crawl-targets" -o /tmp/targets.json
```

返回关键字段：

| 字段 | 用途 |
| --- | --- |
| `fieldCatalog[]` | 20 个字段的定义：`id` / `name` / `unit` / `valueType` / `options` / `difficulty` / `neverEstimate` |
| `fieldFamilies[]` | 3 个字段族 + 检索关键词模板（`queryTemplate` 里 `{城市}` 需替换） |
| `difficultyLevels` | A/B/C/D 四档的含义 |
| `neverEstimateFields` | `["C6","C7","C8"]`，**这三个字段禁止估算** |
| `cities[].sources[]` | 每个城市已配置的来源，含 `fieldsToFill` / `alreadyFilled` / `lastChangeStatus` / `lastArtifactId` |

**增量感知**：`fieldsToFill` 只列出尚未 `accepted`/`overridden` 的字段。若某城市 `fieldsToFill` 为空，说明已填满，该城市可直接跳过抽取（但来源有变更时仍应抓取）。`alreadyFilled` 用于避免重复抽取。

### Step 2 · 声明要抓的 URL，由 API 抓取

```bash
curl -s -X POST "$BASE_URL/api/policies/fetch-requests" \
  -H 'content-type: application/json' \
  -H "x-ue-agent-token: $TOKEN" \
  -d '{"requests":[{"url":"https://ybj.xx.gov.cn/xxx.html","cityId":"XX市","sourceId":"src-xxx"}]}'
```

约束：单批最多 50 条；`maxChars` 默认 40000（1000–200000）。

返回 `results[]`，每条含 `artifactId` / `sha256` / `changeStatus` / `text` / `textTruncated` / `httpStatus`：

| `changeStatus` | 处理方式 |
| --- | --- |
| `first_fetch` | 送 AI 抽取 |
| `new_version` | 送 AI 抽取（内容变了） |
| `unchanged` | **跳过抽取** —— 内容 SHA256 与上次一致，抽了也是同一批值，白花 AI 成本 |
| `status: failed` / `skipped` | 记录进汇总，不抽取（`skipped` 多为来源已停用） |

**这一步就是成本闸门**：先把 `changeStatus` 过滤掉，再决定把哪些 `text` 送进推理。

### HTTP 抓取失败时：浏览器通道兜底（所有城市统一适用）

`fetch-requests` 仍然是第一入口。若某条结果是 `status: failed` 且
`fallbackAction: "browser_search"`，说明 API 的纯 HTTP 通道遇到了 JS 挑战型 WAF、
HTTP 拦截、超时或网络/TLS 限制。**不要反复请求同一个 URL，也不要用搜索摘要代替原文。**

此时按下面顺序处理：

1. 用 WorkBuddy 浏览器打开原 `url`；若页面被拦截，使用 brief 中的城市名、当前年份和字段族
   搜索官方站点，优先同一政府部门的栏目页、具体文章或 PDF 镜像。必须确认页面属于官方域名，
   记录浏览器最终看到的 URL 和页面标题。
2. 将页面中可复核的正文原样回传到 API（正文可以是浏览器读取后的纯文本，不要加入模型解释）：

```bash
curl -s --noproxy '*' -X POST "$BASE_URL/api/policies/browser-artifacts" \
  -H 'content-type: application/json' -H "x-ue-agent-token: $TOKEN" \
  -d '{
    "cityId":"XX市",
    "sourceId":"source-xxx",
    "researchRunId":"research-xxx",
    "requestedUrl":"https://原来源链接",
    "finalUrl":"https://浏览器实际打开的官方链接",
    "title":"页面标题",
    "content":"浏览器读取到的官方正文",
    "contentType":"text/plain; charset=utf-8",
    "fetchMode":"workbuddy_browser"
  }'
```

3. 只有收到返回的 `artifact.artifactId` 后，才按正常 Step 3 抽取；抽取提交中的
   `artifactId` 必须使用这个浏览器归档 ID，`quote` 必须逐字来自回传正文。相同正文重复提交
   会返回 `idempotent: true`，继续复用原 artifact，不产生重复文件。
4. 若浏览器也无法访问或找不到官方正文，保留 `fallbackAction` 失败状态，在
   `complete.errors` 说明来源和原因，并把无法公开的字段放入 `notDisclosed`；禁止编造、估算、
   拼接搜索摘要或把第三方转载当官方证据。

浏览器回传与 HTTP 抓取使用同一套原文、SHA256、版本和建议值审计链路；因此它适用于旧城市、
新增城市、自动入场和全城市定时任务，不需要为某个城市另写代码或另建任务。

### Step 3 · AI 抽取（本 skill 的核心智力活）

只对 `first_fetch` / `new_version` 的 `text` 抽取。产出格式（每条 fact 的字段名必须**一字不差**）：

```json
{
  "fieldId": "P1",
  "value": 45.0,
  "unit": "元/小时",
  "confidence": 0.92,
  "quote": "居家上门服务单小时价格不得超过 45 元",
  "effectiveDate": "2025-01-01"
}
```

抽取硬规则（违反会被 API 逐条拒绝）：

1. **`quote` 必填** —— 必须是从 `text` 里**逐字摘出**的原文片段（≤500 字），不得改写、不得翻译、不得拼接。这是防幻觉的唯一闸门。
2. **D 档字段（`neverEstimate: true`：C6/C7/C8）禁止出值** —— 官方从不按年龄段公布失能率。抽不到就放进 `notDisclosed`，**绝不允许估算或从其他城市类推**。
3. **枚举字段必须落在 `options` 内** —— C2 ∈ {一线, 新一线, 二线, 三线}，P10/P11 ∈ {是, 否}。政策原文不会自称「新一线」，需按城市名录归一化。
4. **单位与数值要换算到参数字典的口径**，不是照抄原文：
   - `P2 基金支付比例` 字典单位写着 `%`，但**存储口径是 0–1 的小数**。原文「基金支付 80%」→ `value: 0.8`，**不是 80**。（历史上这里出过事故：未换算的 `P2=80` 覆盖了正确的 `0.8`。）
   - `C3/C10` 单位是「万人」，原文若给「1234.5 万人」就填 `1234.5`；若给「12,345,678 人」需换算成 `1234.5678`。
   - `C11 医保基金净结余` 单位「亿元」，**允许为负**（结余为负是常见情况）。
5. **`valueType` 要对**：number 字段给数字（不要给字符串），string 字段给字符串。
6. **`confidence` ∈ [0,1]**，给真实把握度，不要一律 0.99。

字段分档参考（`crawl-targets` 的 `difficultyLevels` 是权威来源，这里是速览）：

| 档 | 字段 | 预期 |
| --- | --- | --- |
| A | P1 P2 P4 P5 P6 P7 P8 P9 P10 P11 | 政策文本直读，准确率最高 |
| B | C2 | 政策有表述但需归一化到枚举 |
| C | C3 C4 C5 C10 C11 C13 | 统计公报数据，**通常不在医保局政策页**，需换源（统计局/人社局） |
| D | C6 C7 C8 | 官方无公开数据，**必须返回 null，禁止估算** |

**C 档要换源检索**：`fieldFamilies` 给了每个族的关键词模板。政策准入族配医保局，城市人口族配 `site:gov.cn` 的统计年鉴/统计公报，空间面积族配政府门户。若手上来源只有医保局政策页，C 档字段大概率抽不到 —— 这是正常的，应通过 Step 5 去发现统计口的新来源。

### Step 4 · 回传抽取结果

```bash
curl -s -X POST "$BASE_URL/api/policies/extraction-submissions" \
  -H 'content-type: application/json' \
  -H "x-ue-agent-token: $TOKEN" \
  -d '{
    "cityId": "XX市",
    "agentRunId": "run-20260913-0800",
    "agentVersion": "policy-ai-crawler@1",
    "submissions": [
      {
        "sourceId": "src-xxx",
        "artifactId": "artifact-xxx",
        "facts": [ {"fieldId":"P1","value":45,"unit":"元/小时","confidence":0.92,"quote":"…原文…"} ],
        "notDisclosed": ["C6","C7","C8"]
      }
    ]
  }'
```

返回 `accepted` / `rejected` / `warnings` / `conflicts` / `notDisclosed` 与 `submissionId`。

响应语义（**必须读，这是自检依据**）：

| 字段 | 含义与处理 |
| --- | --- |
| `accepted[]` | 已写入灰色建议值。**不会自动生效**，需人工在城市公式页逐条「采用」 |
| `rejected[]` | 被拒条目 + `reason`。常见原因：quote 为空、字段不在字典、枚举越界、D 档被估。**不要重试同一条**，除非原因指向上游数据问题 |
| `warnings[]` | 数值超合理区间但仍接收（如 `P2=80` 会落在 `[0,1]` 外被标警告）。**见到警告要人工核对**，多半是单位没换算 |
| `conflicts[]` | 同批次同字段重复回传，服务端按「在区间内 > 置信度高 > 引用长」择优保留。若你的抽取产生了重复，说明抽取逻辑要收敛 |
| `notDisclosed[]` | 已登记的未披露字段。**这是合规信号，不是失败** |

### Step 5 · 发现新来源（**每轮必做**）

> 这一步**不是可选项**。已配置来源是「固定 URL」，而统计公报、年鉴、年度政策每年都换
> 新链接 —— 固定 URL 会逐轮返回 `unchanged`，看起来一切正常，实际永远停在旧版本
> （**静默过期**，比 404 危险）。发现新一期只能靠主动检索。

用 `fieldFamilies` 的 `queryTemplate`（把 `{城市}` 换成实际城市名，**并把当前年份带上**）
联网检索，把找到的**权威**页面作为候选来源入池：

- 年度类字段（人口/统计）：「长沙 **2026** 统计公报 常住人口」这类检索词才能命中新一期；
- 只查「长沙 养老政策」这种不带年份的词，搜到的往往是旧的。

```bash
curl -s -X POST "$BASE_URL/api/policies/source-candidates" \
  -H 'content-type: application/json' \
  -H "x-ue-agent-token: $TOKEN" \
  -d '{
    "cityId": "XX市",
    "candidates": [
      {"url":"https://tjj.xx.gov.cn/tongji/nj2025.html","name":"XX市2025统计年鉴",
       "title":"XX市统计年鉴2025","targetFields":["C3","C4","C5","C13"],"relevance":0.9}
    ]
  }'
```

规则：

- 只接受 `http://` / `https://` 链接（`javascript:` 等会被 `skipped`）。
- 入池后的 `status` 是 **`"candidate"`**（不是 `"pending"`）。查询待确认用 `?status=candidate`；
  人工处理后变为 `promoted`（已转正）或 `rejected`（已驳回）。
- 候选**不直接转为正式来源**，需人工确认。这是刻意的：联网检索会带出非权威站点，直接入池会污染来源列表并让后续定时任务持续抓垃圾。
- 同城同 URL 会去重。
- 优先政府域名（`*.gov.cn`）、官方统计公报、医保局政策原文页。**不要**提交聚合站、论坛、自媒体。

#### 选来源的关键标准：具体内容页 ≫ 部门首页

**优先指向「具体文章页」（某年统计公报、某份政策原文、某个数据发布页），而不是部门首页。**

原因：政务门户首页带滚动新闻和动态时间戳，**每次抓 SHA 都变** → `changeStatus` 永远是
`new_version` → 每轮都把整页正文送进 AI，是笔持续白花的成本；而具体公报/政策原文页内容固定，
**`unchanged` 能正常命中**，直接跳过抽取。

实测同一批来源：具体文章页（统计公报第四号、国土空间规划公示、长沙概况、长护险征求意见稿、
定点管理细则）全部命中 `unchanged`；而部门首页（国家医保局、湖南省统计局、湖南省人民政府、
长沙市人民政府）多为 `new_version`。

所以发现新来源时，别停在栏目首页 —— 顺着栏目进去抓**具体的那个链接**。
同理，若某来源长期每轮都 `new_version` 却抽不出值，多半是首页噪音，应替换为具体页。

#### 年度文档 vs 栏目页：配置时就要分开对待

| 类型 | 特征 | 配置建议 |
| --- | --- | --- |
| **栏目 / 索引页** | 每年新增条目，URL 不含年份（如「统计公报」列表、「数据发布」栏目） | **常驻监控**。它会随年份变化，是发现新一期的入口 |
| **年度文档** | 名称/URL 带年份（如「2025年统计公报」、`/202604/t20260420_…`） | 有效期约一年，**跨年要换新 URL** |
| **长期文件** | 办法/细则/意见，修订时才变 | 长期保留即可 |

**加来源时优先加栏目页**，年度文档只配当前最新那一期。

#### 检查有没有来源已过期

```bash
curl -s "$BASE_URL/api/policies/cities/{城市}/source-freshness"
```

返回每个来源的 `daysSinceChange`（自上次实质内容变更以来的天数）与 `level`：

- `stale` —— 名称/URL 带年份 **且** 超过阈值（默认 365 天）无变更 → **疑似过期，去找新年度版本**
- `aging` —— 无年份但超过阈值（默认 180 天）无变更 → 建议确认是否仍有效
- `ok` / `unknown` —— 正常 / 还没抓过

阈值可用环境变量 `UE_AGENT_STALE_DAYS` / `UE_AGENT_AGING_DAYS` 调整。
**页面上也会显示**（「官网来源」卡片里的体检行 + 来源行上的「疑似过期」徽标）。
发现 `stale` 的就回到本步用带年份的检索词去找新一期。



人工确认后由页面（或下面这条接口）转正式来源：

```bash
curl -s -X POST "$BASE_URL/api/policies/source-candidates/{candidateId}/promote"
curl -s -X POST "$BASE_URL/api/policies/source-candidates/{candidateId}/reject" \
  -H 'content-type: application/json' -d '{"reason":"非官方来源"}'
```

### Step 6 · 输出汇总

给用户一段**人话摘要**（不要贴 JSON），包含：

- 本次运行覆盖哪些城市、读了几个来源；
- 因 `unchanged` 跳过几个（省下的抽取量）；
- 新增/更新了多少个字段建议值（按城市列字段名 + 值 + 置信度）；
- 被拒绝多少条、主要原因；
- 数值警告几条（提示需人工核对）；
- 新发现候选来源几个（提示待确认）；
- 明确提示：**建议值需人工在城市公式页逐条「采用」后才生效**。

---

## 参考：20 个自动爬虫字段速查

字段完整定义以 `crawl-targets` 返回的 `fieldCatalog` 为准，下表仅供人工核对时速查。

| ID | 名称 | 单位 | 类型 | 枚举 | 档 |
| --- | --- | --- | --- | --- | --- |
| C2 | 城市行政等级 | - | string | 一线/新一线/二线/三线 | B |
| C3 | 常住总人口 | 万人 | number | - | C |
| C4 | 60岁以上人口占比 | % | number | - | C |
| C5 | 80岁以上人口占比 | % | number | - | C |
| C6 | 失能率_60-69岁 | % | number | - | **D** |
| C7 | 失能率_70-79岁 | % | number | - | **D** |
| C8 | 失能率_80岁以上 | % | number | - | **D** |
| C10 | 职工医保参保人数 | 万人 | number | - | C |
| C11 | 医保基金净结余 | 亿元 | number | - | C |
| C13 | 区域总面积 | km² | number | - | C |
| P1 | 单小时服务单价 | 元/小时 | number | - | A |
| P2 | 基金支付比例 | %(存 0-1) | number | - | A |
| P4 | 最低护理员纳保数 | 人 | number | - | A |
| P5 | 最低护士配置数 | 人 | number | - | A |
| P6 | 失能状态持续时长要求 | 月 | number | - | A |
| P7 | 评估通过率门槛 | % | number | - | A |
| P8 | 单次服务时长 | 小时 | number | - | A |
| P9 | 每月必选服务项数 | 项 | number | - | A |
| P10 | 辅具政策是否试点 | - | string | 是/否 | A |
| P11 | 亲情照护模式 | - | string | 是/否 | A |

数值合理区间（超出会被标 `warning` 但仍接收，需人工核对）：

| 字段 | 区间 | 字段 | 区间 |
| --- | --- | --- | --- |
| C3 | 1 – 5000 | P1 | 1 – 1000 |
| C4 / C5 | 0 – 100 | P2 | **0 – 1** |
| C6 / C7 / C8 | 0 – 100 | P4 / P5 | 0 – 10000 |
| C10 | 1 – 5000 | P6 | 0 – 120 |
| C11 | -1000 – 10000 | P7 | 0 – 100 |
| C13 | 10 – 200000 | P8 | 0.1 – 24 |
| | | P9 | 0 – 100 |

---

## 红线（不可越界）

1. **不自己下载网页。** 所有抓取走 `fetch-requests`，由 API 落盘存档。绕过它会让原文存档断裂、变更检测失效、SSRF 防护形同虚设。
2. **不给 C6/C7/C8 编数。** 官方无公开数据，唯一正确处理是 `notDisclosed`。
3. **不写「内部填写」「公式自动」字段。** 只有 `sourceType === "自动爬虫"` 的字段才可回传；其余会被整条拒绝。
4. **不带 quote 不出值。** 空引用的抽取值一律不采信 —— 这条没有例外。
5. **不把 AI 发现的来源当正式来源用。** 先入候选池，人工确认后再 promote。
6. **建议值不等于生效值。** 回传成功后仍是灰色建议值，需人工采用；不要在汇总里说成「已更新参数」。
7. **不提交聚合站/自媒体来源。** 只提交政府、统计、官方机构页面。

---

## 常见失败与处置

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| 401 UNAUTHORIZED | 没带 token 或 token 不符 | 检查 `UE_AGENT_AGENT_TOKEN`，加 `x-ue-agent-token` 头 |
| 大批 `rejected`，理由「缺少原文引用」 | 抽取时没保留原文片段 | 强制每条 fact 携带逐字 quote，无 quote 就不回传 |
| `warnings` 里出现 `P2` 超区间 | 百分数没换算成 0–1 | 按上文规则 4 换算 |
| C 档字段一条都抽不到 | 来源只有医保局政策页 | 正常现象；走 Step 5 发现统计局/人社局来源 |
| `conflicts` 有大段记录 | 同批次同字段重复回传 | 收敛抽取逻辑，同字段只保留一条最优 |
| `fetch-requests` 返回 `skipped: 来源已停用` | DataSource `status=paused` | 提示用户先在页面启用该来源 |
| `changeStatus` 全是 `unchanged` | 页面确实没更新 | 正常；本次无需抽取，汇总里说明即可 |
| 抓取报「**无法连接目标官网，请检查链接是否可公开访问**」 | 大概率不是网络问题，而是**国密证书导致 SSL 握手被拒**（见下） | 把该来源 URL 从 `https://` 换成 `http://` 后重抓 |
| 抓取报「**官网返回 HTTP 412，未保存内容**」 | **JS 挑战型 WAF**（实测 `*.chengdu.gov.cn` 全域，http/https、换 UA、加 Referer 都无效；返回的是要求计算 cookie 的混淆脚本） | 纯 HTTP 通道**无解**。不要反复重试；登记该域名为「需浏览器通道」，在 complete 的 `errors` 里如实说明，相关字段 notDisclosed 待通道升级后补抓 |
| 抓取报「**响应大小 N 字节超过上限**」 | 原文超过 10MB 上限（政务 PDF 常见，内嵌大量图片可达 30MB+）。注意：**HTML 页被 WAF 拦时，同站的 PDF 附件直链（`/gkml/uploadfiles/...pdf`）往往能通到下载阶段** | PDF 超限无解（不能裁剪——SHA 档案必须完整）。在 errors 里说明；统计公报关键数据常另有 HTML 版或转载版可寻 |

### 政务站抓不了的真正原因：国密证书（重要）

`https://` 的国内政务站常用**国密 SM2 证书**，Python 的 OpenSSL 3.x 拒绝解析，
报错是 `[SSL: BAD_ECPOINT] bad ecpoint`。而 `httpx` 把它归到 `ConnectError`，
于是抓取器只显示成「无法连接目标官网」—— **极具误导性，别去查网络**。

判别方法（用抓取器同款参数复现真实异常，不要只看那句中文报错）：

```bash
PYTHONPATH=services/api services/api/.venv/bin/python -c "
import httpx; from app.crawlers import USER_AGENT
try:
    httpx.get('<URL>', trust_env=False, timeout=15,
              headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
    print('OK')
except Exception as e:
    print(type(e).__name__, e)
"
```

- 打印 `ConnectError('[SSL: BAD_ECPOINT] bad ecpoint')` → **国密证书，换 `http://`**。
- 另一种常见变体：`[SSL: CERTIFICATE_VERIFY_FAILED] ... Hostname mismatch` ——
  **证书没绑定该域名**（政务站常拿主域证书套子域）。处置相同：**换 `http://`**。
- 注意 `curl` 用的是系统 TLS 栈，**它能通不代表抓取器能通**，别用 curl 的结果判断。

实测：`https://ybj.hunan.gov.cn/...` ✗ → `http://ybj.hunan.gov.cn/...` ✓（HTTP 不跳 HTTPS）。
`https://www.gov.cn/` 用的是普通证书，✓ 可用。


---

## 相关文件

| 路径 | 内容 |
| --- | --- |
| `docs/superpowers/specs/2026-09-10-policy-ai-crawl-design.md` | 完整设计（第 8 节为 WorkBuddy 驱动定稿） |
| `services/api/app/domain/policy/agent_service.py` | 派活 / 校验 / 候选来源的确定性逻辑 |
| `services/api/app/api/routes.py` | 四个回传接口的路由与鉴权 |
| `scripts/e2e-agent-flow.sh` | 端到端联调脚本（可参照其请求格式） |
