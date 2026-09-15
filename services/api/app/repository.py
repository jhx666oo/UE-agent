from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
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
        "policyFallbackTasks": [],
        "onboardingJobs": [],
        "policyResearchRuns": [],
        "policyResearchQueries": [],
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
        "policyFallbackTasks",
        "onboardingJobs",
        "policyResearchRuns",
        "policyResearchQueries",
    ):
        if not isinstance(payload.get(collection, []), list):
            raise ValueError(f"Invalid {collection} store")
        payload.setdefault(collection, [])
    return payload


def enrich_legacy_crawl_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """给 009 迁移前的 HTTP 失败记录补出可行动的浏览器兜底元数据。"""
    result = copy.deepcopy(dict(artifact))
    if result.get("status") != "failed" or result.get("fallbackAction"):
        return result
    message = str(result.get("errorMessage") or "")
    match = re.search(r"HTTP\s+(\d{3})", message, flags=re.IGNORECASE)
    if match is None:
        return result
    status = int(match.group(1))
    if status not in {403, 412, 429} and status < 500:
        return result
    result.update(
        {
            "httpStatus": result.get("httpStatus") or status,
            "fetchMode": result.get("fetchMode") or "http",
            "errorCode": result.get("errorCode") or f"HTTP_{status}_BROWSER_REQUIRED",
            "fallbackAction": "browser_search",
            "fallbackReason": "js_challenge" if status == 412 else "http_blocked",
        }
    )
    return result


class PolicyFileStore(Protocol):
    def put(self, pathname: str, content: bytes, *, content_type: str) -> dict[str, str]: ...

    def get(self, pathname: str) -> bytes: ...


class ProjectRepository(Protocol):
    """Storage contract shared by the JSON, Postgres and SQLite repositories."""

    def list_projects(self) -> list[dict[str, Any]]: ...

    def get_project(self, project_id: str) -> dict[str, Any]: ...

    def create_project(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def delete_project(self, project_id: str) -> None: ...

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

    # ---------- 浏览器兜底任务 ----------
    def list_policy_fallback_tasks(
        self, *, city_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_policy_fallback_task(self, task_id: str) -> dict[str, Any]: ...

    def get_active_policy_fallback_task(
        self, *, source_id: str, requested_url: str
    ) -> dict[str, Any] | None: ...

    def create_policy_fallback_task(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def update_policy_fallback_task(
        self, task_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    # ---------- AI 回传链路（WorkBuddy 驱动） ----------
    def list_candidate_sources(
        self, *, city_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]: ...

    def create_candidate_source(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def update_candidate_source(
        self, candidate_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def get_candidate_source(self, candidate_id: str) -> dict[str, Any]: ...

    def create_extraction_submission(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def list_extraction_submissions(
        self, *, city_id: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]: ...

    # ---------- 城市自动入场任务 ----------
    def create_onboarding_job(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def get_onboarding_job(self, job_id: str) -> dict[str, Any]: ...

    def get_active_onboarding_job(self, project_id: str) -> dict[str, Any] | None: ...

    def list_onboarding_jobs(self, project_id: str | None = None) -> list[dict[str, Any]]: ...

    def update_onboarding_job(self, job_id: str, data: Mapping[str, Any]) -> dict[str, Any]: ...

    # ---------- 政策实时检索任务 ----------
    def create_research_run(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def get_research_run(self, run_id: str) -> dict[str, Any]: ...

    def get_active_research_run(self, city_id: str) -> dict[str, Any] | None: ...

    def list_research_runs(
        self, city_id: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]: ...

    def update_research_run(self, run_id: str, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def create_research_query(self, data: Mapping[str, Any]) -> dict[str, Any]: ...

    def list_research_queries(self, run_id: str) -> list[dict[str, Any]]: ...

    def update_research_query(self, query_id: str, data: Mapping[str, Any]) -> dict[str, Any]: ...


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

    def create_onboarding_job(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        job = {
            "id": new_id("onboarding"),
            "projectId": str(data["projectId"]),
            "cityId": str(data["cityId"]),
            "cityName": str(data["cityName"]),
            "status": str(data.get("status") or "queued"),
            "phase": str(data.get("phase") or "queued"),
            "totalQueries": int(data.get("totalQueries") or 0),
            "discoveredCount": int(data.get("discoveredCount") or 0),
            "officialSourceCount": int(data.get("officialSourceCount") or 0),
            "candidateCount": int(data.get("candidateCount") or 0),
            "crawledCount": int(data.get("crawledCount") or 0),
            "suggestionCount": int(data.get("suggestionCount") or 0),
            "errorCount": int(data.get("errorCount") or 0),
            "errors": copy.deepcopy(list(data.get("errors") or [])),
            "startedAt": data.get("startedAt"),
            "finishedAt": data.get("finishedAt"),
            "createdAt": now,
            "updatedAt": now,
        }
        payload = self._read()
        payload.setdefault("onboardingJobs", []).append(job)
        self._write(payload)
        return copy.deepcopy(job)

    def get_onboarding_job(self, job_id: str) -> dict[str, Any]:
        for job in self._read().get("onboardingJobs", []):
            if job.get("id") == job_id:
                return copy.deepcopy(job)
        raise KeyError(job_id)

    def get_active_onboarding_job(self, project_id: str) -> dict[str, Any] | None:
        active = {"queued", "discovering", "sources_ready", "crawling", "extracting"}
        jobs = [
            job
            for job in self._read().get("onboardingJobs", [])
            if job.get("projectId") == project_id and job.get("status") in active
        ]
        if not jobs:
            return None
        return copy.deepcopy(max(jobs, key=lambda item: str(item.get("updatedAt") or "")))

    def list_onboarding_jobs(self, project_id: str | None = None) -> list[dict[str, Any]]:
        jobs = [
            copy.deepcopy(job)
            for job in self._read().get("onboardingJobs", [])
            if project_id is None or job.get("projectId") == project_id
        ]
        return sorted(jobs, key=lambda item: str(item.get("updatedAt") or ""), reverse=True)

    def update_onboarding_job(self, job_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        job = next((item for item in payload.get("onboardingJobs", []) if item.get("id") == job_id), None)
        if job is None:
            raise KeyError(job_id)
        allowed = {
            "status", "phase", "totalQueries", "discoveredCount", "officialSourceCount",
            "candidateCount", "crawledCount", "suggestionCount", "errorCount", "errors",
            "startedAt", "finishedAt",
        }
        for key in allowed:
            if key in data:
                job[key] = copy.deepcopy(data[key])
        job["updatedAt"] = utc_now()
        self._write(payload)
        return copy.deepcopy(job)

    def create_research_run(self, data: Mapping[str, Any]) -> dict[str, Any]:
        active_statuses = {"queued", "researching", "fetching", "extracting", "awaiting_review"}
        payload = self._read()
        active = [
            run
            for run in payload.get("policyResearchRuns", [])
            if run.get("cityId") == data.get("cityId") and run.get("status") in active_statuses
        ]
        if active:
            return copy.deepcopy(max(active, key=lambda item: str(item.get("updatedAt") or "")))
        now = utc_now()
        run = {
            "id": str(data.get("id") or new_id("research")),
            "cityId": str(data["cityId"]),
            "projectId": data.get("projectId"),
            "trigger": str(data.get("trigger") or "ui"),
            "scope": str(data.get("scope") or "all"),
            "fields": copy.deepcopy(list(data.get("fields") or [])),
            "status": str(data.get("status") or "queued"),
            "phase": str(data.get("phase") or "queued"),
            "agentRunId": data.get("agentRunId"),
            "agentVersion": data.get("agentVersion"),
            "queryCount": int(data.get("queryCount") or 0),
            "sourceCount": int(data.get("sourceCount") or 0),
            "newSourceCount": int(data.get("newSourceCount") or 0),
            "changedSourceCount": int(data.get("changedSourceCount") or 0),
            "fetchedCount": int(data.get("fetchedCount") or 0),
            "suggestionCount": int(data.get("suggestionCount") or 0),
            "errorCount": int(data.get("errorCount") or 0),
            "errors": copy.deepcopy(list(data.get("errors") or [])),
            "taskPrompt": data.get("taskPrompt"),
            "requestedAt": data.get("requestedAt") or now,
            "startedAt": data.get("startedAt"),
            "finishedAt": data.get("finishedAt"),
            "createdAt": now,
            "updatedAt": now,
        }
        payload.setdefault("policyResearchRuns", []).append(run)
        self._write(payload)
        return copy.deepcopy(run)

    def get_research_run(self, run_id: str) -> dict[str, Any]:
        for run in self._read().get("policyResearchRuns", []):
            if run.get("id") == run_id:
                return copy.deepcopy(run)
        raise KeyError(run_id)

    def get_active_research_run(self, city_id: str) -> dict[str, Any] | None:
        active_statuses = {"queued", "researching", "fetching", "extracting", "awaiting_review"}
        runs = [
            run
            for run in self._read().get("policyResearchRuns", [])
            if run.get("cityId") == city_id and run.get("status") in active_statuses
        ]
        if not runs:
            return None
        return copy.deepcopy(max(runs, key=lambda item: str(item.get("updatedAt") or "")))

    def list_research_runs(
        self, city_id: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        runs = [
            copy.deepcopy(run)
            for run in self._read().get("policyResearchRuns", [])
            if city_id is None or run.get("cityId") == city_id
        ]
        runs.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
        return runs[:limit] if limit else runs

    def update_research_run(self, run_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        run = next((item for item in payload.get("policyResearchRuns", []) if item.get("id") == run_id), None)
        if run is None:
            raise KeyError(run_id)
        allowed = {
            "projectId", "trigger", "scope", "fields", "status", "phase", "agentRunId", "agentVersion",
            "queryCount", "sourceCount", "newSourceCount", "changedSourceCount", "fetchedCount",
            "suggestionCount", "errorCount", "errors", "taskPrompt", "requestedAt", "startedAt", "finishedAt",
        }
        for key in allowed:
            if key in data:
                run[key] = copy.deepcopy(data[key])
        run["updatedAt"] = utc_now()
        self._write(payload)
        return copy.deepcopy(run)

    def create_research_query(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        query = {
            "id": str(data.get("id") or new_id("research-query")),
            "runId": str(data["runId"]),
            "family": str(data["family"]),
            "query": str(data["query"]),
            "status": str(data.get("status") or "queued"),
            "resultCount": int(data.get("resultCount") or 0),
            "errorMessage": data.get("errorMessage"),
            "searchedAt": data.get("searchedAt"),
            "createdAt": now,
        }
        payload = self._read()
        payload.setdefault("policyResearchQueries", []).append(query)
        self._write(payload)
        return copy.deepcopy(query)

    def list_research_queries(self, run_id: str) -> list[dict[str, Any]]:
        queries = [
            copy.deepcopy(query)
            for query in self._read().get("policyResearchQueries", [])
            if query.get("runId") == run_id
        ]
        return sorted(queries, key=lambda item: str(item.get("createdAt") or ""))

    def update_research_query(self, query_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._read()
        query = next(
            (item for item in payload.get("policyResearchQueries", []) if item.get("id") == query_id), None
        )
        if query is None:
            raise KeyError(query_id)
        for key in ("status", "resultCount", "errorMessage", "searchedAt"):
            if key in data:
                query[key] = copy.deepcopy(data[key])
        self._write(payload)
        return copy.deepcopy(query)

    def delete_project(self, project_id: str) -> None:
        payload = self._read()
        project = self._get_project_ref(payload, project_id)
        scenario_ids = {scenario.get("id") for scenario in project.get("scenarios", [])}
        payload["projects"] = [item for item in payload["projects"] if item.get("id") != project_id]
        payload["calculationSnapshots"] = [
            item for item in payload["calculationSnapshots"] if item.get("projectId") != project_id
        ]
        payload["fieldValues"] = [
            item for item in payload["fieldValues"] if item.get("scenarioId") not in scenario_ids
        ]
        payload["fieldValueHistory"] = [
            item for item in payload["fieldValueHistory"] if item.get("scenarioId") not in scenario_ids
        ]
        self._write(payload)

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
        payload = self._read()
        sources = payload.get("dataSources", [])
        selected = [source for source in sources if city_id is None or source.get("cityId") == city_id]
        artifacts_by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for artifact in payload.get("crawlArtifacts", []):
            artifacts_by_source[str(artifact.get("sourceId"))].append(artifact)
        result: list[dict[str, Any]] = []
        for source in selected:
            item = copy.deepcopy(source)
            item.setdefault("fallbackAction", item.get("lastFallbackAction"))
            item.setdefault("fallbackReason", item.get("lastFallbackReason"))
            if not item.get("fallbackAction") and item.get("status") == "error":
                latest = next(
                    (
                        enrich_legacy_crawl_artifact(artifact)
                        for artifact in reversed(artifacts_by_source.get(str(item.get("id")), []))
                        if artifact.get("status") == "failed"
                    ),
                    None,
                )
                if latest and latest.get("fallbackAction"):
                    item["fallbackAction"] = latest["fallbackAction"]
                    item["fallbackReason"] = latest.get("fallbackReason")
                    item.setdefault("lastHttpStatus", latest.get("httpStatus"))
                    item.setdefault("lastFetchMode", latest.get("fetchMode"))
            result.append(item)
        return sorted(result, key=lambda source: source.get("updatedAt", ""), reverse=True)

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
            "lastFetchMode",
            "lastErrorCode",
            "lastFallbackAction",
            "lastFallbackReason",
        ):
            if key in data and (data[key] is not None or key.startswith("last")):
                source[key] = data[key]
        # 前端展示用短字段；lastFallback* 仍保留给审计和导出。
        source["fallbackAction"] = source.get("lastFallbackAction")
        source["fallbackReason"] = source.get("lastFallbackReason")
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
        return [enrich_legacy_crawl_artifact(artifact) for artifact in selected]

    def get_crawl_artifact(self, artifact_id: str) -> dict[str, Any]:
        for artifact in self._read().get("crawlArtifacts", []):
            if artifact.get("artifactId") == artifact_id:
                return enrich_legacy_crawl_artifact(artifact)
        raise KeyError(artifact_id)

    def create_crawl_artifact(self, data: Mapping[str, Any]) -> dict[str, Any]:
        artifact = copy.deepcopy(dict(data))
        artifact["artifactId"] = new_id("artifact")
        artifact["fetchedAt"] = artifact.get("fetchedAt") or utc_now()
        payload = self._read()
        payload.setdefault("crawlArtifacts", []).append(artifact)
        self._write(payload)
        return copy.deepcopy(artifact)

    # ---------- 浏览器兜底任务 ----------

    def list_policy_fallback_tasks(
        self, *, city_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        tasks = [
            copy.deepcopy(task)
            for task in self._read().get("policyFallbackTasks", [])
            if (city_id is None or task.get("cityId") == city_id)
            and (status is None or task.get("status") == status)
        ]
        return sorted(tasks, key=lambda task: str(task.get("updatedAt") or ""), reverse=True)

    def get_policy_fallback_task(self, task_id: str) -> dict[str, Any]:
        for task in self._read().get("policyFallbackTasks", []):
            if task.get("id") == task_id:
                return copy.deepcopy(task)
        raise KeyError(task_id)

    def get_active_policy_fallback_task(
        self, *, source_id: str, requested_url: str
    ) -> dict[str, Any] | None:
        tasks = self.list_policy_fallback_tasks()
        return next(
            (
                task
                for task in tasks
                if task.get("sourceId") == source_id
                and task.get("requestedUrl") == requested_url
                and task.get("status") in {"queued", "in_progress"}
            ),
            None,
        )

    def create_policy_fallback_task(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        task = {
            "id": str(data.get("id") or new_id("fallback-task")),
            "cityId": str(data["cityId"]),
            "sourceId": str(data["sourceId"]),
            "researchRunId": data.get("researchRunId"),
            "requestedUrl": str(data["requestedUrl"]),
            "sourceName": data.get("sourceName"),
            "status": str(data.get("status") or "queued"),
            "httpStatus": data.get("httpStatus"),
            "errorCode": data.get("errorCode"),
            "fallbackAction": str(data.get("fallbackAction") or "browser_search"),
            "fallbackReason": data.get("fallbackReason"),
            "attempts": int(data.get("attempts") or 0),
            "artifactId": data.get("artifactId"),
            "lastError": data.get("lastError"),
            "createdAt": data.get("createdAt") or now,
            "updatedAt": data.get("updatedAt") or now,
        }
        payload = self._read()
        payload.setdefault("policyFallbackTasks", []).append(task)
        self._write(payload)
        return copy.deepcopy(task)

    def update_policy_fallback_task(
        self, task_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        payload = self._read()
        task = next(
            (item for item in payload.get("policyFallbackTasks", []) if item.get("id") == task_id),
            None,
        )
        if task is None:
            raise KeyError(task_id)
        allowed = {
            "researchRunId", "requestedUrl", "sourceName", "status", "httpStatus", "errorCode",
            "fallbackAction", "fallbackReason", "attempts", "artifactId", "lastError",
        }
        for key in allowed:
            if key in data:
                task[key] = copy.deepcopy(data[key])
        task["updatedAt"] = utc_now()
        self._write(payload)
        return copy.deepcopy(task)

    # ---------- AI 回传链路（WorkBuddy 驱动） ----------

    def list_candidate_sources(
        self, *, city_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        items = self._read().get("candidateSources", [])
        return [
            copy.deepcopy(item)
            for item in items
            if (city_id is None or item.get("cityId") == city_id)
            and (status is None or item.get("status") == status)
        ]

    def get_candidate_source(self, candidate_id: str) -> dict[str, Any]:
        for item in self._read().get("candidateSources", []):
            if item.get("id") == candidate_id:
                return copy.deepcopy(item)
        raise KeyError(candidate_id)

    def create_candidate_source(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        incoming = copy.deepcopy(dict(data))
        incoming.setdefault("origin", "ai_search")
        incoming.setdefault("status", "candidate")
        incoming["updatedAt"] = now
        payload = self._read()
        candidates = payload.setdefault("candidateSources", [])
        # 同城内同一 URL 视为同一候选，直接复用避免重复入池。
        for existing in candidates:
            if existing.get("cityId") == incoming.get("cityId") and existing.get("url") == incoming.get("url"):
                # 保留既有 id / status / createdAt，只更新来源元数据。
                preserved = {
                    key: existing.get(key)
                    for key in (
                        "id",
                        "status",
                        "createdAt",
                        "promotedSourceId",
                        "reviewedBy",
                        "reviewedAt",
                        "researchRunId",
                    )
                }
                existing.update(incoming)
                existing.update({k: v for k, v in preserved.items() if v is not None})
                self._write(payload)
                return copy.deepcopy(existing)
        candidate = {**incoming, "id": incoming.get("id") or new_id("candidate"), "createdAt": now}
        candidates.append(candidate)
        self._write(payload)
        return copy.deepcopy(candidate)

    def update_candidate_source(
        self, candidate_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        payload = self._read()
        for item in payload.get("candidateSources", []):
            if item.get("id") == candidate_id:
                item.update(copy.deepcopy(dict(data)))
                item["updatedAt"] = utc_now()
                self._write(payload)
                return copy.deepcopy(item)
        raise KeyError(candidate_id)

    def create_extraction_submission(self, data: Mapping[str, Any]) -> dict[str, Any]:
        now = utc_now()
        submission = copy.deepcopy(dict(data))
        submission.setdefault("id", new_id("submission"))
        submission.setdefault("submittedAt", now)
        submission.setdefault("createdAt", now)
        payload = self._read()
        payload.setdefault("extractionSubmissions", []).append(submission)
        self._write(payload)
        return copy.deepcopy(submission)

    def list_extraction_submissions(
        self, *, city_id: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        items = [
            copy.deepcopy(item)
            for item in self._read().get("extractionSubmissions", [])
            if city_id is None or item.get("cityId") == city_id
        ]
        items.sort(key=lambda item: str(item.get("submittedAt") or ""), reverse=True)
        return items[:limit] if limit else items


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
