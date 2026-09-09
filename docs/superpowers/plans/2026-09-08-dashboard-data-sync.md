# UE-Agent Dashboard 与数据同步实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 UE-Agent 从“单项目 U1 工作台”升级为以全部城市总览为入口、城市项目负责测算、政策资料负责数据维护的决策仪表盘系统。

**Architecture:** 保留现有 U1 确定性计算引擎和项目/场景能力，在 FastAPI 增加结果快照、最新有效场景选择和 Dashboard 聚合服务。Next.js 首页读取聚合接口并展示全局、单城市和多城市对比，城市项目页继续负责参数编辑和运行测算，政策中心负责文件、来源、候选字段和人工审核。

**Tech Stack:** Next.js 16, React 19, Tailwind CSS v4, Tabler Icons, ECharts, FastAPI, Pydantic, Python JSON repository, Vitest, unittest.

## Global Constraints

- 首页 `/` 默认展示全部城市总览，不再展示工作台介绍页。
- 全局每个城市只取按 `calculatedAt` 排序的最新 `calculated` 或 `confirmed` 结果快照。
- 参数修改后未重算的结果标记为 `stale`，不得冒充当前输入结果。
- 结果快照不可变；重新测算必须生成新快照并保留历史结果。
- 未审核政策字段只能作为候选参考，不能参与正式测算或覆盖项目输入。
- 核心财务结果只能由现有确定性 U1 引擎生成。
- 缺失值、真实零值、不适用、过期、待审核和待重算必须区分。
- 继续使用本地 JSON 和本地文件存储完成开发版，不在本计划内接入生产数据库、账号权限或生产部署。
- 保留 `/u1` 和 `/projects/{projectId}/u1` 兼容入口，主导航移除 U1 名称。
- 保留现有按钮 UI 修改，不回退共享 Button、Topbar 和 Tailwind source 扫描改动。
- 不提交、不推送、不部署生产环境，除非用户另行明确授权。

---

## 文件边界

### 后端

- Modify: `services/api/app/repository.py`，保存结果快照、场景状态和政策本地数据。
- Create: `services/api/app/domain/dashboard/models.py`，定义 Dashboard 聚合返回模型。
- Create: `services/api/app/domain/dashboard/aggregator.py`，按城市选择最新有效结果并计算聚合指标。
- Create: `services/api/app/domain/policy/models.py`，定义政策文件、数据源和政策事实模型。
- Create: `services/api/app/domain/policy/service.py`，管理本地上传元数据、解析候选值和审核状态。
- Modify: `services/api/app/api/schemas.py`，增加快照、Dashboard 和政策接口契约。
- Modify: `services/api/app/api/routes.py`，接入 Dashboard、快照和政策 API。
- Modify: `services/api/tests/test_repository.py`，覆盖快照和 stale 状态。
- Create: `services/api/tests/test_dashboard.py`，覆盖最新场景选择和聚合口径。
- Create: `services/api/tests/test_policy.py`，覆盖政策候选值、审核和发布规则。

### 前端

- Modify: `apps/web/package.json`，加入 `echarts`。
- Create: `apps/web/lib/dashboard.ts`，定义 Dashboard 类型和请求函数。
- Create: `apps/web/lib/policies.ts`，定义政策类型和请求函数。
- Create: `apps/web/components/dashboard-filters.tsx`，全局、城市和周期筛选。
- Create: `apps/web/components/dashboard-metric-grid.tsx`，核心指标区域。
- Create: `apps/web/components/dashboard-chart.tsx`，隔离 ECharts 客户端组件。
- Create: `apps/web/components/dashboard-city-comparison.tsx`，城市对比区域。
- Create: `apps/web/components/dashboard-alerts.tsx`，政策、风险、待重算和待确认提醒。
- Create: `apps/web/components/dashboard-overview.tsx`，组合 Dashboard 页面和加载、空、错误状态。
- Modify: `apps/web/app/(workspace)/page.tsx`，替换工作台为总览仪表盘。
- Modify: `apps/web/components/sidebar.tsx`，改为总览、城市项目、政策资料、参数设置。
- Modify: `apps/web/lib/navigation.ts`，更新活动路由判断。
- Modify: `apps/web/app/(workspace)/projects/page.tsx`，展示城市项目和最新结果。
- Create: `apps/web/app/(workspace)/projects/[projectId]/page.tsx`，城市项目配置入口。
- Modify: `apps/web/app/(workspace)/projects/[projectId]/u1/page.tsx`，兼容跳转到城市项目详情。
- Create: `apps/web/components/city-project-workbench.tsx`，参数分组、场景选择和结果快照操作。
- Create: `apps/web/components/policy-overview.tsx`，政策总览和城市筛选。
- Create: `apps/web/components/policy-city-detail.tsx`，单城市政策详情。
- Create: `apps/web/components/policy-upload-panel.tsx`，Word、Excel、PDF 上传入口和状态。
- Create: `apps/web/app/(workspace)/policies/page.tsx`，政策资料总览页。
- Create: `apps/web/app/(workspace)/policies/[cityId]/page.tsx`，城市政策详情页。

### 测试与文档

- Create: `apps/web/lib/dashboard.test.ts`，覆盖请求参数和聚合展示类型。
- Create: `apps/web/components/dashboard-overview.test.tsx`，覆盖全局、单城市和空数据状态。
- Create: `apps/web/components/city-project-workbench.test.tsx`，覆盖 stale、保存和运行测算操作。
- Create: `apps/web/components/policy-overview.test.tsx`，覆盖审核状态展示。
- Modify: `README.md`，更新运行入口和页面说明。
- Modify: `docs/superpowers/specs/2026-09-08-dashboard-and-data-sync-design.md`，只在实现与设计有必要偏差时补充决策记录。

---

## Task 1: 建立结果快照和场景状态基础

**Files:**
- Modify: `services/api/app/repository.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/tests/test_repository.py`
- Modify: `services/api/tests/test_api.py`

**Interfaces:**
- Consumes: Existing project, scenario and `save_calculation` logic.
- Produces: Scenario records with `status`, `result`, `calculatedAt`, `inputSnapshot`, `resultSnapshotId`; a calculation endpoint that creates a new immutable snapshot.

- [ ] **Step 1: Add a failing repository test for snapshot creation**

Test that calculating the same scenario twice creates two snapshots, preserves the earlier snapshot, and updates the scenario pointer to the latest snapshot.

- [ ] **Step 2: Add a failing repository test for stale status**

Test that updating scenario inputs clears the current result pointer and changes status from `calculated` to `stale`, while preserving the historical snapshot.

- [ ] **Step 3: Run the focused repository tests and verify they fail**

Run:

```bash
pnpm api:test -- services/api/tests/test_repository.py
```

Expected: FAIL because snapshots and stale status do not exist in the current repository.

- [ ] **Step 4: Implement snapshot storage with deterministic fields**

Use a generated snapshot ID, the scenario input copy, serialized result copy, model version, UTC `calculatedAt`, and status. Do not mutate historical snapshot dictionaries after saving.

- [ ] **Step 5: Update calculate and scenario update routes**

Save a snapshot after successful or blocked calculation. On input update, mark the scenario stale and preserve previous snapshots.

- [ ] **Step 6: Run repository and API tests**

Run:

```bash
pnpm api:test
```

Expected: all existing tests and new snapshot tests pass.

## Task 2: Implement Dashboard aggregation API

**Files:**
- Create: `services/api/app/domain/dashboard/models.py`
- Create: `services/api/app/domain/dashboard/aggregator.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/api/app/api/routes.py`
- Create: `services/api/tests/test_dashboard.py`

**Interfaces:**
- Consumes: Project records, scenario snapshots, model result fields, and the latest valid scenario rule.
- Produces: `GET /api/dashboard/overview`, `GET /api/dashboard/cities`, `GET /api/dashboard/cities/{cityId}`, `GET /api/dashboard/compare`, `GET /api/dashboard/issues`, and `GET /api/dashboard/policy-summary` response contracts.

- [ ] **Step 1: Write failing tests for latest scenario selection**

Cover these cases:

```python
assert select_latest_valid_snapshot(city).snapshot_id == "newest-calculated"
assert stale_only_city.has_valid_result is False
assert blocked_snapshot.is_excluded is True
```

- [ ] **Step 2: Write failing tests for aggregate metric rules**

Assert that target customers, monthly revenue, monthly net profit, initial investment, and issue counts are summed across eligible cities; payback is returned as a median plus a distribution and is not summed.

- [ ] **Step 3: Write failing API tests for global and city scopes**

Assert that `scope=global` returns one city record per eligible city, `scope=city&cityIds=...` returns the selected city, and `scope=compare&cityIds=a,b` returns only the requested cities.

- [ ] **Step 4: Implement the typed Dashboard models**

Include city identity, scenario metadata, data status, headline metrics, monthly trend series, cost breakdown, comparison rows, and issue summaries. Every numeric field must be nullable when source data is unavailable.

- [ ] **Step 5: Implement server-side aggregation**

Filter snapshots by status, sort by `calculatedAt`, choose one latest valid snapshot per city, aggregate only eligible values, and preserve stale or missing status in the response.

- [ ] **Step 6: Add API query validation and error payloads**

Validate scope, period, city IDs, and `includeStale`. Return a stable empty response for no valid cities instead of failing the entire dashboard.

- [ ] **Step 7: Run Dashboard API tests**

Run:

```bash
pnpm api:test
```

Expected: all API tests pass, including latest-snapshot selection and aggregation rules.

## Task 3: Add frontend Dashboard contracts and charts

**Files:**
- Modify: `apps/web/package.json`
- Create: `apps/web/lib/dashboard.ts`
- Create: `apps/web/components/dashboard-filters.tsx`
- Create: `apps/web/components/dashboard-metric-grid.tsx`
- Create: `apps/web/components/dashboard-chart.tsx`
- Create: `apps/web/components/dashboard-city-comparison.tsx`
- Create: `apps/web/components/dashboard-alerts.tsx`
- Create: `apps/web/components/dashboard-overview.tsx`
- Create: `apps/web/lib/dashboard.test.ts`
- Create: `apps/web/components/dashboard-overview.test.tsx`

**Interfaces:**
- Consumes: Dashboard API response types from Task 2.
- Produces: Reusable client leaves for filters, metrics, line/bar/scatter charts, comparison table, and alerts.

- [ ] **Step 1: Add the ECharts dependency**

Run:

```bash
pnpm --filter @ue-agent/web add echarts
```

Use one isolated `DashboardChart` client component to initialize and dispose an ECharts instance. Do not create chart instances directly in page components.

- [ ] **Step 2: Write failing request contract tests**

Cover `getDashboardOverview({ scope, cityIds, period, includeStale })` URL serialization and `ApiError` behavior.

- [ ] **Step 3: Write failing Dashboard render tests**

Cover:

- global title and city count;
- city selector change callback;
- empty state when no valid city result exists;
- stale city alert;
- policy and issue alert links.

- [ ] **Step 4: Implement Dashboard request types and functions**

Use nullable fields and explicit status types. Keep formatting in `lib/dashboard.ts`, not inside chart components.

- [ ] **Step 5: Implement ECharts line, bar, and scatter configurations**

Use the existing teal and chart tokens. Tooltip values must include units. Charts must show an empty state when series are empty and dispose instances on unmount.

- [ ] **Step 6: Implement global filters and responsive layouts**

Use one filter state for scope, cities, period, and scenario rule. Desktop uses the approved 12-column layout; mobile stacks charts and keeps risk alerts visible.

- [ ] **Step 7: Run focused frontend tests**

Run:

```bash
pnpm --filter @ue-agent/web test -- dashboard
pnpm --filter @ue-agent/web typecheck
```

Expected: all Dashboard tests pass and TypeScript has no errors.

## Task 4: Replace the workbench homepage and update navigation

**Files:**
- Modify: `apps/web/app/(workspace)/page.tsx`
- Modify: `apps/web/components/sidebar.tsx`
- Modify: `apps/web/lib/navigation.ts`
- Modify: `apps/web/components/topbar.tsx`
- Modify: `apps/web/components/app-shell.tsx`
- Modify: `apps/web/app/(workspace)/u1/page.tsx`

**Interfaces:**
- Consumes: `DashboardOverview` from Task 3 and existing app shell.
- Produces: `/` as the global Dashboard, four-item primary navigation, and compatibility redirects for U1 routes.

- [ ] **Step 1: Write failing navigation tests**

Assert that the primary navigation contains 总览、城市项目、政策资料、参数设置 and does not contain 工作台 or U1 城市选址.

- [ ] **Step 2: Replace the workspace home**

Render `DashboardOverview` at `/` with server-loaded initial data or a clear loading state. Do not keep the current marketing-style three-card workbench section.

- [ ] **Step 3: Update sidebar and topbar context**

Use business page names, preserve the shared Button improvements, and keep the topbar actions on one line.

- [ ] **Step 4: Preserve U1 compatibility links**

Keep the old routes functional and make them render or redirect to the relevant city project path without showing U1 in the primary navigation.

- [ ] **Step 5: Run navigation and build checks**

Run:

```bash
pnpm test
pnpm typecheck
pnpm lint
```

Expected: all existing and new tests pass.

## Task 5: Rework the city project experience

**Files:**
- Modify: `apps/web/app/(workspace)/projects/page.tsx`
- Create: `apps/web/app/(workspace)/projects/[projectId]/page.tsx`
- Modify: `apps/web/app/(workspace)/projects/[projectId]/u1/page.tsx`
- Create: `apps/web/components/city-project-workbench.tsx`
- Create: `apps/web/components/city-project-workbench.test.tsx`
- Modify: `apps/web/lib/api.ts`

**Interfaces:**
- Consumes: Existing model spec, project/scenario APIs, snapshot status from Task 1, and Dashboard links from Task 2.
- Produces: City project list, scenario tabs or selector, grouped parameter editor, save draft, run calculation, copy scenario, confirm result, and snapshot history.

- [ ] **Step 1: Write failing city project tests**

Cover grouped sections, `stale` status after input change, save feedback, calculation loading state, blocked calculation issues, and a link back to the Dashboard.

- [ ] **Step 2: Add typed snapshot and scenario status support to `apps/web/lib/api.ts`**

Keep existing U1 fields and add explicit `calculatedAt`, `snapshotId`, `inputSnapshot`, and `status` fields without breaking old fixture data.

- [ ] **Step 3: Implement the project list summary**

Show one latest result row per city project and distinguish no result, stale result, calculated result, confirmed result, and failed result.

- [ ] **Step 4: Implement grouped parameter editing**

Reuse existing `U1ParameterField`, preserve formula fields as read-only, keep source metadata visible, and use collapsible business groups instead of a single long page.

- [ ] **Step 5: Implement scenario and snapshot actions**

Add save draft, run calculation, copy scenario, confirm result, and view historical snapshots. Every action must show loading, success, error, and stale transitions.

- [ ] **Step 6: Run project UI tests**

Run:

```bash
pnpm --filter @ue-agent/web test -- city-project
pnpm typecheck
```

Expected: all project UI tests and type checks pass.

## Task 6: Implement policy center backend and local file workflow

**Files:**
- Create: `services/api/app/domain/policy/models.py`
- Create: `services/api/app/domain/policy/service.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/app/repository.py`
- Create: `services/api/tests/test_policy.py`

**Interfaces:**
- Consumes: City identifiers and local project repository.
- Produces: Policy overview, city detail, data source configuration, local upload metadata, extraction candidates, review, approve, reject, and policy summary endpoints.

- [ ] **Step 1: Write failing policy state tests**

Assert that uploaded files enter `uploaded`, parsing enters `parsing`, extracted fields enter `review_pending`, rejected fields do not enter Dashboard output, and approved fields do.

- [ ] **Step 2: Implement policy records and local file metadata**

Store file name, MIME type, size, SHA-256 hash, city ID, source, upload time, and status. Store files only under a narrow project data directory, never in the repository root.

- [ ] **Step 3: Implement source and document endpoints**

Add list/create/update endpoints for data sources and policy documents. Do not implement unattended crawling in this task.

- [ ] **Step 4: Implement candidate extraction contract**

For the local MVP, accept explicit candidate fields and preserve the original document reference. Do not invent policy values or auto-approve extracted values.

- [ ] **Step 5: Implement review and approval endpoints**

Approval must store reviewer, review time, source and effective date. Only approved `PolicyFact` records can appear in Dashboard policy summary or become project reference values.

- [ ] **Step 6: Run policy API tests**

Run:

```bash
pnpm api:test
```

Expected: all policy state and existing API tests pass.

## Task 7: Implement policy center frontend

**Files:**
- Create: `apps/web/lib/policies.ts`
- Create: `apps/web/components/policy-overview.tsx`
- Create: `apps/web/components/policy-city-detail.tsx`
- Create: `apps/web/components/policy-upload-panel.tsx`
- Create: `apps/web/components/policy-overview.test.tsx`
- Create: `apps/web/app/(workspace)/policies/page.tsx`
- Create: `apps/web/app/(workspace)/policies/[cityId]/page.tsx`

**Interfaces:**
- Consumes: Policy API contracts and Dashboard policy summary from Task 6.
- Produces: Global policy overview, city policy detail, upload panel, candidate field review, source status, and links back to affected projects.

- [ ] **Step 1: Write failing policy UI tests**

Cover global city filter, empty state, uploaded/review/approved badges, candidate field review, and no direct overwrite of project values.

- [ ] **Step 2: Implement policy overview**

Show city policy completeness, latest update, pending review count, source status and affected project count.

- [ ] **Step 3: Implement city policy detail**

Show source documents, structured fields, version history and links to project parameters that can consume approved references.

- [ ] **Step 4: Implement file upload and review panel**

Support Word, Excel and PDF file selection, upload status, candidate fields, approve/reject actions and clear pending review labels. Do not send sensitive personal data to third-party services.

- [ ] **Step 5: Run policy UI tests**

Run:

```bash
pnpm --filter @ue-agent/web test -- policy
pnpm typecheck
pnpm lint
```

Expected: all policy UI tests and checks pass.

## Task 8: Full integration verification and handoff

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-08-dashboard-and-data-sync-design.md` only for verified implementation notes.

**Interfaces:**
- Consumes: All completed Dashboard, project, snapshot and policy modules.
- Produces: A locally runnable integrated version with documented routes and verification evidence.

- [ ] **Step 1: Run the complete automated suite**

Run:

```bash
pnpm test
pnpm model:test
pnpm api:test
pnpm typecheck
pnpm lint
pnpm build
```

Expected: every command exits with code 0.

- [ ] **Step 2: Run the local smoke flow**

Start:

```bash
pnpm api:dev
pnpm dev
```

Verify in the browser:

1. `/` opens the global Dashboard.
2. Global scope lists all cities with valid snapshots.
3. City scope filters to one city.
4. A scenario input edit changes status to stale.
5. Running calculation creates a new result visible in the Dashboard.
6. Policy upload shows review pending.
7. Approving a policy fact changes the policy summary but does not silently overwrite an existing project value.
8. `/u1` remains a compatible entry path and does not appear in the main navigation.

- [ ] **Step 3: Run repository hygiene checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors, no personal data or uploaded source files committed, no production deployment, and no push performed.

- [ ] **Step 4: Report final evidence**

Report changed modules, test commands and exit statuses, local URLs, known business-confirmation issues, and any intentionally deferred production work. Do not claim completion if any required check fails.
