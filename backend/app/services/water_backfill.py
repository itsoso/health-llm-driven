"""Source-bound, manually confirmed daily water totals using the WriteIntent ledger."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.daily_health import WaterIntake
from app.models.user import User
from app.models.write_intent import WriteIntent
from app.utils.timezone import get_china_now
from app.utils.number_format import format_display_number

logger = logging.getLogger(__name__)

KIND = "water_backfill"
MAX_DAYS = 14
_PREFIX = re.compile(r"^(?:请)?(?:帮我|给我|替我)?(?:补充记录|补记|记录)(?:一下)?")
_AMOUNT = re.compile(r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>毫升|ml|升|l)", re.I)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_RECENT = re.compile(r"最近(?P<days>\d+|[一二两三四五六七八九十]+)天")
_CN_DAYS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
            "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14}


class WaterBackfillConflict(ValueError):
    """The user must review changed facts or a fresh plan before a write."""


@dataclass(frozen=True)
class WaterBackfillDraft:
    items: tuple[dict[str, Any], ...] = ()
    clarification: str = ""
    date_note: str = ""


def parse_water_backfill(message: str, *, reference_now: datetime) -> WaterBackfillDraft | None:
    """Recognize only direct owned batch requests; uncertainty never supplies facts."""
    raw = str(message or "").strip()
    if not _PREFIX.match(raw) or not any(term in raw for term in ("饮水", "喝水")):
        return None
    if any(term in raw for term in ("不要", "别", "取消", "撤销", "如果", "假如", "他说", "她说", "爸爸", "妈妈", "家人", "朋友", "他人", "别人", "？", "?", "“", "”", '"', "‘", "’")):
        return None
    is_batch = any(term in raw for term in ("补记", "补充记录", "每天", "每日", "最近", "至")) or len(_DATE.findall(raw)) > 1
    if not is_batch:
        return None
    missing: list[str] = []
    dates: list[date] = []
    date_note = ""
    raw_dates = _DATE.findall(raw)
    try:
        if raw_dates:
            dates = [date.fromisoformat(value) for value in raw_dates]
            if len(dates) == 2 and re.search(r"\d{4}-\d{2}-\d{2}\s*(?:至|到|~|～)\s*\d{4}-\d{2}-\d{2}", raw):
                span = (dates[1] - dates[0]).days
                dates = [dates[0] + timedelta(days=offset) for offset in range(span + 1)] if 0 <= span < MAX_DAYS else []
        elif match := _RECENT.search(raw):
            token = match.group('days')
            count = int(token) if token.isascii() else _CN_DAYS.get(token, 0)
            if 1 <= count <= MAX_DAYS:
                dates = [reference_now.date() - timedelta(days=offset) for offset in reversed(range(count))]
                date_note = "最近天数按包含今天列出；请核对下列日期。"
        elif any(term in raw for term in ("昨天", "前天", "今天")):
            dates = [reference_now.date() - timedelta(days=offset) for term, offset in (("前天", 2), ("昨天", 1), ("今天", 0)) if term in raw]
    except ValueError:
        dates = []
    if not dates or len(dates) > MAX_DAYS or len(set(dates)) != len(dates) or any(day > reference_now.date() or (reference_now.date() - day).days > 366 for day in dates):
        missing.append("具体日期（最多14天，不能是未来日期）")
        dates = []
    amounts = list(_AMOUNT.finditer(raw))
    lower_bound = any(term in raw for term in ("以上", "以下", "至少", "至多", "超过", "不低于", "不超过", "大于", "小于", "左右", "大概", "大约", "差不多"))
    per_date_amounts: dict[str, int] = {}
    if len(amounts) > 1 and len(raw_dates) == len(amounts) and not lower_bound:
        pairs = re.findall(r'(\d{4}-\d{2}-\d{2})[：:\s]*(\d+(?:\.\d+)?)\s*(毫升|ml|升|l)', raw, re.I)
        for day, value, unit in pairs:
            total = Decimal(value) * (1000 if unit.lower() in {'l', '升'} else 1)
            if total == total.to_integral_value() and 1 <= total <= 5000:
                per_date_amounts[day] = int(total)
        if len(per_date_amounts) != len(amounts):
            per_date_amounts = {}
    amount = None
    if len(amounts) == 1 and not lower_bound:
        try:
            amount = Decimal(amounts[0].group('amount'))
            if amounts[0].group('unit').lower() in {'l', '升'}:
                amount *= 1000
            if not amount.is_finite() or amount != amount.to_integral_value() or not 1 <= amount <= 5000:
                amount = None
        except InvalidOperation:
            amount = None
    if amount is None and not per_date_amounts:
        missing.append("每天准确的总毫升数（“以上”只说明下限，不能当成准确总量）")
    elif not per_date_amounts and len(dates) > 1 and not any(term in raw for term in ("每天", "每日", "各")):
        missing.append("这些日期各自的全天总量，或说明每天总量相同")
    # Consume the constrained input grammar: unknown content must not turn
    # another person's facts, an increment, or a second task into a batch.
    residue = _PREFIX.sub('', raw, count=1)
    residue = _DATE.sub('', residue)
    residue = _RECENT.sub('', residue)
    residue = _AMOUNT.sub('', residue)
    residue = re.sub(r"最近几天|前天|昨天|今天|饮水|喝水|每天|每日|总量|全天|各|记录|都在|都是|均为|为|是|的|至|到|以上|以下|至少|至多|超过|不低于|不超过|大于|小于|左右|大概|大约|差不多|我", '', residue)
    residue = re.sub(r"[\s，,。；;：:、~～和与及]", '', residue)
    if residue:
        return WaterBackfillDraft(clarification="请按具体日期和全天准确总量补记，例如：补记2026-09-30至2026-10-01饮水，每天总量1800ml。不会将新增量或他人数据当作你的全天总量。")
    if missing:
        return WaterBackfillDraft(clarification="可以补记。还需要" + "；".join(missing) + "。请补充后我会逐日核对已有记录，再展示待确认明细。")
    return WaterBackfillDraft(items=tuple({'date': day.isoformat(), 'total_ml': per_date_amounts.get(day.isoformat(), int(amount or 0))} for day in sorted(dates)), date_note=date_note)


def _source(db: Session, user_id: int, source_id: int) -> AgentMessage:
    row = db.query(AgentMessage).join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id).filter(
        AgentMessage.id == source_id, AgentMessage.role == 'user', AgentConversation.user_id == user_id,
    ).first()
    if row is None:
        raise LookupError('water source not found')
    return row


def _rows(db: Session, user_id: int, dates: list[str]) -> dict[str, list[WaterIntake]]:
    result = {day: [] for day in dates}
    for row in db.query(WaterIntake).filter(WaterIntake.user_id == user_id, WaterIntake.record_date.in_([date.fromisoformat(day) for day in dates])).order_by(WaterIntake.id).populate_existing().all():
        result[row.record_date.isoformat()].append(row)
    return result


def propose_water_backfill(db: Session, *, user_id: int, source_message_id: int, reference_now: datetime) -> WriteIntent | None:
    source = _source(db, user_id, source_message_id)
    draft = parse_water_backfill(source.content, reference_now=reference_now)
    if draft is None or not draft.items:
        return None
    # A source retry and a second identical source must converge on the same
    # current totals. Row locking serializes proposal creation for this owner.
    db.query(User).filter(User.id == user_id).with_for_update().one()
    existing = db.query(WriteIntent).filter(WriteIntent.user_id == user_id, WriteIntent.kind == KIND,
        WriteIntent.target_type == 'agent_message', WriteIntent.target_id == source_message_id).first()
    if existing is not None:
        db.commit()
        return existing
    rows = _rows(db, user_id, [item['date'] for item in draft.items])
    items = []
    for item in draft.items:
        day_rows = rows[item['date']]
        total = sum(row.amount_ml or 0 for row in day_rows)
        if total > item['total_ml']:
            raise WaterBackfillConflict('existing_total_exceeds_target')
        items.append({**item, 'existing_ml': total, 'add_ml': item['total_ml'] - total,
                      'baseline': [{'id': row.id, 'amount_ml': row.amount_ml} for row in day_rows]})
    payload = {'version': 1, 'reference_now': reference_now.isoformat(),
               'expires_at': (reference_now + timedelta(minutes=30)).isoformat(),
               'conversation_id': source.conversation_id, 'items': items, 'date_note': draft.date_note}
    wi = WriteIntent(user_id=user_id, kind=KIND, title='饮水补记确认', description='逐日核对全天总量，只补足缺失量。',
                     status='pending', source='chat', trust_tier='manual_confirm', target_type='agent_message',
                     target_id=source_message_id, payload=payload)
    db.add(wi)
    db.commit()
    db.refresh(wi)
    return wi


def preview_text(wi: WriteIntent) -> str:
    lines = [wi.payload.get('date_note') or '请核对饮水补记日期和全天总量：']
    for item in wi.payload['items']:
        lines.append(f"{item['date']}：全天 {format_display_number(item['total_ml'])}ml，已有 {format_display_number(item['existing_ml'])}ml，待补 {format_display_number(item['add_ml'])}ml。")
    lines.append(f"尚未写入。回复“确认饮水补记 {wi.id}”后一次完成；回复“取消”可放弃。确认有效期30分钟。")
    return '\n'.join(lines)


def _validate_plan(db: Session, wi: WriteIntent, now: datetime) -> None:
    if wi.target_type != 'agent_message' or wi.trust_tier != 'manual_confirm':
        raise WaterBackfillConflict('invalid_plan')
    source = _source(db, wi.user_id, wi.target_id)
    payload = wi.payload or {}
    try:
        reference = datetime.fromisoformat(payload['reference_now'])
        expiry = datetime.fromisoformat(payload['expires_at'])
        draft = parse_water_backfill(source.content, reference_now=reference)
        if (reference.tzinfo is None or expiry.tzinfo is None or expiry != reference + timedelta(minutes=30)
            or now > expiry or now < reference - timedelta(minutes=1)):
            raise WaterBackfillConflict('expired_plan')
        items = payload['items']
        if (payload.get('version') != 1 or payload.get('conversation_id') != source.conversation_id or not draft or not draft.items
            or [{'date': x['date'], 'total_ml': x['total_ml']} for x in items] != list(draft.items)
            or payload.get('date_note') != draft.date_note):
            raise WaterBackfillConflict('invalid_plan')
        for item in items:
            if (type(item['existing_ml']) is not int or item['existing_ml'] < 0
                or type(item['add_ml']) is not int or item['add_ml'] != item['total_ml'] - item['existing_ml']
                or item['add_ml'] < 0):
                raise WaterBackfillConflict('invalid_plan')
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, WaterBackfillConflict):
            raise
        raise WaterBackfillConflict('invalid_plan') from exc
    presented = db.query(AgentMessage).filter(AgentMessage.conversation_id == source.conversation_id,
        AgentMessage.role == 'assistant', AgentMessage.id > source.id).all()
    if not any((msg.meta or {}).get('water_backfill_intent_id') == wi.id
               and (msg.meta or {}).get('water_backfill_plan') == payload
               and (msg.meta or {}).get('client_turn_finalized') is True
               and msg.content == preview_text(wi) for msg in presented):
        raise WaterBackfillConflict('plan_not_presented')


def _receipts(db: Session, wi: WriteIntent) -> list[dict[str, Any]]:
    payload = wi.payload or {}
    receipts = payload.get('write_receipts', [])
    unchanged = [item for item in payload.get('items', []) if item['add_ml'] == 0]
    if unchanged:
        current = _rows(db, wi.user_id, [item['date'] for item in unchanged])
        for item in unchanged:
            baseline = [{'id': row.id, 'amount_ml': row.amount_ml} for row in current[item['date']]]
            if baseline != item['baseline'] or sum(row.amount_ml or 0 for row in current[item['date']]) != item['total_ml']:
                raise WaterBackfillConflict('receipt_changed')
    if len(receipts) != sum(item['add_ml'] > 0 for item in payload.get('items', [])):
        raise WaterBackfillConflict('receipt_changed')
    for receipt in receipts:
        row = db.query(WaterIntake).filter(WaterIntake.id == receipt['resource_id'], WaterIntake.user_id == wi.user_id).first()
        if row is None or row.record_date.isoformat() != receipt['record_date'] or row.amount_ml != receipt['amount_ml']:
            raise WaterBackfillConflict('receipt_changed')
    return receipts


def confirm_water_backfill(db: Session, user_id: int, intent_id: int, *, reference_now: datetime | None = None) -> dict[str, Any]:
    """One short transaction: lock, recheck, add deltas and persist verified receipts."""
    try:
        # A table lock also covers legacy NFC / protocol / event writers that
        # do not participate in per-user locks. It is held for DB work only.
        if db.get_bind().dialect.name == 'postgresql':
            db.execute(text("SET LOCAL lock_timeout = '3s'"))
            db.execute(text('LOCK TABLE water_intakes IN SHARE ROW EXCLUSIVE MODE'))
        wi = db.query(WriteIntent).filter(WriteIntent.id == intent_id, WriteIntent.user_id == user_id,
            WriteIntent.kind == KIND).with_for_update().populate_existing().first()
        if wi is None:
            raise LookupError('write_intent not found')
        if wi.status != 'pending':
            result = {'id': wi.id, 'status': wi.status, 'idempotent': True,
                      'write_receipts': _receipts(db, wi) if wi.status == 'executed' else [],
                      'verified_no_change': wi.status == 'executed' and not wi.payload.get('write_receipts')}
            db.commit()
            return result
        _validate_plan(db, wi, reference_now or get_china_now())
        items = wi.payload['items']
        current = _rows(db, user_id, [item['date'] for item in items])
        for item in items:
            baseline = [{'id': row.id, 'amount_ml': row.amount_ml} for row in current[item['date']]]
            if baseline != item['baseline']:
                raise WaterBackfillConflict('baseline_changed')
        receipts = []
        for item in items:
            if item['add_ml'] == 0:
                continue
            record = WaterIntake(user_id=user_id, record_date=date.fromisoformat(item['date']),
                                 amount_ml=item['add_ml'], drink_type='水', notes='用户确认的全天饮水补记')
            db.add(record)
            db.flush()
            receipts.append({'resource_type': 'water_record', 'resource_id': record.id,
                             'status': 'verified', 'record_date': item['date'], 'amount_ml': item['add_ml'],
                             'operation': 'create', 'success': True, 'verified': True,
                             'operation_id': f'write_intent:{KIND}:{wi.id}:{record.id}',
                             'completed_at': record.created_at.isoformat() if record.created_at else None})
        wi.payload = {**wi.payload, 'write_receipts': receipts}
        wi.status = 'executed'
        wi.decision_status = 'executed'
        wi.decided_at = datetime.now(UTC)
        db.flush()
        verified = _receipts(db, wi)
        db.commit()
        from app.twin.cache import invalidate_twin
        try:
            invalidate_twin(user_id)
        except Exception as exc:
            logger.warning('water backfill cache invalidation failed error_type=%s', type(exc).__name__)
        return {'id': wi.id, 'status': 'executed', 'idempotent': False, 'write_receipts': verified, 'verified_no_change': not verified}
    except Exception:
        db.rollback()
        raise


def is_water_backfill_control(message: str) -> bool:
    return bool(re.fullmatch(r"(?:确认饮水补记\s*\d+|确认|取消|取消饮水补记)", str(message or '').strip()))


def resolve_water_backfill_turn(db: Session, *, user_id: int, source_message_id: int, reference_now: datetime) -> dict[str, Any] | None:
    source = _source(db, user_id, source_message_id)
    message = source.content.strip()
    previous = db.query(AgentMessage).filter(AgentMessage.conversation_id == source.conversation_id,
        AgentMessage.id < source.id).order_by(AgentMessage.id.desc()).first()
    previous_meta = previous.meta or {} if previous is not None and previous.role == 'assistant' else {}
    pending_id = previous_meta.get('water_backfill_intent_id')
    explicit = re.fullmatch(r'确认饮水补记\s*(\d+)', message)
    control_id = int(explicit.group(1)) if explicit else pending_id if is_water_backfill_control(message) else None
    if control_id is not None:
        wi = db.query(WriteIntent).filter(WriteIntent.id == control_id, WriteIntent.user_id == user_id,
            WriteIntent.kind == KIND).first()
        if wi is None or (wi.payload or {}).get('conversation_id') != source.conversation_id:
            return {'status': 'clarification', 'reply': '当前对话没有这份饮水补记计划，请重新提供日期和每天总量。'}
        try:
            if message in {'取消', '取消饮水补记'}:
                from app.services.write_intent_service import dismiss
                result = dismiss(db, user_id, wi.id)
            else:
                result = confirm_water_backfill(db, user_id, wi.id, reference_now=reference_now)
        except OperationalError:
            db.rollback()
            return {'status': 'error', 'reply': '饮水补记暂未取得数据库执行结果，请稍后用同一个确认编号重试；已完成的计划不会重复写入。'}
        except WaterBackfillConflict as exc:
            if str(exc) == 'receipt_changed':
                return {'status': 'error', 'reply': '这份饮水补记此前已处理，但对应的记录或无需补记日期的已有总量发生了变化，当前无法完整核验。请查看饮水记录；我不会自动重复补写。'}
            return {'status': 'clarification', 'reason': str(exc), 'reply': '这份饮水补记计划已过期或已有记录发生变化，尚未执行本次补记。请重新发送日期和每天准确总量，我会重新核对并展示明细。'}
        if result['status'] == 'dismissed':
            return {'status': 'cancelled', 'reply': '已取消这份饮水补记，没有执行补记。'}
        if result['status'] != 'executed':
            return {'status': 'error', 'reply': '饮水补记尚未完成，请查看待确认计划后重试。'}
        rows = wi.payload['items']
        text_rows = [f"{item['date']}：原计划全天目标 {format_display_number(item['total_ml'])}ml，当时补记 {format_display_number(item['add_ml'])}ml。" for item in rows]
        if result.get('verified_no_change'):
            return {'status': 'verified', 'reply': '已核对这些日期的现有记录，均已达到你确认的全天总量，无需新增补记。', 'verified_no_change': True, 'write_receipts': []}
        return {'status': 'verified', 'reply': ('已核验之前的补记增量回执，未重复写入；以下为原计划，不代表当前总量。' if result.get('idempotent') else '饮水补记已完成。') + '\n' + '\n'.join(text_rows),
                'write_receipts': result.get('write_receipts', [])}
    draft = parse_water_backfill(message, reference_now=reference_now)
    if draft is None:
        return None
    if draft.clarification:
        return {'status': 'clarification', 'reply': draft.clarification}
    try:
        wi = propose_water_backfill(db, user_id=user_id, source_message_id=source_message_id, reference_now=reference_now)
    except WaterBackfillConflict:
        db.rollback()
        return {'status': 'clarification', 'reply': '已有日期的饮水记录总量高于你提供的全天总量。请先核对该日记录；本次没有添加或删除饮水记录。'}
    if wi is None:
        raise RuntimeError('recognized water draft has no plan')
    if wi.status != 'pending':
        result = confirm_water_backfill(db, user_id, wi.id, reference_now=reference_now)
        return {'status': 'verified' if result['status'] == 'executed' else 'cancelled',
                'reply': '这份饮水补记已处理，没有重复写入。', 'write_receipts': result.get('write_receipts', [])}
    return {'status': 'pending', 'reply': preview_text(wi), 'intent_id': wi.id, 'plan': wi.payload}
