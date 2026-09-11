-- AI 回传链路（WorkBuddy 驱动架构，见 docs/superpowers/specs/2026-09-10-policy-ai-crawl-design.md 第 8 节）
--
-- 背景：AI 检索与字段抽取由 WorkBuddy 执行，结果经 HTTP 回传落库。
-- 本迁移新增两张表：
--   1. candidate_sources          —— AI 检索发现的候选来源，人工确认后才转正式 DataSource
--   2. extraction_submissions     —— 每次回传的审计记录（agentRunId、校验结果、接收计数）
--
-- 注意：scenario_field_values.suggested_source_json 本身就是 JSON 列，
-- confidence / quote 直接扩展该 JSON 结构即可，无需 ALTER TABLE。

CREATE TABLE IF NOT EXISTS candidate_sources (
  id             TEXT PRIMARY KEY,
  city_id        TEXT NOT NULL,
  name           TEXT NOT NULL,
  url            TEXT NOT NULL,
  domain         TEXT,
  title          TEXT,
  published_at   TEXT,
  summary        TEXT,
  -- 该来源预期覆盖的参数编号，JSON 数组，如 ["P1","P2"]
  target_fields_json TEXT,
  -- AI 判断的相关度 0-1
  relevance_json TEXT,
  origin         TEXT NOT NULL DEFAULT 'ai_search',
  status         TEXT NOT NULL DEFAULT 'candidate',
  -- 转正式来源后回填
  promoted_source_id TEXT,
  reviewed_by    TEXT,
  reviewed_at    TEXT,
  note           TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidate_sources_city ON candidate_sources (city_id);
CREATE INDEX IF NOT EXISTS idx_candidate_sources_status ON candidate_sources (status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_sources_city_url ON candidate_sources (city_id, url);

CREATE TABLE IF NOT EXISTS extraction_submissions (
  id                TEXT PRIMARY KEY,
  city_id           TEXT,
  source_id         TEXT,
  artifact_id       TEXT,
  agent_run_id      TEXT,
  agent_version     TEXT,
  -- 回传原文，供审计追溯
  payload_json      TEXT NOT NULL,
  -- 校验结果：accepted / partially_rejected / rejected
  result_status     TEXT NOT NULL,
  accepted_count    INTEGER NOT NULL DEFAULT 0,
  rejected_count    INTEGER NOT NULL DEFAULT 0,
  rejection_json    TEXT,
  submitted_at      TEXT NOT NULL,
  created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_extraction_submissions_city ON extraction_submissions (city_id);
CREATE INDEX IF NOT EXISTS idx_extraction_submissions_source ON extraction_submissions (source_id);
CREATE INDEX IF NOT EXISTS idx_extraction_submissions_run ON extraction_submissions (agent_run_id);
CREATE INDEX IF NOT EXISTS idx_extraction_submissions_at ON extraction_submissions (submitted_at DESC);
