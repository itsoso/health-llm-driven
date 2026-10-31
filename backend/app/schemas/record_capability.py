"""Typed payload contracts shared by Agent capabilities and record endpoints."""
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NasalWashValues(BaseModel):
    model_config = ConfigDict(extra='forbid')

    count: int = Field(strict=True, ge=1, le=20)
    volume_ml: float | None = Field(default=None, gt=0, le=5000, allow_inf_nan=False)
    solution: str | None = Field(default=None, max_length=80)

    @field_validator('volume_ml', mode='before')
    @classmethod
    def reject_boolean_volume(cls, value):
        if isinstance(value, bool):
            raise ValueError('volume_ml must be a numeric volume, not a boolean')
        return value


class NasalWashRecord(NasalWashValues):
    record_date: date


class NasalWashCreate(NasalWashRecord):
    event_id: str = Field(min_length=1, max_length=96, pattern=r'^[A-Za-z0-9_-]+$')
    type: Literal['wash', 'soak'] = 'wash'
    time: str | None = None

    @field_validator('time')
    @classmethod
    def normalize_time(cls, value):
        if value is None:
            return None
        if re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?', value) is None:
            raise ValueError('time must be HH:mm or HH:mm:ss')
        return value + ':00' if len(value) == 5 else value


class NasalWashEvent(NasalWashValues):
    event_id: str
    time: str
    type: Literal['wash', 'soak']


class NasalWashEventResponse(BaseModel):
    id: int
    user_id: int
    checkin_date: date
    event: NasalWashEvent
