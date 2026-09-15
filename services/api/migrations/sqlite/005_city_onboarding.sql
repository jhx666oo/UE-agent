-- 新增城市自动发现来源、抓取与建议值同步的可恢复任务。
CREATE TABLE IF NOT EXISTS city_onboarding_jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  city_id TEXT NOT NULL,
  city_name TEXT NOT NULL,
  status TEXT NOT NULL,
  phase TEXT NOT NULL,
  total_queries INTEGER NOT NULL DEFAULT 0,
  discovered_count INTEGER NOT NULL DEFAULT 0,
  official_source_count INTEGER NOT NULL DEFAULT 0,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  crawled_count INTEGER NOT NULL DEFAULT 0,
  suggestion_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT NOT NULL DEFAULT '[]',
  started_at TEXT,
  finished_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_city_onboarding_project
  ON city_onboarding_jobs (project_id, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_city_onboarding_project_active
  ON city_onboarding_jobs(project_id)
  WHERE status IN ('queued','discovering','sources_ready','crawling','extracting');
