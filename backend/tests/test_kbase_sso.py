import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app.services import kbase_sso as sso

SECRET = 'synthetic-test-secret-with-at-least-32-bytes'
STATE = 'a' * 43

@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(sso, 'settings', SimpleNamespace(kbase_sso_enabled=True,
        kbase_sso_secret=SECRET, kbase_sso_owner_id=7,
        kbase_sso_origin='https://library.example.test',
        kbase_sso_issuer='https://health.example.test'))
    return SimpleNamespace(id=7, is_active=True, is_approved=True, is_managed=False)

def test_ticket_is_identity_only_and_bound(configured):
    result = sso.issue_ticket(configured, STATE, 7)
    payload, signature = result['ticket'].split('.')
    expected = hmac.new(SECRET.encode(), ('kbase-login-v1.' + payload).encode(), hashlib.sha256).digest()
    assert base64.urlsafe_b64decode(signature + '=') == expected
    claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    assert set(claims) == {'v', 'purpose', 'iss', 'aud', 'sub', 'state', 'iat', 'exp'}
    assert claims['sub'] == '7' and claims['state'] == STATE
    assert claims['exp'] - claims['iat'] == 60
    assert result['callback_url'] == 'https://library.example.test/browser/health/callback'

@pytest.mark.parametrize('field,value', [('is_active',False),('is_approved',False),('is_managed',True),('id',8)])
def test_other_accounts_and_disabled_accounts_rejected(configured, field, value):
    setattr(configured, field, value)
    with pytest.raises(HTTPException): sso.issue_ticket(configured, STATE, configured.id)

def test_account_switch_is_rejected(configured):
    with pytest.raises(HTTPException): sso.issue_ticket(configured, STATE, 8)

@pytest.mark.parametrize('field,value', [('kbase_sso_enabled',False),('kbase_sso_secret','short'),
    ('kbase_sso_origin','https://library.example.test.evil/path'),('kbase_sso_issuer','http://health.example.test'),
    ('kbase_sso_origin','https://user:pass@library.example.test'),('kbase_sso_owner_id',0)])
def test_bad_configuration_fails_closed(configured, field, value):
    setattr(sso.settings,field,value)
    with pytest.raises(HTTPException): sso.issue_ticket(configured, STATE, 7)

@pytest.mark.parametrize('state', ['', 'a'*42, 'a'*44, 'x\n'+'a'*41])
def test_bad_state_rejected(configured, state):
    with pytest.raises(HTTPException): sso.issue_ticket(configured,state,7)


def test_real_cookie_endpoint_and_machine_token_boundary(client, db, monkeypatch):
    from app.models.user import User
    from app.services.auth import auth_service
    from app.config import settings
    user = User(id=7, name='SSO synthetic owner', is_active=True, is_approved=True)
    db.add(user); db.commit()
    for name, value in dict(kbase_sso_enabled=True,kbase_sso_secret=SECRET,kbase_sso_owner_id=7,
                           kbase_sso_origin='https://library.example.test',kbase_sso_issuer='https://health.example.test',
                           web_session_allowed_origins='http://testserver').items():
        monkeypatch.setattr(settings,name,value)
    token = auth_service.create_access_token({'sub':'7'})
    path='/api/v1/auth/sso/kbase'
    body={'state':STATE,'expected_user_id':7}
    assert client.post(path,json=body).status_code == 401
    assert client.post(path,json=body,headers={'Authorization':f'Bearer {token}','Origin':'http://testserver'}).status_code == 403
    client.cookies.set('health_session',token)
    assert client.post(path,json=body).status_code == 403
    assert client.post(path,json=body,headers={'Origin':'https://attacker.test'}).status_code == 403
    response=client.post(path,json=body,headers={'Origin':'http://testserver'})
    assert response.status_code == 200
    assert response.headers['cache-control']=='no-store'
    assert 'ticket' in response.json()
    from app.models.agent_audit_log import AgentAuditLog
    audit = db.query(AgentAuditLog).filter_by(action='login_ticket_issued').one()
    assert audit.user_id == 7
    assert audit.result_detail == {'audience':'kbase','ttl_seconds':60}
    assert STATE not in str(audit.result_detail)
    assert client.post(path,json={**body,'expected_user_id':8},headers={'Origin':'http://testserver'}).status_code == 403


def test_proxy_and_api_key_cannot_issue_ticket(configured):
    import asyncio
    from starlette.requests import Request
    from starlette.responses import Response
    from app.api.auth import kbase_login_ticket
    for auth_type, proxy in [('api_key',False),('cookie',True),('jwt',False)]:
        request=Request({'type':'http','method':'POST','path':'/api/v1/auth/sso/kbase','headers':[], 'client':('127.0.0.1',1)})
        request.state.auth_type=auth_type; request.state.is_proxy_mode=proxy
        with pytest.raises(HTTPException) as error:
            asyncio.run(kbase_login_ticket.__wrapped__(request,Response(),{'state':STATE,'expected_user_id':7},configured))
        assert error.value.status_code == 403
