"""Authenticated event writes and independent readback for nasal-wash records."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.health_checkin import HealthCheckin
from app.models.user import User


def payload(event_id='nasal-event-1', **changes):
    return dict(record_date='2026-10-31', event_id=event_id, count=1,
                volume_ml=10.12345, solution='生理盐水', **changes)


def test_nasal_wash_append_replay_and_exact_readback(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    existing = HealthCheckin(user_id=user.id, checkin_date=date(2026, 10, 31),
                             sneeze_count=3, notes='preserve', nasal_wash_count=2,
                             nasal_wash_times=[{'time': '08:00', 'type': 'wash'}])
    db.add(existing)
    db.commit()
    first = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=payload())
    assert first.status_code == 200, first.text
    body = first.json()
    assert body['nasal_wash_count'] == 3
    assert body['sneeze_count'] == 3 and body['notes'] == 'preserve'
    assert len(body['nasal_wash_times']) == 2
    event = body['nasal_wash_times'][-1]
    assert event['volume_ml'] == 10.12345 and event['count'] == 1
    replay = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=payload())
    assert replay.status_code == 200
    assert replay.json()['nasal_wash_count'] == 3
    assert len(replay.json()['nasal_wash_times']) == 2
    read = client.get(f"/api/v1/checkin/{body['id']}/nasal-wash/nasal-event-1", headers=headers)
    assert read.status_code == 200
    assert read.json() == {'id': body['id'], 'user_id': user.id, 'checkin_date': '2026-10-31', 'event': event}


def test_event_id_conflict_cannot_change_quantity_or_date(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    first = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=payload())
    assert first.status_code == 200, first.text
    for change in [{'count': 2}, {'record_date': '2026-10-30'}, {'volume_ml': 9}, {'solution': 'other'}]:
        response = client.post('/api/v1/checkin/nasal-wash', headers=headers, json={**payload(), **change})
        assert response.status_code == 409, response.text
    rows = db.query(HealthCheckin).filter_by(user_id=user.id).all()
    assert len(rows) == 1 and rows[0].nasal_wash_count == 1


@pytest.mark.parametrize('change', [
    {'count': True}, {'count': '1'}, {'count': 1.5}, {'count': 0}, {'count': 21},
    {'volume_ml': True}, {'volume_ml': 0}, {'volume_ml': 5001}, {'volume_ml': 'NaN'},
    {'volume_ml': 'Infinity'}, {'solution': 'x' * 81}, {'event_id': '../other'},
    {'event_id': ''}, {'time': '24:00'}, {'user_id': 999},
])
def test_nasal_wash_contract_rejects_invalid_and_foreign_fields(client, db, auth_user_and_headers, change):
    _, headers = auth_user_and_headers
    response = client.post('/api/v1/checkin/nasal-wash', headers=headers, json={**payload(), **change})
    assert response.status_code == 422, response.text
    assert db.query(HealthCheckin).count() == 0


def test_nasal_wash_requires_auth_and_isolates_readback(client, db, auth_user_and_headers):
    from app.services.auth import auth_service
    user, headers = auth_user_and_headers
    assert client.post('/api/v1/checkin/nasal-wash', json=payload()).status_code in {401, 403}
    created = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=payload())
    assert created.status_code == 200, created.text
    other = User(username='nasal_other', email='nasal_other@example.test', name='Other',
                 hashed_password='unused', is_active=True, is_approved=True)
    db.add(other)
    db.commit()
    other_headers = {'Authorization': 'Bearer ' + auth_service.create_access_token({'sub': str(other.id)})}
    read = client.get(f"/api/v1/checkin/{created.json()['id']}/nasal-wash/nasal-event-1", headers=other_headers)
    assert read.status_code == 404
    own = client.post('/api/v1/checkin/nasal-wash', headers=other_headers, json=payload())
    assert own.status_code == 200 and own.json()['user_id'] == other.id
    assert own.json()['id'] != created.json()['id']


def test_postgresql_concurrent_new_day_and_duplicate_event(db, auth_user_and_headers):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('Row locking and concurrent inserts require PostgreSQL')
    from app.api.health_checkin import create_nasal_wash
    from app.schemas.record_capability import NasalWashCreate
    user, _ = auth_user_and_headers
    user_id = user.id
    db.commit()
    factory = sessionmaker(bind=db.get_bind())
    barrier = Barrier(4)

    def write(event_id):
        with factory() as session:
            owner = session.get(User, user_id)
            barrier.wait(timeout=10)
            return create_nasal_wash(NasalWashCreate(**payload(event_id)), owner, session).id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(write, ['one', 'two', 'one', 'two']))
    db.expire_all()
    rows = db.query(HealthCheckin).filter_by(user_id=user_id).all()
    assert len(set(ids)) == 1 and len(rows) == 1
    assert rows[0].nasal_wash_count == 2
    assert {item['event_id'] for item in rows[0].nasal_wash_times} == {'one', 'two'}


def test_nasal_event_uses_owner_timezone_and_preserves_unknown_fields(client, db, auth_user_and_headers):
    from app.models.user_profile import UserProfile
    from app.utils.timezone import get_user_now
    user, headers = auth_user_and_headers
    db.add(UserProfile(user_id=user.id, manual_timezone='Pacific/Honolulu'))
    db.commit()
    before = get_user_now(db, user.id).strftime('%H:%M:%S')
    response = client.post('/api/v1/checkin/nasal-wash', headers=headers,
                           json={'record_date': '2026-10-31', 'event_id': 'unknown-fields', 'count': 1})
    after = get_user_now(db, user.id).strftime('%H:%M:%S')
    assert response.status_code == 200, response.text
    event = response.json()['nasal_wash_times'][0]
    assert event['time'] >= before and event['time'] <= after
    assert event['volume_ml'] is None and event['solution'] is None
    missing = client.get(f"/api/v1/checkin/{response.json()['id']}/nasal-wash/missing", headers=headers)
    assert missing.status_code == 404


def test_generic_checkin_cannot_erase_or_mutate_canonical_events(client, db, auth_user_and_headers, monkeypatch):
    from datetime import datetime
    from app.api import health_checkin
    _, headers = auth_user_and_headers
    monkeypatch.setattr(health_checkin, 'get_user_now', lambda *args: datetime(2026, 10, 31, 12, 30, 1))
    for event_id in ('same-second-one', 'same-second-two'):
        result = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=payload(event_id))
        assert result.status_code == 200
    original = result.json()
    assert len(original['nasal_wash_times']) == 2
    bad_times = [{**item, 'volume_ml': 999} for item in original['nasal_wash_times']]
    changes = [
        {'nasal_wash_times': []},
        {'nasal_wash_times': original['nasal_wash_times'][:1]},
        {'nasal_wash_times': bad_times},
        {'nasal_wash_count': 1},
        {'nasal_wash_count': 3},
    ]
    for change in changes:
        rejected = client.post('/api/v1/checkin/', headers=headers,
                               json={'checkin_date': '2026-10-31', 'notes': 'must-not-save', **change})
        assert rejected.status_code == 409, rejected.text
    db.expire_all()
    row = db.get(HealthCheckin, original['id'])
    assert row.nasal_wash_times == original['nasal_wash_times']
    assert row.nasal_wash_count == 2 and row.notes is None


def test_generic_roundtrip_and_adjacent_rhinitis_preserve_same_second_events(client, db, auth_user_and_headers, monkeypatch):
    from datetime import datetime
    from app.api import health_checkin
    _, headers = auth_user_and_headers
    monkeypatch.setattr(health_checkin, 'get_user_now', lambda *args: datetime(2026, 10, 31, 12, 30, 1))
    for event_id in ('one', 'two'):
        created = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=payload(event_id))
        assert created.status_code == 200
    original = created.json()
    assert all(event['type'] == 'wash' for event in original['nasal_wash_times'])
    echo = client.post('/api/v1/checkin/', headers=headers, json={
        'checkin_date': '2026-10-31', 'nasal_wash_count': original['nasal_wash_count'],
        'nasal_wash_times': original['nasal_wash_times'], 'notes': 'roundtrip-note',
    })
    assert echo.status_code == 200
    assert echo.json()['nasal_wash_times'] == original['nasal_wash_times']
    adjacent = client.post('/api/v1/checkin/', headers=headers, json={
        'checkin_date': '2026-10-31', 'sneeze_times': [{'time': '12:31', 'count': 3}],
    })
    assert adjacent.status_code == 200
    assert adjacent.json()['sneeze_count'] == 3
    assert adjacent.json()['nasal_wash_count'] == 2
    assert adjacent.json()['nasal_wash_times'] == original['nasal_wash_times']
    assert adjacent.json()['notes'] == 'roundtrip-note'


def test_generic_checkin_cannot_invent_canonical_event_ids(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    response = client.post('/api/v1/checkin/', headers=headers, json={
        'checkin_date': '2026-10-31', 'nasal_wash_count': 1,
        'nasal_wash_times': [{'event_id': 'forged', 'time': '12:00', 'count': 1, 'volume_ml': -10}],
    })
    assert response.status_code == 409
    assert db.query(HealthCheckin).count() == 0


def test_manual_time_soak_and_exact_event_undo_keep_tombstone(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    first_payload = {**payload('first'), 'type': 'soak', 'time': '08:30', 'count': 2}
    first = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=first_payload)
    assert first.status_code == 200, first.text
    event = first.json()['nasal_wash_times'][0]
    assert event['type'] == 'soak' and event['time'] == '08:30:00'
    checkin_id = first.json()['id']
    assert client.post('/api/v1/checkin/nasal-wash', headers=headers, json=first_payload).status_code == 200
    altered_time = client.post('/api/v1/checkin/nasal-wash', headers=headers, json={**first_payload, 'time': '08:31'})
    assert altered_time.status_code == 409
    second = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=payload('second'))
    assert second.status_code == 200 and second.json()['nasal_wash_count'] == 3
    for _ in range(2):
        undone = client.delete(f'/api/v1/checkin/{checkin_id}/nasal-wash/first', headers=headers)
        assert undone.status_code == 200
        assert undone.json()['nasal_wash_count'] == 1
        assert [item['event_id'] for item in undone.json()['nasal_wash_times']] == ['second']
    db.expire_all()
    row = db.get(HealthCheckin, checkin_id)
    assert len(row.nasal_wash_times) == 2
    assert row.nasal_wash_times[0]['undone'] is True
    assert client.get(f'/api/v1/checkin/{checkin_id}/nasal-wash/first', headers=headers).status_code == 404
    assert client.post('/api/v1/checkin/nasal-wash', headers=headers, json=first_payload).status_code == 409
    echo = client.post('/api/v1/checkin/', headers=headers, json={
        'checkin_date': '2026-10-31', 'nasal_wash_count': 1,
        'nasal_wash_times': undone.json()['nasal_wash_times'], 'notes': 'preserve-tombstone',
    })
    assert echo.status_code == 200
    db.expire_all()
    assert len(db.get(HealthCheckin, checkin_id).nasal_wash_times) == 2
    assert client.post('/api/v1/checkin/nasal-wash', headers=headers, json=first_payload).status_code == 409


def test_undo_is_owner_scoped_and_ignores_client_aggregate(client, db, auth_user_and_headers):
    from app.services.auth import auth_service
    _, headers = auth_user_and_headers
    first = client.post('/api/v1/checkin/nasal-wash', headers=headers, json=payload())
    assert first.status_code == 200
    other = User(username='nasal_undo_other', email='nasal_undo_other@example.test', name='Other',
                 hashed_password='unused', is_active=True, is_approved=True)
    db.add(other)
    db.commit()
    other_headers = {'Authorization': 'Bearer ' + auth_service.create_access_token({'sub': str(other.id)})}
    endpoint = f"/api/v1/checkin/{first.json()['id']}/nasal-wash/nasal-event-1"
    assert client.delete(endpoint, headers=other_headers).status_code == 404
    assert client.delete(endpoint).status_code in {401, 403}
    assert client.get(endpoint, headers=headers).status_code == 200
