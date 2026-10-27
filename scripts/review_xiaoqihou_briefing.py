"""Fresh Xiaoqihou demo conversation; never updates or deletes existing rows.

The canonical operator supplies locks, live exact revision, CI, historical
closure and separately authorized intent. This module grants no authority.
"""
import hashlib
import importlib.util
import json
import os
import re
from datetime import datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location('xiaoqihou_readonly_rows', Path(__file__).with_name('review_demo_briefing_repair.py'))
rows = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rows)
RepairError = rows.RepairError
digest = rows.digest
_rows = rows._rows
_tables = rows._tables
TARGET = '8f7d94696424f92ff57243edb906cd6d2dd14a3a'
FIXTURE_SHA256 = '40263013f3b91292e997343f535a45520ec9c28c979e5410530f0f11c0beed14'
SESSION_KEY = 'app-store-review-demo-xiaoqihou-v1'
ACTION = 'INSERT_XIAOQIHOU_FIXED_BRIEFING_ONLY_V1'

def validate_evidence(value):
    required = {'target_sha', 'fixture_sha256',
                'legacy_closure_sha256', 'database_snapshot_sha256', 'production_evidence_sha256',
                'health_snapshot_sha256', 'demo_user_id', 'action', 'ordering_metadata_plan'}
    if (not isinstance(value, dict) or set(value) != required
            or value['target_sha'] != TARGET
            or type(value['demo_user_id']) is not int or value['demo_user_id'] < 1
            or value['fixture_sha256'] != FIXTURE_SHA256 or value['action'] != ACTION
            or any(re.fullmatch('[a-f0-9]{64}', value[k] or '') is None
                   for k in ('legacy_closure_sha256', 'database_snapshot_sha256',
                             'production_evidence_sha256', 'health_snapshot_sha256'))):
        raise RepairError('exact reviewed repair evidence required')
    validate_ordering_plan(value['ordering_metadata_plan'])


def repair(adapter, *, authorized=False, evidence_sha256=None):
    if os.path.lexists(adapter.record):
        raise RepairError('repair already attempted; no retry authority')
    evidence = adapter.inspect()
    validate_evidence(evidence)
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {'state': 'INSPECTED_NOT_AUTHORIZED', 'evidence_sha256': fingerprint}
    if authorized is not True or fingerprint != evidence_sha256:
        raise RepairError('separate explicit repair authority and fresh evidence required')
    adapter.prepare_record()
    adapter.write('intent.json', {'evidence': evidence, 'evidence_sha256': fingerprint})
    if adapter.inspect() != evidence:
        raise RepairError('evidence changed after intent')
    # Adapter must commit only its reviewed narrow transaction once. Any
    # exception (including lost commit response) leaves the intent, never retries.
    result = adapter.apply_once(evidence)
    if (not isinstance(result, dict) or set(result) != {'state', 'before_sha256', 'after_sha256'}
            or result['state'] != 'VERIFIED_BRIEFING_ONLY'
            or result['before_sha256'] != evidence['database_snapshot_sha256']
            or re.fullmatch('[a-f0-9]{64}', result['after_sha256'] or '') is None):
        raise RepairError('fresh transaction verification unavailable')
    terminal = {'state': 'BRIEFING_REPAIRED_ONLY', 'evidence_sha256': fingerprint,
                'result': result, 'original_outcome': 'UNKNOWN', 'reset_authorized': False,
                'release_unblocked': False, 'retry_authorized': False}
    adapter.write('completed.json', terminal)
    return terminal

def empty_ordering_plan():
    return {'action': 'PRESERVE_ALL_EXISTING_ROWS', 'rows': []}


def validate_ordering_plan(plan):
    if plan != empty_ordering_plan():
        raise RepairError('existing rows cannot be changed')


def _ordering_plan(connection, snapshot):
    from sqlalchemy import text
    _, convs, _ = _tables()
    # Check globally for an identifier collision without exposing other owners.
    if connection.execute(text(f'SELECT EXISTS (SELECT 1 FROM {convs} WHERE session_key=:key)'),
                          {'key':SESSION_KEY}).scalar_one():
        raise RepairError('fixed session key already exists; no retry')
    dtype=connection.execute(text("SELECT format_type(atttypid,atttypmod) FROM pg_attribute "
        "WHERE attrelid=to_regclass(:table) AND attname='updated_at' AND NOT attisdropped"), {'table':convs}).scalar_one()
    if dtype != 'timestamp without time zone':
        raise RepairError('fixed UTC-naive timestamp required')
    now=connection.execute(text("SELECT timezone('UTC',clock_timestamp())")).scalar_one()
    for row in snapshot['conversations']:
        try:
            moment=datetime.fromisoformat(row['updated_at'])
        except (KeyError, TypeError, ValueError):
            raise RepairError('invalid previous ordering timestamp') from None
        if moment.tzinfo is not None or moment >= now:
            raise RepairError('existing timestamp cannot be superseded without modification')
    return empty_ordering_plan()


def inspect_briefing_metadata(connection, email, expected_user_id):
    """Read-only explicit plan plus exact owner/chat snapshot digest."""
    connection.exec_driver_sql('SET TRANSACTION READ ONLY')
    snapshot=_rows(connection,email,expected_user_id)
    return {'database_snapshot_sha256':digest(snapshot),
            'ordering_metadata_plan':_ordering_plan(connection,snapshot)}


def _validate_absent_and_time(connection, snapshot):
    # Legacy read-only entry never silently opts into metadata correction.
    if _ordering_plan(connection,snapshot)['rows']:
        raise RepairError('existing ordering time cannot be safely superseded')


def inspect_briefing_rows(connection, email, expected_user_id):
    """Read-only snapshot hash. Never returns message content or identity fields."""
    connection.exec_driver_sql('SET TRANSACTION READ ONLY')
    snapshot = _rows(connection, email, expected_user_id)
    _validate_absent_and_time(connection, snapshot)
    return digest(snapshot)


def create_briefing_rows(connection, email, expected_user_id, expected_snapshot_sha256, fixture_path, *, ordering_metadata_plan=None):
    """One transaction body, no commit/retry. Caller owns durable intent and gates.

    The canonical adapter must independently pin demo identity, CI/source/locks,
    audit acknowledgement and health-table invariants. This function cannot
    claim durable success until the caller commits and performs readback.
    """
    from sqlalchemy import text
    raw = fixture_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise RepairError('fixed fixture bytes changed')
    fixture = json.loads(raw)['agent_conversation']
    before = _rows(connection, email, expected_user_id, lock=True)
    if digest(before) != expected_snapshot_sha256:
        raise RepairError('review account snapshot changed')
    expected_plan=empty_ordering_plan() if ordering_metadata_plan is None else ordering_metadata_plan
    validate_ordering_plan(expected_plan)
    if _ordering_plan(connection,before)!=expected_plan:
        raise RepairError('ordering metadata plan changed or not explicitly authorized')
    _, convs, messages = _tables()
    # Both timestamp columns are UTC-naive in the deployed schema; never bind
    # aware timestamps whose conversion would depend on the session timezone.
    expected_preserved=json.loads(json.dumps(before))
    now = connection.execute(text("SELECT timezone('UTC', clock_timestamp())")).scalar_one()
    if any(datetime.fromisoformat(c['updated_at']) >= now for c in before['conversations']):
        raise RepairError('database clock changed before insertion')
    cid = connection.execute(text(f'INSERT INTO {convs} (user_id,title,session_key,created_at,updated_at) '
        'VALUES (:uid,:title,:key,:now,:now) RETURNING id'),
        {'uid': expected_user_id, 'title': fixture['title_prefix'] + ' · 审核演示', 'key': SESSION_KEY, 'now': now}).scalar_one()
    mids = []
    for role, field in [('user', 'user_message'), ('assistant', 'assistant_message')]:
        mids.append(connection.execute(text(f'INSERT INTO {messages} (conversation_id,role,content,created_at) '
            'VALUES (:cid,:role,:content,:now) RETURNING id'),
            {'cid': cid, 'role': role, 'content': fixture[field], 'now': now}).scalar_one())
    after = _rows(connection, email, expected_user_id, lock=True)
    preserved = {'owner': after['owner'],
        'conversations': [c for c in after['conversations'] if c['id'] != cid],
        'messages': [m for m in after['messages'] if m['id'] not in mids]}
    if preserved != expected_preserved:
        raise RepairError('existing review rows changed')
    new_convs = [c for c in after['conversations'] if c['id'] == cid]
    new_messages = [m for m in after['messages'] if m['id'] in mids]
    if (len(new_convs) != 1 or len(new_messages) != 2
            or [(m['role'], m['content']) for m in new_messages] != [
                ('user', fixture['user_message']), ('assistant', fixture['assistant_message'])]
            or any(m['conversation_id'] != cid or m.get('image_url') is not None or m.get('meta') is not None for m in new_messages)
            or connection.execute(text(f'SELECT id FROM {convs} WHERE user_id=:uid ORDER BY updated_at DESC LIMIT 1'),
                {'uid': expected_user_id}).scalar_one() != cid):
        raise RepairError('new fixed briefing verification failed')
    return {'state': 'VERIFIED_BRIEFING_ONLY', 'before_sha256': expected_snapshot_sha256,
            'after_sha256': digest(after)}


def verify_created_briefing_rows(connection, email, expected_user_id, expected_after_sha256, fixture_path):
    """Fresh read-only post-commit reconciliation; grants no retry authority."""
    from sqlalchemy import text
    connection.exec_driver_sql('SET TRANSACTION READ ONLY')
    raw = fixture_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise RepairError('fixed fixture bytes changed')
    fixture = json.loads(raw)['agent_conversation']
    current = _rows(connection, email, expected_user_id)
    if digest(current) != expected_after_sha256:
        raise RepairError('post-commit review snapshot changed')
    conversations = [c for c in current['conversations'] if c.get('session_key') == SESSION_KEY]
    if len(conversations) != 1:
        raise RepairError('unique fixed briefing absent')
    cid = conversations[0]['id']
    messages = [m for m in current['messages'] if m['conversation_id'] == cid]
    _, convs, _ = _tables()
    if ([(m['role'], m['content']) for m in messages] != [('user', fixture['user_message']), ('assistant', fixture['assistant_message'])]
            or any(m.get('image_url') is not None or m.get('meta') is not None for m in messages)
            or connection.execute(text(f'SELECT id FROM {convs} WHERE user_id=:uid ORDER BY updated_at DESC LIMIT 1'),
                {'uid': expected_user_id}).scalar_one() != cid):
        raise RepairError('post-commit fixed briefing is not exact default')
    return {'state': 'VERIFIED_BRIEFING_ONLY', 'after_sha256': expected_after_sha256}
