from typing import Final


PREPARATION: Final = "筹备期"
STARTUP: Final = "启动期"
PLATFORM: Final = "平台期"


def stage_for_month(month: int, preparation_months: int, startup_months: int) -> str:
    if month <= 0:
        raise ValueError("Excel month numbers start at 1")
    if month <= preparation_months:
        return PREPARATION
    if month <= preparation_months + startup_months:
        return STARTUP
    return PLATFORM


def build_stage_sequence(preparation_months: int, startup_months: int, platform_months: int) -> tuple[str, ...]:
    if min(preparation_months, startup_months, platform_months) < 0:
        raise ValueError("Stage month counts cannot be negative")
    return tuple(
        [PREPARATION] * preparation_months
        + [STARTUP] * startup_months
        + [PLATFORM] * platform_months
    )
