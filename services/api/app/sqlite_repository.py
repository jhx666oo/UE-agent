"""本地 SQLite 仓储。

与 JsonProjectRepository 保持完全相同的方法契约和返回结构，差别只在存储位置：
业务 ID、状态、城市、时间和 Excel 编号使用独立列并建立索引，只有输入快照、
结果快照、问题列表和值负载保存为 JSON 文本列。所有写入走事务，
文件实体继续通过 PolicyFileStore 落盘。
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from .repository import LocalPolicyFileStore, PolicyFileStore, new_id, utc_now

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "sqlite"
DATABASE_NAME = "ue-agent.sqlite3"

# data_sources 新增列（003 迁移）-> API 字段名映射
SQLITE_SOURCE_KEYS = {
    "timeout_seconds": "timeoutSeconds",
    "max_bytes": "maxBytes",
    "note": "note",
    "last_fetched_at": "lastFetchedAt",
    "last_http_status": "lastHttpStatus",
    "last_change_status": "lastChangeStatus",
}


def default_data_dir() -> Path:
    configured = os.getenv("UE_AGENT_DATA_DIR")
    if configured:
        return Path(configured)
    return DATA_ROOT


def default_database_path() -> Path:
    configured = os.getenv("UE_AGENT_DB_FILE")
    if configured:
        return Path(configured)
    return default_data_dir() / DATABASE_NAME


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(Path(path)), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def run_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row["name"] for row in connection.execute("SELECT name FROM schema_migrations")}
    for script in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if script.name in applied:
            continue
        with connection:
            connection.executescript(script.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (script.name, utc_now()),
            )


def initialize_database(path: Path | None = None) -> Path:
    database = Path(path or default_database_path())
    database.parent.mkdir(parents=True, exist_ok=True)
    (database.parent / "policy_files").mkdir(parents=True, exist_ok=True)
    (database.parent / "raw_sources").mkdir(parents=True, exist_ok=True)
    connection = connect_database(database)
    try:
        run_migrations(connection)
    finally:
        connection.close()
    return database


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(text: str | None, default: Any = None) -> Any:
    if text is None:
        return default
    return json.loads(text)


class SqliteProjectRepository:
    """可交付给业务侧独立运行的本地数据库仓储。"""

    def __init__(self, path: Path, file_store: PolicyFileStore | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        initialize_database(self.path)
        self.file_store = file_store or LocalPolicyFileStore(self.path.parent)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        connection = connect_database(self.path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    # ---------- 行映射 ----------
    @staticmethod
    def _scenario_dict(row: sqlite3.Row) -> dict[str, Any]:
        scenario: dict[str, Any] = {
            "id": row["id"],
            "name": row["name"],
            "inputs": _load(row["inputs_json"], {}),
            "result": _load(row["result_json"]),
            "inputSnapshot": _load(row["input_snapshot_json"], {}),
            "resultSnapshotId": row["result_snapshot_id"],
            "calculatedAt": row["calculated_at"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        if row["confirmed_at"] is not None:
            scenario["confirmedAt"] = row["confirmed_at"]
        return scenario

    @staticmethod
    def _project_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "cityId": row["city_id"],
            "city": row["city"],
            "district": row["district"],
            "baseMonth": row["base_month"],
            "stationMode": row["station_mode"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "scenarios": [],
        }

    @staticmethod
    def _snapshot_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "snapshotId": row["id"],
            "projectId": row["project_id"],
            "scenarioId": row["scenario_id"],
            "inputSnapshot": _load(row["input_snapshot_json"], {}),
            "resultSnapshot": _load(row["result_snapshot_json"], {}),
            "modelVersion": row["model_version"],
            "calculatedAt": row["calculated_at"],
            "status": row["status"],
            "issues": _load(row["issues_json"], []),
        }

    @staticmethod
    def _data_source_dict(row: sqlite3.Row) -> dict[str, Any]:
        source = {
            "id": row["id"],
            "cityId": row["city_id"],
            "name": row["name"],
            "kind": row["kind"],
            "url": row["url"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        # 抓取配置与最近抓取状态（003 迁移新增列；旧库可能尚未迁移）
        for key in ("timeout_seconds", "max_bytes", "note", "last_fetched_at", "last_http_status", "last_change_status"):
            try:
                value = row[key]
            except (IndexError, KeyError):
                value = None
            if value is not None:
                source[SQLITE_SOURCE_KEYS[key]] = value
        return source

    @staticmethod
    def _document_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "cityId": row["city_id"],
            "originalName": row["original_name"],
            "mimeType": row["mime_type"],
            "size": row["size"],
            "sha256": row["sha256"],
            "source": row["source"],
            "storedPath": row["stored_path"],
            "storedUrl": row["stored_url"],
            "status": row["status"],
            "uploadedAt": row["uploaded_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _fact_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "documentId": row["document_id"],
            "cityId": row["city_id"],
            "fieldId": row["field_id"],
            "value": _load(row["value_json"]),
            "unit": row["unit"],
            "confidence": _load(row["confidence_json"]),
            "source": row["source"],
            "status": row["status"],
            "reviewer": row["reviewer"],
            "reviewedAt": row["reviewed_at"],
            "effectiveDate": row["effective_date"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    # ---------- 项目与场景 ----------
    def list_projects(self) -> list[dict[str, Any]]:
        with self._db() as connection:
            projects = [
                self._project_dict(row)
                for row in connection.execute("SELECT * FROM projects ORDER BY updated_at DESC")
            ]
            scenarios = list(
                connection.execute("SELECT * FROM scenarios ORDER BY created_at ASC, id ASC")
            )
        by_project: dict[str, list[dict[str, Any]]] = {}
        for row in scenarios:
            by_project.setdefault(row["project_id"], []).append(self._scenario_dict(row))
        for project in projects:
            project["scenarios"] = by_project.get(project["id"], [])
        return projects

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self._db() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                raise KeyError(project_id)
            project = self._project_dict(row)
            project["scenarios"] = [
                self._scenario_dict(scenario)
                for scenario in connection.execute(
                    "SELECT * FROM scenarios WHERE project_id = ? ORDER BY created_at ASC, id ASC",
                    (project_id,),
                )
            ]
        return project

    def _require_project(self, connection: sqlite3.Connection, project_id: str) -> None:
        if connection.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
            raise KeyError(project_id)

    def _get_scenario_row(self, connection: sqlite3.Connection, project_id: str, scenario_id: str) -> sqlite3.Row:
        self._require_project(connection, project_id)
        row = connection.execute(
            "SELECT * FROM scenarios WHERE id = ? AND project_id = ?", (scenario_id, project_id)
        ).fetchone()
        if row is None:
            raise KeyError(scenario_id)
        return row

    @staticmethod
    def _require_scenario(connection: sqlite3.Connection, scenario_id: str) -> None:
        if connection.execute("SELECT 1 FROM scenarios WHERE id = ?", (scenario_id,)).fetchone() is None:
            raise KeyError(scenario_id)

    @staticmethod
    def _write_scenario_inputs(
        connection: sqlite3.Connection, scenario_id: str, inputs: dict[str, Any]
    ) -> None:
        """写入新输入并按是否有历史结果标记 stale/draft（与 update_scenario 同一套规则）。"""
        row = connection.execute(
            "SELECT result_snapshot_id, result_json FROM scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
        had_current_result = row["result_snapshot_id"] is not None or row["result_json"] is not None
        now = utc_now()
        connection.execute(
            "UPDATE scenarios SET status = ?, inputs_json = ?, input_snapshot_json = ?, result_json = NULL,"
            " result_snapshot_id = NULL, calculated_at = NULL, updated_at = ? WHERE id = ?",
            (
                "stale" if had_current_result else "draft",
                _dump(inputs),
                _dump(inputs),
                now,
                scenario_id,
            ),
        )
        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = (SELECT project_id FROM scenarios WHERE id = ?)",
            (now, scenario_id),
        )

    def create_project(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        project = {
            "id": new_id("project"),
            "name": str(data["name"]),
            "cityId": data.get("cityId"),
            "city": str(data["city"]),
            "district": data.get("district"),
            "baseMonth": data.get("baseMonth"),
            "stationMode": data.get("stationMode", "自营"),
            "createdAt": now,
            "updatedAt": now,
        }
        with self._db() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, city_id, city, district, base_month, station_mode,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project["id"],
                    project["name"],
                    project["cityId"],
                    project["city"],
                    project["district"],
                    project["baseMonth"],
                    project["stationMode"],
                    project["createdAt"],
                    project["updatedAt"],
                ),
            )
        return {**project, "scenarios": []}

    def create_scenario(self, project_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        inputs = dict(data.get("inputs") or {})
        scenario = {
            "id": new_id("scenario"),
            "name": str(data["name"]),
            "inputs": inputs,
            "result": None,
            "inputSnapshot": inputs,
            "resultSnapshotId": None,
            "calculatedAt": None,
            "status": "draft",
            "createdAt": now,
            "updatedAt": now,
        }
        with self._db() as connection:
            self._require_project(connection, project_id)
            connection.execute(
                "INSERT INTO scenarios (id, project_id, name, status, inputs_json, result_json,"
                " input_snapshot_json, result_snapshot_id, calculated_at, confirmed_at, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, ?, ?)",
                (
                    scenario["id"],
                    project_id,
                    scenario["name"],
                    scenario["status"],
                    _dump(scenario["inputs"]),
                    _dump(scenario["inputSnapshot"]),
                    scenario["createdAt"],
                    scenario["updatedAt"],
                ),
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return dict(scenario)

    def get_scenario(self, project_id: str, scenario_id: str) -> dict[str, Any]:
        with self._db() as connection:
            row = self._get_scenario_row(connection, project_id, scenario_id)
            return self._scenario_dict(row)

    def update_scenario(
        self, project_id: str, scenario_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        now = utc_now()
        with self._db() as connection:
            row = self._get_scenario_row(connection, project_id, scenario_id)
            name = row["name"]
            inputs_json = row["inputs_json"]
            input_snapshot_json = row["input_snapshot_json"]
            result_json = row["result_json"]
            result_snapshot_id = row["result_snapshot_id"]
            calculated_at = row["calculated_at"]
            status = row["status"]

            if "name" in data and data["name"] is not None:
                name = str(data["name"])
            if "inputs" in data and data["inputs"] is not None:
                inputs = dict(data["inputs"])
                had_current_result = result_snapshot_id is not None or result_json is not None
                inputs_json = _dump(inputs)
                input_snapshot_json = inputs_json
                result_json = None
                result_snapshot_id = None
                calculated_at = None
                status = "stale" if had_current_result else "draft"

            connection.execute(
                "UPDATE scenarios SET name = ?, status = ?, inputs_json = ?, result_json = ?,"
                " input_snapshot_json = ?, result_snapshot_id = ?, calculated_at = ?, updated_at = ?"
                " WHERE id = ?",
                (
                    name,
                    status,
                    inputs_json,
                    result_json,
                    input_snapshot_json,
                    result_snapshot_id,
                    calculated_at,
                    now,
                    scenario_id,
                ),
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
            updated = connection.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
            return self._scenario_dict(updated)

    def save_calculation(
        self, project_id: str, scenario_id: str, result: Mapping[str, Any]
    ) -> dict[str, Any]:
        now = utc_now()
        with self._db() as connection:
            row = self._get_scenario_row(connection, project_id, scenario_id)
            inputs = _load(row["inputs_json"], {})
            snapshot_id = new_id("snapshot")
            ok = result.get("status") == "ok"
            connection.execute(
                "INSERT INTO calculation_snapshots (id, project_id, scenario_id, model_version, status,"
                " calculated_at, input_snapshot_json, result_snapshot_json, issues_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    project_id,
                    scenario_id,
                    result.get("modelVersion"),
                    "calculated" if ok else "blocked",
                    now,
                    _dump(inputs),
                    _dump(dict(result)),
                    _dump(list(result.get("issues", []))),
                ),
            )
            connection.execute(
                "UPDATE scenarios SET status = ?, result_json = ?, input_snapshot_json = ?,"
                " result_snapshot_id = ?, calculated_at = ?, updated_at = ? WHERE id = ?",
                (
                    "calculated" if ok else "failed",
                    _dump(dict(result)),
                    _dump(inputs),
                    snapshot_id,
                    now,
                    now,
                    scenario_id,
                ),
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
            updated = connection.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
            return self._scenario_dict(updated)

    def list_snapshots(
        self, project_id: str | None = None, scenario_id: str | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if scenario_id is not None:
            clauses.append("scenario_id = ?")
            params.append(scenario_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._db() as connection:
            rows = connection.execute(
                f"SELECT * FROM calculation_snapshots{where} ORDER BY calculated_at ASC, id ASC", params
            ).fetchall()
        return [self._snapshot_dict(row) for row in rows]

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        with self._db() as connection:
            row = connection.execute(
                "SELECT * FROM calculation_snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return self._snapshot_dict(row)

    def confirm_scenario(self, project_id: str, scenario_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._db() as connection:
            row = self._get_scenario_row(connection, project_id, scenario_id)
            if row["status"] != "calculated" or row["result_snapshot_id"] is None:
                raise ValueError("Only a calculated scenario can be confirmed")
            connection.execute(
                "UPDATE scenarios SET status = 'confirmed', confirmed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, scenario_id),
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
            updated = connection.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
            return self._scenario_dict(updated)

    # ---------- 数据来源 ----------
    def list_data_sources(self, city_id: str | None = None) -> list[dict[str, Any]]:
        where = " WHERE city_id = ?" if city_id is not None else ""
        params: tuple[Any, ...] = (city_id,) if city_id is not None else ()
        with self._db() as connection:
            rows = connection.execute(
                f"SELECT * FROM data_sources{where} ORDER BY updated_at DESC", params
            ).fetchall()
        return [self._data_source_dict(row) for row in rows]

    def create_data_source(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        source = {
            "id": new_id("source"),
            "cityId": str(data["cityId"]),
            "name": str(data["name"]),
            "kind": str(data.get("kind") or "web"),
            "url": data.get("url"),
            "status": str(data.get("status") or "active"),
            "createdAt": now,
            "updatedAt": now,
        }
        for key in ("timeoutSeconds", "maxBytes", "note"):
            if data.get(key) is not None:
                source[key] = data[key]
        with self._db() as connection:
            connection.execute(
                "INSERT INTO data_sources (id, city_id, name, kind, url, status, timeout_seconds,"
                " max_bytes, note, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source["id"],
                    source["cityId"],
                    source["name"],
                    source["kind"],
                    source["url"],
                    source["status"],
                    source.get("timeoutSeconds"),
                    source.get("maxBytes"),
                    source.get("note"),
                    source["createdAt"],
                    source["updatedAt"],
                ),
            )
        return dict(source)

    def update_data_source(self, source_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        with self._db() as connection:
            if connection.execute("SELECT 1 FROM data_sources WHERE id = ?", (source_id,)).fetchone() is None:
                raise KeyError(source_id)
            for key in (
                "name",
                "kind",
                "url",
                "status",
                "lastFetchedAt",
                "lastHttpStatus",
                "lastChangeStatus",
                "timeoutSeconds",
                "maxBytes",
                "note",
            ):
                if key in data and data[key] is not None:
                    connection.execute(
                        f"UPDATE data_sources SET {key} = ? WHERE id = ?", (data[key], source_id)
                    )
            connection.execute(
                "UPDATE data_sources SET updated_at = ? WHERE id = ?", (utc_now(), source_id)
            )
            row = connection.execute("SELECT * FROM data_sources WHERE id = ?", (source_id,)).fetchone()
            return self._data_source_dict(row)

    # ---------- 政策原文 ----------
    def list_policy_documents(self, city_id: str | None = None) -> list[dict[str, Any]]:
        where = " WHERE city_id = ?" if city_id is not None else ""
        params: tuple[Any, ...] = (city_id,) if city_id is not None else ()
        with self._db() as connection:
            rows = connection.execute(
                f"SELECT * FROM policy_documents{where} ORDER BY updated_at DESC", params
            ).fetchall()
        return [self._document_dict(row) for row in rows]

    def get_policy_document(self, document_id: str) -> dict[str, Any]:
        with self._db() as connection:
            row = connection.execute("SELECT * FROM policy_documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            raise KeyError(document_id)
        return self._document_dict(row)

    def create_policy_document(
        self, data: Mapping[str, Any], content: bytes, suffix: str
    ) -> dict[str, Any]:
        document_id = new_id("policy")
        stored_path = f"policy_files/{document_id}{suffix}"
        stored_file = self.file_store.put(
            stored_path,
            content,
            content_type=str(data.get("mimeType") or "application/octet-stream"),
        )
        now = utc_now()
        document = {
            "id": document_id,
            "cityId": str(data["cityId"]),
            "originalName": str(data["originalName"]),
            "mimeType": str(data.get("mimeType") or "application/octet-stream"),
            "size": int(data.get("size") or len(content)),
            "sha256": str(data["sha256"]),
            "source": str(data["source"]),
            "storedPath": stored_file["pathname"],
            "storedUrl": stored_file["url"],
            "status": str(data.get("status") or "uploaded"),
            "uploadedAt": now,
            "updatedAt": now,
        }
        with self._db() as connection:
            connection.execute(
                "INSERT INTO policy_documents (id, city_id, original_name, mime_type, size, sha256, source,"
                " stored_path, stored_url, status, uploaded_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    document["id"],
                    document["cityId"],
                    document["originalName"],
                    document["mimeType"],
                    document["size"],
                    document["sha256"],
                    document["source"],
                    document["storedPath"],
                    document["storedUrl"],
                    document["status"],
                    document["uploadedAt"],
                    document["updatedAt"],
                ),
            )
        return dict(document)

    def read_policy_document(self, document: Mapping[str, Any]) -> bytes:
        return self.file_store.get(str(document["storedPath"]))

    def update_policy_document(self, document_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        with self._db() as connection:
            if connection.execute("SELECT 1 FROM policy_documents WHERE id = ?", (document_id,)).fetchone() is None:
                raise KeyError(document_id)
            for column, key in (("status", "status"), ("source", "source")):
                if key in data and data[key] is not None:
                    connection.execute(
                        f"UPDATE policy_documents SET {column} = ? WHERE id = ?", (data[key], document_id)
                    )
            connection.execute(
                "UPDATE policy_documents SET updated_at = ? WHERE id = ?", (utc_now(), document_id)
            )
            row = connection.execute("SELECT * FROM policy_documents WHERE id = ?", (document_id,)).fetchone()
            return self._document_dict(row)

    # ---------- 政策候选字段 ----------
    def list_policy_facts(
        self, *, city_id: str | None = None, document_id: str | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if city_id is not None:
            clauses.append("city_id = ?")
            params.append(city_id)
        if document_id is not None:
            clauses.append("document_id = ?")
            params.append(document_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._db() as connection:
            rows = connection.execute(
                f"SELECT * FROM policy_facts{where} ORDER BY created_at ASC, id ASC", params
            ).fetchall()
        return [self._fact_dict(row) for row in rows]

    def get_policy_fact(self, fact_id: str) -> dict[str, Any]:
        with self._db() as connection:
            row = connection.execute("SELECT * FROM policy_facts WHERE id = ?", (fact_id,)).fetchone()
        if row is None:
            raise KeyError(fact_id)
        return self._fact_dict(row)

    def create_policy_fact(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        fact = {
            "id": new_id("fact"),
            "documentId": str(data["documentId"]),
            "cityId": str(data["cityId"]),
            "fieldId": str(data["fieldId"]),
            "value": data.get("value"),
            "unit": data.get("unit"),
            "confidence": data.get("confidence"),
            "source": data.get("source"),
            "status": str(data.get("status") or "candidate"),
            "reviewer": data.get("reviewer"),
            "reviewedAt": data.get("reviewedAt"),
            "effectiveDate": data.get("effectiveDate"),
            "createdAt": now,
            "updatedAt": now,
        }
        with self._db() as connection:
            connection.execute(
                "INSERT INTO policy_facts (id, document_id, city_id, field_id, value_json, unit, confidence_json,"
                " source, status, reviewer, reviewed_at, effective_date, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fact["id"],
                    fact["documentId"],
                    fact["cityId"],
                    fact["fieldId"],
                    _dump(fact["value"]),
                    fact["unit"],
                    _dump(fact["confidence"]) if fact["confidence"] is not None else None,
                    fact["source"],
                    fact["status"],
                    fact["reviewer"],
                    fact["reviewedAt"],
                    fact["effectiveDate"],
                    fact["createdAt"],
                    fact["updatedAt"],
                ),
            )
        return dict(fact)

    def update_policy_fact(self, fact_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        with self._db() as connection:
            if connection.execute("SELECT 1 FROM policy_facts WHERE id = ?", (fact_id,)).fetchone() is None:
                raise KeyError(fact_id)
            columns = {
                "status": "status",
                "reviewer": "reviewer",
                "reviewedAt": "reviewed_at",
                "source": "source",
                "effectiveDate": "effective_date",
            }
            for key, column in columns.items():
                if key in data:
                    connection.execute(
                        f"UPDATE policy_facts SET {column} = ? WHERE id = ?", (data[key], fact_id)
                    )
            connection.execute("UPDATE policy_facts SET updated_at = ? WHERE id = ?", (utc_now(), fact_id))
            row = connection.execute("SELECT * FROM policy_facts WHERE id = ?", (fact_id,)).fetchone()
            return self._fact_dict(row)

    # ---------- 字段值（PRD 12.2 四元组与采用/覆盖历史） ----------

    @staticmethod
    def _field_value_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "scenarioId": row["scenario_id"],
            "fieldId": row["field_id"],
            "suggestedValue": _load(row["suggested_value_json"]),
            "suggestedSource": _load(row["suggested_source_json"]),
            "suggestedAt": row["suggested_at"],
            "valueState": row["value_state"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _history_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "scenarioId": row["scenario_id"],
            "fieldId": row["field_id"],
            "action": row["action"],
            "oldValue": _load(row["old_value_json"]),
            "newValue": _load(row["new_value_json"]),
            "source": _load(row["source_json"]),
            "actedAt": row["acted_at"],
        }

    @staticmethod
    def _insert_history(
        connection: sqlite3.Connection,
        scenario_id: str,
        field_id: str,
        action: str,
        old_value: Any,
        new_value: Any,
        source: Any,
    ) -> None:
        connection.execute(
            "INSERT INTO scenario_field_value_history (id, scenario_id, field_id, action, old_value_json,"
            " new_value_json, source_json, acted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("fvh"),
                scenario_id,
                field_id,
                action,
                _dump(old_value),
                _dump(new_value),
                _dump(source),
                utc_now(),
            ),
        )

    def list_field_values(self, scenario_id: str) -> list[dict[str, Any]]:
        with self._db() as connection:
            rows = connection.execute(
                "SELECT * FROM scenario_field_values WHERE scenario_id = ? ORDER BY field_id", (scenario_id,)
            ).fetchall()
        return [self._field_value_dict(row) for row in rows]

    def save_field_suggestion(
        self, scenario_id: str, field_id: str, value: Any, source: Mapping[str, Any]
    ) -> dict[str, Any]:
        now = utc_now()
        with self._db() as connection:
            self._require_scenario(connection, scenario_id)
            old = connection.execute(
                "SELECT suggested_value_json FROM scenario_field_values WHERE scenario_id = ? AND field_id = ?",
                (scenario_id, field_id),
            ).fetchone()
            connection.execute(
                "INSERT INTO scenario_field_values (scenario_id, field_id, suggested_value_json,"
                " suggested_source_json, suggested_at, value_state, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'suggestion_ready', ?)"
                " ON CONFLICT (scenario_id, field_id) DO UPDATE SET"
                " suggested_value_json = excluded.suggested_value_json,"
                " suggested_source_json = excluded.suggested_source_json,"
                " suggested_at = excluded.suggested_at,"
                " value_state = 'suggestion_ready', updated_at = excluded.updated_at",
                (scenario_id, field_id, _dump(value), _dump(dict(source)), now, now),
            )
            self._insert_history(
                connection,
                scenario_id,
                field_id,
                "suggestion_updated",
                _load(old["suggested_value_json"]) if old else None,
                value,
                dict(source),
            )
            row = connection.execute(
                "SELECT * FROM scenario_field_values WHERE scenario_id = ? AND field_id = ?",
                (scenario_id, field_id),
            ).fetchone()
            return self._field_value_dict(row)

    def accept_field_suggestion(self, project_id: str, scenario_id: str, field_id: str) -> dict[str, Any]:
        with self._db() as connection:
            self._get_scenario_row(connection, project_id, scenario_id)
            row = connection.execute(
                "SELECT * FROM scenario_field_values WHERE scenario_id = ? AND field_id = ?",
                (scenario_id, field_id),
            ).fetchone()
            if row is None or row["suggested_value_json"] is None:
                raise ValueError("SUGGESTION_NOT_AVAILABLE")
            scenario = connection.execute(
                "SELECT inputs_json FROM scenarios WHERE id = ?", (scenario_id,)
            ).fetchone()
            inputs = _load(scenario["inputs_json"], {})
            old_value = inputs.get(field_id)
            accepted_value = _load(row["suggested_value_json"])
            inputs[field_id] = accepted_value
            self._write_scenario_inputs(connection, scenario_id, inputs)
            now = utc_now()
            connection.execute(
                "UPDATE scenario_field_values SET value_state = 'accepted', updated_at = ?"
                " WHERE scenario_id = ? AND field_id = ?",
                (now, scenario_id, field_id),
            )
            self._insert_history(
                connection,
                scenario_id,
                field_id,
                "accepted",
                old_value,
                accepted_value,
                _load(row["suggested_source_json"]),
            )
            updated = connection.execute(
                "SELECT * FROM scenario_field_values WHERE scenario_id = ? AND field_id = ?",
                (scenario_id, field_id),
            ).fetchone()
            return self._field_value_dict(updated)

    def set_field_value(
        self, project_id: str, scenario_id: str, field_id: str, value: Any
    ) -> dict[str, Any] | None:
        with self._db() as connection:
            self._get_scenario_row(connection, project_id, scenario_id)
            row = connection.execute(
                "SELECT * FROM scenario_field_values WHERE scenario_id = ? AND field_id = ?",
                (scenario_id, field_id),
            ).fetchone()
            scenario = connection.execute(
                "SELECT inputs_json FROM scenarios WHERE id = ?", (scenario_id,)
            ).fetchone()
            inputs = _load(scenario["inputs_json"], {})
            old_value = inputs.get(field_id)
            inputs[field_id] = value
            self._write_scenario_inputs(connection, scenario_id, inputs)
            if row is not None:
                now = utc_now()
                connection.execute(
                    "UPDATE scenario_field_values SET value_state = 'overridden', updated_at = ?"
                    " WHERE scenario_id = ? AND field_id = ?",
                    (now, scenario_id, field_id),
                )
                self._insert_history(
                    connection,
                    scenario_id,
                    field_id,
                    "overridden",
                    old_value,
                    value,
                    _load(row["suggested_source_json"]),
                )
                updated = connection.execute(
                    "SELECT * FROM scenario_field_values WHERE scenario_id = ? AND field_id = ?",
                    (scenario_id, field_id),
                ).fetchone()
                return self._field_value_dict(updated)
            self._insert_history(connection, scenario_id, field_id, "manual_set", old_value, value, None)
            return None

    def mark_field_overridden(
        self, scenario_id: str, field_id: str, old_value: Any, new_value: Any
    ) -> dict[str, Any] | None:
        with self._db() as connection:
            self._require_scenario(connection, scenario_id)
            row = connection.execute(
                "SELECT * FROM scenario_field_values WHERE scenario_id = ? AND field_id = ?",
                (scenario_id, field_id),
            ).fetchone()
            if row is None:
                return None
            now = utc_now()
            connection.execute(
                "UPDATE scenario_field_values SET value_state = 'overridden', updated_at = ?"
                " WHERE scenario_id = ? AND field_id = ?",
                (now, scenario_id, field_id),
            )
            self._insert_history(
                connection,
                scenario_id,
                field_id,
                "overridden",
                old_value,
                new_value,
                _load(row["suggested_source_json"]),
            )
            updated = connection.execute(
                "SELECT * FROM scenario_field_values WHERE scenario_id = ? AND field_id = ?",
                (scenario_id, field_id),
            ).fetchone()
            return self._field_value_dict(updated)

    def list_field_value_history(self, scenario_id: str, field_id: str | None = None) -> list[dict[str, Any]]:
        clauses = ["scenario_id = ?"]
        params: list[Any] = [scenario_id]
        if field_id is not None:
            clauses.append("field_id = ?")
            params.append(field_id)
        with self._db() as connection:
            rows = connection.execute(
                f"SELECT * FROM scenario_field_value_history WHERE {' AND '.join(clauses)}"
                " ORDER BY acted_at ASC, id ASC",
                params,
            ).fetchall()
        return [self._history_dict(row) for row in rows]

    # ---------- 抓取记录（PRD 11.8） ----------

    @staticmethod
    def _artifact_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "artifactId": row["id"],
            "sourceId": row["source_id"],
            "cityId": row["city_id"],
            "requestedUrl": row["requested_url"],
            "finalUrl": row["final_url"],
            "fetchedAt": row["fetched_at"],
            "httpStatus": row["http_status"],
            "contentType": row["content_type"],
            "contentLength": row["content_length"],
            "sha256": row["sha256"],
            "storedPath": row["stored_path"],
            "title": row["title"],
            "changeStatus": row["change_status"],
            "status": row["status"],
            "errorMessage": row["error_message"],
        }

    def list_crawl_artifacts(
        self, *, source_id: str | None = None, city_id: str | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if source_id is not None:
            clauses.append("source_id = ?")
            params.append(source_id)
        if city_id is not None:
            clauses.append("city_id = ?")
            params.append(city_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._db() as connection:
            rows = connection.execute(
                f"SELECT * FROM crawl_artifacts{where} ORDER BY fetched_at ASC, id ASC", params
            ).fetchall()
        return [self._artifact_dict(row) for row in rows]

    def get_crawl_artifact(self, artifact_id: str) -> dict[str, Any]:
        with self._db() as connection:
            row = connection.execute(
                "SELECT * FROM crawl_artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return self._artifact_dict(row)

    def create_crawl_artifact(self, data: Mapping[str, Any]) -> dict[str, Any]:
        artifact = dict(data)
        artifact_id = artifact.get("artifactId") or new_id("artifact")
        artifact["artifactId"] = artifact_id
        artifact.setdefault("fetchedAt", utc_now())
        with self._db() as connection:
            connection.execute(
                "INSERT INTO crawl_artifacts (id, source_id, city_id, requested_url, final_url, fetched_at,"
                " http_status, content_type, content_length, sha256, stored_path, title, change_status,"
                " status, error_message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    artifact["sourceId"],
                    artifact["cityId"],
                    artifact["requestedUrl"],
                    artifact.get("finalUrl"),
                    artifact["fetchedAt"],
                    artifact.get("httpStatus"),
                    artifact.get("contentType"),
                    artifact.get("contentLength"),
                    artifact.get("sha256"),
                    artifact.get("storedPath"),
                    artifact.get("title"),
                    artifact.get("changeStatus"),
                    artifact.get("status", "success"),
                    artifact.get("errorMessage"),
                    utc_now(),
                ),
            )
        return {k: v for k, v in artifact.items() if k != "rawContent"}
