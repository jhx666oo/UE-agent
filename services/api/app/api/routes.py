from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
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
from ..domain.policy.service import CrawlServiceError, PolicyService
from ..repository import ProjectRepository
from .schemas import (
    DataSourceCreate,
    DataSourceUpdate,
    FieldValueUpdate,
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


@router.post("/policies/sources", status_code=201)
def create_policy_source(payload: DataSourceCreate, request: Request) -> dict[str, Any]:
    return repository_from_request(request).create_data_source(payload.model_dump())


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
            content={"error": {"code": error.code, "message": error.message}},
        )


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
    "最近抓取时间", "最近HTTP状态", "最近变更", "备注",
]
_EXPORT_ARTIFACT_HEADER = [
    "抓取记录ID", "来源ID", "城市", "请求URL", "最终URL", "抓取时间", "HTTP状态",
    "内容类型", "字节数", "SHA256", "标题", "变更状态", "状态", "错误信息",
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
    if format not in ("csv", "json"):
        return error_payload("UNSUPPORTED_EXPORT_FORMAT", f"不支持的导出格式：{format}，可选 csv 或 json")
    if dataset not in ("fields", "sources", "artifacts"):
        return error_payload(
            "UNSUPPORTED_EXPORT_DATASET", f"不支持的导出内容：{dataset}，可选 fields、sources 或 artifacts"
        )

    repository = repository_from_request(request)
    sources, artifacts, field_rows = _collect_export_data(repository, cityId, sourceId)
    label = cityId or sourceId or scope

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
                    s.get("lastFetchedAt"), s.get("lastHttpStatus"), s.get("lastChangeStatus"), s.get("note"),
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
                    a.get("sha256"), a.get("title"), a.get("changeStatus"), a.get("status"), a.get("errorMessage"),
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


@router.get("/projects/{project_id}/scenarios/{scenario_id}/values", response_model=None)
def list_scenario_values(
    project_id: str, scenario_id: str, request: Request
) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
    try:
        scenario = repository.get_scenario(project_id, scenario_id)
    except KeyError:
        return error_payload("NOT_FOUND", f"Scenario not found: {scenario_id}")
    rows = _scenario_value_rows(repository, scenario_id)
    inputs = scenario.get("inputs") or {}
    catalog = load_parameter_catalog()
    fields = [
        _field_value_view(entry, inputs.get(entry["id"]), rows.get(entry["id"]))
        for entry in catalog.values()
    ]
    return {"scenarioId": scenario_id, "fields": fields}


@router.patch("/projects/{project_id}/scenarios/{scenario_id}/values/{field_id}", response_model=None)
def patch_scenario_value(
    project_id: str, scenario_id: str, field_id: str, payload: FieldValueUpdate, request: Request
) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
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


@router.post(
    "/projects/{project_id}/scenarios/{scenario_id}/values/{field_id}/accept-suggestion",
    response_model=None,
)
def accept_field_suggestion(
    project_id: str, scenario_id: str, field_id: str, request: Request
) -> dict[str, Any] | JSONResponse:
    repository = repository_from_request(request)
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
