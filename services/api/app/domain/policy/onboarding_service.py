"""新增城市后的来源发现、抓取和字段建议值同步编排。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ...repository import ProjectRepository, new_id, utc_now
from .agent_service import FIELD_FAMILIES, AgentSubmissionService
from .discovery import (
    SourceDiscoveryProvider,
    WebSearchDiscoveryProvider,
    city_id_from_name,
    classify_source,
)
from .service import CrawlServiceError, PolicyService


ACTIVE_JOB_STATUSES = frozenset({"queued", "discovering", "sources_ready", "crawling", "extracting"})


def _field_families() -> list[dict[str, Any]]:
    return [
        {
            "family": family,
            "queryTemplate": template,
            "fields": list(fields),
            "sourceHint": source_hint,
        }
        for family, template, fields, source_hint in FIELD_FAMILIES
    ]


def _domain(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


class CityOnboardingService:
    """城市自动入场服务。

    该服务不保存城市专属规则。发现器只接收城市名和字段族，正式来源、抓取
    与建议值均复用既有政策领域服务，确保新增城市不会产生另一套测算逻辑。
    """

    def __init__(
        self,
        repository: ProjectRepository,
        *,
        discovery_provider: SourceDiscoveryProvider | None = None,
        policy_service: PolicyService | Any | None = None,
        raw_dir: Path | None = None,
        crawl_allow_private: bool = False,
    ):
        self.repository = repository
        self.discovery_provider = discovery_provider or WebSearchDiscoveryProvider()
        self.policy_service = policy_service or PolicyService(repository)
        self.raw_dir = raw_dir or Path(__file__).resolve().parents[3] / "data" / "raw_sources"
        if hasattr(self.policy_service, "crawl_allow_private"):
            self.policy_service.crawl_allow_private = crawl_allow_private

    def start(self, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        active = self.repository.get_active_onboarding_job(project_id)
        if active is not None:
            return active
        city_name = str(project.get("city") or "").strip()
        city_id = str(project.get("cityId") or city_id_from_name(city_name))
        return self.repository.create_onboarding_job(
            {
                "projectId": project_id,
                "cityId": city_id,
                "cityName": city_name,
                "status": "queued",
                "phase": "queued",
                "totalQueries": len(FIELD_FAMILIES),
            }
        )

    def get_status(self, project_id: str) -> dict[str, Any]:
        jobs = self.repository.list_onboarding_jobs(project_id)
        if not jobs:
            raise KeyError(project_id)
        return jobs[0]

    def run_for_project(self, project_id: str) -> dict[str, Any]:
        job = self.start(project_id)
        if job.get("status") not in ACTIVE_JOB_STATUSES:
            return job
        return self.run(str(job["id"]))

    def retry_for_project(self, project_id: str) -> dict[str, Any]:
        job = self.get_status(project_id)
        if job.get("status") in ACTIVE_JOB_STATUSES:
            return job
        if job.get("status") not in {"failed", "partial_failed"}:
            return job
        return self.repository.update_onboarding_job(
            str(job["id"]),
            {
                "status": "queued",
                "phase": "queued",
                "totalQueries": len(FIELD_FAMILIES),
                "discoveredCount": 0,
                "officialSourceCount": 0,
                "candidateCount": 0,
                "crawledCount": 0,
                "suggestionCount": 0,
                "errorCount": 0,
                "errors": [],
                "startedAt": None,
                "finishedAt": None,
            },
        )

    def run(self, job_id: str) -> dict[str, Any]:
        job = self.repository.get_onboarding_job(job_id)
        if job.get("status") not in ACTIVE_JOB_STATUSES:
            return job

        started_at = utc_now()
        self.repository.update_onboarding_job(
            job_id,
            {"status": "discovering", "phase": "discovering", "startedAt": started_at, "errors": []},
        )
        errors: list[str] = []
        official_sources: list[dict[str, Any]] = []
        candidate_count = 0
        discovered: list[dict[str, Any]] = []
        try:
            discovered = self._dedupe_discovery(
                self.discovery_provider.discover(str(job["cityName"]), _field_families())
            )
        except Exception as error:  # discovery is optional; a failed provider cannot block editing
            errors.append(str(error))

        self.repository.update_onboarding_job(
            job_id,
            {
                "discoveredCount": len(discovered),
                "errorCount": len(errors),
                "errors": errors,
                "phase": "sources_ready",
                "status": "sources_ready",
            },
        )

        existing_sources = {
            str(item.get("url")): item
            for item in self.repository.list_data_sources(city_id=str(job["cityId"]))
            if item.get("url")
        }
        candidates: list[dict[str, Any]] = []
        for item in discovered:
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip() or url
            classification = classify_source(url, title)
            if classification == "rejected":
                errors.append(f"已跳过无效来源：{url or '空 URL'}")
                continue
            if classification == "candidate":
                candidates.append(
                    {
                        "url": url,
                        "name": title,
                        "title": title,
                        "domain": item.get("domain") or _domain(url),
                        "summary": item.get("summary"),
                        "targetFields": list(item.get("targetFields") or []),
                        "relevance": item.get("relevance"),
                        "origin": item.get("origin") or "web_search",
                    }
                )
                continue
            source = existing_sources.get(url)
            if source is None:
                try:
                    source = self.repository.create_data_source(
                        {
                            "cityId": job["cityId"],
                            "name": title,
                            "kind": "government",
                            "url": url,
                            "status": "active",
                            "note": f"新增城市自动发现：{item.get('family') or '通用政策数据源'}",
                        }
                    )
                    existing_sources[url] = source
                except Exception as error:
                    errors.append(f"来源入库失败 {url}：{error}")
                    continue
            if source.get("status") != "paused":
                official_sources.append(source)

        if candidates:
            candidate_result = AgentSubmissionService(self.repository).submit_candidate_sources(
                city_id=str(job["cityId"]), candidates=candidates
            )
            candidate_count = int(candidate_result.get("createdCount") or 0)

        self.repository.update_onboarding_job(
            job_id,
            {
                "officialSourceCount": len(official_sources),
                "candidateCount": candidate_count,
                "errorCount": len(errors),
                "errors": errors,
                "phase": "crawling",
                "status": "crawling",
            },
        )

        crawled_count = 0
        suggestion_field_ids: set[str] = set()
        for source in official_sources:
            try:
                artifact = self.policy_service.crawl_source_now(
                    str(source["id"]), raw_dir=self.raw_dir
                )
                if artifact.get("status") == "success":
                    crawled_count += 1
                for suggestion in artifact.get("suggestions") or []:
                    field_id = str(suggestion.get("fieldId") or "")
                    if field_id:
                        suggestion_field_ids.add(field_id)
                self._sync_suggestions_from_artifact(str(job["cityId"]), source, artifact)
            except CrawlServiceError as error:
                errors.append(f"{source.get('name') or source.get('url')}：{error.message}")
            except Exception as error:
                errors.append(f"{source.get('name') or source.get('url')}：{error}")
            self.repository.update_onboarding_job(
                job_id,
                {
                    "crawledCount": crawled_count,
                    "suggestionCount": len(suggestion_field_ids),
                    "errorCount": len(errors),
                    "errors": errors,
                },
            )

        final_status = "partial_failed" if errors else "completed"
        return self.repository.update_onboarding_job(
            job_id,
            {
                "status": final_status,
                "phase": "completed" if final_status == "completed" else "partial_failed",
                "crawledCount": crawled_count,
                "suggestionCount": len(suggestion_field_ids),
                "errorCount": len(errors),
                "errors": errors,
                "finishedAt": utc_now(),
            },
        )

    @staticmethod
    def _dedupe_discovery(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            result.append(dict(item))
        return result

    def _sync_suggestions_from_artifact(
        self, city_id: str, source: Mapping[str, Any], artifact: Mapping[str, Any]
    ) -> None:
        suggestions = artifact.get("suggestions") or []
        if not suggestions:
            return
        suggested_source = {
            "sourceId": source.get("id"),
            "sourceName": source.get("name") or source.get("id"),
            "url": artifact.get("finalUrl") or source.get("url"),
            "artifactId": artifact.get("artifactId"),
            "documentId": None,
        }
        for project in self.repository.list_projects():
            project_city_id = str(project.get("cityId") or city_id_from_name(str(project.get("city") or "")))
            if project_city_id != city_id:
                continue
            for scenario in project.get("scenarios") or []:
                existing = {
                    str(row.get("fieldId")): row
                    for row in self.repository.list_field_values(str(scenario["id"]))
                }
                for suggestion in suggestions:
                    field_id = str(suggestion.get("fieldId") or "")
                    if not field_id:
                        continue
                    current = existing.get(field_id) or {}
                    if current.get("valueState") in {"accepted", "overridden"}:
                        continue
                    if current.get("suggestedValue") is not None:
                        continue
                    row_source = dict(suggested_source)
                    row_source["quote"] = suggestion.get("quote")
                    self.repository.save_field_suggestion(
                        str(scenario["id"]), field_id, suggestion.get("value"), row_source
                    )
