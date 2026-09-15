# Portable UE-Agent and WorkBuddy Delivery Implementation Plan

> **For agentic workers:** This plan is executed inline in the current workspace. Each task has an independent test cycle.

**Goal:** Package the UE-Agent source, local SQLite data, WorkBuddy skills, and scheduled-task template into a portable handoff bundle that another developer can install and run with one setup command.

**Architecture:** UE-Agent remains the source of truth: FastAPI owns deterministic calculations, SQLite persistence, raw-source archiving, and audit records. WorkBuddy receives project-level skills from `.workbuddy/skills/`; a repository-scoped automation template starts one global policy-sync workflow that discovers all cities and calls the existing research-run callback protocol. Account-owned WorkBuddy automation records and secrets are deliberately excluded from the bundle and are recreated from the template once by the recipient.

**Tech Stack:** Python 3.11 stdlib (`sqlite3`, `tarfile`, `shutil`), FastAPI, SQLite, Next.js 16, pnpm 11, Bash, WorkBuddy project-level Markdown skills and JSON automation template.

## Global Constraints

- Local runtime uses SQLite and `services/api/data/`; no cloud database or Vercel credentials are required.
- `C6/C7/C8` remain `notDisclosed`; WorkBuddy suggestions never overwrite manual or formula values.
- The handoff package must exclude `.env.local`, Vercel tokens, `.git`, dependencies, build output, and private WorkBuddy memory.
- `.workbuddy/skills/` and `.workbuddy/automations/` are delivery assets and must remain tracked by Git.
- A WorkBuddy scheduled task must use `policy-ai-crawler` by name and call `complete` only after actual execution.
- Every new behavior gets a failing test before production implementation; shell wrappers must delegate to testable Python or documented commands.

---

### Task 1: Define the portable handoff contract and failing tests

**Files:**
- Create: `services/api/tests/test_portable_handoff.py`
- Create: `docs/deployment/portable-handoff.md`
- Create: `.workbuddy/automations/policy-ai-sync.template.json`
- Create: `.workbuddy/automations/README.md`

**Interfaces:**
- Produces a testable `scripts.handoff.package_handoff(repo_root, output_dir, include_data=True) -> Path` contract.
- Produces a machine-readable automation template with `name`, `rrule`, `timezone`, `skill`, `apiBaseUrl`, and `prompt`.

- [ ] **Step 1: Write failing tests for package filtering and automation assets**

  Add tests that create a miniature repository tree containing source files, `.env.local`, `node_modules`, `.workbuddy/memory`, `.workbuddy/skills`, and `.workbuddy/automations`, then assert the package contains only the portable assets. Also assert the automation template references the skill, local API, all-city mode, and no user-specific path or token.

- [ ] **Step 2: Run the tests and verify the expected import failure**

  Run:

  ```bash
  PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_portable_handoff.py -v
  ```

  Expected: FAIL because `scripts.handoff` and the automation template do not exist yet.

- [ ] **Step 3: Add the delivery contract documents and template**

  Document the exact recipient flow:

  ```text
  tar -xzf ue-agent-handoff-*.tar.gz
  cd ue-agent-handoff-*
  bash scripts/setup-local.sh
  bash scripts/dev-all.sh
  ```

  Explain that source, SQLite backup, raw policy files, two Skills, and the automation template are included; WorkBuddy account records and secrets are not exported. The recipient creates the recurring task once by asking WorkBuddy to read `.workbuddy/automations/policy-ai-sync.template.json`.

- [ ] **Step 4: Re-run the tests after the contract-only changes**

  Run the same targeted command. Expected: the asset contract assertions pass while package-function assertions remain the only failing group until Task 2 implements the packager.

---

### Task 2: Implement the portable package builder

**Files:**
- Create: `scripts/handoff.py`
- Create: `scripts/package-handoff.sh`
- Modify: `services/api/tests/test_portable_handoff.py`
- Modify: `package.json`

**Interfaces:**
- `scripts.handoff.copy_portable_source(repo_root: Path, target: Path) -> None` copies source while applying the delivery exclusion policy.
- `scripts.handoff.package_handoff(repo_root: Path, output_dir: Path | None = None, include_data: bool = True) -> Path` returns a `.tar.gz` path.
- The package contains `handoff-data/` when a database exists; it is a verified backup created through the existing `create_backup` function and does not mutate live data.

- [ ] **Step 1: Extend tests for a real SQLite data backup**

  Seed a temporary SQLite database with one project and one raw-source file, call `package_handoff`, extract the tarball, and assert:

  - `handoff-data/ue-agent.sqlite3` exists and passes `PRAGMA integrity_check`;
  - `handoff-data/raw_sources/...` exists;
  - `.workbuddy/skills/policy-ai-crawler/SKILL.md` and the automation template exist;
  - `.env.local`, `node_modules/`, `.workbuddy/memory/`, and `.git/` do not exist;
  - the generated `HANDOFF.md` includes `bash scripts/setup-local.sh`.

- [ ] **Step 2: Run the new test and verify it fails on the missing implementation**

  Run the targeted test file and confirm the failure is the missing `package_handoff` import or function, not a fixture error.

- [ ] **Step 3: Implement `scripts/handoff.py`**

  Use only stdlib file operations. Skip build/dependency directories and any file whose basename is `.env`, `.env.local`, `.env.*` except `.env.example`. Skip private `.workbuddy/memory/` while explicitly retaining `.workbuddy/skills/` and `.workbuddy/automations/`. When data exists, call `create_backup(data_dir, temporary_backup_root)` and copy the verified backup into `handoff-data/`. Create `HANDOFF.md` inside the package root, then write a gzip tarball without following symlinks outside the repository.

- [ ] **Step 4: Add the shell entrypoint and package scripts**

  `scripts/package-handoff.sh` resolves the repository root and invokes `python3 scripts/handoff.py`. Add:

  ```json
  "handoff:package": "bash scripts/package-handoff.sh",
  "handoff:check": "bash scripts/check-portable.sh",
  "setup": "bash scripts/setup-local.sh"
  ```

- [ ] **Step 5: Run targeted tests and an actual package smoke test**

  Run the targeted Python tests, then:

  ```bash
  bash scripts/package-handoff.sh
  tar -tzf dist/ue-agent-handoff-*.tar.gz | rg '(.workbuddy/skills|.workbuddy/automations|handoff-data|HANDOFF.md)'
  ```

  Expected: test pass and the archive lists skills, automation template, data backup when present, and handoff instructions.

---

### Task 3: Make local installation and startup independent of uv/Vercel state

**Files:**
- Create: `scripts/setup-local.sh`
- Create: `scripts/api-dev.sh`
- Create: `scripts/check-portable.sh`
- Create: `.env.example`
- Modify: `scripts/dev-all.sh`
- Modify: `package.json`
- Modify: `docs/deployment/local.md`

**Interfaces:**
- `bash scripts/setup-local.sh` installs Node dependencies, creates `services/api/.venv`, installs API runtime dependencies, restores bundled `handoff-data/` only into an empty data directory, and runs bootstrap.
- `bash scripts/api-dev.sh` selects `UE_AGENT_API_PYTHON`, `services/api/.venv/bin/python`, `.venv-publish/bin/python`, or `python3` with a clear error if `uvicorn` is unavailable.
- `bash scripts/check-portable.sh` exits non-zero when required delivery assets are missing or a secret file is accidentally present in the tracked package surface.

- [ ] **Step 1: Add failing contract tests for setup assets and scripts**

  Assert the scripts are executable, contain no hard-coded `/Users/jhx` path, reference `handoff-data`, use the existing `restore_data.py` safety flow, and that `package.json` points `api:dev` to `scripts/api-dev.sh`.

- [ ] **Step 2: Run the contract tests and verify the expected failures**

  Run `test_portable_handoff.py -v`; expected failures identify the missing setup/start/check files and old `api:dev` command.

- [ ] **Step 3: Implement the setup and runtime scripts**

  Use Bash arrays and `pip install -r <(python scripts/_read_api_deps.py)` so the installer works on macOS and Linux without GNU-only `xargs`. Use `corepack pnpm` only when the `pnpm` executable is unavailable. Do not create or copy any secret file. Restore bundled data only when `services/api/data/ue-agent.sqlite3` is absent; subsequent runs only initialize missing schema/directories.

- [ ] **Step 4: Update the local delivery documentation and environment example**

  Put all recipient-facing variables in `.env.example` with empty token values, including `UE_AGENT_AGENT_TOKEN`, `UE_AGENT_ALLOWED_ORIGINS`, `UE_AGENT_DATA_DIR`, and `NEXT_PUBLIC_API_BASE_URL`. State that WorkBuddy must run on the same machine to reach `http://127.0.0.1:8000`; cloud WorkBuddy requires a reachable API address.

- [ ] **Step 5: Run setup-script contract tests and shell syntax checks**

  Run:

  ```bash
  bash -n scripts/setup-local.sh scripts/api-dev.sh scripts/check-portable.sh scripts/package-handoff.sh scripts/dev-all.sh
  ```

  Expected: exit 0. Then run the targeted Python contract test and the existing backup/restore test module.

---

### Task 4: Turn the WorkBuddy Skill into a reusable global scheduled workflow

**Files:**
- Modify: `.workbuddy/skills/policy-ai-crawler/SKILL.md`
- Modify: `.workbuddy/skills/policy-city-onboarding/SKILL.md`
- Modify: `.workbuddy/automations/policy-ai-sync.template.json`
- Modify: `.workbuddy/automations/README.md`
- Modify: `services/api/README.md`
- Modify: `README.md`
- Modify: `services/api/tests/test_documentation_contract.py`

**Interfaces:**
- The Skill supports an “全城市政策同步” trigger that reads `/api/projects`, handles cities with no active sources through `policy-city-onboarding`, then runs the research-run protocol for every city.
- The automation prompt references only repository-relative Skill names and `BASE_URL`; it contains no account id, user path, token, or fixed city.
- The API remains unchanged as the callback contract: `research-runs`, `source-candidates`, `fetch-requests`, `extraction-submissions`, and `complete`.

- [ ] **Step 1: Add failing documentation contract assertions**

  Assert that the global Skill contains “全城市”, `/api/projects`, `policy-city-onboarding`, “不要覆盖”, `research-runs`, and `complete`; assert the automation template contains `FREQ=DAILY`, `Asia/Shanghai`, `policy-ai-crawler`, and does not contain `/Users/` or `UE_AGENT_AGENT_TOKEN` values.

- [ ] **Step 2: Run the documentation test and verify the expected failure**

  Run:

  ```bash
  PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_documentation_contract.py -v
  ```

  Expected: FAIL on the missing global scheduled-workflow sections.

- [ ] **Step 3: Update the Skill and automation template**

  Define one global scheduled task instead of one task per city. It must health-check the API, list cities, create/reuse one research run per city, use current-year queries, preserve official-source review rules, skip unchanged artifacts, return structured suggestions with quotes, mark unavailable D-fields as `notDisclosed`, and call `complete` only after work starts. The final report must distinguish “候选来源” from “正式来源” and “建议值” from “人工采用值”.

- [ ] **Step 4: Update repository docs and contract tests**

  Explain that copying the repository carries both Skills and the scheduler template, while the recipient still must create the account-owned recurring task once. Remove instructions that imply a UI-generated prompt is the only way to run a research cycle.

- [ ] **Step 5: Run the documentation contract test**

  Expected: PASS with the global Skill and portable scheduler assertions.

---

### Task 5: Full verification and handoff checklist

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment/portable-handoff.md`

- [ ] **Step 1: Run all backend tests**

  ```bash
  pnpm api:test
  ```

- [ ] **Step 2: Run frontend checks**

  ```bash
  pnpm test
  pnpm typecheck
  pnpm lint
  pnpm build
  ```

- [ ] **Step 3: Run package and portable checks**

  ```bash
  pnpm handoff:check
  pnpm handoff:package
  ```

  Inspect the archive contents and verify no `.env.local`, Vercel token, private WorkBuddy memory, or dependency directory is included.

- [ ] **Step 4: Report actual delivery state**

  Report source changes, handoff archive path, included data status, verification output, and the one recipient action that cannot be automated: create the WorkBuddy scheduled task from the repository template in the recipient’s own WorkBuddy account.
