# Policy Realtime WorkBuddy Research Implementation Plan

> **For agentic workers:** Follow this plan task by task and keep the checkbox status updated as work progresses.

**Goal:** Add a unified on-demand policy research run so both the frontend button and WorkBuddy conversation can search current city policies, preserve evidence, and produce reviewable parameter suggestions.

**Architecture:** The API owns research-run state, task briefs, raw artifact storage, validation, and SQLite persistence. WorkBuddy owns web search and document understanding through the existing `crawl-targets`, `fetch-requests`, `source-candidates`, and `extraction-submissions` contracts. The frontend creates and polls a run; if WorkBuddy cannot be invoked programmatically, it shows a copyable task prompt without pretending the run has executed.

**Tech Stack:** FastAPI, Pydantic, SQLite migrations, existing `ProjectRepository`/`SqliteProjectRepository`, WorkBuddy Markdown skill, Next.js/React, TypeScript, Vitest, Python `unittest`, shell E2E fixture.

## Global Constraints

- “实时” means user-triggered current web search; no policy freshness guarantee is claimed and no P0 scheduler is added.
- AI never writes final measurement inputs directly; it only creates gray suggestions that require human adoption.
- C6, C7, and C8 must be returned as `notDisclosed` and can never be estimated.
- WorkBuddy callbacks must continue to honor `UE_AGENT_AGENT_TOKEN` when configured.
- API download remains the only raw-page ingestion path so SSRF protection, SHA256 change detection, and local artifact storage remain intact.
- Do not break existing `crawl-targets`, `fetch-requests`, `extraction-submissions`, `source-candidates`, or current city onboarding behavior.
- Do not create a branch, worktree, commit, push, login flow, or production deployment as part of implementation.

## File Map

- Create `services/api/migrations/sqlite/006_policy_research_runs.sql` for run/query tables and indexes.
- Create `services/api/migrations/sqlite/007_policy_research_correlation.sql` and `008_artifact_research_correlation.sql` for callback/artifact task linkage.
- Modify `services/api/app/repository.py` and `services/api/app/sqlite_repository.py` for JSON/SQLite run persistence.
- Modify `services/api/app/api/schemas.py` for typed run creation, result, and completion payloads.
- Create `services/api/app/domain/policy/research_service.py` for run lifecycle, dynamic brief generation, idempotency, and prompt creation.
- Modify `services/api/app/api/routes.py` to expose run endpoints and correlate existing WorkBuddy callbacks.
- Create `services/api/tests/test_policy_research.py` for domain/API coverage alongside the existing API suite.
- Modify `.workbuddy/skills/policy-ai-crawler/SKILL.md` to make dynamic research the default WorkBuddy procedure.
- Modify `apps/web/lib/policies.ts` and create `apps/web/components/policy-research-run-card.tsx` for typed API calls and progress UI.
- Modify `apps/web/app/(workspace)/policies/[cityId]/page.tsx` to trigger/poll a run and refresh policy sections.
- Create `apps/web/components/policy-research-run-card.test.tsx` for trigger, waiting, failure, and completion states.
- Modify `services/api/scripts/e2e_fixture_server.py`, `scripts/e2e_assert.py`, and `scripts/e2e-agent-flow.sh` for dynamic-query acceptance coverage.
- Modify `README.md`, `services/api/README.md`, and `docs/deployment/local.md` with the local WorkBuddy research workflow.

### Task 1: Add research-run persistence and public types

**Files:**
- Create: `services/api/migrations/sqlite/006_policy_research_runs.sql`
- Modify: `services/api/app/repository.py`
- Modify: `services/api/app/sqlite_repository.py`
- Modify: `services/api/app/api/schemas.py`
- Test: `services/api/tests/test_policy_research.py`

**Interfaces:**
- Produce `create_research_run(data)`, `get_research_run(run_id)`, `get_active_research_run(city_id)`, `list_research_runs(city_id=None, limit=None)`, and `update_research_run(run_id, data)` on `ProjectRepository` and both repository implementations.
- Produce `ResearchRunCreate`, `ResearchRunResultRequest`, and `ResearchRunCompleteRequest` Pydantic models.

- [x] **Step 1: Write failing repository tests**

```python
def test_active_research_run_is_unique_and_round_trips_json(repo):
    first = repo.create_research_run({"cityId": "长沙", "trigger": "ui", "scope": "all"})
    second = repo.create_research_run({"cityId": "长沙", "trigger": "workbuddy", "scope": "all"})
    assert second["id"] == first["id"]
    assert repo.get_active_research_run("长沙")["scope"] == "all"

def test_finished_run_allows_a_new_active_run(repo):
    first = repo.create_research_run({"cityId": "长沙", "trigger": "ui", "scope": "all"})
    repo.update_research_run(first["id"], {"status": "completed", "finishedAt": "2026-09-15T00:00:00Z"})
    second = repo.create_research_run({"cityId": "长沙", "trigger": "workbuddy", "scope": "policy"})
    assert second["id"] != first["id"]
```

- [x] **Step 2: Run the focused tests and verify they fail**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_policy_research.py -v`

Expected: import or repository-method failure because the research-run contract does not exist.

- [x] **Step 3: Add SQLite migration and repository mappings**

Create `policy_research_runs` with `city_id`, `project_id`, `trigger`, `scope_json`, lifecycle status, counters, prompt, timestamps, and error JSON. Create `policy_research_queries` with `run_id`, family, query, status, result count, searched time, and error. Add a partial unique index on `city_id` for statuses `queued`, `researching`, `fetching`, `extracting`, and `awaiting_review`.

Use API-to-SQL mappings in `_research_run_dict` and JSON deep copies in `JsonProjectRepository`. On duplicate active insertion, return the existing active row. Keep completed and failed runs in history.

- [x] **Step 4: Add strict request models and run the focused tests**

Use `trigger: Literal["ui", "workbuddy"]`, `scope: Literal["all", "policy", "population", "space"]`, `fields: list[str]`, and `researchRunId: str | None`. Reject unknown fields through `extra="forbid"`. Run the focused repository tests and then `pnpm api:test`.

### Task 2: Implement the run lifecycle and dynamic WorkBuddy brief

**Files:**
- Create: `services/api/app/domain/policy/research_service.py`
- Test: `services/api/tests/test_policy_research.py`

**Interfaces:**
- `PolicyResearchService.create_run(*, city_id: str, project_id: str | None, trigger: str, scope: str, fields: list[str]) -> dict[str, Any]`
- `PolicyResearchService.get_run(run_id: str) -> dict[str, Any]`
- `PolicyResearchService.build_brief(run_id: str) -> dict[str, Any]`
- `PolicyResearchService.retry(run_id: str) -> dict[str, Any]`
- `PolicyResearchService.complete(run_id: str, *, status: str, agent_run_id: str | None, agent_version: str | None, errors: list[str]) -> dict[str, Any]`
- `PolicyResearchService.task_prompt(run: Mapping[str, Any]) -> str`

- [x] **Step 1: Write failing service tests**

```python
def test_brief_uses_current_year_and_excludes_manual_and_formula_fields(service):
    run = service.create_run(city_id="长沙", project_id=None, trigger="workbuddy", scope="all", fields=[])
    brief = service.build_brief(run["id"])
    assert str(datetime.now(timezone.utc).year) in " ".join(q["query"] for q in brief["queries"])
    assert {item["id"] for item in brief["fieldCatalog"]}.isdisjoint({"S1", "B12"})
    assert brief["neverEstimateFields"] == ["C6", "C7", "C8"]

def test_retry_only_requeues_failed_or_partial_run(service):
    run = service.create_run(city_id="长沙", project_id=None, trigger="ui", scope="all", fields=[])
    service.repository.update_research_run(run["id"], {"status": "completed"})
    with pytest.raises(ValueError, match="RESEARCH_RUN_NOT_RETRYABLE"):
        service.retry(run["id"])
```

- [x] **Step 2: Run the focused tests to verify the service is missing**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_policy_research.py -v`

Expected: failure because `PolicyResearchService` and its brief contract do not exist.

- [x] **Step 3: Implement lifecycle and brief generation**

Build the brief from `load_parameter_catalog()` and the existing `FIELD_FAMILIES`. Add the current UTC year to policy and population queries, preserve a previous-year fallback query, include accepted/overridden field IDs, and include existing sources and recent artifacts. Generate a Chinese task prompt containing the run ID and the exact API sequence: brief → source candidates → fetch requests → extraction submissions → complete.

Use allowed transitions only: `queued -> researching -> fetching -> extracting -> awaiting_review -> completed|partial_failed|failed`. Reject terminal-to-terminal changes except idempotent completion. Set `taskPrompt` when creating a run.

- [x] **Step 4: Add idempotency and retry behavior**

Return an existing active run for duplicate city creation. `retry` must clear counters/errors, increment no history row, and set status back to `queued`. A repeated `complete` with the same `agentRunId` must return the stored terminal result.

- [x] **Step 5: Run service and regression tests**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_policy_research.py services/api/tests/test_city_onboarding.py -v`

Expected: all focused tests pass and existing city onboarding tests remain green.

### Task 3: Expose the research-run API and correlate WorkBuddy callbacks

**Files:**
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/api/app/domain/policy/agent_service.py`
- Test: `services/api/tests/test_policy_research.py`

**Interfaces:**
- `POST /api/policies/research-runs`
- `GET /api/policies/research-runs?cityId=&limit=`
- `GET /api/policies/research-runs/{run_id}`
- `GET /api/policies/research-runs/{run_id}/brief`
- `POST /api/policies/research-runs/{run_id}/retry`
- `POST /api/policies/research-runs/{run_id}/results`
- `POST /api/policies/research-runs/{run_id}/complete`

- [x] **Step 1: Write failing API tests**

```python
def test_create_research_run_returns_prompt_and_reuses_active(client):
    first = client.post("/api/policies/research-runs", json={"cityId": "长沙", "trigger": "ui", "scope": "all"})
    second = client.post("/api/policies/research-runs", json={"cityId": "长沙", "trigger": "ui", "scope": "all"})
    assert first.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert "更新长沙" in first.json()["taskPrompt"]

def test_brief_has_dynamic_queries_and_completion_is_idempotent(client):
    created = client.post("/api/policies/research-runs", json={"cityId": "长沙", "trigger": "workbuddy", "scope": "all"}).json()
    brief = client.get(f"/api/policies/research-runs/{created['id']}/brief")
    assert brief.status_code == 200
    assert any("site:gov.cn" in item["query"] for item in brief.json()["queries"])
    body = {"status": "completed", "agentRunId": "agent-1", "agentVersion": "policy-ai-crawler@2", "errors": []}
    assert client.post(f"/api/policies/research-runs/{created['id']}/complete", json=body).status_code == 200
    assert client.post(f"/api/policies/research-runs/{created['id']}/complete", json=body).status_code == 200
```

- [x] **Step 2: Run the API tests and verify they fail**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_policy_research.py -v`

Expected: 404 or missing route/model failure.

- [x] **Step 3: Add routes and run correlation**

Route all reads through `repository_from_request(request)`. Require the existing agent token for `/results`, `/complete`, and callback reuse of `source-candidates`, `fetch-requests`, and `extraction-submissions`. Check that callback `cityId` matches the run city. Update run counters after accepted source/artifact/fact results, but leave existing detailed audit records as the source of truth.

- [x] **Step 4: Add the combined result endpoint without bypassing validation**

`ResearchRunResultRequest` contains `candidates` and `submissions`; URL fetching continues through the existing `fetch-requests` endpoint with `researchRunId`. The route delegates to `AgentSubmissionService` and never writes `scenario_field_values` directly. All facts continue through quote, enum, unit, range, and never-estimate validation.

- [x] **Step 5: Verify API security and regression behavior**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest discover -s services/api/tests -p 'test_*.py'`

Expected: the full backend suite passes, including unauthorized callback checks and old policy crawl endpoints.

### Task 4: Update the WorkBuddy execution contract

**Files:**
- Modify: `.workbuddy/skills/policy-ai-crawler/SKILL.md`
- Modify: `.workbuddy/skills/policy-city-onboarding/SKILL.md`
- Modify: `README.md`
- Modify: `services/api/README.md`
- Test: `services/api/tests/test_documentation_contract.py`

**Interfaces:**
- WorkBuddy receives a run ID and uses `GET /api/policies/research-runs/{runId}/brief`.
- The skill sends `researchRunId` on fetch/candidate/extraction calls and closes through `/complete`.

- [x] **Step 1: Add documentation-contract assertions**

```python
def test_readmes_and_workbuddy_skill_describe_realtime_research():
    for path in (REPO_ROOT / "README.md", REPO_ROOT / "services/api/README.md", REPO_ROOT / ".workbuddy/skills/policy-ai-crawler/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        assert "research-runs" in text
        assert "当前年份" in text or "current year" in text
```

- [x] **Step 2: Run the documentation test and verify the new assertions fail**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_documentation_contract.py -v`

Expected: failure because the current skill documents only the fixed-source workflow.

- [x] **Step 3: Rewrite the WorkBuddy run order**

Make dynamic research the default for “更新城市政策”: create/reuse a run, read the brief, search using current-year queries, prefer concrete official article/PDF links, submit candidates, ask API to fetch, extract only changed artifacts, submit exact quotes, and call complete. Keep fixed configured-source crawling as a compatible fallback.

- [x] **Step 4: Document frontend waiting semantics**

State that a UI-created run is `queued` until a WorkBuddy invocation or local bridge executes it. The prompt must contain the exact city and run ID. Never label a queued run as completed.

- [x] **Step 5: Run documentation and backend tests**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_documentation_contract.py services/api/tests/test_policy_research.py -v`

Expected: all documentation and research-run tests pass.

### Task 5: Add the policy-page realtime update experience

**Files:**
- Modify: `apps/web/lib/policies.ts`
- Create: `apps/web/components/policy-research-run-card.tsx`
- Create: `apps/web/components/policy-research-run-card.test.tsx`
- Modify: `apps/web/app/(workspace)/policies/[cityId]/page.tsx`

**Interfaces:**
- `createPolicyResearchRun(input: { cityId: string; projectId?: string; trigger?: "ui" | "workbuddy"; scope?: ResearchScope })`
- `getPolicyResearchRun(runId: string)`
- `getPolicyResearchBrief(runId: string)`
- `retryPolicyResearchRun(runId: string)`
- `PolicyResearchRunCard({ cityId, cityName, initialRun, onSettled })`

- [x] **Step 1: Write failing component tests**

```tsx
it("creates a run and shows waiting-for-WorkBuddy prompt", async () => {
  render(<PolicyResearchRunCard cityId="长沙" run={null} onRefresh={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "AI 实时更新" }));
  expect(await screen.findByText("等待 WorkBuddy 执行")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "复制 WorkBuddy 指令" })).toBeInTheDocument();
});

it("shows partial failure and exposes retry", () => {
  render(<PolicyResearchRunCard cityId="长沙" run={{ status: "partial_failed", errorCount: 1, errors: ["搜索超时"], taskPrompt: "更新长沙" }} onRefresh={vi.fn()} />);
  expect(screen.getByText("搜索超时")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "再次更新" })).toBeInTheDocument();
});
```

- [x] **Step 2: Run the component test and verify it fails**

Run: `pnpm --filter @ue-agent/web test -- policy-research-run-card.test.tsx`

Expected: failure because the typed API functions and component do not exist.

- [x] **Step 3: Add typed API functions and the run card**

Render button, last run time, status badge, current phase, counters, errors, task prompt, copy action, retry action, and “查看变更” summary. Poll every 2 seconds only while status is active; stop on terminal status. Use the existing button/card styles and Chinese UI copy.

- [x] **Step 4: Wire the city policy page**

Load the latest city run independently from the existing policy sections. The button creates `trigger: "ui"`, `scope: "all"`; on terminal completion reload sources, freshness, extraction submissions, and targets. Keep a failed AI panel from blanking the policy page.

- [x] **Step 5: Run frontend tests, lint, and typecheck**

Run: `pnpm --filter @ue-agent/web test && pnpm lint && pnpm typecheck`

Expected: all frontend tests pass with no lint or TypeScript errors.

### Task 6: Add E2E coverage and finish verification

**Files:**
- Modify: `scripts/e2e_assert.py`
- Modify: `scripts/e2e-agent-flow.sh`
- Modify: `README.md`
- Modify: `services/api/README.md`
- Modify: `docs/deployment/local.md`

**Interfaces:**
- The existing fixture provides a concrete official policy page; E2E asserts dynamic query creation, run completion, evidence correlation, and no overwrite of adopted/manual values.

- [x] **Step 1: Add a failing E2E assertion**

```bash
created=$(post_json /api/policies/research-runs '{"cityId":"长沙","trigger":"workbuddy","scope":"all"}')
run_id=$(json_get "$created" id)
brief=$(get_json "/api/policies/research-runs/$run_id/brief")
assert_contains "$brief" "$(date +%Y)"
assert_contains "$brief" "currentYear"
```

- [x] **Step 2: Run E2E and verify the new assertion fails**

Run: `bash scripts/e2e-agent-flow.sh`

Expected: failure until the research-run endpoints and fixture handshake exist.

- [x] **Step 3: Complete fixture-driven WorkBuddy handshake**

Have the fixture return a concrete official policy page and candidate search result. Run the research flow through brief, source discovery, fetch, extraction, complete, and retry. Assert `first_fetch/new_version` triggers extraction while `unchanged` does not create a second suggestion.

- [x] **Step 4: Run the complete verification suite**

Run: `pnpm api:test && pnpm --filter @ue-agent/web test && pnpm lint && pnpm typecheck && pnpm build && bash scripts/e2e-agent-flow.sh`

Expected: backend, frontend, lint, typecheck, production build, and E2E all exit 0.

- [x] **Step 5: Run final diff and requirement checks**

Run: `git diff --check` and scan the spec/plan for placeholder markers, stale fixed-URL-only claims, and any path that bypasses `AgentSubmissionService`. The final report must state that this is on-demand realtime search, not an always-on guarantee, and that no commit/push was performed unless separately requested.
