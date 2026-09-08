# GitHub 参考项目与技术选型

## 1. 调研目的

本次调研用于确定 UE Agent 的技术框架、后台界面基础、政策资料管理方式和爬虫任务设计方式。参考项目只用于学习架构和交互模式，不直接整仓复制。

调研日期：2026-09-08。

## 2. 参考项目

| 项目 | 调研时状态 | 参考价值 | 许可证 | 采用方式 |
|---|---|---|---|---|
| [Kiranism/next-shadcn-dashboard-starter](https://github.com/Kiranism/next-shadcn-dashboard-starter) | 约 7.0k Stars，2026-08 有更新 | Next.js 16、TypeScript、shadcn/ui、Tailwind CSS v4、TanStack Query/Table、Zod、Recharts；后台页面、表格和表单模式完整 | MIT | 作为前端工程和交互骨架的首选参考 |
| [Oliveluo666/post-investment-platform](https://github.com/Oliveluo666/post-investment-platform) | 约 100 Stars，2026-08 有更新 | 项目总览、项目详情、财务看板、Excel 导入、报告导出和后台数据表设计与本项目接近 | MIT | 参考“项目工作台”和财务信息组织方式，不采用其 CloudBase 绑定 |
| [Po1ntu04/policy-RAG](https://github.com/Po1ntu04/policy-RAG) | 约 30 Stars，2026-05 有更新 | 政策元数据、结构化指标、文档块检索、RBAC、审计证据和批量入库设计较完整 | Apache-2.0 | 参考政策库数据模型、来源追溯和审核流程；其 README 明确为课程设计，不能直接当生产底座 |
| [Gerapy/Gerapy](https://github.com/Gerapy/Gerapy) | 约 3.5k Stars，2026-07 有更新 | Scrapy/Scrapyd 任务部署、定时任务、运行监控和失败状态管理 | MIT | 参考爬虫任务管理流程；不直接引入其完整平台和不稳定的可视化配置模块 |
| [infiniflow/ragflow](https://github.com/infiniflow/ragflow) | 约 90k Stars，2026-09 有更新 | 文档解析、分块、引用溯源、知识库和检索增强生成能力成熟 | Apache-2.0 | 作为后续语义检索能力参考；其完整部署资源要求较高，首版不作为基础依赖 |
| [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | 约 123k Stars，2026-09 有更新 | 可访问、可定制、代码归属项目自身的组件体系 | MIT | 作为基础组件库 |
| [recharts/recharts](https://github.com/recharts/recharts) | 约 27.5k Stars，2026-09 有更新 | React 图表库，适合月度趋势、现金流和结构占比图 | MIT | 作为首版图表库 |

## 3. 候选架构比较

### 方案 A：全 TypeScript 单体

技术组合：Next.js + TypeScript + PostgreSQL + Node.js 定时任务。

优点：

- 工程数量少，前后端语言统一。
- 首版部署和本地启动较简单。
- 适合普通 CRUD、表单和报表。

局限：

- 政务网页抓取、文档解析和后续数据分析生态不如 Python 集中。
- 计算、爬虫和网页请求混在同一进程后，长期维护边界容易模糊。

### 方案 B：Next.js + FastAPI 模块化架构

技术组合：Next.js 前端、FastAPI 业务 API、Python 爬虫 Worker、PostgreSQL、Redis。

优点：

- 前端适合建设专业后台和交互式测算页面。
- Python 适合公式复算、Excel 校验、网页抓取、文档解析和后续 AI 能力。
- API、计算引擎和爬虫任务边界清楚。
- 后续上线鹅宝或迁移部署时，可以独立替换认证、队列或存储。

局限：

- 比单体多一个服务，需维护前后端接口契约。
- 本地开发需要统一启动脚本或 Docker Compose。

### 方案 C：Streamlit/低代码快速原型

技术组合：Streamlit + Python + SQLite/PostgreSQL。

优点：

- 形成可操作原型速度快。
- 复用 Python 计算逻辑方便。

局限：

- 复杂表单、权限、项目管理和高密度后台体验受限。
- 后续扩展政策中心、多人协作和鹅宝集成时重构成本较高。

## 4. 最终选择

采用方案 B：Next.js + FastAPI 模块化架构。

选择依据：

1. U1 不是一次性计算器，而是需要保存项目、场景、模型版本和计算快照的长期业务系统。
2. 政策采集、文档解析和 Excel 对照验证更适合 Python。
3. 前端需要高密度表格、分步表单、图表和来源侧栏，Next.js + shadcn/ui 更合适。
4. 首版可以保持模块化单体部署，不必一开始拆成大量微服务。

## 5. 确定的技术栈

### 5.1 前端

| 类别 | 选择 |
|---|---|
| 框架 | Next.js 16，App Router |
| 语言 | TypeScript |
| UI | shadcn/ui + Tailwind CSS v4 |
| 表单 | TanStack Form + Zod |
| 服务端状态 | TanStack Query |
| 表格 | TanStack Table |
| URL 状态 | nuqs |
| 图表 | Recharts |
| 图标 | Tabler Icons |
| 测试 | Vitest + Testing Library + Playwright |

实施时基于 `Kiranism/next-shadcn-dashboard-starter` 的工程模式启动，但删除计费、聊天、看板等无关模块。认证部分不直接依赖 Clerk，保留鹅宝统一认证适配接口。

### 5.2 后端

| 类别 | 选择 |
|---|---|
| API 框架 | FastAPI |
| 数据校验 | Pydantic |
| ORM | SQLAlchemy 2 |
| 数据迁移 | Alembic |
| 数据库 | PostgreSQL |
| 缓存/队列 | Redis |
| 后台任务 | Celery |
| API 文档 | OpenAPI/Swagger |
| 测试 | Pytest |

### 5.3 数据采集

| 场景 | 选择 |
|---|---|
| 普通 HTML 页面 | httpx + BeautifulSoup |
| 结构化批量抓取 | Scrapy |
| JavaScript 动态页面 | Playwright |
| 定时调度 | Celery Beat |
| 文件解析 | Python 文档解析库，按 PDF、DOCX、XLSX 分类型处理 |
| OCR | 仅在扫描件无法读取文本时启用 |

### 5.4 政策检索

首版使用 PostgreSQL 元数据检索和全文检索。政策正文、发布机关、文号、生效日期、失效日期、适用区域、申报材料和人员配置要求均保存为结构化字段。

后续需要语义问答时，在 PostgreSQL 中增加 pgvector，或者通过标准接口接入独立 RAG 服务。RAGFlow 首期不引入，原因是其部署资源和运维复杂度明显高于当前政策检索需求。

## 6. 前端主题选择

主题名称：长护险决策工作台。

风格定位：专业、克制、可信、适合高信息密度业务决策。

### 6.1 色彩

| 用途 | 建议色 |
|---|---|
| 页面背景 | 暖灰白 `#F7F7F5` |
| 卡片背景 | 白色 `#FFFFFF` |
| 主文字 | 深石板 `#1F2937` |
| 次级文字 | 灰色 `#667085` |
| 主色 | 深青绿 `#0F766E` |
| 信息提示 | 深蓝 `#2563EB` |
| 正向结果 | 绿色 `#15803D` |
| 风险提示 | 琥珀色 `#D97706` |
| 错误/阻断 | 红色 `#B42318` |
| 边框 | `#E5E7EB` |

不用大面积渐变、玻璃拟态和纯装饰性动画。颜色只用于表达层级、状态和风险。

### 6.2 字体与数字

- 中文优先：PingFang SC、Noto Sans SC、Microsoft YaHei。
- 英文和数字：Inter 或系统无衬线字体。
- 财务数据使用等宽数字特性，金额默认千分位。
- 百分比、人数、月份和金额必须同时显示单位。

### 6.3 页面布局

- 左侧固定导航，宽度约 240px。
- 顶部工具栏展示当前项目、城市、模型版本和测算状态。
- 内容区使用 12 列网格，最大宽度约 1440px。
- 输入页面采用“步骤导航 + 主表单 + 来源与说明侧栏”。
- 结果页面采用“核心指标卡 + 现金流趋势 + 月度明细 + 口径说明”。

### 6.4 关键交互

- 参考值和人工填写值并排展示。
- 一键填入参考值必须是显式动作。
- 低可信度、过期或缺少来源的数据必须显示标记。
- 修改参数后显示“结果待重新计算”，避免旧结果与新输入混淆。
- 每次正式计算产生不可变的结果快照。

## 7. 不直接采用的方案

- 不使用纯 Excel 作为生产计算引擎。Excel 只作为口径校验和测试基准。
- 不让大模型生成或修改核心财务结果。
- 不让爬虫结果自动覆盖业务确认值。
- 不在首版引入重型 RAG 平台、微服务网格或复杂数据仓库。
- 不直接使用需要境外 SaaS 才能运行的认证组件作为生产唯一认证方式。

## 8. 许可证与复用要求

- 复用 MIT 和 Apache-2.0 项目的代码或配置时，保留原始许可证和必要版权声明。
- 参考 UI 布局和产品思路时，在设计记录中注明来源。
- 不复制许可证不明确项目的源代码。
- 第三方依赖在正式开发前生成依赖清单和许可证清单。
