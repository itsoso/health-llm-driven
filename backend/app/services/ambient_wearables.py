from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.ambient_wearable import (
    AudioInputEvent,
    GlanceCard,
    HearingHealthTask,
    VisualInputEvent,
)
from app.models.daily_health import DietRecord
from app.schemas.diet import MealType
from app.models.write_intent import WriteIntent
from app.services import write_intent_service

_BEIJING_TZ = timezone(timedelta(hours=8))
_MEAL_TYPES = {meal.value for meal in MealType}


def audio_next_action(intent: str) -> Optional[Dict[str, str]]:
    if intent == "food":
        return {"type": "parse_food_draft", "method": "POST", "path": "/diet/voice/parse"}
    if intent == "symptom":
        return {"type": "evaluate_symptom", "method": "POST", "path": "/watch/symptoms"}
    if intent == "movement":
        return {"type": "fetch_guided_movement", "method": "GET", "path": "/movement/guided-task?domain=strength"}
    return None


def visual_next_action(intent: str) -> Optional[Dict[str, str]]:
    if intent == "food_scan":
        return {"type": "confirm_food_draft", "method": "POST", "path": "/diet/records"}
    if intent == "medication_scan":
        return {"type": "review_medication_label", "method": "POST", "path": "/medications"}
    if intent == "supplement_scan":
        return {"type": "review_supplement_label", "method": "POST", "path": "/supplements"}
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


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _target_reps_from_text(text: str) -> int:
    match = re.search(r"(\d{1,3})\s*(个|下|次)?", text)
    if match:
        reps = int(match.group(1))
        if 1 <= reps <= 200:
            return reps
    zh_numbers = (
        ("二十五", 25),
        ("十五", 15),
        ("二十", 20),
        ("三十", 30),
        ("四十", 40),
        ("五十", 50),
        ("十", 10),
    )
    for token, reps in zh_numbers:
        if token in text:
            return reps
    return 20


def _voice_command(
    *,
    intent: str,
    event_intent: str,
    client_action: str,
    voice_reply: str,
    display_text: str,
    route: Optional[str] = None,
    requires_confirmation: bool = False,
    safety_level: str = "health_l3",
    parameters: Optional[Dict[str, Any]] = None,
    recommended_next_action: Optional[Dict[str, str]] = None,
    event_status: str = "processed",
    routed: bool = True,
) -> Dict[str, Any]:
    return {
        "intent": intent,
        "event_intent": event_intent,
        "event_status": event_status,
        "client_action": client_action,
        "route": route,
        "voice_reply": voice_reply,
        "display_text": display_text,
        "requires_confirmation": requires_confirmation,
        "safety_level": safety_level,
        "parameters": parameters or {},
        "recommended_next_action": recommended_next_action,
        "safety_result": {
            "routed": routed,
            "router": "deterministic_rokid_voice_v1",
            "autonomy_tier": "manual_confirm",
        },
    }


def route_rokid_voice_command(transcript: str, *, context: str = "rokid_health") -> Dict[str, Any]:
    """Map a bounded Rokid transcript into a whitelisted mobile client action."""
    text = (transcript or "").strip().lower()

    if _contains_any(
        text,
        (
            "拍一下",
            "拍这餐",
            "拍一下这餐",
            "记录这餐",
            "记录这顿",
            "记录这顿饭",
            "记录这一顿",
            "记录这一餐",
            "记录午饭",
            "记录晚饭",
            "记录早餐",
            "热量",
        ),
    ):
        return _voice_command(
            intent="food_photo",
            event_intent="food",
            client_action="capture_food_photo",
            voice_reply="我来拍这餐, 识别后会生成待确认的热量和营养记录。",
            display_text="拍摄餐食并生成待确认饮食记录",
            requires_confirmation=True,
            parameters={"visual_intent": "food_scan"},
            recommended_next_action={
                "type": "capture_food_photo",
                "method": "POST",
                "path": "/ambient/visual-inputs",
            },
        )

    if "俯卧撑" in text and _contains_any(text, ("开始", "来一组", "开一组", "做一组")):
        target_reps = _target_reps_from_text(text)
        return _voice_command(
            intent="pushup_start",
            event_intent="movement",
            client_action="open_pushup_coach",
            route="/rokid-pushup-coach",
            voice_reply=f"开始俯卧撑, 目标 {target_reps} 个。先保证动作完整。",
            display_text=f"启动 Rokid 俯卧撑计数: {target_reps} 个",
            parameters={"target_reps": target_reps},
            recommended_next_action={
                "type": "start_rokid_pushup_session",
                "method": "POST",
                "path": "/devices/rokid/pushup-sessions",
            },
        )

    if "俯卧撑" in text and _contains_any(text, ("保存", "记下来", "记录本组")):
        return _voice_command(
            intent="pushup_save",
            event_intent="movement",
            client_action="save_pushup_set",
            route="/rokid-pushup-coach",
            voice_reply="我会保存当前这一组俯卧撑。",
            display_text="保存当前俯卧撑组",
            requires_confirmation=True,
            recommended_next_action={
                "type": "save_pushup_exercise",
                "method": "POST",
                "path": "/daily-health/exercise",
            },
        )

    if "俯卧撑" in text and _contains_any(text, ("停止", "结束", "停下")):
        return _voice_command(
            intent="pushup_stop",
            event_intent="movement",
            client_action="stop_pushup_coach",
            route="/rokid-pushup-coach",
            voice_reply="已准备停止俯卧撑识别, 完成后可以保存本组。",
            display_text="停止 Rokid 俯卧撑识别",
            recommended_next_action={
                "type": "finish_rokid_pushup_session",
                "method": "POST",
                "path": "/devices/rokid/pushup-sessions/{session_id}/finish",
            },
        )

    if _contains_any(text, ("今天练什么", "指导我运动", "运动指导", "怎么练", "练什么", "换轻一点")):
        return _voice_command(
            intent="exercise_guidance",
            event_intent="movement",
            client_action="open_guided_task",
            route="/guided-task?domain=strength&source=rokid_voice",
            voice_reply="我会打开今天的运动指导, 强度由 Reva 的恢复状态门控决定。",
            display_text="打开今日运动指导",
            parameters={"domain": "strength"},
            recommended_next_action={
                "type": "fetch_guided_movement",
                "method": "GET",
                "path": "/movement/guided-task?domain=strength",
            },
        )

    if _contains_any(text, ("确认", "可以", "保存", "对的")):
        return _voice_command(
            intent="confirm",
            event_intent="note",
            client_action="confirm_current",
            voice_reply="收到, 我会确认当前待处理动作。",
            display_text="确认当前动作",
            requires_confirmation=True,
        )

    if _contains_any(text, ("跳过", "不用", "取消")):
        return _voice_command(
            intent="skip",
            event_intent="note",
            client_action="skip_current",
            voice_reply="已准备跳过当前动作。",
            display_text="跳过当前动作",
        )

    if _contains_any(text, ("等会", "稍后", "晚点")):
        return _voice_command(
            intent="later",
            event_intent="note",
            client_action="snooze_current",
            voice_reply="好, 这个动作稍后再提醒。",
            display_text="稍后提醒",
        )

    return _voice_command(
        intent="unknown",
        event_intent="note",
        client_action="clarify",
        voice_reply="这句我还不能安全执行。你可以说记录这餐、开始俯卧撑, 或指导我运动。",
        display_text="未识别的 Rokid 语音命令",
        event_status="pending_clarification",
        routed=False,
    )


def create_visual_input_event(
    db: Session,
    user_id: int,
    *,
    intent: str,
    source: str = "rokid_glasses",
    device_type: str = "glasses",
    image_uri: Optional[str] = None,
    image_sha256: Optional[str] = None,
    ocr_text: Optional[str] = None,
    recognition_result: Optional[Dict[str, Any]] = None,
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
) -> VisualInputEvent:
    event = VisualInputEvent(
        user_id=user_id,
        intent=intent,
        source=source,
        device_type=device_type,
        image_uri=image_uri,
        image_sha256=image_sha256,
        ocr_text=(ocr_text or "").strip() or None,
        recognition_result=recognition_result,
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


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _compact_number(value: Any) -> Optional[str]:
    number = _as_float(value)
    if number is None:
        text = str(value).strip() if value is not None else ""
        return text or None
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _food_name(food: Dict[str, Any]) -> str:
    return str(food.get("name") or food.get("food_name") or "").strip()


def _format_food_item(food: Dict[str, Any]) -> Optional[str]:
    name = _food_name(food)
    if not name:
        return None
    quantity = _compact_number(food.get("quantity"))
    unit = str(food.get("unit") or "").strip()
    if quantity and unit:
        return f"{name} {quantity}{unit}"
    if quantity:
        return f"{name} {quantity}"
    return name


def _foods_from_recognition(recognition: Dict[str, Any]) -> list[Dict[str, Any]]:
    foods = recognition.get("foods") or recognition.get("food_items") or []
    if not isinstance(foods, list):
        return []
    return [food for food in foods if isinstance(food, dict) and _food_name(food)]


def _sum_food_nutrient(foods: list[Dict[str, Any]], key: str) -> Optional[float]:
    values = [_as_float(food.get(key)) for food in foods]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return float(sum(values))


def _nutrition_value(
    recognition: Dict[str, Any],
    foods: list[Dict[str, Any]],
    *,
    total_key: str,
    item_key: str,
) -> Optional[float]:
    direct = _as_float(recognition.get(total_key))
    if direct is not None:
        return direct
    direct = _as_float(recognition.get(item_key))
    if direct is not None:
        return direct
    return _sum_food_nutrient(foods, item_key)


def _average_food_confidence(foods: list[Dict[str, Any]]) -> Optional[float]:
    values = [_as_float(food.get("confidence")) for food in foods]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return float(sum(values) / len(values))


def _normalize_meal_type(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(getattr(value, "value", value)).strip().lower()
    zh = {
        "早餐": MealType.BREAKFAST.value,
        "早饭": MealType.BREAKFAST.value,
        "午餐": MealType.LUNCH.value,
        "午饭": MealType.LUNCH.value,
        "晚餐": MealType.DINNER.value,
        "晚饭": MealType.DINNER.value,
        "加餐": MealType.SNACK.value,
        "零食": MealType.SNACK.value,
        "夜宵": MealType.SNACK.value,
        "其他": MealType.EXTRA.value,
    }
    text = zh.get(text, text)
    return text if text in _MEAL_TYPES else None


def _infer_meal_type(captured_at: datetime) -> str:
    local = captured_at.astimezone(_BEIJING_TZ) if captured_at.tzinfo else captured_at.replace(tzinfo=_BEIJING_TZ)
    hour = local.hour
    if 5 <= hour < 10:
        return MealType.BREAKFAST.value
    if 10 <= hour < 14:
        return MealType.LUNCH.value
    if 16 <= hour < 21:
        return MealType.DINNER.value
    return MealType.SNACK.value


def create_food_diet_record_from_visual_event(
    db: Session,
    user_id: int,
    event: VisualInputEvent,
    *,
    flush: bool = True,
) -> Optional[DietRecord]:
    """Write a DietRecord when a Rokid food visual event already has nutrition."""
    if event.intent != "food_scan" or not isinstance(event.recognition_result, dict):
        return None

    recognition = event.recognition_result
    if recognition.get("success") is False:
        return None

    foods = _foods_from_recognition(recognition)
    food_items = [item for item in (_format_food_item(food) for food in foods) if item]
    if not food_items:
        return None

    calories = _nutrition_value(recognition, foods, total_key="total_calories", item_key="calories")
    protein = _nutrition_value(recognition, foods, total_key="total_protein", item_key="protein")
    carbs = _nutrition_value(recognition, foods, total_key="total_carbs", item_key="carbs")
    fat = _nutrition_value(recognition, foods, total_key="total_fat", item_key="fat")
    fiber = _nutrition_value(recognition, foods, total_key="total_fiber", item_key="fiber")
    if all(value is None for value in (calories, protein, carbs, fat, fiber)):
        return None

    meta = event.meta if isinstance(event.meta, dict) else {}
    meal_type = (
        _normalize_meal_type(recognition.get("meal_type"))
        or _normalize_meal_type(meta.get("meal_type"))
        or _infer_meal_type(event.captured_at)
    )
    local_captured = (
        event.captured_at.astimezone(_BEIJING_TZ)
        if event.captured_at and event.captured_at.tzinfo
        else event.captured_at
    )
    record_date = local_captured.date() if local_captured else datetime.now(_BEIJING_TZ).date()
    meal_time = local_captured.time().replace(tzinfo=None) if local_captured else None
    primary_name = _food_name(foods[0])[:100]
    confidence = event.confidence or _as_float(recognition.get("confidence")) or _average_food_confidence(foods)

    # R4(医疗安全):食物/饮食是用户确认类写入,采集端不自动落"已确认"记录。
    # 调用方要求确认(meta.manual_confirm_required)、或识别置信缺失/不足(< 0.9)时,
    # 只把事件标记为待确认草稿、不写 DietRecord;由用户在饮食页确认后再落库
    # (避免识别错 → 静默写错一条饮食记录,council 标定的 R4 违规)。
    manual_confirm_required = bool(meta.get("manual_confirm_required"))
    if manual_confirm_required or confidence is None or confidence < 0.9:
        event.status = "needs_confirmation"
        event.target_type = "diet_draft"
        event.safety_result = {
            **(event.safety_result if isinstance(event.safety_result, dict) else {}),
            "manual_confirmation_required": True,
            "reason": "manual_confirm_required" if manual_confirm_required else "low_confidence",
            "confidence": confidence,
            "nutrition_from_recognition": True,
        }
        if flush:
            db.flush()
        return None

    record = DietRecord(
        user_id=user_id,
        record_date=record_date,
        meal_type=meal_type,
        meal_time=meal_time,
        food_name=primary_name,
        food_items=", ".join(food_items),
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        fiber=fiber,
        image_url=event.image_uri,
        ai_recognized=True,
        ai_confidence=confidence,
        ai_raw_result=json.dumps(recognition, ensure_ascii=False, default=str),
        notes="Rokid 眼镜食物照片自动生成, 请确认份量和营养估算。",
        health_tips=recognition.get("health_tips") if isinstance(recognition.get("health_tips"), str) else None,
    )
    db.add(record)
    if flush:
        db.flush()

    event.status = "processed"
    event.target_type = "diet_record"
    event.target_id = record.id
    event.safety_result = {
        **(event.safety_result if isinstance(event.safety_result, dict) else {}),
        "manual_confirmation_recommended": bool(meta.get("manual_confirm_required")),
        "nutrition_from_recognition": True,
    }
    return record


def create_glance_card(
    db: Session,
    user_id: int,
    *,
    surface: str = "rokid_glasses",
    card_type: str = "action_prompt",
    title: str,
    body: str,
    priority: str = "normal",
    action: Optional[Dict[str, Any]] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    expires_at: Optional[datetime] = None,
    meta: Optional[Dict[str, Any]] = None,
    flush: bool = True,
) -> GlanceCard:
    card = GlanceCard(
        user_id=user_id,
        surface=surface,
        card_type=card_type,
        title=title.strip(),
        body=body.strip(),
        priority=priority,
        action=action,
        target_type=target_type,
        target_id=target_id,
        expires_at=expires_at,
        meta=meta,
    )
    db.add(card)
    if flush:
        db.flush()
    return card


def list_active_glance_cards(
    db: Session,
    user_id: int,
    *,
    surface: Optional[str] = None,
    limit: int = 50,
) -> list[GlanceCard]:
    now = datetime.now(timezone.utc)
    query = db.query(GlanceCard).filter(
        GlanceCard.user_id == user_id,
        GlanceCard.status == "active",
    )
    if surface:
        query = query.filter(GlanceCard.surface == surface)
    query = query.filter((GlanceCard.expires_at.is_(None)) | (GlanceCard.expires_at > now))
    return query.order_by(GlanceCard.created_at.desc()).limit(limit).all()


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
