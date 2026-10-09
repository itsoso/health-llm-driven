"""Private life workspace has atomic versioned writes and bounded typed backups."""
from copy import deepcopy
import pytest
from app.schemas.life_navigation import LifeData, LifeWorkspaceWrite, LifeBackup
from app.services import life_navigation as service


def data(title='合成规划'):
    value = LifeData().model_dump(mode='json')
    value['strategy']['vision'] = title
    return value


def test_get_is_empty_and_does_not_write(db, auth_user_and_headers):
    from app.models.life_navigation import LifeNavigationWorkspace
    user, _ = auth_user_and_headers
    result = service.get_workspace(db, user.id)
    assert result.revision == 0 and result.updated_at is None
    assert result.data.strategy.vision == ''
    assert db.query(LifeNavigationWorkspace).count() == 0


def test_revision_conflict_restore_and_complete_backup(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    first = service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=0, data=data('one')))
    assert first.revision == 1
    with pytest.raises(service.HTTPException) as error:
        service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=0, data=data('stale')))
    assert error.value.status_code == 409
    db.rollback()
    service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=1, data=data('two')))
    restored = service.restore_workspace(db, user.id, 1, 2)
    assert restored.revision == 3 and restored.data.strategy.vision == 'one'
    backup = service.get_backup(db, user.id)
    assert backup.workspace.revision == 3
    assert [item.data.strategy.vision for item in backup.history] == ['one', 'two', 'one']
    assert service.get_workspace(db, user.id).data.strategy.vision == 'one'


def test_strict_input_and_week_membership():
    from pydantic import ValidationError
    value = data()
    value['unknown'] = 'not permitted'
    with pytest.raises(ValidationError):
        LifeData.model_validate(value)
    value = data()
    value['weeks'] = {'2026-10-06': {}}
    with pytest.raises(ValidationError):
        LifeData.model_validate(value)
    value['weeks'] = {'2026-10-05': {'notes': {'2026-10-12': {'valuable': 'wrong week'}}}}
    with pytest.raises(ValidationError):
        LifeData.model_validate(value)


def test_import_validates_all_before_mutation(db, auth_user_and_headers):
    from pydantic import ValidationError
    user, _ = auth_user_and_headers
    service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=0, data=data('keep')))
    backup = service.get_backup(db, user.id).model_dump(mode='json')
    backup['history'][0]['data']['strategy']['unexpected'] = 'forbidden'
    with pytest.raises(ValidationError):
        LifeBackup.model_validate(backup)
    assert service.get_workspace(db, user.id).revision == 1
    assert service.get_workspace(db, user.id).data.strategy.vision == 'keep'


def test_import_renumbers_and_preserves_prior_version(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=0, data=data('before')))
    backup = service.get_backup(db, user.id).model_dump(mode='json')
    backup['workspace']['data']['strategy']['vision'] = 'imported'
    result = service.import_backup(db, user.id, 1, LifeBackup.model_validate(backup))
    assert result.revision > 1
    history = service.get_history(db, user.id)
    assert history[-1].data.strategy.vision == 'imported'
    assert any(item.data.strategy.vision == 'before' for item in history)
    assert len({item.revision for item in history}) == len(history)


def test_history_is_bounded_and_other_owner_isolated(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    for revision in range(25):
        service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=revision, data=data(str(revision))))
    assert len(service.get_history(db, user.id)) == 20
    assert service.get_workspace(db, user.id + 10000).revision == 0
    assert service.get_history(db, user.id + 10000) == []


@pytest.fixture
def private_client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.life_navigation import router
    from app.database import get_db
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    def request_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise
    app.dependency_overrides[get_db] = request_db
    with TestClient(app) as client:
        yield client


def test_api_owner_subject_privacy_and_no_health_mutation(private_client, db, auth_user_and_headers):
    from app.models.intervention_event import InterventionEvent
    from app.models.daily_operating_plan import DailyOperatingPlan
    user, headers = auth_user_and_headers
    path = '/api/v1/life-navigation/workspace'
    before = (db.query(InterventionEvent).count(), db.query(DailyOperatingPlan).count())
    response = private_client.put(path, headers={**headers, 'X-Reva-AI-Subject': str(user.id + 1)},
                                  json={'expected_revision': 0, 'data': data()})
    assert response.status_code == 409
    assert service.get_workspace(db, user.id).revision == 0
    response = private_client.put(path, headers={**headers, 'X-Reva-AI-Subject': str(user.id)},
                                  json={'expected_revision': 0, 'data': data('private-body-marker')})
    assert response.status_code == 200 and response.json()['revision'] == 1
    assert response.headers['cache-control'] == 'private, no-store'
    exported = private_client.get('/api/v1/life-navigation/backup', headers=headers)
    assert exported.status_code == 200
    assert exported.json()['workspace']['data']['strategy']['vision'] == 'private-body-marker'
    assert (db.query(InterventionEvent).count(), db.query(DailyOperatingPlan).count()) == before
    invalid = private_client.put(path, headers=headers,
        json={'expected_revision': 1, 'data': {**data(), 'health_body': 'private-input-marker'}})
    assert invalid.status_code == 422
    assert 'private-input-marker' not in invalid.text
    assert invalid.headers['cache-control'] == 'private, no-store'


def test_api_key_and_managed_accounts_cannot_use_private_workspace(private_client, db, auth_user_and_headers):
    from app.models.user_api_key import UserApiKey
    from hashlib import sha256
    user, headers = auth_user_and_headers
    raw = 'synthetic-planning-api-key'
    db.add(UserApiKey(user_id=user.id, name='synthetic', scopes='read,write', api_key=sha256(raw.encode()).hexdigest()))
    db.commit()
    assert private_client.get('/api/v1/life-navigation/workspace', headers={'X-API-Key': raw}).status_code == 403
    user.is_managed = True
    db.commit()
    assert private_client.get('/api/v1/life-navigation/workspace', headers=headers).status_code == 403


def test_task_ids_are_global_and_timer_never_completes_task():
    from uuid import uuid4
    from pydantic import ValidationError
    task_id = str(uuid4())
    value = data()
    value['weeks'] = {'2026-10-05': {'tasks': [{'id': task_id, 'date': '2026-10-05'}]},
                      '2026-10-12': {'tasks': [{'id': task_id, 'date': '2026-10-12'}]}}
    with pytest.raises(ValidationError):
        LifeData.model_validate(value)
    value['weeks'].pop('2026-10-12')
    value['focus'].update(phase='focus', task_id=task_id, deadline='2026-10-10T10:00:00+08:00')
    parsed = LifeData.model_validate(value)
    assert parsed.weeks['2026-10-05'].tasks[0].status == 'planned'
    assert parsed.focus.phase == 'focus'


def test_total_body_size_is_bounded():
    from pydantic import ValidationError
    value = data()
    from uuid import uuid4
    value['opportunities'] = [{'id': str(uuid4()), 'category': 'macro', 'insight': 'x' * 4000,
                                'evidence': 'y' * 4000} for _ in range(40)]
    with pytest.raises(ValidationError):
        LifeData.model_validate(value)


def test_postgresql_concurrent_cas_has_one_winner(db, auth_user_and_headers):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('Requires PostgreSQL owner locks and separate transactions')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    user, _ = auth_user_and_headers
    user_id = user.id
    bind = db.get_bind()
    db.rollback()
    barrier = Barrier(2)
    def write(label):
        with Session(bind=bind) as session:
            barrier.wait(timeout=10)
            try:
                return service.save_workspace(session, user_id,
                    LifeWorkspaceWrite(expected_revision=0, data=data(label))).revision
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ['first', 'second']))
    assert sorted(results) == [1, 409]
    db.expire_all()
    assert service.get_workspace(db, user_id).revision == 1
    assert len(service.get_history(db, user_id)) == 1


def test_failed_import_rolls_back_entire_write(private_client, db, auth_user_and_headers, monkeypatch):
    user, headers = auth_user_and_headers
    service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=0, data=data('retained')))
    backup = service.get_backup(db, user.id).model_dump(mode='json')
    backup['workspace']['data']['strategy']['vision'] = 'must-not-persist'
    def fail_commit():
        raise RuntimeError('synthetic commit failure')
    with monkeypatch.context() as patch:
        patch.setattr(db, 'commit', fail_commit)
        response = private_client.post('/api/v1/life-navigation/import', headers=headers,
            json={'expected_revision': 1, 'backup': backup})
    assert response.status_code == 503
    assert 'must-not-persist' not in response.text
    assert service.get_workspace(db, user.id).revision == 1
    assert service.get_workspace(db, user.id).data.strategy.vision == 'retained'
    assert len(service.get_history(db, user.id)) == 1


def test_import_full_history_retains_pre_import_current(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    service.save_workspace(db, user.id, LifeWorkspaceWrite(expected_revision=0, data=data('original-private-state')))
    stamp = '2026-10-10T00:00:00+00:00'
    incoming = LifeBackup.model_validate({
        'schema_version': 'life_navigation.backup.v1',
        'workspace': {'schema_version': 'life_navigation.v1', 'revision': 20, 'data': data('incoming19'), 'updated_at': stamp},
        'history': [{'revision': index + 1, 'data': data('incoming' + str(index)), 'updated_at': stamp}
                    for index in range(20)],
    })
    result = service.import_backup(db, user.id, 1, incoming)
    history = service.get_history(db, user.id)
    assert len(history) == 20
    assert history[0].data.strategy.vision == 'original-private-state'
    assert history[-1].data.strategy.vision == 'incoming19'
    assert result.revision == history[-1].revision
