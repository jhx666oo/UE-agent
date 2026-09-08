# U1 MVP Vertical Slice Design

## 1. 目标

在现有 Next.js 前端骨架和 `u1-excel-v2.1-parity` Python 计算域之上，完成第一条可运行的业务闭环：

```text
新建项目 -> 创建场景 -> 动态填写 U1 参数 -> 保存输入 -> 调用测算 -> 查看 24 个月结果和待确认问题
```

本阶段的“完成”指本地可运行、输入和结果可持久化、前后端契约明确、基准模型可复算；不把政策爬虫、多城市比较、权限后台或生产部署混入本阶段。

## 2. 架构

```text
Next.js Web
  |  fetch JSON API
  v
FastAPI adapter
  |-- parameter catalog / baseline defaults
  |-- project and scenario endpoints
  |-- calculate endpoint
  v
JsonProjectRepository
  |-- local JSON file, atomic replacement
  v
U1 domain engine
  |-- model-spec JSON
  |-- deterministic 24-month calculation
  |-- issues and FormulaValue states
```

- 公式唯一归属 `services/api/app/domain/u1`，API 不实现任何业务公式，前端不实现任何财务公式。
- API 默认使用仓库内的本地数据文件；通过 `UE_AGENT_DATA_FILE` 可替换为测试临时文件。
- 前端通过 `NEXT_PUBLIC_API_BASE_URL` 访问 API，默认 `http://localhost:8000`。
- FastAPI 开启本地开发 CORS，只允许 `localhost:3000`、`127.0.0.1:3000` 和 API 自身本地地址。

## 3. API 契约

### 3.1 系统和规格

- `GET /api/health`：返回服务状态和当前模型版本。
- `GET /api/model/u1`：返回模型版本、参数字典、基准输入和已知问题。

### 3.2 项目和场景

- `GET /api/projects`：返回按更新时间倒序的项目摘要。
- `POST /api/projects`：创建项目，输入 `name`、`city`、可选 `district`、`baseMonth` 和 `stationMode`。
- `GET /api/projects/{project_id}`：返回项目及其场景。
- `POST /api/projects/{project_id}/scenarios`：创建场景，输入场景名和完整/部分参数；空参数使用基准输入副本。
- `GET /api/projects/{project_id}/scenarios/{scenario_id}`：返回场景、输入快照、最近一次结果和保存时间。
- `PUT /api/projects/{project_id}/scenarios/{scenario_id}`：保存参数快照，不自动计算。
- `POST /api/projects/{project_id}/scenarios/{scenario_id}/calculate`：运行确定性引擎，保存结果快照并返回结果。

错误响应统一为：

```json
{"error":{"code":"NOT_FOUND","message":"..."}}
```

缺少模型驱动参数时返回 HTTP 422，响应保留 `MISSING_REQUIRED_INPUT` 及其 Excel 单元格；模型公式错误和待确认问题作为 200 响应中的结构化结果返回，不伪装为 HTTP 失败。

## 4. 本地保存

`JsonProjectRepository` 保存一个 JSON 文档，包含 `projects[]`、场景输入、结果和 `updatedAt`。每次写入先写同目录临时文件，再使用 `os.replace` 原子替换。运行时数据路径加入 `.gitignore`，仓库只提交结构和测试 fixture，不提交业务数据。

## 5. 前端流程

1. `/projects/new` 创建项目后跳转 `/projects/{projectId}/u1`。
2. U1 页面加载 `/api/model/u1`，按 C/P/S/B/D/E/A/Z 分组渲染字段。
3. `formula` 字段只读并展示“公式值”；手工或参考值展示单位、必填状态和当前来源。
4. “保存参数”调用场景 `PUT`；“运行测算”先保存，再调用 calculate。
5. 结果区展示 headline、阶段摘要、24 个月表格和 issues；`formula_error`、`null`、`0` 分别显示为错误、未计算和 0。
6. 结果区保留模型版本和更新时间，待业务确认问题不能被折叠成普通提示。

## 6. 错误和边界

- API 不接受未知项目或场景 ID，返回 `404`。
- 参数值保持数字、字符串和 `null` 类型；前端不会把空输入自动转换为 0。
- 公式字段由服务端计算，客户端提交时忽略或拒绝对公式字段的人工覆盖。
- 计算结果中的 `#DIV/0!` 映射为 `FormulaValue(status="formula_error", error_code="DIV0")`，页面显示“不可计算：除数为 0”。
- 原始 Excel 仍只读，不上传、不改写、不作为 API 运行时依赖。

## 7. 测试策略

- Python：repository 原子保存/读取、API 契约、基准计算、缺失参数和问题透传。
- TypeScript：API client 的 URL/错误解析、参数分组和数字/null 格式化。
- 浏览器交互：先以组件级状态测试和生产构建为门槛；Playwright 在下一阶段 API 稳定后补充。
- 验收基准继续使用 `packages/model-spec/fixtures/u1-baseline.json`，不生成新的虚构业务结果。
