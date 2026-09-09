-- 场景级字段值：爬虫建议值与采用/覆盖状态（PRD 12.2 / 13.2）
-- currentValue 的权威来源仍是 scenarios.inputs_json（计算引擎直接消费），
-- 本表只保存建议值、建议来源、值状态与操作历史，避免双写不一致。

CREATE TABLE IF NOT EXISTS scenario_field_values (
  scenario_id          TEXT NOT NULL REFERENCES scenarios (id) ON DELETE CASCADE,
  field_id             TEXT NOT NULL,
  suggested_value_json TEXT,
  suggested_source_json TEXT,
  suggested_at         TEXT,
  value_state          TEXT NOT NULL,
  updated_at           TEXT NOT NULL,
  PRIMARY KEY (scenario_id, field_id)
);

CREATE INDEX IF NOT EXISTS idx_scenario_field_values_field_id ON scenario_field_values (field_id);
CREATE INDEX IF NOT EXISTS idx_scenario_field_values_state ON scenario_field_values (value_state);

CREATE TABLE IF NOT EXISTS scenario_field_value_history (
  id             TEXT PRIMARY KEY,
  scenario_id    TEXT NOT NULL,
  field_id       TEXT NOT NULL,
  action         TEXT NOT NULL,
  old_value_json TEXT,
  new_value_json TEXT,
  source_json    TEXT,
  acted_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_field_value_history_scenario ON scenario_field_value_history (scenario_id);
CREATE INDEX IF NOT EXISTS idx_field_value_history_field ON scenario_field_value_history (scenario_id, field_id);
