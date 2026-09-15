# UE-Agent Demo 收口 Implementation Plan

> **For agentic workers:** This plan is executed inline in the current workspace. Production deployment, authentication, and permission systems are explicitly out of scope.

**Goal:** 完成公开 Demo 的政策官网抓取闭环、75 字段来源口径、文档同步和本地可验收运行，使城市参数建议值可以从已保存的官网原文进入测算页面。

**Architecture:** 保留现有 Next.js + FastAPI + SQLite + Python crawler 架构。政策来源由用户配置，Python 抓取器保存原文并计算指纹；确定性字段解析生成灰色建议值，建议值仍需用户在城市测算页点击“采用”后才进入当前参数。WorkBuddy 回传接口继续作为可选的高阶 AI 入口，不改变 Demo 的安全边界。

**Tech Stack:** Next.js 16、React 19、TypeScript、Tailwind CSS v4、Recharts、FastAPI、Pydantic、SQLite、httpx、Python unittest、Vitest。

## Global Constraints

- Demo 不提供登录、权限和生产部署；所有查看、编辑和抓取操作保持公开。
- Demo 不提供政策文件手动上传；政策原文必须由配置的公开官网来源抓取产生。
- 自动爬虫建议值以灰色提示展示，未点击“采用建议值”不得覆盖当前参数或参与计算。
- 公式自动字段保持只读；内部填写字段允许填写或留空。
- C6、C7、C8 无官方公开数据时必须返回未披露，不得由规则或 AI 估算。
- 75 个字段、Excel 单元格、公式和待确认问题以 `packages/model-spec/` 为唯一模型契约。
- 本次不提交、不推送、不创建分支，保留工作区已有改动。

---

### Task 1: 先锁定政策解析和模型口径测试

**Files:**
- Modify: `services/api/tests/test_crawl_api.py`
- Modify: `services/api/tests/test_crawler.py`
- Modify: `apps/web/components/policy-overview.test.tsx`
- Modify: `apps/web/components/policy-ai-crawl-sections.test.tsx`

**Interfaces:**
- Consumes: 现有 `PolicyService.crawl_source_now`、`parse_suggestions`、`PolicyOverview`、`PolicyCityDetail`。
- Produces: 可验证的 20 个自动爬虫字段覆盖、无手动上传文案、官网抓取导出的用户提示。

- [x] **Step 1: 写 Python 解析红测**

```python
def test_parser_extracts_supported_policy_and_city_fields(self):
    text = (
        "长沙市为新一线城市；常住人口 499.14 万人；60岁以上人口占比 20.58%；"
        "80岁以上人口占比 3.2%；职工医保参保人数 210 万人；医保基金净结余 12.6 亿元；"
        "区域总面积 11819 平方公里；单小时服务单价 66 元；基金支付比例 80%；"
        "最低护理员纳保数 20 人；最低护士配置数 2 人；失能状态持续时长要求 6 个月；"
        "评估通过率门槛 70%；单次服务时长 2 小时；每月必选服务项数 3 项；"
        "辅具政策纳入试点，支持亲情照护模式。"
    )
    result = {item["fieldId"]: item["value"] for item in parse_suggestions(text)}
    self.assertEqual(result["C2"], "新一线")
    self.assertEqual(result["C3"], 499.14)
    self.assertEqual(result["C4"], 0.2058)
    self.assertEqual(result["C5"], 0.032)
    self.assertEqual(result["C10"], 210)
    self.assertEqual(result["C11"], 12.6)
    self.assertEqual(result["C13"], 11819)
    self.assertEqual(result["P4"], 20)
    self.assertEqual(result["P5"], 2)
    self.assertEqual(result["P6"], 6)
    self.assertEqual(result["P7"], 0.7)
    self.assertEqual(result["P9"], 3)
    self.assertEqual(result["P10"], "是")
    self.assertEqual(result["P11"], "是")
```

- [x] **Step 2: 运行红测**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_crawl_api.py -v`

Expected: FAIL，因为 `parse_suggestions` 当前只有 P1、P2、P8 三条规则。

- [x] **Step 3: 写前端文案红测**

把 `apps/web/components/policy-overview.test.tsx` 的旧“上传/审核”断言改成：

```tsx
expect(screen.getByText(/官网来源/)).toBeInTheDocument();
expect(screen.getByText(/配置公开官网链接/)).toBeInTheDocument();
expect(screen.queryByText(/上传城市政策/)).toBeNull();
```

- [x] **Step 4: 运行前端红测**

Run: `pnpm --filter @ue-agent/web test -- policy-overview.test.tsx`

Expected: FAIL，因为页面仍有旧政策上传和人工审核描述。

---

### Task 2: 扩展确定性政策解析，并保持建议值不静默覆盖

**Files:**
- Modify: `services/api/app/domain/policy/service.py:28-52`
- Modify: `services/api/tests/test_crawl_api.py`
- Modify: `services/api/tests/test_crawler.py`

**Interfaces:**
- Consumes: `extract_readable_text` 输出的纯文本和 `packages/model-spec/parameters/u1.parameters.json` 的字段语义。
- Produces: `parse_suggestions(text) -> list[dict[str, Any]]`，覆盖可明确从正文读取的 C2/C3/C4/C5/C10/C11/C13/P1/P2/P4/P5/P6/P7/P8/P9/P10/P11；C6/C7/C8 永不生成建议。

- [x] **Step 1: 保留红测并补边界测**

```python
def test_parser_does_not_estimate_disability_rate_fields(self):
    result = parse_suggestions("失能率_60-69岁约 12%，失能率_70-79岁约 18%，失能率_80岁以上约 25%。")
    self.assertNotIn("C6", {item["fieldId"] for item in result})
    self.assertNotIn("C7", {item["fieldId"] for item in result})
    self.assertNotIn("C8", {item["fieldId"] for item in result})

def test_parser_converts_percent_to_decimal_and_keeps_quotes(self):
    result = parse_suggestions("基金支付比例为 80%，评估通过率门槛为 70%。")
    by_id = {item["fieldId"]: item for item in result}
    self.assertEqual(by_id["P2"]["value"], 0.8)
    self.assertEqual(by_id["P7"]["value"], 0.7)
    self.assertIn("80%", by_id["P2"]["quote"])
```

- [x] **Step 2: 运行边界红测**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_crawl_api.py -v`

Expected: FAIL only for the newly required fields.

- [x] **Step 3: 实现最小解析器**

在 `service.py` 中使用按字段排列的正则规则；每条规则只接受带有明确字段标签的文本窗口，百分比字段统一除以 100，枚举字段只返回 `是/否` 或模型字典允许的城市等级。规则结果统一返回 `fieldId`、`name`、`value`、`quote`，不处理 C6/C7/C8，不覆盖已有建议值。

- [x] **Step 4: 运行绿色测试和全 API 测试**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_crawl_api.py services/api/tests/test_crawler.py -v`

Expected: 所有测试通过，已有的“AI 建议值优先、正则不覆盖”回归测试保持通过。

---

### Task 3: 收口政策页面为“官网抓取中心”

**Files:**
- Modify: `apps/web/components/policy-overview.tsx`
- Modify: `apps/web/components/policy-city-detail.tsx`
- Modify: `apps/web/components/policy-ai-crawl-sections.tsx`
- Modify: `apps/web/lib/policies.ts`
- Modify: `apps/web/components/policy-overview.test.tsx`
- Modify: `apps/web/components/policy-ai-crawl-sections.test.tsx`

**Interfaces:**
- Consumes: 来源 CRUD、单个/全部抓取、来源新鲜度、抓取产物、灰色建议值和 WorkBuddy 审计接口。
- Produces: 页面只引导配置公开来源和抓取；旧 PolicyDocument 手动上传入口不再出现在界面；建议值与原文来源可回溯。

- [x] **Step 1: 更新页面红测断言**

```tsx
expect(screen.getByText(/配置公开官网来源并一键抓取/)).toBeInTheDocument();
expect(screen.getByText(/抓取原文会保存到本地/)).toBeInTheDocument();
expect(screen.queryByText(/上传城市政策 Word/)).toBeNull();
```

- [x] **Step 2: 运行前端红测**

Run: `pnpm --filter @ue-agent/web test -- policy-overview.test.tsx policy-ai-crawl-sections.test.tsx`

Expected: FAIL on old copy and old policy-count labels.

- [x] **Step 3: 修改页面文案和类型**

将总览指标从“待审核/已确认”改为“已配置来源/正常来源/抓取记录/建议值待采用”等实际抓取指标；城市详情保留来源、全部抓取、单条抓取、历史和导出入口。WorkBuddy 候选来源区块改成“AI 发现的待确认来源”，明确它是可选增强能力，不把它描述为手动上传审核流程。

- [x] **Step 4: 运行前端绿色测试**

Run: `pnpm --filter @ue-agent/web test -- policy-overview.test.tsx policy-ai-crawl-sections.test.tsx`

Expected: PASS。

---

### Task 4: 同步模型口径、README、API 文档和 PRD

**Files:**
- Modify: `README.md`
- Modify: `services/api/README.md`
- Modify: `packages/model-spec/README.md`
- Modify: `docs/product/UE-Agent-产品需求文档-v1.0.md`
- Modify: `docs/superpowers/specs/2026-09-10-policy-ai-crawl-design.md`
- Modify: `docs/product/需求待办-2026-09-10-B12默认常量5000.md`
- Modify: `docs/product/需求待办-2026-09-10-删除功能与总览改版.md`

**Interfaces:**
- Consumes: 实际 SQLite 启动方式、当前 API 路由和 `packages/model-spec` 字段/公式契约。
- Produces: 文档不再声称手动上传是当前能力，不再把 JSON 当作默认存储；明确 75 字段来源统计和 S3/S5 的业务修正状态。

- [x] **Step 1: 写文档一致性检查脚本/测试**

在 `services/api/tests/test_documentation_contract.py` 增加只读检查：README 和 API README 必须包含 SQLite、`pnpm bootstrap`、`crawl-all`；不得包含“当前版本支持 Word/Excel/PDF 本地上传”或“默认写入 projects.json”；PRD 必须包含“Demo 不提供政策文件手动上传接口”。

- [x] **Step 2: 运行红测**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_documentation_contract.py -v`

Expected: FAIL，因为 README 和 API README 仍存在旧描述。

- [x] **Step 3: 按实际代码更新文档**

README 说明四个主页面、公开 Demo、本地 SQLite、政策官网来源抓取、原文落档、CSV/ZIP 导出和建议值采用规则。API README 改成 `uvicorn app.main:app` + SQLite 数据目录说明。PRD 统一标题为 v1.1 Demo 基线；模型字典注明原 Excel 的“暗访实地/市场调研”被产品口径统一归为内部填写；S3/S5 明确为业务修正公式。

- [x] **Step 4: 运行文档绿色测试**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_documentation_contract.py -v`

Expected: PASS。

---

### Task 5: 补本地真实链路验收

**Files:**
- Modify: `scripts/e2e-agent-flow.sh`
- Modify: `services/api/scripts/e2e_fixture_server.py`
- Modify: `scripts/e2e_assert.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: FastAPI 统一 `/api` 路由、SQLite 数据目录、假政策页和 crawler/WorkBuddy 接口。
- Produces: 一条可重复执行的本地验收命令，覆盖建城市、来源配置、全部抓取、原文存储、建议值、采用前不入当前值、导出和城市总览读取。

- [x] **Step 1: 为直接抓取链路写失败断言**

验收脚本新增：调用 `/api/policies/cities/{cityId}/crawl-all` 后检查成功/失败/未变统计；读取 artifact content；读取 `/api/cities/{cityId}/values` 检查 P1/P2/P4/P5/P6/P7/P8/P9/P10/P11/C2/C3/C4/C5/C10/C11/C13 建议值；确认 scenario 的当前输入仍未被建议值静默覆盖；最后请求 `/api/dashboard/overview` 确认城市仍可被总览读取。

- [x] **Step 2: 运行验收红测**

Run: `bash scripts/e2e-agent-flow.sh`

Expected: 当前脚本会因新增字段建议值或导出断言缺失而失败。

- [x] **Step 3: 补夹具和断言**

夹具页面提供全部可解析字段的明确标签和单位；断言脚本按 JSON 字段读取结果，不使用易受 shell 引号影响的文本匹配。测试数据放在 `/tmp/ue-e2e-data`，脚本退出时清理，不触碰仓库 `services/api/data/`。

- [x] **Step 4: 运行验收绿色测试**

Run: `bash scripts/e2e-agent-flow.sh`

Expected: 输出健康检查、来源抓取、建议值数量、未覆盖当前输入和总览读取均成功，退出码为 0。

---

### Task 6: 最终工程验证

**Files:**
- No production code changes; inspect all files changed by Tasks 1–5.

**Interfaces:**
- Consumes: 全部测试、lint、typecheck、build、E2E 和 Git diff。
- Produces: 可交接的本地 Demo 代码状态和明确的未提交清单。

- [x] **Step 1: 运行前端测试**

Run: `pnpm --recursive test`

Expected: 所有 Vitest 测试通过。

- [x] **Step 2: 运行 API 测试**

Run: `pnpm api:test`

Expected: 所有 Python unittest 通过。

- [x] **Step 3: 运行质量检查**

Run: `pnpm lint && pnpm typecheck && pnpm build`

Expected: 三条命令均退出 0，Next.js 生产构建成功。

- [x] **Step 4: 检查差异和文档禁用词**

Run: `git diff --check && git status --short && rg -n "当前版本支持.*上传|默认写入.*projects\\.json|上传城市政策" README.md services/api/README.md docs/product apps/web || true`

Expected: `git diff --check` 通过；只保留用户明确要求的旧兼容接口说明，不出现当前页面仍支持手动上传的误导描述；不提交、不推送。
