"""DynamicView API surfaces composed by Aheng."""
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.today_dynamic_view_service import build_today_dynamic_view

router = APIRouter(prefix="/dynamic-views", tags=["dynamic-views"])


class TodayDynamicViewRequest(BaseModel):
    trigger: Literal["open", "resume", "pull_refresh", "action_completed"] = "open"
    surface: Literal["mobile.today"] = "mobile.today"
    client_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("client_context")
    @classmethod
    def _context_size_limit(cls, value: dict[str, Any]):
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > 4096:
            raise ValueError("client_context too large (max 4KB)")
        return value


@router.post("/today")
def post_today_dynamic_view(
    body: TodayDynamicViewRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return build_today_dynamic_view(
        db,
        current_user.id,
        trigger=body.trigger,
        client_context=body.client_context,
    )
