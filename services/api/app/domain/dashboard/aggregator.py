from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable, Mapping

from .models import DashboardDataStatus, DashboardMetricSet, SnapshotSelection

VALID_SNAPSHOT_STATUSES = {"calculated", "confirmed"}
SUPPORTED_PERIODS = {12, 24}


def _metric_value(value: Any) -> float | int | None:
    if isinstance(value, Mapping):
        if value.get("status") not in (None, "ok"):
            return None
        value = value.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _calculated_at(snapshot: Mapping[str, Any]) -> str:
    return str(snapshot.get("calculatedAt") or "")


def _city_id(project: Mapping[str, Any]) -> str:
    return str(project.get("cityId") or project.get("city") or "unknown-city")


def select_latest_valid_snapshot(city: Mapping[str, Any]) -> SnapshotSelection:
    snapshots = [item for item in city.get("snapshots", []) if isinstance(item, Mapping)]
    valid = [item for item in snapshots if item.get("status") in VALID_SNAPSHOT_STATUSES]
    if valid:
        selected = max(valid, key=_calculated_at)
        return SnapshotSelection(
            snapshot=selected,
            snapshot_id=str(selected.get("snapshotId")) if selected.get("snapshotId") is not None else None,
            has_valid_result=True,
            is_excluded=False,
        )
    if any(item.get("status") == "blocked" for item in snapshots):
        return SnapshotSelection(None, None, False, True, "blocked")
    if any(item.get("status") == "stale" for item in snapshots):
        return SnapshotSelection(None, None, False, False, "stale")
    return SnapshotSelection(None, None, False, False, "missing")


def _empty_metric_set() -> DashboardMetricSet:
    return DashboardMetricSet(None, None, None, None, None, None)


def _result_from_snapshot(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    result = snapshot.get("resultSnapshot")
    return result if isinstance(result, Mapping) else {}


def _metric_set(snapshot: Mapping[str, Any]) -> DashboardMetricSet:
    result = _result_from_snapshot(snapshot)
    headline = result.get("headlineMetrics") if isinstance(result.get("headlineMetrics"), Mapping) else {}
    months = result.get("months") if isinstance(result.get("months"), list) else []
    target_customers = None
    if months:
        target_customers = _metric_value(months[-1].get("signedCustomers")) if isinstance(months[-1], Mapping) else None
    return DashboardMetricSet(
        target_customers=target_customers,
        monthly_revenue=_metric_value(headline.get("platform_monthly_revenue")),
        monthly_net_profit=_metric_value(headline.get("platform_monthly_net_profit")),
        initial_investment=_metric_value(headline.get("initial_investment")),
        payback_month=_metric_value(headline.get("payback_month")),
        cumulative_net_profit=_metric_value(headline.get("twenty_four_month_cumulative_net_profit")),
    )


def _project_scenario(project: Mapping[str, Any], scenario_id: str | None) -> Mapping[str, Any] | None:
    scenarios = project.get("scenarios") if isinstance(project.get("scenarios"), list) else []
    if scenario_id is not None:
        return next((scenario for scenario in scenarios if scenario.get("id") == scenario_id), None)
    return max(scenarios, key=lambda scenario: str(scenario.get("updatedAt") or ""), default=None)


def _monthly_trend(snapshot: Mapping[str, Any], period: int) -> list[dict[str, Any]]:
    result = _result_from_snapshot(snapshot)
    months = result.get("months") if isinstance(result.get("months"), list) else []
    trend: list[dict[str, Any]] = []
    for item in months[:period]:
        if not isinstance(item, Mapping):
            continue
        trend.append(
            {
                "month": item.get("month"),
                "stage": item.get("stage"),
                "revenue": _metric_value(item.get("totalRevenue")),
                "netProfit": _metric_value(item.get("netProfit")),
                "cumulativeCashFlow": _metric_value(item.get("cumulativeCashFlow")),
            }
        )
    return trend


def _cost_breakdown(snapshot: Mapping[str, Any]) -> dict[str, float | int | None]:
    result = _result_from_snapshot(snapshot)
    months = result.get("months") if isinstance(result.get("months"), list) else []
    platform_month = next((item for item in reversed(months) if isinstance(item, Mapping) and item.get("stage") == "平台期"), None)
    if platform_month is None and months:
        platform_month = months[-1]
    if not isinstance(platform_month, Mapping):
        return {"caregiverCost": None, "salesCost": None, "nurseCost": None, "fixedCost": None}
    return {
        "caregiverCost": _metric_value(platform_month.get("caregiverCost")),
        "salesCost": _metric_value(platform_month.get("salesCost")),
        "nurseCost": _metric_value(platform_month.get("nurseCost")),
        "fixedCost": _metric_value(platform_month.get("fixedCost")),
    }


def _issue_count(snapshot: Mapping[str, Any]) -> int:
    result = _result_from_snapshot(snapshot)
    issues = result.get("issues")
    return len(issues) if isinstance(issues, list) else 0


def _data_completeness(project: Mapping[str, Any], snapshot: Mapping[str, Any] | None) -> int:
    if snapshot is None:
        return 0
    inputs = snapshot.get("inputSnapshot")
    if not isinstance(inputs, Mapping) or not inputs:
        return 0
    present = sum(value is not None for value in inputs.values())
    return round(present / len(inputs) * 100)


def _city_row(
    city_id: str,
    projects: list[Mapping[str, Any]],
    snapshots: list[Mapping[str, Any]],
    period: int,
    include_stale: bool,
) -> dict[str, Any]:
    city_name = str(projects[0].get("city") or city_id)
    district = next((project.get("district") for project in projects if project.get("district")), None)
    project_ids = {str(project.get("id")) for project in projects}
    city_snapshots = [snapshot for snapshot in snapshots if str(snapshot.get("projectId")) in project_ids]
    selection = select_latest_valid_snapshot({"cityId": city_id, "cityName": city_name, "snapshots": city_snapshots})
    selected_snapshot = selection.snapshot
    selected_project = next(
        (project for project in projects if selected_snapshot and str(project.get("id")) == str(selected_snapshot.get("projectId"))),
        projects[0],
    )
    scenario = _project_scenario(selected_project, str(selected_snapshot.get("scenarioId")) if selected_snapshot else None)
    stale = any(
        scenario_item.get("status") == "stale"
        for project in projects
        for scenario_item in (project.get("scenarios") if isinstance(project.get("scenarios"), list) else [])
    )
    failed = any(
        scenario_item.get("status") == "failed"
        for project in projects
        for scenario_item in (project.get("scenarios") if isinstance(project.get("scenarios"), list) else [])
    )
    usable = selected_snapshot is not None and (include_stale or not stale)
    metric_set = _metric_set(selected_snapshot) if usable and selected_snapshot else _empty_metric_set()
    data_status: DashboardDataStatus = "stale" if stale and selected_snapshot else "ready" if selected_snapshot else "failed" if failed else "missing"
    scenario_status = scenario.get("status") if scenario else ("stale" if stale else "draft")
    return {
        "cityId": city_id,
        "cityName": city_name,
        "district": district,
        "dataStatus": data_status,
        "hasValidResult": selection.has_valid_result,
        "stale": stale,
        "scenario": {
            "scenarioId": selected_snapshot.get("scenarioId") if selected_snapshot else scenario.get("id") if scenario else None,
            "name": scenario.get("name") if scenario else None,
            "status": scenario_status,
            "calculatedAt": selected_snapshot.get("calculatedAt") if selected_snapshot else None,
            "modelVersion": selected_snapshot.get("modelVersion") if selected_snapshot else None,
            "snapshotId": selection.snapshot_id,
        },
        "metrics": {
            "targetCustomers": metric_set.target_customers,
            "monthlyRevenue": metric_set.monthly_revenue,
            "monthlyNetProfit": metric_set.monthly_net_profit,
            "initialInvestment": metric_set.initial_investment,
            "paybackMonth": metric_set.payback_month,
            "cumulativeNetProfit": metric_set.cumulative_net_profit,
        },
        "monthlyTrend": _monthly_trend(selected_snapshot, period) if usable and selected_snapshot else [],
        "costBreakdown": _cost_breakdown(selected_snapshot) if usable and selected_snapshot else {"caregiverCost": None, "salesCost": None, "nurseCost": None, "fixedCost": None},
        "issueCount": _issue_count(selected_snapshot) if selected_snapshot else 0,
        "dataCompleteness": _data_completeness(selected_project, selected_snapshot) if usable else 0,
        "projectId": selected_project.get("id"),
        "projectIds": [project.get("id") for project in projects],
    }


def _sum_metric(rows: Iterable[Mapping[str, Any]], name: str) -> float | int | None:
    values = [row.get("metrics", {}).get(name) for row in rows if isinstance(row.get("metrics", {}).get(name), (int, float))]
    return sum(values) if values else None


def _aggregate_trend(rows: list[Mapping[str, Any]], period: int) -> list[dict[str, Any]]:
    by_month: dict[int, dict[str, Any]] = {}
    for row in rows:
        for point in row.get("monthlyTrend", []):
            if not isinstance(point, Mapping) or not isinstance(point.get("month"), int):
                continue
            month = int(point["month"])
            if month > period:
                continue
            current = by_month.setdefault(month, {"month": month, "stage": point.get("stage"), "revenue": [], "netProfit": [], "cumulativeCashFlow": []})
            for key in ("revenue", "netProfit", "cumulativeCashFlow"):
                if isinstance(point.get(key), (int, float)):
                    current[key].append(point[key])
    return [
        {
            "month": month,
            "stage": by_month[month].get("stage"),
            "revenue": sum(by_month[month]["revenue"]) if by_month[month]["revenue"] else None,
            "netProfit": sum(by_month[month]["netProfit"]) if by_month[month]["netProfit"] else None,
            "cumulativeCashFlow": sum(by_month[month]["cumulativeCashFlow"]) if by_month[month]["cumulativeCashFlow"] else None,
        }
        for month in sorted(by_month)
    ]


def _payback_distribution(values: list[float | int]) -> list[dict[str, Any]]:
    buckets = {"1-12个月": 0, "13-24个月": 0, "25个月以上": 0}
    for value in values:
        if value <= 12:
            buckets["1-12个月"] += 1
        elif value <= 24:
            buckets["13-24个月"] += 1
        else:
            buckets["25个月以上"] += 1
    return [{"range": label, "count": count} for label, count in buckets.items()]


def _alerts(rows: list[Mapping[str, Any]], policy_summary: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for row in rows:
        if row.get("stale"):
            alerts.append({"type": "stale", "severity": "warning", "cityId": row["cityId"], "cityName": row["cityName"], "message": "参数已修改，结果待重算", "href": f"/projects/{row.get('projectId')}"})
        elif not row.get("hasValidResult"):
            alerts.append({"type": "missing", "severity": "info", "cityId": row["cityId"], "cityName": row["cityName"], "message": "暂无有效测算结果", "href": f"/projects/{row.get('projectId')}"})
        if row.get("issueCount", 0) > 0:
            alerts.append({"type": "issue", "severity": "warning", "cityId": row["cityId"], "cityName": row["cityName"], "message": f"有 {row['issueCount']} 个待确认问题", "href": f"/projects/{row.get('projectId')}"})
    if policy_summary:
        alerts.extend(policy_summary.get("alerts", []))
    return alerts


def build_dashboard_overview(
    projects: list[Mapping[str, Any]],
    snapshots: list[Mapping[str, Any]],
    *,
    scope: str = "global",
    city_ids: list[str] | None = None,
    period: int = 12,
    include_stale: bool = True,
    policy_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if period not in SUPPORTED_PERIODS:
        raise ValueError("period must be 12 or 24")
    if scope not in {"global", "city", "compare"}:
        raise ValueError("scope must be global, city, or compare")
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for project in projects:
        groups[_city_id(project)].append(project)
    selected_city_ids = city_ids or []
    if scope == "city" and len(selected_city_ids) != 1:
        raise ValueError("city scope requires exactly one cityId")
    if scope == "compare" and len(selected_city_ids) < 1:
        raise ValueError("compare scope requires at least one cityId")
    if selected_city_ids:
        groups = {city_id: groups[city_id] for city_id in selected_city_ids if city_id in groups}
    rows = [_city_row(city_id, city_projects, snapshots, period, include_stale) for city_id, city_projects in groups.items()]
    eligible_rows = [row for row in rows if row.get("hasValidResult") and (include_stale or not row.get("stale"))]
    payback_values = [row["metrics"]["paybackMonth"] for row in eligible_rows if isinstance(row["metrics"].get("paybackMonth"), (int, float))]
    summary = {
        "eligibleCityCount": len(eligible_rows),
        "totalCityCount": len(rows),
        "targetCustomers": _sum_metric(eligible_rows, "targetCustomers"),
        "monthlyRevenue": _sum_metric(eligible_rows, "monthlyRevenue"),
        "monthlyNetProfit": _sum_metric(eligible_rows, "monthlyNetProfit"),
        "initialInvestment": _sum_metric(eligible_rows, "initialInvestment"),
        "cumulativeNetProfit": _sum_metric(eligible_rows, "cumulativeNetProfit"),
        "paybackMedian": median(payback_values) if payback_values else None,
        "paybackDistribution": _payback_distribution(payback_values),
        "pendingIssueCount": sum(int(row.get("issueCount", 0)) for row in rows),
    }
    return {
        "scope": scope,
        "period": period,
        "scenarioRule": "latest",
        "includeStale": include_stale,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "cities": rows,
        "trend": _aggregate_trend(eligible_rows, period),
        "alerts": _alerts(rows, policy_summary),
        "policySummary": dict(policy_summary or {"pendingReviewCount": 0, "cities": [], "alerts": []}),
    }
