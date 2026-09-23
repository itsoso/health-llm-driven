"""Source-bound photo descriptions propose an edit; they never execute a write.

The existing editor and revision-checked recalculation command own confirmation.
Neither model prose nor model-selected record IDs are accepted here.
"""
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import re
from zoneinfo import ZoneInfo

from app.config import settings
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.daily_health import DietPhotoAsset, DietRecord
from app.services.post_record_quality import build_diet_adjust_action
from app.utils.number_format import format_card_numbers

_KEY = "diet_photo_recognition"
_REQUEST = re.compile(
    r"(?:请)?(?:基于|根据|用)(?:刚才|刚刚)?"
    r"(?:识别的(?:这一餐|这餐)|识别结果|这(?:一)?餐的识别结果)"
    r"(?:来)?(?:修改|更新|替换)(?:我(?:的)?)?今天(?:的)?"
    r"(?P<meal>早餐|午餐|晚餐|加餐)(?:记录)?[。！!]?"
)
_MEALS = {"早餐": "breakfast", "午餐": "lunch", "晚餐": "dinner", "加餐": "snack"}


def _signature(payload):
    if not settings.secret_key:
        return ""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    return hmac.new(str(settings.secret_key).encode(), b"photo-edit-proposal:v1\0" + encoded,
                    hashlib.sha256).hexdigest()


def _owned_message(db, user_id, conversation_id, message_id):
    return (db.query(AgentMessage)
            .join(AgentConversation, AgentMessage.conversation_id == AgentConversation.id)
            .filter(AgentConversation.user_id == user_id, AgentMessage.id == message_id,
                    AgentMessage.conversation_id == conversation_id,
                    AgentMessage.role == "user").first())


def save_recognition(db, user_id, source_message_id, food_items, now):
    """Store only a bounded, structured vision description on its owned image turn."""
    if (type(user_id) is not int or user_id <= 0 or type(source_message_id) is not int
            or not isinstance(food_items, str) or not 1 <= len(food_items.strip()) <= 300
            or now.tzinfo is None):
        return False
    source = (db.query(AgentMessage)
              .join(AgentConversation, AgentMessage.conversation_id == AgentConversation.id)
              .filter(AgentConversation.user_id == user_id, AgentMessage.id == source_message_id,
                      AgentMessage.role == "user").first())
    if source is None or not source.image_url:
        return False
    payload = {"user_id": user_id, "conversation_id": source.conversation_id,
               "source_message_id": source.id, "image_binding": source.image_url,
               "food_items": food_items.strip(), "recognized_at": now.isoformat()}
    signature = _signature(payload)
    if not signature:
        return False
    source.meta = {**(source.meta or {}), _KEY: {**payload, "signature": signature}}
    db.commit()
    return True


def _blocked(reason, detail):
    return {"status": "blocked", "reason": reason, "cards": [],
            "reply": f"尚未修改饮食记录。{detail}"}


def build_correction_proposal(db, user_id, conversation_id, current_message_id, text, now, timezone_name):
    match = _REQUEST.fullmatch(str(text or "").strip())
    if match is None:
        return None
    if type(user_id) is not int or user_id <= 0 or now.tzinfo is None:
        return _blocked("source_unavailable", "无法核实本次照片来源，请重新发送餐食照片后再修改。")
    current = _owned_message(db, user_id, conversation_id, current_message_id)
    if current is None or current.content.strip() != str(text).strip():
        return _blocked("source_unavailable", "无法核实本次照片来源，请重新发送餐食照片后再修改。")
    previous = (db.query(AgentMessage).filter(
        AgentMessage.conversation_id == conversation_id, AgentMessage.id < current_message_id)
        .order_by(AgentMessage.id.desc()).limit(2).all())
    if (len(previous) != 2 or previous[0].role != "assistant" or previous[1].role != "user"
            or not isinstance(previous[0].meta, dict)
            or previous[0].meta.get("client_turn_finalized") is not True):
        return _blocked("source_unavailable", "请紧接已完成的餐食照片识别结果发起修改。")
    source = previous[1]
    saved = source.meta.get(_KEY) if isinstance(source.meta, dict) else None
    if not isinstance(saved, dict):
        return _blocked("source_unavailable", "这张历史照片没有可核验的识别快照，请重新发送照片。")
    payload = {key: value for key, value in saved.items() if key != "signature"}
    expected = _signature(payload)
    try:
        recognized_at = datetime.fromisoformat(payload["recognized_at"])
        valid_age = recognized_at.tzinfo is not None and timedelta(0) <= now - recognized_at <= timedelta(hours=24)
    except (KeyError, ValueError, TypeError):
        valid_age = False
    if (not expected or not isinstance(saved.get("signature"), str)
            or not hmac.compare_digest(expected, saved["signature"]) or not valid_age
            or payload.get("user_id") != user_id or payload.get("conversation_id") != conversation_id
            or payload.get("source_message_id") != source.id
            or not source.image_url or payload.get("image_binding") != source.image_url
            or not isinstance(payload.get("food_items"), str)
            or not 1 <= len(payload["food_items"].strip()) <= 300):
        return _blocked("source_unavailable", "照片识别来源已失效或过期，请重新发送照片。")
    local_date = now.astimezone(ZoneInfo(timezone_name)).date()
    candidates = (db.query(DietRecord).filter(
        DietRecord.user_id == user_id, DietRecord.record_date == local_date,
        DietRecord.meal_type == _MEALS[match["meal"]]).order_by(DietRecord.id).limit(2).all())
    if not candidates:
        return _blocked("target_not_found", f"没有找到今天的{match['meal']}记录；不会自动新建一餐。请先在饮食页核对日期和餐次。")
    if len(candidates) != 1:
        return _blocked("ambiguous_target", f"今天有多条{match['meal']}记录，请在饮食页选择要修改的那条。")
    target = candidates[0]
    other_saved_photo = (db.query(DietPhotoAsset.id).filter(
        DietPhotoAsset.user_id == user_id, DietPhotoAsset.origin_message_id == source.id,
        DietPhotoAsset.lifecycle == "attached", DietPhotoAsset.diet_record_id != target.id).first())
    if other_saved_photo:
        return _blocked("photo_already_recorded", "这张照片已经关联另一条饮食记录，请在饮食页核对，避免重复计入。")
    fields = ("meal_type", "food_items", "calories", "protein", "carbs", "fat", "fiber")
    action = build_diet_adjust_action(target.id, {key: getattr(target, key) for key in fields},
                                      current_record=target)
    seed = action["payload"]["patch"]["adjust_record"]
    seed["proposed_food_items"] = payload["food_items"]
    card = {"type": "record_quality", "data": format_card_numbers({
        "domain": "diet", "title": f"{local_date.isoformat()} {match['meal']}待修改",
        "summary": f"原记录：{target.food_items or '未填写食物'}",
        "record_id": target.id, "expanded_sections": ["adjust_record"], "adjust_record": seed,
        "boundary": "尚未保存；确认后重新估算营养，保留原记录照片。",
    }), "actions": [action]}
    return {"status": "waiting_for_user", "reason": "photo_edit_confirmation_required", "cards": [card],
            "reply": f"尚未修改。准备把今天{match['meal']}改为：{payload['food_items']}。请核对下方食物和份量，点击保存后才会重新估算并更新；原记录照片不变。旧版若未预填，可在饮食编辑页填入上述描述。"}
