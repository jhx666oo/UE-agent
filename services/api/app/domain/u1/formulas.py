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
    """站点覆盖失能客户上限（控制台!E32）。

    末项使用 C8（80 岁以上失能率），与 S3 的年龄段加权结构保持一致。

    原 Excel 该单元格最后一项写成 E12（区域人口密度），把「人/km²」当成
    「失能率」参与三年龄段加权，量纲失配导致结果虚高约 32 万倍
    （基准输入下 2.26 亿人，站点覆盖客户 1.13 亿，平台期月收入 2205 亿元）。
    业务方 2026-09-10 确认改为 C8。

    遗留疑点：改用 C8 后 S5 与 S3 数值相同（689.89），但两者单位不同
    （S5 为人、S3 为小时），字段语义是否应共用同一公式结构仍需业务方复核，
    见 docs/model/u1-known-issues.md。
    """
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


def initial_investment(values: Mapping[str, Any]) -> float:
    return float(values["B14"]) + float(values["B15"]) + (
        float(values["B6"]) * float(values["B7"])
        + float(values["B1"]) * float(values["P4"])
        + float(values["B8"])
        + float(values["B9"])
        + float(values["B10"])
        + float(values["B11"])
    ) * 3
