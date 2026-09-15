# 新增城市自动入场 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增城市后自动发现公开来源、抓取政策原文、解析自动爬虫字段并把灰色建议值同步到城市测算页。

**Architecture:** 在现有 FastAPI + SQLite + Next.js 架构上增加 `CityOnboardingService` 和可替换 `SourceDiscoveryProvider`。项目创建后创建可恢复的 SQLite 任务，后台按查询族发现来源，官方来源自动入池并抓取，其他来源进入候选；后续复用现有原文存档、解析、WorkBuddy 校验和建议值机制。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLite、httpx、Next.js 16、React 19、TypeScript、Vitest、Python unittest。

## Global Constraints

- Demo 不增加登录、权限和生产部署。
- SQLite 是默认持久化介质，任务状态必须可恢复。
- 官方高可信来源自动入正式来源；其他来源只入候选。
- C6、C7、C8 永远不生成估算建议。
- 灰色建议值不得覆盖当前输入、人工覆盖值或已采用值。
- 不为任何具体城市编写代码分支。
- 不提交、不推送、不创建分支或 worktree。

---

### Task 1: 锁定自动入场任务与发现规则的红测

**Files:**
- Create: `services/api/tests/test_city_onboarding.py`
- Modify: `services/api/tests/test_api.py`
- Modify: `services/api/tests/test_sqlite_repository.py`

**Interfaces:**
- Consumes: `ProjectRepository`、`AgentSubmissionService`、`FIELD_FAMILIES`。
- Produces: 明确的任务状态、来源分流、URL 去重和错误容错行为。

- [x] **Step 1: Write the failing tests**

```python
def test_discovery_classifies_official_sources_and_keeps_other_sources_as_candidates(self):
    provider = StaticDiscoveryProvider([
        {"url": "https://ybj.chengdu.gov.cn/policy", "title": "成都医保局长护险办法"},
        {"url": "https://example.com/chengdu-care", "title": "成都养老政策整理"},
    ])
    result = CityOnboardingService(self.repository, discovery_provider=provider).run_for_project(self.project_id)
    self.assertEqual(result["officialSourceCount"], 1)
    self.assertEqual(result["candidateCount"], 1)
    self.assertEqual(len(self.repository.list_data_sources(city_id="chengdu")), 1)
    self.assertEqual(len(self.repository.list_candidate_sources(city_id="chengdu")), 1)

def test_running_city_onboarding_is_reused_instead_of_started_twice(self):
    first = CityOnboardingService(self.repository).start(self.project_id)
    second = CityOnboardingService(self.repository).start(self.project_id)
    self.assertEqual(first["id"], second["id"])

def test_failed_source_does_not_stop_other_sources(self):
    provider = StaticDiscoveryProvider([
        {"url": "https://good.example/policy", "title": "可抓取政策"},
        {"url": "https://bad.example/policy", "title": "不可抓取政策"},
    ])
    result = CityOnboardingService(self.repository, discovery_provider=provider).run_for_project(self.project_id)
    self.assertEqual(result["status"], "partial_failed")
    self.assertEqual(result["errorCount"], 1)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_city_onboarding.py -v`

Expected: FAIL because the onboarding service, provider and repository job methods do not exist.

- [x] **Step 3: Add only the test fixtures and public types needed by the tests**

Define a test-local `StaticDiscoveryProvider` and keep the expected provider contract explicit:

```python
class StaticDiscoveryProvider:
    def __init__(self, results):
        self.results = results

    def discover(self, city_name, field_families):
        return self.results
```

- [x] **Step 4: Run the tests again and confirm the failure is still about missing production behavior**

Run the same unittest command. Expected: the fixture imports succeed, while the missing service/repository behavior remains the only failure.

### Task 2: Add persistent onboarding jobs to both repositories

**Files:**
- Create: `services/api/migrations/sqlite/005_city_onboarding.sql`
- Modify: `services/api/app/repository.py`
- Modify: `services/api/app/sqlite_repository.py`
- Modify: `services/api/app/repository.py` JSON implementation
- Test: `services/api/tests/test_sqlite_repository.py`

**Interfaces:**
- Produces:
- `create_onboarding_job(data: Mapping[str, Any]) -> dict[str, Any]`
- `get_onboarding_job(job_id: str) -> dict[str, Any]`
- `get_active_onboarding_job(project_id: str) -> dict[str, Any] | None`
- `list_onboarding_jobs(project_id: str | None = None) -> list[dict[str, Any]]`
- `update_onboarding_job(job_id: str, data: Mapping[str, Any]) -> dict[str, Any]`

- [x] **Step 1: Write a failing SQLite persistence test**

```python
def test_onboarding_job_survives_repository_reload(self):
    job = self.repository.create_onboarding_job({
        "projectId": self.project_id, "cityId": "chengdu", "cityName": "成都",
        "status": "queued", "phase": "queued",
    })
    updated = self.repository.update_onboarding_job(job["id"], {
        "status": "completed", "phase": "completed", "suggestionCount": 4,
    })
    self.assertEqual(updated["suggestionCount"], 4)
    reloaded = SQLiteProjectRepository(self.db_path)
    self.assertEqual(reloaded.get_onboarding_job(job["id"])["status"], "completed")
```

- [x] **Step 2: Run the focused test and verify it fails**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_sqlite_repository.py -v`

Expected: FAIL with a missing repository method or missing table.

- [x] **Step 3: Add migration and repository mapping**

Create the migration with the fields in the design spec. Map SQLite snake_case columns to API camelCase in `_onboarding_job_dict`, serialize `errors` as JSON, and update only allow-listed columns. The JSON repository should store jobs in a top-level `onboardingJobs` list using the same camelCase result shape.

- [x] **Step 4: Run the focused repository tests**

Run the same unittest command. Expected: all repository tests pass, including a fresh-instance reload.

### Task 3: Implement source discovery, trust classification and onboarding orchestration

**Files:**
- Create: `services/api/app/domain/policy/discovery.py`
- Create: `services/api/app/domain/policy/onboarding_service.py`
- Modify: `services/api/app/domain/policy/__init__.py`
- Modify: `services/api/app/domain/policy/agent_service.py`
- Modify: `services/api/app/domain/policy/service.py`
- Test: `services/api/tests/test_city_onboarding.py`

**Interfaces:**
- `SourceDiscoveryProvider.discover(city_name: str, field_families: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]`
- `classify_source(url: str, title: str | None) -> Literal["official", "candidate", "rejected"]`
- `CityOnboardingService.start(project_id: str) -> dict[str, Any]`
- `CityOnboardingService.run(job_id: str) -> dict[str, Any]`
- `CityOnboardingService.run_for_project(project_id: str) -> dict[str, Any]`
- `CityOnboardingService.get_status(project_id: str) -> dict[str, Any]`

- [x] **Step 1: Add failing classification and parser integration tests**

```python
def test_classify_source_prefers_government_and_bureau_domains(self):
    self.assertEqual(classify_source("https://ybj.chengdu.gov.cn/a", "医保局政策"), "official")
    self.assertEqual(classify_source("https://www.chengdu.gov.cn/a", "政府公开信息"), "official")
    self.assertEqual(classify_source("https://example.com/a", "政策整理"), "candidate")
    self.assertEqual(classify_source("javascript:alert(1)", "bad"), "rejected")

def test_onboarding_writes_suggestions_without_overwriting_current_inputs(self):
    result = CityOnboardingService(self.repository, discovery_provider=StaticDiscoveryProvider([
        {"url": "https://ybj.chengdu.gov.cn/policy", "title": "长护险政策"},
    ])).run_for_project(self.project_id)
    values = self.repository.list_field_values(self.scenario_id)
    self.assertEqual(result["suggestionCount"], 17)
    self.assertEqual(next(row for row in values if row["fieldId"] == "P1")["valueState"], "suggestion_ready")
```

- [x] **Step 2: Run the tests to verify the new behavior fails**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_city_onboarding.py -v`

Expected: FAIL because discovery classification and onboarding orchestration are not implemented.

- [x] **Step 3: Implement the provider contract and generic source rules**

Implement `WebSearchDiscoveryProvider` with a configurable `UE_AGENT_DISCOVERY_SEARCH_URL` template. It must URL-encode each query, parse only `http`/`https` result URLs, cap results per query, and return title, URL, query family and relevance. Implement `classify_source` with official suffix/domain markers (`gov.cn`, government/医保/统计/民政 domain tokens) and candidate fallback; never make city-specific branches.

- [x] **Step 4: Implement the orchestration state machine**

The service must update the job before and after each phase, deduplicate same-city URLs, create official `DataSource` records, create candidate records for other results, call the existing crawl method for official sources, parse the saved artifact through the existing deterministic parser, and write gray suggestions only when the field row is not `accepted` or `overridden`. Catch one-source errors into `errors` and continue.

- [x] **Step 5: Run onboarding tests and the existing policy tests**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_city_onboarding.py services/api/tests/test_policy.py services/api/tests/test_crawler.py -v`

Expected: PASS; existing parser and no-overwrite behavior remain green.

### Task 4: Trigger onboarding from project creation and expose status APIs

**Files:**
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/api/tests/test_api.py`
- Modify: `services/api/tests/test_crawl_api.py`

**Interfaces:**
- `POST /api/projects` returns `{project, onboarding}` without removing existing project fields.
- `GET /api/projects/{project_id}/onboarding` returns the latest job.
- `POST /api/projects/{project_id}/onboarding/retry` returns the restarted job.

- [x] **Step 1: Write failing API tests**

```python
def test_create_project_returns_onboarding_job(self):
    response = self.client.post("/api/projects", json={"name": "成都测算", "city": "成都"})
    self.assertEqual(response.status_code, 201)
    body = response.json()
    self.assertIn("onboarding", body)
    self.assertEqual(body["onboarding"]["status"], "queued")

def test_onboarding_status_is_readable_after_project_creation(self):
    created = self.client.post("/api/projects", json={"name": "成都测算", "city": "成都"}).json()
    response = self.client.get(f"/api/projects/{created['project']['id']}/onboarding")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["projectId"], created["project"]["id"])
```

- [x] **Step 2: Run the API tests and verify they fail**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_api.py -v`

Expected: FAIL because the current create response is only the project and the status routes do not exist.

- [x] **Step 3: Add the response schema and background trigger**

Keep the existing client compatibility by returning the created project fields at the top level and also adding `project` and `onboarding` keys; update the typed frontend wrapper to read `body.project`. Use FastAPI `BackgroundTasks` to call `CityOnboardingService.run` after the response is prepared. If a provider is not configured, create a job and mark it `partial_failed` with a readable configuration message rather than raising a 500.

- [x] **Step 4: Add status and retry routes with idempotency**

The status route returns 404 for an unknown project. Retry is allowed for `failed` and `partial_failed`, reuses existing URLs, resets counters/errors, and never creates two active jobs. It does not delete historical artifacts.

- [x] **Step 5: Run API regression tests**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_api.py services/api/tests/test_crawl_api.py services/api/tests/test_city_onboarding.py -v`

Expected: PASS.

### Task 5: Update frontend creation flow and city progress UI

**Files:**
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/city-project-workbench.tsx`
- Modify: `apps/web/app/(workspace)/projects/new/page.tsx`
- Create: `apps/web/components/city-onboarding-status.tsx`
- Create: `apps/web/components/city-onboarding-status.test.tsx`

**Interfaces:**
- `createProject` understands the new response and returns `{ project, onboarding }` while preserving existing callers.
- `getCityOnboarding(projectId: string)` returns the job status.
- `CityOnboardingStatus` renders queued/running/completed/partial-failed states and counts.

- [x] **Step 1: Write the failing component tests**

```tsx
it("shows source discovery progress and suggestion count", () => {
  render(<CityOnboardingStatus projectId="project-1" initialJob={{
    id: "job-1", projectId: "project-1", cityId: "chengdu", cityName: "成都",
    status: "crawling", phase: "crawling", discoveredCount: 4,
    officialSourceCount: 2, candidateCount: 2, crawledCount: 1,
    suggestionCount: 0, errorCount: 0, errors: [],
  }} />);
  expect(screen.getByText(/正在抓取成都/)).toBeInTheDocument();
  expect(screen.getByText(/已发现 4 个来源/)).toBeInTheDocument();
});

it("explains partial failure without blocking measurement", () => {
  render(<CityOnboardingStatus projectId="project-1" initialJob={{
    ...completedFixture, status: "partial_failed", errorCount: 1,
    errors: ["统计局来源暂时不可达"],
  }} />);
  expect(screen.getByText(/部分完成/)).toBeInTheDocument();
  expect(screen.getByText(/仍可继续填写和运行测算/)).toBeInTheDocument();
});
```

- [x] **Step 2: Run the component test and verify it fails**

Run: `pnpm --filter @ue-agent/web test -- city-onboarding-status.test.tsx`

Expected: FAIL because the status component and API wrapper do not exist.

- [x] **Step 3: Add typed API wrappers and the status component**

Use the existing `apiFetch` helper. Poll only while status is active, stop after completed/failed/partial_failed, and show a “重新尝试” action for failed states. Do not put provider secrets or raw policy text in the browser state.

- [x] **Step 4: Connect the create page and city workbench**

After successful creation, route to `/projects/{projectId}` and pass no city-specific configuration. The workbench reads the project ID and renders the onboarding status above the parameter card. Existing manual editing, gray suggestion adoption and calculation actions remain available while onboarding runs.

- [x] **Step 5: Run frontend tests and typecheck**

Run: `pnpm --filter @ue-agent/web test && pnpm typecheck`

Expected: all existing tests plus the onboarding component tests pass.

### Task 6: Add end-to-end coverage and documentation

**Files:**
- Modify: `services/api/scripts/e2e_fixture_server.py`
- Modify: `scripts/e2e-agent-flow.sh`
- Modify: `scripts/e2e_assert.py`
- Modify: `README.md`
- Modify: `services/api/README.md`
- Test: `services/api/tests/test_documentation_contract.py`

**Interfaces:**
- E2E covers create → onboarding → official source → artifact → suggestion → dashboard.
- Documentation explains provider configuration, fallback behavior and no-production scope.

- [x] **Step 1: Add a failing E2E assertion for automatic onboarding**

```bash
run_step "自动新增城市入场" \
  "$BASE_URL/api/projects" \
  '{"name":"成都自动入场","city":"成都"}'
assert_json '.onboarding.status == "queued"'
assert_json '.project.city == "成都"'
```

- [x] **Step 2: Run E2E and verify the new assertion fails before wiring is complete**

Run: `bash scripts/e2e-agent-flow.sh`

Expected during the red phase: the current response lacks the onboarding envelope. After implementation, the same command must finish with exit code 0.

- [x] **Step 3: Extend the fixture provider and assertions**

Make the fixture discovery endpoint return official and candidate URLs for arbitrary city names, not a Chengdu-specific branch. Assert same-city duplicate URLs are not duplicated, one failed source does not stop another, and accepted suggestions remain gray before adoption.

- [x] **Step 4: Update local setup documentation**

Document `UE_AGENT_DISCOVERY_SEARCH_URL`, optional AI provider configuration, the job status meanings, the official-domain rule, and the local-only demo boundary. State that without a provider the city can still be edited manually and the job exposes a retry/configuration message.

- [x] **Step 5: Run the complete verification suite**

Run:

```bash
git diff --check
pnpm --recursive test
pnpm api:test
pnpm lint
pnpm typecheck
pnpm build
bash scripts/e2e-agent-flow.sh
```

Expected: all commands exit 0; no production deployment, commit or push is performed.
