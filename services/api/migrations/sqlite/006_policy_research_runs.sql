-- WorkBuddy 按需实时政策检索任务与查询审计。
CREATE TABLE IF NOT EXISTS policy_research_runs (
  id TEXT PRIMARY KEY,
  city_id TEXT NOT NULL,
  project_id TEXT,
  trigger TEXT NOT NULL,
  scope_json TEXT NOT NULL DEFAULT '"all"',
  fields_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL,
  phase TEXT NOT NULL,
  agent_run_id TEXT,
  agent_version TEXT,
  query_count INTEGER NOT NULL DEFAULT 0,
  source_count INTEGER NOT NULL DEFAULT 0,
  new_source_count INTEGER NOT NULL DEFAULT 0,
  changed_source_count INTEGER NOT NULL DEFAULT 0,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  suggestion_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  errors_json TEXT NOT NULL DEFAULT '[]',
  task_prompt TEXT,
  requested_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_research_runs_city
  ON policy_research_runs (city_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_policy_research_runs_status
  ON policy_research_runs (status, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_policy_research_runs_city_active
  ON policy_research_runs (city_id)
  WHERE status IN ('queued','researching','fetching','extracting','awaiting_review');

CREATE TABLE IF NOT EXISTS policy_research_queries (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  family TEXT NOT NULL,
  query TEXT NOT NULL,
  status TEXT NOT NULL,
  result_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  searched_at TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_research_queries_run
  ON policy_research_queries (run_id, created_at ASC);
