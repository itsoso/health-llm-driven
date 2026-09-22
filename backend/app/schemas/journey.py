"""Strict journey API and explicit private/export projections."""
import re
import unicodedata
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

JourneyKind = Literal["diet", "life_event", "chat_photo"]


def validated_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("请选择有效时区") from None
    if len(value) > 64:
        raise ValueError("请选择有效时区")
    return value


def month_dates(value: str) -> tuple[date, date]:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("月份格式应为 YYYY-MM")
    year, month = map(int, value.split("-"))
    if not 1900 <= year <= 9998:
        raise ValueError("月份超出支持范围")
    return date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JourneyWrite(StrictModel):
    city: str = Field(min_length=1, max_length=80)
    local_date: date
    timezone: str
    location_source: Literal["manual", "device"]
    expected_version: StrictInt = Field(ge=0)
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("请明确确认日期和城市")
        return value

    @field_validator("city")
    @classmethod
    def clean_city(cls, value):
        if any(unicodedata.category(c).startswith("C") for c in value) or any(c in value for c in "<>"):
            raise ValueError("城市名称包含无效字符")
        value = value.strip()
        if not value:
            raise ValueError("请填写城市")
        return value

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        return validated_timezone(value)

    @field_validator("local_date", mode="before")
    @classmethod
    def date_only(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("日期格式应为 YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def device_today(self):
        if self.location_source == "device" and self.local_date != datetime.now(ZoneInfo(self.timezone)).date():
            raise ValueError("历史日期只能手动填写城市")
        return self


class JourneyImage(StrictModel):
    key: str
    url: str


class JourneyPlaceBase(StrictModel):
    id: int
    kind: JourneyKind
    source_id: int
    city: str
    local_date: date
    timezone: str
    location_source: Literal["manual", "device"]
    version: int


class JourneyPlaceResponse(JourneyPlaceBase):
    title: str
    images: list[JourneyImage]
    image_status: Literal["ready", "unavailable", "none"]


class JourneySource(StrictModel):
    kind: JourneyKind
    source_id: int
    title: str
    suggested_date: date
    date_basis: Literal["record", "message"]
    images: list[JourneyImage]
    image_status: Literal["ready", "unavailable", "none"]
    place: JourneyPlaceBase | None


class JourneySourcesResponse(StrictModel):
    items: list[JourneySource]
    total: int
    offset: int
    limit: int


class JourneyMonthResponse(StrictModel):
    month: str
    items: list[JourneyPlaceResponse]
    total: int
    offset: int
    limit: int


class JourneyExportSelection(StrictModel):
    place_id: StrictInt = Field(gt=0)
    version: StrictInt = Field(gt=0)
    image_keys: list[str] = Field(max_length=30)

    @field_validator("image_keys")
    @classmethod
    def unique_keys(cls, values):
        if len(values) != len(set(values)) or any(not re.fullmatch(r"[a-f0-9]{64}", x) for x in values):
            raise ValueError("照片选择无效")
        return values


class JourneyExportRequest(StrictModel):
    items: list[JourneyExportSelection] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_places(self):
        if len({item.place_id for item in self.items}) != len(self.items):
            raise ValueError("不能重复选择片段")
        return self


class JourneyExportItem(StrictModel):
    city: str
    local_date: date
    kind: JourneyKind
    images: list[JourneyImage]


class JourneyExportResponse(StrictModel):
    month: str
    items: list[JourneyExportItem]
