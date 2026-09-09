# 本地运行与交付

UE Agent 首版按「本机可运行、可交接」设计：结构化数据存 SQLite，政策原文和抓取原文存本地文件目录，不依赖任何云端数据库或对象存储。

## 前置条件

- Node.js 与 pnpm（仓库 `packageManager` 固定 `pnpm@10.13.1`）
- uv（用于 Python 依赖与虚拟环境）
- 首次拉取后执行 `pnpm install`，Python 侧由 `uv run --project services/api` 自动建环境

## 启动步骤

```bash
pnpm install
pnpm bootstrap   # 建数据目录、建库建表，并在库内无项目时导入既有 projects.json
pnpm dev:all     # 同时启动 API（:8000）和前端（:3000），任一进程退出即整体停止
```

需要分开看日志时用两个终端：

```bash
pnpm api:dev
pnpm dev
```

前端默认访问 `http://localhost:3000`，API 访问 `http://localhost:8000`。API 不在默认地址时，复制 `apps/web/.env.example` 为 `.env.local` 并修改 `NEXT_PUBLIC_API_BASE_URL`。

## 数据位置

```text
services/api/data/
├── ue-agent.sqlite3     结构化数据：项目、场景、快照、政策来源、原文记录、政策字段
├── policy_files/        政策原文文件实体
└── raw_sources/         官网抓取原文
```

整个 `services/api/data/` 与 `services/api/backups/` 都不入库。数据库里只保存文件相对路径、内容指纹和元数据，导出与下载一律通过记录 ID 定位，不接受任意本地路径。

## 备份与恢复

```bash
pnpm data:backup
pnpm data:restore --from services/api/backups/<时间戳目录>
```

备份目录名是 UTC 时间戳，内含数据库、`policy_files/`、`raw_sources/`、迁移源 `projects.json` 和 `MANIFEST.txt`。备份只读取当前数据，不删除不修改。

恢复顺序固定为：先校验备份数据库完整性，再把当前数据整体移入 `services/api/backups/pre-restore-<时间戳>/`，最后从备份复制回来，并在数据目录写入 `RESTORE_SOURCE.txt` 说明来源。校验失败时直接终止，现有数据保持原样；恢复前请先用 `pnpm dev:all` 停止写入。

## 环境变量

| 变量 | 作用 | 默认值 |
|---|---|---|
| `UE_AGENT_DB_FILE` | SQLite 数据库路径 | `services/api/data/ue-agent.sqlite3` |
| `UE_AGENT_DATA_DIR` | 本地数据目录 | `services/api/data` |
| `UE_AGENT_DATA_FILE` | 迁移源单文件 JSON 路径 | `services/api/data/projects.json` |
| `UE_AGENT_ALLOWED_ORIGINS` | 允许的前端来源，逗号分隔 | `http://localhost:3000` |
| `NEXT_PUBLIC_API_BASE_URL` | 前端访问的 API 地址 | `http://localhost:8000` |

## 验证命令

```bash
pnpm model:test   # U1 公式、阶段、基准与回归
pnpm api:test     # API、SQLite 仓储、迁移、备份恢复与仪表盘聚合
pnpm test         # 前端单元与组件测试
pnpm typecheck
pnpm lint
pnpm build
```

## 交接清单

1. 交付内容：本仓库源码 + `docs/`（需求文档、规范、模型台账）+ 一份 `pnpm data:backup` 产物。
2. 接手方执行 `pnpm install && pnpm bootstrap && pnpm dev:all`，浏览器打开 `http://localhost:3000`。
3. 需要带走演示数据时，把备份目录解压到 `services/api/data/`（先跑一次 `pnpm bootstrap` 建目录），再 `pnpm data:restore --from <备份目录>`。
4. 环境自检：`curl http://localhost:8000/api/health` 返回 `modelVersion`，`GET /api/projects` 能看到迁移进来的城市。
5. Vercel 与 Postgres 相关配置在本地运行模式下完全用不到，保留只是历史遗留，不需要申请任何云端资源或密钥。
