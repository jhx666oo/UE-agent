from __future__ import annotations

from dataclasses import fields, is_dataclass
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from ..domain.u1.engine import DEFAULT_MODEL_VERSION, calculate_u1
from ..domain.u1.issues import load_known_issues
from ..domain.u1.models import FormulaValue, ModelIssue, MonthlyProjection, U1Result
from ..domain.u1.spec import load_json_spec, load_parameter_catalog
from ..domain.dashboard.aggregator import build_dashboard_overview
from ..domain.policy.service import PolicyService
from ..repository import ProjectRepository
from .schemas import (
    DataSourceCreate,
    DataSourceUpdate,
    PolicyParseRequest,
    PolicyReviewRequest,
    ProjectCreate,
    ScenarioCreate,
    ScenarioUpdate,
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


def error_payload(code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=404 if code == "NOT_FOUND" else 400, content={"error": {"code": code, "message": message}})


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
        return error_payload("INVALID_QUERY", "scope 必须是 global、city 或 compare")
    if period not in {12, 24}:
        return error_payload("INVALID_QUERY", "period 必须是 12 或 24")
    if scenario != "latest":
        return error_payload("INVALID_QUERY", "当前仅支持 scenario=latest")
    ids = [item.strip() for item in (city_ids or "").split(",") if item.strip()]
    if scope == "city" and len(ids) != 1:
        return error_payload("INVALID_QUERY", "city 视图需要一个 cityIds")
    if scope == "compare" and not ids:
        return error_payload("INVALID_QUERY", "compare 视图至少需要一个 cityIds")
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


@router.post("/policies/sources", status_code=201)
def create_policy_source(payload: DataSourceCreate, request: Request) -> dict[str, Any]:
    return repository_from_request(request).create_data_source(payload.model_dump())


@router.put("/policies/sources/{source_id}", response_model=None)
def update_policy_source(source_id: str, payload: DataSourceUpdate, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return repository_from_request(request).update_data_source(source_id, payload.model_dump(exclude_none=True))
    except KeyError:
        return error_payload("NOT_FOUND", f"Data source not found: {source_id}")


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


@router.post("/policies/documents/upload", status_code=201, response_model=None)
async def upload_policy_document(
    request: Request,
    cityId: str = Form(...),
    source: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any] | JSONResponse:
    try:
        content = await file.read()
        return PolicyService(repository_from_request(request)).upload_document(
            city_id=cityId,
            source=source,
            original_name=file.filename or "policy",
            mime_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except ValueError as error:
        return JSONResponse(status_code=400, content={"error": {"code": "INVALID_POLICY_FILE", "message": str(error)}})


@router.post("/policies/documents/{document_id}/parse", response_model=None)
def parse_policy_document(document_id: str, payload: PolicyParseRequest, request: Request) -> dict[str, Any] | JSONResponse:
    try:
        return PolicyService(repository_from_request(request)).parse_document(
            document_id,
            [candidate.model_dump() for candidate in payload.candidates],
        )
    except KeyError:
        return error_payload("NOT_FOUND", f"Policy document not found: {document_id}")
    except ValueError as error:
        return JSONResponse(status_code=409, content={"error": {"code": "POLICY_PARSE_ERROR", "message": str(error)}})


@router.post("/policies/documents/{document_id}/facts/{fact_id}/review", response_model=None)
def review_policy_fact(
    document_id: str,
    fact_id: str,
    payload: PolicyReviewRequest,
    request: Request,
) -> dict[str, Any] | JSONResponse:
    try:
        return PolicyService(repository_from_request(request)).review_fact(
            document_id,
            fact_id,
            decision=payload.decision,
            reviewer=payload.reviewer,
            source=payload.source,
            effective_date=payload.effectiveDate,
        )
    except KeyError:
        return error_payload("NOT_FOUND", f"Policy fact not found: {fact_id}")
    except ValueError as error:
        return JSONResponse(status_code=409, content={"error": {"code": "POLICY_REVIEW_ERROR", "message": str(error)}})


@router.get("/model/u1")
def model_u1() -> dict[str, Any]:
    catalog = load_parameter_catalog()
    return {
        "modelVersion": DEFAULT_MODEL_VERSION,
        "parameters": list(catalog.values()),
        "baselineInputs": baseline_inputs(),
        "issues": [_serialize(issue) for issue in load_known_issues()],
    }


@router.get("/projects")
def list_projects(request: Request) -> list[dict[str, Any]]:
    return repository_from_request(request).list_projects()


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate, request: Request) -> dict[str, Any]:
    return repository_from_request(request).create_project(payload.model_dump())


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, Any]:
    try:
        return repository_from_request(request).get_project(project_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Project not found: {project_id}")


@router.post("/projects/{project_id}/scenarios", status_code=201)
def create_scenario(project_id: str, payload: ScenarioCreate, request: Request) -> dict[str, Any]:
    repository = repository_from_request(request)
    try:
        repository.get_project(project_id)
        inputs = baseline_inputs()
        inputs.update(payload.inputs or {})
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
            merged_inputs.update(data["inputs"])
            data["inputs"] = merged_inputs
        return repository.update_scenario(project_id, scenario_id, data)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")


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

    result = calculate_u1(scenario["inputs"])
    serialized = result_to_dict(result)
    repository.save_calculation(project_id, scenario_id, serialized)
    if result.status == "blocked":
        return JSONResponse(status_code=422, content=serialized)
    return JSONResponse(status_code=200, content=serialized)
