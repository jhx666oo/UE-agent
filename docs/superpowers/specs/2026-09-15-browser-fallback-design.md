# 政策双通道抓取兜底设计

## 1. 目标

当普通 HTTP 抓取遇到 JS 挑战型 WAF、证书握手、超时或其他外站限制时，系统不把本次政策更新静默丢弃，而是生成可执行的浏览器兜底任务。WorkBuddy 使用浏览器或 AI 检索能力获取正文后，将带来源和引用的内容回传 UE-Agent，由 API 统一归档、校验和生成灰色建议值。

该流程必须对现有城市和未来新增城市通用，不为单个城市编写专用抓取器，也不能覆盖人工填写或人工覆盖的测算参数。

## 2. 非目标

- 不在 API 进程内内置 Playwright、验证码破解或代理池。
- 不把 WorkBuddy、搜索服务或模型密钥放进前端、SQLite 或 Git 仓库。
- 不把搜索摘要直接当作政策原文，也不因兜底成功而绕过 quote、单位、枚举、区间和 C6/C7/C8 禁估校验。
- 不修改确定性测算公式，不让 AI 直接写入正式测算值。

## 3. 方案选择

### 方案 A：WorkBuddy 浏览器兜底（采用）

API 先走当前轻量 HTTP 抓取；失败后返回结构化兜底动作。WorkBuddy 打开原 URL 或搜索官方镜像，回传页面正文和证据；API 新增浏览器归档接口，后续复用原有抽取校验链路。

优点是保持本地项目轻量、移交简单，并且利用 WorkBuddy 已有的浏览器和 AI 检索能力。缺点是浏览器动作依赖 WorkBuddy 执行，需要在 Skill 中明确完成协议。

### 方案 B：API 内嵌 Playwright

在本地 API 内安装 Chromium 并自动执行 JS。优点是调用方更简单，缺点是安装包大、跨电脑移交复杂，仍不能保证绕过验证码或复杂 WAF，不符合当前 Demo 的可移植性要求。

### 方案 C：外部浏览器服务

API 将失败 URL 交给第三方浏览器抓取服务。优点是托管方便，缺点是产生账号、费用、数据合规和网络依赖，无法做到拿到项目目录即可离线移交。

## 4. 数据流

```text
新增城市 / 定时全城市任务
        ↓
WorkBuddy 读取 brief，调用 fetch-requests
        ↓
普通 httpx 成功 ─────────────→ 保存 artifact → 抽取建议值
        ↓ 失败
返回 fallbackAction=browser_search
        ↓
WorkBuddy 打开原 URL / 检索官方镜像
        ↓
POST /api/policies/browser-artifacts
        ↓
保存浏览器正文 artifact + SHA256 + 来源方式
        ↓
extraction-submissions（沿用现有 quote/字段校验）
        ↓
灰色建议值 → 人工采用后 → 测算页与总览
```

## 5. 后端接口与状态

### 5.1 普通抓取失败结果

`fetch-requests` 和单来源抓取在失败结果中增加：

```json
{
  "status": "failed",
  "errorCode": "HTTP_412_BROWSER_REQUIRED",
  "errorMessage": "官网返回 HTTP 412，未保存内容",
  "fallbackAction": "browser_search",
  "fallbackReason": "js_challenge"
}
```

网络、证书、超时分别保留可读错误，并返回同样的兜底动作；参数非法、私网地址、停用来源等安全或配置错误不进入浏览器兜底。

### 5.2 浏览器正文归档

新增 `POST /api/policies/browser-artifacts`，只允许 WorkBuddy Agent Token 调用。请求字段：

- `cityId`、`sourceId`、`researchRunId`：关联城市、已知来源和任务，可按协议校验归属。
- `requestedUrl`、`finalUrl`、`title`：保留原始页面和实际证据地址。
- `content`、`contentType`：正文文本，限制大小并以 UTF-8 保存。
- `fetchMode`：固定为 `workbuddy_browser`，禁止调用方伪造为内部 HTTP。

接口执行 SSRF 无关的回传校验：URL 必须是 http/https；正文不能为空且不超过上限；城市和来源必须存在。保存后生成标准 `crawl_artifact`，计算 SHA256、变更状态和引用路径，更新来源为 active，并返回 `artifactId`。同一来源、同一指纹重复回传应幂等，不产生重复建议值。

### 5.3 来源和城市状态

来源保留 `error` 与最近失败 artifact，浏览器归档成功后恢复为 `active`。城市汇总新增或计算 `fallbackRequiredCount`，状态按优先级显示为：

```text
部分失败 > 需要浏览器通道 > 正常 > 暂无来源
```

因此“2 个来源成功、4 个来源需浏览器兜底”的城市不能显示为完全正常。

## 6. WorkBuddy 通用规则

`policy-ai-crawler` 对每个城市都执行相同逻辑：

1. 先请求普通 `fetch-requests`。
2. 对 `fallbackAction=browser_search` 的 URL，优先打开原 URL，失败后用“城市 + 政策标题 + 当前年份 + 官方域名”检索。
3. 只接受官方原文、官方镜像或官方 PDF；第三方结果只能作为候选来源，不能直接生成正式建议。
4. 将页面标题、正文、实际 URL、原始 URL、抓取时间和逐字引用回传 `browser-artifacts`。
5. 只把浏览器 artifact 的正文交给 `extraction-submissions`；每条字段保留 quote、单位、置信度和 effectiveDate。
6. 无法获得可靠原文时，提交候选来源并将对应字段放入 `notDisclosed`，任务完成为 `partial_failed`，不猜测、不覆盖旧值。

新增城市的 onboarding、全城市定时任务和单城市手动更新都复用这套循环。Skill 不保存城市专用 URL 规则，也不为城市复制定时任务。

## 7. 安全和数据一致性

- 浏览器回传仍不能写 `scenario_field_values`；所有字段先进入灰色建议值。
- 已有人工填写或人工覆盖的字段不被 AI 或普通正则路径覆盖。
- C6、C7、C8 永远只进入 `notDisclosed`。
- 正文和引用必须保留在本地 artifact 中；搜索摘要不能作为唯一证据。
- 回传接口继续使用 `UE_AGENT_AGENT_TOKEN`；未配置 Token 的本地 Demo 可按现有开发约定运行。
- `finalUrl` 只作为证据地址保存，不能改变已配置来源的城市归属。

## 8. 测试与验收

后端测试覆盖：

- HTTP 412、403、TLS/超时失败时返回结构化浏览器兜底信息。
- 参数错误、SSRF、停用来源不触发兜底。
- 浏览器正文归档、SHA256、变更检测、幂等和任务关联。
- 未授权回传被拒绝；城市/来源不匹配被拒绝。
- 浏览器 artifact 可以继续走 quote、单位、禁估和人工采用校验。

前端测试覆盖：

- 来源列表显示“需浏览器通道”。
- 城市部分失败状态优先于正常状态。
- 任务卡片展示兜底数量和失败原因。

验收条件：成都现有 412 来源触发浏览器兜底；未来新增任意城市只需通过 onboarding 和同一个 Skill 流程即可获得相同能力；普通抓取成功路径、历史数据和人工采用流程不回归。
