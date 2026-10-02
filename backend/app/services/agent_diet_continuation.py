"""Bind a short portion correction only to the immediately preceding owned receipt."""
from datetime import datetime, timedelta
import re

from app.services.agent_kernel.types import ActionableReference

_BARE_PORTION = re.compile(r"(?:我)?(?:实际)?只吃了(?:其中的)?(?:[一二三四五六七八九十]+分之[一二三四五六七八九十]+|一半|半份|[0-9]+\s*/\s*[0-9]+)[。!！]*")


def diet_continuation_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest, authorization_grammar_digest,
        authorization_module_behavior_names,
    )
    return {
        "version": "owned-diet-portion.v1",
        "grammar": authorization_grammar_digest(globals()),
        "behavior": authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__),
        ),
    }


def is_bare_portion_correction(text):
    return isinstance(text, str) and _BARE_PORTION.fullmatch(text.strip()) is not None


def load_diet_portion_reference(db, user_id, conversation_id, snapshot):
    if (not is_bare_portion_correction(snapshot.envelope.text)
            or type(user_id) is not int or user_id <= 0
            or type(snapshot.context.user_id) is not int or type(snapshot.envelope.user_id) is not int
            or snapshot.context.user_id != user_id or snapshot.envelope.user_id != user_id
            or snapshot.context.current_time.tzinfo is None):
        return None
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.daily_health import DietRecord

    source_id = snapshot.envelope.source_message_id
    if not str(source_id or '').isdigit():
        return None
    current = (db.query(AgentMessage).join(AgentConversation)
               .filter(AgentConversation.user_id == user_id, AgentConversation.id == conversation_id,
                       AgentMessage.id == int(source_id), AgentMessage.role == 'user').first())
    if current is None or current.content != snapshot.envelope.text:
        return None
    previous = (db.query(AgentMessage).filter(AgentMessage.conversation_id == conversation_id,
                                            AgentMessage.id < current.id)
                .order_by(AgentMessage.id.desc()).first())
    if (previous is None or previous.role != 'assistant' or not isinstance(previous.meta, dict)
            or previous.meta.get('client_turn_finalized') is not True):
        return None
    receipts = previous.meta.get('write_receipts')
    if not isinstance(receipts, list) or len(receipts) != 1:
        return None
    receipt = receipts[0]
    if (not isinstance(receipt, dict) or receipt.get('verified') is not True
            or receipt.get('status') != 'verified' or receipt.get('resource_type') != 'diet_record'
            or receipt.get('action') not in {'create', 'update'}):
        return None
    try:
        if not str(receipt.get('resource_id', '')).isdigit():
            return None
        record_id = int(receipt['resource_id'])
        completed = datetime.fromisoformat(receipt['completed_at'].replace('Z', '+00:00'))
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    now = snapshot.context.current_time
    if record_id <= 0 or completed.tzinfo is None or not timedelta(0) <= now - completed <= timedelta(hours=24):
        return None
    # The verified receipt carries an offset; the message table stores naive
    # timestamps. Use the receipt's completion instant for the freshness gate.
    target = db.query(DietRecord).filter(DietRecord.user_id == user_id, DietRecord.id == record_id).first()
    if target is None or target.meal_type not in {'breakfast', 'lunch', 'dinner', 'snack'}:
        return None
    return ActionableReference(kind='owned_diet_portion_receipt', source_message_id=str(previous.id),
        data={'user_id': user_id, 'record_id': record_id, 'date': target.record_date.isoformat(),
              'meal_type': target.meal_type, 'completed_at': completed.isoformat()})


def resolve_diet_portion_correction(snapshot):
    from app.services.agent_executor import _parse_explicit_diet_correction
    explicit = _parse_explicit_diet_correction(snapshot.envelope.text, reference_now=snapshot.context.current_time)
    if explicit is not None:
        return explicit
    if not is_bare_portion_correction(snapshot.envelope.text):
        return None
    refs = [r for r in snapshot.actionable_references if r.kind == 'owned_diet_portion_receipt']
    if len(refs) != 1 or not str(refs[0].source_message_id or '').isdigit():
        return None
    data = refs[0].data
    if (type(data.get('record_id')) is not int or data['record_id'] <= 0
            or data.get('user_id') != snapshot.context.user_id
            or snapshot.context.user_id != snapshot.envelope.user_id):
        return None
    meal = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '加餐'}.get(data.get('meal_type'))
    if meal is None:
        return None
    canonical = f"修改{data.get('date')}{meal}记录#{data['record_id']}，{snapshot.envelope.text}"
    return _parse_explicit_diet_correction(canonical, reference_now=snapshot.context.current_time)
