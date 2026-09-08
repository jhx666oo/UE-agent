# U1 MVP Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make U1 locally runnable from project creation through parameter entry, deterministic calculation, persistence, and result review.

**Architecture:** Add a thin FastAPI adapter over the existing pure U1 domain engine, backed by an atomic local JSON repository. Replace the current placeholder project/U1 pages with a typed client and a dynamic parameter/result workflow; the browser never owns financial formulas.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, Uvicorn, standard-library JSON persistence, Next.js 16, React 19, TypeScript strict mode, existing shared UI package, Vitest, unittest.

## Global Constraints

- Keep `u1-excel-v2.1-parity` formulas unchanged and expose `E32`, `B12`, and `AB32` issues.
- Do not add a database, crawler, authentication system, or policy center to this vertical slice.
- Do not commit runtime project data or the source Excel workbook.
- Keep all core financial calculations in `services/api/app/domain/u1`.
- Preserve `null`, numeric zero, formula errors, and formula-only fields as distinct states.
- Use test-first cycles for new behavior and run the complete verification suite before pushing.

---

### Task 1: Add a local project/scenario repository and API schemas

**Files:**
- Create: `services/api/app/repository.py`
- Create: `services/api/app/api/__init__.py`
- Create: `services/api/app/api/schemas.py`
- Create: `services/api/tests/test_repository.py`
- Modify: `services/api/pyproject.toml`
- Modify: `.gitignore`

**Interfaces:**
- `JsonProjectRepository(path: Path)` with `list_projects()`, `get_project(project_id)`, `create_project(payload)`, `create_scenario(project_id, payload)`, `update_scenario(project_id, scenario_id, payload)`, `save_calculation(project_id, scenario_id, result)`.
- Schemas: `ProjectCreate`, `ScenarioCreate`, `ScenarioUpdate`, `ProjectRecord`, `ScenarioRecord`.

- [ ] **Step 1: Write failing repository tests**

Test that a temporary JSON file can create a project, create a scenario, update inputs containing both `0` and `None`, and reload the same records through a fresh repository instance.

- [ ] **Step 2: Run the repository tests to verify red**

Run `PYTHONPATH=services/api python3 -m unittest services/api/tests/test_repository.py -v` and confirm the repository import is missing.

- [ ] **Step 3: Implement the atomic JSON repository**

Use UUID strings, UTC ISO timestamps, an empty document shape `{"projects": []}`, `tempfile.NamedTemporaryFile` in the target directory, `json.dump`, and `os.replace`. Raise `KeyError` for missing project/scenario IDs. Keep repository methods synchronous.

- [ ] **Step 4: Add Pydantic request/response schemas and FastAPI dependencies**

Add `fastapi>=0.115,<1`, `uvicorn[standard]>=0.30,<1`, and test extra `httpx>=0.27,<1` to `services/api/pyproject.toml`. Keep schema validation limited to shape, non-empty names, and mapping types; domain required-input validation remains in the engine.

- [ ] **Step 5: Run repository tests to verify green**

Run the targeted test and `uv run --project services/api python -m unittest services/api/tests/test_repository.py -v`.

---

### Task 2: Expose the U1 FastAPI contract

**Files:**
- Create: `services/api/app/main.py`
- Create: `services/api/app/api/routes.py`
- Create: `services/api/tests/test_api.py`
- Modify: `services/api/app/repository.py`
- Modify: `services/api/README.md`
- Modify: `package.json`

**Interfaces:**
- `app.main:app` is the Uvicorn entrypoint.
- `GET /api/health`, `GET /api/model/u1`, project/scenario CRUD, and calculate endpoint as defined in `docs/superpowers/specs/2026-09-08-u1-mvp-vertical-slice-design.md`.

- [ ] **Step 1: Write failing API tests**

Use `fastapi.testclient.TestClient` with `UE_AGENT_DATA_FILE` pointing to a temporary file. Cover health, model catalog, project creation, scenario creation, calculation, result persistence, unknown project `404`, and missing `P1` `422`.

- [ ] **Step 2: Run API tests to verify red**

Run `uv run --project services/api --extra test python -m unittest services/api/tests/test_api.py -v` and confirm `app.main` is missing.

- [ ] **Step 3: Implement the FastAPI app and routes**

Build the app from a repository dependency, load the baseline fixture for empty scenarios, convert `U1Result` dataclasses into JSON-safe dictionaries, return model issues unchanged, and enable local CORS. Use explicit exception handlers for `KeyError` and `ValueError`.

- [ ] **Step 4: Add API test command and local run instructions**

Add root script `api:test` using `uv run --project services/api --extra test python -m unittest discover -s services/api/tests -p 'test_*.py'`; document `uv run --project services/api uvicorn app.main:app --reload --port 8000`.

- [ ] **Step 5: Run all Python tests to verify green**

Run `pnpm model:test` and `pnpm api:test`.

---

### Task 3: Replace the placeholder project creation page with a real flow

**Files:**
- Create: `apps/web/lib/api.ts`
- Create: `apps/web/lib/api.test.ts`
- Create: `apps/web/app/(workspace)/projects/[projectId]/u1/page.tsx`
- Modify: `apps/web/app/(workspace)/projects/new/page.tsx`
- Modify: `apps/web/app/(workspace)/projects/page.tsx`
- Modify: `apps/web/components/empty-state.tsx`

**Interfaces:**
- `apiFetch<T>(path, init?)` handles base URL, JSON headers, API error payloads, and network errors.
- `createProject(input)`, `getModelSpec()`, `getProject(projectId)`, `updateScenario(...)`, `calculateScenario(...)` are typed wrappers.

- [ ] **Step 1: Write failing client tests**

Test base URL joining, structured API error messages, and `formatFormulaValue` for `0`, `null`, and `formula_error`.

- [ ] **Step 2: Run client tests to verify red**

Run `pnpm --filter @ue-agent/web test -- lib/api.test.ts` and confirm the client module is missing.

- [ ] **Step 3: Implement the typed API client**

Use `NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"`, never calculate U1 values in TypeScript, and return typed JSON data.

- [ ] **Step 4: Implement project creation and project list loading**

Make `/projects/new` a client component with controlled fields and a disabled submit while saving. On success navigate to `/projects/{id}/u1`; show inline errors and preserve zero/blank input behavior. Make `/projects` load saved projects with loading, empty, and error states.

- [ ] **Step 5: Run frontend tests and typecheck**

Run `pnpm --filter @ue-agent/web test`, `pnpm typecheck`, and `pnpm lint`.

---

### Task 4: Build the dynamic U1 parameter and result workflow

**Files:**
- Create: `apps/web/components/u1-workbench.tsx`
- Create: `apps/web/components/u1-parameter-field.tsx`
- Create: `apps/web/components/u1-result-panel.tsx`
- Create: `apps/web/components/u1-workbench.test.tsx`
- Modify: `apps/web/app/(workspace)/u1/page.tsx`
- Modify: `apps/web/app/(workspace)/projects/[projectId]/u1/page.tsx`

**Interfaces:**
- `groupParameters(catalog)` groups the catalog in C/P/S/B/D/E/A/Z order.
- `U1Workbench` owns edit/save/calculate state but delegates calculations to `api.ts`.
- `U1ResultPanel` renders headline metrics, stage summary, monthly projection, and issue severity/status.

- [ ] **Step 1: Write failing UI tests**

Test that the workbench renders formula fields as read-only, keeps a manually entered `0`, displays `DIV0` as an error state, and renders all three known issue codes after a calculated result is supplied.

- [ ] **Step 2: Run UI tests to verify red**

Run `pnpm --filter @ue-agent/web test -- components/u1-workbench.test.tsx` and confirm the components are missing.

- [ ] **Step 3: Implement parameter grouping and field states**

Render field labels, units, source type, required state, formula/read-only state, and controlled values. Use numeric inputs with `value={value ?? ""}` and convert an empty string to `null`, never to `0`.

- [ ] **Step 4: Implement save/calculate/result states**

Show `未保存`, `保存中`, `待测算`, `测算中`, `已完成` and error states. Result cards must show model version, payback month, max cash deficit, platform profit, platform margin, cumulative metric, break-even customers, and initial investment.

- [ ] **Step 5: Run UI tests and production build**

Run `pnpm --filter @ue-agent/web test`, `pnpm typecheck`, `pnpm lint`, and `pnpm build`.

---

### Task 5: Integrate documentation, local scripts, and verification

**Files:**
- Modify: `README.md`
- Modify: `services/api/README.md`
- Modify: `docs/UE-Agent-详细开发规范-v0.1.md`
- Modify: `docs/standards/06-前端验收检查表.md`
- Modify: `docs/superpowers/specs/2026-09-08-u1-mvp-vertical-slice-design.md`
- Modify: `docs/superpowers/plans/2026-09-08-u1-mvp-vertical-slice.md`

- [ ] **Step 1: Document the two-process local run**

Document `uv run --project services/api uvicorn app.main:app --reload --port 8000` and `pnpm dev`, plus `NEXT_PUBLIC_API_BASE_URL` override.

- [ ] **Step 2: Mark only verified acceptance items**

Record API tests, model tests, frontend tests, typecheck, lint, build, and clean diff results; leave policy crawling, authentication, and Playwright explicitly unchecked.

- [ ] **Step 3: Run the complete verification suite**

Run `pnpm model:test`, `pnpm api:test`, `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm build`, and `git diff --check`. Confirm no Excel source or runtime JSON data is staged.

- [ ] **Step 4: Commit and push the vertical slice**

Use commit message `feat: add U1 MVP calculation workflow` and push `origin main`.

## Self-review

- The design keeps the Python engine as the only formula owner.
- Each task has a testable deliverable and an explicit red-green cycle.
- Local persistence is intentionally replaceable and does not lock the project into a database before the API contract stabilizes.
- The plan does not claim policy, crawler, multi-city, permissions, or production deployment are complete.
