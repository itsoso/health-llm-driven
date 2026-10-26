"""Bounded recovery continuation: select, state the date, review, then confirm.

Old assistant prose is only a candidate hint, never write authority. Each named
row is re-read under the authenticated owner and a server-signed preview must
be presented before the manual WriteIntent can execute atomically.
"""
from datetime import UTC, date, datetime, timedelta
import hashlib
import hmac
import json
import logging
import re
from zoneinfo import ZoneInfo

from app.config import settings
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.illness import IllnessEpisode
from app.models.user import User
from app.models.write_intent import WriteIntent

KIND = 'illness_recovery'
TTL = timedelta(minutes=30)
_COLLECTIVE = re.compile(r'(?:这)?(?:两条|两项|两个)?都(?:好了|痊愈了|康复了)[。！!]?')
_ITEM = re.compile(r'^\s*(\d+)[.、]\s*(.+?)\s*[—–-]+\s*起病\s*(\d{4}-\d{2}-\d{2})(?:\D|$)', re.M)
logger = logging.getLogger(__name__)


class RecoveryConflict(ValueError):
    """No execution when the source, preview, dates, or record revision changed."""


def is_control(text):
    return bool(_COLLECTIVE.fullmatch(str(text or '').strip()) or re.fullmatch(
        r'(?:今天|昨天|明天|\d{4}-\d{2}-\d{2}|确认|取消|确认病症痊愈\s*\d+)', str(text or '').strip()))


def _sign(payload):
    if not settings.secret_key:
        raise RecoveryConflict('signing_unavailable')
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hmac.new(str(settings.secret_key).encode(), b'illness-recovery:v1\0' + raw.encode(), hashlib.sha256).hexdigest()


def _seal(payload):
    return {**payload, 'signature': _sign(payload)}


def _verify(payload):
    if not isinstance(payload, dict):
        raise RecoveryConflict('missing_context')
    body = {k: v for k, v in payload.items() if k != 'signature'}
    if not hmac.compare_digest(str(payload.get('signature', '')), _sign(body)):
        raise RecoveryConflict('invalid_context')
    return body


def _owned_source(db, user_id, message_id):
    row = db.query(AgentMessage).join(AgentConversation).filter(
        AgentMessage.id == message_id, AgentMessage.role == 'user',
        AgentConversation.user_id == user_id).first()
    if row is None:
        raise RecoveryConflict('source_not_owned')
    return row


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _snapshot(row):
    # Hash every persisted field so even a concurrent note edit invalidates the
    # proposal, without copying free-text notes into the confirmation payload.
    state = {c.name: str(getattr(row, c.name)) for c in row.__table__.columns}
    return {'id': row.id, 'name': row.name, 'start_date': row.start_date.isoformat(),
            'revision': _digest(json.dumps(state, sort_keys=True, ensure_ascii=False))}


def _rows(db, user_id, items, *, lock=False):
    ids = [item['id'] for item in items]
    if not 2 <= len(ids) <= 8 or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise RecoveryConflict('invalid_selection')
    query = db.query(IllnessEpisode).filter(IllnessEpisode.user_id == user_id,
                                           IllnessEpisode.id.in_(ids)).order_by(IllnessEpisode.id)
    if lock:
        query = query.with_for_update()
    rows = query.populate_existing().all()
    if len(rows) != len(ids):
        raise RecoveryConflict('record_not_owned')
    return rows


def _validate_selection(db, user_id, selection, now, timezone_name):
    body = _verify(selection)
    if body['user_id'] != user_id or body['timezone'] != timezone_name:
        raise RecoveryConflict('owner_or_timezone_changed')
    source = _owned_source(db, user_id, body['source_id'])
    if (source.conversation_id != body['conversation_id'] or _digest(source.content) != body['source_digest']
            or not _COLLECTIVE.fullmatch(source.content.strip())):
        raise RecoveryConflict('source_changed')
    reference = datetime.fromisoformat(body['reference_now'])
    if reference.tzinfo is None or now.tzinfo is None or not timedelta(0) <= now - reference <= TTL:
        raise RecoveryConflict('expired_selection')
    rows = _rows(db, user_id, body['items'])
    current = {r.id: _snapshot(r) for r in rows}
    if any(current[item['id']] != item for item in body['items']) or any(r.status not in {'active', 'improving'} for r in rows):
        raise RecoveryConflict('records_changed')
    return body


def selection_text(selection):
    lines = [f"{i}. {r['name']}（起病 {r['start_date']}）" for i, r in enumerate(selection['items'], 1)]
    return ('收到，你说上述记录都好了。请核对这几条：\n' + '\n'.join(lines)
            + '\n痊愈日期是哪一天？请回复“今天”“昨天”或 YYYY-MM-DD；尚未保存，补齐日期后会展示最终确认信息。')


def preview_text(wi):
    body = wi.payload['plan']
    lines = [f"{i}. {r['name']}（起病 {r['start_date']}）" for i, r in enumerate(body['selection']['items'], 1)]
    return ('待确认的病症状态修改：\n' + '\n'.join(lines)
            + f"\n将以上记录标为已痊愈，痊愈日期：{body['end_date']}。这是你的自述，不代表医学诊断。"
            + f'\n尚未保存。回复“确认病症痊愈 {wi.id}”或“确认”后一次保存；回复“取消”放弃。确认有效期30分钟。')


def _clarify():
    return {'status': 'clarification', 'reply': '尚未修改病症记录。无法完整核对上一轮的候选记录或日期，请明确病症名称、起病日期和痊愈日期，或从病症记录页选择对应记录后更新。'}


def _result(wi, decision):
    return {'status': 'verified', 'reply': ('已核验此前的更新，没有重复写入。' if decision.get('idempotent') else '已按你的确认保存这些病症的痊愈状态。')
            + f"痊愈日期：{wi.payload['plan']['end_date']}。",
            'write_receipts': decision['write_receipts']}


def _lock_runtime_admission(db, user_id):
    from sqlalchemy.exc import SQLAlchemyError
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService, RolloutConfigurationError
    rollout = AgentRuntimeRolloutService(db)
    try:
        if not rollout._selection_decision(user_id).managed:
            return
        state = rollout._locked_state()
        db.refresh(state)
        if not rollout.admission_decision(user_id).managed:
            raise RecoveryConflict('runtime_write_blocked')
    except (SQLAlchemyError, RolloutConfigurationError) as exc:
        raise RecoveryConflict('runtime_write_unavailable') from exc


def confirm(db, user_id, intent_id, *, reference_now=None):
    now = reference_now or datetime.now(UTC)
    try:
        wi = db.query(WriteIntent).filter(WriteIntent.id == intent_id, WriteIntent.user_id == user_id,
                                         WriteIntent.kind == KIND).with_for_update().populate_existing().first()
        if wi is None:
            raise LookupError('write_intent not found')
        if wi.trust_tier != 'manual_confirm' or wi.source != 'chat' or wi.target_type != 'agent_message':
            raise RecoveryConflict('invalid_plan')
        plan = _verify(wi.payload['plan'])
        selection = plan['selection']
        source = _owned_source(db, user_id, wi.target_id)
        if source.conversation_id != selection['conversation_id'] or _digest(source.content) != plan['date_source_digest']:
            raise RecoveryConflict('source_changed')
        # Require the exact server-rendered preview, not model prose or a plan
        # merely persisted before a disconnected client received its response.
        presented = db.query(AgentMessage).filter(AgentMessage.conversation_id == source.conversation_id,
            AgentMessage.role == 'assistant', AgentMessage.id > source.id).all()
        if not any(isinstance(m.meta, dict) and m.meta.get('illness_recovery_intent_id') == wi.id
                   and m.meta.get('client_turn_finalized') is True and m.content == preview_text(wi) for m in presented):
            raise RecoveryConflict('plan_not_presented')
        if wi.status == 'pending':
            _lock_runtime_admission(db, user_id)
        rows = _rows(db, user_id, selection['items'], lock=True)
        if wi.status == 'executed':
            receipts = wi.payload.get('write_receipts', [])
            if (len(receipts) != len(rows)
                    or wi.payload.get('execution_revisions') != [_snapshot(r) for r in rows]
                    or any(r.status != 'resolved' or r.end_date is None or r.end_date.isoformat() != plan['end_date'] for r in rows)
                    or any(receipt.get('resource_id') != row.id
                           or receipt.get('resource_type') != 'illness_episode'
                           or receipt.get('action') != 'update' or receipt.get('verified') is not True
                           or receipt.get('status') != 'verified' or receipt.get('end_date') != plan['end_date']
                           or receipt.get('operation_id') != f'write_intent:{KIND}:{wi.id}:{row.id}'
                           for receipt, row in zip(receipts, rows))):
                raise RecoveryConflict('receipt_changed')
            db.commit()
            return {'status': 'executed', 'idempotent': True, 'write_receipts': receipts}
        if wi.status != 'pending':
            raise RecoveryConflict('plan_not_pending')
        from app.utils.timezone import resolve_timezone_name
        from app.models.user_profile import UserProfile
        profile = db.query(UserProfile.manual_timezone, UserProfile.detected_timezone,
                           UserProfile.timezone).filter(UserProfile.user_id == user_id).first()
        current_timezone, _ = resolve_timezone_name(*(profile or (None, None, None)))
        if current_timezone != selection['timezone']:
            raise RecoveryConflict('timezone_changed')
        _validate_selection(db, user_id, selection, now, selection['timezone'])
        day = date.fromisoformat(plan['end_date'])
        local_day = now.astimezone(ZoneInfo(selection['timezone'])).date()
        if day > local_day or any(day < r.start_date for r in rows):
            raise RecoveryConflict('invalid_date')
        for row in rows:
            row.status, row.end_date = 'resolved', day
        db.flush()
        receipts = [{'resource_type': 'illness_episode', 'resource_id': row.id,
                     'action': 'update', 'status': 'verified', 'verified': True,
                     'success': True, 'operation_id': f'write_intent:{KIND}:{wi.id}:{row.id}',
                     'completed_at': now.isoformat(), 'end_date': day.isoformat()} for row in rows]
        for row in rows:
            db.refresh(row)
        wi.payload = {**wi.payload, 'write_receipts': receipts,
                      'execution_revisions': [_snapshot(row) for row in rows]}
        wi.status = wi.decision_status = 'executed'
        wi.decided_at = now
        db.commit()
        from app.twin.cache import invalidate_twin
        try:
            invalidate_twin(user_id)
        except Exception as exc:
            logger.warning('recovery cache invalidation failed error_type=%s', type(exc).__name__)
        return {'status': 'executed', 'idempotent': False, 'write_receipts': receipts}
    except Exception:
        db.rollback()
        raise


def resolve_turn(db, *, user_id, source_message_id, reference_now, timezone_name,
                 runtime_write_block_reason=None):
    source = _owned_source(db, user_id, source_message_id)
    text = source.content.strip()
    previous = db.query(AgentMessage).filter(AgentMessage.conversation_id == source.conversation_id,
        AgentMessage.id < source.id).order_by(AgentMessage.id.desc()).first()
    meta = previous.meta if previous is not None and previous.role == 'assistant' and isinstance(previous.meta, dict) else {}
    collective = _COLLECTIVE.fullmatch(text)
    explicit = re.fullmatch(r'确认病症痊愈\s*(\d+)', text)
    intent_id = int(explicit[1]) if explicit else meta.get('illness_recovery_intent_id') if text in {'确认', '取消'} else None
    selection = meta.get('illness_recovery_selection')
    if not collective and intent_id is None and selection is None:
        return None
    # Uncertain, quoted, negative or extra clauses cannot borrow this context.
    if not is_control(text):
        return None
    if runtime_write_block_reason:
        return {'status': 'error', 'runtime_control_unavailable': True,
                'reply': '病症记录写入暂时暂停或不可用，本次没有修改；请稍后重新核对确认。'}
    try:
        if intent_id is not None:
            wi = db.query(WriteIntent).filter(WriteIntent.id == intent_id, WriteIntent.user_id == user_id,
                                             WriteIntent.kind == KIND).first()
            if wi is None or wi.payload['plan']['selection']['conversation_id'] != source.conversation_id:
                return _clarify()
            if text == '取消':
                from app.services.write_intent_service import dismiss
                decision = dismiss(db, user_id, wi.id)
                if decision.get('status') == 'executed':
                    return _result(wi, decision)
                if decision.get('status') != 'dismissed':
                    return _clarify()
                return {'status': 'cancelled', 'reply': '已取消这次病症更新，没有执行新的修改。'}
            return _result(wi, confirm(db, user_id, wi.id, reference_now=reference_now))
        if collective:
            if (not meta.get('client_turn_finalized') or meta.get('write_receipts')
                    or not set(meta.get('tools_used') or []) & {'health_manage', 'health_query'}
                    or '确认' not in previous.content or '痊愈' not in previous.content):
                return _clarify()
            created = previous.created_at
            created = created.replace(tzinfo=UTC) if created.tzinfo is None else created
            if not timedelta(0) <= reference_now - created <= TTL:
                return _clarify()
            hints = list(_ITEM.finditer(previous.content))
            if not 2 <= len(hints) <= 8 or [int(m[1]) for m in hints] != list(range(1, len(hints) + 1)):
                return _clarify()
            items = []
            for match in hints:
                name = match[2].strip().strip('*').strip()
                rows = db.query(IllnessEpisode).filter(IllnessEpisode.user_id == user_id,
                    IllnessEpisode.name == name, IllnessEpisode.start_date == date.fromisoformat(match[3]),
                    IllnessEpisode.status.in_(['active', 'improving'])).limit(2).all()
                if len(rows) != 1 or rows[0].id in [item['id'] for item in items]:
                    return _clarify()
                items.append(_snapshot(rows[0]))
            selection = _seal({'version': 1, 'user_id': user_id, 'conversation_id': source.conversation_id,
                'source_id': source.id, 'source_digest': _digest(source.content), 'items': items,
                'timezone': timezone_name, 'reference_now': reference_now.isoformat()})
            return {'status': 'clarification', 'reply': selection_text(selection),
                    'meta': {'illness_recovery_selection': selection}}
        if text == '取消':
            return {'status': 'cancelled', 'reply': '已取消这次病症更新，没有修改记录。'}
        body = _validate_selection(db, user_id, selection, reference_now, timezone_name)
        if (source.conversation_id != body['conversation_id'] or previous.content != selection_text(selection)
                or meta.get('client_turn_finalized') is not True):
            return _clarify()
        local_day = reference_now.astimezone(ZoneInfo(timezone_name)).date()
        day = local_day if text == '今天' else local_day - timedelta(days=1) if text == '昨天' else date.fromisoformat(text)
        if day > local_day or any(day < date.fromisoformat(item['start_date']) for item in body['items']):
            return _clarify()
        db.query(User).filter(User.id == user_id).with_for_update().one()
        wi = db.query(WriteIntent).filter(WriteIntent.user_id == user_id, WriteIntent.kind == KIND,
            WriteIntent.target_type == 'agent_message', WriteIntent.target_id == source.id).first()
        if wi is None:
            plan = _seal({'selection': selection, 'end_date': day.isoformat(), 'date_source_digest': _digest(source.content)})
            wi = WriteIntent(user_id=user_id, kind=KIND, title='病症痊愈确认', source='chat',
                status='pending', trust_tier='manual_confirm', target_type='agent_message', target_id=source.id,
                payload={'plan': plan})
            db.add(wi)
        db.commit()
        return {'status': 'pending', 'reply': preview_text(wi), 'meta': {'illness_recovery_intent_id': wi.id}}
    except (RecoveryConflict, ValueError, KeyError, TypeError):
        db.rollback()
        return _clarify()
