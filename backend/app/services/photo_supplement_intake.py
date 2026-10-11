"""Owner-bound photo supplement confirmation. No image recognition authorizes writes.

Only persisted, readable owner chat images are supported. All methods own their
transaction and must be called at an isolated request boundary. PostgreSQL row
locks serialize source proposals and definition writes; SQLite is unit-test only.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.write_intent import WriteIntent
from app.services.chat_utils import read_owned_chat_image_data_uri
from app.services.photo_supplement_preview import build_photo_supplement_preview
from app.utils.timezone import get_user_timezone

KIND = 'photo_supplement_intake'


class PhotoSupplementConflict(ValueError):
    """Frozen plan cannot currently be safely confirmed or replayed."""



def _clock():
    return datetime.now(UTC)


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _source(db, user_id, message_id):
    row = db.query(AgentMessage).join(AgentConversation).filter(
        AgentMessage.id == message_id, AgentMessage.role == 'user',
        AgentConversation.user_id == user_id,
    ).with_for_update(of=AgentMessage).first()
    if row is None:
        raise LookupError('source not found')
    return row


def _images(source, user_id):
    raw = source.image_url
    try:
        refs = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        refs = [raw]
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 8 or any(not isinstance(r, str) or not r for r in refs):
        raise PhotoSupplementConflict('unsupported persisted images')
    # The existing reader validates namespace, owner, path traversal and file
    # availability. Its data URI includes content plus media type, not a URL hash.
    return [{'reference': r, 'content_sha256': hashlib.sha256(read_owned_chat_image_data_uri(r, user_id).encode()).hexdigest()} for r in refs]


def propose(db, user_id, source_message_id, candidates, *, now=None):
    now = _utc(now or datetime.now(UTC))
    try:
        source = _source(db, user_id, source_message_id)
        images = _images(source, user_id)
        request_text = source.content
        caption = f"\n[附图: {len(images)}张]"
        if request_text.endswith(caption):
            request_text = request_text[:-len(caption)]
        existing = db.query(WriteIntent).filter_by(user_id=user_id, kind=KIND, target_type='agent_message', target_id=source.id).first()
        if existing:
            _validate_source(db, existing)
            for item in existing.payload['items']:
                definitions = db.query(SupplementDefinition).filter_by(user_id=user_id, name=item['name'], is_active=True).all()
                if (len(definitions) != 1 or definitions[0].id != item['supplement_id']
                        or definitions[0].dosage != item['definition_dosage']
                        or definitions[0].product_id != item['product_id']):
                    raise PhotoSupplementConflict('changed owner definition')
            preview = build_photo_supplement_preview(request_text, candidates)
            frozen = [{'name': i['name'], 'actual_dosage': i['actual_dosage']} for i in existing.payload['items']]
            if preview is None or preview['items'] != frozen:
                raise PhotoSupplementConflict('changed candidate plan')
            db.expunge(existing)
            db.commit()
            return existing
        preview = build_photo_supplement_preview(request_text, candidates)
        if preview is None:
            raise PhotoSupplementConflict('unresolved quantities or candidates')
        items = []
        for item in preview['items']:
            matches = db.query(SupplementDefinition).filter_by(user_id=user_id, name=item['name'], is_active=True).all()
            if len(matches) != 1:
                raise PhotoSupplementConflict('candidate requires unique owner definition')
            items.append({**item, 'supplement_id': matches[0].id,
                          'definition_dosage': matches[0].dosage,
                          'observed_strength': matches[0].dosage,
                          'strength_source': 'supplement_definition',
                          'product_id': matches[0].product_id})
        created = _utc(source.created_at)
        if created > now or now >= created + timedelta(minutes=30):
            raise PhotoSupplementConflict('source expired or future')
        local = created.astimezone(get_user_timezone(db, user_id))
        payload = {'version': 1, 'user_id': user_id, 'source_message_id': source.id,
                   'conversation_id': source.conversation_id, 'source_text': source.content, 'client_turn_id': source.client_turn_id,
                   'images': images, 'source_created_at': created.isoformat(),
                   'local_datetime': local.isoformat(), 'record_date': local.date().isoformat(),
                   'taken_time': local.time().isoformat(), 'expires_at': (created + timedelta(minutes=30)).isoformat(),
                   'items': items, 'candidate_count': len(items)}
        payload['plan_sha256'] = _hash(payload)
        wi = WriteIntent(user_id=user_id, kind=KIND, title='确认补剂记录', status='pending',
                         trust_tier='manual_confirm', source='photo_supplement_preview',
                         target_type='agent_message', target_id=source.id, payload=payload)
        db.add(wi); db.flush(); db.expunge(wi); db.commit()
        return wi
    except Exception:
        db.rollback()
        raise


def build_card(intent):
    """Caller must durably store this exact object in assistant meta.cards."""
    p = intent.payload
    from app.services.atomic_capability_registry import attach_action_policy_metadata

    card = {'type': 'supplement_draft', 'data': {
        'supplement_name': '、'.join(item['name'] for item in p['items']),
        'write_intent_id': intent.id, 'plan_sha256': p['plan_sha256'],
        'source_message_id': p['source_message_id'], 'source': 'photo',
        'items': [{**item, 'supplement_name': item['name']} for item in p['items']], 'record_date': p['record_date'], 'taken_date': p['record_date'], 'decision_status': 'pending',
        'taken_time': p['taken_time'], 'expires_at': p['expires_at'],
        'presentation_state': 'pending', 'requires_confirmation': True,
    }, 'actions': [
        {'id': f'photo-supplement-confirm:{intent.id}', 'action': 'write_intent.confirm', 'label': '确认记录', 'style': 'primary', 'endpoint': f'/write-intents/{intent.id}/confirm', 'requires_manual_confirm': True, 'payload': {'write_intent_id': intent.id}},
        {'id': f'photo-supplement-dismiss:{intent.id}', 'action': 'write_intent.dismiss', 'label': '取消', 'style': 'secondary', 'endpoint': f'/write-intents/{intent.id}/dismiss', 'requires_manual_confirm': True, 'payload': {'write_intent_id': intent.id}},
    ]}
    card['actions'] = attach_action_policy_metadata('supplement_draft', card['actions'])
    return card


def _intent(db, user_id, intent_id):
    wi = db.query(WriteIntent).filter_by(id=intent_id, user_id=user_id, kind=KIND).populate_existing().with_for_update().first()
    if wi is None:
        raise LookupError('intent not found')
    return wi


def _result(wi, *, replay=False):
    return {'id': wi.id, 'status': wi.decision_status or wi.status,
            'idempotent': replay, 'write_receipts': copy.deepcopy((wi.payload or {}).get('write_receipts', []))}


def _validate_source(db, wi):
    p = wi.payload
    if not isinstance(p, dict):
        raise PhotoSupplementConflict('invalid plan')
    frozen = {k: v for k, v in p.items() if k not in ('plan_sha256', 'write_receipts')}
    if _hash(frozen) != p.get('plan_sha256') or p.get('user_id') != wi.user_id or wi.trust_tier != 'manual_confirm':
        raise PhotoSupplementConflict('plan integrity failure')
    source = _source(db, wi.user_id, wi.target_id)
    if (source.id != p['source_message_id'] or source.conversation_id != p['conversation_id']
            or source.content != p['source_text'] or source.client_turn_id != p.get('client_turn_id') or _utc(source.created_at).isoformat() != p['source_created_at']
            or _images(source, wi.user_id) != p['images']):
        raise PhotoSupplementConflict('source changed')
    return source


def _validate(db, wi):
    source = _validate_source(db, wi)
    if not source.client_turn_id:
        raise PhotoSupplementConflict('plan not durably presented with turn identity')
    expected = build_card(wi)
    assistants = db.query(AgentMessage).filter_by(conversation_id=source.conversation_id, role='assistant').order_by(AgentMessage.id).all()
    presented = [a for a in assistants if a.id > source.id and a.client_turn_id == source.client_turn_id
                 and isinstance(a.meta, dict) and a.meta.get('client_turn_finalized') is True
                 and a.meta.get('completion_status') == 'complete'
                 and expected in (a.meta.get('cards') or [])]
    if not presented:
        raise PhotoSupplementConflict('plan not durably presented')
    return presented


def _project(assistants, wi):
    for assistant in assistants:
        meta = copy.deepcopy(assistant.meta or {})
        for card in meta.get('cards', []):
            if card.get('type') == 'supplement_draft' and card.get('data', {}).get('write_intent_id') == wi.id:
                card['data']['presentation_state'] = wi.decision_status or wi.status
                card['data']['decision_status'] = wi.decision_status or wi.status
                card['data']['write_receipts'] = copy.deepcopy(wi.payload.get('write_receipts', []))
                card['actions'] = []
        # Preserve all narrative and unrelated operations in composite turns.
        # The exact draft card is the terminal projection for this intent.
        receipts = copy.deepcopy(meta.get('write_receipts', []))
        if not isinstance(receipts, list):
            raise PhotoSupplementConflict('invalid assistant receipt projection')
        for receipt in wi.payload.get('write_receipts', []):
            found = [r for r in receipts if isinstance(r, dict) and r.get('operation_id') == receipt['operation_id']]
            if found and any(r != receipt for r in found):
                raise PhotoSupplementConflict('conflicting assistant receipt projection')
            if not found:
                receipts.append(copy.deepcopy(receipt))
        meta['write_receipts'] = receipts
        pending_ids = meta.get('pending_write_intent_ids') or []
        pending_kinds = meta.get('pending_write_intent_kinds') or []
        remaining = [(value, pending_kinds[index] if index < len(pending_kinds) else None)
                     for index, value in enumerate(pending_ids) if str(value) != str(wi.id)]
        meta['pending_write_intent_ids'] = [value for value, _ in remaining]
        meta['pending_write_intent_kinds'] = [kind for _, kind in remaining]
        if not remaining and meta.get('mode') == KIND:
            from app.services.agent_turn_outcome import classify_agent_turn_outcome, agent_completion_metadata
            terminal_text = '补剂已记录。' if wi.status == 'executed' else '本次补剂确认已结束，没有写入记录。'
            outcome = classify_agent_turn_outcome(completion_status='complete', final_text=terminal_text,
                                                   write_receipts=receipts)
            meta['turn_outcome'] = outcome
            meta.update(agent_completion_metadata('complete', outcome))
        assistant.meta = meta



def _verify_receipts(db, wi):
    if wi.status != 'executed':
        return
    p = wi.payload or {}
    frozen = {k: v for k, v in p.items() if k not in ('plan_sha256', 'write_receipts')}
    receipts = p.get('write_receipts')
    items = p.get('items', [])
    if (_hash(frozen) != p.get('plan_sha256') or not isinstance(receipts, list)
            or len(receipts) != len(items) or not items):
        raise PhotoSupplementConflict('receipt integrity failure')
    for item, receipt in zip(items, receipts):
        try:
            record_id = int(receipt['resource_id'])
        except (TypeError, ValueError, KeyError) as exc:
            raise PhotoSupplementConflict('receipt invalid id') from exc
        row = db.query(SupplementRecord).filter_by(id=record_id, user_id=wi.user_id).with_for_update().first()
        if (row is None or row.supplement_id != item['supplement_id']
                or row.record_date.isoformat() != p['record_date'] or row.taken is not True
                or row.actual_dosage != item['actual_dosage']
                or row.taken_time is None or row.taken_time.isoformat() != p['taken_time']
                or receipt.get('supplement_id') != row.supplement_id
                or receipt.get('record_date') != p['record_date']
                or receipt.get('actual_dosage') != item['actual_dosage']
                or receipt.get('taken') is not True or receipt.get('verified') is not True
                or receipt.get('status') != 'verified' or receipt.get('action') != 'create'
                or receipt.get('resource_type') != 'supplement_record'
                or receipt.get('operation_id') != f'write_intent:{KIND}:{wi.id}:{row.id}'):
            raise PhotoSupplementConflict('receipt no longer matches persisted record')

def _lock_runtime_admission(db, user_id):
    """Keep the existing circuit lock until this intake transaction finishes."""
    from sqlalchemy.exc import SQLAlchemyError
    from app.services.agent_runtime_rollout import (
        AgentRuntimeRolloutService, RolloutConfigurationError,
    )
    rollout = AgentRuntimeRolloutService(db)
    try:
        selection = rollout._selection_decision(user_id)
        if not selection.managed:
            return
        state = rollout._locked_state()
        # API callers may already have loaded the singleton before another
        # transaction paused it. Refresh only after acquiring its row lock.
        db.refresh(state)
        decision = rollout.admission_decision(user_id)
        if not decision.managed:
            raise PhotoSupplementConflict('runtime write admission blocked')
    except (SQLAlchemyError, RolloutConfigurationError) as exc:
        raise PhotoSupplementConflict('runtime write admission unavailable') from exc


def confirm(db, user_id, intent_id, *, now=None):
    try:
        wi = _intent(db, user_id, intent_id)
        if wi.status != 'pending':
            _verify_receipts(db, wi)
            result = _result(wi, replay=True)
            db.commit()
            return result
        _lock_runtime_admission(db, user_id)
        assistants = _validate(db, wi)
        p = wi.payload
        # Lock definitions in ID order, serializing competing plans for the same
        # supplement/date even before a record row exists.
        ids = sorted(i['supplement_id'] for i in p['items'])
        defs = db.query(SupplementDefinition).filter(SupplementDefinition.id.in_(ids), SupplementDefinition.user_id == user_id).order_by(SupplementDefinition.id).with_for_update(of=SupplementDefinition).all()
        by_id = {d.id: d for d in defs}
        for item in p['items']:
            d = by_id.get(item['supplement_id'])
            if (d is None or not d.is_active or d.name != item['name']
                    or d.dosage != item['definition_dosage'] or d.product_id != item['product_id']):
                raise PhotoSupplementConflict('definition changed')
        now = _utc(now if now is not None else _clock())
        if now >= datetime.fromisoformat(p['expires_at']):
            wi.status, wi.decision_status, wi.decided_at = 'dismissed', 'expired', now
            _project(assistants, wi)
            result = _result(wi)
            db.commit()
            return result
        record_date = date.fromisoformat(p['record_date'])
        if db.query(SupplementRecord).filter(SupplementRecord.supplement_id.in_(ids), SupplementRecord.record_date == record_date).first():
            raise PhotoSupplementConflict('existing daily record requires separate correction')
        affected = db.query(WriteIntent).filter_by(id=wi.id, user_id=user_id, kind=KIND, status='pending').update({'status': 'executed', 'decision_status': 'executed', 'decided_at': now}, synchronize_session=False)
        if affected != 1:
            raise PhotoSupplementConflict('intent already claimed')
        receipts = []
        for item in p['items']:
            row = SupplementRecord(user_id=user_id, supplement_id=item['supplement_id'], record_date=record_date,
                                   taken=True, taken_time=time.fromisoformat(p['taken_time']), actual_dosage=item['actual_dosage'])
            db.add(row); db.flush()
            receipts.append({'operation_id': f'write_intent:{KIND}:{wi.id}:{row.id}', 'status': 'verified',
                             'resource_type': 'supplement_record', 'resource_id': str(row.id), 'verified': True,
                             'action': 'create', 'completed_at': now.isoformat(), 'supplement_id': row.supplement_id,
                             'record_date': record_date.isoformat(), 'taken': True, 'actual_dosage': row.actual_dosage})
        wi.status, wi.decision_status, wi.decided_at = 'executed', 'executed', now
        wi.payload = {**p, 'write_receipts': receipts}
        wi.executed_ref = ','.join(r['resource_id'] for r in receipts)
        _project(assistants, wi)
        result = _result(wi)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def dismiss(db, user_id, intent_id, *, now=None):
    try:
        wi = _intent(db, user_id, intent_id)
        if wi.status != 'pending':
            _verify_receipts(db, wi)
            result = _result(wi, replay=True)
            db.commit()
            return result
        assistants = _validate(db, wi)
        wi.status, wi.decision_status = 'dismissed', 'dismissed'
        wi.decided_at = _utc(now or datetime.now(UTC))
        _project(assistants, wi)
        result = _result(wi)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
