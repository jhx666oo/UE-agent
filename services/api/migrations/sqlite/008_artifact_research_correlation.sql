-- 关联 WorkBuddy 实时检索任务与 API 保存的原文版本。
ALTER TABLE crawl_artifacts ADD COLUMN research_run_id TEXT;

CREATE INDEX IF NOT EXISTS idx_crawl_artifacts_research_run
  ON crawl_artifacts (research_run_id, fetched_at DESC);
