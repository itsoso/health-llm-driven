"""Numeric projection of an executed medical read; never parse clinical prose."""
from __future__ import annotations

import json
import math
from datetime import date
from typing import Any

from app.services.agent_write_outcome import result_declares_explicit_failure
from app.utils.number_format import format_display_number

SCHEMA = 'medical-readout.v1'
SOURCE_NOTE = '已存录入值，未核验原始报告'
_ALLOWED_QUERY_KEYS = {'dimension', 'days', 'indicator', 'keyword'}


def _text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return None
    if any(c in value for c in '\n\r\t`{}[]<>'):
        return None
    return value.strip()


def _finite(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def medical_readout_query(args: dict) -> dict | None:
    if set(args) - _ALLOWED_QUERY_KEYS or args.get('dimension') != 'medical_exam':
        return None
    days = args.get('days', 7)
    if type(days) is not int or not 1 <= days <= 3650:
        return None
    indicator, keyword = args.get('indicator', ''), args.get('keyword', '')
    if not isinstance(indicator, str) or not isinstance(keyword, str):
        return None
    return {'days': days, 'indicator': indicator.strip(), 'keyword': keyword.strip()}


def _valid_item(item: Any, since: date, reference: date) -> bool:
    if not isinstance(item, dict) or not _text(item.get('name'), 100) or not _finite(item.get('value')):
        return False
    unit = item.get('unit')
    if unit not in ('', None) and not _text(unit, 30):
        return False
    try:
        day = date.fromisoformat(item['record_date'])
    except (KeyError, TypeError, ValueError):
        return False
    if not since <= day <= reference:
        return False
    return all(item.get(k) is None or _finite(item[k]) for k in ('reference_low', 'reference_high'))


def serialize_medical_readout(summary: str, rows, *, days, indicator: str, keyword: str,
                              since: date, reference_date: date) -> str:
    """Opt-in envelope from the same owner-scoped ORM rows used in summary.

    Invalid/non-numeric rows remain available in the original clinical summary;
    they cannot become numeric facts. No additional query or range expansion.
    """
    query = medical_readout_query({'dimension': 'medical_exam', 'days': days, 'indicator': indicator, 'keyword': keyword})
    if query is None or (reference_date-since).days != max(query['days'], 365):
        return summary
    items = []
    for row in rows:
        item = {k: getattr(row, k) for k in ('name', 'value', 'unit', 'reference_low', 'reference_high')}
        item['record_date'] = row.record_date.isoformat() if row.record_date else None
        if _valid_item(item, since, reference_date):
            items.append(item)
    if not items:
        return summary
    return json.dumps({
        'schema': SCHEMA, 'status': 'success', 'summary': summary,
        'readout': {'query': query, 'since': since.isoformat(),
                    'reference_date': reference_date.isoformat(),
                    'window_days': (reference_date-since).days, 'items': items},
    }, ensure_ascii=False, allow_nan=False)


def medical_readout_rows(payload: Any, args: dict) -> tuple[list[dict], str] | None:
    """Validate the envelope against executed args before rendering existing UI."""
    if (not isinstance(payload, dict) or payload.get('schema') != SCHEMA
            or payload.get('status') != 'success' or result_declares_explicit_failure(payload)
            or any(payload.get(k) for k in ('truncated', 'has_more', 'next_cursor'))
            or not isinstance(payload.get('summary'), str)):
        return None
    query = medical_readout_query(args)
    data = payload.get('readout')
    if query is None or not isinstance(data, dict) or data.get('query') != query:
        return None
    try:
        since = date.fromisoformat(data['since'])
        reference = date.fromisoformat(data['reference_date'])
    except (KeyError, TypeError, ValueError):
        return None
    window_days = max(query['days'], 365)
    if data.get('window_days') != window_days or (reference-since).days != window_days:
        return None
    items = data.get('items')
    if not isinstance(items, list) or not items or not all(_valid_item(item, since, reference) for item in items):
        return None
    rows = []
    for item in items[:12]:
        day = date.fromisoformat(item['record_date'])
        notes = [day.isoformat()]
        if (reference-day).days > 180:
            notes.append('较旧')
        low, high = item.get('reference_low'), item.get('reference_high')
        if low is not None and high is not None:
            notes.append(f'录入参考 {format_display_number(low)}–{format_display_number(high)}')
        elif low is not None:
            notes.append(f'录入参考下限 {format_display_number(low)}')
        elif high is not None:
            notes.append(f'录入参考上限 {format_display_number(high)}')
        notes.append(SOURCE_NOTE)
        rows.append({'metric': item['name'].strip(),
                     'value': f"{format_display_number(item['value'])} {item.get('unit') or ''}".strip(),
                     'note': ' · '.join(notes)})
    note = (f'查询窗口 {since.isoformat()} 至 {reference.isoformat()}（{window_days}天）；'
            f'展示 {len(rows)}/{len(items)} 条可展示数值，非完整报告 · 参考值非诊断')
    return rows, note
