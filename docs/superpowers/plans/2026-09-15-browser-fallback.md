# 政策双通道抓取兜底 Implementation Plan

> **For agentic workers:** Follow this plan task by task and keep the checkbox status updated as work progresses.

**Goal:** 为普通 HTTP 抓取增加结构化浏览器兜底，让 WorkBuddy 能把被 WAF、网络限制或大响应体拦截的官方正文回传并继续进入统一证据归档、字段校验和建议值流程；已进入队列的来源不再重复 HTTP。

**Architecture:** 保留现有 `httpx` 抓取作为第一通道；API 对可兜底错误返回 `fallbackAction` 和错误分类并生成幂等任务，WorkBuddy Skill 领取任务后使用浏览器或 AI 检索原文，再通过受保护的 `browser-artifacts` 接口回传。浏览器内容落为标准 crawl artifact，后续复用现有 extraction-submissions 校验链路；城市和来源状态从 artifact、任务与来源元数据派生，适配所有城市。

**Tech Stack:** FastAPI、Pydantic、SQLite migration、现有 Json/SQLite Repository、WorkBuddy Markdown Skill、Next.js/React、TypeScript、Vitest、Python unittest。

## Global Constraints

- 普通 HTTP 抓取优先，只有 JS/WAF、TLS/网络和超时等可恢复外站错误才触发浏览器兜底。
- 响应超过来源 `maxBytes` 时转浏览器读取，不保存不完整的 HTTP 内容；同一来源同一 URL 的活动兜底任务抑制重复 HTTP。
- 参数校验、SSRF、停用来源和空 URL 等安全或配置错误不得转交浏览器。
- 浏览器正文必须带原始 URL、实际 URL、正文、抓取方式和逐字引用；搜索摘要不能作为唯一证据。
- 浏览器回传只能创建 artifact 和灰色建议值，不得直接写正式测算输入。
- 已有人工填写或人工覆盖的字段不被任何自动路径覆盖；C6/C7/C8 永远进入 `notDisclosed`。
- WorkBuddy 回传接口继续使用 `UE_AGENT_AGENT_TOKEN`，不在仓库、前端或 SQLite 中保存密钥。
- 不引入 Playwright、代理池、第三方浏览器服务或新的云端基础设施，保持本地一键移交能力。
- 不创建分支、worktree、提交、推送或生产部署；本轮只修改源码、测试和文档。

---

### Task 1: 为抓取错误增加分类和浏览器兜底元数据

**Files:**
- Modify: `services/api/app/crawlers/__init__.py`
- Modify: `services/api/app/domain/policy/service.py`
- Test: `services/api/tests/test_crawler.py`
- Test: `services/api/tests/test_crawl_api.py`

**Interfaces:**
- `CrawlError(message: str, *, http_status: int | None = None, error_code: str | None = None, fallback_action: str | None = None, fallback_reason: str | None = None)` 保存机器可读分类，同时保持 `str(error)` 的现有中文文案。
- `crawl_source()` 对 HTTP 412/403/429/5xx 返回 `fallback_action="browser_search"`；对连接、TLS、超时返回 `fallback_action="browser_search"`；对 URL/SSRF/大小/重定向安全错误不设置兜底动作。
- `PolicyService.fetch_for_agent()` 与 `crawl_source_now()` 的失败结果包含 `httpStatus`、`errorCode`、`fallbackAction`、`fallbackReason`，旧字段 `status` 和 `errorMessage` 保持兼容。

- [x] **Step 1: Write the failing tests**

```python
def test_http_412_exposes_browser_fallback_metadata(self):
    with self.assertRaises(CrawlError) as context:
        crawl_source(self._public("/challenge"), self.raw_dir, allow_private=True)

    error = context.exception
    self.assertEqual(error.http_status, 412)
    self.assertEqual(error.error_code, "HTTP_412_BROWSER_REQUIRED")
    self.assertEqual(error.fallback_action, "browser_search")
    self.assertEqual(error.fallback_reason, "js_challenge")

def test_private_url_does_not_expose_browser_fallback(self):
    with self.assertRaises(CrawlError) as context:
        crawl_source("http://127.0.0.1/policy", self.raw_dir)

    self.assertIsNone(context.exception.fallback_action)
```

- [x] **Step 2: Run the focused tests and verify they fail**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_crawler.py -v`

Expected: FAIL because `_QuietHandler` has no `/challenge` response metadata and `CrawlError` has no classification attributes.

- [x] **Step 3: Add the minimal error classification**

Make `CrawlError` retain the metadata. In `crawl_source`, raise an HTTP-specific error before content persistence:

```python
if response.status_code >= 400:
    status = response.status_code
    browser = status in {403, 412, 429} or status >= 500
    raise CrawlError(
        f"官网返回 HTTP {status}，未保存内容",
        http_status=status,
        error_code="HTTP_412_BROWSER_REQUIRED" if status == 412 else f"HTTP_{status}",
        fallback_action="browser_search" if browser else None,
        fallback_reason="js_challenge" if status == 412 else "http_blocked" if browser else None,
    )
```

Map timeout and connect/TLS exceptions to `NETWORK_BROWSER_FALLBACK` / `network_or_tls` while leaving invalid URL, SSRF, redirect and size-limit errors without fallback.

- [x] **Step 4: Propagate metadata without changing old behavior**

Create one helper in `PolicyService` that converts a `CrawlError` into the common response keys. Use it for single-source and agent batch fetch failure artifacts. Preserve the previous-success artifact and still mark the configured source as `error` until a later browser artifact succeeds.

- [x] **Step 5: Run crawler and crawl API regression tests**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_crawler.py services/api/tests/test_crawl_api.py -v`

Expected: existing tests pass, plus HTTP 412 returns browser metadata and SSRF does not.

### Task 2: Persist and expose browser-fetched artifacts

**Files:**
- Create: `services/api/migrations/sqlite/009_policy_browser_fallback.sql`
- Modify: `services/api/app/repository.py`
- Modify: `services/api/app/sqlite_repository.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/api/app/domain/policy/service.py`
- Modify: `services/api/app/api/routes.py`
- Test: `services/api/tests/test_policy_fallback.py`

**Interfaces:**
- `BrowserArtifactSubmit` contains `cityId`, `sourceId`, `researchRunId`, `requestedUrl`, `finalUrl`, `title`, `content`, `contentType`, and fixed `fetchMode="workbuddy_browser"`.
- `PolicyService.archive_browser_artifact(payload: Mapping[str, Any], *, raw_dir: Path) -> dict[str, Any]` creates or returns an idempotent standard crawl artifact.
- `POST /api/policies/browser-artifacts` requires the agent token and returns `{ "artifact": ..., "idempotent": bool }`.

- [x] **Step 1: Write the failing API and repository tests**

```python
def test_browser_artifact_requires_agent_token(self):
    response = self.client.post("/api/policies/browser-artifacts", json=self.browser_payload())
    self.assertEqual(response.status_code, 401)

def test_browser_artifact_is_saved_and_idempotent(self):
    first = self.client.post(
        "/api/policies/browser-artifacts",
        headers={"x-ue-agent-token": "test-token"},
        json=self.browser_payload(),
    )
    second = self.client.post(
        "/api/policies/browser-artifacts",
        headers={"x-ue-agent-token": "test-token"},
        json=self.browser_payload(),
    )
    self.assertEqual(first.status_code, 200)
    self.assertEqual(second.status_code, 200)
    self.assertEqual(first.json()["artifact"]["artifactId"], second.json()["artifact"]["artifactId"])
    self.assertTrue(second.json()["idempotent"])
```

- [x] **Step 2: Run the focused test and verify it fails**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_policy_fallback.py -v`

Expected: FAIL because the migration, schema, service method and route do not exist.

- [x] **Step 3: Add SQLite/JSON-compatible metadata**

Add nullable `fetch_mode`, `error_code`, `fallback_action`, and `fallback_reason` columns to `data_sources` and `crawl_artifacts`. Keep JSON repository payloads permissive. Add mappings in `SqliteProjectRepository` so old databases migrate in place and old artifacts continue returning null metadata.

- [x] **Step 4: Implement browser artifact archiving**

Validate `cityId` and required `sourceId` ownership, require http/https URLs without credentials, reject empty content and content over 200,000 UTF-8 characters, and require `fetchMode == "workbuddy_browser"`. Compute SHA256 from UTF-8 content, write `raw_sources/{sha256}.bin` atomically, compare the latest successful artifact for `first_fetch`/`unchanged`/`new_version`, and persist `contentType` as text/plain when the agent sends visible browser text. On success update the source to active, clear fallback metadata, set the latest fetch mode, and return the artifact. A repeated source/fingerprint returns the existing success artifact without a duplicate record.

- [x] **Step 5: Add the protected route and verify the full policy path**

Require `x-ue-agent-token` using the existing helper. If a `researchRunId` is provided, verify that the run city matches the payload city. Ensure `extraction-submissions` can locate the browser artifact text through the existing artifact content endpoint, so quote validation and field rules remain unchanged.

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_policy_fallback.py services/api/tests/test_agent_submission.py -v`

Expected: unauthorized, mismatch, invalid payload, archive, idempotency, quote validation and no-overwrite tests pass.

### Task 3: Make the WorkBuddy Skill automatically execute the fallback

**Files:**
- Modify: `.workbuddy/skills/policy-ai-crawler/SKILL.md`
- Modify: `.workbuddy/skills/policy-city-onboarding/SKILL.md`
- Modify: `.workbuddy/automations/policy-ai-sync.template.json`
- Modify: `services/api/tests/test_documentation_contract.py`

**Interfaces:**
- `fetch-requests` failure results with `fallbackAction=browser_search` are actionable work items, not terminal errors.
- WorkBuddy calls `/api/policies/browser-artifacts` before `/api/policies/extraction-submissions` for browser-retrieved text.

- [x] **Step 1: Add documentation-contract tests**

```python
def test_skill_documents_browser_fallback_protocol(self):
    skill = (REPO_ROOT / ".workbuddy/skills/policy-ai-crawler/SKILL.md").read_text(encoding="utf-8")
    self.assertIn("browser-artifacts", skill)
    self.assertIn("fallbackAction", skill)
    self.assertIn("browser_search", skill)
    self.assertIn("不反复重试", skill)
```

- [x] **Step 2: Run the documentation test and verify it fails**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_documentation_contract.py -v`

Expected: FAIL because the skill has no browser artifact callback sequence.

- [x] **Step 3: Add the generic fallback loop**

Document the exact sequence for every city: call `fetch-requests`; collect failed results with `fallbackAction=browser_search`; open the original URL in the browser; if blocked, search exact title plus city/current year and prefer official mirrors/PDFs; send visible正文 to `browser-artifacts`; use returned `artifactId` in `extraction-submissions`; record unresolved fields in `notDisclosed`; call `complete` with `partial_failed` when any target remains unresolved. Prohibit repeating the same blocked URL and prohibit search summaries without a quote.

- [x] **Step 4: Cover onboarding and scheduled all-city runs**

Update onboarding and the global automation instructions so a newly discovered city uses the same fallback loop before completion. The automation must continue through all cities sequentially, include fallback counts in its final summary, and never create per-city schedules or overwrite manual/overridden parameters.

- [x] **Step 5: Run the contract tests**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_documentation_contract.py -v`

Expected: all documentation assertions pass.

### Task 4: Fix source and city status presentation

**Files:**
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/app/domain/policy/service.py`
- Modify: `apps/web/lib/policies.ts`
- Modify: `apps/web/components/policy-city-detail.tsx`
- Modify: `apps/web/components/policy-overview.tsx`
- Test: `services/api/tests/test_policy_fallback.py`
- Test: `apps/web/components/policy-overview.test.tsx`

**Interfaces:**
- API source objects expose `fallbackAction`, `fallbackReason`, and `fetchMode` when known.
- API city summaries expose `fallbackRequiredCount` and `sourceStatus="partial_failed" | "fallback_required"` where applicable.
- Existing `DataSourceStatus` values remain backward compatible; UI status labels add “需浏览器通道” and “部分失败”.

- [x] **Step 1: Write failing status tests**

```tsx
it("部分来源失败时不显示为完全正常", () => {
  render(<PolicyCityStatus summary={{ sourceCount: 6, activeSourceCount: 2, errorSourceCount: 4, fallbackRequiredCount: 4 }} />);
  expect(screen.getByText("部分失败")).toBeInTheDocument();
  expect(screen.queryByText("正常")).not.toBeInTheDocument();
});
```

- [x] **Step 2: Run focused frontend tests and verify they fail**

Run: `pnpm --filter @ue-agent/web exec vitest run components/policy-fallback-status.test.tsx`

Expected: FAIL because the status component and fields do not exist.

- [x] **Step 3: Derive and render fallback state**

Make the city summary prioritize partial failures over active sources. Count sources whose latest state requests browser fallback. Add source row badges and crawl-history metadata for `fetchMode` and fallback reason. Keep historical failed artifacts visible, but distinguish them from current source state.

- [x] **Step 4: Add retry guidance without auto-looping**

For a browser-required source, show “交给 WorkBuddy 浏览器兜底” guidance and do not automatically retry the same blocked URL in the browser UI. Keep the existing manual “立即抓取” action available.

- [x] **Step 5: Run focused frontend tests**

Run: `pnpm --filter @ue-agent/web exec vitest run components/policy-fallback-status.test.tsx components/policy-overview.test.tsx`

Expected: status and existing policy overview tests pass.

### Task 5: Add end-to-end acceptance coverage and documentation

**Files:**
- Modify: `scripts/e2e_assert.py`
- Modify: `scripts/e2e-agent-flow.sh`
- Modify: `README.md`
- Modify: `services/api/README.md`
- Modify: `docs/deployment/portable-handoff.md`
- Modify: `docs/deployment/local.md`
- Test: `services/api/tests/test_policy_fallback.py`

**Interfaces:**
- E2E fixture exposes a deterministic HTTP 412 page and validates the browser artifact callback path.
- Delivery docs explain that WorkBuddy must have browser access to complete the fallback; if it cannot access a page, the task remains partial and fields are not disclosed.

- [x] **Step 1: Add a deterministic fixture test**

```python
def test_412_to_browser_artifact_to_extraction_preserves_evidence(self):
    failed = self.client.post("/api/policies/fetch-requests", headers=self.agent_headers, json={"requests": [self.blocked_request]}).json()
    self.assertEqual(failed["results"][0]["fallbackAction"], "browser_search")
    artifact = self.client.post("/api/policies/browser-artifacts", headers=self.agent_headers, json=self.browser_payload()).json()
    self.assertTrue(artifact["artifact"]["storedPath"])
```

- [x] **Step 2: Run the fixture test and verify it fails**

Run: `PYTHONPATH=services/api uv run --project services/api --extra test python -m unittest services/api/tests/test_policy_fallback.py -v`

Expected: FAIL until the complete fallback path is implemented.

- [x] **Step 3: Update E2E assertions and docs**

Assert that HTTP 412 is classified as browser-required, browser text is saved locally, the artifact is linked to the research run, and the downstream extraction still requires a quote. Document the local API URL, token header, WorkBuddy one-time setup, and the no-fabrication behavior for unresolved sources.

- [x] **Step 4: Run the complete verification suite**

Run:

```bash
pnpm api:test
pnpm test
pnpm typecheck
pnpm lint
pnpm build
pnpm handoff:check
```

Expected: backend, frontend, typecheck, lint, build and portable handoff checks pass.

- [x] **Step 5: Verify a clean implementation report**

Run: `git diff --check && git status --short`

Report the exact files changed, the deterministic fallback test result, and whether a live WorkBuddy browser run was executed. Do not claim live Chengdu recovery unless WorkBuddy actually returned and the API stored a browser artifact.

### Task 6: Turn fallback failures into a retryable queue and prevent repeat requests

**Files:**
- Create: `services/api/migrations/sqlite/010_policy_fallback_tasks.sql`
- Modify: `services/api/app/repository.py`
- Modify: `services/api/app/sqlite_repository.py`
- Modify: `services/api/app/crawlers/__init__.py`
- Modify: `services/api/app/domain/policy/service.py`
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `.workbuddy/skills/policy-ai-crawler/SKILL.md`
- Modify: `.workbuddy/automations/policy-ai-sync.template.json`
- Modify: `apps/web/lib/policies.ts`
- Modify: `apps/web/components/policy-city-detail.tsx`
- Modify: `apps/web/app/(workspace)/policies/[cityId]/page.tsx`
- Test: `services/api/tests/test_policy_fallback.py`

- [x] **Step 1: Add failing regression tests**

Cover oversized response classification, one task for repeated 412 failures, retry suppression, claim attempts,
browser artifact auto-archival, and SQLite round-trip.

- [x] **Step 2: Implement task persistence and lifecycle**

Add JSON/SQLite repositories and the `GET`/`claim`/`fail` API. Existing 009-era failure artifacts backfill a task on
the first retry, so historical blocked sources also stop being repeatedly requested.

- [x] **Step 3: Integrate the queue into HTTP and browser paths**

Classify oversized responses as `CONTENT_TOO_LARGE_BROWSER_FALLBACK`; create or reuse a task for all browser fallback
errors; return `browser_required` for an active task; archive the matching task when browser text is persisted.

- [x] **Step 4: Update UI and WorkBuddy automation**

Show an actionable queue card and copyable task prompt, change batch wording to “批量请求已结束”, disable the
per-source HTTP button while queued, and make the scheduled Skill process queued/failed tasks first.

- [x] **Step 5: Run final verification after the queue patch**

Run the API fallback test, all API tests, frontend tests, typecheck, lint, build, E2E and handoff checks. Do not claim
completion until every command returns success; a live browser recovery is not part of local automated verification.
