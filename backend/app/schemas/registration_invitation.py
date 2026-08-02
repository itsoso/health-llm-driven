"""Admin API contracts for phone-bound registration invitations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RegistrationInvitationCreate(BaseModel):
    # Phone validation is route-local so FastAPI's default validation payload
    # cannot echo sensitive input back to the caller.
    phone: Any
    note: str | None = Field(default=None, max_length=200)
    expires_at: datetime | None = None


class RegistrationInvitationSafe(BaseModel):
    id: int
    phone_masked: str
    note: str | None
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    prepared_for_delivery: bool

    model_config = ConfigDict(from_attributes=True, frozen=True)


class RegistrationInvitationPrepared(RegistrationInvitationSafe):
    manual_code: str
    link_token: str
    deep_link: str


class RegistrationInvitationList(BaseModel):
    items: list[RegistrationInvitationSafe]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(frozen=True)
