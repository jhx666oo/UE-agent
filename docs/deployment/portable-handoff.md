# UE-Agent 可移植交付说明

## 交付内容

交付包包含：

- UE-Agent 前端、FastAPI、模型规格、测试和开发文档；
- 当前本地 SQLite 数据库；
- `policy_files/` 政策文件和 `raw_sources/` 官网抓取原文；
- `.workbuddy/skills/policy-ai-crawler/`：常规政策实时检索与字段抽取 Skill；
- `.workbuddy/skills/policy-city-onboarding/`：新增城市自动发现来源 Skill；
- `.workbuddy/automations/policy-ai-sync.template.json`：全城市每日同步模板；
- `PROJECT_CONTEXT.md`：仅包含 UE-Agent 项目约定的 AI 上下文与长期记忆；
- WorkBuddy HTTP 失败后的浏览器兜底协议：`/api/policies/browser-artifacts`；
- WorkBuddy 浏览器兜底任务队列：`/api/policies/fallback-tasks`，以及 010 SQLite 迁移；
- `HANDOFF.md`：解压后的启动说明。

交付包不会包含 `.env.local`、Vercel OIDC token、依赖目录、构建缓存、`.git`、用户/账号级记忆或 WorkBuddy 私有 memory。令牌只能由接手方在本地环境配置，不能写入仓库或任务模板。项目约定统一写入 `PROJECT_CONTEXT.md`。

## 交付方生成压缩包

在仓库根目录执行：

```bash
pnpm bootstrap
pnpm handoff:check
pnpm handoff:package
```

压缩包会生成在 `dist/ue-agent-handoff-<UTC时间>.tar.gz`。打包过程只读取当前数据库，并通过 SQLite 在线备份接口生成一致性副本，不会删除或修改正在运行的数据。

如只需要空库源码：

```bash
PYTHONPATH=services/api:$PWD python3 scripts/handoff.py --without-data
```

## 接手方一键启动

解压后在包目录执行：

```bash
bash scripts/setup-local.sh
bash scripts/dev-all.sh
```

`setup-local.sh` 会创建 `services/api/.venv`、安装 Python 依赖、安装 pnpm workspace 依赖、初始化 SQLite，并在目标数据目录没有数据库时恢复包内的 `handoff-data/`。重复执行不会导入第二份项目数据。

浏览器访问：

- 前端：`http://localhost:3000`
- API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

## WorkBuddy 一次初始化

打开同一个仓库工作区，在 WorkBuddy 中让它读取：

```text
.workbuddy/automations/policy-ai-sync.template.json
```

并创建每日 08:00（Asia/Shanghai）的“UE-Agent 全城市政策同步”定时任务。该任务只需要创建一次，后续新增城市不需要新增任务。定时任务运行时应调用项目级 `policy-ai-crawler` Skill；没有政策来源的新城市先调用 `policy-city-onboarding`。

WorkBuddy 的账号级定时任务记录不能随 Git 复制，接手方必须在自己的 WorkBuddy 账号中完成这一次创建。Skill 文件、定时任务内容、API 地址约定和所有政策数据规则已经在交付包中。
其中固定 URL 遇到 JS/WAF、超时或 TLS 失败时，`policy-ai-crawler` 会按统一协议切换浏览器读取，
回传正文并归档为 `workbuddy_browser` artifact；新增城市不需要增加代码或单独定时任务。
大 PDF/大页面响应超过 HTTP 通道上限时也会进入同一队列；任务未归档前不会重复请求同一来源，
因此交接方只需启动本地 API，并在自己的 WorkBuddy 中按模板启用一次全城市定时任务。

## 本地 API 与 WorkBuddy 网络边界

默认 API 地址为 `http://127.0.0.1:8000`。只有在同一台电脑运行的 WorkBuddy 才能直接访问这个地址。若 WorkBuddy 任务运行在云端，需要把 `apiBaseUrl` 改成接手方可访问的内网地址或受保护的部署地址，并在 API 设置 `UE_AGENT_AGENT_TOKEN`；不要把 token 写进 Skill 或 JSON 模板。

## 数据安全边界

- AI 只能提交来源、原文关联和灰色字段建议，不能直接写入核心财务计算结果；
- `C6/C7/C8` 只能标记 `notDisclosed`，不能估算；
- 政策建议值必须由业务人员在城市测算页逐条采用后才影响计算；
- 原文和抓取版本保留在本地，便于审计和继续开发；
- 备份与恢复命令见 `docs/deployment/local.md`。
