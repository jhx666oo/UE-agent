-- 来源配置增强：抓取超时、大小上限、备注与最近抓取状态（PRD 11.5）
ALTER TABLE data_sources ADD COLUMN timeout_seconds INTEGER;
ALTER TABLE data_sources ADD COLUMN max_bytes INTEGER;
ALTER TABLE data_sources ADD COLUMN note TEXT;
ALTER TABLE data_sources ADD COLUMN last_fetched_at TEXT;
ALTER TABLE data_sources ADD COLUMN last_http_status INTEGER;
ALTER TABLE data_sources ADD COLUMN last_change_status TEXT;
