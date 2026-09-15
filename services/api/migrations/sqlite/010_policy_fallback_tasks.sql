-- 可执行的 WorkBuddy 浏览器兜底任务。
-- 同一来源的 queued/in_progress 任务会抑制重复 HTTP，避免 WAF、超时和大文件来源被反复撞击。
CREATE TABLE IF NOT EXISTS policy_fallback_tasks (
  id               TEXT PRIMARY KEY,
  city_id          TEXT NOT NULL,
  source_id        TEXT NOT NULL,
  research_run_id  TEXT,
  requested_url    TEXT NOT NULL,
  source_name      TEXT,
  status           TEXT NOT NULL DEFAULT 'queued',
  http_status      INTEGER,
  error_code       TEXT,
  fallback_action  TEXT NOT NULL DEFAULT 'browser_search',
  fallback_reason  TEXT,
  attempts         INTEGER NOT NULL DEFAULT 0,
  artifact_id      TEXT,
  last_error       TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES data_sources (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_policy_fallback_tasks_city_status
  ON policy_fallback_tasks (city_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_policy_fallback_tasks_source_url
  ON policy_fallback_tasks (source_id, requested_url, status);
