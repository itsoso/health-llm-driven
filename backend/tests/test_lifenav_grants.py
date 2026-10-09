"""Dedicated credentials never acquire ordinary account or health API authority."""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app.models.user import User
from app.models.lifenav_grant import LifeNavGrant, LifeNavAccessAudit
from app.schemas.lifenav_grant import LifeNavGrantCreate, LifeNavCodeExchange
from app.services import integration_grant_service as grants

SECRET = 'synthetic-recipient-backend-secret'
VERIFIER = 'v' * 64
CALLBACK = 'https://lifenav.example.test/oauth/reva/callback'
STATE = 'synthetic-session-state-1234567890'


@pytest.fixture
def recipient(monkeypatch):
    monkeypatch.setattr(grants, 'settings', SimpleNamespace(lifenav_integration_enabled=True, lifenav_recipients_json='{}'))
    monkeypatch.setattr(grants.settings, 'lifenav_recipients_json', json.dumps({'test-client': {
        'verified': True, 'origin': 'https://lifenav.example.test',
        'redirect_uri': CALLBACK, 'client_secret_sha256': grants.credential_hash(SECRET),
    }}), raising=False)


def owner(db):
    user = User(name='synthetic', is_active=True, is_approved=True)
    db.add(user)
    db.commit()
    return user


def create(db, user):
    challenge = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip('=')
    result = grants.create_grant(db, user, LifeNavGrantCreate(
        recipient_id='test-client', redirect_uri=CALLBACK, state=STATE,
        code_challenge=challenge, expires_in_days=7,
    ))
    code = parse_qs(urlsplit(result.authorization_url).query)['code'][0]
    return result, code


def exchange(db, code, **overrides):
    data = dict(client_id='test-client', client_secret=SECRET, code=code,
                redirect_uri=CALLBACK, state=STATE, code_verifier=VERIFIER)
    data.update(overrides)
    return grants.exchange_code(db, LifeNavCodeExchange(**data))


def test_code_is_bound_and_one_time_credential_is_hashed(db, recipient):
    user = owner(db)
    result, code = create(db, user)
    assert 'access_token' not in result.model_dump()
    row = db.query(LifeNavGrant).one()
    assert row.code_hash != code
    for bad in ({'client_secret': 'wrong-secret-long-enough'}, {'state': 'another-session-state-1234567890'},
                {'code_verifier': 'w' * 64}, {'redirect_uri': CALLBACK + '/wrong'}):
        with pytest.raises(HTTPException):
            exchange(db, code, **bad)
    token = exchange(db, code)
    assert token.access_token.startswith('ln1_')
    assert db.query(LifeNavGrant).one().token_hash == grants.credential_hash(token.access_token)
    with pytest.raises(HTTPException):
        exchange(db, code)
    assert grants.authenticate_grant(db, token.access_token).user_id == user.id


@pytest.mark.parametrize('change', ['revoke', 'expire', 'inactive', 'unapproved', 'managed', 'recipient', 'policy', 'scope'])
def test_every_read_rechecks_current_grant_owner_and_recipient(db, recipient, monkeypatch, change):
    user = owner(db)
    result, code = create(db, user)
    token = exchange(db, code).access_token
    row = db.query(LifeNavGrant).one()
    if change == 'revoke':
        grants.revoke_grant(db, user.id, result.grant_id)
    elif change == 'expire':
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif change == 'inactive':
        user.is_active = False
    elif change == 'unapproved':
        user.is_approved = False
    elif change == 'managed':
        user.is_managed = True
    elif change == 'recipient':
        monkeypatch.setattr(grants.settings, 'lifenav_recipients_json', '{}')
    elif change == 'policy':
        row.policy_version = 'obsolete'
    elif change == 'scope':
        row.scope = 'read'
    db.commit()
    with pytest.raises(HTTPException):
        grants.authenticate_grant(db, token)


def test_disabled_allowlist_and_redirect_fail_closed(db, recipient, monkeypatch):
    user = owner(db)
    monkeypatch.setattr(grants.settings, 'lifenav_integration_enabled', False)
    with pytest.raises(HTTPException):
        create(db, user)
    monkeypatch.setattr(grants.settings, 'lifenav_integration_enabled', True)
    monkeypatch.setattr(grants.settings, 'lifenav_recipients_json', '{}')
    with pytest.raises(HTTPException):
        create(db, user)
    assert db.query(LifeNavGrant).count() == 0


def test_other_owner_cannot_revoke_or_list_grant(db, recipient):
    first, other = owner(db), owner(db)
    result, _ = create(db, first)
    assert grants.list_grants(db, other.id) == []
    with pytest.raises(HTTPException) as error:
        grants.revoke_grant(db, other.id, result.grant_id)
    assert error.value.status_code == 404
    assert db.query(LifeNavGrant).one().revoked_at is None


def test_code_expiry_and_revoke_before_exchange(db, recipient):
    user = owner(db)
    result, code = create(db, user)
    row = db.query(LifeNavGrant).one()
    row.code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    with pytest.raises(HTTPException):
        exchange(db, code)
    result, code = create(db, user)
    grants.revoke_grant(db, user.id, result.grant_id)
    with pytest.raises(HTTPException):
        exchange(db, code)


def test_schema_rejects_broad_fields_and_non_tls_callback():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        LifeNavGrantCreate(recipient_id='test-client', redirect_uri='http://localhost/cb',
                           state=STATE, code_challenge='x' * 43)
    with pytest.raises(ValidationError):
        LifeNavGrantCreate(recipient_id='test-client', redirect_uri=CALLBACK,
                           state=STATE, code_challenge='x' * 43, scope='read', user_id=3)


@pytest.fixture
def integration_client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.integration_lifenav import router
    from app.database import get_db
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client


def test_generic_summary_is_scoped_read_only_and_audited(db, recipient, integration_client, monkeypatch):
    from app.services import health_week_navigation
    user = owner(db)
    result, code = create(db, user)
    token = exchange(db, code).access_token
    seen = []
    original_projection = health_week_navigation.build_health_week_navigation
    def projection(read_db, user_id, **kwargs):
        seen.append((read_db, user_id, kwargs))
        assert read_db is not db
        if read_db.bind.dialect.name == 'postgresql':
            from sqlalchemy import text
            assert read_db.execute(text('SHOW transaction_read_only')).scalar() == 'on'
        result = original_projection(read_db, user_id, **kwargs)
        result['expires_at'] = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        return result
    monkeypatch.setattr(health_week_navigation, 'build_health_week_navigation', projection)
    response = integration_client.get('/api/v1/integrations/lifenav/summary', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    assert seen[0][1:] == (user.id, {'audience': 'lifenav', 'view_id': result.grant_id})
    assert datetime.fromisoformat(response.json()['expires_at']) <= grants.utc(db.query(LifeNavGrant).one().expires_at)
    assert db.query(LifeNavAccessAudit).filter_by(outcome='read').count() == 1
    assert db.query(LifeNavGrant).count() == 1


def test_summary_rejects_selectors_and_ordinary_credentials(db, recipient, integration_client):
    from app.services.auth import auth_service
    user = owner(db)
    _, code = create(db, user)
    token = exchange(db, code).access_token
    for suffix in ('?user_id=2', '?end_date=2026-01-01', '?scope=metrics'):
        response = integration_client.get('/api/v1/integrations/lifenav/summary' + suffix,
                                          headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 400
        assert response.headers['cache-control'] == 'private, no-store'
    response = integration_client.get('/api/v1/integrations/lifenav/summary',
        headers={'Authorization': 'Bearer ' + auth_service.create_access_token({'sub': str(user.id)})})
    assert response.status_code == 403
    assert db.query(LifeNavAccessAudit).filter_by(outcome='denied').count() == 1


def test_grants_require_personal_session_and_reject_proxy_and_api_key(db, recipient, integration_client):
    from app.services.auth import auth_service
    from app.models.user_api_key import UserApiKey
    user = owner(db)
    jwt = auth_service.create_access_token({'sub': str(user.id)})
    response = integration_client.get('/api/v1/health-navigation/grants', headers={'Authorization': f'Bearer {jwt}'})
    assert response.status_code == 200
    raw = 'synthetic-broad-api-key'
    db.add(UserApiKey(user_id=user.id, name='synthetic', scopes='read,write', api_key=grants.credential_hash(raw)))
    db.commit()
    response = integration_client.get('/api/v1/health-navigation/grants', headers={'X-API-Key': raw})
    assert response.status_code == 403
    user.is_managed = True
    db.commit()
    response = integration_client.get('/api/v1/health-navigation/grants', headers={'Authorization': f'Bearer {jwt}'})
    assert response.status_code == 403


def test_exchange_validation_never_echoes_sensitive_inputs(recipient, integration_client):
    response = integration_client.post('/api/v1/integrations/lifenav/exchange', json={
        'client_id': 'test-client', 'client_secret': 'secret-to-not-echo',
        'code': 'code-to-not-echo', 'state': 'tiny', 'redirect_uri': CALLBACK,
        'code_verifier': 'verifier-to-not-echo', 'unknown': 'synthetic-private-data',
    })
    assert response.status_code == 422
    for text in ('secret-to-not-echo', 'code-to-not-echo', 'verifier-to-not-echo', 'synthetic-private-data'):
        assert text not in response.text
    assert response.headers['cache-control'] == 'private, no-store'


def test_audit_failure_never_returns_a_summary(db, recipient, integration_client, monkeypatch):
    from app.api import integration_lifenav
    from app.services import health_week_navigation
    user = owner(db)
    _, code = create(db, user)
    token = exchange(db, code).access_token
    monkeypatch.setattr(health_week_navigation, 'build_health_week_navigation',
                        lambda *args, **kwargs: {'actions': [], 'synthetic_marker': 'must-not-return'})
    def broken_audit(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(integration_lifenav, '_audit_separately', broken_audit)
    response = integration_client.get('/api/v1/integrations/lifenav/summary',
                                      headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 503
    assert 'must-not-return' not in response.text
    assert response.headers['cache-control'] == 'private, no-store'


def test_postgresql_exchange_code_concurrent_one_winner(db, recipient):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('Requires PostgreSQL row-lock semantics')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    user = owner(db)
    _, code = create(db, user)
    barrier = Barrier(2)
    def consume():
        with Session(bind=db.get_bind()) as session:
            barrier.wait(timeout=10)
            try:
                return exchange(session, code).access_token
            except HTTPException:
                session.rollback()
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sum(value is not None for value in results) == 1
    db.expire_all()
    assert db.query(LifeNavAccessAudit).filter_by(outcome='exchanged').count() == 1


def test_postgresql_external_business_transaction_refuses_writes(db, recipient, integration_client, monkeypatch):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('Requires PostgreSQL enforced READ ONLY')
    from sqlalchemy import text
    from app.services import health_week_navigation
    user = owner(db)
    _, code = create(db, user)
    token = exchange(db, code).access_token
    def illegal_projection(read_db, user_id, **kwargs):
        read_db.execute(text('UPDATE users SET name = :name WHERE id = :id'),
                        {'name': 'should-never-persist', 'id': user_id})
        return {'actions': []}
    monkeypatch.setattr(health_week_navigation, 'build_health_week_navigation', illegal_projection)
    response = integration_client.get('/api/v1/integrations/lifenav/summary',
                                      headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 503
    db.expire_all()
    assert db.query(User).filter_by(id=user.id).one().name == 'synthetic'
    assert db.query(LifeNavAccessAudit).filter_by(outcome='unavailable').count() == 1


def test_integration_token_has_no_ordinary_health_or_write_authority(db, recipient, client, caplog):
    user = owner(db)
    _, code = create(db, user)
    token = exchange(db, code).access_token
    for headers in ({'Authorization': f'Bearer {token}'}, {'X-API-Key': token}):
        for path in ('/api/v1/twin/me', '/api/v1/user-api-keys', '/api/v1/health-navigation/grants',
                     f'/api/v1/diseases/user/{user.id}'):
            response = client.get(path, headers=headers)
            assert response.status_code in (401, 403), (path, response.status_code)
        response = client.post('/api/v1/daily-health/water', headers=headers,
                               json={'user_id': user.id, 'record_date': '2026-10-09', 'amount': 250})
        assert response.status_code in (401, 403)
    assert token not in caplog.text

def test_private_navigation_rejects_previous_account_subject(db, recipient, integration_client):
    from app.services.auth import auth_service
    user=owner(db)
    token=auth_service.create_access_token({'sub':str(user.id)})
    response=integration_client.get('/api/v1/health-navigation/grants',headers={'Authorization':'Bearer '+token,'X-Reva-AI-Subject':str(user.id+1)})
    assert response.status_code==409
