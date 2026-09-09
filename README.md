# UE Agent

长护险城市与单站投资决策系统。

本仓库已经完成工程规范基线、长护险经营决策总览、城市项目测算和本地政策资料审核闭环。当前版本支持全部城市总览、单城市/多城市对比、创建项目、编辑参数、保存场景、执行 24 个月测算、不可变结果快照，以及 Word/Excel/PDF 本地上传和政策候选字段人工审核。

## 项目目标

将现有长护险调研报告、政策文件和 Excel UE 模型整理为一套可追溯、可配置、可复算的决策工具，帮助业务人员回答以下问题：

- 目标城市或行政区是否具备长护险业务条件？
- 一个护理站能够触达多少潜在客户？
- 需要配置多少护理员、护士和管理人员？
- 筹备期、启动期和平台期分别需要投入多少钱？
- 预计何时实现月度盈亏平衡和累计现金流回正？
- 哪些结论来自官方数据，哪些属于推算或人工假设？

## 当前文档

- [UE Agent 产品需求文档（v1.1 Demo 基线）](docs/product/UE-Agent-产品需求文档-v1.0.md)
- [本地运行与交付](docs/deployment/local.md)
- [UE Agent 详细开发规范 v0.1](docs/UE-Agent-详细开发规范-v0.1.md)
- [GitHub 参考项目与技术选型](docs/GitHub-参考项目与技术选型.md)
- [开发规范总则 v0.2](docs/standards/00-规范总则.md)
- [组件与第三方代码复用规范](docs/standards/01-组件与第三方代码复用规范.md)
- [前端视觉设计系统](docs/standards/02-前端视觉设计系统.md)
- [页面布局与交互规范](docs/standards/03-页面布局与交互规范.md)
- [CSS 与样式文件规范](docs/standards/04-CSS与样式文件规范.md)
- [Vibe Coding 开发约束](docs/standards/05-Vibe-Coding开发约束.md)
- [前端验收检查表](docs/standards/06-前端验收检查表.md)
- [U1 参数字典](docs/model/u1-parameter-dictionary.md)
- [U1 公式台账](docs/model/u1-formula-ledger.md)
- [U1 已知问题与待业务确认](docs/model/u1-known-issues.md)

## 当前阶段原则

- 先完成整体产品骨架和数据关系，再逐项深化功能。
- U1 测算是首版唯一要求完整闭环的业务模块。
- 公开数据是参考值，必须保留来源、日期和可信度，不得静默覆盖人工确认值。
- 财务与运营计算使用确定性公式，不让大模型直接计算核心财务结果。
- 缺失值、真实零值和“不适用”必须区分。
- 当前 Excel 模型需完成公式审计后，才能作为系统验收基准。

## 计划中的系统模块

1. 总览仪表盘（全部城市、单城市、多城市对比）
2. 城市测算（控制台参数、场景、24 个月测算与结果快照）
3. 政策资料（官网来源配置、一键抓取、原文留存与参数建议值）
4. 城市对比（统一口径比较经营指标与数据完整度）

字段与公式不再作为独立管理模块：控制台字段、公式说明和待业务确认问题直接内嵌在城市测算页面。

## 仓库状态

- 状态：前端基础骨架和 U1 Excel 复刻计算基座已完成，本地可交付运行模式已切换为 SQLite
- 产品与架构文档：需求文档 v1.1 Demo 基线已定稿（含 75 字段控制台字典、四类数据源交互、待业务确认清单）
- 工程与前端规范：v0.2
- 本地数据：SQLite 仓储 + 初始化/迁移/备份/恢复命令已完成，既有 JSON 数据可一键导入
- 前端代码：workspace、总览、城市项目、政策资料、参数设置和兼容入口已完成；导航与四类数据源交互正按需求文档改造
- 计算引擎：Python 纯计算域已接入并通过基准回归
- 本地 API 与前端：FastAPI、动态参数表单和结果复核已接入
- 政策资料：当前仍是「本地上传 + 候选字段人工审核」，需求文档要求改为「官网来源配置 + 一键抓取 + 灰色建议值」，尚未改造
- 部署环境：本地运行为准，云端资源不依赖

## 本阶段运行方式

```bash
pnpm install
pnpm bootstrap   # 建数据目录与 SQLite 表结构，并在库内无项目时导入既有 projects.json
pnpm dev:all     # 同时启动 API 与前端，任一进程退出即整体停止
```

需要在两个终端分别看日志时执行 `pnpm api:dev` 和 `pnpm dev`。API 默认访问 `http://localhost:8000`，前端默认访问 `http://localhost:3000`。当前可查看 `/`、`/projects`、`/projects/new`、`/policies`、`/settings`。旧入口 `/u1` 和 `/projects/{projectId}/u1` 保留兼容跳转。

运行数据全部留在本机 `services/api/data/`（数据库 + `policy_files/` + `raw_sources/`），不入库。备份用 `pnpm data:backup`，恢复用 `pnpm data:restore --from services/api/backups/<时间戳>`，细节见[本地运行与交付](docs/deployment/local.md)。

Dashboard 默认读取 `/api/dashboard/overview`，按城市选择最近一次 `calculated` 或 `confirmed` 快照；参数修改后会标记为 `stale`。政策资料接口支持本地文件元数据、显式候选字段解析和人工通过/驳回，未审核字段不会进入正式政策汇总，也不会覆盖项目输入。

验证 U1 模型与后端：

```bash
pnpm model:test
pnpm api:test
```

如果 API 不在默认地址，复制 `apps/web/.env.example` 为 `.env.local` 并修改 `NEXT_PUBLIC_API_BASE_URL`。
