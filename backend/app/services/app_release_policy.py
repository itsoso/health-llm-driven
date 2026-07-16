"""Remote Config release policy service.

The policy is intentionally limited to application delivery controls. It is
not a remote medical-rule or medication-management configuration surface.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Optional

from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_audit_log import AgentAuditLog
from app.models.app_release_policy import AppReleasePolicy


_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")
_FORBIDDEN_KILL_SWITCH_PARTS = frozenset({
    "diagnosis",
    "disease",
    "dose",
    "drug",
    "medical",
    "medication",
    "prescription",
    "safety",
    "symptom",
    "threshold",
    "clinical",
    "red_line",
})


class PolicyVersionConflict(ValueError):
    """Raised when an admin writes against an old policy version."""


class PolicyValidationError(ValueError):
    """Raised when a release policy violates its safety contract."""


def _now_utc(value: Optional[datetime] = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _validate_scope(platform: str, channel: str) -> tuple[str, str]:
    platform = platform.strip().lower()
    channel = channel.strip().lower()
    if not _TOKEN.fullmatch(platform) or not _TOKEN.fullmatch(channel):
        raise PolicyValidationError("platform/channel 格式不合法")
    return platform, channel


def _validate_kill_switches(value: Optional[dict[str, Any]]) -> dict[str, bool]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PolicyValidationError("kill_switches 必须是对象")
    result: dict[str, bool] = {}
    for key, enabled in value.items():
        if not isinstance(key, str) or not _TOKEN.fullmatch(key):
            raise PolicyValidationError("kill_switch 名称不合法")
        parts = {part for part in re.split(r"[._:-]+", key) if part}
        if parts & _FORBIDDEN_KILL_SWITCH_PARTS:
            raise PolicyValidationError("Remote Config 不允许控制医疗安全规则")
        if type(enabled) is not bool:
            raise PolicyValidationError("kill_switch 值必须是布尔值")
        result[key] = enabled
    return result


def validate_policy_input(
    *,
    platform: str,
    channel: str,
    rollout_percent: int,
    minimum_native_build: Optional[str],
    recommended_native_build: Optional[str],
    kill_switches: Optional[dict[str, Any]],
) -> tuple[str, str, dict[str, bool]]:
    platform, channel = _validate_scope(platform, channel)
    if not 0 <= rollout_percent <= 100:
        raise PolicyValidationError("rollout_percent 必须在 0 到 100 之间")
    for name, version in (
        ("minimum_native_build", minimum_native_build),
        ("recommended_native_build", recommended_native_build),
    ):
        if version is not None and (not version.strip() or len(version.strip()) > 32):
            raise PolicyValidationError(f"{name} 格式不合法")
    return platform, channel, _validate_kill_switches(kill_switches)


def _safe_default(platform: str, channel: str) -> dict[str, Any]:
    return {
        "config_version": 0,
        "platform": platform,
        "channel": channel,
        "ota_enabled": True,
        "rollout_percent": 100,
        "minimum_native_build": None,
        "recommended_native_build": None,
        "forced_update": False,
        "kill_switches": {},
        "rollback_update_id": None,
        "expires_at": None,
        "source": "safe_default",
    }


def policy_to_public(policy: AppReleasePolicy, *, now: Optional[datetime] = None) -> dict[str, Any]:
    current = _now_utc(now)
    expires_at = policy.expires_at
    if expires_at is not None and _now_utc(expires_at) <= current:
        return _safe_default(policy.platform, policy.channel)
    return {
        "config_version": policy.config_version,
        "platform": policy.platform,
        "channel": policy.channel,
        "ota_enabled": bool(policy.ota_enabled),
        "rollout_percent": int(policy.rollout_percent),
        "minimum_native_build": policy.minimum_native_build,
        "recommended_native_build": policy.recommended_native_build,
        "forced_update": bool(policy.forced_update),
        "kill_switches": dict(policy.kill_switches or {}),
        "rollback_update_id": policy.rollback_update_id,
        "expires_at": policy.expires_at.isoformat() if policy.expires_at else None,
        "source": "remote",
    }


def get_release_policy(
    db: Session,
    *,
    platform: str,
    channel: str,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    platform, channel, _ = validate_policy_input(
        platform=platform,
        channel=channel,
        rollout_percent=100,
        minimum_native_build=None,
        recommended_native_build=None,
        kill_switches={},
    )
    policy = (
        db.query(AppReleasePolicy)
        .filter(
            AppReleasePolicy.platform == platform,
            AppReleasePolicy.channel == channel,
        )
        .order_by(desc(AppReleasePolicy.config_version))
        .first()
    )
    if policy is None:
        return _safe_default(platform, channel)
    return policy_to_public(policy, now=now)


def get_current_policy_revision(
    db: Session,
    *,
    platform: str,
    channel: str,
) -> Optional[AppReleasePolicy]:
    platform, channel, _ = validate_policy_input(
        platform=platform,
        channel=channel,
        rollout_percent=100,
        minimum_native_build=None,
        recommended_native_build=None,
        kill_switches={},
    )
    return (
        db.query(AppReleasePolicy)
        .filter(
            AppReleasePolicy.platform == platform,
            AppReleasePolicy.channel == channel,
        )
        .order_by(desc(AppReleasePolicy.config_version))
        .first()
    )


def publish_release_policy(
    db: Session,
    *,
    platform: str,
    channel: str,
    expected_config_version: int,
    ota_enabled: bool,
    rollout_percent: int,
    minimum_native_build: Optional[str],
    recommended_native_build: Optional[str],
    forced_update: bool,
    kill_switches: Optional[dict[str, Any]],
    rollback_update_id: Optional[str],
    expires_at: Optional[datetime],
    created_by_user_id: int,
) -> AppReleasePolicy:
    platform, channel, kill_switches = validate_policy_input(
        platform=platform,
        channel=channel,
        rollout_percent=rollout_percent,
        minimum_native_build=minimum_native_build,
        recommended_native_build=recommended_native_build,
        kill_switches=kill_switches,
    )
    if expected_config_version < 0:
        raise PolicyValidationError("expected_config_version 不能小于 0")
    if rollback_update_id is not None and (
        not rollback_update_id.strip() or len(rollback_update_id.strip()) > 128
    ):
        raise PolicyValidationError("rollback_update_id 格式不合法")

    current = get_current_policy_revision(db, platform=platform, channel=channel)
    current_version = current.config_version if current else 0
    if current_version != expected_config_version:
        raise PolicyVersionConflict("配置版本已变化，请刷新后重试")

    policy = AppReleasePolicy(
        platform=platform,
        channel=channel,
        config_version=current_version + 1,
        ota_enabled=ota_enabled,
        rollout_percent=rollout_percent,
        minimum_native_build=minimum_native_build.strip() if minimum_native_build else None,
        recommended_native_build=recommended_native_build.strip() if recommended_native_build else None,
        forced_update=forced_update,
        kill_switches=kill_switches,
        rollback_update_id=rollback_update_id.strip() if rollback_update_id else None,
        expires_at=expires_at,
        created_by_user_id=created_by_user_id,
    )
    db.add(policy)
    db.add(AgentAuditLog(
        user_id=created_by_user_id,
        agent_type="release_control_plane",
        action="release_policy_published",
        result_summary="应用发布策略已更新",
        result_detail={
            "platform": platform,
            "channel": channel,
            "config_version": current_version + 1,
            "ota_enabled": ota_enabled,
            "rollout_percent": rollout_percent,
            "minimum_native_build": minimum_native_build,
            "recommended_native_build": recommended_native_build,
            "forced_update": forced_update,
            "kill_switches": kill_switches,
            "rollback_update_id": rollback_update_id,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    ))
    try:
        db.commit()
        db.refresh(policy)
    except IntegrityError as exc:
        db.rollback()
        raise PolicyVersionConflict("配置版本已变化，请刷新后重试") from exc
    return policy
