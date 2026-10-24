"""Fail-closed, content-free proof for selective mixed-intake retry.

Only the executor may attest item/fingerprint correspondence after authorization.
This module never infers no side effect from a missing receipt or a failed status.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone as utc_timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.intake_plan import parse_intake_plan


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def build_intake_retry_plan(*, source_text: str, owner_id: int, conversation_id: int,
                            source_message_id: int, local_date: str, timezone: str,
                            item_fingerprints: list[str]) -> dict[str, Any] | None:
    """Seal an exhaustive authorized item mapping; do not pass guessed mappings."""
    plan = parse_intake_plan(source_text)
    if plan.status != 'complete' or len({i.record_type for i in plan.items}) < 2:
        return None
    if any(type(i) is not int or i <= 0 for i in (owner_id, conversation_id, source_message_id)):
        return None
    if (not isinstance(item_fingerprints, list) or len(item_fingerprints) != len(plan.items)
            or any(not isinstance(fp, str) or not fp for fp in item_fingerprints)
            or len(set(item_fingerprints)) != len(item_fingerprints)):
        return None
    try:
        if date.fromisoformat(local_date).isoformat() != local_date:
            return None
        ZoneInfo(timezone)
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return None
    return {
        'version': 1, 'sealed': True, 'owner_id': owner_id,
        'conversation_id': conversation_id, 'source_message_id': source_message_id,
        'source_sha256': hashlib.sha256(source_text.encode()).hexdigest(),
        'plan_digest': _digest([{'index': n, 'record_type': i.record_type,
                                'source_span': i.source_span,
                                'canonical_sha256': hashlib.sha256(i.canonical_text.encode()).hexdigest()}
                               for n, i in enumerate(plan.items)]),
        'local_date': local_date, 'timezone': timezone,
        'items': [{'item_index': n, 'fingerprint': fp} for n, fp in enumerate(item_fingerprints)],
    }


@dataclass(frozen=True)
class IntakeRetrySelection:
    message: str
    item_indexes: tuple[int, ...]
    plan_digest: str
    local_date: str
    timezone: str


def resolve_intake_retry_selection(*, source_text: str, owner_id: int,
                                   conversation_id: int, source_message_id: int,
                                   meta: Any, now: datetime | None = None) -> IntakeRetrySelection | None:
    if not isinstance(meta, dict):
        return None
    checkpoint = meta.get('intake_retry_plan')
    if not isinstance(checkpoint, dict):
        return None
    items = checkpoint.get('items')
    if (type(checkpoint.get('version')) is not int or checkpoint.get('sealed') is not True
            or not isinstance(items, list)
            or not all(isinstance(i, dict) and type(i.get('item_index')) is int for i in items)):
        return None
    expected = build_intake_retry_plan(
        source_text=source_text, owner_id=owner_id, conversation_id=conversation_id,
        source_message_id=source_message_id, local_date=checkpoint.get('local_date'),
        timezone=checkpoint.get('timezone'), item_fingerprints=[i.get('fingerprint') for i in items],
    )
    if expected is None or checkpoint != expected:
        return None
    current = now if now is not None else datetime.now(utc_timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        return None
    if current.astimezone(ZoneInfo(checkpoint['timezone'])).date().isoformat() != checkpoint['local_date']:
        return None
    fingerprints = [i['fingerprint'] for i in items]
    operations, write_plan, receipts = (meta.get('write_operations'), meta.get('write_plan'), meta.get('write_receipts'))
    if (not isinstance(operations, dict) or set(operations) != set(fingerprints)
            or not isinstance(write_plan, dict) or write_plan.get('sealed') is not True
            or not isinstance(write_plan.get('fingerprints'), list)
            or sorted(write_plan['fingerprints'], key=str) != sorted(fingerprints)
            or not isinstance(receipts, list)):
        return None
    receipt_ids = []
    for receipt in receipts:
        if (not isinstance(receipt, dict) or receipt.get('verified') is not True
                or not isinstance(receipt.get('operation_id'), str) or not receipt['operation_id']):
            return None
        receipt_ids.append(receipt['operation_id'])
    if len(set(receipt_ids)) != len(receipt_ids):
        return None
    verified_ids, pending = [], []
    for i in items:
        operation = operations[i['fingerprint']]
        if not isinstance(operation, dict):
            return None
        if operation.get('status') == 'verified':
            rid = operation.get('receipt_operation_id')
            if rid not in receipt_ids or operation.get('no_side_effect') is True:
                return None
            verified_ids.append(rid)
        elif (operation.get('status') in {'planned', 'rejected', 'failed'}
              and operation.get('no_side_effect') is True
              and not operation.get('receipt_operation_id')):
            pending.append(i['item_index'])
        else:
            return None
    if sorted(verified_ids) != sorted(receipt_ids) or not pending or not verified_ids:
        return None
    plan = parse_intake_plan(source_text)
    return IntakeRetrySelection('记录' + '，'.join(plan.items[i].canonical_text.removeprefix('记录补剂').removeprefix('记录饮食') for i in pending),
                                tuple(pending), checkpoint['plan_digest'],
                                checkpoint['local_date'], checkpoint['timezone'])
