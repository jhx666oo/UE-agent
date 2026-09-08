from __future__ import annotations

from dataclasses import fields, is_dataclass
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..domain.u1.engine import DEFAULT_MODEL_VERSION, calculate_u1
from ..domain.u1.issues import load_known_issues
from ..domain.u1.models import FormulaValue, ModelIssue, MonthlyProjection, U1Result
from ..domain.u1.spec import load_json_spec, load_parameter_catalog
from ..repository import JsonProjectRepository
from .schemas import ProjectCreate, ScenarioCreate, ScenarioUpdate


router = APIRouter()


def repository_from_request(request: Request) -> JsonProjectRepository:
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
