"""腰围记录 schema."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WaistRecordInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    record_date: date
    waist_cm: float = Field(..., gt=30, lt=200)
    source: Optional[str] = Field("manual", max_length=50)
    notes: Optional[str] = None


class WaistRecordUpdate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    record_date: Optional[date] = None
    waist_cm: Optional[float] = Field(None, gt=30, lt=200)
    source: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class WaistRecordResponse(BaseModel):
    id: int
    user_id: int
    record_date: date
    waist_cm: float
    source: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
