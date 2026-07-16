"""Remote Config and Admin release policy endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.app_release_policy import (
    PolicyValidationError,
    PolicyVersionConflict,
    get_release_policy,
    publish_release_policy,
    policy_to_public,
)

router = APIRouter(tags=["app-release-policy"])


class ReleasePolicyUpdate(BaseModel):
    platform: str = Field(min_length=1, max_length=32)
    channel: str = Field(min_length=1, max_length=64)
    expected_config_version: int = Field(ge=0)
    ota_enabled: StrictBool = True
    rollout_percent: int = Field(default=100, ge=0, le=100)
    minimum_native_build: Optional[str] = Field(default=None, max_length=32)
    recommended_native_build: Optional[str] = Field(default=None, max_length=32)
    forced_update: StrictBool = False
    kill_switches: dict[str, StrictBool] = Field(default_factory=dict)
    rollback_update_id: Optional[str] = Field(default=None, max_length=128)
    expires_at: Optional[datetime] = None


class ReleasePolicyResponse(BaseModel):
    config_version: int
    platform: str
    channel: str
    ota_enabled: bool
    rollout_percent: int
    minimum_native_build: Optional[str] = None
    recommended_native_build: Optional[str] = None
    forced_update: bool
    kill_switches: dict[str, bool]
    rollback_update_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    source: Literal["remote", "safe_default"]


@router.get(
    "/app-release-policy",
    response_model=ReleasePolicyResponse,
    summary="读取当前客户端发布策略",
)
def read_release_policy(
    platform: str = Query("ios", min_length=1, max_length=32),
    channel: str = Query("production", min_length=1, max_length=64),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return get_release_policy(db, platform=platform, channel=channel)


@router.get(
    "/admin/app-release-policy",
    response_model=ReleasePolicyResponse,
    summary="管理员读取发布策略",
)
def read_admin_release_policy(
    platform: str = Query("ios", min_length=1, max_length=32),
    channel: str = Query("production", min_length=1, max_length=64),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return get_release_policy(db, platform=platform, channel=channel)


@router.put(
    "/admin/app-release-policy",
    response_model=ReleasePolicyResponse,
    summary="管理员发布新的应用策略",
)
def update_release_policy(
    body: ReleasePolicyUpdate,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    try:
        policy = publish_release_policy(
            db,
            platform=body.platform,
            channel=body.channel,
            expected_config_version=body.expected_config_version,
            ota_enabled=body.ota_enabled,
            rollout_percent=body.rollout_percent,
            minimum_native_build=body.minimum_native_build,
            recommended_native_build=body.recommended_native_build,
            forced_update=body.forced_update,
            kill_switches=body.kill_switches,
            rollback_update_id=body.rollback_update_id,
            expires_at=body.expires_at,
            created_by_user_id=admin_user.id,
        )
    except PolicyVersionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PolicyValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return policy_to_public(policy)
