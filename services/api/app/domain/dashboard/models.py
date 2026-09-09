from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


DashboardDataStatus = Literal["ready", "stale", "missing", "failed"]
SnapshotStatus = Literal["calculated", "confirmed", "blocked", "stale"]


@dataclass(frozen=True)
class SnapshotSelection:
    snapshot: Mapping[str, Any] | None
    snapshot_id: str | None
    has_valid_result: bool
    is_excluded: bool
    reason: str | None = None


@dataclass(frozen=True)
class DashboardMetricSet:
    target_customers: float | int | None
    monthly_revenue: float | int | None
    monthly_net_profit: float | int | None
    initial_investment: float | int | None
    payback_month: float | int | None
    cumulative_net_profit: float | int | None
