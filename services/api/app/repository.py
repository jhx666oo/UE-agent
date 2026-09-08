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
            return {"projects": []}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list):
            raise ValueError(f"Invalid project store: {self.path}")
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
            scenario["inputs"] = copy.deepcopy(dict(data["inputs"]))
            scenario["result"] = None
            scenario["status"] = "draft"
        scenario["updatedAt"] = now
        project["updatedAt"] = now
        self._write(payload)
        return copy.deepcopy(scenario)

    def save_calculation(self, project_id: str, scenario_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        project = self._get_project_ref(payload, project_id)
        scenario = self._get_scenario_ref(project, scenario_id)
        now = utc_now()
        scenario["result"] = copy.deepcopy(dict(result))
        scenario["status"] = "calculated" if result.get("status") == "ok" else "blocked"
        scenario["updatedAt"] = now
        project["updatedAt"] = now
        self._write(payload)
        return copy.deepcopy(scenario)
