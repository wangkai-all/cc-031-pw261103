"""Pydantic 请求/响应模型。时间一律使用北京时间 naive 字符串。"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

FLAG_VALUES = {"normal", "reset", "replacement"}
DAY_TYPES = {"workday", "holiday"}


class MeterIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


class ReadingIn(BaseModel):
    read_at: datetime
    reading_kwh: Decimal
    flag: str = "normal"
    note: str = ""

    @field_validator("flag")
    @classmethod
    def _flag(cls, v: str) -> str:
        if v not in FLAG_VALUES:
            raise ValueError(f"flag 必须是 {sorted(FLAG_VALUES)}")
        return v


class PeriodIn(BaseModel):
    label: str = Field(min_length=1, max_length=16)
    start_min: int = Field(ge=0, le=1439)
    end_min: int = Field(ge=1, le=1440)
    price_yuan: Decimal


class TariffIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    effective_date: date
    day_type: str
    note: str = ""
    periods: list[PeriodIn]

    @field_validator("day_type")
    @classmethod
    def _day(cls, v: str) -> str:
        if v not in DAY_TYPES:
            raise ValueError(f"day_type 必须是 {sorted(DAY_TYPES)}")
        return v


class HolidayIn(BaseModel):
    date: date
    name: str = ""
    kind: str = "holiday"

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in {"holiday", "workday"}:
            raise ValueError("kind 必须是 holiday 或 workday")
        return v
