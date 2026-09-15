"""WorkBuddy 按需实时政策检索任务编排。

本模块只负责任务状态、查询审计和 WorkBuddy brief，不直接联网，也不解释政策。
网页下载与字段校验仍由现有 PolicyService / AgentSubmissionService 负责。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .agent_service import DIFFICULTY_LEVELS, FIELD_FAMILIES, NEVER_ESTIMATE_FIELDS
from ...repository import ProjectRepository


ACTIVE_RESEARCH_RUN_STATUSES = frozenset(
    {"queued", "researching", "fetching", "extracting", "awaiting_review"}
)
TERMINAL_RESEARCH_RUN_STATUSES = frozenset({"completed", "partial_failed", "failed"})
ALLOWED_TRIGGERS = frozenset({"ui", "workbuddy"})
ALLOWED_SCOPES = frozenset({"all", "policy", "population", "space"})
SCOPE_TO_FAMILY = {
    "policy": "政策准入",
    "population": "城市人口",
    "space": "空间面积",
}


class PolicyResearchService:
    def __init__(self, repository: ProjectRepository, catalog: Mapping[str, Mapping[str, Any]]):
        self.repository = repository
        self.catalog = catalog

    def create_run(
        self,
        *,
        city_id: str,
        project_id: str | None,
        trigger: str,
        scope: str,
        fields: list[str],
    ) -> dict[str, Any]:
        city_id = city_id.strip()
        if not city_id:
            raise ValueError("CITY_ID_REQUIRED")
        if trigger not in ALLOWED_TRIGGERS:
            raise ValueError("INVALID_RESEARCH_TRIGGER")
        if scope not in ALLOWED_SCOPES:
            raise ValueError("INVALID_RESEARCH_SCOPE")
        requested_fields = [str(field).strip() for field in fields if str(field).strip()]
        existing = self.repository.get_active_research_run(city_id)
        if existing is not None:
            return existing
        run = self.repository.create_research_run(
            {
                "cityId": city_id,
                "projectId": project_id,
                "trigger": trigger,
                "scope": scope,
                "fields": requested_fields,
                "status": "queued",
                "phase": "queued",
            }
        )
        return self._prepare_brief(run)["run"]

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.repository.get_research_run(run_id)

    def build_brief(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        return self._prepare_brief(run)

    def retry(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run.get("status") not in {"failed", "partial_failed"}:
            raise ValueError("RESEARCH_RUN_NOT_RETRYABLE")
        for query in self.repository.list_research_queries(run_id):
            self.repository.update_research_query(
                query["id"],
                {"status": "queued", "resultCount": 0, "errorMessage": None, "searchedAt": None},
            )
        return self.repository.update_research_run(
            run_id,
            {
                "status": "queued",
                "phase": "queued",
                "agentRunId": None,
                "agentVersion": None,
                "queryCount": 0,
                "sourceCount": 0,
                "newSourceCount": 0,
                "changedSourceCount": 0,
                "fetchedCount": 0,
                "suggestionCount": 0,
                "errorCount": 0,
                "errors": [],
                "startedAt": None,
                "finishedAt": None,
            },
        )

    def complete(
        self,
        run_id: str,
        *,
        status: str,
        agent_run_id: str | None,
        agent_version: str | None,
        errors: list[str],
    ) -> dict[str, Any]:
        if status not in TERMINAL_RESEARCH_RUN_STATUSES:
            raise ValueError("INVALID_RESEARCH_TERMINAL_STATUS")
        run = self.get_run(run_id)
        if run.get("status") in TERMINAL_RESEARCH_RUN_STATUSES:
            same_agent = not agent_run_id or run.get("agentRunId") == agent_run_id
            if same_agent:
                return run
            raise ValueError("RESEARCH_RUN_ALREADY_COMPLETED")
        if run.get("status") == "queued" and status == "completed":
            raise ValueError("RESEARCH_RUN_NOT_STARTED")
        now = datetime.now(timezone.utc).isoformat()
        return self.repository.update_research_run(
            run_id,
            {
                "status": status,
                "phase": "completed" if status == "completed" else status,
                "agentRunId": agent_run_id,
                "agentVersion": agent_version,
                "errors": [str(error) for error in errors],
                "errorCount": len(errors),
                "finishedAt": now,
            },
        )

    def record_results(
        self,
        run_id: str,
        *,
        agent_run_id: str | None,
        agent_version: str | None,
        source_count: int = 0,
        new_source_count: int = 0,
        changed_source_count: int = 0,
        fetched_count: int = 0,
        suggestion_count: int = 0,
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run.get("status") in TERMINAL_RESEARCH_RUN_STATUSES:
            if not agent_run_id or run.get("agentRunId") == agent_run_id:
                return run
            raise ValueError("RESEARCH_RUN_ALREADY_COMPLETED")
        if run.get("status") == "awaiting_review" and agent_run_id and run.get("agentRunId") == agent_run_id:
            return run
        started_at = run.get("startedAt") or datetime.now(timezone.utc).isoformat()
        return self.repository.update_research_run(
            run_id,
            {
                "status": "awaiting_review",
                "phase": "awaiting_review",
                "agentRunId": agent_run_id,
                "agentVersion": agent_version,
                "startedAt": started_at,
                "sourceCount": int(run.get("sourceCount") or 0) + max(0, source_count),
                "newSourceCount": int(run.get("newSourceCount") or 0) + max(0, new_source_count),
                "changedSourceCount": int(run.get("changedSourceCount") or 0) + max(0, changed_source_count),
                "fetchedCount": int(run.get("fetchedCount") or 0) + max(0, fetched_count),
                "suggestionCount": int(run.get("suggestionCount") or 0) + max(0, suggestion_count),
            },
        )

    def mark_progress(
        self,
        run_id: str,
        *,
        status: str,
        phase: str,
        agent_run_id: str | None = None,
        agent_version: str | None = None,
        fetched_count: int = 0,
        changed_source_count: int = 0,
    ) -> dict[str, Any]:
        if status not in ACTIVE_RESEARCH_RUN_STATUSES:
            raise ValueError("INVALID_RESEARCH_ACTIVE_STATUS")
        run = self.get_run(run_id)
        if run.get("status") in TERMINAL_RESEARCH_RUN_STATUSES:
            return run
        started_at = run.get("startedAt") or datetime.now(timezone.utc).isoformat()
        return self.repository.update_research_run(
            run_id,
            {
                "status": status,
                "phase": phase,
                "agentRunId": agent_run_id or run.get("agentRunId"),
                "agentVersion": agent_version or run.get("agentVersion"),
                "startedAt": started_at,
                "fetchedCount": int(run.get("fetchedCount") or 0) + max(0, fetched_count),
                "changedSourceCount": int(run.get("changedSourceCount") or 0) + max(0, changed_source_count),
            },
        )

    def task_prompt(self, run: Mapping[str, Any]) -> str:
        city = str(run.get("cityId") or "")
        run_id = str(run.get("id") or "")
        return (
            f"请更新{city}的长护险政策，researchRunId={run_id}。"
            "先读取 /api/policies/research-runs/{runId}/brief，使用当前年份检索最新政策、统计公报和政府文件；"
            "再把候选来源提交给 /api/policies/source-candidates，并通过 /api/policies/fetch-requests"
            "让 API 下载和保存原文。只对 first_fetch 或 new_version 的原文抽取字段，"
            "每条建议必须带 artifactId、逐字 quote、单位、置信度和生效日期，最后调用"
            " /api/policies/extraction-submissions 和 /api/policies/research-runs/{runId}/complete。"
            "C6、C7、C8 必须放入 notDisclosed，禁止估算；不要覆盖人工采用或人工覆盖的参数。"
        )

    def _prepare_brief(self, run: Mapping[str, Any]) -> dict[str, Any]:
        run_id = str(run["id"])
        families = self._selected_families(run)
        queries = self.repository.list_research_queries(run_id)
        existing_by_family = {str(item.get("family")): item for item in queries}
        current_year = datetime.now(timezone.utc).year
        city_name = str(run.get("cityName") or run["cityId"])
        for family, template, family_fields, source_hint in families:
            if family in existing_by_family:
                continue
            query = template.replace("{城市}", city_name).replace("{city}", city_name)
            query = f"{query} {current_year}"
            created = self.repository.create_research_query(
                {
                    "runId": run_id,
                    "family": family,
                    "query": query,
                    "status": "queued",
                }
            )
            existing_by_family[family] = created
        query_rows = [existing_by_family[family] for family, *_ in families]
        auto_catalog = self._selected_catalog(run)
        sources = self.repository.list_data_sources(str(run["cityId"]))
        artifacts = self.repository.list_crawl_artifacts(city_id=str(run["cityId"]))
        filled = self._filled_fields(str(run["cityId"]))
        brief = {
            "runId": run_id,
            "cityId": run["cityId"],
            "projectId": run.get("projectId"),
            "trigger": run.get("trigger"),
            "scope": run.get("scope"),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "currentYear": current_year,
            "queries": [
                {
                    **query,
                    "fallbackQuery": f"{query['query']} {current_year - 1}",
                    "fields": list(family_fields),
                    "sourceHint": source_hint,
                }
                for query, (family, _template, family_fields, source_hint) in zip(
                    query_rows, families, strict=True
                )
            ],
            "fieldCatalog": [self._catalog_entry(entry) for entry in auto_catalog],
            "fieldFamilies": [
                {
                    "family": family,
                    "queryTemplate": template,
                    "fields": list(family_fields),
                    "sourceHint": source_hint,
                }
                for family, template, family_fields, source_hint in families
            ],
            "difficultyLevels": DIFFICULTY_LEVELS,
            "neverEstimateFields": sorted(NEVER_ESTIMATE_FIELDS),
            "alreadyFilled": sorted(filled),
            "sources": sources,
            "recentArtifacts": artifacts[-20:],
        }
        updated = self.repository.update_research_run(
            run_id,
            {
                "queryCount": len(query_rows),
                "sourceCount": len(sources),
                "taskPrompt": self.task_prompt(run),
            },
        )
        brief["run"] = updated
        return brief

    def _selected_families(
        self, run: Mapping[str, Any]
    ) -> list[tuple[str, str, tuple[str, ...], str]]:
        scope = str(run.get("scope") or "all")
        requested = {str(field) for field in run.get("fields") or []}
        selected: list[tuple[str, str, tuple[str, ...], str]] = []
        for family in FIELD_FAMILIES:
            name, _template, family_fields, _hint = family
            if scope != "all" and name != SCOPE_TO_FAMILY.get(scope):
                continue
            if requested and not requested.intersection(family_fields):
                continue
            selected.append(family)
        return selected or list(FIELD_FAMILIES)

    def _selected_catalog(self, run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        requested = {str(field) for field in run.get("fields") or []}
        entries = [
            entry
            for entry in self.catalog.values()
            if entry.get("sourceType") == "自动爬虫"
            and (not requested or str(entry.get("id")) in requested)
        ]
        return entries

    @staticmethod
    def _catalog_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": entry.get("id"),
            "name": entry.get("name"),
            "unit": entry.get("unit"),
            "valueType": entry.get("valueType"),
            "options": entry.get("options"),
            "block": entry.get("block"),
        }

    def _filled_fields(self, city_id: str) -> set[str]:
        filled: set[str] = set()
        for project in self.repository.list_projects():
            if str(project.get("cityId") or project.get("city")) != city_id:
                continue
            for scenario in project.get("scenarios") or []:
                for row in self.repository.list_field_values(str(scenario["id"])):
                    if row.get("valueState") in {"accepted", "overridden"}:
                        filled.add(str(row.get("fieldId")))
        return filled
