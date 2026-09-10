# PRD v1.1 实施进度与待办（交接记录）

> 更新时间：2026-09-09 晚。分支 `codex/dashboard-data-sync`。
> 本文档供下一个接手的 agent / 开发者继续实施 PRD v1.1（`docs/product/UE-Agent-产品需求文档-v1.0.md`）使用。

## 已完成（全部已推送）

### M1 本地 SQLite 可交付运行（1588752）
- `SqliteProjectRepository`：业务列+索引、快照 JSON 列、WAL、每操作短连接；与 JSON 仓储同契约（`ProjectRepository` 协议）
- 迁移脚本按方言分目录：`services/api/migrations/sqlite/`（001 建表、002 字段值、003 来源抓取配置）、`postgres/`（旧）
- `pnpm bootstrap`（幂等，库空时导入 projects.json）、`pnpm data:backup` / `data:restore`（恢复先把现有数据移入 pre-restore 副本，无删除操作）
- `pnpm dev:all` 一键起 API+前端；本地交付文档 `docs/deployment/local.md`
- 本地真实数据已迁移（2 项目 4 场景 3 快照），重启持久化已验证

### M2 字段契约与字段值四元组（3a12160、2df4bd7）
- `u1.parameters.json` 75 字段全部带 `block`/`blockOrder`（PRD 14.1 八分组）+ 8 个枚举参数 `options`，spec 契约测试锁定
- `GET /api/fields?block=` 控件契约（readOnly/editable/options）
- 场景创建/更新校验：公式自动字段（C9/P3/S3/S5/B12/B16）拒绝写入 `FORMULA_FIELD_READ_ONLY`、未知编号 `UNKNOWN_FIELD`、枚举越界 `INVALID_FIELD_VALUE`
- 字段值四元组：`scenario_field_values`（SQLite）+ `fieldValues`/`fieldValueHistory`（JSON），建议值未采用永不参与计算
- `GET /scenarios/{id}/values`、`PATCH .../values/{fieldId}`、`POST .../accept-suggestion`；普通 PUT 碰到爬虫字段自动标 `overridden`

### M3 抓取链（85970b2）
- `app/crawlers/`：仅 http/https、拒绝私有/回环/链路本地（SSRF）、最多 5 次重定向且每次重校验、超时≤60s、大小≤20MB、可识别 UA、原子落盘 `raw_sources/<sha256>.bin`
- `POST /policies/sources/{id}/crawl`：每次抓取留 `crawl_artifacts` 记录，变更比对 first_fetch/unchanged/new_version，失败也留记录且不删上次成功
- HTML 标题/可读文本提取；`parse_suggestions`（P1/P2/P8 模式）生成建议值写入同城市场景四元组
- 来源配置增强：timeoutSeconds/maxBytes/note/lastFetchedAt/lastHttpStatus/lastChangeStatus（PUT 可改）
- 手动上传路由已移除：`POST /policies/documents/upload` 返回 404 `UPLOAD_NOT_AVAILABLE`；`app/(workspace)/policies/[cityId]` 上传面板组件已删

### M4 前端（a364b22，已推送）
- M4a 导航四项化完成：`lib/navigation.ts` 总览/城市测算/政策资料/城市对比（`/?scope=compare`），删「参数设置」项；`/settings` 页面仍在但不在主导航；全站术语统一（城市测算/新增城市/打开城市）
- M4b 城市测算页完成：`FieldValueControl` 四类数据源交互（内部填写=普通输入、自动爬虫=灰色建议值+采用按钮+查看来源、公式自动=浅绿只读框、其他来源=可留空），枚举渲染下拉；`city-project-workbench` 改为字段值驱动 + 按八分组渲染 + 乐观更新 PATCH + 接受建议值后标待重算
- M4c 政策页完成：`policy-city-detail` 重构为官网来源列表（新增/启停/立即抓取）+ 抓取历史（含建议值摘要/失败原因/查看原文）+ 关联城市；`lib/policies.ts` 全套抓取 API
- M4d 验证通过：后端 101 项、前端 27 项、typecheck、eslint 全绿
- M4e README 状态校正（M4 后补）：仓库状态中"前端代码"由"正按需求文档改造"改为"已按需求文档改造"，"政策资料"改为「官网来源配置 + 一键抓取 + 灰色建议值」描述

## 运行中的进程（接手时先看）

> 上一位 agent 留了两个进程在跑：**API :8000**、**前端 :3000**，日志落在 `/tmp/prd_build/`。
>
> ⚠️ **API 进程是 M4 之前起的旧代码**，其中"查看公式 options"这个后端小改动没有生效。
> 接手第一步请先杀掉 API 进程，再重启：
>
> ```bash
> lsof -ti:8000 | xargs kill -9        # 杀旧 API
> pnpm api:dev                         # 在仓库根目录重启
> ```
>
> 前端 :3000 进程代码已就绪，必要时同样 `lsof -ti:3000 | xargs kill -9 && pnpm dev`。

## M5 接手后续（本轮已完成，均已推送）

本轮由接手 agent 完成，4 个提交：`5d67234` → `e1991fb` → `0b26cd3` → `74655c9`。
门禁：后端 **110 项**、前端 **24 项**、typecheck、eslint 全绿。

### 发现并修复 P0 bug：抓取接口 500（e1991fb）
- **现象**：`POST /api/policies/sources/{id}/crawl` 返回 500，日志 `sqlite3.OperationalError: no such column: lastFetchedAt`
- **根因**：`SqliteProjectRepository.update_data_source` 把 camelCase 的 API 字段名直接拼进 SQL 列名（`SET lastFetchedAt = ?`），而 003 迁移建的是 snake_case 列（`last_fetched_at`）。`name/url/status` 等单词两边同名，所以一直没暴露
- **修复**：新增 `SOURCE_COLUMN_BY_KEY`（`SQLITE_SOURCE_KEYS` 的反向表），拼列名前先映射
- **为什么 101 项测试没发现**：`test_crawl_api.py` 用的是 `JsonProjectRepository`（纯 dict，不做 SQL 映射），而生产默认走 SQLite。已补回归测试 `test_data_source_crawl_status_columns_use_snake_case_columns`
- **教训**：抓取链路的测试要覆盖 SQLite 仓储，不能只跑 JSON 仓储

### 端到端验收（原待办 1，已完成）
走通「抓取 → 建议值 → 采用 → 手工覆盖 → 重算 → 仪表盘」全链路，均符合 PRD：
- 抓取 HTTP 200，标题 / 指纹 / 原文落盘正常
- 建议值解析：P1=60、P2=0.8（80% 正确换算为 0-1）、P8=2
- 灰色建议值状态 `suggestion_ready`，未采用前不参与计算
- 采用 P1：50→60，状态 `accepted`，**场景自动转 `stale`**
- 手工改 P2：状态 `overridden`，**建议值仍保留**（PRD 15.3）
- 重算：24 个月，`u1-excel-v2.1-parity`；仪表盘 200，summary/cities/trend 正常
- 验收后已把测试期写入的脏值恢复（P1=50、P2=0.8）并重算

> 抓取需要公网 URL（SSRF 默认拒绝本机/私有地址）。`crawl_allow_private` 是仅测试用的放行开关，
> 通过 `app.state.crawl_allow_private = True` 生效，生产路径保持拒绝。真实公网抓取用 example.com 验证过。

### 清理 /u1 死代码（原待办 3，已完成）
删除 `u1-workbench.tsx`、`u1-workbench.test.tsx`、`u1-parameter-field.tsx`、`lib/u1.ts`、`lib/u1.test.ts`（共 271 行）。
⚠️ `u1-result-panel.tsx` **仍被 `city-project-workbench` 使用，必须保留**——不要因为名字带 u1 就一起删。

### 导出接口（原待办 6，已完成）
`GET /api/policies/export`，支持 `format=csv|json`、`dataset=fields|sources|artifacts`、`cityId` / `sourceId` 过滤：
- CSV 带 UTF-8 BOM，Excel 中文正常（PRD 20.4）
- 建议值 / 当前实际值 / 值状态 / 建议来源 / 采集时间分列（PRD 11.12）
- artifact 用 `artifactId` 字段（不是 `id`）
- 非法 format / dataset 返回 400 + `UNSUPPORTED_EXPORT_FORMAT` / `UNSUPPORTED_EXPORT_DATASET`

### 错误结构补全（原待办 7，已完成）
`error_payload` 增加 `requestId`（uuid4）与可选 `field`；查询参数与字段校验错误带上 field，`NOT_FOUND` 不带。

## M6 接手后续（本轮已完成，均已提交，待推送）

本轮完成 4 项待办，2 个提交：`941e181`（后端）、`8d2c196`（前端）。
门禁：后端 **115 项**、前端 **24 项**、typecheck、eslint、`next build` 全绿。

### ZIP 导出（原待办 4，已完成）
`GET /api/policies/export?sourceId={id}&format=zip`：打包该来源抓取原文（`raw_sources/<sha>.bin`）+ `manifest.csv`（记录 ID/文件名/SHA256/标题/状态），`Content-Type: application/zip`。缺 `sourceId` 返回 `MISSING_EXPORT_SOURCE`，无原文返回 404。

### 仪表盘筛选进 URL（原待办 2，已完成）
引入 `nuqs@2.10.1`（规范白名单内，复用判断：URL 状态管理是其文档明确的类别）。根布局挂 `<NuqsAdapter>`；首页改为客户端组件，`scope/cityIds/period/includeStale` 用 `useQueryStates` 读写 URL（PRD 9.2 刷新后保留筛选），首页包 `<Suspense>` 满足 `useSearchParams` 边界。`DashboardOverview` 增加受控 `query` 模式，筛选变化时自动重拉数据（此前生产路径筛选不触发刷新，一并修复）。「城市对比」导航 `/?scope=compare` 现在真正生效。

### 城市级字段值别名（原待办 3，已完成）
新增 `GET/PATCH /api/cities/{cityId}/values[/{fieldId}]` 与 `accept-suggestion` 别名，把城市解析到「主项目 + 最近更新场景」（与仪表盘聚合器 `_city_id`/`_project_scenario` 一致），复用场景级校验与写值逻辑，不动存储。

### /settings 页（原待办 1，已完成）
页面保留为只读「字段与公式」字典（模型版本/参数/问题），标题由「参数设置」改为「字段与公式」，并从城市测算列表页头部加「字段与公式」入口（PRD 7.1/7.2）。

### 旧测试数据清理（原待办 5，已完成，用户已授权）
删除 2 个测试项目（进程验证项目、SQLite 重启验证）及其场景/快照/字段值/历史，删除 2 条 E2E 来源与 4 条抓取记录、2 条 E2E 快照，清理 `raw_sources/` 下 2 个孤儿 `.bin`。删前用 `scripts/backup_data.py` 备份（`services/api/backups/20260910T014006Z`）。剩余 1 项目 3 场景 3 快照，外键检查通过。

## 待办（剩余，仅 1 项）

1. **B12 GR 公关费用**：参数字典标「公式自动」但 Excel E47 是常量 5000，引擎目前当普通必填输入读（engine.py 中 `B12` 仍 required）。需业务确认后决定：改为只读常量公式 + issue 标记，属模型语义变更，勿擅自改（AGENTS.md 门禁）

## 验证命令速查

```bash
pnpm model:test   # 纯计算域（python3 直接跑）
pnpm api:test     # API 全量（uv；或 PYTHONPATH=services/api services/api/.venv/bin/python -m unittest discover -s services/api/tests -p 'test_*.py'）
cd apps/web && ../apps/web/node_modules/.bin/vitest run   # 前端（本机 pnpm 不在 PATH，直接用 node_modules/.bin）
```

注意：本机 shell 没有 pnpm/corepack，Python 用 `services/api/.venv/bin/python` 直跑。
