"""Cold-session HTTP budgets for synthetic, owner-scoped meal/photo reads."""
import ast
import hashlib
import json
import math
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import perf_counter

import pytest
from app.models.daily_health import DietPhotoAsset, DietRecord
from sqlalchemy import event

from tests.conftest import create_authenticated_user

TODAY = date(2026, 10, 15)
ROUTES = ('user-list', 'user-day', 'me-list', 'me-day')
BASELINE_SOURCE_SHA256 = '280a1a70612dc5ede61848ace6878e8a06351b58f1b80e032c534577001e9105'


@pytest.fixture(autouse=True)
def canonical_read_baseline(monkeypatch):
    """Optional benchmark-only old read functions; shared source is never edited.

    CI does not set this variable. The four bodies come from one exact Git blob;
    all current authentication dependencies and serializers remain identical.
    """
    filename = os.environ.get('REVA_DIET_QUERY_BASELINE_SOURCE')
    if not filename:
        return
    from app.api import diet

    raw = Path(filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == BASELINE_SOURCE_SHA256
    names = {'get_user_diet_records', 'get_daily_diet_summary',
             'get_my_diet_records', 'get_my_daily_diet_summary'}
    nodes = [node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == names
    for node in nodes:
        node.decorator_list = []  # no duplicate route registration
    namespace = dict(vars(diet))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<byte-bound-diet-read-baseline>', 'exec'), namespace)  # noqa: S102 - four byte-bound canonical GET bodies only
    for name in names:
        current = getattr(diet, name)
        assert current.__closure__ is None and namespace[name].__closure__ is None
        # Retain the function object captured by lazy/compiled FastAPI routers.
        # Signatures, defaults, globals and authentication dependencies are unchanged.
        monkeypatch.setattr(current, '__code__', namespace[name].__code__)


def route(kind, owner_id, day=TODAY):
    return {
        'user-list': f'/api/v1/diet/records/user/{owner_id}',
        'user-day': f'/api/v1/diet/records/user/{owner_id}/date/{day}',
        'me-list': '/api/v1/diet/records/me',
        'me-day': f'/api/v1/diet/records/me/date/{day}',
    }[kind]


@pytest.fixture(params=[3, 30])
def meals(db, auth_user_and_headers, request):
    owner, headers = auth_user_and_headers
    foreign, _ = create_authenticated_user(db)
    owner_id, foreign_id = owner.id, foreign.id
    records = []
    count = request.param
    for index in range(count):
        record_day = TODAY - timedelta(days=(count - 1) // 3 - index // 3)
        record = DietRecord(user_id=owner_id, record_date=record_day, meal_type='lunch',
            food_items=f'合成餐{index}', calories=100 + index,
            created_at=datetime(record_day.year, record_day.month, record_day.day, 8, tzinfo=UTC)
                       + timedelta(minutes=index % 3))
        db.add(record)
        db.flush()
        for ordinal in (1, 0):
            db.add(DietPhotoAsset(id=f'synthetic-{index}-{ordinal}', user_id=owner_id,
                diet_record_id=record.id, storage_key=f'/api/v1/upload/files/diet/{owner_id}/{index}-{ordinal}.jpg',
                content_sha256=hashlib.sha256(f'synthetic-{index}-{ordinal}'.encode()).hexdigest(),
                media_type='image/jpeg', origin='manual',
                ordinal=ordinal, classification='food', intent_decision='auto_record',
                recognition_snapshot={}, lifecycle='attached'))
        records.append(record.id)
    other = DietRecord(user_id=foreign_id, record_date=TODAY, meal_type='dinner',
        food_items='不应交付的合成外部餐', calories=999)
    db.add(other)
    db.flush()
    db.add(DietPhotoAsset(id='synthetic-foreign-photo', user_id=foreign_id,
        diet_record_id=other.id, storage_key=f'/api/v1/upload/files/diet/{foreign_id}/foreign.jpg',
        content_sha256='f' * 64, media_type='image/jpeg', origin='manual', ordinal=0,
        classification='food', intent_decision='auto_record', recognition_snapshot={}, lifecycle='attached'))
    db.commit()
    return owner_id, foreign_id, headers, records


def quantile(values, percentile):
    return sorted(values)[max(0, math.ceil(len(values) * percentile) - 1)]


def cold_requests(db, client, url, headers, repeats):
    samples = []
    current = None
    def before(_conn, _cursor, statement, _params, _context, _many):
        text = statement.lower().lstrip()
        if text.startswith('select') and ('from diet_records' in text or 'from diet_photo_assets' in text):
            current['count'] += 1
            current['started'] = perf_counter()
    def after(_conn, _cursor, _statement, _params, _context, _many):
        if current.get('started') is not None:
            current['sql_ms'] += (perf_counter() - current.pop('started')) * 1000
    event.listen(db.get_bind(), 'before_cursor_execute', before)
    event.listen(db.get_bind(), 'after_cursor_execute', after)
    try:
        for _ in range(repeats):
            # A reused fixture Session must not hide lazy loads through its
            # identity map; real HTTP dependencies create fresh Sessions.
            db.expunge_all()
            current = {'count': 0, 'sql_ms': 0.0}
            started = perf_counter()
            response = client.get(url, headers=headers)
            current['http_ms'] = (perf_counter() - started) * 1000
            samples.append(current)
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', before)
        event.remove(db.get_bind(), 'after_cursor_execute', after)
    return response, samples


@pytest.mark.parametrize('kind', ROUTES)
def test_owned_photo_reads_have_constant_query_budget_and_stable_order(db, client, meals, kind):
    owner_id, _foreign_id, headers, record_ids = meals
    repeats = 20 if os.environ.get('REVA_DIET_QUERY_EVIDENCE') else 2
    response, samples = cold_requests(db, client, route(kind, owner_id), headers, repeats)
    assert response.status_code == 200
    body = response.json()
    delivered = body if kind.endswith('list') else body['meals']
    expected_ids = list(reversed(record_ids)) if kind.endswith('list') else record_ids[-3:]
    assert [record['id'] for record in delivered] == expected_ids
    assert all(record['user_id'] == owner_id for record in delivered)
    for record in delivered:
        assert [asset['ordinal'] for asset in record['photo_assets']] == [0, 1]
        assert len(record['image_urls']) == 2
        assert all(f'/diet/{owner_id}/' in asset['url'] for asset in record['photo_assets'])
    prefix = os.environ.get('REVA_DIET_QUERY_EVIDENCE')
    if prefix:
        descriptor = f'synthetic-v1:{len(record_ids)}-owned-meals:2-photos-each:1-foreign-meal:ordinal-1-before-0'
        summary = {'kind': 'synthetic-cold-http', 'endpoint': kind,
            'fixture_sha256': hashlib.sha256(descriptor.encode()).hexdigest(),
            'fixture_records': len(record_ids), 'baseline_source_sha256': BASELINE_SOURCE_SHA256
                if os.environ.get('REVA_DIET_QUERY_BASELINE_SOURCE') else None,
            'database': db.get_bind().dialect.name, 'samples': len(samples), 'records': len(delivered),
            'diet_select_counts': [s['count'] for s in samples],
            'timing_ms': {field: {f'p{int(p * 100)}': round(quantile([s[field] for s in samples], p), 4)
                for p in (0.5, 0.95, 0.99)} for field in ('http_ms', 'sql_ms')}}
        Path(f'{prefix}-{kind}-{len(record_ids)}.json').write_text(json.dumps(summary, sort_keys=True))
    assert all(s['count'] == 2 for s in samples), samples


@pytest.mark.parametrize('kind', ROUTES)
def test_empty_owner_and_date_never_fetch_unrelated_photos(db, client, auth_user_and_headers, kind):
    user, headers = auth_user_and_headers
    owner_id = user.id
    response, samples = cold_requests(db, client, route(kind, owner_id), headers, 1)
    assert response.status_code == 200
    body = response.json()
    assert (body if kind.endswith('list') else body['meals']) == []
    assert samples[0]['count'] == 1


@pytest.mark.parametrize('kind', ['user-list', 'user-day'])
def test_foreign_owner_is_rejected_before_photo_load(db, client, meals, kind):
    _owner_id, foreign_id, headers, _record_ids = meals
    response, samples = cold_requests(db, client, route(kind, foreign_id), headers, 1)
    assert response.status_code == 403
    assert samples[0]['count'] == 0
