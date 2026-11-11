"""北京时间日期 -> workday / holiday。

规则：holidays 表中 kind='workday' 表示调休补班（周末按工作日），
kind='holiday' 表示法定节假日（工作日按节假日）；未登记的日期按
周一至周五=工作日、周六周日=节假日处理。
"""
from datetime import date

from . import repos


def day_type(day: date, overrides: dict[date, str] | None = None) -> str:
    if overrides is not None and day in overrides:
        return overrides[day]
    overrides = {h["date"]: h["kind"] for h in repos.list_holidays()}
    kind = overrides.get(day)
    if kind == "workday":
        return "workday"
    if kind == "holiday":
        return "holiday"
    return "workday" if day.weekday() < 5 else "holiday"


def override_map() -> dict[date, str]:
    return {h["date"]: h["kind"] for h in repos.list_holidays()}
