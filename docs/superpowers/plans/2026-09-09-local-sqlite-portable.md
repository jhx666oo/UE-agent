# Local SQLite Portable Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Vercel production storage path with a portable local SQLite and file-based runtime that can be handed off next week and continued by another developer.

**Architecture:** Keep the existing FastAPI route contracts and deterministic U1 engine. Add a `SqliteProjectRepository` implementing the same repository behavior, a migration runner for the current JSON fixture, local policy/raw-source file stores, and a small crawler runner. The API defaults to SQLite locally; the JSON repository remains only for isolated unit tests and migration input.

**Tech Stack:** Python 3.11+, FastAPI, stdlib `sqlite3`, Next.js 16, pnpm, uv, Vitest, unittest.

## Global Constraints

- Runtime data lives under `services/api/data/` and is excluded from source-only artifacts.
- Existing API response shapes and Dashboard behavior remain compatible.
- No policy fact is published without an explicit review decision.
- Crawl jobs save source evidence and metadata; they do not invent or auto-approve policy values.
- Do not delete Vercel projects or Blob storage in this plan; they remain unused external resources until separately confirmed.
- Use TDD for repository, migration, bootstrap, and crawler behavior.

---

### Task 1: Define SQLite schema and repository contract

**Files:**
- Create: `services/api/app/sqlite_repository.py`
- Create: `services/api/migrations/001_initial.sql`
- Create: `services/api/tests/test_sqlite_repository.py`
- Modify: `services/api/app/main.py`
- Modify: `services/api/app/api/routes.py`

**Interfaces:**
- Consumes: existing repository method names used by `services/api/app/api/routes.py`.
- Produces: `SqliteProjectRepository`, `initialize_database(path)`, and `default_database_path()`.

- [ ] **Step 1: Write failing SQLite persistence tests**

Test that a project/scenario/calculation snapshot survives closing and reopening the repository, that a policy document stores a file below `services/api/data/policy_files/`, and that `initialize_database` is idempotent.

- [ ] **Step 2: Run the focused test and verify it fails for the missing repository**

Run:

```bash
PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_sqlite_repository.py
```

Expected: import failure for `app.sqlite_repository` before implementation.

- [ ] **Step 3: Implement the schema and repository**

Use `sqlite3.connect(path)`, `PRAGMA foreign_keys = ON`, `row_factory = sqlite3.Row`, and JSON serialization for `inputs`, `result`, `issues`, and `value`. Create tables `projects`, `scenarios`, `calculation_snapshots`, `data_sources`, `policy_documents`, `policy_facts`, and `crawl_artifacts`. Keep `PolicyFileStore` local-only and write files through temporary files plus `os.replace`.

- [ ] **Step 4: Make API repository selection local by default**

`create_repository()` must return `SqliteProjectRepository(default_database_path())`. Keep `JsonProjectRepository` available for existing tests and migration reads. Change policy content responses to use the repository file-store interface rather than a Vercel or local path assumption.

- [ ] **Step 5: Run focused tests and the full API suite**

Run:

```bash
PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_sqlite_repository.py
pnpm api:test
```

Expected: focused SQLite tests and all API tests pass.

### Task 2: Migrate existing JSON data into SQLite

**Files:**
- Create: `services/api/scripts/bootstrap.py`
- Create: `services/api/scripts/migrate_json_to_sqlite.py`
- Create: `scripts/backup_data.py`
- Create: `services/api/tests/test_bootstrap.py`
- Modify: `package.json`
- Modify: `.gitignore`
- Modify: `services/api/README.md`

**Interfaces:**
- Consumes: `JsonProjectRepository`, `SqliteProjectRepository`, and `initialize_database`.
- Produces: `pnpm bootstrap`, `pnpm data:backup`, and a repeatable migration command.

- [ ] **Step 1: Write failing bootstrap tests**

Test that bootstrap creates the data directories and database, imports `services/api/data/projects.json` only when the target database has no projects, and does not overwrite an existing database.

- [ ] **Step 2: Run the focused test and verify the expected failure**

Run:

```bash
PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_bootstrap.py
```

Expected: missing bootstrap module or command failure.

- [ ] **Step 3: Implement bootstrap and JSON migration**

`bootstrap.py` must create `services/api/data/policy_files/` and `services/api/data/raw_sources/`, apply migrations, then call the JSON migration only when the SQLite project count is zero. The migration must copy projects, nested scenarios, snapshots, data sources, policy documents, and policy facts without generating new business values.

- [ ] **Step 4: Add backup command and package scripts**

Add scripts:

```json
{
  "bootstrap": "uv run --project services/api python services/api/scripts/bootstrap.py",
  "data:backup": "uv run --project services/api python services/api/scripts/backup_data.py"
}
```

The backup script copies the SQLite file and data folders into `services/api/backups/<UTC timestamp>/` without deleting source data.

- [ ] **Step 5: Run bootstrap twice and verify idempotency**

Run `pnpm bootstrap` twice in a temporary data path, then run the bootstrap test suite. Expected: the second run reports that existing records were retained and does not duplicate projects.

### Task 3: Add one-command local development and handoff documentation

**Files:**
- Create: `scripts/dev-all.sh`
- Create: `docs/deployment/local.md`
- Modify: `package.json`
- Modify: `apps/web/.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: local API database path and `NEXT_PUBLIC_API_BASE_URL`.
- Produces: `pnpm dev:all`, local environment documentation, backup/restore instructions, and a handoff checklist.

- [ ] **Step 1: Write a smoke test for the command contract**

Test the package JSON scripts and the shell script’s documented commands without launching long-running servers in the test process.

- [ ] **Step 2: Implement `scripts/dev-all.sh`**

Start `pnpm api:dev` and `pnpm dev`, forward termination to both child processes, and exit when either process exits. The script must not read or print secrets.

- [ ] **Step 3: Update README and local env example**

Document prerequisites (`node`, `pnpm`, `uv`), `pnpm install`, `pnpm bootstrap`, `pnpm dev:all`, data backup, and the exact files to copy during handoff. Replace Vercel production instructions with an explicit local deployment section while preserving a short note that Vercel resources are not required.

- [ ] **Step 4: Verify the local handoff flow**

Run `pnpm bootstrap`, start `pnpm dev:all`, call `/api/health`, open `/`, and verify that the local database path is reported in API logs without exposing credentials.

### Task 4: Add local policy-source crawling artifacts

**Files:**
- Create: `services/api/app/crawlers/__init__.py`
- Create: `services/api/app/crawlers/runner.py`
- Create: `services/api/tests/test_crawler.py`
- Modify: `services/api/app/repository.py` or the SQLite repository interface
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/pyproject.toml`

**Interfaces:**
- Consumes: active `data_sources` records with an HTTP URL.
- Produces: `crawl_source(source_id) -> CrawlArtifact` and `POST /api/policies/sources/{source_id}/crawl`.

- [ ] **Step 1: Write failing crawler tests**

Test URL validation, timeout handling, raw response persistence under `services/api/data/raw_sources/`, SHA-256 calculation, and crawl artifact metadata. Use a local test HTTP server rather than external websites.

- [ ] **Step 2: Run the focused test and verify the expected failure**

Run:

```bash
PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_crawler.py
```

Expected: missing crawler module or endpoint.

- [ ] **Step 3: Implement the bounded local crawler**

Use an explicit timeout, a maximum response size, an allowed `http/https` URL check, a descriptive user-agent, and atomic raw-file writes. Store status code, final URL, fetched time, content type, content length, SHA-256, and local path. Do not parse or approve policy facts in the fetch step.

- [ ] **Step 4: Add the API endpoint and source status update**

Return a stable artifact response and map invalid source IDs or failed fetches to structured API errors. Keep the operation manual and synchronous for this handoff version; scheduling can be added later on top of the artifact store.

- [ ] **Step 5: Run crawler, API, and regression tests**

Expected: local crawler tests, all API tests, model tests, and frontend tests pass.

### Task 5: Remove Vercel runtime dependencies and finalize portable mode

**Files:**
- Modify: `services/api/app/main.py`
- Modify: `services/api/app/repository.py`
- Modify: `services/api/pyproject.toml`
- Modify: `services/api/uv.lock`
- Delete: `services/api/vercel.json`
- Delete: `services/api/.vercelignore`
- Delete: `services/api/migrations/001_ue_agent_store.sql`
- Delete: `services/api/scripts/migrate_json_to_postgres.py`
- Delete: `docs/deployment/vercel.md`
- Modify: `services/api/.gitignore`
- Modify: `apps/web/.gitignore`

**Interfaces:**
- Consumes: SQLite repository and local file store from Tasks 1–4.
- Produces: no runtime dependency on `psycopg` or the Python `vercel` SDK; Vercel tokens remain unreferenced by application code.

- [ ] **Step 1: Add a regression test that local startup ignores cloud environment variables**

Set `DATABASE_URL` and `BLOB_READ_WRITE_TOKEN` to sentinel values, construct the app with no injected repository, and assert that the repository is SQLite-backed and no network client is created.

- [ ] **Step 2: Remove cloud adapters and dependencies**

Delete the Postgres/Vercel repository path and remove `psycopg` and `vercel` from `pyproject.toml` and the lockfile. Keep the local repository and its test adapter.

- [ ] **Step 3: Remove Vercel-only deployment files**

Remove the Vercel project configuration from the repository; do not delete the already-created external Vercel projects or Blob store.

- [ ] **Step 4: Run all tests and inspect the final dependency graph**

Run `pnpm test`, `pnpm model:test`, `pnpm api:test`, `pnpm typecheck`, `pnpm lint`, `pnpm build`, and `git diff --check`. Expected: all pass and no application file imports `psycopg`, `vercel.blob`, or `DATABASE_URL`.

### Task 6: Handoff verification and GitHub update

**Files:**
- Modify: `README.md`
- Create: `docs/handoff/2026-09-09-local-delivery-checklist.md`
- Test: all project test suites and a temporary clean-copy smoke run.

**Interfaces:**
- Consumes: completed local runtime and crawler artifacts.
- Produces: a documented handoff checklist and a clean branch update to the existing Draft PR.

- [ ] **Step 1: Create a clean-copy smoke directory**

Copy tracked source plus a sample data directory to a temporary directory, run `pnpm install`, `pnpm bootstrap`, and the focused health check without using the original `.env.local` or `.vercel` directories.

- [ ] **Step 2: Verify data survives an API restart**

Create a test project and scenario, calculate it, stop the API, restart it, and confirm the Dashboard overview returns the saved snapshot.

- [ ] **Step 3: Verify policy file and crawl artifact handoff**

Upload a test policy file, run the local source crawler against a local HTTP fixture, restart the API, and confirm both records and files are present.

- [ ] **Step 4: Update and push the existing branch**

Run `git diff --check`, commit the local-delivery change, and push `codex/dashboard-data-sync` so the existing Draft PR contains the final handoff architecture.
