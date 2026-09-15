# 本地运行与交付

UE Agent 首版按「本机可运行、可交接」设计：结构化数据存 SQLite，政策原文和抓取原文存本地文件目录，不依赖任何云端数据库或对象存储。

## 前置条件

- Node.js 与 pnpm（仓库 `packageManager` 固定 `pnpm@11.14.0`）
- Python 3.11+
- 首次拉取后执行 `pnpm setup`，脚本会创建 `services/api/.venv` 并安装 Python/Node 依赖；不要求接手方预装 uv

## 启动步骤

```bash
pnpm setup       # 安装依赖，初始化或恢复交付包内 SQLite 数据
pnpm dev:all     # 同时启动 API（:8000）和前端（:3000），任一进程退出即整体停止
```

如果是从 Git 仓库直接拉取且没有 `handoff-data/`，`pnpm setup` 会创建空库；如果是从
`pnpm handoff:package` 的压缩包解压，脚本会在空数据目录中自动恢复其中的演示数据和政策原文。
重新执行不会重复导入项目。

需要分开看日志时用两个终端：

```bash
pnpm api:dev
pnpm dev
```

前端默认访问 `http://localhost:3000`，API 访问 `http://localhost:8000`。API 不在默认地址时，复制 `apps/web/.env.example` 为 `.env.local` 并修改 `NEXT_PUBLIC_API_BASE_URL`。

需要更新某城市最新政策时，在政策城市页点击“AI 实时更新政策”创建任务；页面会显示 `queued` 和可复制的 WorkBuddy 任务提示。将提示交给 WorkBuddy，或直接在 WorkBuddy 对话中说“更新长沙政策”，WorkBuddy 会读取 research run brief，按当前年份检索并通过 API 保存原文、候选来源和灰色建议值。建议值不会自动覆盖人工参数，必须回到城市测算页逐条采用。

长期运行时使用仓库内的 `.workbuddy/skills/policy-ai-crawler/SKILL.md` 和
`.workbuddy/automations/policy-ai-sync.template.json`：WorkBuddy 每日 08:00 读取全部城市，
新增城市先走 `policy-city-onboarding`，然后逐城执行实时研究和回传。定时任务记录属于
WorkBuddy 账号，接手方需要在自己的账号中按模板创建一次；代码、Skill、数据和执行规则均随交付包携带。
当固定官网被 JS/WAF、超时或 TLS 拦截时，Skill 会自动切换 WorkBuddy 浏览器通道，
把浏览器看到的官方正文通过 `/api/policies/browser-artifacts` 归档后再抽取；该流程对全部城市
复用，不需要新增城市专门编写抓取代码。
失败来源会进入 `/api/policies/fallback-tasks` 队列；队列未处理前系统不会重复请求同一 URL。
响应体过大的 PDF/页面也会转入该队列，由 WorkBuddy 浏览器读取可见正文；若浏览器仍失败，任务会保留失败原因并在下一轮重试。

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
