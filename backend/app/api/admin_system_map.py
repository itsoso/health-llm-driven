"""Administrator-only access to the checked-in System Map artifact."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.admin import get_admin_user
from app.models.user import User


logger = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SYSTEM_MAP_PATH = REPOSITORY_ROOT / "docs" / "_generated" / "system-map.json"
SCRIPTS_PATH = REPOSITORY_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_PATH))

from system_map_contract import SystemMapContractError, validate_system_map  # noqa: E402


router = APIRouter()


def load_validated_system_map() -> dict:
    """Load the canonical artifact and fail closed when it is unavailable."""
    try:
        payload = json.loads(SYSTEM_MAP_PATH.read_text(encoding="utf-8"))
        validate_system_map(payload)
        return payload
    except (OSError, UnicodeError, json.JSONDecodeError, SystemMapContractError) as exc:
        logger.error(
            "System Map artifact unavailable: path=%s error_type=%s",
            SYSTEM_MAP_PATH,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="系统地图暂不可用",
        ) from None


@router.get("", summary="获取管理员系统地图")
async def get_system_map(admin: User = Depends(get_admin_user)) -> dict:
    return load_validated_system_map()
