# 新增城市自动发现与测算同步设计

## 1. 目标

新增城市时，用户只填写城市名称和项目基本信息，系统自动创建一条“城市入场任务”，完成以下闭环：

1. 根据城市名生成政策准入、城市人口、空间面积三类检索任务。
2. 通过可替换的 AI/搜索发现适配器找到公开数据源与政策页面。
3. 高可信官方来源自动进入该城市的正式政策来源并抓取；非官方来源只进入待确认候选。
4. 抓取原文写入本地 `raw_sources/`，保存 SHA256、HTTP 状态、历史和引用。
5. 从抓取内容解析自动爬虫字段，写入城市测算场景的灰色建议值。
6. 建议值只提示，不自动改变当前输入；用户点击“采用建议值”后才参与计算。

系统不为城市名称增加代码分支，新增城市全部使用相同的字段族、来源发现、抓取和解析流程。

## 2. 范围与约束

- Demo 保持公开访问，不增加登录、权限或审批系统。
- 默认数据库仍为本地 SQLite，任务状态也落 SQLite，重启后可恢复查看。
- 不自动估算 C6、C7、C8；无公开数据时记录 `notDisclosed`。
- 不覆盖人工填写、人工覆盖或已采用的字段值。
- 不把普通搜索结果直接当成正式来源；来源需要满足可信度规则。
- 不改变现有 75 字段、Excel 单元格映射和公式计算契约。
- 不包含 Vercel、Cloudflare 或其他生产环境部署。

## 3. 用户流程

### 3.1 新增城市

用户在 `/projects/new` 提交城市名称后，后端同步创建项目、基准场景和入场任务，响应中返回：

```json
{
  "project": {"id": "project-...", "cityId": "chengdu", "city": "成都"},
  "onboarding": {"id": "onboarding-...", "status": "queued"}
}
```

前端跳转城市测算页，展示任务卡片并轮询状态。任务失败不影响用户手动编辑和运行测算。

### 3.2 发现与抓取

系统为每个城市生成三组查询：

- 政策准入：`{城市} 长期护理保险 实施办法 待遇标准 site:gov.cn`
- 城市人口：`{城市} 统计公报 常住人口 老龄化率 site:gov.cn`
- 空间面积：`{城市} 行政区域面积 官方 site:gov.cn`

发现结果按 URL 去重并评分：政府、医保、统计、民政等官方域名优先；具体政策文章页优先于部门首页；搜索结果缺少有效 HTTP/HTTPS 地址时丢弃。

高可信来源自动创建为 `DataSource` 并抓取，普通来源写入 `CandidateSource`。已有同城市同 URL 时不重复创建，只复用并继续抓取。

### 3.3 参数同步

抓取完成后，确定性解析器和可选 AI 抽取器共同产生字段候选。候选必须包含字段编号、值、原文引用和来源产物。服务端按现有校验规则写入每个城市场景的 `suggestion_ready` 状态。

测算页字段显示：

- 当前值：已有人工/已采用值。
- 灰色提示：待采用建议值。
- 来源：原文标题、引用和抓取时间。
- 操作：采用建议值；不采用则保持当前值。

## 4. 架构

### 4.1 入场编排服务

新增 `CityOnboardingService`，只负责流程编排，不负责具体搜索或字段解析：

```python
start(project_id: str) -> dict[str, Any]
run(onboarding_id: str) -> dict[str, Any]
run_for_project(project_id: str) -> dict[str, Any]
get_status(onboarding_id: str) -> dict[str, Any]
retry(onboarding_id: str) -> dict[str, Any]
```

服务依次调用：

```text
DiscoveryProvider.discover(city, field_families)
  -> SourceDiscoveryResult[]
SourcePolicy.classify(result)
  -> official / candidate / rejected
PolicyService.crawl_source_now(source_id)
  -> CrawlArtifact
PolicyService.parse_suggestions(text)
  -> suggestion_ready field values
```

### 4.2 发现适配器

定义稳定接口 `SourceDiscoveryProvider`，本次提供两个实现：

1. `WebSearchDiscoveryProvider`：默认本地 Demo 实现，通过配置的搜索 URL 模板获取结果，适合没有 AI Key 的环境。
2. `WorkBuddyDiscoveryProvider`：保留现有 WorkBuddy 回传入口，供联网 AI 任务把候选 URL 回传至同一套入场任务。

如果配置了 OpenAI 兼容的 AI 发现端点，后续可新增 `OpenAICompatibleDiscoveryProvider`，不改入场编排和前端。当前实现不把密钥写入 SQLite、前端或日志。

### 4.3 任务执行

本地 Demo 使用 FastAPI `BackgroundTasks` 启动任务，并把每个阶段及时写入 SQLite。HTTP 请求不等待搜索、抓取或 AI 推理完成。页面通过状态接口轮询；重复启动同一任务返回原任务，不并行重复跑。

任务阶段：

`queued` → `discovering` → `sources_ready` → `crawling` → `extracting` → `completed`

任一阶段部分失败时状态为 `partial_failed`，保存每条错误，仍继续处理其他来源。完全无法启动时状态为 `failed`，可点击重试。

## 5. 数据模型

新增 SQLite 迁移 `005_city_onboarding.sql`：

```sql
CREATE TABLE city_onboarding_jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  city_id TEXT NOT NULL,
  city_name TEXT NOT NULL,
  status TEXT NOT NULL,
  phase TEXT NOT NULL,
  total_queries INTEGER NOT NULL DEFAULT 0,
  discovered_count INTEGER NOT NULL DEFAULT 0,
  official_source_count INTEGER NOT NULL DEFAULT 0,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  crawled_count INTEGER NOT NULL DEFAULT 0,
  suggestion_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT NOT NULL DEFAULT '[]',
  started_at TEXT,
  finished_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_city_onboarding_project_active
  ON city_onboarding_jobs(project_id)
  WHERE status IN ('queued','discovering','sources_ready','crawling','extracting');
```

仓储层提供 `create_onboarding_job`、`get_onboarding_job`、`update_onboarding_job`、`list_onboarding_jobs`，JSON 和 SQLite 仓储保持相同接口，确保测试和本地迁移一致。

## 6. API

- `POST /api/projects`：创建项目后自动创建入场任务；响应保留已有项目字段，并新增 `project` 和 `onboarding` 两个嵌套对象，兼容现有客户端。
- `GET /api/projects/{project_id}/onboarding`：返回最新任务状态和统计。
- `POST /api/projects/{project_id}/onboarding/retry`：对失败或部分失败任务重新执行，复用已存在来源并去重。
- `POST /api/policies/source-candidates`：继续接收 WorkBuddy 候选来源；若带有有效 `onboardingId`，关联任务统计。
- 现有 `crawl-all`、`fetch-requests`、`extraction-submissions`、导出接口保持兼容。

## 7. 错误与安全

- 搜索服务不可用：任务变为 `partial_failed`，页面提示“可稍后重试或手动配置来源”，不阻塞城市测算。
- 来源 URL 不合法、重定向到内网、超时或超过大小限制：只记录该条错误，沿用现有 SSRF 防护和抓取限制。
- AI 返回字段无 quote、写入公式字段、写入内部填写字段、枚举不合法或 C6/C7/C8：拒绝该条并保留审计原因。
- 同城市重复创建：URL 唯一去重；同一城市只能有一个运行中的入场任务。
- 任务异常不返回堆栈给前端，前端只显示可读错误和任务 ID。

## 8. 验收标准

1. 输入“成都”创建项目后，项目响应包含入场任务 ID，城市页能看到任务状态。
2. 任务使用城市名生成三组查询，不包含任何 `if city == ...` 城市分支。
3. 至少一个高可信官方来源可自动进入正式来源并触发抓取；低可信来源进入候选区。
4. 抓取原文、指纹、历史和来源关联可从政策页查看。
5. 自动爬虫字段出现灰色建议值，当前输入值不被静默修改。
6. 用户采用建议值后，该值参与测算并在总仪表盘同步。
7. 重试不会重复创建同 URL 来源，也不会并行执行同一城市任务。
8. API、前端组件、迁移和端到端测试覆盖成功、部分失败、空搜索结果、重复来源和禁止估算场景。
