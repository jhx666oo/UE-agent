# UE-Agent 交付与 AI 复现手册 v1.0

> 文档版本：v1.0
> 快照日期：2026-09-15
> 对应代码提交：`85be483 feat(policy): add browser fallback task queue`
> GitHub：<https://github.com/jhx666oo/UE-agent>
> 目标：让接手人员或 AI 在不依赖原开发者口头说明的情况下，完成本地启动、理解业务、继续开发和打包移交。

## 0. 一页摘要

UE-Agent 不是传统后台管理系统，而是一个“长护险城市成本测算网站” Demo：用户选择或新增城市，在城市项目中配置测算参数，系统使用确定性公式生成 24 个月经营预测，再把每个城市最近一次已测算结果汇总到总览仪表盘。政策资料页负责从公开官网或 WorkBuddy 实时检索中保存政策原文，并生成可追溯的灰色建议值；建议值必须由业务人员逐条采用后才进入测算参数。

当前产品采用以下边界：

- 所有人可直接访问和查看，Demo 暂不提供登录、权限和组织管理。
- 本地 SQLite 是默认数据源，政策原文和抓取文件保存在本机目录，不依赖云数据库。
- Excel 只作为只读对照物；运行时使用 `packages/model-spec/` 中的参数和公式契约。
- 核心财务结果必须由 Python 确定性计算引擎生成，AI 只能负责检索、来源发现和建议值提交。
- 政策页面当前不提供手动上传政策 Word/Excel/PDF 的产品入口，主流程是公开官网来源抓取与 WorkBuddy 检索。
- 固定官网遇到 JS/WAF、网络/TLS、超时或大响应时，系统将其放入 WorkBuddy 浏览器兜底任务队列，不重复请求同一来源。
- 本文档是 Demo 的交付说明，不代表已经完成生产级部署、安全审计或无人值守的云端自动化。

当前本地 SQLite 快照统计（仅代表当前工作区数据，不是代码契约）：

| 对象 | 数量 |
|---|---:|
| 城市项目 | 3 |
| 测算场景 | 10 |
| 政策来源 | 50 |
| 抓取产物 | 201 |
| WorkBuddy 兜底任务 | 4 |
| 实时政策研究任务 | 2 |

现有示例城市包括成都、岳阳、长沙。接手时不要把这些城市写成代码分支；新城市必须通过通用项目创建、自动发现来源和同一套模型契约接入。

## 1. 业务模型和产品结构

### 1.1 核心对象关系

```text
城市项目 Project
  └── 基准/自定义场景 Scenario
        ├── 控制台参数 ScenarioFieldValue
        │     ├── 内部填写：人工录入或留空
        │     ├── 自动爬虫：灰色建议值，采用后才写入当前值
        │     └── 公式自动：计算引擎生成，只读
        └── 测算结果 CalculationSnapshot
              ├── 24 个月投影
              ├── 阶段汇总
              ├── 核心指标
              └── 待业务确认问题

城市项目 Project
  └── 政策来源 DataSource
        └── 抓取产物 CrawlArtifact / 原文文件
              └── 结构化政策事实与灰色建议值

所有项目的最近一次有效快照
  └── 总览仪表盘 / 单城市视图 / 城市对比
```

### 1.2 四个主页面

1. **总览**：展示所有城市的核心经营指标、城市数量、结果新鲜度、趋势图、城市横向对比和政策同步状态；支持全局和单城市筛选。
2. **城市测算**：城市项目列表、新增城市、城市参数、场景保存、执行测算、结果快照和结果回到总览映射。
3. **政策资料**：城市总览、单城市政策来源、官网抓取、抓取历史、原文查看、AI 实时研究、灰色建议值和 CSV/ZIP 导出。
4. **城市对比**：按同一口径比较多个城市的收入、成本、回本、利润率、数据完整度和政策状态。

旧入口 `/u1`、`/projects/{projectId}/u1` 保留兼容跳转；不应继续增加新的独立 U1 导航模块。

## 2. 当前技术架构

### 2.1 技术栈

| 层 | 技术 | 责任 |
|---|---|---|
| 前端 | Next.js 16、React 19、TypeScript、Tailwind CSS v4 | 页面、表单、仪表盘、交互状态 |
| 图表 | Recharts | 折线图、指标对比、城市比较 |
| API | FastAPI、Pydantic | HTTP 接口、校验、任务状态和导出 |
| 计算域 | Python | U1 公式、阶段、24 个月投影和核心指标 |
| 持久化 | SQLite | 项目、场景、参数、快照、政策、任务 |
| 抓取 | Python `httpx` + 可读文本提取 | 官网正文、大小限制、指纹和原文落盘 |
| AI 协作 | WorkBuddy 项目级 Skill + 定时任务模板 | 实时搜索、浏览器兜底、建议值回传 |
| 测试 | Python unittest、Vitest、TypeScript、ESLint | 后端、前端、类型、静态和交付校验 |

### 2.2 代码目录

```text
UE-agent/
├── apps/web/                         # Next.js 前端
│   ├── app/(workspace)/              # 总览、城市、政策、设置页面
│   ├── components/                  # 页面组件和可复用 UI
│   └── lib/                         # API 类型与前端请求封装
├── packages/model-spec/              # U1 唯一模型契约
│   ├── parameters/u1.parameters.json # 75 个控制台字段
│   ├── formulas/u1.formulas.json     # 公式与结果依赖
│   ├── issues/u1.issues.json         # 已知问题/待业务确认
│   └── fixtures/u1-baseline.json     # 脱敏基准回归数据
├── services/api/
│   ├── app/domain/u1/                # 纯计算域
│   ├── app/domain/policy/            # 政策抓取、研究、解析、入场
│   ├── app/domain/dashboard/         # 总览聚合
│   ├── app/api/                      # FastAPI 路由和 Schema
│   ├── app/repository.py             # JSON/协议兼容仓储
│   ├── app/sqlite_repository.py      # SQLite 正式仓储
│   ├── migrations/sqlite/            # 001-010 SQLite 迁移
│   └── tests/                        # 后端全量测试
├── .workbuddy/
│   ├── skills/policy-ai-crawler/     # 政策检索、抽取、兜底 Skill
│   ├── skills/policy-city-onboarding/# 新城市来源发现 Skill
│   └── automations/                  # 全城市同步任务模板
├── scripts/                          # setup、开发、备份、交付和 E2E
└── docs/                             # PRD、规范、模型台账、部署和计划
```

### 2.3 数据位置

```text
services/api/data/
├── ue-agent.sqlite3       # SQLite 结构化数据
├── policy_files/          # 政策文件实体（如有）
└── raw_sources/           # 官网/浏览器回传原文
```

`services/api/data/`、`services/api/backups/`、`.env.local`、依赖和构建产物不入 Git。交付数据必须通过 `pnpm data:backup` 或 `pnpm handoff:package` 生成一致性备份。

## 3. 当前已完成能力

### 3.1 测算和总览

- 已完成公开 Demo 的总览仪表盘。
- 支持全局所有城市、单城市筛选和城市横向对比。
- 支持新增城市项目、基准场景、场景参数编辑、保存和执行测算。
- 支持 24 个月筹备期、启动期、平台期预测。
- 支持收入、变动成本、固定成本、净利润、累计净利润、累计现金流、回本月份和盈亏平衡客户数。
- 最近一次 `calculated` 或 `confirmed` 快照会映射到总览；参数改动后会标记结果过期（`stale`）。
- 结果快照不可变，便于追溯历史计算结果。

### 3.2 Excel 模型契约

- 已建立 75 个控制台字段的稳定 ID、名称、单位、Excel 单元格、输入类型、阶段、来源类型和状态。
- 字段来源分为：内部填写、自动爬虫、公式自动。
- 内部填写允许录入或留空；自动爬虫只产生灰色建议值；公式自动字段只读。
- `C6/C7/C8` 没有可靠公开数据时必须为 `notDisclosed`，不得由 AI 或经验值估算。
- `S3` 已按业务确认改为通勤扣减公式，`S5` 已修正末项引用；修正记录保留在公式台账和问题清单。
- `DIV0_IN_SUMMARY`、累计序列求和等疑似 Excel 口径问题仍按当前契约保留并标记。

### 3.3 政策资料和城市自动入场

- 支持新增城市后创建城市入场任务。
- 入场任务按政策准入、城市人口、空间面积等查询族发现来源。
- `.gov.cn` 等官方来源进入正式来源，普通结果进入待确认候选来源；不为具体城市增加代码分支。
- 支持启用/停用来源、单来源抓取、城市全部来源抓取、来源新鲜度、抓取历史和原文内容查看。
- 抓取原文保存到本地并计算指纹，未变化的内容会跳过重复解析。
- 已支持 C2/C3/C4/C5/C10/C11/C13、P1/P2/P4/P5/P6/P7/P8/P9/P10/P11 等明确字段的确定性解析。
- 建议值带来源、引用原文和抓取时间，必须人工点击“采用建议值”后才写入城市参数。
- 已提供 CSV/ZIP 导出，便于业务复核和后续处理。

### 3.4 AI 实时政策和失败兜底

- 页面可创建 `research-runs`，WorkBuddy 读取 brief 后用当前年份搜索最新官方政策、统计公报和 PDF。
- WorkBuddy 先处理 `/api/policies/fallback-tasks`，避免对同一失败 URL 反复发起 HTTP 请求。
- HTTP 抓取遇到 JS/WAF、网络/TLS、超时或响应体超过配置上限，会返回 `browser_search` 兜底动作，而不是保存不完整正文。
- WorkBuddy 可用浏览器读取可见正文，回传 `/api/policies/browser-artifacts`，系统自动归档匹配的兜底任务。
- 浏览器读取失败时可调用 `/fail` 回写错误；任务仍保留在队列中供下一轮处理。
- 页面显示 `queued` 只代表等待 WorkBuddy 执行，不会误报为已完成。

### 3.5 本地可移植交付

- 已完成 SQLite 初始化、迁移、JSON 首次导入、备份、恢复和完整性校验。
- 已完成 `pnpm setup`、`pnpm dev:all`、`pnpm handoff:check`、`pnpm handoff:package`。
- 交付包包含源码、SQLite 备份、政策原文、两个 WorkBuddy Skill、全城市定时任务模板和 `HANDOFF.md`。
- 不携带 `.env.local`、令牌、`.git`、依赖、构建缓存和 WorkBuddy 私有 memory。

## 4. 关键运行流程

### 4.1 新增城市到总览

```text
新增城市
  → 创建 Project + 基准 Scenario
  → 创建城市入场任务
  → 发现来源并按官方/候选分流
  → 抓取或进入 WorkBuddy 浏览器兜底
  → 保存原文与抓取版本
  → 确定性解析自动爬虫字段
  → 灰色建议值显示在城市测算页
  → 业务人员逐条采用建议值
  → 执行公式测算
  → 保存不可变结果快照
  → 总览和城市对比读取最近有效快照
```

### 4.2 政策实时更新

```text
用户点击“AI 实时更新政策”或 WorkBuddy 定时任务
  → 创建或复用 research run
  → 读取 brief（城市、字段族、当前年份、历史来源）
  → WorkBuddy 搜索官方文章/公报/PDF
  → 通过 fetch-requests 请求 API 下载和指纹校验
  → HTTP 被拦截或过大时读取 fallback-tasks
  → 浏览器回传 browser-artifacts
  → 保存来源、原文、引用和字段建议
  → 建议值保持灰色，不自动覆盖业务参数
  → 业务人员采用后重新测算
```

### 4.3 三种字段来源规则

| 来源类型 | 页面行为 | 是否参与计算 |
|---|---|---|
| 内部填写 | 用户直接输入，可留空；适用于业务假设、现场调研、市场判断 | 保存后参与计算，缺少必需字段则阻断并提示 |
| 自动爬虫 | 输入框显示灰色建议值、来源和引用；用户可采用或自行修改 | 只有点击采用后才进入当前场景参数 |
| 公式自动 | 公式标签、只读展示、运行测算后生成 | 由计算引擎自动参与，不在填写框中修改 |

禁止把空值当 0，禁止用人口、工资等语义不同字段强行填满模板，禁止用 AI 猜测 C6/C7/C8。

## 5. 接手方一键启动

### 5.1 从 GitHub 源码启动

```bash
git clone https://github.com/jhx666oo/UE-agent.git
cd UE-agent
pnpm setup
pnpm dev:all
```

打开：

- 前端：<http://localhost:3000>
- API：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>

如果前端找不到 API，复制 `apps/web/.env.example` 为 `apps/web/.env.local`，设置：

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 5.2 从交付压缩包启动

```bash
tar -xzf dist/ue-agent-handoff-*.tar.gz
cd ue-agent-handoff-*
bash scripts/setup-local.sh
bash scripts/dev-all.sh
```

`setup-local.sh` 会安装 Node/Python 依赖、创建虚拟环境、初始化 SQLite，并且只在目标数据目录为空时恢复包内演示数据。重复执行不会重复导入。

### 5.3 WorkBuddy 初始化

WorkBuddy 的账号级定时任务不能随 Git 或压缩包复制。接手方在同一工作区中让 WorkBuddy 读取：

```text
.workbuddy/automations/policy-ai-sync.template.json
```

并创建一次“UE-Agent 全城市政策同步”定时任务。模板要求每日 08:00（Asia/Shanghai）处理所有城市，新增城市走 `policy-city-onboarding`，政策实时检索和失败兜底走 `policy-ai-crawler`。如果 WorkBuddy 不在同一台电脑运行，必须把 `apiBaseUrl` 改成接手方可访问的地址，并配置 API 的 `UE_AGENT_AGENT_TOKEN`；不要把 token 写进 Skill 或模板。

## 6. 关键 API 目录

以下接口以当前代码为准，完整可交互文档在 `http://localhost:8000/docs`。

### 6.1 项目与测算

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/projects` | 获取城市项目列表 |
| POST | `/api/projects` | 创建城市项目并生成基准场景/入场任务 |
| GET | `/api/projects/{projectId}` | 获取项目详情 |
| GET | `/api/projects/{projectId}/scenarios` | 获取项目场景 |
| GET | `/api/scenarios/{scenarioId}/values` | 获取参数当前值与建议值 |
| PATCH | `/api/scenarios/{scenarioId}/values/{fieldId}` | 修改内部填写或采用建议值 |
| POST | `/api/scenarios/{scenarioId}/calculate` | 执行 U1 测算并保存快照 |
| GET | `/api/dashboard/overview` | 获取总览和城市对比聚合数据 |
| GET | `/api/projects/{projectId}/onboarding` | 查看新增城市入场状态 |
| POST | `/api/projects/{projectId}/onboarding/retry` | 重试失败/部分失败入场任务 |

### 6.2 政策来源和原文

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/policies/sources` | 获取政策来源 |
| POST | `/api/policies/sources` | 配置公开官网来源 |
| POST | `/api/policies/sources/{sourceId}/crawl` | 抓取单个来源 |
| POST | `/api/policies/cities/{cityId}/crawl-all` | 抓取城市全部启用来源 |
| GET | `/api/policies/cities/{cityId}/source-freshness` | 查看来源新鲜度 |
| GET | `/api/policies/artifacts/{artifactId}/content` | 查看已保存原文 |
| GET | `/api/policies/export` | 导出来源、抓取记录和建议值 |
| GET | `/api/policies/fallback-tasks` | 查看 WorkBuddy 浏览器兜底队列 |
| POST | `/api/policies/fallback-tasks/{taskId}/claim` | 领取兜底任务 |
| POST | `/api/policies/fallback-tasks/{taskId}/fail` | 回写兜底失败 |
| POST | `/api/policies/browser-artifacts` | 回传浏览器读取的原文 |

### 6.3 AI 实时研究

| 方法 | 路径 | 用途 |
|---|---|---|
| POST/GET | `/api/policies/research-runs` | 创建/查看实时政策研究任务 |
| GET | `/api/policies/research-runs/{runId}/brief` | 获取给 WorkBuddy 的检索 brief |
| POST | `/api/policies/research-runs/{runId}/retry` | 重试研究任务 |
| POST | `/api/policies/research-runs/{runId}/results` | 回传候选来源和字段建议 |
| POST | `/api/policies/research-runs/{runId}/complete` | 完成研究任务 |

AI 回传不能直接写入 `scenario_field_values`，必须经过来源、引用、单位、枚举、范围和禁止估算校验。

## 7. 本地备份、恢复和交付

### 7.1 备份当前数据

```bash
pnpm data:backup
```

备份包括 SQLite、`policy_files/`、`raw_sources/`、迁移源和 `MANIFEST.txt`。备份只读当前数据，不删除或覆盖运行数据。

### 7.2 恢复数据

```bash
pnpm data:restore --from services/api/backups/<时间戳目录>
```

恢复前停止 API 写入。恢复程序会先校验备份数据库，再把现有数据移入 `pre-restore-*` 目录；校验失败不会破坏当前数据。

### 7.3 生成移交包

```bash
pnpm handoff:check
pnpm handoff:package
```

交付包内容：源码、文档、模型契约、测试、SQLite 数据备份、政策原文、WorkBuddy Skill、定时任务模板和 `HANDOFF.md`。交付包明确排除密钥、依赖目录、构建缓存、`.git` 和私有 WorkBuddy memory。

## 8. 当前已知问题和未来待办

### P0：交付后优先确认

- [ ] 在接手方 WorkBuddy 账号中创建一次全城市政策同步定时任务；账号级记录无法随仓库复制。
- [ ] 处理当前本地队列中的 4 个 `queued` 兜底任务，确认成都历史来源是否需要浏览器补采。
- [ ] 将接手方的 API 地址、浏览器网络边界和 `UE_AGENT_AGENT_TOKEN` 配置方式写入其本地环境，不把令牌提交到仓库。
- [ ] 对现有城市逐个执行一次“参数修改 → 结果 stale → 重新测算 → 总览更新”的交付验收。

### P1：下一阶段产品和工程

- [ ] 做一个 WorkBuddy/API 的正式桥接器，让页面创建的 `queued` 研究任务可以自动被本地代理领取，而不是依赖人工复制提示词。
- [ ] 增加任务重试退避、最大尝试次数、死信状态、耗时、最后错误和可观测日志。
- [ ] 为大 PDF 增加分页/章节提取、OCR 兜底和页码级引用；当前系统只保证进入浏览器兜底队列，不保证所有扫描 PDF 自动抽取成功。
- [ ] 将默认百度发现服务替换为稳定的企业搜索或 AI 网关，并在 `UE_AGENT_DISCOVERY_SEARCH_URL` 中配置；不要把具体搜索引擎写死在业务逻辑里。
- [ ] 增加政策事实冲突处理：同一字段有多个官方来源时，展示版本、发布日期、优先级和人工选择记录。
- [ ] 增加城市级数据完整度、来源新鲜度和“建议值待采用”数量的仪表盘告警。
- [ ] 对 75 个字段补充更细的单位、范围、空值、真 0 和“不适用”校验提示。

### P2：业务模型深化

- [ ] 组织业务人员复核 `u1-known-issues.md` 中的累计序列、筹备期 `DIV0`、城市总量/站点覆盖边界等问题。
- [ ] 明确 B12 默认常量和来源；任何修改必须新增模型版本、同步 fixture、公式台账和回归测试。
- [ ] 明确政策中的失能率 C6/C7/C8 是否存在可公开、可审计的官方统计口径；在确认前继续保持 `notDisclosed`。
- [ ] 增加不同进入模式、自营/收购/联营等场景的对比视图，但不能破坏当前单城市基准场景。
- [ ] 增加导出报告或打印版结果，且报告必须带模型版本、参数来源、快照时间和待确认问题。

### P3：生产化（当前明确未完成）

- [ ] 登录、角色、项目权限和审计主体。
- [ ] 生产数据库、对象存储、队列、定时调度、监控、告警和日志留存。
- [ ] SSRF、限流、文件病毒扫描、访问审计、密钥管理、备份加密和灾备演练。
- [ ] 正式域名、HTTPS、部署流水线、回滚策略和生产验收。

生产化不是本 Demo 当前交付承诺。接手方不要因为本地 Demo 能运行，就把它直接暴露在公网。

## 9. 验收清单

### 9.1 自动验证

在仓库根目录执行：

```bash
pnpm model:test
pnpm api:test
pnpm test
pnpm typecheck
pnpm lint
pnpm build
pnpm handoff:check
bash scripts/e2e-agent-flow.sh
```

当前代码提交前已验证：后端 221 个测试通过，前端 59 个测试通过，类型检查、Lint、Next.js 构建、可移植交付检查和 E2E 全部通过。接手方修改代码后必须重新执行对应检查，不得仅凭页面能打开就判断完成。

### 9.2 手工验收

- [ ] 打开总览，确认可看到城市列表、指标卡、趋势和城市筛选。
- [ ] 新增一个测试城市，确认项目创建后出现城市入场状态，而不是要求开发者新增代码。
- [ ] 打开城市测算页，确认内部填写、自动爬虫、公式自动三类字段视觉和交互不同。
- [ ] 修改参数后确认结果被标记为 `stale`；重新测算后总览同步更新。
- [ ] 抓取一个测试官网，确认原文落盘、来源可追溯、建议值为灰色且不会自动覆盖。
- [ ] 对一个失败或超大来源确认它进入 `fallback-tasks`，批量统计将其计为浏览器待处理而非普通 HTTP 失败。
- [ ] 用 WorkBuddy Skill 领取任务并回传浏览器 artifact，确认任务自动归档。
- [ ] 导出政策资料，确认来源、抓取记录和建议值能被下载。
- [ ] 关闭并重启 API，确认 SQLite 数据仍存在。

## 10. 给接手 AI 的复现提示词

下面的内容可以直接复制给接手人员使用的 AI。使用时，把“本地路径”替换为实际仓库路径；不要把密钥、个人身份证号、手机号或私有政策文件粘贴给在线 AI。

```text
你现在接手一个名为 UE-Agent 的长护险城市成本测算网站，请把当前仓库视为已有项目，先理解并验证，再继续开发，不要从零重写。

项目仓库： https://github.com/jhx666oo/UE-agent
当前基线提交：85be483
产品目标：所有人可以访问的长护险城市成本测算 Demo。用户按城市创建项目，配置参数，执行确定性 U1 测算，查看 24 个月收入/成本/利润/现金流，并在总览页查看全部城市和城市对比。政策资料页通过公开官网抓取或 WorkBuddy 实时检索保存政策原文，生成带逐字引用的灰色建议值；业务人员采用后才进入测算。

一、先做环境和代码勘察
1. 在仓库根目录运行：
   pnpm setup
   pnpm handoff:check
   pnpm dev:all
2. 查看：
   README.md
   docs/deployment/UE-Agent-交付与AI复现手册-v1.0.md
   docs/deployment/local.md
   docs/deployment/portable-handoff.md
   docs/product/UE-Agent-产品需求文档-v1.0.md
   docs/model/u1-parameter-dictionary.md
   docs/model/u1-formula-ledger.md
   docs/model/u1-known-issues.md
   packages/model-spec/parameters/u1.parameters.json
   packages/model-spec/formulas/u1.formulas.json
   .workbuddy/skills/policy-ai-crawler/SKILL.md
   .workbuddy/skills/policy-city-onboarding/SKILL.md
3. 确认前端 http://localhost:3000、API http://localhost:8000、API 文档 http://localhost:8000/docs 可以访问。
4. 先读测试和现有实现，再决定改动位置。不要根据截图或猜测重新设计已经存在的字段与公式。

二、不可违反的产品和模型规则
1. 默认运行模式是 Next.js + FastAPI + SQLite；不要把 Vercel、Postgres 或云对象存储设为必需依赖。
2. 暂不增加登录、权限和生产部署，除非我明确提出。
3. 75 个参数和 Excel 单元格映射以 packages/model-spec 为唯一契约。
4. 核心财务和运营数字只能由 Python 确定性引擎计算，AI 不得直接计算或写入财务结果。
5. 三种字段来源必须保持区分：内部填写、自动爬虫、公式自动。
6. 自动爬虫只创建灰色建议值。建议值必须保留原文、逐字引用、来源 URL、抓取时间和可信度；只有用户点击采用后才写入场景当前值。
7. 公式自动字段只读，场景尚未测算时可以显示“待测算”，不能让用户在填写框中修改。
8. null、数字 0、notApplicable、notDisclosed 和 formula_error 必须区分。
9. C6/C7/C8 无可靠公开数据时只能登记 notDisclosed，不能由 AI、平均值或常识估算。
10. 现有 Excel 疑似问题必须原样保留并标记“待业务确认”，除非取得明确业务确认并同步模型版本、台账、fixture 和测试。
11. 政策固定链接被 JS/WAF、TLS、超时或超大响应拦截时，创建或复用 fallback task，交给 WorkBuddy 浏览器处理；任务未归档前不要反复请求同一 URL。
12. 不为成都、长沙、岳阳等已有城市写硬编码分支；新增城市必须复用通用流程。
13. 不提供政策文件手动上传入口作为当前主流程；优先使用公开来源、AI 发现和本地原文归档。

三、开发规范
1. 修改前先说明目标、影响文件、数据流和验收标准。
2. 新功能或修复先增加失败测试，再写实现；至少覆盖成功、空值、重复执行和失败兜底。
3. API 先改 Schema/仓储/服务，再改路由，再改前端类型和组件。
4. 所有新数据必须有 SQLite migration，同时考虑 JSON 兼容仓储和备份/恢复。
5. 所有外部抓取必须做 URL 协议校验、SSRF 防护、超时、最大响应体限制、SHA256 指纹和错误留痕。
6. WorkBuddy 只能通过公开 API 协议回传，不能绕过服务直接改 SQLite，也不能直接改场景当前参数。
7. 前端沿用现有 packages/ui、Tailwind tokens、按钮/卡片/Badge 组件和中文文案风格，不引入重复 UI 库，不用内联大段 CSS。
8. 页面需要表现加载、空状态、错误、部分成功、queued、in_progress、completed、failed、stale 等状态。
9. 变更要同步 README、API README、相关产品文档、Skill 或交付文档，避免文档与代码不一致。
10. 不要删除用户已有数据，不要 git reset --hard，不要覆盖 .env.local，不要提交任何 token。

四、完成前必须运行
pnpm model:test
pnpm api:test
pnpm test
pnpm typecheck
pnpm lint
pnpm build
pnpm handoff:check
bash scripts/e2e-agent-flow.sh

完成汇报必须包含：
- 改了哪些文件和为什么；
- API、数据库迁移、前端、Skill、文档是否同步；
- 测试命令和真实结果；
- 是否有未完成事项、待业务确认事项或生产风险；
- 如果要求提交/推送，先展示 git diff --check、git status 和提交摘要，再执行非破坏性的 commit/push。
```

## 11. 接手后的推荐开发顺序

1. 先按本手册启动并完成自动/手工验收，确认不是环境问题。
2. 处理 4 个现有浏览器兜底任务，观察 WorkBuddy 回传链路和原文归档。
3. 完成页面创建研究任务到 WorkBuddy 的本地自动桥接，消除手工复制提示词。
4. 再做政策来源冲突、PDF/OCR、任务观测和数据完整度告警。
5. 最后再进入登录、权限、生产存储和部署评估；生产化之前不得把当前 Demo 直接作为公网业务系统使用。

## 12. 交付联系和判断原则

遇到“字段缺失、公式异常、抓取失败、AI 给出一个看似合理的值”时，优先保留证据并标记状态，不要为了让页面有数字而静默填充。判断顺序固定为：原 Excel/模型契约 → 官方来源原文 → 引用和时间 → 业务确认 → 确定性公式 → 页面展示。任何不能审计的值都只能作为候选建议，不能直接成为经营决策结果。
