"""Private bowel media and owner-scoped request replay contracts."""
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from app.models.user import User
from app.models.excretion import ExcretionRecord
from app.services.auth import auth_service


@pytest.fixture
def owned(client, db, tmp_path, monkeypatch):
    from app.api import upload
    monkeypatch.setattr(upload, 'UPLOAD_DIR', str(tmp_path))
    users = []
    for name in ('bowel_a', 'bowel_b'):
        user = User(username=name, name=name, email=f'{name}@example.test', hashed_password='test',
                    is_active=True, is_approved=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        users.append(user)
    owner = users[0]
    folder = tmp_path / 'medical' / str(owner.id)
    folder.mkdir(parents=True)
    (folder / 'test.jpg').write_bytes(b'private synthetic image')
    headers = {'Authorization': 'Bearer ' + auth_service.create_access_token({'sub': str(owner.id)})}
    payload = {'type': 'bowel', 'record_date': '2026-10-11',
               'photo_key': f'medical/{owner.id}/test.jpg', 'client_request_id': str(uuid.uuid4())}
    return headers, payload, users, tmp_path


def test_private_photo_and_replay(client, db, owned):
    headers, data, users, _ = owned
    first = client.post('/api/v1/excretion/records', json=data, headers=headers)
    assert first.status_code == 200
    result = first.json()
    assert result['photo_key'] == data['photo_key']
    assert result['client_request_id'] == data['client_request_id']
    url = urlsplit(result['photo_url'])
    assert url.path == f'/api/v1/upload/files/medical/{users[0].id}/test.jpg'
    assert 'signature' in parse_qs(url.query)
    repeat = client.post('/api/v1/excretion/records', json=data, headers=headers)
    assert repeat.status_code == 200
    assert repeat.json()['id'] == result['id']
    assert db.query(ExcretionRecord).count() == 1
    changed = client.post('/api/v1/excretion/records', json={**data, 'notes': 'changed'}, headers=headers)
    assert changed.status_code == 409


@pytest.mark.parametrize('key', ['https://example.test/test.jpg', 'medical/999999/test.jpg',
    'medical/1/../test.jpg', 'medical/1/%2e%2e/test.jpg', 'avatar/test.jpg', 'medical/1/missing.jpg'])
def test_unsafe_or_missing_photo_rejected(client, db, owned, key):
    headers, data, _, _ = owned
    response = client.post('/api/v1/excretion/records', json={**data, 'photo_key': key}, headers=headers)
    assert response.status_code in (400, 422)
    assert db.query(ExcretionRecord).count() == 0


def test_symlink_rejected(client, db, owned):
    headers, data, _, root = owned
    original = root / data['photo_key']
    original.unlink()
    target = root / 'other.jpg'
    target.write_bytes(b'synthetic')
    original.symlink_to(target)
    assert client.post('/api/v1/excretion/records', json=data, headers=headers).status_code == 400
    assert db.query(ExcretionRecord).count() == 0


def test_cross_owner_record_and_subject_rejected(client, owned):
    headers, data, users, _ = owned
    saved = client.post('/api/v1/excretion/records', json=data, headers=headers).json()
    other = {'Authorization': 'Bearer ' + auth_service.create_access_token({'sub': str(users[1].id)})}
    assert client.get(f"/api/v1/excretion/records/{saved['id']}", headers=other).status_code == 404
    assert client.post('/api/v1/excretion/records', json=data, headers=other).status_code == 400
    assert client.post('/api/v1/excretion/records', json=data,
                       headers={**headers, 'X-Reva-AI-Subject': str(users[1].id)}).status_code == 409


def test_unknown_blood_remains_null(client, owned):
    headers, data, _, _ = owned
    result = client.post('/api/v1/excretion/records', json=data, headers=headers)
    assert result.status_code == 200
    assert result.json()['blood_present'] is None


def test_urls_refreshed_and_private_upload_route(client, owned, monkeypatch):
    from app.services import private_uploads
    headers, data, _, _ = owned
    monkeypatch.setattr(private_uploads.time, 'time', lambda: 1000)
    saved = client.post('/api/v1/excretion/records', json=data, headers=headers).json()
    assert parse_qs(urlsplit(saved['photo_url']).query)['expires'] == ['1300']
    assert client.get(urlsplit(saved['photo_url']).path).status_code in (401, 403)
    monkeypatch.setattr(private_uploads.time, 'time', lambda: 1100)
    refreshed = client.get(f"/api/v1/excretion/records/{saved['id']}", headers=headers).json()
    assert parse_qs(urlsplit(refreshed['photo_url']).query)['expires'] == ['1400']
    assert refreshed['photo_url'] != saved['photo_url']
    assert client.get(saved['photo_url']).status_code == 200
    monkeypatch.setattr(private_uploads.time, 'time', lambda: 1301)
    assert client.get(saved['photo_url']).status_code in (401, 403)


def test_no_photo_old_clients_and_unique_scoped_per_user(client, db, owned):
    headers, data, users, _ = owned
    data.pop('photo_key')
    saved = client.post('/api/v1/excretion/records', json=data, headers=headers).json()
    assert saved['photo_url'] is None
    other = {'Authorization': 'Bearer ' + auth_service.create_access_token({'sub': str(users[1].id)})}
    result = client.post('/api/v1/excretion/records', json=data, headers=other)
    assert result.status_code == 200
    assert result.json()['id'] != saved['id']
    legacy = {'type': 'bowel', 'record_date': '2026-10-11'}
    assert client.post('/api/v1/excretion/records', json=legacy, headers=headers).status_code == 200
    assert client.post('/api/v1/excretion/records', json=legacy, headers=headers).status_code == 200
    assert db.query(ExcretionRecord).count() == 4


def test_invalid_uuid_rejected_without_write(client, db, owned):
    headers, data, _, _ = owned
    assert client.post('/api/v1/excretion/records', json={**data, 'client_request_id': 'invalid'},
                       headers=headers).status_code == 422
    assert db.query(ExcretionRecord).count() == 0


def test_replay_after_record_update_keeps_original_receipt(client, db, owned):
    headers, data, _, _ = owned
    first = client.post('/api/v1/excretion/records', json=data, headers=headers).json()
    assert client.put(f"/api/v1/excretion/records/{first['id']}", json={'notes': 'updated'},
                      headers=headers).status_code == 200
    replay = client.post('/api/v1/excretion/records', json=data, headers=headers)
    assert replay.status_code == 200
    assert replay.json()['id'] == first['id']
    assert replay.json()['notes'] == 'updated'
    assert db.query(ExcretionRecord).count() == 1


def test_directory_and_hardlink_photos_rejected(client, db, owned):
    headers, data, _, root = owned
    original = root / data['photo_key']
    original.unlink()
    original.mkdir()
    assert client.post('/api/v1/excretion/records', json=data, headers=headers).status_code == 400
    original.rmdir()
    original.write_bytes(b'synthetic')
    import os
    os.link(original, original.parent / 'other.jpg')
    assert client.post('/api/v1/excretion/records', json=data, headers=headers).status_code == 400
    assert db.query(ExcretionRecord).count() == 0


@pytest.mark.parametrize('different', [False, True])
def test_postgres_concurrent_request_replay(db, owned, different):
    """Force both transactions to read 'absent' before the unique-index race."""
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('real concurrent transactions require PostgreSQL')
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from app.api.excretion import create_record
    from app.schemas.excretion import ExcretionRecordCreate
    _, data, users, _ = owned
    data.pop('photo_key')
    owner_id = users[0].id
    barrier = Barrier(2, timeout=15)

    class RaceSession(Session):
        def query(self, *args, **kwargs):
            query = super().query(*args, **kwargs)
            if args == (ExcretionRecord,) and not getattr(self, '_did_wait', False):
                session = self
                class QueryProxy:
                    def filter_by(self, **criteria):
                        self.filtered = query.filter_by(**criteria)
                        return self
                    def first(self):
                        result = self.filtered.first()
                        session._did_wait = True
                        barrier.wait()
                        return result
                return QueryProxy()
            return query

    def save(index):
        with RaceSession(bind=db.bind) as session:
            user = session.get(User, owner_id)
            payload = {**data, 'notes': str(index) if different else None}
            try:
                response = asyncio.run(create_record(ExcretionRecordCreate(**payload), user, session))
                return (200, response.id)
            except HTTPException as exc:
                return (exc.status_code, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, range(2)))
    assert db.query(ExcretionRecord).count() == 1
    if different:
        assert sorted(status for status, _ in results) == [200, 409]
    else:
        assert results[0] == results[1]
        assert results[0][0] == 200


def test_owner_directory_symlink_rejected(client, db, owned):
    headers, data, _, root = owned
    owner_dir = (root / data['photo_key']).parent
    replacement = root / 'moved-owner'
    owner_dir.rename(replacement)
    owner_dir.symlink_to(replacement, target_is_directory=True)
    assert client.post('/api/v1/excretion/records', json=data, headers=headers).status_code == 400
    assert db.query(ExcretionRecord).count() == 0


def test_missing_historical_photo_keeps_record_readable(client, db, owned):
    headers, data, _, root = owned
    first = client.post('/api/v1/excretion/records', json=data, headers=headers).json()
    (root / data['photo_key']).unlink()
    listing = client.get('/api/v1/excretion/records/me?type=bowel', headers=headers)
    assert listing.status_code == 200
    assert listing.json()[0]['id'] == first['id']
    assert listing.json()[0]['photo_unavailable'] is True
    assert listing.json()[0]['photo_url'] is None
    assert listing.json()[0]['photo_key'] is None
    replay = client.post('/api/v1/excretion/records', json=data, headers=headers)
    assert replay.status_code == 200
    assert replay.json()['id'] == first['id']
    assert db.query(ExcretionRecord).count() == 1


def test_tampered_stored_owner_key_never_signed(client, db, owned):
    headers, data, users, _ = owned
    first = client.post('/api/v1/excretion/records', json=data, headers=headers).json()
    record = db.get(ExcretionRecord, first['id'])
    record.photo_key = f'medical/{users[1].id}/test.jpg'
    db.commit()
    response = client.get(f"/api/v1/excretion/records/{first['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()['photo_unavailable'] is True
    assert response.json()['photo_key'] is None
    assert response.json()['photo_url'] is None
