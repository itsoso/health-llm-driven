"""Ephemeral location lookup contract; no record or profile mutation."""
from datetime import datetime, timezone
from typing import Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr, field_validator


class LookupConsent(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    consent: Literal["amap-share-location-v1"]


class NearbyRequest(LookupConsent):
    latitude: StrictFloat = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: StrictFloat = Field(ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: StrictFloat = Field(gt=0, le=200, allow_inf_nan=False)
    captured_at: datetime

    @field_validator("captured_at", mode="before")
    @classmethod
    def iso_timestamp(cls, value):
        if not isinstance(value, str) or len(value) > 40 or "T" not in value:
            raise ValueError("定位时间无效")
        return value

    @field_validator("captured_at")
    @classmethod
    def fresh(cls, value):
        if value.tzinfo is None:
            raise ValueError("定位时间无效")
        age = (datetime.now(timezone.utc) - value).total_seconds()
        if not -10 <= age <= 120:
            raise ValueError("请重新定位")
        return value


class SearchRequest(LookupConsent):
    keyword: StrictStr = Field(min_length=1, max_length=80)
    city: StrictStr | None = Field(default=None, min_length=1, max_length=40)

    @field_validator("keyword", "city")
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return None
        if not value.strip() or any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("请输入有效地点")
        return value.strip()


class LocationItem(BaseModel):
    id: str = Field(max_length=100)
    name: str = Field(max_length=120)
    address: str = Field(max_length=240)
    label: str = Field(max_length=40)
    distance_m: float | None = None


class LocationAvailability(BaseModel):
    enabled: bool


class LocationResults(BaseModel):
    items: list[LocationItem] = Field(max_length=10)
    suggested_id: str | None = None
