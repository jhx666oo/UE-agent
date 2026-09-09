"""把既有单文件 JSON 数据原样搬进本地 SQLite。

只做搬运，不生成或改写任何业务值：主键、外键、状态、时间和快照内容
全部沿用源文件，保证历史结果在迁移后仍可复核。目标库已有项目时直接跳过，
重复执行不会覆盖也不会重复导入。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # 允许直接以脚本方式运行
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.repository import normalize_store_payload
from app.sqlite_repository import DATABASE_NAME, default_data_dir, initialize_database


@dataclass(frozen=True)
class MigrationReport:
    projects: int = 0
    scenarios: int = 0
    snapshots: int = 0
    data_sources: int = 0
    policy_documents: int = 0
    policy_facts: int = 0
    applied: bool = False
    skipped_reason: str | None = None

    def summary(self) -> str:
        if not self.applied:
            return f"未迁移：{self.skipped_reason}"
        return (
            f"已迁移 项目 {self.projects}、场景 {self.scenarios}、快照 {self.snapshots}、"
            f"数据来源 {self.data_sources}、政策文件 {self.policy_documents}、"
            f"政策字段 {self.policy_facts}"
        )


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _text(row: dict[str, Any], key: str, default: str = "") -> str:
    value = row.get(key)
    return default if value is None else str(value)


def migrate_json_to_sqlite(json_path: Path, database_path: Path) -> MigrationReport:
    json_path = Path(json_path)
    database_path = Path(database_path)
    if not json_path.is_file():
        return MigrationReport(applied=False, skipped_reason="source file not found")

    payload = normalize_store_payload(json.loads(json_path.read_text(encoding="utf-8")))
    if not payload["projects"]:
        return MigrationReport(applied=False, skipped_reason="source contains no projects")

    initialize_database(database_path)
    connection = sqlite3.connect(str(database_path), timeout=30)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        existing = int(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0])
        if existing:
            return MigrationReport(applied=False, skipped_reason="target already contains projects")

        with connection:
            for project in payload["projects"]:
                connection.execute(
                    "INSERT INTO projects (id, name, city_id, city, district, base_month, station_mode,"
                    " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _text(project, "id"),
                        _text(project, "name"),
                        project.get("cityId"),
                        _text(project, "city"),
                        project.get("district"),
                        project.get("baseMonth"),
                        _text(project, "stationMode", "自营"),
                        _text(project, "createdAt"),
                        _text(project, "updatedAt"),
                    ),
                )
                for scenario in project.get("scenarios", []):
                    result = scenario.get("result")
                    connection.execute(
                        "INSERT INTO scenarios (id, project_id, name, status, inputs_json, result_json,"
                        " input_snapshot_json, result_snapshot_id, calculated_at, confirmed_at, created_at,"
                        " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            _text(scenario, "id"),
                            _text(project, "id"),
                            _text(scenario, "name"),
                            _text(scenario, "status", "draft"),
                            _dump(scenario.get("inputs") or {}),
                            None if result is None else _dump(result),
                            _dump(scenario.get("inputSnapshot") or {}),
                            scenario.get("resultSnapshotId"),
                            scenario.get("calculatedAt"),
                            scenario.get("confirmedAt"),
                            _text(scenario, "createdAt"),
                            _text(scenario, "updatedAt"),
                        ),
                    )

            for snapshot in payload.get("calculationSnapshots", []):
                connection.execute(
                    "INSERT INTO calculation_snapshots (id, project_id, scenario_id, model_version, status,"
                    " calculated_at, input_snapshot_json, result_snapshot_json, issues_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _text(snapshot, "snapshotId"),
                        _text(snapshot, "projectId"),
                        _text(snapshot, "scenarioId"),
                        snapshot.get("modelVersion"),
                        _text(snapshot, "status", "blocked"),
                        _text(snapshot, "calculatedAt"),
                        _dump(snapshot.get("inputSnapshot") or {}),
                        _dump(snapshot.get("resultSnapshot") or {}),
                        _dump(snapshot.get("issues") or []),
                    ),
                )

            for source in payload.get("dataSources", []):
                connection.execute(
                    "INSERT INTO data_sources (id, city_id, name, kind, url, status, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _text(source, "id"),
                        _text(source, "cityId"),
                        _text(source, "name"),
                        _text(source, "kind", "web"),
                        source.get("url"),
                        _text(source, "status", "active"),
                        _text(source, "createdAt"),
                        _text(source, "updatedAt"),
                    ),
                )

            for document in payload.get("policyDocuments", []):
                connection.execute(
                    "INSERT INTO policy_documents (id, city_id, original_name, mime_type, size, sha256, source,"
                    " stored_path, stored_url, status, uploaded_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _text(document, "id"),
                        _text(document, "cityId"),
                        _text(document, "originalName"),
                        _text(document, "mimeType", "application/octet-stream"),
                        int(document.get("size") or 0),
                        _text(document, "sha256"),
                        _text(document, "source"),
                        _text(document, "storedPath"),
                        _text(document, "storedUrl"),
                        _text(document, "status", "uploaded"),
                        _text(document, "uploadedAt"),
                        _text(document, "updatedAt"),
                    ),
                )

            for fact in payload.get("policyFacts", []):
                confidence = fact.get("confidence")
                connection.execute(
                    "INSERT INTO policy_facts (id, document_id, city_id, field_id, value_json, unit,"
                    " confidence_json, source, status, reviewer, reviewed_at, effective_date, created_at,"
                    " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _text(fact, "id"),
                        _text(fact, "documentId"),
                        _text(fact, "cityId"),
                        _text(fact, "fieldId"),
                        _dump(fact.get("value")),
                        fact.get("unit"),
                        None if confidence is None else _dump(confidence),
                        fact.get("source"),
                        _text(fact, "status", "candidate"),
                        fact.get("reviewer"),
                        fact.get("reviewedAt"),
                        fact.get("effectiveDate"),
                        _text(fact, "createdAt"),
                        _text(fact, "updatedAt"),
                    ),
                )

            for row in payload.get("fieldValues", []):
                connection.execute(
                    "INSERT INTO scenario_field_values (scenario_id, field_id, suggested_value_json,"
                    " suggested_source_json, suggested_at, value_state, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (scenario_id, field_id) DO UPDATE SET"
                    " suggested_value_json = excluded.suggested_value_json,"
                    " suggested_source_json = excluded.suggested_source_json,"
                    " suggested_at = excluded.suggested_at,"
                    " value_state = excluded.value_state, updated_at = excluded.updated_at",
                    (
                        _text(row, "scenarioId"),
                        _text(row, "fieldId"),
                        _dump(row.get("suggestedValue")),
                        _dump(row.get("suggestedSource")),
                        row.get("suggestedAt"),
                        _text(row, "valueState", "suggestion_ready"),
                        _text(row, "updatedAt"),
                    ),
                )

            for entry in payload.get("fieldValueHistory", []):
                connection.execute(
                    "INSERT INTO scenario_field_value_history (id, scenario_id, field_id, action,"
                    " old_value_json, new_value_json, source_json, acted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _text(entry, "id"),
                        _text(entry, "scenarioId"),
                        _text(entry, "fieldId"),
                        _text(entry, "action"),
                        _dump(entry.get("oldValue")),
                        _dump(entry.get("newValue")),
                        _dump(entry.get("source")),
                        _text(entry, "actedAt"),
                    ),
                )

        counts = {
            "projects": int(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]),
            "scenarios": int(connection.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0]),
            "snapshots": int(
                connection.execute("SELECT COUNT(*) FROM calculation_snapshots").fetchone()[0]
            ),
            "data_sources": int(connection.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]),
            "policy_documents": int(
                connection.execute("SELECT COUNT(*) FROM policy_documents").fetchone()[0]
            ),
            "policy_facts": int(connection.execute("SELECT COUNT(*) FROM policy_facts").fetchone()[0]),
        }
    finally:
        connection.close()

    return MigrationReport(applied=True, **counts)


def default_json_path() -> Path:
    return default_data_dir() / "projects.json"


def default_sqlite_path() -> Path:
    return default_data_dir() / DATABASE_NAME


def main() -> int:
    parser = argparse.ArgumentParser(description="导入单文件 JSON 数据到本地 SQLite")
    parser.add_argument("--json", type=Path, default=default_json_path(), help="源 projects.json 路径")
    parser.add_argument("--database", type=Path, default=default_sqlite_path(), help="目标 SQLite 路径")
    arguments = parser.parse_args()

    report = migrate_json_to_sqlite(arguments.json, arguments.database)
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
