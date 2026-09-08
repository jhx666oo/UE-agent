from dataclasses import dataclass
from typing import Any, Literal, Mapping


FormulaStatus = Literal["ok", "formula_error", "unavailable"]


@dataclass(frozen=True)
class FormulaValue:
    value: float | int | str | None
    status: FormulaStatus = "ok"
    error_code: str | None = None


@dataclass(frozen=True)
class ModelIssue:
    code: str
    excelCell: str
    severity: str
    status: str
    message: str


@dataclass(frozen=True)
class MonthlyProjection:
    month: int
    stage: str
    signed_customers: FormulaValue
    single_customer_month_revenue: FormulaValue
    long_term_care_revenue: FormulaValue
    auxiliary_revenue: FormulaValue
    total_revenue: FormulaValue
    caregivers: FormulaValue
    caregiver_cost: FormulaValue
    sales_cost: FormulaValue
    nurse_cost: FormulaValue
    variable_cost: FormulaValue
    fixed_cost: FormulaValue
    gross_profit: FormulaValue
    net_profit: FormulaValue
    gross_margin: FormulaValue
    net_margin: FormulaValue
    cumulative_net_profit: FormulaValue
    cumulative_cash_flow: FormulaValue
    cash_flow_positive_marker: FormulaValue
    cash_flow_positive_month: FormulaValue
    break_even_customers: FormulaValue


@dataclass(frozen=True)
class U1Result:
    model_version: str
    status: Literal["ok", "blocked"]
    parameters: Mapping[str, Any]
    months: tuple[MonthlyProjection, ...]
    stage_summary: Mapping[str, Mapping[str, Any]]
    headline_metrics: Mapping[str, FormulaValue]
    issues: tuple[ModelIssue, ...]
