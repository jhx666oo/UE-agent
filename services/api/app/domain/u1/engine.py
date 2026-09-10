from collections.abc import Mapping
from typing import Any

from .formulas import (
    ceil_excel,
    formula_value,
    initial_investment,
    personal_payment_ratio,
    population_density,
    safe_ratio,
    station_coverage_disabled_limit,
    station_daily_caregiver_hours,
)
from .issues import load_known_issues, missing_input_issue
from .models import FormulaValue, MonthlyProjection, U1Result
from .stages import PLATFORM, PREPARATION, STARTUP, build_stage_sequence


DEFAULT_MODEL_VERSION = "u1-excel-v2.1-parity"

# B12（GR公关月均费用）在原 Excel 控制台中为固定常量 5000，不由用户填写。
# 这里作为唯一事实来源：参数缺省时用该值，而不是把缺失数据当 0。
DEFAULT_GOVERNMENT_RELATIONS_COST = 5000.0

DEFAULT_PARAMETER_VALUES: Mapping[str, Any] = {
    "B12": DEFAULT_GOVERNMENT_RELATIONS_COST,
}

REQUIRED_DRIVERS = (
    "C3",
    "C4",
    "C6",
    "C7",
    "C8",
    "C13",
    "P1",
    "P2",
    "P4",
    "P5",
    "P8",
    "S1",
    "S4",
    "S6",
    "S7",
    "S8",
    "B1",
    "B2",
    "B3",
    "B4",
    "B5",
    "B6",
    "B7",
    "B8",
    "B9",
    "B10",
    "B11",
    "B13",
    "B14",
    "B15",
    "D1",
    "D2",
    "D3",
    "E1",
    "E3",
    "E5",
    "E6",
    "A1",
    "A2",
    "A3",
    "A4",
    "A5",
)


def _number(value: float | int) -> FormulaValue:
    return formula_value(float(value))


def _blocked_result(values: Mapping[str, Any], model_version: str, missing: list[str]) -> U1Result:
    issues = load_known_issues() + tuple(missing_input_issue(parameter_id) for parameter_id in missing)
    return U1Result(
        model_version=model_version,
        status="blocked",
        parameters=dict(values),
        months=(),
        stage_summary={},
        headline_metrics={},
        issues=issues,
    )


def _calculate_month(
    month: int,
    stage: str,
    values: Mapping[str, Any],
    previous_customers: float,
    previous_cumulative_net: float,
    previous_cumulative_cash: float,
    derived: Mapping[str, float],
) -> MonthlyProjection:
    s5 = derived["S5"]
    s3 = derived["S3"]

    if stage == PREPARATION:
        customers = 0.0
        single_revenue = 0.0
    elif stage == STARTUP:
        target_customers = s5 * float(values["S8"])
        customers = min(
            target_customers * (month - int(values["D1"])) / float(values["D2"]),
            target_customers,
        )
        single_revenue = float(values["P1"]) * float(values["P8"]) * float(values["S4"])
    else:
        customers = s5 * float(values["S8"])
        single_revenue = float(values["P1"]) * float(values["P8"]) * float(values["S4"])

    long_term_care_revenue = customers * single_revenue
    fund_payment = long_term_care_revenue * float(values["P2"])
    personal_payment = long_term_care_revenue * derived["P3"]

    if stage == PREPARATION:
        auxiliary_revenue = 0.0
    elif stage == STARTUP:
        auxiliary_revenue = float(values["A2"]) + float(values["A5"])
    else:
        auxiliary_revenue = (
            float(values["A1"])
            + float(values["A2"])
            + float(values["A3"]) * float(values["A4"]) * float(values["E6"])
            + float(values["A5"])
        )

    total_revenue = long_term_care_revenue + auxiliary_revenue

    if stage == PREPARATION:
        caregivers = float(values["P4"])
    else:
        caregivers = max(
            float(values["P4"]),
            float(ceil_excel(customers * float(values["P8"]) / s3 / float(values["S4"]) / float(values["E1"]))),
        )
    caregiver_cost = caregivers * float(values["B1"]) * float(values["B2"])

    if stage == PREPARATION:
        sales_cost = 0.0
    elif stage == STARTUP:
        sales_cost = max(0.0, customers - previous_customers) * float(values["E5"])
    else:
        sales_cost = max(0.0, customers * float(values["E3"])) * float(values["E5"]) * 0.5

    if values["B3"] == "挂证":
        nurse_cost = float(values["B4"]) * float(values["P5"])
    elif values["B3"] == "全职":
        nurse_cost = float(values["B5"]) * float(values["P5"])
    else:
        nurse_cost = 0.0

    variable_cost = caregiver_cost + nurse_cost if stage == PREPARATION else caregiver_cost + sales_cost + nurse_cost

    management_cost = float(values["B6"]) * float(values["B7"])
    rent_cost = float(values["S7"]) * float(values["S6"])
    system_cost = float(values["B8"])
    training_cost = float(values["B9"])
    water_cost = float(values["B10"])
    office_cost = float(values["B11"])
    if stage == PREPARATION:
        government_relations_cost = float(values["B12"])
    elif stage == STARTUP:
        government_relations_cost = float(values["B12"]) * 0.3
    else:
        government_relations_cost = 0.0
    compliance_cost = float(values["B13"])
    material_amortization = float(values["B15"]) / 24
    renovation_amortization = float(values["B14"]) / 24
    fixed_cost = sum(
        (
            management_cost,
            rent_cost,
            system_cost,
            training_cost,
            water_cost,
            office_cost,
            government_relations_cost,
            compliance_cost,
            material_amortization,
            renovation_amortization,
        )
    )

    gross_profit = 0.0 if stage == PREPARATION else total_revenue - variable_cost
    net_profit = gross_profit - fixed_cost
    gross_margin = 0.0 if stage == PREPARATION else (gross_profit / total_revenue if total_revenue != 0 else 0.0)
    net_margin = 0.0 if stage == PREPARATION else (net_profit / total_revenue if total_revenue != 0 else 0.0)
    cumulative_net = previous_cumulative_net + net_profit
    if month == 1:
        cumulative_cash = net_profit + material_amortization + renovation_amortization - derived["B16"]
    else:
        cumulative_cash = previous_cumulative_cash + net_profit + material_amortization + renovation_amortization
    cash_marker = 1 if cumulative_cash >= 0 and cumulative_cash != 0 else 0
    positive_month = month if cash_marker == 1 else None

    contribution_per_customer = (
        float(values["P1"]) * float(values["P8"]) * float(values["S4"])
        - float(values["B1"]) * float(values["B2"]) * float(values["P8"]) / s3 / float(values["S4"]) / float(values["E1"])
    )
    if stage == PLATFORM:
        break_even = ceil_excel(fixed_cost / contribution_per_customer, 1.0)
    else:
        break_even = None

    return MonthlyProjection(
        month=month,
        stage=stage,
        signed_customers=_number(customers),
        single_customer_month_revenue=_number(single_revenue),
        long_term_care_revenue=_number(long_term_care_revenue),
        auxiliary_revenue=_number(auxiliary_revenue),
        total_revenue=_number(total_revenue),
        caregivers=_number(caregivers),
        caregiver_cost=_number(caregiver_cost),
        sales_cost=_number(sales_cost),
        nurse_cost=_number(nurse_cost),
        variable_cost=_number(variable_cost),
        fixed_cost=_number(fixed_cost),
        gross_profit=_number(gross_profit),
        net_profit=_number(net_profit),
        gross_margin=_number(gross_margin),
        net_margin=_number(net_margin),
        cumulative_net_profit=_number(cumulative_net),
        cumulative_cash_flow=_number(cumulative_cash),
        cash_flow_positive_marker=_number(cash_marker),
        cash_flow_positive_month=formula_value(positive_month),
        break_even_customers=formula_value(break_even),
    )


def _stage_summary(months: tuple[MonthlyProjection, ...]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    cash_deltas: dict[int, float] = {}
    previous_cash = 0.0
    for index, month in enumerate(months):
        current_cash = float(month.cumulative_cash_flow.value)
        cash_deltas[month.month] = current_cash - (previous_cash if index else 0.0)
        previous_cash = current_cash
    for stage in (PREPARATION, STARTUP, PLATFORM):
        selected = [month for month in months if month.stage == stage]
        total_revenue = sum(float(month.total_revenue.value) for month in selected)
        total_variable = sum(float(month.variable_cost.value) for month in selected)
        total_fixed = sum(float(month.fixed_cost.value) for month in selected)
        total_net = sum(float(month.net_profit.value) for month in selected)
        total_cash_flow = sum(cash_deltas[month.month] for month in selected)
        summary[stage] = {
            "month_count": len(selected),
            "total_revenue": total_revenue,
            "total_variable_cost": total_variable,
            "total_fixed_cost": total_fixed,
            "total_net_profit": total_net,
            "total_cash_flow": total_cash_flow,
            "average_revenue": total_revenue / len(selected) if selected else 0,
            "average_net_profit": total_net / len(selected) if selected else 0,
            "net_margin": safe_ratio(total_net, total_revenue),
        }
    return summary


def calculate_u1(values: Mapping[str, Any], model_version: str = DEFAULT_MODEL_VERSION) -> U1Result:
    missing = [parameter_id for parameter_id in REQUIRED_DRIVERS if values.get(parameter_id) is None]
    if missing:
        return _blocked_result(values, model_version, missing)

    resolved = dict(values)
    # 常量参数（如 B12）先用默认值补齐，用户显式提供的值优先。
    for parameter_id, default_value in DEFAULT_PARAMETER_VALUES.items():
        if resolved.get(parameter_id) is None:
            resolved[parameter_id] = default_value
    derived = {
        "C9": population_density(resolved),
        "P3": personal_payment_ratio(resolved),
        "S3": station_daily_caregiver_hours({**resolved, "C9": population_density(resolved)}),
        "S5": station_coverage_disabled_limit({**resolved, "C9": population_density(resolved)}),
        "B16": initial_investment(resolved),
    }
    resolved.update(derived)

    stages = build_stage_sequence(int(resolved["D1"]), int(resolved["D2"]), int(resolved["D3"]))
    months: list[MonthlyProjection] = []
    previous_customers = 0.0
    previous_cumulative_net = 0.0
    previous_cumulative_cash = 0.0
    for month_number, stage in enumerate(stages, start=1):
        month = _calculate_month(
            month_number,
            stage,
            resolved,
            previous_customers,
            previous_cumulative_net,
            previous_cumulative_cash,
            derived,
        )
        months.append(month)
        previous_customers = float(month.signed_customers.value)
        previous_cumulative_net = float(month.cumulative_net_profit.value)
        previous_cumulative_cash = float(month.cumulative_cash_flow.value)

    month_tuple = tuple(months)
    stage_summary = _stage_summary(month_tuple)
    payback_months = [month.cash_flow_positive_month.value for month in month_tuple if month.cash_flow_positive_month.value is not None]
    break_even_values = [month.break_even_customers.value for month in month_tuple if month.break_even_customers.value is not None]
    platform = stage_summary[PLATFORM]

    # 启动期阶段切片：核心指标卡需要独立于全周期的启动期口径。
    startup_months = [month for month in month_tuple if month.stage == STARTUP]
    # 启动期累计最大亏损：Excel 指标卡“启动期现金流最差时的窟窿”。
    # 口径为筹备期 + 启动期的累计现金流最低点（投入期尚未产生收入，最低点即最大窟窿），
    # 与全阶段 max_cash_deficit 在正常参数下应一致；分阶段取值可避免平台期转正后掩盖该值。
    startup_phase_months = [
        month for month in month_tuple if month.stage in (PREPARATION, STARTUP)
    ]
    startup_max_cash_deficit = (
        min(float(month.cumulative_cash_flow.value) for month in startup_phase_months)
        if startup_phase_months
        else None
    )
    # 启动期总亏损：启动期内净利润的累计值（Excel 指标卡“爬坡期累计亏掉的钱”）。
    startup_total_loss = (
        sum(float(month.net_profit.value) for month in startup_months) if startup_months else None
    )
    # 盈亏平衡月份：累计净利润首次转正的月份（与 payback_month 的现金流口径区分）。
    net_positive_months = [
        month.month for month in month_tuple if float(month.cumulative_net_profit.value) > 0
    ]

    headline_metrics = {
        "payback_month": formula_value(max(payback_months) if payback_months else None),
        "max_cash_deficit": formula_value(min(float(month.cumulative_cash_flow.value) for month in month_tuple)),
        "startup_max_cash_deficit": formula_value(startup_max_cash_deficit),
        "platform_monthly_net_profit": formula_value(platform["average_net_profit"]),
        "platform_net_margin": platform["net_margin"],
        "twenty_four_month_cumulative_net_profit": formula_value(
            sum(float(month.cumulative_net_profit.value) for month in month_tuple)
        ),
        "net_break_even_month": formula_value(min(net_positive_months) if net_positive_months else None),
        "break_even_customers": formula_value(max(break_even_values) if break_even_values else None),
        "initial_investment": formula_value(derived["B16"]),
        "startup_total_loss": formula_value(startup_total_loss),
        "platform_monthly_revenue": formula_value(platform["average_revenue"]),
    }

    return U1Result(
        model_version=model_version,
        status="ok",
        parameters=resolved,
        months=month_tuple,
        stage_summary=stage_summary,
        headline_metrics=headline_metrics,
        issues=load_known_issues(),
    )
