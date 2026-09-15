# 政策实时检索与 WorkBuddy 协作设计

## 1. 背景与目标

当前政策资料链路依赖固定 URL 的定时抓取。政府网站的年度统计公报、政策通知和具体文件链接经常变化，固定 URL 即使返回 HTTP 200，也可能长期停留在旧内容。因此本功能把“政策更新”从固定链接轮询改为“按需实时检索”：用户从前端或 WorkBuddy 发起任务，WorkBuddy 使用城市名、当前年份和字段主题搜索最新政策，UE-Agent API 负责抓取证据、校验、存档、生成建议值并同步到现有政策页和测算页。

本期目标：

1. 前端政策页支持“AI 实时更新”按钮。
2. WorkBuddy 对话支持“更新长沙政策”等自然语言入口。
3. 两个入口使用同一套 `policy research run` 任务协议，避免两套数据逻辑。
4. 检索必须优先寻找具体政策文章、统计公报和 PDF 文件，而不是只保存部门首页。
5. 所有字段建议都保留原文引用、来源、检索时间、有效时间和 AI 版本；建议值仍需人工采用，不得静默覆盖人工值。
6. C6、C7、C8 继续标记为未披露，禁止估算。

## 2. 非目标

- 不实现 24 小时持续监听或政策网站变更推送；“实时”定义为用户触发后的即时联网检索。
- 不让浏览器直接调用 WorkBuddy 模型，也不把 AI 密钥放进前端。
- 不改变确定性测算公式，不由大模型计算成本结果。
- 不在本期实现登录、角色权限、多租户和生产级消息队列。
- 不删除现有 `crawl-targets`、`fetch-requests`、`extraction-submissions`、`source-candidates` 接口；旧 WorkBuddy skill 仍可继续运行。

## 3. 方案选择

### 3.1 方案 A：前端直接调用 WorkBuddy

浏览器直接请求 WorkBuddy 的模型接口，拿到检索结果后提交 API。体验简单，但会暴露调用凭证，且依赖 WorkBuddy 是否允许跨域调用，不适合本地移交和后续公开 Demo。

### 3.2 方案 B：API 直接调用 WorkBuddy

后端统一调用 WorkBuddy 的 AI 接口。产品链路最短，但 API 与 WorkBuddy 的调用协议、运行环境和凭证强绑定；如果 WorkBuddy 只在对话环境提供联网检索，后端无法独立完成调用。

### 3.3 方案 C：任务编排 + WorkBuddy 拉取/回传（采用）

API 创建并维护任务，WorkBuddy 通过 brief 接口获取待办，使用自身检索能力寻找来源，再通过现有安全接口请求 API 抓取原文并回传字段结果。前端按钮和 WorkBuddy 对话都只创建同一种任务。

方案 C 的关键边界是：API 不假设能够主动唤醒 WorkBuddy。前端按钮创建任务后，如果当前 WorkBuddy 环境有本机 CLI/HTTP 调用能力，就由桥接器自动接手；如果没有，页面展示可复制的任务指令，WorkBuddy 对话仍可立即执行。任务协议不因触发方式变化。

## 4. 端到端流程

```text
前端按钮 / WorkBuddy 对话
          ↓
POST /api/policies/research-runs
          ↓
读取 brief：城市、字段、当前年份、历史来源、查询词
          ↓
WorkBuddy 联网检索并选择具体文章/PDF
          ↓
API fetch-requests 下载、反 SSRF 校验、保存原文与 SHA256
          ↓
WorkBuddy 阅读 artifact 文本并回传 facts
          ↓
API 逐条校验 quote、单位、枚举、置信度和禁估字段
          ↓
生成灰色建议值、记录变更事件、保留人工采用入口
          ↓
政策页显示新来源/变更；测算页和总览只读取正式采用值
```

## 5. 任务模型

新增 SQLite 表 `policy_research_runs`，一个城市同一时刻最多一个 active run。字段如下：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT | `research-...`，主键 |
| `city_id` | TEXT | 城市标识 |
| `project_id` | TEXT | 可选，前端从项目页发起时关联项目 |
| `trigger` | TEXT | `ui` 或 `workbuddy` |
| `scope_json` | TEXT | `all` 或指定字段族/字段列表 |
| `status` | TEXT | `queued/researching/fetching/extracting/awaiting_review/completed/partial_failed/failed` |
| `agent_run_id` | TEXT | WorkBuddy 侧幂等运行 ID |
| `agent_version` | TEXT | WorkBuddy skill 版本 |
| `query_count` | INTEGER | 生成的查询数量 |
| `source_count` | INTEGER | 发现的去重来源数量 |
| `new_source_count` | INTEGER | 新来源数量 |
| `changed_source_count` | INTEGER | 已知来源出现新内容的数量 |
| `fetched_count` | INTEGER | 成功归档的原文数量 |
| `suggestion_count` | INTEGER | 生成的建议值数量 |
| `error_count` | INTEGER | 错误数量 |
| `errors_json` | TEXT | 可读错误数组 |
| `task_prompt` | TEXT | 前端可复制给 WorkBuddy 的任务提示 |
| `requested_at` / `started_at` / `finished_at` | TEXT | UTC 时间 |
| `created_at` / `updated_at` | TEXT | UTC 时间 |

新增 `policy_research_queries` 保存每个查询族的真实检索词、结果数量和执行状态，便于解释“为什么找到这份政策”。现有 `crawl_artifacts`、`extraction_submissions`、`candidate_sources` 通过 `researchRunId`/`agentRunId` 关联本次任务，不重复建设原文和抽取存储；抓取失败也保留任务关联，便于定位失败来源。

## 6. API 协议

### 6.1 创建任务

`POST /api/policies/research-runs`

请求：

```json
{
  "cityId": "长沙",
  "projectId": "project-xxx",
  "trigger": "ui",
  "scope": "all",
  "fields": []
}
```

返回任务、状态、任务指令和 brief 地址。重复点击不创建第二个 active run，而是返回当前任务。

### 6.2 查询任务

- `GET /api/policies/research-runs?cityId={cityId}&limit={n}`：返回城市最近任务，供政策页恢复任务状态。
- `GET /api/policies/research-runs/{runId}`：返回进度、错误、发现来源和建议值计数。
- `GET /api/policies/research-runs/{runId}/brief`：返回 WorkBuddy 执行所需的城市、字段族、动态查询模板、历史来源、已采用字段和禁止估算字段。
- `POST /api/policies/research-runs/{runId}/retry`：仅允许 `failed` 或 `partial_failed` 重新进入 `queued`。

### 6.3 WorkBuddy 回传

`POST /api/policies/research-runs/{runId}/results` 接收本次检索发现的来源和字段结果，服务端将其路由到已有的候选来源、抓取和抽取校验服务。结果中每个字段必须包含：

```json
{
  "fieldId": "P2",
  "value": 0.8,
  "unit": "比例",
  "confidence": 0.92,
  "quote": "基金支付比例为80%",
  "effectiveDate": "2026-01-01",
  "sourceId": "source-xxx",
  "artifactId": "artifact-xxx"
}
```

`POST /api/policies/research-runs/{runId}/complete` 接收 WorkBuddy 的完成信号、版本和未披露字段，服务端只允许任务状态向终态转换一次。所有回传类接口继续支持 `UE_AGENT_AGENT_TOKEN`。

现有 `fetch-requests` 增加可选 `researchRunId`；现有 `source-candidates` 增加可选 `researchRunId`；现有 `extraction-submissions.agentRunId` 可使用本次任务的 `agentRunId`，并新增 `researchRunId` 以便 API 查询任务详情。

## 7. WorkBuddy 检索规则

WorkBuddy 每次都从 brief 生成带当前年份的查询，不使用固定 URL 作为唯一入口：

- 政策准入：`{城市} {年份} 长期护理保险 实施办法 待遇标准 site:gov.cn`
- 城市人口：`{城市} {年份} 统计公报 常住人口 老龄化率 site:gov.cn`
- 空间面积：`{城市} 行政区域面积 官方 site:gov.cn`

来源优先级：具体政策文章/PDF > 官方栏目中的具体公告 > 政府部门首页。每个来源需要返回 URL、标题、域名、发布/生效时间、命中的查询、目标字段和相关度。`*.gov.cn` 或已验证官方域名可以进入正式来源；其他结果先进入候选来源。

WorkBuddy 不自行下载原文，先将 URL 交给 `fetch-requests`。只有 `first_fetch` 和 `new_version` 的 artifact 才送入抽取；`unchanged` 跳过抽取。抽取必须逐字引用 artifact 原文，不得使用搜索摘要代替证据。

## 8. 数据一致性与安全规则

1. 同一城市 active run 唯一；同一 `agentRunId` 重试返回幂等结果，不重复写建议值。
2. AI 建议只能写 `suggestion_ready`，已有 `accepted` 或 `overridden` 的字段不覆盖。
3. P2 按 0–1 存储；C3/C10 按万人；C11 可为负；C6/C7/C8 只允许进入 `notDisclosed`。
4. `quote` 必须能在保存的 artifact 文本中定位；字段、单位、枚举和数值区间沿用现有 `AgentSubmissionService` 校验。
5. URL 仍经过 http/https、域名解析、私网地址和重定向校验；WorkBuddy 不能通过结果接口写任意数据库字段。
6. 新政策发现不会删除旧来源；旧来源进入历史，变更事件保留前后值和证据。
7. 搜索无结果、网页无法读取、PDF 解析失败或 AI 回传部分失败，都保留已完成证据并将任务标记为 `partial_failed`，不清空旧数据。

## 9. 前端交互

城市政策页增加“AI 实时更新”按钮和任务卡片：

- 未运行：显示上次检索时间、上次发现的新来源和待确认变更数。
- 运行中：显示当前阶段、查询数、来源数、成功抓取数和建议值数，每 2 秒轮询。
- 等待 WorkBuddy：显示任务编号和可复制指令；不假装已经完成。
- 完成/部分失败：显示新来源、变更字段、错误原因和“再次更新”按钮。
- 每个建议值继续提供查看原文、采用、忽略入口。

总览仪表盘显示“待确认政策变更”提示，但只使用 `accepted`/`overridden` 数据计算指标。政策总览页增加最近检索记录和城市级筛选；不新增登录页。

## 10. 失败处理

| 场景 | 处理 |
| --- | --- |
| WorkBuddy 未执行 | 任务保持 `queued`，前端展示复制指令 |
| 搜索服务无结果 | 任务 `partial_failed`，保留查询和错误，不改旧值 |
| 发现非官方来源 | 写入 `candidate_sources`，等待人工转正 |
| 官方来源内容变更 | 归档新 artifact，允许重新抽取并生成建议 |
| quote 不在原文 | 单条 rejected，其他字段继续处理 |
| AI 重复回传 | 按任务 ID 和字段幂等，不能重复堆叠建议 |
| 所有字段已有人工值 | 仍可检索和保存政策版本，但 brief 把字段列为已填，不生成覆盖建议 |

## 11. 验收标准

1. 前端点击长沙“AI 实时更新”后生成任务，状态卡片可见；重复点击复用同一 active run。
2. WorkBuddy 触发同一个城市时得到同样的 brief 和字段口径。
3. 使用当前年份检索模板，不依赖已有固定来源 URL；新 URL 能入候选/正式来源并保存检索证据。
4. API 保存原文 artifact、SHA256 和检索任务关联；内容未变时不重复抽取。
5. 有效 quote 的字段进入灰色建议值；非法单位、枚举、空 quote 和 C6/C7/C8 被拒绝。
6. 建议值不会覆盖人工输入；人工采用后才影响测算和总览。
7. 搜索失败、来源失败和 AI 部分失败都能展示并重试。
8. 前端测试、后端测试、lint、typecheck、build 和 E2E 全部通过。
