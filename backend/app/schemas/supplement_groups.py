"""Explicit manual supplement-group contracts; no dose or owner input."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class SupplementGroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    supplement_ids: list[StrictInt] = Field(min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("组合名称不能为空")
        return value.strip()

    @field_validator("supplement_ids")
    @classmethod
    def valid_ids(cls, value):
        if len(set(value)) != len(value) or any(i <= 0 for i in value):
            raise ValueError("补剂必须为不重复的有效编号")
        return value


class SupplementGroupUpdate(SupplementGroupCreate):
    revision: str = Field(min_length=1, max_length=64)


class SupplementGroupConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=1, max_length=64)
    record_date: date
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("必须明确确认已服")
        return value


class SupplementGroupMember(BaseModel):
    supplement_id: int
    name: str
    reference_dosage: str | None
    available: bool


class SupplementGroupSnapshotMember(BaseModel):
    supplement_id: int
    name: str
    reference_dosage: str | None
    record_id: int
    already_taken: bool


class SupplementGroupConfirmation(BaseModel):
    event_id: int
    group_id: int
    name: str
    revision: str
    record_date: date
    source: Literal["manual_group"]
    members: list[SupplementGroupSnapshotMember]


class SupplementGroupResponse(BaseModel):
    id: int
    name: str
    revision: str
    members: list[SupplementGroupMember]
    today_confirmation: SupplementGroupConfirmation | None


class SupplementGroupListResponse(BaseModel):
    record_date: date
    timezone: str
    groups: list[SupplementGroupResponse]


class SupplementGroupArchiveResponse(BaseModel):
    archived: Literal[True]
