import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from app.services import edu_sso as sso

SECRET = 'synthetic-test-secret-with-at-least-32-bytes'
STATE = 'a' * 43

@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(sso, 'settings', SimpleNamespace(edu_sso_enabled=True,
        edu_sso_secret=SECRET, edu_sso_owner_id=7,
        edu_sso_origin='https://library.example.test',
        edu_sso_issuer='https://health.example.test'))
    return SimpleNamespace(id=7, is_active=True, is_approved=True, is_managed=False)

def test_ticket_is_identity_only_and_bound(configured):
    result = sso.issue_ticket(configured, STATE, 7)
    payload, signature = result['ticket'].split('.')
    expected = hmac.new(SECRET.encode(), ('edu-login-v1.' + payload).encode(), hashlib.sha256).digest()
    assert base64.urlsafe_b64decode(signature + '=') == expected
    claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    assert set(claims) == {'v', 'purpose', 'iss', 'aud', 'sub', 'state', 'iat', 'exp'}
    assert claims['purpose'] == 'edu-browser-login'
    assert claims['iss'] == 'https://health.example.test'
    assert claims['aud'] == 'https://library.example.test'
    assert claims['sub'] == '7' and claims['state'] == STATE
    assert claims['exp'] - claims['iat'] == 60
    assert result['callback_url'] == 'https://library.example.test/api/auth/health/callback'

@pytest.mark.parametrize('field,value', [('is_active',False),('is_approved',False),('is_managed',True),('id',8)])
def test_other_accounts_and_disabled_accounts_rejected(configured, field, value):
    setattr(configured, field, value)
    with pytest.raises(HTTPException): sso.issue_ticket(configured, STATE, configured.id)

def test_account_switch_is_rejected(configured):
    with pytest.raises(HTTPException): sso.issue_ticket(configured, STATE, 8)

@pytest.mark.parametrize('field,value', [('edu_sso_enabled',False),('edu_sso_secret','short'),
    ('edu_sso_origin','https://library.example.test.evil/path'),('edu_sso_issuer','http://health.example.test'),
    ('edu_sso_origin','https://user:pass@library.example.test'),('edu_sso_owner_id',0)])
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
    for name, value in dict(edu_sso_enabled=True,edu_sso_secret=SECRET,edu_sso_owner_id=7,
                           edu_sso_origin='https://library.example.test',edu_sso_issuer='https://health.example.test',
                           web_session_allowed_origins='http://testserver').items():
        monkeypatch.setattr(settings,name,value)
    token = auth_service.create_access_token({'sub':'7'})
    path='/api/v1/auth/sso/edu'
    body={'state':STATE,'expected_user_id':7}
    assert client.post(path,json=body).status_code == 401
    assert client.post(path,json=body,headers={'Authorization':f'Bearer {token}','Origin':'http://testserver'}).status_code == 403
    client.cookies.set('health_session',token)
    assert client.post(path,json=body).status_code == 403
    assert client.post(path,json=body,headers={'Origin':'https://attacker.test'}).status_code == 403
    for invalid in [{**body, 'expected_user_id': True}, {**body, 'redirect': 'https://attacker.test'}, {**body, 'state': STATE + '\n'}]:
        assert client.post(path, json=invalid, headers={'Origin': 'http://testserver'}).status_code == 422
    response=client.post(path,json=body,headers={'Origin':'http://testserver'})
    assert response.status_code == 200
    assert response.headers['cache-control']=='no-store'
    assert 'ticket' in response.json()
    from app.models.agent_audit_log import AgentAuditLog
    audit = db.query(AgentAuditLog).filter_by(action='login_ticket_issued').one()
    assert audit.user_id == 7
    assert audit.result_detail == {'audience':'edu','ttl_seconds':60}
    assert STATE not in str(audit.result_detail)
    assert client.post(path,json={**body,'expected_user_id':8},headers={'Origin':'http://testserver'}).status_code == 403


def test_proxy_and_api_key_cannot_issue_ticket(configured):
    import asyncio
    from starlette.requests import Request
    from starlette.responses import Response
    from app.api.auth import edu_login_ticket
    for auth_type, proxy in [('api_key',False),('cookie',True),('jwt',False)]:
        request=Request({'type':'http','method':'POST','path':'/api/v1/auth/sso/edu','headers':[], 'client':('127.0.0.1',1)})
        request.state.auth_type=auth_type; request.state.is_proxy_mode=proxy
        with pytest.raises(HTTPException) as error:
            asyncio.run(edu_login_ticket.__wrapped__(request,Response(),{'state':STATE,'expected_user_id':7},configured))
        assert error.value.status_code == 403


@pytest.mark.parametrize('body', [
    {'state': STATE, 'expected_user_id': True},
    {'state': STATE, 'expected_user_id': '7'},
    {'state': STATE, 'expected_user_id': 7.0},
    {'state': STATE, 'expected_user_id': 0},
    {'state': STATE, 'expected_user_id': 7, 'redirect': 'https://attacker.test'},
    {'state': STATE + '\n', 'expected_user_id': 7},
    {'state': 123, 'expected_user_id': 7},
])
def test_request_contract_rejects_coercion_and_untrusted_fields(body):
    from app.schemas.auth import EduLoginTicketRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EduLoginTicketRequest.model_validate(body)


def test_native_ticket_is_domain_separated_and_has_no_callback(configured):
    result = sso.issue_native_ticket(configured, STATE, 7)
    assert set(result) == {'ticket'}
    payload, signature = result['ticket'].split('.')
    expected = hmac.new(SECRET.encode(), ('edu-native-login-v1.' + payload).encode(), hashlib.sha256).digest()
    assert base64.urlsafe_b64decode(signature + '=') == expected
    claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    assert claims == dict(v=1, purpose='edu-native-login', iss='https://health.example.test',
        aud='https://library.example.test', sub='7', state=STATE, iat=claims['iat'], exp=claims['iat'] + 60)


def test_native_endpoint_requires_personal_bearer_jwt(client, db, monkeypatch):
    from app.models.user import User
    from app.services.auth import auth_service
    from app.config import settings
    user = User(id=7, name='Synthetic native owner', is_active=True, is_approved=True)
    other = User(id=8, name='Synthetic other owner', is_active=True, is_approved=True)
    db.add_all([user, other]); db.commit()
    for name, value in dict(edu_sso_enabled=True,edu_sso_secret=SECRET,edu_sso_owner_id=7,
                           edu_sso_origin='https://library.example.test',edu_sso_issuer='https://health.example.test',
                           web_session_allowed_origins='http://testserver').items():
        monkeypatch.setattr(settings,name,value)
    token = auth_service.create_access_token({'sub':'7'})
    path='/api/v1/auth/sso/edu/native'
    body={'state':STATE,'expected_user_id':7}
    assert client.post(path,json=body).status_code == 401
    client.cookies.set('health_session',token)
    assert client.post(path,json=body,headers={'Origin':'http://testserver'}).status_code == 403
    client.cookies.clear()
    headers={'Authorization':f'Bearer {token}'}
    response=client.post(path,json=body,headers=headers)
    assert response.status_code == 200
    assert response.headers['cache-control']=='no-store'
    assert set(response.json()) == {'ticket'}
    assert client.post(path,json={**body,'expected_user_id':True},headers=headers).status_code == 422
    assert client.post(path,json={**body,'state':STATE+'\n'},headers=headers).status_code == 422
    assert client.post(path,json={**body,'expected_user_id':8},headers=headers).status_code == 403
    other_token = auth_service.create_access_token({'sub':'8'})
    assert client.post(path,json={**body,'expected_user_id':8},headers={'Authorization':f'Bearer {other_token}'}).status_code == 403
    from app.models.agent_audit_log import AgentAuditLog
    audit = db.query(AgentAuditLog).filter_by(specialist_name='edu_native_login').one()
    assert audit.user_id == 7 and audit.result_detail == {'audience':'edu','transport':'native','ttl_seconds':60}
    assert STATE not in str(audit.result_detail)


@pytest.mark.parametrize('auth_type,proxy', [('api_key',False),('jwt',True),('cookie',False)])
def test_native_rejects_cookie_api_key_and_proxy(configured, auth_type, proxy):
    import asyncio
    from starlette.requests import Request
    from starlette.responses import Response
    from app.api.auth import edu_native_login_ticket
    from app.schemas.auth import EduLoginTicketRequest
    request=Request({'type':'http','method':'POST','path':'/api/v1/auth/sso/edu/native','headers':[], 'client':('127.0.0.1',1)})
    request.state.auth_type=auth_type; request.state.is_proxy_mode=proxy
    with pytest.raises(HTTPException) as error:
        asyncio.run(edu_native_login_ticket.__wrapped__(request,Response(),EduLoginTicketRequest(state=STATE,expected_user_id=7),configured))
    assert error.value.status_code == 403


@pytest.mark.parametrize('case', ['personal', 'tampered', 'expired', 'proxy', 'null_proxy', 'original_user', 'wrong_subject', 'missing_exp'])
def test_activation_uses_real_health_decoder_for_personal_session(case):
    import importlib.util
    import os
    from pathlib import Path
    import subprocess
    import sys
    import time
    import jwt
    backend = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('edu_activation_proof', backend.parent / 'scripts/trusted_edu_login.py')
    operator = importlib.util.module_from_spec(spec); spec.loader.exec_module(operator)
    secret = 'synthetic-only-health-activation-jwt-test-key'
    claims = {'sub':'7','exp':int(time.time())+60}
    if case == 'expired': claims['exp'] = int(time.time())-60
    if case == 'proxy': claims['acting_as'] = 7
    if case == 'null_proxy': claims['acting_as'] = None
    if case == 'original_user': claims['original_user'] = None
    if case == 'wrong_subject': claims['sub'] = '8'
    if case == 'missing_exp': del claims['exp']
    token = jwt.encode(claims, secret if case != 'tampered' else 'another-synthetic-key-with-32-characters', algorithm='HS256')
    code = operator.JWT_PROOF_CODE.replace('/opt/health-app/backend', str(backend))
    result = subprocess.run([sys.executable,'-I','-B','-c',code,'7'], input=token.encode(),
        cwd=backend, env={**os.environ,'SECRET_KEY':secret,'DATABASE_URL':'sqlite:///:memory:',
                         'GARMIN_ENCRYPTION_KEY':'mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU='},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert result.returncode == (0 if case == 'personal' else 1)
    assert token.encode() not in result.stdout + result.stderr
    assert result.stdout == b''
