"""POST /api/v1/client-events — Mobile 侧埋点接入.

仅接受白名单事件, 避免垃圾数据. 旁路写, 失败不影响主流程.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.client_event import ClientEvent
from app.models.user import User
from app.services.agent_runtime_identity import runtime_hmac_digest

router = APIRouter(prefix="/client-events", tags=["client-events"])
logger = logging.getLogger(__name__)


# 白名单: 观察期看板需要跟踪的事件.
# Phase 0.4 (2026-05-04): 加 5 种核心事件解除"客户端埋点几乎为空" 的观察盲区.
# 同步 mobile/services/clientEvents.ts ClientEventName 类型定义.
_ALLOWED_EVENTS = frozenset({
    # 上一季 ship (2026-05-01)
    "reasoning_sheet_opened",
    "journal_timeline_entered",
    "specialist_scorecard_entered",
    # Phase 0.4 — 让看板看得见用户操作
    "home_chip_clicked",          # meta: { chip: 'trust_hero' | 'specialist', target? }
    "action_card_executed",       # meta: { card_id, action: 'execute' | 'complete' | 'reminder' }
    "push_notification_opened",   # meta: { kind, deep_link }
    "chat_message_sent",          # meta: { source: 'chat'|'voice'|'siri', has_image }
    "chat_runtime_skill_completed",
    "quick_record_logged",        # meta: { kind: 'bp'|'weight'|'water'|'medication'|... }
    "home_cold_start_perf",
    # Phase 5 (2026-05-29) — starter chip CTR (调权从拍脑袋变成有据)
    "starter_chips_shown",        # meta: { keys: string[], source: 'chat' }  曝光(分母)
    "starter_chip_clicked",       # meta: { key, priority, position, source: 'chat' }  点击(分子)
    "cold_start_action_clicked",
    # Watch leverage-action loop (2026-06-16) — Health Agenda top_action 可观测
    "watch_action_shown",         # meta: { action_id, kind, priority_tier }
    "watch_action_completed",     # meta: { action_id, kind, priority_tier }
    "watch_action_snoozed",       # meta: { action_id, kind, priority_tier, minutes? }
    "watch_action_skipped",       # meta: { action_id, kind, priority_tier, reason? }
    "watch_action_failed",        # meta: { action_id, kind, priority_tier, error? }
    "watch_smart_reminder_visible",  # meta: { action_id, reminder_id, kind, surface }
    "agenda_action_failed",
    # Mobile Agent 可靠性终态. meta 严格限制为无正文、无资源标识的字段.
    "chat_turn_queued",
    "chat_attachment_terminal",
    "agent_turn_terminal",
    "voice_input_terminal",
    "voice_asr_terminal",
    "write_receipt_terminal",
    "diet_photo_recognition_terminal",
    "diet_photo_confirmation_terminal",
    "diet_share_terminal",
    # AIGC 媒体结果使用漏斗；禁止正文、URL、job_id 等资源标识。
    "aigc_media_played",
    "aigc_media_shared",
    # App update control plane — content-free lifecycle telemetry only.
    "app_update_phase",
    "app_update_terminal",
    "app_update_launch",
    # N-of-1 闭环北极星 (2026-06-17) — 已验证闭环数 (verified closed loops)
    "verified_loop",              # meta: { cycle_id, verdict_count, total } 复查产出 ≥1 个非 pending 裁决
})

_DURATION_BUCKETS = frozenset({"lt_1s", "1_3s", "3_10s", "10_30s", "gte_30s"})
_SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")
_DIET_SHARE_TARGETS = frozenset({"generic", "wechat", "xiaohongshu"})
_APP_UPDATE_EVENT_SCHEMAS = {
    "app_update_phase": {
        "allowed": frozenset({
            "phase", "platform", "channel", "runtime", "native_build", "update_id",
        }),
        "required": frozenset({"phase"}),
        "phases": frozenset({"checking", "downloading", "applying"}),
    },
    "app_update_terminal": {
        "allowed": frozenset({
            "phase", "duration_bucket", "platform", "channel", "runtime", "native_build",
            "update_id", "error_code",
        }),
        "required": frozenset({"phase", "duration_bucket"}),
        "phases": frozenset({
            "disabled", "current", "ready", "failed", "applied",
            "native_update_required", "native_update_recommended",
        }),
    },
    "app_update_launch": {
        "allowed": frozenset({
            "launch_source", "platform", "channel", "runtime", "native_build", "update_id",
        }),
        "required": frozenset({"launch_source"}),
        "launch_sources": frozenset({"embedded", "ota", "emergency", "unknown"}),
    },
}
_RELIABILITY_EVENT_SCHEMAS = {
    "agent_turn_terminal": {
        "allowed": frozenset({"phase", "duration_bucket", "error_code"}),
        "required": frozenset({"phase", "duration_bucket"}),
        "phases": frozenset({"completed", "failed", "interrupted"}),
    },
    "voice_input_terminal": {
        "allowed": frozenset({"phase", "duration_bucket", "error_code", "action_type"}),
        "required": frozenset({"phase", "duration_bucket", "action_type"}),
        "phases": frozenset({"completed", "failed", "cancelled"}),
    },
    "voice_asr_terminal": {
        "allowed": frozenset({
            "phase", "duration_bucket", "error_code", "action_type",
            "provider", "confidence", "empty",
        }),
        "required": frozenset({"phase", "duration_bucket", "action_type", "provider", "empty"}),
        "phases": frozenset({"completed", "failed"}),
    },
    "write_receipt_terminal": {
        "allowed": frozenset({
            "phase", "duration_bucket", "error_code", "action_type", "verified",
        }),
        "required": frozenset({"phase", "duration_bucket", "action_type", "verified"}),
        "phases": frozenset({"verified", "unverified", "failed"}),
    },
}
_CHAT_QUEUE_EVENT_SCHEMA = {
    "allowed": frozenset({"surface", "channel", "queue_depth_at_submit"}),
    "required": frozenset({"surface", "channel", "queue_depth_at_submit"}),
    "surfaces": frozenset({"mobile", "web", "mac"}),
    "channels": frozenset({"typed", "voice", "siri", "card"}),
}
_CHAT_ATTACHMENT_EVENT_SCHEMA = {
    "allowed": frozenset({
        "phase", "stage", "image_count", "duration_bucket",
        "payload_bucket", "error_code",
    }),
    "required": frozenset({
        "phase", "stage", "image_count", "duration_bucket", "payload_bucket",
    }),
    "phases": frozenset({"accepted", "failed"}),
    "stages": frozenset({"local_prepare", "server_accept"}),
    "payload_buckets": frozenset({
        "unknown", "lt_256kb", "256kb_1mb", "1_4mb", "gte_4mb",
    }),
    "error_codes": frozenset({
        "draft_hydration_failed", "server_not_accepted", "send_rejected",
    }),
}

_DIET_CAPTURE_EVENT_SCHEMAS = {
    "diet_photo_recognition_terminal": {
        "allowed": frozenset({
            "phase", "duration_ms", "server_total_ms", "food_count",
            "table_calibrated_count", "client_prepare_ms", "payload_bytes",
            "error_code",
        }),
        "required": frozenset({
            "phase", "duration_ms", "food_count", "table_calibrated_count",
        }),
        "phases": frozenset({"completed", "failed", "cancelled"}),
    },
    "diet_photo_confirmation_terminal": {
        "allowed": frozenset({
            "phase", "duration_ms", "verified", "corrected", "error_code",
        }),
        "required": frozenset({"phase", "duration_ms", "verified"}),
        "phases": frozenset({"completed", "failed"}),
    },
    "diet_share_terminal": {
        "allowed": frozenset({
            "phase", "duration_ms", "has_photo", "share_target", "error_code",
        }),
        "required": frozenset({"phase", "duration_ms", "has_photo"}),
        "phases": frozenset({"completed", "failed", "cancelled"}),
    },
}
_DIET_SHARE_ERROR_CODES = frozenset({
    "poster_render_failed", "poster_save_failed", "poster_share_failed",
})
_AIGC_ENGAGEMENT_EVENT_SCHEMAS = {
    "aigc_media_played": {
        "allowed": frozenset({"media_kind"}),
        "required": frozenset({"media_kind"}),
    },
    "aigc_media_shared": {
        "allowed": frozenset({"phase", "media_kind", "share_target", "error_code"}),
        "required": frozenset({"phase", "media_kind", "share_target"}),
        "phases": frozenset({"completed", "failed"}),
    },
}
_AIGC_MEDIA_KINDS = frozenset({"image", "video"})
_AIGC_SHARE_TARGETS = frozenset({"wechat", "xiaohongshu"})


class EventIn(BaseModel):
    event_name: str = Field(..., max_length=64)
    event_key: Optional[str] = Field(default=None, max_length=64)
    meta: Optional[Dict[str, Any]] = None

    @field_validator("event_key")
    @classmethod
    def _safe_event_key(cls, value: Optional[str]):
        if value is not None and _SAFE_TOKEN.fullmatch(value) is None:
            raise ValueError("invalid event_key")
        return value

    @field_validator("meta")
    @classmethod
    def _meta_size_limit(cls, v: Optional[Dict[str, Any]]):
        if v is None:
            return v
        import json

        payload = json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(payload.encode("utf-8")) > 2048:
            raise ValueError("meta too large (max 2KB)")
        return v

    @model_validator(mode="after")
    def _validate_reliability_meta(self):
        if (
            self.event_key is not None
            and self.event_name != "chat_attachment_terminal"
        ):
            raise ValueError("event_key is not supported for this event")
        if self.event_name == "chat_turn_queued":
            if self.meta is None:
                raise ValueError("chat queue event meta is required")

            keys = set(self.meta)
            extra = keys - _CHAT_QUEUE_EVENT_SCHEMA["allowed"]
            missing = _CHAT_QUEUE_EVENT_SCHEMA["required"] - keys
            if extra:
                raise ValueError(f"chat queue event meta has forbidden fields: {sorted(extra)}")
            if missing:
                raise ValueError(f"chat queue event meta missing fields: {sorted(missing)}")
            if self.meta.get("surface") not in _CHAT_QUEUE_EVENT_SCHEMA["surfaces"]:
                raise ValueError("invalid chat queue event surface")
            if self.meta.get("channel") not in _CHAT_QUEUE_EVENT_SCHEMA["channels"]:
                raise ValueError("invalid chat queue event channel")
            queue_depth = self.meta.get("queue_depth_at_submit")
            if type(queue_depth) is not int or not 1 <= queue_depth <= 50:
                raise ValueError("invalid chat queue event queue_depth_at_submit")
            return self

        if self.event_name == "chat_attachment_terminal":
            if self.event_key is None:
                raise ValueError("chat attachment event_key is required")
            if self.meta is None:
                raise ValueError("chat attachment event meta is required")
            keys = set(self.meta)
            extra = keys - _CHAT_ATTACHMENT_EVENT_SCHEMA["allowed"]
            missing = _CHAT_ATTACHMENT_EVENT_SCHEMA["required"] - keys
            if extra:
                raise ValueError(
                    f"chat attachment event meta has forbidden fields: {sorted(extra)}"
                )
            if missing:
                raise ValueError(
                    f"chat attachment event meta missing fields: {sorted(missing)}"
                )
            if self.meta.get("phase") not in _CHAT_ATTACHMENT_EVENT_SCHEMA["phases"]:
                raise ValueError("invalid chat attachment event phase")
            if self.meta.get("stage") not in _CHAT_ATTACHMENT_EVENT_SCHEMA["stages"]:
                raise ValueError("invalid chat attachment event stage")
            if self.meta.get("duration_bucket") not in _DURATION_BUCKETS:
                raise ValueError("invalid chat attachment event duration_bucket")
            if (
                self.meta.get("payload_bucket")
                not in _CHAT_ATTACHMENT_EVENT_SCHEMA["payload_buckets"]
            ):
                raise ValueError("invalid chat attachment event payload_bucket")
            image_count = self.meta.get("image_count")
            if type(image_count) is not int or not 1 <= image_count <= 9:
                raise ValueError("invalid chat attachment event image_count")
            error_code = self.meta.get("error_code")
            if (
                error_code is not None
                and (
                    not isinstance(error_code, str)
                    or error_code
                    not in _CHAT_ATTACHMENT_EVENT_SCHEMA["error_codes"]
                )
            ):
                raise ValueError("invalid chat attachment event error_code")
            phase = self.meta.get("phase")
            stage = self.meta.get("stage")
            if phase == "accepted" and (
                stage != "server_accept" or error_code is not None
            ):
                raise ValueError("invalid accepted chat attachment terminal state")
            if phase == "failed" and error_code is None:
                raise ValueError("failed chat attachment terminal requires error_code")
            if (
                phase == "failed"
                and stage == "local_prepare"
                and error_code != "draft_hydration_failed"
            ):
                raise ValueError("invalid local preparation attachment failure")
            if (
                phase == "failed"
                and stage == "server_accept"
                and error_code not in {"server_not_accepted", "send_rejected"}
            ):
                raise ValueError("invalid server attachment failure")
            return self

        app_update_schema = _APP_UPDATE_EVENT_SCHEMAS.get(self.event_name)
        if app_update_schema is not None:
            if self.meta is None:
                raise ValueError("app update event meta is required")

            keys = set(self.meta)
            extra = keys - app_update_schema["allowed"]
            missing = app_update_schema["required"] - keys
            if extra:
                raise ValueError(f"app update event meta has forbidden fields: {sorted(extra)}")
            if missing:
                raise ValueError(f"app update event meta missing fields: {sorted(missing)}")

            if self.event_name == "app_update_launch":
                if self.meta.get("launch_source") not in app_update_schema["launch_sources"]:
                    raise ValueError("invalid app update launch_source")
            elif self.meta.get("phase") not in app_update_schema["phases"]:
                raise ValueError("invalid app update phase")

            if "duration_bucket" in self.meta and self.meta["duration_bucket"] not in _DURATION_BUCKETS:
                raise ValueError("invalid app update duration_bucket")
            for key in (
                "platform", "channel", "runtime", "native_build", "update_id", "error_code",
            ):
                value = self.meta.get(key)
                if value is not None and (
                    not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None
                ):
                    raise ValueError(f"invalid app update {key}")
            return self

        schema = _RELIABILITY_EVENT_SCHEMAS.get(self.event_name)
        if schema is not None:
            if self.meta is None:
                raise ValueError("reliability event meta is required")

            keys = set(self.meta)
            extra = keys - schema["allowed"]
            missing = schema["required"] - keys
            if extra:
                raise ValueError(f"reliability event meta has forbidden fields: {sorted(extra)}")
            if missing:
                raise ValueError(f"reliability event meta missing fields: {sorted(missing)}")
            if self.meta.get("phase") not in schema["phases"]:
                raise ValueError("invalid reliability event phase")
            if self.meta.get("duration_bucket") not in _DURATION_BUCKETS:
                raise ValueError("invalid reliability event duration_bucket")

            for key in ("action_type", "error_code", "provider"):
                value = self.meta.get(key)
                if value is not None and (
                    not isinstance(value, str) or _SAFE_TOKEN.fullmatch(value) is None
                ):
                    raise ValueError(f"invalid reliability event {key}")
            confidence = self.meta.get("confidence")
            if confidence is not None and confidence not in {"high", "medium", "low"}:
                raise ValueError("invalid reliability event confidence")
            if "empty" in self.meta and type(self.meta["empty"]) is not bool:
                raise ValueError("invalid reliability event empty")
            if "verified" in self.meta and type(self.meta["verified"]) is not bool:
                raise ValueError("invalid reliability event verified")
            if self.event_name == "write_receipt_terminal":
                expected_verified = self.meta.get("phase") == "verified"
                if self.meta.get("verified") is not expected_verified:
                    raise ValueError("write receipt phase contradicts verified")
            return self

        aigc_schema = _AIGC_ENGAGEMENT_EVENT_SCHEMAS.get(self.event_name)
        if aigc_schema is not None:
            if self.meta is None:
                raise ValueError("AIGC engagement event meta is required")
            keys = set(self.meta)
            extra = keys - aigc_schema["allowed"]
            missing = aigc_schema["required"] - keys
            if extra:
                raise ValueError(f"AIGC engagement event meta has forbidden fields: {sorted(extra)}")
            if missing:
                raise ValueError(f"AIGC engagement event meta missing fields: {sorted(missing)}")
            if self.meta.get("media_kind") not in _AIGC_MEDIA_KINDS:
                raise ValueError("invalid AIGC engagement media_kind")
            if self.event_name == "aigc_media_shared":
                if self.meta.get("phase") not in aigc_schema["phases"]:
                    raise ValueError("invalid AIGC engagement phase")
                if self.meta.get("share_target") not in _AIGC_SHARE_TARGETS:
                    raise ValueError("invalid AIGC engagement share_target")
                error_code = self.meta.get("error_code")
                if error_code is not None and (
                    not isinstance(error_code, str)
                    or _SAFE_TOKEN.fullmatch(error_code) is None
                ):
                    raise ValueError("invalid AIGC engagement error_code")
            return self

        diet_schema = _DIET_CAPTURE_EVENT_SCHEMAS.get(self.event_name)
        if diet_schema is None:
            return self
        if self.meta is None:
            raise ValueError("diet capture event meta is required")
        keys = set(self.meta)
        extra = keys - diet_schema["allowed"]
        missing = diet_schema["required"] - keys
        if extra:
            raise ValueError(f"diet capture event meta has forbidden fields: {sorted(extra)}")
        if missing:
            raise ValueError(f"diet capture event meta missing fields: {sorted(missing)}")
        if self.meta.get("phase") not in diet_schema["phases"]:
            raise ValueError("invalid diet capture event phase")

        for key in ("duration_ms", "server_total_ms", "client_prepare_ms"):
            value = self.meta.get(key)
            if value is not None and (
                type(value) not in {int, float} or not 0 <= value <= 300_000
            ):
                raise ValueError(f"invalid diet capture event {key}")
        payload_bytes = self.meta.get("payload_bytes")
        if payload_bytes is not None and (
            type(payload_bytes) is not int or not 0 <= payload_bytes <= 20 * 1024 * 1024
        ):
            raise ValueError("invalid diet capture event payload_bytes")
        for key in ("food_count", "table_calibrated_count"):
            value = self.meta.get(key)
            if value is not None and (type(value) is not int or not 0 <= value <= 20):
                raise ValueError(f"invalid diet capture event {key}")
        if self.meta.get("table_calibrated_count", 0) > self.meta.get("food_count", 0):
            raise ValueError("table calibrated count exceeds food count")
        for key in ("verified", "corrected", "has_photo"):
            if key in self.meta and type(self.meta[key]) is not bool:
                raise ValueError(f"invalid diet capture event {key}")
        if self.event_name == "diet_share_terminal":
            share_target = self.meta.get("share_target")
            if share_target is not None and share_target not in _DIET_SHARE_TARGETS:
                raise ValueError("invalid diet share target")
        error_code = self.meta.get("error_code")
        if error_code is not None:
            if self.event_name == "diet_share_terminal":
                if (
                    not isinstance(error_code, str)
                    or error_code not in _DIET_SHARE_ERROR_CODES
                ):
                    raise ValueError("invalid diet share error_code")
            elif not isinstance(error_code, str) or _SAFE_TOKEN.fullmatch(error_code) is None:
                raise ValueError("invalid diet capture event error_code")
        return self


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="上报一条 UI 事件")
def post_client_event(
    body: EventIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if body.event_name not in _ALLOWED_EVENTS:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"event_name 不在白名单: {body.event_name}",
                "allowed": sorted(_ALLOWED_EVENTS),
            },
        )

    stored_event_key = None
    if body.event_key is not None:
        stored_event_key = runtime_hmac_digest(
            "client-event-idempotency-v1",
            current_user.id,
            body.event_name,
            body.event_key,
        )
    existing = None
    if stored_event_key is not None:
        existing = db.query(ClientEvent).filter(
            ClientEvent.user_id == current_user.id,
            ClientEvent.event_name == body.event_name,
            ClientEvent.event_key == stored_event_key,
        ).first()
    if existing is not None:
        return {"ok": True, "id": existing.id, "duplicate": True}

    try:
        ev = ClientEvent(
            user_id=current_user.id,
            event_name=body.event_name,
            event_key=stored_event_key,
            meta=body.meta,
        )
        db.add(ev)
        db.commit()
        return {"ok": True, "id": ev.id, "duplicate": False}
    except IntegrityError:
        db.rollback()
        if stored_event_key is not None:
            existing = db.query(ClientEvent).filter(
                ClientEvent.user_id == current_user.id,
                ClientEvent.event_name == body.event_name,
                ClientEvent.event_key == stored_event_key,
            ).first()
            if existing is not None:
                return {"ok": True, "id": existing.id, "duplicate": True}
        logger.warning("[client-events] 幂等键冲突后未找到原事件")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "事件暂未持久化，请稍后重试",
                "error_code": "client_event_persistence_failed",
            },
        )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.warning("[client-events] 写入失败", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "事件暂未持久化，请稍后重试",
                "error_code": "client_event_persistence_failed",
            },
        )
