# UE Agent API domain

当前目录先承载不依赖 FastAPI 的 U1 纯计算域。它读取 `packages/model-spec` 中的版本化 JSON 规格，输出 24 个月投影、阶段汇总、关键指标和待业务确认问题。

当前已增加 FastAPI 适配层和本地 SQLite 项目、场景、政策来源及抓取记录存储。原有 `projects.json` 只用于首次 bootstrap 迁移或兼容测试。

完整交付包由仓库根目录的 `pnpm handoff:package` 生成，包含源码、SQLite 备份、政策原文、WorkBuddy
项目级 Skill 和全城市定时任务模板；账号级 WorkBuddy 定时任务不会写入仓库。

首次运行建议在仓库根目录执行 `pnpm bootstrap`，创建本地数据目录、SQLite 表结构，并在数据库为空时导入既有项目样例。

## 运行模型测试

在仓库根目录执行：

```bash
pnpm model:test
```

运行 API 契约测试：

```bash
pnpm api:test
```

启动本地 API：

```bash
pnpm api:dev
```

默认地址为 `http://localhost:8000`，接口文档为 `http://localhost:8000/docs`。本地数据默认写入 `services/api/data/ue-agent.sqlite`，政策原文写入同目录的 `raw_sources/`；可使用 `UE_AGENT_DATA_DIR` 指定数据目录。

也可以直接执行：

```bash
PYTHONPATH=services/api python3 -m unittest discover -s services/api/tests -p 'test_*.py' -v
```

## 重要边界

- 计算引擎不在运行时读取 Excel；原工作簿只作为只读对照物，模型契约来自 `packages/model-spec`。
- FastAPI 提供项目、场景、政策来源、抓取和导出接口，核心公式仍由 `app/domain/u1` 统一负责。
- 原始工作簿只作为只读对照物，不进入运行时，也不应被脚本改写。
- `u1-excel-v2.1-parity` 保留 Excel 可复核链路；S3、S5 的业务修正和 B12 默认常量已在公式台账、问题清单中明确记录。
- 政策页面只接受公开官网来源抓取，不提供 Demo 阶段的手动政策文件上传；抓取原文保存后生成灰色建议值，采用后才进入城市参数。
- 新增城市会自动创建城市入场任务，按三组字段族发现来源；`.gov.cn` 等高可信官方来源自动入正式来源，普通来源保留为待确认候选。任务状态通过 `/api/projects/{projectId}/onboarding` 查看。

## 关键政策接口

- `POST /api/policies/sources`：新增城市官网来源。
- `POST /api/policies/sources/{sourceId}/crawl`：抓取单个来源。
- `POST /api/policies/cities/{cityId}/crawl-all`：抓取该城市全部启用来源，单条失败不阻断整批。
- `GET /api/policies/cities/{cityId}/source-freshness`：检查长期未变或疑似过期来源。
- `GET /api/policies/artifacts/{artifactId}/content`：查看已保存的抓取原文。
- `GET /api/policies/export`：导出来源、抓取记录和结构化建议值。
- `POST/GET /api/policies/research-runs`：创建或查看按需实时政策检索任务；任务 brief 使用当前年份查询词。
- `GET /api/policies/research-runs/{runId}/brief`：给 WorkBuddy 的城市、字段、历史来源和检索任务说明。
- `POST /api/policies/research-runs/{runId}/results`、`POST /api/policies/research-runs/{runId}/complete`：回传候选来源/字段建议并结束任务。

## 城市自动入场

真实 API 默认使用公开搜索页发现来源，也可以配置自有搜索服务或 AI 网关：

```bash
export UE_AGENT_DISCOVERY_SEARCH_URL='https://www.baidu.com/s?wd={query}'
```

创建城市后，`POST /api/projects` 会同时创建基准场景和入场任务，响应包含 `onboarding.id`。任务完成后，正式来源会出现在政策资料页，自动爬虫字段建议值会出现在城市测算页；建议值仍需手动采用。

- `GET /api/projects/{projectId}/onboarding`：读取最新任务状态与统计。
- `POST /api/projects/{projectId}/onboarding/retry`：重试失败或部分失败任务。

### 按需实时政策检索

“实时”指用户触发后由 WorkBuddy 联网搜索当前年份的政策信息，不承诺 24 小时监听。WorkBuddy 先创建或复用一个城市 research run，再读取 `/brief`，使用动态查询词寻找最新的具体官方文章、统计公报或 PDF；原文必须交给 `/fetch-requests` 由 API 下载、落盘和计算 SHA256，HTTP 遇到 JS/WAF、超时或 TLS 失败时改用浏览器读取并回传 `/browser-artifacts` 归档，抽取结果通过 `/extraction-submissions` 或 `/research-runs/{runId}/results` 回传。`C6/C7/C8` 只能登记 `notDisclosed`，所有建议值都保持灰色，人工采用后才进入城市参数。

前端按钮创建的任务默认状态是 `queued`，这表示等待 WorkBuddy 执行，不代表检索已完成。若当前环境没有可调用 WorkBuddy 的桥接器，页面会提供可复制任务提示；在 WorkBuddy 对话中直接说“更新某城市政策”即可执行同一任务协议。回传接口在配置 `UE_AGENT_AGENT_TOKEN` 后必须携带 token。
