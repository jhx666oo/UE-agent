from __future__ import annotations

import copy
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any, Mapping, Protocol


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def empty_store_payload() -> dict[str, Any]:
    return {
        "projects": [],
        "calculationSnapshots": [],
        "dataSources": [],
        "policyDocuments": [],
        "policyFacts": [],
        "fieldValues": [],
        "fieldValueHistory": [],
        "crawlArtifacts": [],
    }


def normalize_store_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list):
        raise ValueError("Invalid project store payload")
    for collection in (
        "calculationSnapshots",
        "dataSources",
        "policyDocuments",
        "policyFacts",
        "fieldValues",
        "fieldValueHistory",
        "crawlArtifacts",
    ):
        if not isinstance(payload.get(collection, []), list):
            raise ValueError(f"Invalid {collection} store")
        payload.setdefault(collection, [])
    return payload


class PolicyFileStore(Protocol):
    def put(self, pathname: str, content: bytes, *, content_type: str) -> dict[str, str]: ...

    def get(self, pathname: str) -> bytes: ...


class ProjectRepository(Protocol):
    """Storage contract shared by the JSON, Postgres and SQLite repositories."""

    def list_projects(self) -> list[dict[str, Any]]: ...

    def get_project(self, project_id: str) -> dict[str, Any]: ...

    def create_project(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def create_scenario(self, project_id: str, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def get_scenario(self, project_id: str, scenario_id: str) -> dict[str, Any]: ...

    def update_scenario(
        self, project_id: str, scenario_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def save_calculation(
        self, project_id: str, scenario_id: str, result: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def list_snapshots(
        self, project_id: str | None = None, scenario_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]: ...

    def confirm_scenario(self, project_id: str, scenario_id: str) -> dict[str, Any]: ...

    def list_data_sources(self, city_id: str | None = None) -> list[dict[str, Any]]: ...

    def create_data_source(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def update_data_source(self, source_id: str, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def list_policy_documents(self, city_id: str | None = None) -> list[dict[str, Any]]: ...

    def get_policy_document(self, document_id: str) -> dict[str, Any]: ...

    def create_policy_document(
        self, data: Mapping[str, Any], content: bytes, suffix: str
    ) -> dict[str, Any]: ...

    def read_policy_document(self, document: Mapping[str, Any]) -> bytes: ...

    def update_policy_document(self, document_id: str, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def list_policy_facts(
        self, *, city_id: str | None = None, document_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_policy_fact(self, fact_id: str) -> dict[str, Any]: ...

    def create_policy_fact(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def update_policy_fact(self, fact_id: str, data: Mapping[str, Any]) -> dict[str, Any]: ...

    # ---------- 字段值（PRD 12.2 四元组与采用/覆盖历史） ----------
    def list_field_values(self, scenario_id: str) -> list[dict[str, Any]]: ...

    def save_field_suggestion(
        self, scenario_id: str, field_id: str, value: Any, source: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def accept_field_suggestion(
        self, project_id: str, scenario_id: str, field_id: str
    ) -> dict[str, Any]: ...

    def set_field_value(
        self, project_id: str, scenario_id: str, field_id: str, value: Any
    ) -> dict[str, Any] | None: ...

    def mark_field_overridden(
        self, scenario_id: str, field_id: str, old_value: Any, new_value: Any
    ) -> dict[str, Any] | None: ...

    def list_field_value_history(
        self, scenario_id: str, field_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    # ---------- 抓取记录（PRD 11.8） ----------
    def list_crawl_artifacts(
        self, *, source_id: str | None = None, city_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_crawl_artifact(self, artifact_id: str) -> dict[str, Any]: ...

    def create_crawl_artifact(self, data: Mapping[str, Any]) -> dict[str, Any]: ...


class LocalPolicyFileStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _resolve(self, pathname: str) -> Path:
        relative = Path(pathname)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid policy file path")
        return self.root / relative

    def put(self, pathname: str, content: bytes, *, content_type: str) -> dict[str, str]:
        target = self._resolve(pathname)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as temporary:
                temporary_path = temporary.name
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
        finally:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)
        return {"pathname": pathname, "url": f"/{pathname}"}

    def get(self, pathname: str) -> bytes:
        return self._resolve(pathname).read_bytes()


class VercelBlobPolicyFileStore:
    def __init__(self, client_factory: Callable[[], Any] | None = None):
        self.client_factory = client_factory

    def _client(self) -> Any:
        if self.client_factory is not None:
            return self.client_factory()
        from vercel.blob import BlobClient

        return BlobClient()

    @staticmethod
    def _close(client: Any) -> None:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    def put(self, pathname: str, content: bytes, *, content_type: str) -> dict[str, str]:
        client = self._client()
        try:
            result = client.put(
                pathname,
                content,
                access="private",
                content_type=content_type,
                add_random_suffix=False,
            )
            return {"pathname": result.pathname, "url": result.url}
        finally:
            self._close(client)

    def get(self, pathname: str) -> bytes:
        client = self._client()
        try:
            result = client.get(pathname, access="private")
            return bytes(result.content)
        finally:
            self._close(client)


class JsonProjectRepository:
    """Small local repository used until the API has a database adapter."""

    def __init__(self, path: Path, file_store: PolicyFileStore | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file_store = file_store or LocalPolicyFileStore(self.path.parent)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_store_payload()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        try:
            return normalize_store_payload(payload)
        except ValueError as error:
            raise ValueError(f"Invalid project store: {self.path}") from error

    def _write(self, payload: dict[str, Any]) -> None:
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)

    def list_projects(self) -> list[dict[str, Any]]:
        projects = copy.deepcopy(self._read()["projects"])
        return sorted(projects, key=lambda project: project.get("updatedAt", ""), reverse=True)

    def get_project(self, project_id: str) -> dict[str, Any]:
        payload = self._read()
        for project in payload["projects"]:
            if project.get("id") == project_id:
                return copy.deepcopy(project)
        raise KeyError(project_id)

    def _get_project_ref(self, payload: dict[str, Any], project_id: str) -> dict[str, Any]:
        for project in payload["projects"]:
            if project.get("id") == project_id:
                return project
        raise KeyError(project_id)

    def _get_scenario_ref(self, project: dict[str, Any], scenario_id: str) -> dict[str, Any]:
        for scenario in project.get("scenarios", []):
            if scenario.get("id") == scenario_id:
                return scenario
        raise KeyError(scenario_id)

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
            "scenarios": [],
        }
        payload = self._read()
        payload["projects"].append(project)
        self._write(payload)
        return copy.deepcopy(project)

    def create_scenario(self, project_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        project = self._get_project_ref(payload, project_id)
        now = utc_now()
        scenario = {
            "id": new_id("scenario"),
            "name": str(data["name"]),
            "inputs": copy.deepcopy(dict(data.get("inputs") or {})),
            "result": None,
            "inputSnapshot": copy.deepcopy(dict(data.get("inputs") or {})),
            "resultSnapshotId": None,
            "calculatedAt": None,
            "status": "draft",
            "createdAt": now,
            "updatedAt": now,
        }
        project.setdefault("scenarios", []).append(scenario)
        project["updatedAt"] = now
        self._write(payload)
        return copy.deepcopy(scenario)

    def get_scenario(self, project_id: str, scenario_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        return copy.deepcopy(self._get_scenario_ref(project, scenario_id))

    @staticmethod
    def _apply_input_change(scenario: dict[str, Any], inputs: dict[str, Any]) -> None:
        """写入新输入并按是否有历史结果标记 stale/draft（与 update_scenario 同一套规则）。"""
        had_current_result = scenario.get("resultSnapshotId") is not None or scenario.get("result") is not None
        scenario["inputs"] = copy.deepcopy(inputs)
        scenario["inputSnapshot"] = copy.deepcopy(inputs)
        scenario["result"] = None
        scenario["resultSnapshotId"] = None
        scenario["calculatedAt"] = None
        scenario["status"] = "stale" if had_current_result else "draft"

    def update_scenario(self, project_id: str, scenario_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        project = self._get_project_ref(payload, project_id)
        scenario = self._get_scenario_ref(project, scenario_id)
        now = utc_now()
        if "name" in data and data["name"] is not None:
            scenario["name"] = str(data["name"])
        if "inputs" in data and data["inputs"] is not None:
            had_current_result = scenario.get("resultSnapshotId") is not None or scenario.get("result") is not None
            scenario["inputs"] = copy.deepcopy(dict(data["inputs"]))
            scenario["inputSnapshot"] = copy.deepcopy(scenario["inputs"])
            scenario["result"] = None
            scenario["resultSnapshotId"] = None
            scenario["calculatedAt"] = None
            scenario["status"] = "stale" if had_current_result else "draft"
        scenario["updatedAt"] = now
        project["updatedAt"] = now
        self._write(payload)
        return copy.deepcopy(scenario)

    def save_calculation(self, project_id: str, scenario_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        project = self._get_project_ref(payload, project_id)
        scenario = self._get_scenario_ref(project, scenario_id)
        now = utc_now()
        result_snapshot = copy.deepcopy(dict(result))
        snapshot_status = "calculated" if result.get("status") == "ok" else "blocked"
        snapshot = {
            "snapshotId": new_id("snapshot"),
            "projectId": project_id,
            "scenarioId": scenario_id,
            "inputSnapshot": copy.deepcopy(scenario.get("inputs", {})),
            "resultSnapshot": result_snapshot,
            "modelVersion": result.get("modelVersion"),
            "calculatedAt": now,
            "status": snapshot_status,
            "issues": copy.deepcopy(result.get("issues", [])),
        }
        payload.setdefault("calculationSnapshots", []).append(snapshot)
        scenario["result"] = copy.deepcopy(result_snapshot)
        scenario["inputSnapshot"] = copy.deepcopy(snapshot["inputSnapshot"])
        scenario["resultSnapshotId"] = snapshot["snapshotId"]
        scenario["calculatedAt"] = now
        scenario["status"] = "calculated" if result.get("status") == "ok" else "failed"
        scenario["updatedAt"] = now
        project["updatedAt"] = now
        self._write(payload)
        return copy.deepcopy(scenario)

    def list_snapshots(self, project_id: str | None = None, scenario_id: str | None = None) -> list[dict[str, Any]]:
        snapshots = self._read().get("calculationSnapshots", [])
        selected = [
            snapshot
            for snapshot in snapshots
            if (project_id is None or snapshot.get("projectId") == project_id)
            and (scenario_id is None or snapshot.get("scenarioId") == scenario_id)
        ]
        return copy.deepcopy(sorted(selected, key=lambda snapshot: snapshot.get("calculatedAt", "")))

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        for snapshot in self._read().get("calculationSnapshots", []):
            if snapshot.get("snapshotId") == snapshot_id:
                return copy.deepcopy(snapshot)
        raise KeyError(snapshot_id)

    def confirm_scenario(self, project_id: str, scenario_id: str) -> dict[str, Any]:
        payload = self._read()
        project = self._get_project_ref(payload, project_id)
        scenario = self._get_scenario_ref(project, scenario_id)
        if scenario.get("status") != "calculated" or not scenario.get("resultSnapshotId"):
            raise ValueError("Only a calculated scenario can be confirmed")
        now = utc_now()
        scenario["status"] = "confirmed"
        scenario["confirmedAt"] = now
        scenario["updatedAt"] = now
        project["updatedAt"] = now
        self._write(payload)
        return copy.deepcopy(scenario)

    def list_data_sources(self, city_id: str | None = None) -> list[dict[str, Any]]:
        sources = self._read().get("dataSources", [])
        selected = [source for source in sources if city_id is None or source.get("cityId") == city_id]
        return copy.deepcopy(sorted(selected, key=lambda source: source.get("updatedAt", ""), reverse=True))

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
        payload = self._read()
        payload.setdefault("dataSources", []).append(source)
        self._write(payload)
        return copy.deepcopy(source)

    def update_data_source(self, source_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        source = next((item for item in payload.get("dataSources", []) if item.get("id") == source_id), None)
        if source is None:
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
                source[key] = data[key]
        source["updatedAt"] = utc_now()
        self._write(payload)
        return copy.deepcopy(source)

    def list_policy_documents(self, city_id: str | None = None) -> list[dict[str, Any]]:
        documents = self._read().get("policyDocuments", [])
        selected = [document for document in documents if city_id is None or document.get("cityId") == city_id]
        return copy.deepcopy(sorted(selected, key=lambda document: document.get("updatedAt", ""), reverse=True))

    def get_policy_document(self, document_id: str) -> dict[str, Any]:
        for document in self._read().get("policyDocuments", []):
            if document.get("id") == document_id:
                return copy.deepcopy(document)
        raise KeyError(document_id)

    def create_policy_document(self, data: Mapping[str, Any], content: bytes, suffix: str) -> dict[str, Any]:
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
        payload = self._read()
        payload.setdefault("policyDocuments", []).append(document)
        self._write(payload)
        return copy.deepcopy(document)

    def read_policy_document(self, document: Mapping[str, Any]) -> bytes:
        return self.file_store.get(str(document["storedPath"]))

    def update_policy_document(self, document_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        document = next((item for item in payload.get("policyDocuments", []) if item.get("id") == document_id), None)
        if document is None:
            raise KeyError(document_id)
        for key in ("status", "source"):
            if key in data and data[key] is not None:
                document[key] = data[key]
        document["updatedAt"] = utc_now()
        self._write(payload)
        return copy.deepcopy(document)

    def list_policy_facts(
        self,
        *,
        city_id: str | None = None,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        facts = self._read().get("policyFacts", [])
        selected = [
            fact
            for fact in facts
            if (city_id is None or fact.get("cityId") == city_id)
            and (document_id is None or fact.get("documentId") == document_id)
        ]
        return copy.deepcopy(sorted(selected, key=lambda fact: fact.get("createdAt", "")))

    def get_policy_fact(self, fact_id: str) -> dict[str, Any]:
        for fact in self._read().get("policyFacts", []):
            if fact.get("id") == fact_id:
                return copy.deepcopy(fact)
        raise KeyError(fact_id)

    def create_policy_fact(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        fact = {
            "id": new_id("fact"),
            "documentId": str(data["documentId"]),
            "cityId": str(data["cityId"]),
            "fieldId": str(data["fieldId"]),
            "value": copy.deepcopy(data.get("value")),
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
        payload = self._read()
        payload.setdefault("policyFacts", []).append(fact)
        self._write(payload)
        return copy.deepcopy(fact)

    def update_policy_fact(self, fact_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        fact = next((item for item in payload.get("policyFacts", []) if item.get("id") == fact_id), None)
        if fact is None:
            raise KeyError(fact_id)
        for key in ("status", "reviewer", "reviewedAt", "source", "effectiveDate"):
            if key in data:
                fact[key] = data[key]
        fact["updatedAt"] = utc_now()
        self._write(payload)
        return copy.deepcopy(fact)

    # ---------- 字段值（PRD 12.2 四元组与采用/覆盖历史） ----------

    def _find_scenario_owner(self, payload: dict[str, Any], scenario_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        for project in payload["projects"]:
            for scenario in project.get("scenarios", []):
                if scenario.get("id") == scenario_id:
                    return project, scenario
        raise KeyError(scenario_id)

    def _field_value_ref(self, payload: dict[str, Any], scenario_id: str, field_id: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in payload.get("fieldValues", [])
                if row.get("scenarioId") == scenario_id and row.get("fieldId") == field_id
            ),
            None,
        )

    def _append_history(
        self,
        payload: dict[str, Any],
        scenario_id: str,
        field_id: str,
        action: str,
        old_value: Any,
        new_value: Any,
        source: Any,
    ) -> None:
        payload.setdefault("fieldValueHistory", []).append(
            {
                "id": new_id("fvh"),
                "scenarioId": scenario_id,
                "fieldId": field_id,
                "action": action,
                "oldValue": copy.deepcopy(old_value),
                "newValue": copy.deepcopy(new_value),
                "source": copy.deepcopy(source),
                "actedAt": utc_now(),
            }
        )

    def list_field_values(self, scenario_id: str) -> list[dict[str, Any]]:
        rows = [row for row in self._read().get("fieldValues", []) if row.get("scenarioId") == scenario_id]
        return copy.deepcopy(sorted(rows, key=lambda row: row.get("fieldId", "")))

    def save_field_suggestion(
        self, scenario_id: str, field_id: str, value: Any, source: Mapping[str, Any]
    ) -> dict[str, Any]:
        payload = self._read()
        self._find_scenario_owner(payload, scenario_id)
        now = utc_now()
        row = self._field_value_ref(payload, scenario_id, field_id)
        old_suggested = row.get("suggestedValue") if row else None
        if row is None:
            row = {"scenarioId": scenario_id, "fieldId": field_id, "createdAt": now}
            payload.setdefault("fieldValues", []).append(row)
        row.update(
            {
                "suggestedValue": copy.deepcopy(value),
                "suggestedSource": copy.deepcopy(dict(source)),
                "suggestedAt": now,
                "valueState": "suggestion_ready",
                "updatedAt": now,
            }
        )
        self._append_history(payload, scenario_id, field_id, "suggestion_updated", old_suggested, value, row["suggestedSource"])
        self._write(payload)
        return copy.deepcopy(row)

    def accept_field_suggestion(self, project_id: str, scenario_id: str, field_id: str) -> dict[str, Any]:
        payload = self._read()
        project = self._get_project_ref(payload, project_id)
        scenario = self._get_scenario_ref(project, scenario_id)
        row = self._field_value_ref(payload, scenario_id, field_id)
        if row is None or row.get("suggestedValue") is None:
            raise ValueError("SUGGESTION_NOT_AVAILABLE")
        old_value = (scenario.get("inputs") or {}).get(field_id)
        accepted_value = copy.deepcopy(row["suggestedValue"])
        inputs = dict(scenario.get("inputs") or {})
        inputs[field_id] = accepted_value
        self._apply_input_change(scenario, inputs)
        now = utc_now()
        scenario["updatedAt"] = now
        project["updatedAt"] = now
        row["valueState"] = "accepted"
        row["updatedAt"] = now
        self._append_history(payload, scenario_id, field_id, "accepted", old_value, accepted_value, row.get("suggestedSource"))
        self._write(payload)
        return copy.deepcopy(row)

    def set_field_value(self, project_id: str, scenario_id: str, field_id: str, value: Any) -> dict[str, Any] | None:
        payload = self._read()
        project = self._get_project_ref(payload, project_id)
        scenario = self._get_scenario_ref(project, scenario_id)
        row = self._field_value_ref(payload, scenario_id, field_id)
        old_value = (scenario.get("inputs") or {}).get(field_id)
        inputs = dict(scenario.get("inputs") or {})
        inputs[field_id] = copy.deepcopy(value)
        self._apply_input_change(scenario, inputs)
        now = utc_now()
        scenario["updatedAt"] = now
        project["updatedAt"] = now
        if row is not None:
            row["valueState"] = "overridden"
            row["updatedAt"] = now
            self._append_history(payload, scenario_id, field_id, "overridden", old_value, value, row.get("suggestedSource"))
        else:
            self._append_history(payload, scenario_id, field_id, "manual_set", old_value, value, None)
        self._write(payload)
        return copy.deepcopy(row) if row is not None else None

    def mark_field_overridden(self, scenario_id: str, field_id: str, old_value: Any, new_value: Any) -> dict[str, Any] | None:
        payload = self._read()
        self._find_scenario_owner(payload, scenario_id)
        row = self._field_value_ref(payload, scenario_id, field_id)
        if row is None:
            return None
        now = utc_now()
        row["valueState"] = "overridden"
        row["updatedAt"] = now
        self._append_history(payload, scenario_id, field_id, "overridden", old_value, new_value, row.get("suggestedSource"))
        self._write(payload)
        return copy.deepcopy(row)

    def list_field_value_history(self, scenario_id: str, field_id: str | None = None) -> list[dict[str, Any]]:
        entries = [
            entry
            for entry in self._read().get("fieldValueHistory", [])
            if entry.get("scenarioId") == scenario_id and (field_id is None or entry.get("fieldId") == field_id)
        ]
        return copy.deepcopy(sorted(entries, key=lambda entry: entry.get("actedAt", "")))

    # ---------- 抓取记录（PRD 11.8） ----------

    def list_crawl_artifacts(
        self, *, source_id: str | None = None, city_id: str | None = None
    ) -> list[dict[str, Any]]:
        artifacts = self._read().get("crawlArtifacts", [])
        selected = [
            artifact
            for artifact in artifacts
            if (source_id is None or artifact.get("sourceId") == source_id)
            and (city_id is None or artifact.get("cityId") == city_id)
        ]
        return copy.deepcopy(selected)

    def get_crawl_artifact(self, artifact_id: str) -> dict[str, Any]:
        for artifact in self._read().get("crawlArtifacts", []):
            if artifact.get("artifactId") == artifact_id:
                return copy.deepcopy(artifact)
        raise KeyError(artifact_id)

    def create_crawl_artifact(self, data: Mapping[str, Any]) -> dict[str, Any]:
        artifact = copy.deepcopy(dict(data))
        artifact["artifactId"] = new_id("artifact")
        artifact["fetchedAt"] = artifact.get("fetchedAt") or utc_now()
        payload = self._read()
        payload.setdefault("crawlArtifacts", []).append(artifact)
        self._write(payload)
        return copy.deepcopy(artifact)


class PostgresProjectRepository(JsonProjectRepository):
    """Postgres-backed JSON document store used by the Vercel API deployment."""

    def __init__(self, dsn: str, file_store: PolicyFileStore | None = None):
        self.dsn = dsn
        self.file_store = file_store or VercelBlobPolicyFileStore()
        self.path = Path("/tmp/ue-agent/projects.json")
        self._ensure_schema()

    def _connect(self) -> Any:
        import psycopg

        return psycopg.connect(self.dsn)

    def _ensure_schema(self) -> None:
        from psycopg.types.json import Jsonb

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ue_agent_store (
                        id SMALLINT PRIMARY KEY CHECK (id = 1),
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO ue_agent_store (id, payload)
                    VALUES (1, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (Jsonb(empty_store_payload()),),
                )

    def _read(self) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload FROM ue_agent_store WHERE id = 1")
                row = cursor.fetchone()
        if row is None:
            return empty_store_payload()
        return normalize_store_payload(row[0])

    def _write(self, payload: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE ue_agent_store SET payload = %s, updated_at = NOW() WHERE id = 1",
                    (Jsonb(payload),),
                )
