-- 把 WorkBuddy 回传的来源与抽取审计关联到一次实时检索任务。
ALTER TABLE candidate_sources ADD COLUMN research_run_id TEXT;
ALTER TABLE extraction_submissions ADD COLUMN research_run_id TEXT;

CREATE INDEX IF NOT EXISTS idx_candidate_sources_research_run
  ON candidate_sources (research_run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_extraction_submissions_research_run
  ON extraction_submissions (research_run_id, submitted_at DESC);
