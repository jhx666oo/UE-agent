-- 记录 HTTP 抓取失败后的 WorkBuddy 浏览器兜底，以及回传原文的来源链路。
ALTER TABLE data_sources ADD COLUMN last_fetch_mode TEXT;
ALTER TABLE data_sources ADD COLUMN last_error_code TEXT;
ALTER TABLE data_sources ADD COLUMN last_fallback_action TEXT;
ALTER TABLE data_sources ADD COLUMN last_fallback_reason TEXT;

ALTER TABLE crawl_artifacts ADD COLUMN fetch_mode TEXT;
ALTER TABLE crawl_artifacts ADD COLUMN error_code TEXT;
ALTER TABLE crawl_artifacts ADD COLUMN fallback_action TEXT;
ALTER TABLE crawl_artifacts ADD COLUMN fallback_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_crawl_artifacts_fallback_action
  ON crawl_artifacts (fallback_action, fetched_at DESC);
