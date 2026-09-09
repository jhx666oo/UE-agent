-- UE Agent 本地 SQLite 初始结构
-- 可重复执行：所有对象使用 IF NOT EXISTS，业务值不在迁移中生成。
-- 结构化业务 ID、状态、城市、时间和编号独立成列并建索引；
-- 只有输入快照、结果快照、问题列表和值负载使用 JSON 文本列。

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  name       TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  city_id      TEXT,
  city         TEXT NOT NULL,
  district     TEXT,
  base_month   TEXT,
  station_mode TEXT NOT NULL DEFAULT '自营',
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_city_id ON projects (city_id);

CREATE TABLE IF NOT EXISTS scenarios (
  id                TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  status            TEXT NOT NULL,
  inputs_json       TEXT NOT NULL DEFAULT '{}',
  result_json       TEXT,
  input_snapshot_json TEXT NOT NULL DEFAULT '{}',
  result_snapshot_id TEXT,
  calculated_at     TEXT,
  confirmed_at      TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scenarios_project_id ON scenarios (project_id);
CREATE INDEX IF NOT EXISTS idx_scenarios_status ON scenarios (status);
CREATE INDEX IF NOT EXISTS idx_scenarios_updated_at ON scenarios (updated_at DESC);

CREATE TABLE IF NOT EXISTS calculation_snapshots (
  id                  TEXT PRIMARY KEY,
  project_id          TEXT NOT NULL,
  scenario_id         TEXT NOT NULL,
  model_version       TEXT,
  status              TEXT NOT NULL,
  calculated_at       TEXT NOT NULL,
  input_snapshot_json TEXT NOT NULL DEFAULT '{}',
  result_snapshot_json TEXT NOT NULL DEFAULT '{}',
  issues_json         TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_calculation_snapshots_project_id ON calculation_snapshots (project_id);
CREATE INDEX IF NOT EXISTS idx_calculation_snapshots_scenario_id ON calculation_snapshots (scenario_id);
CREATE INDEX IF NOT EXISTS idx_calculation_snapshots_calculated_at ON calculation_snapshots (calculated_at DESC);

CREATE TABLE IF NOT EXISTS data_sources (
  id         TEXT PRIMARY KEY,
  city_id    TEXT NOT NULL,
  name       TEXT NOT NULL,
  kind       TEXT NOT NULL,
  url        TEXT,
  status     TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_data_sources_city_id ON data_sources (city_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_updated_at ON data_sources (updated_at DESC);

CREATE TABLE IF NOT EXISTS policy_documents (
  id            TEXT PRIMARY KEY,
  city_id       TEXT NOT NULL,
  original_name TEXT NOT NULL,
  mime_type     TEXT NOT NULL,
  size          INTEGER NOT NULL,
  sha256        TEXT NOT NULL,
  source        TEXT NOT NULL,
  stored_path   TEXT NOT NULL,
  stored_url    TEXT NOT NULL,
  status        TEXT NOT NULL,
  uploaded_at   TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_documents_city_id ON policy_documents (city_id);
CREATE INDEX IF NOT EXISTS idx_policy_documents_sha256 ON policy_documents (sha256);
CREATE INDEX IF NOT EXISTS idx_policy_documents_updated_at ON policy_documents (updated_at DESC);

CREATE TABLE IF NOT EXISTS policy_facts (
  id            TEXT PRIMARY KEY,
  document_id   TEXT NOT NULL REFERENCES policy_documents (id) ON DELETE CASCADE,
  city_id       TEXT NOT NULL,
  field_id      TEXT NOT NULL,
  value_json    TEXT,
  unit          TEXT,
  confidence_json TEXT,
  source        TEXT,
  status        TEXT NOT NULL,
  reviewer      TEXT,
  reviewed_at   TEXT,
  effective_date TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_facts_field_id ON policy_facts (field_id);
CREATE INDEX IF NOT EXISTS idx_policy_facts_city_id ON policy_facts (city_id);
CREATE INDEX IF NOT EXISTS idx_policy_facts_document_id ON policy_facts (document_id);
CREATE INDEX IF NOT EXISTS idx_policy_facts_status ON policy_facts (status);

CREATE TABLE IF NOT EXISTS crawl_artifacts (
  id             TEXT PRIMARY KEY,
  source_id      TEXT NOT NULL,
  city_id        TEXT NOT NULL,
  requested_url  TEXT NOT NULL,
  final_url      TEXT,
  fetched_at     TEXT NOT NULL,
  http_status    INTEGER,
  content_type   TEXT,
  content_length INTEGER,
  sha256         TEXT,
  stored_path    TEXT,
  title          TEXT,
  change_status  TEXT,
  status         TEXT NOT NULL,
  error_message  TEXT,
  created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_crawl_artifacts_source_id ON crawl_artifacts (source_id);
CREATE INDEX IF NOT EXISTS idx_crawl_artifacts_city_id ON crawl_artifacts (city_id);
CREATE INDEX IF NOT EXISTS idx_crawl_artifacts_fetched_at ON crawl_artifacts (fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_artifacts_sha256 ON crawl_artifacts (sha256);
