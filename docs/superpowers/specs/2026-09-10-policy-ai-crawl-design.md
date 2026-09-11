# 政策资料 AI 抓取与自动更新设计

日期：2026-09-10
状态：设计确认（已定稿，已改为 WorkBuddy 驱动架构）

> **架构修订（2026-09-10 下午）**：原方案把 AI 能力（LiteLLM Gateway 调用）与
> asyncio 调度器内置在 FastAPI 中，需要额外维护模型 API Key。经讨论改为
> **WorkBuddy 驱动架构**：AI 检索、网页理解、字段抽取全部由 WorkBuddy 执行，
> 通过 HTTP 接口把结果回传给 API 落库。API 保持纯确定性。
>
> 第 3 节之后的「5.1 AI 能力通道」「5.3 AI 检索层」「5.4 AI 结构化抽取层」
> 「5.6 定时任务」「5.7 前端改动」已被第 8 节取代，保留原文仅供追溯决策过程。

## 1. 需求

用户在「政策资料」页面希望实现：

1. **结合 AI 检索能力**搜索到最新的政策数据。
2. 把检索结果**按参数字典要求的字段整理填写回来**。
3. 城市页面的**公式计算页可以更新自动爬虫字段**。
4. **每 3 天一次定时任务**，爬取一次最新数据。

## 2. 现状盘点

`apps/web/app/(workspace)/policies/[cityId]/page.tsx` + `PolicyService` 已有链路：

| 能力 | 现状 | 位置 |
| --- | --- | --- |
| 数据源 CRUD（名称 + 官网链接） | 已有 | `POST/PUT /api/policies/sources` |
| 原文抓取 + SSRF 防护 | 已有 | `services/api/app/crawlers/__init__.py` |
| SHA256 变更检测（first_fetch/unchanged/new_version） | 已有 | `PolicyService.crawl_source_now` |
| 抓取历史 + 原文回看 | 已有 | `/api/policies/artifacts/{id}/content` |
| 候选事实审核（candidate → approved/rejected） | 已有 | `PolicyService.review_fact` |
| 写回城市参数 → 灰色建议值 | 已有 | `save_field_suggestion` |
| 城市公式页「采用建议值」按钮 | 已有 | `field-value-control.tsx` |

**缺口**：

1. AI 理解政策文本 —— 现仅 `SUGGESTION_PATTERNS` **3 条正则**（P1/P2/P8），覆盖 20 个自动爬虫字段中的 3 个。
2. AI 检索发现新政策来源 —— 完全没有。
3. 每 3 天定时任务 —— 没有，只有手动「立即抓取」。

## 3. 20 个自动爬虫字段的抽取难度分档

| 档位 | 字段 | 说明 |
| --- | --- | --- |
| A · 政策文本直读 | P1 单小时服务单价、P2 基金支付比例、P4 最低护理员纳保数、P5 最低护士配置数、P6 失能状态持续时长、P7 评估通过率门槛、P8 单次服务时长、P9 每月必选服务项数、P10 辅具试点(是/否)、P11 亲情照护(是/否) | LLM 抽取准确率最高 |
| B · 需归一化 | C2 城市行政等级（一线/新一线/二线/三线，有 `options` 枚举） | 政策文件不会自称「新一线」，需 AI 从城市名录判断 |
| C · 统计公报数据 | C3 常住总人口、C4 60岁以上占比、C5 80岁以上占比、C10 职工医保参保人数、C11 医保基金净结余、C13 区域总面积 | 不在医保局政策页，需抓统计局/人社局统计公报。**数据源须按字段族分类配置** |
| D · 无公开数据 | C6 失能率_60-69岁、C7 失能率_70-79岁、C8 失能率_80岁以上 | 官方从不按年龄段公布。**AI 必须返回 null，禁止估算** |

C 档决定了：一条来源配一个检索关键词是不够的，**每个 DataSource 需归属字段族**，由字段族决定检索词。

## 4. 端到端流程

```
阶段一 发现来源（AI 检索，每 3 天）
  AI 联网检索 → 候选来源列表 → 人工确认入池（转 DataSource）

阶段二 抓取 + AI 抽取
  原文抓取(SHA256 变更检测) → 正文清洗 → LLM 结构化抽取(20 字段 + 原文引用)

阶段三 审核 → 写回
  候选审核(逐条 采用/驳回) → 写回城市参数(灰色建议值) → 公式计算页采用后参与测算
```

## 5. 实现方案

### 5.1 AI 能力通道（已定）

复用本地 **LiteLLM Gateway** `http://127.0.0.1:15721/v1`（OpenAI Responses API 协议），选用带联网检索能力的模型。

- 环境变量：`UE_AGENT_LLM_BASE_URL`（默认 `http://127.0.0.1:15721/v1`）、`UE_AGENT_LLM_API_KEY`、`UE_AGENT_LLM_MODEL`。
- **不新增 Python 依赖**：用现有 `httpx` 直接发 OpenAI 兼容请求。
- Provider 抽象成接口，后续可替换为 Search API 通道而不改上层。

### 5.2 新增模块

| 文件 | 职责 |
| --- | --- |
| `services/api/app/llm/client.py` | LiteLLM Gateway 薄客户端（httpx，超时/重试/JSON 模式） |
| `services/api/app/llm/prompts.py` | 检索查询词模板 + 20 字段抽取 Prompt + JSON Schema |
| `services/api/app/crawlers/ai_search.py` | 按字段族生成查询词 → 返回 `SearchHit[]`（标题/URL/日期/摘要） |
| `services/api/app/domain/policy/extractor.py` | 正文清洗 + LLM 结构化抽取 → `PolicyCandidate[]` |
| `services/api/app/domain/policy/scheduler.py` | asyncio 后台循环，每 72h 触发全量刷新 |

### 5.3 AI 检索层

检索按**字段族**生成查询词，而非泛泛的「{城市}养老政策」：

| 字段族 | 查询词模板 |
| --- | --- |
| 政策准入（P 族） | `{城市} 长期护理保险 实施办法 待遇标准` |
| 城市人口（C3-C5） | `{城市} 统计年鉴 常住人口 老龄化率 site:gov.cn` |
| 医保基金（C10-C11） | `{城市} 医疗保障事业发展统计公报` |
| 空间（C13） | `{城市} 行政区域面积 官方` |

**候选来源不自动入池**：落成 `CandidateSource`（新表），页面展示「AI 发现的候选来源」列表，人工点「加入监控」才转成 `DataSource`。理由：AI 检索会返回大量非权威站点，直接入池会污染来源列表。

### 5.4 AI 结构化抽取层

替换 `parse_suggestions` 的三条正则，改为两段式：

```
extract_readable_text() → 正文清洗（去导航/页脚/相关链接）
        ↓
   LLM 结构化抽取（JSON Schema 约束）
        ↓
   PolicyCandidate[] { field_id, value, unit, confidence, quote, source_url }
```

**三条硬约束**（质量关键）：

1. **强制引用原文**：每个抽取值必须返回 `quote` 原文片段，页面展示，人工一眼判断是否瞎编。
2. **置信度分级**：`confidence < 0.7` 标记为「AI 低置信」，UI 单独成栏。
3. **禁止估算**：D 档字段（C6/C7/C8）Prompt 明确要求「公开信息未披露则返回 null」。

**输出分流**：
- 政策类字段（P 族）→ 写 `PolicyFact`（复用 `candidate → approved/rejected` 审核流）
- 城市类字段（C 族）→ 直接走 `save_field_suggestion`，在城市公式页显示灰色建议值

### 5.5 写回机制（沿用现有，微调）

现有链路不改：`save_field_suggestion` → 城市页灰色建议值 → 点「采用建议值」→ `accept_field_suggestion` 写入 `inputs` → 场景变 `stale` → 重算。

补两点：

1. `suggestedSource` 增加 `confidence` 与 `quote` 字段，让城市页显示「AI 置信度 92%」+ 原文引用。
2. **政策更新提醒**：已 `accepted` 的字段，新一轮抽到**不同值**时，应重新置为 `suggestion_ready` 并提示「政策可能已更新」，而不是静默覆盖当前值。

**写回策略（已定）**：全部进灰色建议值，人工逐条采用。不自动写入参数，符合《规范总则》「确认值不被静默覆盖」铁律。

### 5.6 定时任务（已定）

**FastAPI 内置 asyncio 调度器**（`lifespan` 启动），SQLite 表记录 `last_run_at`，重启不重复跑。

- 触发间隔：72 小时。环境变量 `UE_AGENT_REFRESH_INTERVAL_HOURS` 可覆盖。
- 接口：`POST /api/policies/refresh-all`（手动/外部触发）、`GET /api/scheduler/status`（下次时间 + 上次汇总）。
- 执行序列：

```
遍历 status=active 的 DataSource
  → crawl_source()（复用现有，含 SSRF 防护）
  → SHA256 比对：unchanged 则跳过（省钱，避免重复调 LLM）
  → new_version 才触发 AI 抽取
  → 候选值写入 PolicyFact / suggestion
  → 记录 RefreshRun 汇总（成功数/失败数/新增候选数）
```

**成本控制**：SHA256 无变化则**完全不调 LLM**。这是省钱核心。

### 5.7 前端改动

现有 `/policies/[cityId]` 页面新增三个区块，不重做：

1. **调度状态条**：「下次自动抓取：9月12日 08:00 · 上次：9月9日 08:00（3 个来源，2 个更新，新增 7 个候选值）」+「立即全量刷新」按钮。
2. **AI 发现的候选来源**：卡片列表，含标题/域名/发布日期/AI 摘要/相关字段标签 +「加入监控」按钮。
3. **字段抽取结果表**：20 行表格 —— 字段 / 当前值 / AI 建议值 / **原文引用** / 置信度 / 状态 / 操作。「AI 低置信」与「未披露」分开展示。

`packages/model-spec` 不涉及公式或参数语义变更，无需架构决策。

## 6. 待办清单（实现顺序）

1. `llm/client.py` + `llm/prompts.py`（LLM 通道与 20 字段 Schema）
2. `domain/policy/extractor.py`（正文清洗 + 结构化抽取）+ 单测
3. `PolicyService.crawl_source_now` 接入 extractor，替换 `parse_suggestions`
4. `suggestedSource` 增加 `confidence`/`quote`；SQLite 迁移
5. `crawlers/ai_search.py` + `CandidateSource` 表与接口
6. `domain/policy/scheduler.py` + `/refresh-all` + `/scheduler/status`
7. 前端三个区块 + 测试
8. 全量校验：后端 pytest、前端 vitest、`tsc --noEmit`、端到端一次真实抓取

## 7. 风险

| 风险 | 缓解 |
| --- | --- |
| AI 检索返回非权威站点 | 候选来源人工确认后才入池；优先 `site:gov.cn` |
| LLM 抽取幻觉 | 强制 `quote` 原文引用 + 置信度分级 + 人工逐条采用 |
| LLM 调用成本 | SHA256 未变不调用；仅对 new_version 抽取 |
| 沙箱发布环境无 cron | 调度器内置在 FastAPI lifespan，不依赖外部设施 |
| 政策更新被静默忽略 | 已采用字段抽到不同值时置回 `suggestion_ready` 并提示 |

---

## 8. 架构修订：WorkBuddy 驱动（定稿）

### 8.1 为什么改

原方案把 AI 能力内置在 FastAPI，需要：
- 额外维护 LiteLLM Gateway 的 API Key；
- 写一个 asyncio 后台调度器；
- 在服务端实现检索与抽取逻辑。

而 WorkBuddy 本身具备**联网检索**与**模型推理**能力，且已有 automation 定时能力。
重复在服务端建设这两件事没有必要。

### 8.2 职责边界（定稿）

| 环节 | 负责方 | 说明 |
| --- | --- | --- |
| 决定读哪些网站 | WorkBuddy | 检索 + 读已配置来源 |
| **网页抓取（下载原文）** | **API** | 见 8.3，必须留在 API |
| 原文存档 + SHA256 变更检测 | API | 现有 `crawlers/__init__.py` 能力 |
| 理解政策、抽 20 字段 | WorkBuddy | 模型强项 |
| 定时触发 | WorkBuddy automation | 无需服务端调度器 |
| 校验、落库、写建议值 | API | 确定性逻辑 |

**修正说明**：先说「API 侧一行调度代码都不用写」是不准确的。
准确说法是：**定时调度不用写代码，但「派活接口」与「回传接口」必须写。**
API 从不做事前调度，但必须提供数据、接收结果。

### 8.3 为什么抓取必须留在 API

如果把网页抓取也搬到 WorkBuddy，会丢掉三样已在运行的能力：

1. **原文存档断裂** —— 现每次抓取把原始字节存到 `raw_sources/{sha256}.bin`，页面「查看原文」依赖它。
   若 WorkBuddy 自己下载，则人工审核候选值时**无法回溯 AI 当时基于什么内容抽的值**（政策页可能已改版或 404）。
2. **SHA256 变更检测失效** —— 这是成本控制核心（内容未变则不调 AI）。抓取在外部则 API 无从判断「哪些字段需要重抽」。
3. **SSRF 防护与抓取审计丢失** —— `crawlers/__init__.py` 含内网地址拒绝、超时上限、大小上限、重定向次数限制。

因此：**「决定抓什么」与「理解内容」交给 WorkBuddy，「落盘存档」与「变更检测」留在 API。**

### 8.4 端到端流程（定稿）

```
WorkBuddy：检索 → 决定读哪些 URL
       ↓ POST /api/policies/fetch-requests（声明要抓的 URL）
API：crawl_source() 抓取 → 存原文 → SHA256 比对
       ↓ 返回 [{url, artifactId, text, sha256, changeStatus}]
WorkBuddy：读 text → AI 抽 20 字段
       ↓ POST /api/policies/extraction-submissions
API：7 项校验 → 写灰色建议值
```

API 抓取响应里的 `changeStatus: "unchanged"` 会直接告诉 WorkBuddy「这篇没变，别抽了」，**AI 成本省在源头**。

### 8.5 四个接口

| 接口 | 用途 |
| --- | --- |
| `GET /api/policies/crawl-targets` | 派活：返回城市、已配置来源、`lastChangeStatus`、`fieldsToFill`（增量感知）、`fieldCatalog`（含 difficulty 分档） |
| `POST /api/policies/fetch-requests` | WorkBuddy 提交一批 URL，API 抓取落档并返回正文文本 |
| `POST /api/policies/extraction-submissions` | WorkBuddy 回传抽取结果，含 7 项校验 |
| `POST /api/policies/source-candidates` | AI 检索发现的候选来源入池，人工确认后转正式 `DataSource` |

**读取范围（已定）**：已配置来源 + AI 发现新来源。AI 发现的来源先落候选表，不直接入池
（联网检索会返回非权威站点，直接入池会污染来源列表并让后续定时任务持续抓垃圾）。

**鉴权（已定）**：回传类接口用静态 token 校验（环境变量 `UE_AGENT_AGENT_TOKEN`），防止公网发布后接口裸奔。

### 8.6 回传校验（7 项，防幻觉核心）

| 校验项 | 不通过时行为 |
| --- | --- |
| `fieldId` 存在于参数字典 | 整条拒绝 |
| 字段 `sourceType === "自动爬虫"` | 拒绝（禁止 AI 写「内部填写」/「公式自动」字段） |
| `valueType` 匹配（number / string） | 拒绝该条 |
| 有 `options` 的字段值须在枚举内 | 拒绝（C2/P10/P11） |
| `confidence` ∈ [0, 1] | 拒绝 |
| **`quote` 非空** | **拒绝**（空引用的抽取值一律不采信） |
| 数值合理区间（如 P2 ∈ [0,1]、C4 ∈ [0,100]） | 标警告但仍接收 |

### 8.7 定时任务（已定）

交给 **WorkBuddy automation**，每 3 天 08:00 唤起一次，执行本 skill：

```
调 GET /crawl-targets 拿待办
  → POST /fetch-requests 让 API 抓取（拿回 artifactId + text + changeStatus）
  → unchanged 的跳过；new_version / first_fetch 的送 AI 抽取
  → 检索新政策来源（可选）
  → POST /extraction-submissions 回传
  → POST /source-candidates 回传新来源
  → 输出汇总摘要
```

**API 侧不写调度代码**。这样也解决了发布沙箱无持久 cron 的问题。

### 8.8 修订后的实现顺序

1. SQLite 迁移 004：`candidate_sources` 表 + `extraction_submissions` 审计表
2. `POST /policies/fetch-requests`（复用 `crawl_source`，返回正文）
3. `GET /policies/crawl-targets`（派活清单，含 difficulty 分档与增量 `fieldsToFill`）
4. `POST /policies/extraction-submissions`（7 项校验 + 写建议值 + token 鉴权）
5. `POST/GET /policies/source-candidates` + `promote` 转正式来源
6. `suggested_source_json` 扩展 `confidence` / `quote` 字段
7. 编写 `policy-ai-crawler` skill（WorkBuddy 执行手册）
8. 创建每 3 天 automation
9. 端到端跑通一次真实抓取，核对抽取质量
10. 前端三个区块（调度状态条 / 候选来源 / 抽取结果表）
