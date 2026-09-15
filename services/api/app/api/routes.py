from __future__ import annotations

import csv
import hmac
import io
import json
import os
import re
import uuid
import zipfile
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse

from ..domain.u1.engine import DEFAULT_MODEL_VERSION, calculate_u1
from ..domain.u1.issues import load_known_issues
from ..domain.u1.models import FormulaValue, ModelIssue, MonthlyProjection, U1Result
from ..domain.u1.spec import (
    BLOCK_ORDER,
    ENUM_PARAMETER_OPTIONS,
    load_json_spec,
    load_parameter_catalog,
)
from ..domain.dashboard.aggregator import build_dashboard_overview
from ..domain.policy.agent_service import AgentSubmissionService, SubmissionError
from ..domain.policy.discovery import city_id_from_name
from ..domain.policy.onboarding_service import CityOnboardingService
from ..domain.policy.research_service import PolicyResearchService
from ..domain.policy.service import CrawlServiceError, PolicyService
from ..repository import ProjectRepository
from .schemas import (
    BulkSourceBatch,
    BrowserArtifactSubmit,
    DataSourceCreate,
    DataSourceUpdate,
    ExtractionSubmissionRequest,
    FetchRequestBatch,
    FieldValueUpdate,
    ProjectCreate,
    ScenarioCreate,
    ScenarioUpdate,
    SourceCandidateBatch,
    SourceCandidateReject,
    ResearchRunCompleteRequest,
    ResearchRunCreate,
    ResearchRunResultRequest,
)


router = APIRouter()


def repository_from_request(request: Request) -> ProjectRepository:
    return request.app.state.repository


def baseline_inputs() -> dict[str, Any]:
    return dict(load_json_spec("fixtures/u1-baseline.json")["inputs"])


def _camelize(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _serialize(value: Any) -> Any:
    if isinstance(value, FormulaValue):
        return {"value": value.value, "status": value.status, "errorCode": value.error_code}
    if isinstance(value, ModelIssue):
        return {
            "code": value.code,
            "excelCell": value.excelCell,
            "severity": value.severity,
            "status": value.status,
            "message": value.message,
        }
    if isinstance(value, MonthlyProjection):
        return {_camelize(field.name): _serialize(getattr(value, field.name)) for field in fields(value)}
    if is_dataclass(value):
        return {_camelize(field.name): _serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def result_to_dict(result: U1Result) -> dict[str, Any]:
    return {
        "modelVersion": result.model_version,
        "status": result.status,
        "parameters": _serialize(dict(result.parameters)),
        "months": [_serialize(month) for month in result.months],
        "stageSummary": _serialize(dict(result.stage_summary)),
        "headlineMetrics": _serialize(dict(result.headline_metrics)),
        "issues": [_serialize(issue) for issue in result.issues],
    }


def error_payload(code: str, message: str, field: str | None = None) -> JSONResponse:
    """PRD 16.8：错误返回稳定错误码、可读提示、相关字段与请求标识。"""
    error: dict[str, Any] = {"code": code, "message": message, "requestId": uuid.uuid4().hex}
    if field:
        error["field"] = field
    return JSONResponse(
        status_code=404 if code == "NOT_FOUND" else 400,
        content={"error": error},
    )


@router.get("/health")
@router.get("/status")
def health() -> dict[str, str]:
    return {"status": "ok", "modelVersion": DEFAULT_MODEL_VERSION}


def _dashboard_query(
    request: Request,
    scope: str,
    city_ids: str | None,
    period: int,
    scenario: str,
    include_stale: bool,
) -> dict[str, Any] | JSONResponse:
    if scope not in {"global", "city", "compare"}:
        return error_payload("INVALID_QUERY", "scope 必须是 global、city 或 compare", field="scope")
    if period not in {12, 24}:
        return error_payload("INVALID_QUERY", "period 必须是 12 或 24", field="period")
    if scenario != "latest":
        return error_payload("INVALID_QUERY", "当前仅支持 scenario=latest", field="scenario")
    ids = [item.strip() for item in (city_ids or "").split(",") if item.strip()]
    if scope == "city" and len(ids) != 1:
        return error_payload("INVALID_QUERY", "city 视图需要一个 cityIds", field="cityIds")
    if scope == "compare" and not ids:
        return error_payload("INVALID_QUERY", "compare 视图至少需要一个 cityIds", field="cityIds")
    repository = repository_from_request(request)
    policy_summary = PolicyService(repository).overview(ids if scope != "global" and ids else None)
    return build_dashboard_overview(
        repository.list_projects(),
        repository.list_snapshots(),
        scope=scope,
        city_ids=ids,
        period=period,
        include_stale=include_stale,
        policy_summary=policy_summary,
    )


@router.get("/dashboard/overview", response_model=None)
def dashboard_overview(
    request: Request,
    scope: str = "global",
    cityIds: str | None = None,
    period: int = 12,
    scenario: str = "latest",
    includeStale: bool = True,
) -> dict[str, Any] | JSONResponse:
    return _dashboard_query(request, scope, cityIds, period, scenario, includeStale)


@router.get("/dashboard/cities", response_model=None)
def dashboard_cities(request: Request, period: int = 12, includeStale: bool = True) -> list[dict[str, Any]] | JSONResponse:
    response = _dashboard_query(request, "global", None, period, "latest", includeStale)
    return response if isinstance(response, JSONResponse) else response["cities"]


@router.get("/dashboard/cities/{city_id}", response_model=None)
def dashboard_city(city_id: str, request: Request, period: int = 12, includeStale: bool = True) -> dict[str, Any] | JSONResponse:
    response = _dashboard_query(request, "city", city_id, period, "latest", includeStale)
    if isinstance(response, JSONResponse):
        return response
    return response["cities"][0] if response["cities"] else {"cityId": city_id, "hasValidResult": False, "dataStatus": "missing"}


@router.get("/dashboard/compare", response_model=None)
def dashboard_compare(request: Request, cityIds: str | None = None, period: int = 12, includeStale: bool = True) -> dict[str, Any] | JSONResponse:
    return _dashboard_query(request, "compare", cityIds, period, "latest", includeStale)


@router.get("/dashboard/issues", response_model=None)
def dashboard_issues(request: Request, period: int = 12, includeStale: bool = True) -> list[dict[str, Any]] | JSONResponse:
    response = _dashboard_query(request, "global", None, period, "latest", includeStale)
    return response if isinstance(response, JSONResponse) else response["alerts"]


@router.get("/dashboard/policy-summary", response_model=None)
def dashboard_policy_summary(request: Request, cityIds: str | None = None) -> dict[str, Any]:
    ids = [item.strip() for item in (cityIds or "").split(",") if item.strip()]
    return PolicyService(repository_from_request(request)).overview(ids or None)


@router.get("/policies/overview", response_model=None)
def policy_overview(request: Request, cityIds: str | None = None) -> dict[str, Any]:
    ids = [item.strip() for item in (cityIds or "").split(",") if item.strip()]
    return PolicyService(repository_from_request(request)).overview(ids or None)


@router.get("/policies/cities/{city_id}", response_model=None)
def policy_city_detail(city_id: str, request: Request) -> dict[str, Any]:
    return PolicyService(repository_from_request(request)).city_detail(city_id)


@router.get("/policies/sources", response_model=None)
def list_policy_sources(request: Request, cityId: str | None = None) -> list[dict[str, Any]]:
    return repository_from_request(request).list_data_sources(cityId)


# ---------- 来源新鲜度（防「静默过期」） ----------
#
# 背景：SHA256 变更检测只能回答「这一页变了吗」，回答不了「有没有更新的页」。
# 年度文档（如「长沙市2025年统计公报」）每年换一个新 URL，固定 URL 的来源
# 会逐轮返回 unchanged，页面上看起来一切正常，实际永远停在旧版本。
# 这里用「自上次实质内容变更以来的天数」把这个风险量化出来。

SOURCE_STALE_DAYS = int(os.getenv("UE_AGENT_STALE_DAYS", "365"))
SOURCE_AGING_DAYS = int(os.getenv("UE_AGENT_AGING_DAYS", "180"))
_YEAR_PATTERN = re.compile(r"20\d{2}")


def _source_freshness(repository: ProjectRepository, source: Mapping[str, Any]) -> dict[str, Any]:
    """算单个来源的新鲜度。

    只把 changeStatus 为 first_fetch / new_version 的抓取视为「实质内容变更」——
    后面连续 unchanged 都说明页面没动，但**不代表没过期**。
    """
    artifacts = repository.list_crawl_artifacts(source_id=str(source.get("id")))
    changed_at = [
        str(item.get("fetchedAt"))
        for item in artifacts
        if item.get("changeStatus") in ("first_fetch", "new_version") and item.get("fetchedAt")
    ]
    last_changed_at = max(changed_at) if changed_at else None

    days: int | None = None
    if last_changed_at:
        try:
            moment = datetime.fromisoformat(last_changed_at.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            days = max(0, int((datetime.now(timezone.utc) - moment).total_seconds() // 86400))
        except ValueError:
            days = None

    # 名称或 URL 里带年份 → 大概率是「年度文档」，跨年就该换新链接
    looks_annual = bool(_YEAR_PATTERN.search(f"{source.get('name') or ''} {source.get('url') or ''}"))

    if days is None:
        level, reason = "unknown", "暂无抓取记录"
    elif looks_annual and days >= SOURCE_STALE_DAYS:
        level, reason = "stale", f"年度文档已 {days} 天无内容变更，可能已有新年度版本"
    elif days >= SOURCE_STALE_DAYS:
        level, reason = "aging", f"已 {days} 天无内容变更，建议确认是否仍有效"
    elif days >= SOURCE_AGING_DAYS:
        level, reason = "aging", f"已 {days} 天无内容变更"
    else:
        level, reason = "ok", None

    return {
        "sourceId": source.get("id"),
        "name": source.get("name"),
        "url": source.get("url"),
        "status": source.get("status"),
        "lastFetchedAt": source.get("lastFetchedAt"),
        "lastContentChangedAt": last_changed_at,
        "daysSinceChange": days,
        "looksAnnual": looks_annual,
        "level": level,
        "reason": reason,
    }


@router.get("/policies/cities/{city_id}/source-freshness", response_model=None)
def city_source_freshness(city_id: str, request: Request) -> dict[str, Any]:
    """城市级来源新鲜度体检：谁可能已经过期，需要去找新年度版本。"""
    repository = repository_from_request(request)
    items = [
        _source_freshness(repository, source)
        for source in repository.list_data_sources()
        if str(source.get("cityId") or "") == city_id
    ]
    items.sort(key=lambda item: (item["level"] != "stale", -(item["daysSinceChange"] or 0)))
    return {
        "cityId": city_id,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "staleDays": SOURCE_STALE_DAYS,
        "agingDays": SOURCE_AGING_DAYS,
        "counts": {
            "total": len(items),
            "stale": sum(1 for item in items if item["level"] == "stale"),
            "aging": sum(1 for item in items if item["level"] == "aging"),
            "unknown": sum(1 for item in items if item["level"] == "unknown"),
        },
        "sources": items,
    }


@router.post("/policies/sources", status_code=201)
def create_policy_source(payload: DataSourceCreate, request: Request) -> dict[str, Any]:
    return repository_from_request(request).create_data_source(payload.model_dump())


@router.post("/policies/cities/{city_id}/sources/bulk", response_model=None)
def bulk_create_policy_sources(
    city_id: str, payload: BulkSourceBatch, request: Request
) -> dict[str, Any]:
    """批量预置来源 —— 「新增城市一键配置来源」的执行端。

    逐个建 + 立即抓取验证，单条失败不影响其余。**不可达的会自动停用**：
    本仓库没有删除来源的接口，停用等价于「不进后续轮次」（crawl-all 会跳过 paused），
    同时保留记录便于人工改 URL 后重新启用 —— 避免把猜错的域名留成反复失败的活跃来源。
    """
    repository = repository_from_request(request)
    service = PolicyService(repository)
    service.crawl_allow_private = _crawl_allow_private(request)
    raw_dir = _raw_sources_dir(request)

    known = {
        str(source.get("url"))
        for source in repository.list_data_sources()
        if str(source.get("cityId") or "") == city_id
    }

    results: list[dict[str, Any]] = []
    for item in payload.sources:
        url = item.url.strip()
        entry: dict[str, Any] = {
            "name": item.name,
            "url": url,
            "sourceId": None,
            "status": "created",
            "httpStatus": None,
            "title": None,
            "message": None,
        }
        if url in known:
            entry.update(status="duplicate", message="该城市已有同 URL 来源")
            results.append(entry)
            continue
        if not url.startswith(("http://", "https://")):
            entry.update(status="rejected", message="仅接受 http/https 链接")
            results.append(entry)
            continue

        source = repository.create_data_source(
            {"cityId": city_id, "name": item.name, "kind": "web", "url": url, "note": item.note}
        )
        known.add(url)
        entry["sourceId"] = source.get("id")
        if not payload.verify:
            results.append(entry)
            continue

        try:
            artifact = service.crawl_source_now(str(source.get("id")), raw_dir=raw_dir)
        except CrawlServiceError as error:
            if error.details.get("fallbackAction") == "browser_search":
                entry.update(status="browser_required", message=error.message, **error.details)
            else:
                repository.update_data_source(
                    str(source.get("id")),
                    {"status": "paused", "note": f"自动预置时不可达，已停用：{error.message}"},
                )
                entry.update(status="unreachable", message=error.message, **error.details)
            results.append(entry)
            continue

        entry.update(
            status="verified",
            httpStatus=artifact.get("httpStatus"),
            title=artifact.get("title"),
        )
        results.append(entry)

    return {
        "cityId": city_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "verified": sum(1 for item in results if item["status"] == "verified"),
        "created": sum(1 for item in results if item["status"] == "created"),
        "duplicate": sum(1 for item in results if item["status"] == "duplicate"),
        "rejected": sum(1 for item in results if item["status"] == "rejected"),
        "unreachable": sum(1 for item in results if item["status"] == "unreachable"),
        "browserRequired": sum(1 for item in results if item["status"] == "browser_required"),
        "results": results,
    }


@router.put("/policies/sources/{source_id}", response_model=None)
def update_policy_source(source_id: str, payload: DataSourceUpdate, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return repository_from_request(request).update_data_source(source_id, payload.model_dump(exclude_none=True))
    except KeyError:
        return error_payload("NOT_FOUND", f"Data source not found: {source_id}")


def _raw_sources_dir(request: Request) -> Path:
    from ..sqlite_repository import default_data_dir

    repository = repository_from_request(request)
    data_dir = getattr(repository, "path", None)
    if data_dir is not None:
        return Path(data_dir).parent / "raw_sources"
    return default_data_dir() / "raw_sources"


def _crawl_allow_private(request: Request) -> bool:
    """仅测试用：允许通过 app.state.crawl_allow_private 放行本机地址。"""
    return bool(getattr(request.app.state, "crawl_allow_private", False))


@router.post("/policies/sources/{source_id}/crawl", response_model=None)
def crawl_policy_source(source_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    service = PolicyService(repository_from_request(request))
    service.crawl_allow_private = _crawl_allow_private(request)
    try:
        return service.crawl_source_now(source_id, raw_dir=_raw_sources_dir(request))
    except CrawlServiceError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message, **error.details}},
        )


@router.post("/policies/cities/{city_id}/crawl-all", response_model=None)
def crawl_all_policy_sources(city_id: str, request: Request) -> dict[str, Any]:
    """一键抓取该城市所有「启用」来源（顺序执行，逐条返回结果）。

    单个来源失败不中断整批 —— 只记录该条失败原因，其余照常抓取，
    这样一次点击就能拿到全量新鲜度，而不是逐个点按钮。
    已停用（paused）的来源会被跳过并标注原因。
    """
    repository = repository_from_request(request)
    service = PolicyService(repository)
    service.crawl_allow_private = _crawl_allow_private(request)
    raw_dir = _raw_sources_dir(request)

    results: list[dict[str, Any]] = []
    for source in repository.list_data_sources():
        if str(source.get("cityId") or "") != city_id:
            continue
        source_id = str(source.get("id"))
        name = source.get("name")
        if str(source.get("status") or "") == "paused":
            results.append(
                {
                    "sourceId": source_id,
                    "name": name,
                    "status": "skipped",
                    "changeStatus": None,
                    "httpStatus": source.get("lastHttpStatus"),
                    "fallbackAction": source.get("lastFallbackAction"),
                    "fallbackReason": source.get("lastFallbackReason"),
                    "message": "来源已停用，未抓取",
                }
            )
            continue
        try:
            artifact = service.crawl_source_now(source_id, raw_dir=raw_dir)
        except CrawlServiceError as error:
            results.append(
                {
                    "sourceId": source_id,
                    "name": name,
                    "status": "browser_required" if error.details.get("fallbackAction") == "browser_search" else "failed",
                    "changeStatus": None,
                    **error.details,
                    "message": error.message,
                }
            )
            continue
        results.append(
            {
                "sourceId": source_id,
                "name": name,
                "status": "success",
                "changeStatus": artifact.get("changeStatus"),
                "httpStatus": artifact.get("httpStatus"),
                "fallbackAction": artifact.get("fallbackAction"),
                "fallbackReason": artifact.get("fallbackReason"),
                "message": None,
            }
        )

    return {
        "cityId": city_id,
        "crawledAt": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "succeeded": sum(1 for item in results if item["status"] == "success"),
        "failed": sum(1 for item in results if item["status"] in {"failed", "browser_required"}),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
        # 未变 / 有更新 直接对应「省下的抽取量」与「值得送 AI 的量」
        "unchanged": sum(1 for item in results if item.get("changeStatus") == "unchanged"),
        "changed": sum(
            1 for item in results if item.get("changeStatus") in ("first_fetch", "new_version")
        ),
        "results": results,
    }


@router.get("/policies/sources/{source_id}/artifacts", response_model=None)
def list_source_artifacts(source_id: str, request: Request) -> list[dict[str, Any]] | JSONResponse:
    try:
        repository_from_request(request).list_data_sources()
    except KeyError:
        return error_payload("NOT_FOUND", f"Data source not found: {source_id}")
    return repository_from_request(request).list_crawl_artifacts(source_id=source_id)


@router.get("/policies/artifacts/{artifact_id}", response_model=None)
def get_crawl_artifact(artifact_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return repository_from_request(request).get_crawl_artifact(artifact_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Crawl artifact not found: {artifact_id}")


@router.get("/policies/artifacts/{artifact_id}/content")
def crawl_artifact_content(artifact_id: str, request: Request) -> Response:
    repository = repository_from_request(request)
    try:
        artifact = repository.get_crawl_artifact(artifact_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Crawl artifact not found: {artifact_id}")
    stored_path = artifact.get("storedPath")
    if not stored_path:
        return error_payload("NOT_FOUND", "该抓取记录没有保存原文")
    raw_dir = _raw_sources_dir(request)
    # storedPath 形如 raw_sources/<sha>.bin，只允许拼接受控相对路径
    from ..repository import LocalPolicyFileStore

    try:
        content = LocalPolicyFileStore(raw_dir.parent).get(stored_path)
    except (FileNotFoundError, ValueError):
        return error_payload("NOT_FOUND", "抓取原文文件不存在")
    return Response(
        content=content,
        media_type=artifact.get("contentType") or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{artifact_id}"'},
    )


# ---------- WorkBuddy AI 回传链路（设计文档 8.5） ----------
#
# 职责边界：AI 检索与字段抽取由 WorkBuddy 执行；本服务只做确定性部分
# —— 派活、抓取落档、回传校验、写建议值。
# 回传类接口用静态 token 校验（UE_AGENT_AGENT_TOKEN），防止公网发布后裸奔。


def _agent_token_required(request: Request) -> JSONResponse | None:
    """校验 WorkBuddy 回传凭证。未配置 token 时（本地开发）放行。"""
    expected = os.getenv("UE_AGENT_AGENT_TOKEN", "").strip()
    if not expected:
        return None
    provided = (
        request.headers.get("x-ue-agent-token")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    if not hmac.compare_digest(provided, expected):
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "UNAUTHORIZED", "message": "回传凭证无效或缺失"}},
        )
    return None


def _agent_service(request: Request) -> AgentSubmissionService:
    return AgentSubmissionService(repository_from_request(request))


def _research_service(request: Request) -> PolicyResearchService:
    return PolicyResearchService(repository_from_request(request), load_parameter_catalog())


@router.post("/policies/research-runs", response_model=None)
def create_policy_research_run(payload: ResearchRunCreate, request: Request) -> JSONResponse:
    """创建一次按需实时政策检索；重复点击同一城市会复用 active run。"""
    repository = repository_from_request(request)
    if payload.projectId:
        try:
            project = repository.get_project(payload.projectId)
        except KeyError:
            return error_payload("NOT_FOUND", f"Project not found: {payload.projectId}")
        project_city_id = str(project.get("cityId") or project.get("city") or "")
        if project_city_id and project_city_id != payload.cityId:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "CITY_PROJECT_MISMATCH", "message": "项目与城市不匹配"}},
            )
    existing = repository.get_active_research_run(payload.cityId)
    try:
        run = _research_service(request).create_run(
            city_id=payload.cityId,
            project_id=payload.projectId,
            trigger=payload.trigger,
            scope=payload.scope,
            fields=payload.fields,
        )
    except ValueError as error:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": str(error), "message": str(error)}},
        )
    return JSONResponse(status_code=200 if existing is not None else 201, content=run)


@router.get("/policies/research-runs", response_model=None)
def list_policy_research_runs(
    request: Request, cityId: str | None = None, limit: int = 20
) -> list[dict[str, Any]] | JSONResponse:
    if limit < 1 or limit > 100:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_LIMIT", "message": "limit 必须在 1 到 100 之间"}},
        )
    return repository_from_request(request).list_research_runs(city_id=cityId, limit=limit)


@router.get("/policies/research-runs/{run_id}", response_model=None)
def get_policy_research_run(run_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return _research_service(request).get_run(run_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"政策检索任务不存在：{run_id}")


@router.get("/policies/research-runs/{run_id}/brief", response_model=None)
def get_policy_research_brief(run_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return _research_service(request).build_brief(run_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"政策检索任务不存在：{run_id}")


@router.post("/policies/research-runs/{run_id}/retry", response_model=None)
def retry_policy_research_run(run_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return _research_service(request).retry(run_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"政策检索任务不存在：{run_id}")
    except ValueError as error:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": str(error), "message": str(error)}},
        )


@router.post("/policies/research-runs/{run_id}/complete", response_model=None)
def complete_policy_research_run(
    run_id: str, payload: ResearchRunCompleteRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    unauthorized = _agent_token_required(request)
    if unauthorized is not None:
        return unauthorized
    try:
        return _research_service(request).complete(
            run_id,
            status=payload.status,
            agent_run_id=payload.agentRunId,
            agent_version=payload.agentVersion,
            errors=payload.errors,
        )
    except KeyError:
        return error_payload("NOT_FOUND", f"政策检索任务不存在：{run_id}")
    except ValueError as error:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": str(error), "message": str(error)}},
        )


@router.post("/policies/research-runs/{run_id}/results", response_model=None)
def submit_policy_research_results(
    run_id: str, payload: ResearchRunResultRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    """接收 WorkBuddy 发现的来源和抽取结果，复用既有确定性校验链路。"""
    unauthorized = _agent_token_required(request)
    if unauthorized is not None:
        return unauthorized
    service = _research_service(request)
    try:
        run = service.get_run(run_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"政策检索任务不存在：{run_id}")
    if not payload.candidates and not payload.submissions:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "EMPTY_RESEARCH_RESULTS", "message": "候选来源和抽取结果不能同时为空"}},
        )
    if run.get("status") == "awaiting_review" and payload.agentRunId and run.get("agentRunId") == payload.agentRunId:
        return {"run": run, "candidateResult": {"createdCount": 0, "skippedCount": 0}, "extractionResult": None, "idempotent": True}
    candidate_result: dict[str, Any] = {"createdCount": 0, "skippedCount": 0, "created": [], "skipped": []}
    extraction_result: dict[str, Any] | None = None
    try:
        if payload.candidates:
            candidate_result = _agent_service(request).submit_candidate_sources(
                city_id=str(run["cityId"]),
                candidates=[item.model_dump() for item in payload.candidates],
                research_run_id=run_id,
            )
        if payload.submissions:
            extraction_result = _agent_service(request).submit_extraction(
                city_id=str(run["cityId"]),
                catalog=load_parameter_catalog(),
                submissions=[item.model_dump() for item in payload.submissions],
                agent_run_id=payload.agentRunId,
                agent_version=payload.agentVersion,
                research_run_id=run_id,
            )
        updated = service.record_results(
            run_id,
            agent_run_id=payload.agentRunId,
            agent_version=payload.agentVersion,
            source_count=len(payload.candidates),
            new_source_count=int(candidate_result.get("createdCount") or 0),
            fetched_count=sum(1 for item in payload.submissions if item.artifactId),
            suggestion_count=int((extraction_result or {}).get("acceptedCount") or 0),
        )
    except SubmissionError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )
    except ValueError as error:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": str(error), "message": str(error)}},
        )
    return {"run": updated, "candidateResult": candidate_result, "extractionResult": extraction_result}


@router.get("/policies/crawl-targets", response_model=None)
def policy_crawl_targets(request: Request) -> dict[str, Any]:
    """派活：给 WorkBuddy 的待办清单（已配置来源 + 增量感知的待填字段）。"""
    return _agent_service(request).crawl_targets(load_parameter_catalog())


@router.post("/policies/fetch-requests", response_model=None)
def policy_fetch_requests(payload: FetchRequestBatch, request: Request) -> dict[str, Any] | JSONResponse:
    """WorkBuddy 声明要读的 URL，由服务端抓取落档并回传正文文本。

    复用现有抓取链路（SSRF 防护、原文存档、SHA256 变更检测），
    使「AI 决定读什么」与「存档与变更检测」两者兼得。
    """
    unauthorized = _agent_token_required(request)
    if unauthorized is not None:
        return unauthorized
    research_service = _research_service(request) if payload.researchRunId else None
    if research_service is not None:
        try:
            run = research_service.get_run(payload.researchRunId or "")
        except KeyError:
            return error_payload("NOT_FOUND", f"政策检索任务不存在：{payload.researchRunId}")
        requested_cities = {item.cityId for item in payload.requests if item.cityId}
        if requested_cities and requested_cities != {str(run["cityId"])}:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "CITY_RESEARCH_RUN_MISMATCH", "message": "抓取城市与检索任务不匹配"}},
            )
        research_service.mark_progress(
            payload.researchRunId,
            status="fetching",
            phase="fetching",
        )
    service = PolicyService(repository_from_request(request))
    service.crawl_allow_private = _crawl_allow_private(request)
    results = service.fetch_for_agent(
        requests=[item.model_dump() for item in payload.requests],
        raw_dir=_raw_sources_dir(request),
        max_chars=payload.maxChars or 40000,
        research_run_id=payload.researchRunId,
    )
    if research_service is not None:
        research_service.mark_progress(
            payload.researchRunId or "",
            status="extracting",
            phase="extracting",
            fetched_count=sum(1 for item in results if item.get("status") == "success"),
            changed_source_count=sum(1 for item in results if item.get("changeStatus") == "new_version"),
        )
    return {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "requested": len(payload.requests),
        "succeeded": sum(1 for item in results if item.get("status") == "success"),
        "failed": sum(1 for item in results if item.get("status") == "failed"),
        "unchanged": sum(1 for item in results if item.get("changeStatus") == "unchanged"),
        "results": results,
    }


@router.post("/policies/browser-artifacts", response_model=None)
def archive_policy_browser_artifact(
    payload: BrowserArtifactSubmit, request: Request
) -> dict[str, Any] | JSONResponse:
    """接收 WorkBuddy 浏览器通道看到的官方正文，归档后进入同一证据链。"""
    unauthorized = _agent_token_required(request)
    if unauthorized is not None:
        return unauthorized
    if payload.researchRunId:
        try:
            run = _research_service(request).get_run(payload.researchRunId)
        except KeyError:
            return error_payload("NOT_FOUND", f"政策检索任务不存在：{payload.researchRunId}")
        if str(run["cityId"]) != payload.cityId:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "CITY_RESEARCH_RUN_MISMATCH", "message": "回传城市与检索任务不匹配"}},
            )
    try:
        return PolicyService(repository_from_request(request)).archive_browser_artifact(
            city_id=payload.cityId,
            source_id=payload.sourceId,
            research_run_id=payload.researchRunId,
            requested_url=payload.requestedUrl,
            final_url=payload.finalUrl,
            title=payload.title,
            content=payload.content,
            content_type=payload.contentType,
            raw_dir=_raw_sources_dir(request),
        )
    except CrawlServiceError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message, **error.details}},
        )


@router.post("/policies/extraction-submissions", response_model=None)
def policy_extraction_submissions(
    payload: ExtractionSubmissionRequest, request: Request
) -> dict[str, Any] | JSONResponse:
    """接收 WorkBuddy 的字段抽取结果，逐条校验后写入灰色建议值。"""
    unauthorized = _agent_token_required(request)
    if unauthorized is not None:
        return unauthorized
    research_service = _research_service(request) if payload.researchRunId else None
    if research_service is not None:
        try:
            run = research_service.get_run(payload.researchRunId or "")
        except KeyError:
            return error_payload("NOT_FOUND", f"政策检索任务不存在：{payload.researchRunId}")
        if str(run["cityId"]) != payload.cityId:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "CITY_RESEARCH_RUN_MISMATCH", "message": "抽取城市与检索任务不匹配"}},
            )
        research_service.mark_progress(
            payload.researchRunId,
            status="extracting",
            phase="extracting",
            agent_run_id=payload.agentRunId,
            agent_version=payload.agentVersion,
        )
    try:
        result = _agent_service(request).submit_extraction(
            city_id=payload.cityId,
            catalog=load_parameter_catalog(),
            submissions=[item.model_dump() for item in payload.submissions],
            agent_run_id=payload.agentRunId,
            agent_version=payload.agentVersion,
            research_run_id=payload.researchRunId,
        )
        if research_service is not None:
            research_service.record_results(
                payload.researchRunId or "",
                agent_run_id=payload.agentRunId,
                agent_version=payload.agentVersion,
                suggestion_count=int(result.get("acceptedCount") or 0),
            )
        return result
    except SubmissionError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )


@router.post("/policies/source-candidates", status_code=201, response_model=None)
def create_source_candidates(
    payload: SourceCandidateBatch, request: Request
) -> dict[str, Any] | JSONResponse:
    """AI 检索发现的候选来源入池（不直接转为正式来源，需人工确认）。"""
    unauthorized = _agent_token_required(request)
    if unauthorized is not None:
        return unauthorized
    if payload.researchRunId:
        try:
            run = _research_service(request).get_run(payload.researchRunId)
        except KeyError:
            return error_payload("NOT_FOUND", f"政策检索任务不存在：{payload.researchRunId}")
        if str(run["cityId"]) != payload.cityId:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "CITY_RESEARCH_RUN_MISMATCH", "message": "来源城市与检索任务不匹配"}},
            )
    try:
        return _agent_service(request).submit_candidate_sources(
            city_id=payload.cityId,
            candidates=[item.model_dump() for item in payload.candidates],
            research_run_id=payload.researchRunId,
        )
    except SubmissionError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )


@router.get("/policies/source-candidates", response_model=None)
def list_source_candidates(
    request: Request, cityId: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    return repository_from_request(request).list_candidate_sources(city_id=cityId, status=status)


@router.post("/policies/source-candidates/{candidate_id}/promote", response_model=None)
def promote_source_candidate(candidate_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    """人工确认：候选来源转为正式 DataSource，纳入后续抓取。"""
    try:
        return _agent_service(request).promote_candidate_source(candidate_id)
    except SubmissionError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )


@router.post("/policies/source-candidates/{candidate_id}/reject", response_model=None)
def reject_source_candidate(
    candidate_id: str, payload: SourceCandidateReject, request: Request
) -> dict[str, Any] | JSONResponse:
    try:
        return _agent_service(request).reject_candidate_source(candidate_id, payload.reason)
    except SubmissionError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )


@router.get("/policies/extraction-submissions", response_model=None)
def list_extraction_submissions(
    request: Request, cityId: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    """回传审计记录：供页面展示「上次 AI 抓取新增了多少候选值」。"""
    return repository_from_request(request).list_extraction_submissions(city_id=cityId, limit=limit)


@router.get("/policies/documents", response_model=None)
def list_policy_documents(request: Request, cityId: str | None = None) -> list[dict[str, Any]]:
    return repository_from_request(request).list_policy_documents(cityId)


@router.get("/policies/documents/{document_id}", response_model=None)
def get_policy_document(document_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return repository_from_request(request).get_policy_document(document_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Policy document not found: {document_id}")


@router.get("/policies/documents/{document_id}/content")
def policy_document_content(document_id: str, request: Request) -> Response:
    repository = repository_from_request(request)
    try:
        document = repository.get_policy_document(document_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Policy document not found: {document_id}")
    try:
        content = repository.read_policy_document(document)
    except (FileNotFoundError, KeyError):
        return error_payload("NOT_FOUND", f"Policy file not found: {document_id}")
    return Response(
        content=content,
        media_type=document.get("mimeType"),
        headers={"Content-Disposition": f'inline; filename="{document.get("originalName", "policy")}"'},
    )


@router.post("/policies/documents/upload", status_code=404, response_model=None, include_in_schema=False)
async def upload_policy_document() -> JSONResponse:
    """PRD 16.4：Demo 不提供政策文件手动上传接口；政策文件由抓取接口产生。"""
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "UPLOAD_NOT_AVAILABLE", "message": "Demo 阶段不提供政策文件手动上传，请配置官网来源并一键抓取"}},
    )


# ---------- 政策导出（PRD 16.7 / 11.12 / 22.3） ----------

_EXPORT_FIELD_HEADER = [
    "城市", "项目", "场景", "参数编号", "参数名称", "单位", "数据源类型",
    "当前实际值", "建议值", "值状态", "建议来源", "建议采集时间",
]
_EXPORT_SOURCE_HEADER = [
    "城市", "来源ID", "来源名称", "类型", "链接", "状态",
    "最近抓取时间", "最近HTTP状态", "最近变更", "最近抓取通道", "兜底动作", "备注",
]
_EXPORT_ARTIFACT_HEADER = [
    "抓取记录ID", "来源ID", "城市", "请求URL", "最终URL", "抓取时间", "HTTP状态",
    "内容类型", "字节数", "SHA256", "标题", "变更状态", "状态", "抓取通道", "兜底动作", "错误信息",
]


def _csv_response(filename: str, header: list[str], rows: list[list[Any]]) -> Response:
    """UTF-8 带 BOM 的 CSV，保证 Excel 正确显示中文（PRD 20.4）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return Response(
        content=("\ufeff" + buffer.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def _zip_response(source_id: str, artifacts: list[dict[str, Any]], request: Request) -> Response:
    """PRD 16.7：把某个来源的抓取原文打包成 ZIP，附带抓取记录清单。"""
    from ..repository import LocalPolicyFileStore

    raw_dir = _raw_sources_dir(request)
    store = LocalPolicyFileStore(raw_dir.parent)

    buffer = io.BytesIO()
    manifest_rows: list[list[Any]] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for artifact in artifacts:
            artifact_id = artifact.get("artifactId") or artifact.get("id")
            stored_path = artifact.get("storedPath")
            raw_name = f"{artifact_id}.bin"
            if stored_path:
                try:
                    content = store.get(stored_path)
                except (FileNotFoundError, ValueError):
                    content = None
                else:
                    raw_name = Path(stored_path).name or raw_name
                    archive.writestr(f"raw/{raw_name}", content)
            manifest_rows.append(
                [
                    artifact_id, raw_name if stored_path else "", artifact.get("sha256"),
                    artifact.get("title"), artifact.get("fetchedAt"), artifact.get("httpStatus"),
                    artifact.get("changeStatus"), artifact.get("status"), artifact.get("fetchMode"),
                    artifact.get("fallbackAction"), artifact.get("errorMessage"),
                ]
            )
        manifest_csv = io.StringIO()
        writer = csv.writer(manifest_csv)
        writer.writerow(["抓取记录ID", "原始文件名", "SHA256", "标题", "抓取时间", "HTTP状态", "变更状态", "状态", "抓取通道", "兜底动作", "错误信息"])
        for row in manifest_rows:
            writer.writerow(["" if value is None else value for value in row])
        archive.writestr("manifest.csv", ("\ufeff" + manifest_csv.getvalue()).encode("utf-8"))

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'政策原文-{source_id}.zip')}"},
    )


def _source_name_of(row: Mapping[str, Any]) -> Any:
    source = row.get("suggestedSource")
    return source.get("sourceName") if isinstance(source, Mapping) else None


def _collect_export_data(
    repository: ProjectRepository, city_id: str | None, source_id: str | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """汇总来源、抓取记录与政策字段值；建议值、实际值与覆盖值分列保留。"""
    sources = repository.list_data_sources(city_id)
    if source_id:
        sources = [item for item in sources if item["id"] == source_id]
    artifacts: list[dict[str, Any]] = []
    for source in sources:
        artifacts.extend(repository.list_crawl_artifacts(source_id=source["id"]))
    if source_id and not artifacts:
        artifacts = repository.list_crawl_artifacts(source_id=source_id)

    projects = repository.list_projects()
    if city_id:
        projects = [p for p in projects if p.get("city") == city_id or p.get("cityId") == city_id]
    catalog = load_parameter_catalog()
    field_rows: list[dict[str, Any]] = []
    for project in projects:
        for scenario in project.get("scenarios", []):
            try:
                detail = repository.get_scenario(project["id"], scenario["id"])
            except KeyError:
                continue
            inputs = detail.get("inputs") or {}
            rows = {row["fieldId"]: row for row in repository.list_field_values(scenario["id"])}
            for entry in catalog.values():
                view = _field_value_view(entry, inputs.get(entry["id"]), rows.get(entry["id"]))
                if view["suggestedValue"] is None and view["valueState"] not in ("accepted", "overridden"):
                    continue  # 只导出与政策建议值相关的字段，避免 75 行全量噪音
                field_rows.append(
                    {
                        "city": project.get("city"),
                        "projectName": project.get("name"),
                        "scenarioName": scenario.get("name"),
                        **view,
                    }
                )
    return sources, artifacts, field_rows


@router.get("/policies/export", response_model=None)
def export_policies(
    request: Request,
    format: str = "csv",
    scope: str = "global",
    cityId: str | None = None,
    sourceId: str | None = None,
    dataset: str = "fields",
) -> Response | JSONResponse:
    """PRD 16.7：导出政策来源、抓取记录与结构化政策字段。

    建议值、实际值和手工覆盖值分列导出，并附带来源、采集时间和状态（PRD 11.12）。
    """
    if format not in ("csv", "json", "zip"):
        return error_payload("UNSUPPORTED_EXPORT_FORMAT", f"不支持的导出格式：{format}，可选 csv、json 或 zip")
    if format in ("csv", "json") and dataset not in ("fields", "sources", "artifacts"):
        return error_payload(
            "UNSUPPORTED_EXPORT_DATASET", f"不支持的导出内容：{dataset}，可选 fields、sources 或 artifacts"
        )

    repository = repository_from_request(request)
    sources, artifacts, field_rows = _collect_export_data(repository, cityId, sourceId)
    label = cityId or sourceId or scope

    if format == "zip":
        if not sourceId:
            return error_payload("MISSING_EXPORT_SOURCE", "ZIP 导出需要指定 sourceId", field="sourceId")
        if not artifacts:
            return error_payload("NOT_FOUND", f"该来源没有可导出的抓取原文：{sourceId}")
        return _zip_response(sourceId, artifacts, request)

    if format == "json":
        body = json.dumps(
            {
                "exportedAt": datetime.now(timezone.utc).isoformat(),
                "scope": scope,
                "cityId": cityId,
                "sourceId": sourceId,
                "sources": sources,
                "artifacts": artifacts,
                "fieldValues": field_rows,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'政策导出-{label}.json')}"},
        )

    if dataset == "sources":
        return _csv_response(
            f"政策来源-{label}.csv",
            _EXPORT_SOURCE_HEADER,
            [
                [
                    s.get("cityId"), s.get("id"), s.get("name"), s.get("kind"), s.get("url"), s.get("status"),
                    s.get("lastFetchedAt"), s.get("lastHttpStatus"), s.get("lastChangeStatus"),
                    s.get("lastFetchMode"), s.get("fallbackAction") or s.get("lastFallbackAction"), s.get("note"),
                ]
                for s in sources
            ],
        )

    if dataset == "artifacts":
        return _csv_response(
            f"抓取记录-{label}.csv",
            _EXPORT_ARTIFACT_HEADER,
            [
                [
                    a.get("artifactId"), a.get("sourceId"), a.get("cityId"), a.get("requestedUrl"), a.get("finalUrl"),
                    a.get("fetchedAt"), a.get("httpStatus"), a.get("contentType"), a.get("contentLength"),
                    a.get("sha256"), a.get("title"), a.get("changeStatus"), a.get("status"), a.get("fetchMode"),
                    a.get("fallbackAction"), a.get("errorMessage"),
                ]
                for a in artifacts
            ],
        )

    return _csv_response(
        f"政策字段-{label}.csv",
        _EXPORT_FIELD_HEADER,
        [
            [
                f.get("city"), f.get("projectName"), f.get("scenarioName"), f.get("fieldId"), f.get("name"),
                f.get("unit"), f.get("sourceType"), f.get("currentValue"), f.get("suggestedValue"),
                f.get("valueState"), _source_name_of(f), f.get("suggestedAt"),
            ]
            for f in field_rows
        ],
    )


@router.get("/model/u1")
def model_u1() -> dict[str, Any]:
    catalog = load_parameter_catalog()
    return {
        "modelVersion": DEFAULT_MODEL_VERSION,
        "parameters": list(catalog.values()),
        "baselineInputs": baseline_inputs(),
        "issues": [_serialize(issue) for issue in load_known_issues()],
    }


def field_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """字段控制契约：只读、可编辑与枚举选项由 sourceType 和字典共同决定。"""
    read_only = entry["sourceType"] == "公式自动"
    return {
        "fieldId": entry["id"],
        "name": entry["name"],
        "unit": entry["unit"],
        "excelCell": entry["excelCell"],
        "sourceType": entry["sourceType"],
        "block": entry["block"],
        "blockOrder": entry["blockOrder"],
        "stage": entry["stage"],
        "valueType": entry["valueType"],
        "required": entry["required"],
        "editable": not read_only,
        "readOnly": read_only,
        "options": entry.get("options"),
    }


@router.get("/fields", response_model=None)
def list_fields(block: str | None = None) -> dict[str, Any] | JSONResponse:
    if block is not None and block not in BLOCK_ORDER:
        return error_payload("INVALID_QUERY", f"block 必须是 {'、'.join(BLOCK_ORDER)} 之一")
    catalog = load_parameter_catalog()
    entries = list(catalog.values())
    if block is not None:
        entries = [entry for entry in entries if entry["block"] == block]
    return {"modelVersion": DEFAULT_MODEL_VERSION, "fields": [field_payload(entry) for entry in entries]}


def validate_scenario_inputs(inputs: Mapping[str, Any]) -> JSONResponse | None:
    """按参数字典校验输入：拒绝公式字段、未知编号和超出枚举的值。"""
    catalog = load_parameter_catalog()
    for field_id, value in inputs.items():
        entry = catalog.get(field_id)
        if entry is None:
            return error_payload("UNKNOWN_FIELD", f"未知参数编号：{field_id}", field=field_id)
        if entry["sourceType"] == "公式自动":
            return error_payload(
                "FORMULA_FIELD_READ_ONLY",
                f"{field_id} {entry['name']} 是公式自动字段，不能在普通填写框修改",
                field=field_id,
            )
        expected_options = ENUM_PARAMETER_OPTIONS.get(field_id)
        if expected_options is not None and value is not None and value not in expected_options:
            return error_payload(
                "INVALID_FIELD_VALUE",
                f"{field_id} {entry['name']} 只能是 {'、'.join(expected_options)}，收到 {value!r}",
                field=field_id,
            )
    return None


@router.get("/projects")
def list_projects(request: Request) -> list[dict[str, Any]]:
    return repository_from_request(request).list_projects()


@router.post("/projects", status_code=201)
def create_project(
    payload: ProjectCreate, request: Request, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    repository = repository_from_request(request)
    project_data = payload.model_dump()
    project_data["cityId"] = str(payload.cityId or city_id_from_name(payload.city))
    project = repository.create_project(project_data)
    scenario = repository.create_scenario(
        project["id"], {"name": "基准", "inputs": baseline_inputs()}
    )
    project = repository.get_project(project["id"])
    job = CityOnboardingService(
        repository,
        discovery_provider=getattr(request.app.state, "discovery_provider", None),
        raw_dir=_raw_sources_dir(request),
        crawl_allow_private=_crawl_allow_private(request),
    ).start(project["id"])
    background_tasks.add_task(
        _run_city_onboarding,
        repository,
        job["id"],
        getattr(request.app.state, "discovery_provider", None),
        _raw_sources_dir(request),
        _crawl_allow_private(request),
    )
    # 继续保留旧的顶层项目字段，旧版客户端仍可读取 body.id；新客户端使用嵌套对象。
    return {**project, "project": project, "onboarding": job, "scenario": scenario}


def _run_city_onboarding(
    repository: ProjectRepository,
    job_id: str,
    discovery_provider: Any,
    raw_dir: Path,
    crawl_allow_private: bool,
) -> None:
    CityOnboardingService(
        repository,
        discovery_provider=discovery_provider,
        raw_dir=raw_dir,
        crawl_allow_private=crawl_allow_private,
    ).run(job_id)


@router.get("/projects/{project_id}/onboarding", response_model=None)
def get_city_onboarding(project_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
    try:
        repository.get_project(project_id)
        return CityOnboardingService(repository).get_status(project_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"城市入场任务不存在：{project_id}")


@router.post("/projects/{project_id}/onboarding/retry", response_model=None)
def retry_city_onboarding(project_id: str, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
    try:
        repository.get_project(project_id)
        job = CityOnboardingService(repository).retry_for_project(project_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"城市入场任务不存在：{project_id}")
    if job.get("status") in {"queued", "discovering", "sources_ready", "crawling", "extracting"}:
        background_tasks.add_task(
            _run_city_onboarding,
            repository,
            job["id"],
            getattr(request.app.state, "discovery_provider", None),
            _raw_sources_dir(request),
            _crawl_allow_private(request),
        )
    return job


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, Any]:
    try:
        return repository_from_request(request).get_project(project_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Project not found: {project_id}")


@router.delete("/projects/{project_id}", response_model=None)
def delete_project(project_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    """删除城市测算项目并级联清理场景数据；政策来源/抓取记录按城市保留（用户已确认）。"""
    try:
        repository_from_request(request).delete_project(project_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Project not found: {project_id}")
    return {"deleted": True, "projectId": project_id}


@router.post("/projects/{project_id}/scenarios", status_code=201)
def create_scenario(project_id: str, payload: ScenarioCreate, request: Request) -> dict[str, Any]:
    repository = repository_from_request(request)
    try:
        repository.get_project(project_id)
        inputs = baseline_inputs()
        provided = dict(payload.inputs or {})
        validation = validate_scenario_inputs(provided)
        if validation is not None:
            return validation
        inputs.update(provided)
        return repository.create_scenario(project_id, {"name": payload.name, "inputs": inputs})
    except KeyError:
        return error_payload("NOT_FOUND", f"Project not found: {project_id}")


@router.get("/projects/{project_id}/scenarios/{scenario_id}")
def get_scenario(project_id: str, scenario_id: str, request: Request) -> dict[str, Any]:
    try:
        return repository_from_request(request).get_scenario(project_id, scenario_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")


@router.get("/projects/{project_id}/scenarios/{scenario_id}/snapshots", response_model=None)
def list_scenario_snapshots(project_id: str, scenario_id: str, request: Request) -> list[dict[str, Any]] | JSONResponse:
    repository = repository_from_request(request)
    try:
        repository.get_scenario(project_id, scenario_id)
        return repository.list_snapshots(project_id, scenario_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")


@router.put("/projects/{project_id}/scenarios/{scenario_id}")
def update_scenario(project_id: str, scenario_id: str, payload: ScenarioUpdate, request: Request) -> dict[str, Any]:
    repository = repository_from_request(request)
    try:
        current = repository.get_scenario(project_id, scenario_id)
        data = payload.model_dump(exclude_none=True)
        if "inputs" in data:
            merged_inputs = dict(current["inputs"])
            incoming = dict(data["inputs"])
            validation = validate_scenario_inputs(incoming)
            if validation is not None:
                return validation
            merged_inputs.update(incoming)
            data["inputs"] = merged_inputs
            updated = repository.update_scenario(project_id, scenario_id, data)
            # 爬虫字段被直接手工填写时保留建议值，仅把值状态标记为 overridden（PRD 15.3）
            catalog = load_parameter_catalog()
            for field_id, value in incoming.items():
                entry = catalog.get(field_id)
                if entry is not None and entry["sourceType"] == "自动爬虫":
                    repository.mark_field_overridden(
                        scenario_id, field_id, current["inputs"].get(field_id), value
                    )
            return updated
        return repository.update_scenario(project_id, scenario_id, data)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")


def _field_value_view(
    entry: dict[str, Any],
    current_value: Any,
    row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_type = entry["sourceType"]
    if source_type == "公式自动":
        state = "formula"
    elif row is not None:
        state = row.get("valueState")
    elif source_type == "自动爬虫":
        state = "empty"
    else:
        state = "manual"
    return {
        "fieldId": entry["id"],
        "name": entry["name"],
        "unit": entry["unit"],
        "sourceType": source_type,
        "valueType": entry.get("valueType"),
        "block": entry["block"],
        "blockOrder": entry["blockOrder"],
        "readOnly": source_type == "公式自动",
        "currentValue": current_value,
        "suggestedValue": row.get("suggestedValue") if row else None,
        "suggestedSource": row.get("suggestedSource") if row else None,
        "suggestedAt": row.get("suggestedAt") if row else None,
        "valueState": state,
        "options": entry.get("options"),
    }


def _scenario_value_rows(repository: ProjectRepository, scenario_id: str) -> dict[str, dict[str, Any]]:
    return {row["fieldId"]: row for row in repository.list_field_values(scenario_id)}


def _scenario_fields_view(
    repository: ProjectRepository, project_id: str, scenario_id: str
) -> list[dict[str, Any]]:
    """按参数字典顺序构建一个场景的完整字段视图（当前值 + 建议值 + 状态）。"""
    scenario = repository.get_scenario(project_id, scenario_id)
    rows = _scenario_value_rows(repository, scenario_id)
    inputs = scenario.get("inputs") or {}
    catalog = load_parameter_catalog()
    return [_field_value_view(entry, inputs.get(entry["id"]), rows.get(entry["id"])) for entry in catalog.values()]


@router.get("/projects/{project_id}/scenarios/{scenario_id}/values", response_model=None)
def list_scenario_values(
    project_id: str, scenario_id: str, request: Request
) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
    try:
        fields = _scenario_fields_view(repository, project_id, scenario_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")
    return {"scenarioId": scenario_id, "fields": fields}


def _patch_field_value(
    repository: ProjectRepository, project_id: str, scenario_id: str, field_id: str, payload: FieldValueUpdate
) -> dict[str, Any] | JSONResponse:
    validation = validate_scenario_inputs({field_id: payload.value})
    if validation is not None:
        return validation
    catalog = load_parameter_catalog()
    entry = catalog[field_id]
    try:
        repository.set_field_value(project_id, scenario_id, field_id, payload.value)
        scenario = repository.get_scenario(project_id, scenario_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")
    rows = _scenario_value_rows(repository, scenario_id)
    return _field_value_view(entry, (scenario.get("inputs") or {}).get(field_id), rows.get(field_id))


def _accept_field_suggestion(
    repository: ProjectRepository, project_id: str, scenario_id: str, field_id: str
) -> dict[str, Any] | JSONResponse:
    catalog = load_parameter_catalog()
    entry = catalog.get(field_id)
    if entry is None:
        return error_payload("UNKNOWN_FIELD", f"未知参数编号：{field_id}", field=field_id)
    if entry["sourceType"] == "公式自动":
        return error_payload(
            "FORMULA_FIELD_READ_ONLY",
            f"{field_id} {entry['name']} 是公式自动字段，不能采用建议值",
            field=field_id,
        )
    try:
        repository.accept_field_suggestion(project_id, scenario_id, field_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")
    except ValueError:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "SUGGESTION_NOT_AVAILABLE",
                    "message": f"{field_id} 当前没有可采用的建议值",
                }
            },
        )
    scenario = repository.get_scenario(project_id, scenario_id)
    rows = _scenario_value_rows(repository, scenario_id)
    return _field_value_view(entry, (scenario.get("inputs") or {}).get(field_id), rows.get(field_id))


@router.patch("/projects/{project_id}/scenarios/{scenario_id}/values/{field_id}", response_model=None)
def patch_scenario_value(
    project_id: str, scenario_id: str, field_id: str, payload: FieldValueUpdate, request: Request
) -> dict[str, Any] | JSONResponse:
    return _patch_field_value(repository_from_request(request), project_id, scenario_id, field_id, payload)


@router.post(
    "/projects/{project_id}/scenarios/{scenario_id}/values/{field_id}/accept-suggestion",
    response_model=None,
)
def accept_field_suggestion(
    project_id: str, scenario_id: str, field_id: str, request: Request
) -> dict[str, Any] | JSONResponse:
    return _accept_field_suggestion(repository_from_request(request), project_id, scenario_id, field_id)


# ---------- 城市级字段值别名（PRD 16.6） ----------


def _resolve_city_scenario(repository: ProjectRepository, city_id: str) -> tuple[str, str]:
    """把城市标识解析到「主项目 + 主场景」。

    城市由 cityId 或 city（中文名）匹配，主场景取 updatedAt 最新者，与仪表盘聚合器保持一致。
    """
    projects = repository.list_projects()
    matches = [p for p in projects if p.get("cityId") == city_id or p.get("city") == city_id]
    if not matches:
        raise KeyError(city_id)
    project = matches[0]
    scenarios = project.get("scenarios") or []
    if not scenarios:
        raise KeyError(city_id)
    main_scenario = max(scenarios, key=lambda s: str(s.get("updatedAt") or ""))
    return str(project["id"]), str(main_scenario["id"])


@router.get("/cities/{city_id}/values", response_model=None)
def list_city_values(city_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
    try:
        project_id, scenario_id = _resolve_city_scenario(repository, city_id)
        fields = _scenario_fields_view(repository, project_id, scenario_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"City not found: {city_id}")
    return {"cityId": city_id, "scenarioId": scenario_id, "fields": fields}


@router.patch("/cities/{city_id}/values/{field_id}", response_model=None)
def patch_city_value(
    city_id: str, field_id: str, payload: FieldValueUpdate, request: Request
) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
    try:
        project_id, scenario_id = _resolve_city_scenario(repository, city_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"City not found: {city_id}")
    return _patch_field_value(repository, project_id, scenario_id, field_id, payload)


@router.post("/cities/{city_id}/values/{field_id}/accept-suggestion", response_model=None)
def accept_city_suggestion(city_id: str, field_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
    try:
        project_id, scenario_id = _resolve_city_scenario(repository, city_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"City not found: {city_id}")
    return _accept_field_suggestion(repository, project_id, scenario_id, field_id)


@router.post("/projects/{project_id}/scenarios/{scenario_id}/confirm", response_model=None)
def confirm_scenario(project_id: str, scenario_id: str, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return repository_from_request(request).confirm_scenario(project_id, scenario_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")
    except ValueError as error:
        return JSONResponse(status_code=409, content={"error": {"code": "SCENARIO_NOT_CONFIRMABLE", "message": str(error)}})


@router.post("/projects/{project_id}/scenarios/{scenario_id}/calculate")
def calculate_scenario(project_id: str, scenario_id: str, request: Request) -> Response:
    repository = repository_from_request(request)
    try:
        scenario = repository.get_scenario(project_id, scenario_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")

    try:
        result = calculate_u1(scenario["inputs"])
    except ValueError as error:
        # 输入本身不合法（如通勤时速为 0），返回 422 而不是 500。
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_INPUT", "message": str(error), "requestId": uuid.uuid4().hex}},
        )
    serialized = result_to_dict(result)
    repository.save_calculation(project_id, scenario_id, serialized)
    if result.status == "blocked":
        return JSONResponse(status_code=422, content=serialized)
    return JSONResponse(status_code=200, content=serialized)
