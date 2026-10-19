"""Transaction core for separately reviewed Store 279 briefing repair.

No CLI, credentials or standalone production authority. PostgreSQL writes
require a canonical adapter and a separately authorized durable intent.
A canonical adapter must supply lock/CI/account/receipt checks before this can
be used. UNKNOWN acknowledgement is evidence, never repair authorization.
"""
import hashlib
import json
import os
import re

TARGET = '1ba724dcb62ac389a72e41eecf40fea7aaca27e3'
FAILED_OPERATION = 'a71c3840b6f24bc79937d178cb838066'
FIXTURE_SHA256 = '40263013f3b91292e997343f535a45520ec9c28c979e5410530f0f11c0beed14'
ACTION = 'FIXED_REVIEW_BRIEFING_ONLY'


class RepairError(Exception):
    """Static diagnostics, without account content."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_evidence(value):
    required = {'target_sha', 'failed_operation', 'fixture_sha256',
                'acknowledgement_sha256', 'database_snapshot_sha256', 'production_evidence_sha256',
                'health_snapshot_sha256', 'demo_user_id', 'action'}
    if (not isinstance(value, dict) or set(value) != required
            or value['target_sha'] != TARGET or value['failed_operation'] != FAILED_OPERATION
            or type(value['demo_user_id']) is not int or value['demo_user_id'] < 1
            or value['fixture_sha256'] != FIXTURE_SHA256 or value['action'] != ACTION
            or any(re.fullmatch('[a-f0-9]{64}', value[k] or '') is None
                   for k in ('acknowledgement_sha256', 'database_snapshot_sha256',
                             'production_evidence_sha256', 'health_snapshot_sha256'))):
        raise RepairError('exact reviewed repair evidence required')


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

# Not configurable through an executable interface. Tests substitute an isolated
# schema; the future canonical production adapter must verify this equals public.
SCHEMA = 'public'
SESSION_KEY = 'app-store-review-demo-279'


def _tables():
    if re.fullmatch('[a-z][a-z0-9_]*', SCHEMA) is None:
        raise RepairError('invalid fixed schema')
    return tuple(f'{SCHEMA}.{name}' for name in ('users', 'agent_conversations', 'agent_messages'))


def _rows(connection, email, expected_user_id, *, lock=False):
    from sqlalchemy import text
    if (connection.dialect.name != 'postgresql' or type(expected_user_id) is not int
            or expected_user_id < 1 or not isinstance(email, str) or not email):
        raise RepairError('fixed PostgreSQL review identity required')
    if connection.exec_driver_sql('SHOW transaction_isolation').scalar_one() != 'serializable':
        raise RepairError('serializable transaction required')
    connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
    connection.exec_driver_sql("SET LOCAL lock_timeout = '2000ms'")
    users, convs, messages = _tables()
    suffix = ' FOR UPDATE' if lock else ''
    owner = connection.execute(text(f'SELECT to_jsonb(u) FROM {users} u WHERE id=:id AND email=:email' + suffix),
                               {'id': expected_user_id, 'email': email}).scalars().all()
    if (len(owner) != 1 or owner[0].get('is_active') is not True
            or owner[0].get('is_approved') is not True or owner[0].get('is_admin') is not False):
        raise RepairError('exact active non-admin review identity required')
    conversations = connection.execute(text(f'SELECT to_jsonb(c) FROM {convs} c WHERE user_id=:id ORDER BY id LIMIT 1001' + suffix),
                                       {'id': expected_user_id}).scalars().all()
    if len(conversations) > 1000:
        raise RepairError('review conversation bound exceeded')
    rows = connection.execute(text(f'SELECT to_jsonb(m) FROM {messages} m WHERE conversation_id IN '
        f'(SELECT id FROM {convs} WHERE user_id=:id) ORDER BY id LIMIT 10001' + suffix), {'id': expected_user_id}).scalars().all()
    snapshot = {'owner': owner[0], 'conversations': conversations, 'messages': rows}
    if len(rows) > 10000 or len(json.dumps(snapshot)) > 16_000_000:
        raise RepairError('review snapshot bound exceeded')
    return snapshot


def _validate_absent_and_time(connection, snapshot):
    from sqlalchemy import text
    if any(c.get('session_key') == SESSION_KEY for c in snapshot['conversations']):
        raise RepairError('fixed briefing already exists; no replay')
    _, convs, _ = _tables()
    if connection.execute(text(f"SELECT EXISTS (SELECT 1 FROM {convs} WHERE user_id=:id AND "
        "(updated_at IS NULL OR updated_at >= timezone('UTC', clock_timestamp())))"),
        {'id': snapshot['owner']['id']}).scalar_one():
        raise RepairError('existing ordering time cannot be safely superseded')


def inspect_briefing_rows(connection, email, expected_user_id):
    """Read-only snapshot hash. Never returns message content or identity fields."""
    connection.exec_driver_sql('SET TRANSACTION READ ONLY')
    snapshot = _rows(connection, email, expected_user_id)
    _validate_absent_and_time(connection, snapshot)
    return digest(snapshot)


def create_briefing_rows(connection, email, expected_user_id, expected_snapshot_sha256, fixture_path):
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
    _validate_absent_and_time(connection, before)
    _, convs, messages = _tables()
    # Both timestamp columns are UTC-naive in the deployed schema; never bind
    # aware timestamps whose conversion would depend on the session timezone.
    now = connection.execute(text("SELECT timezone('UTC', clock_timestamp())")).scalar_one()
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
    if preserved != before:
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
