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


CAREGIVER_DAILY_SHIFT_HOURS = 10.0
"""护理员日工作总时段（小时）。不含通勤，作为 S3 计算的固定常量。

当前控制台没有承载该值的字段，业务方 2026-09-10 确认按经验值固定为 10 小时，
暂不进入可编辑参数表。
"""


def station_daily_caregiver_hours(values: Mapping[str, Any]) -> float:
    """护理员日工作时段 S3（控制台!E30）。

    公式：护理员日工作总时段 − 往返通勤小时
        = CAREGIVER_DAILY_SHIFT_HOURS − S1 / S2 * 2

    其中 `S1` 为站点覆盖半径（km）、`S2` 为区域平均通勤时速（km/h），
    `S1 / S2` 是单程通勤小时数，乘以 2 得到往返通勤小时数。

    基准输入（S1=3、S2=20）下往返通勤 0.3 小时，S3 = 9.7 小时。

    注：原实现误与 S5 共用「面积 × 人口密度 × 年龄段加权失能率」结构，
    算出 689.89（单位却是小时），量纲完全失配。业务方 2026-09-10 确认
    S3 应为通勤扣减模型，是 S3/S5 共用公式疑点（SHARED_FORMULA_STRUCTURE）
    的真正根因；S5 本身无误，保持原公式。
    """
    commute_speed = float(values["S2"])
    if commute_speed <= 0:
        # 通勤时速必须为正；0 或负数无业务含义，直接暴露为输入错误，
        # 不静默改成 0 或兜底值（见 AGENTS.md「不得把缺失数据变成 0」）。
        raise ValueError("区域平均通勤时速（S2）必须大于 0")
    round_trip_hours = float(values["S1"]) / commute_speed * 2
    return CAREGIVER_DAILY_SHIFT_HOURS - round_trip_hours


def station_coverage_disabled_limit(values: Mapping[str, Any]) -> float:
    """站点覆盖失能客户上限（控制台!E32）。

    末项使用 C8（80 岁以上失能率），与前两项的失能率量纲一致。

    原 Excel 该单元格最后一项写成 E12（区域人口密度），把「人/km²」当成
    「失能率」参与三年龄段加权，量纲失配导致结果虚高约 32 万倍
    （基准输入下 2.26 亿人，站点覆盖客户 1.13 亿，平台期月收入 2205 亿元）。
    业务方 2026-09-10 确认改为 C8。

    该公式结构仅适用于 S5（单位：人），不再与 S3 共用。
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
