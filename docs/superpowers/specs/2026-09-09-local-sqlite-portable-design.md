# 本地 SQLite 可移植交付设计

## 目标

将 UE-Agent 从依赖 Vercel Postgres/Blob 的生产部署方向切换为本地可移植交付：项目、测算结果、政策审核数据保存在 SQLite，政策原文件和爬取原文保存在项目数据目录，接收方复制仓库与数据目录后即可继续开发。

## 方案选择

采用 SQLite + 本地文件目录。

- SQLite：结构化保存项目、场景、测算快照、数据源、政策资料和政策事实。
- `services/api/data/policy_files/`：保存政策原文件。
- `services/api/data/raw_sources/`：保存爬取原文和抓取元数据。
- `services/api/migrations/`：保存幂等数据库迁移脚本。
- 本地 JSON 仅作为一次性迁移输入和测试夹具，不再作为运行时主存储。

不采用本地 Postgres：它增加安装、端口、用户权限和备份依赖，不利于下周移交。

## 数据边界

SQLite 表使用稳定业务 ID；复杂输入和结果保留为 JSON 文本，以保持现有 U1 引擎和 Dashboard API 的响应结构不变。

- `projects`
- `scenarios`
- `calculation_snapshots`
- `data_sources`
- `policy_documents`
- `policy_facts`
- `crawl_artifacts`

政策事实仍必须人工审核后才进入 Dashboard 汇总。爬虫只保存原文和候选资料，不自动发布政策结论。

## 运行方式

```bash
pnpm install
pnpm bootstrap
pnpm dev:all
```

`pnpm bootstrap` 创建/升级 SQLite、导入现有 `projects.json`（仅当目标库为空时）并创建数据目录；`pnpm dev:all` 同时启动 FastAPI 和 Next.js。

## 移交方式

移交时保留：

- 源代码和锁文件
- `services/api/data/ue-agent.sqlite3`
- `services/api/data/policy_files/`
- `services/api/data/raw_sources/`
- `.env.example` 和开发文档

不移交：

- `node_modules/`
- `.venv/`
- `.next/`
- `.env.local`
- Vercel token 或其他平台密钥

## 失败与备份

- 数据库迁移失败时退出并保留原数据库，不覆盖原文件。
- 写入文件使用临时文件后原子替换。
- 提供 `pnpm data:backup` 生成带时间戳的 SQLite、政策文件和爬取原文备份。
- SQLite 适合当前单机/小团队交付，不承诺多实例并发写入；未来需要多人在线协作时再迁移到 Postgres。

## 验收标准

1. 新环境执行 `pnpm bootstrap` 后能启动首页、项目页和政策中心。
2. 创建项目、修改参数、计算、确认结果后，重启 API 数据仍存在。
3. 上传政策文件、审核政策事实、重启 API 后记录和文件仍存在。
4. 配置一个政策来源后可执行本地抓取，原文和抓取元数据进入 `raw_sources`/`crawl_artifacts`。
5. 现有 Dashboard、U1、政策和回归测试全部通过。
