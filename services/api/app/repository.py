from __future__ import annotations

import copy
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class JsonProjectRepository:
    """Small local repository used until the API has a database adapter."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "projects": [],
                "calculationSnapshots": [],
                "dataSources": [],
                "policyDocuments": [],
                "policyFacts": [],
            }
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list):
            raise ValueError(f"Invalid project store: {self.path}")
        for collection in ("calculationSnapshots", "dataSources", "policyDocuments", "policyFacts"):
            if not isinstance(payload.get(collection, []), list):
                raise ValueError(f"Invalid {collection} store: {self.path}")
            payload.setdefault(collection, [])
        return payload

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
        payload = self._read()
        payload.setdefault("dataSources", []).append(source)
        self._write(payload)
        return copy.deepcopy(source)

    def update_data_source(self, source_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        source = next((item for item in payload.get("dataSources", []) if item.get("id") == source_id), None)
        if source is None:
            raise KeyError(source_id)
        for key in ("name", "kind", "url", "status"):
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
        file_dir = self.path.parent / "policy_files"
        file_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{document_id}{suffix}"
        stored_path = file_dir / stored_name
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=file_dir, prefix=f".{document_id}.", suffix=".tmp", delete=False) as temporary:
                temporary_path = temporary.name
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, stored_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)

        now = utc_now()
        document = {
            "id": document_id,
            "cityId": str(data["cityId"]),
            "originalName": str(data["originalName"]),
            "mimeType": str(data.get("mimeType") or "application/octet-stream"),
            "size": int(data.get("size") or len(content)),
            "sha256": str(data["sha256"]),
            "source": str(data["source"]),
            "storedPath": str(Path("policy_files") / stored_name),
            "status": str(data.get("status") or "uploaded"),
            "uploadedAt": now,
            "updatedAt": now,
        }
        payload = self._read()
        payload.setdefault("policyDocuments", []).append(document)
        self._write(payload)
        return copy.deepcopy(document)

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
