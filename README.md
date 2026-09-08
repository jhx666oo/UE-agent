# UE Agent

长护险城市与单站投资决策系统。

本仓库已经完成工程规范基线、第一阶段前端骨架、U1 Excel 复刻计算基座和本地可运行的 U1 MVP 闭环。当前可运行版本支持创建项目、编辑参数、保存场景、执行 24 个月测算和复核待确认问题；数据库、真实数据连接和政策采集将在后续阶段逐步接入。

## 项目目标

将现有长护险调研报告、政策文件和 Excel UE 模型整理为一套可追溯、可配置、可复算的决策工具，帮助业务人员回答以下问题：

- 目标城市或行政区是否具备长护险业务条件？
- 一个护理站能够触达多少潜在客户？
- 需要配置多少护理员、护士和管理人员？
- 筹备期、启动期和平台期分别需要投入多少钱？
- 预计何时实现月度盈亏平衡和累计现金流回正？
- 哪些结论来自官方数据，哪些属于推算或人工假设？

## 当前文档

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

1. 项目管理
2. U1 单站 UE 测算
3. 城市与市场资料
4. 长护险政策中心
5. 多城市对比
6. 后台管理

## 仓库状态

- 状态：前端基础骨架和 U1 Excel 复刻计算基座已完成
- 产品与架构文档：v0.1
- 工程与前端规范：v0.2
- 前端代码：workspace、应用壳层、共享组件、项目入口、U1 入口已完成第一阶段
- 计算引擎：Python 纯计算域已接入并通过基准回归
- 本地 API 与前端：FastAPI、JSON 项目存储、动态参数表单和结果复核已接入
- 部署环境：未创建

## 本阶段运行方式

```bash
pnpm install
```

在两个终端分别执行：

```bash
pnpm api:dev
```

```bash
pnpm dev
```

API 默认访问 `http://localhost:8000`，前端默认访问 `http://localhost:3000`。当前可查看 `/projects`、`/projects/new`、`/u1` 和创建项目后的 `/projects/{projectId}/u1`。

验证 U1 模型：

```bash
pnpm model:test
pnpm api:test
```

如果 API 不在默认地址，复制 `apps/web/.env.example` 为 `.env.local` 并修改 `NEXT_PUBLIC_API_BASE_URL`。
