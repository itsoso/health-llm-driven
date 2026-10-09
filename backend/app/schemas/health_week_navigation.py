from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict

class NavigationEventRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_type: Literal['completed','skipped','deferred']
    expected_revision: str
    operation_id: UUID

class NavigationAction(BaseModel):
    action_ref: str
    action_revision: str
    share_title: str
    share_completion_criterion: str
    execution_status: Literal['pending','completed','skipped','deferred','withdrawn','unknown']
    safety_state: Literal['allowed','restricted','unknown']
    requires_health_review: bool
    scheduling_mode: Literal['flexible','view_only']
    detail_ref: str

class NavigationReview(BaseModel):
    recorded_days: int
    window_days: int
    coverage_status: Literal['complete','partial','missing']
    completed_occurrences: int
    skipped_occurrences: int
    deferred_occurrences: int
    unknown_occurrences: int
    claim_boundary: str

class HealthWeekNavigation(BaseModel):
    schema_version: Literal['health_week_navigation.v1']
    local_date: date
    timezone: str
    timezone_source: str
    availability: Literal['ready','partial','not_generated','unavailable']
    projection_revision: str
    projection_sequence: int
    generated_at: datetime
    source_as_of: datetime | None
    expires_at: datetime
    review_window: dict
    actions: list[NavigationAction]
    review: NavigationReview
    restrictions: list[dict]

class NavigationActionDetail(BaseModel):
    action_ref: str
    action_revision: str
    title: str
    completion_criterion: str
    execution_status: Literal['pending','completed','skipped','deferred','withdrawn','unknown']
    safety_state: Literal['allowed','restricted','unknown']
    requires_health_review: bool
    scheduling_mode: Literal['view_only']
    plan_date: date
    action_key: str
    expires_at: datetime
    can_confirm: bool

class NavigationEventReceipt(BaseModel):
    action: NavigationActionDetail
    idempotent: bool
