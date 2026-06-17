from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.ambient_wearable import AudioInputEvent, HearingHealthTask
from app.models.write_intent import WriteIntent
from app.services import write_intent_service


def audio_next_action(intent: str) -> Optional[Dict[str, str]]:
    if intent == "food":
        return {"type": "parse_food_draft", "method": "POST", "path": "/diet/voice/parse"}
    if intent == "symptom":
        return {"type": "evaluate_symptom", "method": "POST", "path": "/watch/symptoms"}
    return None


def create_audio_input_event(
    db: Session,
    user_id: int,
    *,
    intent: str,
    transcript: str,
    source: str = "ambient_audio",
    device_type: str = "unknown",
    confidence: Optional[float] = None,
    captured_at: Optional[datetime] = None,
    status: str = "pending_confirmation",
    privacy_class: str = "health_l3",
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    write_intent_id: Optional[int] = None,
    safety_result: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    flush: bool = True,
) -> AudioInputEvent:
    event = AudioInputEvent(
        user_id=user_id,
        intent=intent,
        transcript=(transcript or "").strip(),
        source=source,
        device_type=device_type,
        confidence=confidence,
        captured_at=captured_at or datetime.now(timezone.utc),
        status=status,
        privacy_class=privacy_class,
        target_type=target_type,
        target_id=target_id,
        write_intent_id=write_intent_id,
        safety_result=safety_result,
        meta=meta,
    )
    db.add(event)
    if flush:
        db.flush()
    return event


def _hearing_title(task_type: str) -> str:
    if task_type == "noise_review":
        return "回顾近期噪音暴露"
    if task_type == "audiology_followup":
        return "安排听力专科复查"
    return "做一次听力测试"


def _hearing_description(task_type: str, reason: Optional[str]) -> str:
    base = {
        "noise_review": "回顾最近通勤、办公室或健身房的噪音暴露,必要时调整音量或佩戴听力保护。",
        "audiology_followup": "如近期听清困难、耳鸣或听力测试异常,建议预约听力专科评估。",
        "hearing_test": "用已授权的听力测试或专业听力评估建立个人听力基线。",
    }.get(task_type, "建立听力健康基线。")
    return f"{base} 原因:{reason}" if reason else base


def _write_intent_view(intent: Optional[WriteIntent]) -> Optional[Dict[str, Any]]:
    if intent is None:
        return None
    return {
        "id": intent.id,
        "kind": intent.kind,
        "title": intent.title,
        "description": intent.description,
        "status": intent.status,
        "source": intent.source,
        "trust_tier": intent.trust_tier,
        "target_type": intent.target_type,
        "target_id": intent.target_id,
        "payload": intent.payload,
        "executed_ref": intent.executed_ref,
        "created_at": intent.created_at.isoformat() if intent.created_at else None,
    }


def ensure_hearing_health_task(
    db: Session,
    user_id: int,
    *,
    task_type: str,
    reason: Optional[str] = None,
    source: str = "ambient_hearing",
    due_at: Optional[datetime] = None,
    priority: str = "normal",
    payload: Optional[Dict[str, Any]] = None,
) -> tuple[HearingHealthTask, WriteIntent, bool]:
    existing = (
        db.query(HearingHealthTask)
        .filter(
            HearingHealthTask.user_id == user_id,
            HearingHealthTask.task_type == task_type,
            HearingHealthTask.status == "pending",
        )
        .order_by(HearingHealthTask.created_at.desc())
        .first()
    )
    if existing is not None and existing.write_intent_id:
        wi = (
            db.query(WriteIntent)
            .filter(WriteIntent.id == existing.write_intent_id, WriteIntent.user_id == user_id)
            .first()
        )
        if wi is not None:
            return existing, wi, False

    task_payload = dict(payload or {})
    if due_at is not None:
        task_payload.setdefault("due_at", due_at.isoformat())
    task_payload.setdefault("task_type", task_type)

    task = existing or HearingHealthTask(
        user_id=user_id,
        task_type=task_type,
        status="pending",
        source=source,
        reason=reason,
        due_at=due_at,
        priority=priority,
        payload=task_payload,
    )
    if existing is None:
        db.add(task)
        db.flush()

    wi = write_intent_service.propose(
        db,
        user_id,
        kind="hearing_health_task",
        title=_hearing_title(task_type),
        description=_hearing_description(task_type, reason),
        source=source,
        target_type="hearing_health_task",
        target_id=task.id,
        payload={
            **task_payload,
            "remind_at": due_at.isoformat() if due_at else None,
            "priority": priority,
        },
        commit=False,
    )
    if wi is None:
        wi = (
            db.query(WriteIntent)
            .filter(
                WriteIntent.user_id == user_id,
                WriteIntent.kind == "hearing_health_task",
                WriteIntent.status == "pending",
                WriteIntent.target_type == "hearing_health_task",
                WriteIntent.target_id == task.id,
            )
            .first()
        )
    if wi is None:
        raise RuntimeError("failed to create or load hearing health write intent")

    task.write_intent_id = wi.id
    db.commit()
    db.refresh(task)
    db.refresh(wi)
    return task, wi, existing is None


def write_intent_view(intent: Optional[WriteIntent]) -> Optional[Dict[str, Any]]:
    return _write_intent_view(intent)
