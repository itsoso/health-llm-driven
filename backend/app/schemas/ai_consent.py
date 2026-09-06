"""Shared client/server disclosure contract; grants cannot target another user."""
from pydantic import BaseModel, ConfigDict, StrictBool


class AIConsentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: StrictBool
    policy_version: str


class AIRecipient(BaseModel):
    id: str
    name: str
    purpose: str


class AIConsentStatus(BaseModel):
    subject_id: int
    policy_version: str
    accepted: bool
    accepted_at: str | None
    recipients: list[AIRecipient]
    data_types: list[str]
    purpose: str
