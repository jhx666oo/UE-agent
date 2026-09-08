import math
from collections.abc import Mapping
from typing import Any

from .models import FormulaValue


def formula_value(value: float | int | str | None, *, error_code: str | None = None) -> FormulaValue:
    if error_code is not None:
        return FormulaValue(value=None, status="formula_error", error_code=error_code)
    return FormulaValue(value=value)


def safe_ratio(numerator: float, denominator: float) -> FormulaValue:
    if denominator == 0:
        return formula_value(None, error_code="DIV0")
    return formula_value(numerator / denominator)


def ceil_excel(value: float, significance: float = 1.0) -> int:
    if significance <= 0:
        raise ValueError("Excel CEILING significance must be positive for this model")
    return math.ceil(value / significance) * int(significance)


def population_density(values: Mapping[str, Any]) -> float:
    return float(values["C3"]) * 10000 / float(values["C13"])


def personal_payment_ratio(values: Mapping[str, Any]) -> float:
    return 1 - float(values["P2"])


def station_daily_caregiver_hours(values: Mapping[str, Any]) -> float:
    return (
        math.pi
        * float(values["S1"]) ** 2
        * float(values["C9"])
        * float(values["C4"])
        * (
            float(values["C6"]) * 0.6
            + float(values["C7"]) * 0.3
            + float(values["C8"]) * 0.1
        )
    )


def station_coverage_disabled_limit(values: Mapping[str, Any]) -> float:
    # Deliberately preserves 控制台!E32's final E12 reference.
    return (
        math.pi
        * float(values["S1"]) ** 2
        * float(values["C9"])
        * float(values["C4"])
        * (
            float(values["C6"]) * 0.6
            + float(values["C7"]) * 0.3
            + float(values["C9"]) * 0.1
        )
    )


def initial_investment(values: Mapping[str, Any]) -> float:
    return float(values["B14"]) + float(values["B15"]) + (
        float(values["B6"]) * float(values["B7"])
        + float(values["B1"]) * float(values["P4"])
        + float(values["B8"])
        + float(values["B9"])
        + float(values["B10"])
        + float(values["B11"])
    ) * 3
