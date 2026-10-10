import base64
import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import pytest
from starlette.testclient import TestClient

from services.neo_wechat.server import Config, Service
from services.neo_wechat.store import Store


class Offline:
    def __init__(self): self.calls = []
    def qr(self):
        self.calls.append('qr')
        return {'qrcode': 'synthetic', 'qrcode_img_content': 'https://synthetic.example/qr'}
    def poll_qr(self, qr):
        return {'status': 'confirmed', 'ilink_user_id': 'synthetic-peer',
                'ilink_bot_id': 'synthetic-account', 'bot_token': 'SYNTHETIC_PRIVATE_TOKEN'}
    def send(self, *args):
        self.calls.append(args)
        return 'confirmed'


@pytest.fixture
def environment(tmp_path):
    tmp_path.chmod(0o700)
    key = b's' * 32
    store = Store(tmp_path, key, 'synthetic-owner')
    config = Config(owner='synthetic-owner', origin='https://bridge.example',
                    client_id='neo', redirect_uri='https://client.example/callback', proxy_gid=123)
    password = 'synthetic-password-only'
    salt = b's' * 16
    hashed = b'scrypt-v1:' + base64.b64encode(salt) + b':' + base64.b64encode(hashlib.scrypt(
        password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32))
    transport = Offline()
    service = Service(config, store, key, hashed,
        'https://hooks.slack.com/services/T6TNPEFLY/B123/synthetic', transport)
    client = TestClient(service.app(), base_url=config.origin)
    admin = {'Authorization': 'Basic ' + base64.b64encode(('owner:' + password).encode()).decode()}
    yield service, client, admin
    client.close()
    store.close()


def csrf(client, admin):
    response = client.get('/neo-wechat/admin', headers=admin)
    assert response.status_code == 200
    return re.search(r'name="csrf" value="([^"]+)"', response.text)[1]


def test_startup_discovery_auth_and_privacy(environment):
    service, client, admin = environment
    assert service.transport.calls == []
    meta = client.get('/.well-known/oauth-authorization-server/neo-wechat')
    assert meta.status_code == 200
    assert meta.json()['code_challenge_methods_supported'] == ['S256']
    assert meta.headers['cache-control'] == 'no-store'
    denied = client.post('/neo-wechat/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    assert denied.status_code == 401
    assert 'resource_metadata=' in denied.headers['www-authenticate']
    assert client.get('/neo-wechat/admin').status_code == 401
    assert client.get('/neo-wechat/admin', headers={**admin, 'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/neo-wechat/admin', headers={**admin, 'Host': 'evil.example'}).status_code == 403
    assert service.transport.calls == []


def test_qr_requires_owner_csrf_and_explicit_confirmation(environment):
    service, client, admin = environment
    token = csrf(client, admin)
    assert client.post('/neo-wechat/admin/qr-start', headers=admin, data={'csrf': token, 'accepted': 'yes'}).status_code == 400
    assert not service.transport.calls
    origin = {**admin, 'Origin': service.config.origin}
    result = client.post('/neo-wechat/admin/qr-start', headers=origin,
                        data={'csrf': token, 'accepted': 'yes'}, follow_redirects=False)
    assert result.status_code == 303
    assert service.transport.calls == ['qr']
    login = service.binding.view()
    service.binding.poll(login['attempt'])
    assert not service.store.read()['binding']
    page = client.get('/neo-wechat/admin', headers=admin)
    assert 'SYNTHETIC_PRIVATE_TOKEN' not in page.text
    service.binding.activate(login['attempt'], 'synthetic-peer')
    assert service.bridge.binding()['peer'] == 'synthetic-peer'


def test_pkce_browser_consent_to_authenticated_mcp_and_revocation(environment):
    service, client, admin = environment
    verifier = 'v' * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    authorize = client.get('/neo-wechat/authorize', params={
        'client_id': 'neo', 'redirect_uri': service.config.redirect_uri, 'resource': service.config.resource,
        'response_type': 'code', 'scope': 'wechat:inbox wechat:reply', 'state': 'synthetic-state',
        'code_challenge_method': 'S256', 'code_challenge': challenge}, follow_redirects=False)
    assert authorize.status_code == 303
    request = parse_qs(urlsplit(authorize.headers['location']).query)['request'][0]
    preview = client.get(authorize.headers['location'], headers=admin)
    assert '3650' in preview.text
    assert "form-action 'self' https://client.example" in preview.headers['content-security-policy']
    token = re.search(r'name="csrf" value="([^"]+)"', preview.text)[1]
    approved = client.post('/neo-wechat/admin/consent', headers={**admin, 'Origin': service.config.origin},
        data={'request': request, 'approved': 'yes', 'csrf': token}, follow_redirects=False)
    assert approved.status_code == 303
    code = parse_qs(urlsplit(approved.headers['location']).query)['code'][0]
    exchange = client.post('/neo-wechat/token', data={'client_id': 'neo', 'resource': service.config.resource,
        'grant_type': 'authorization_code', 'redirect_uri': service.config.redirect_uri,
        'code': code, 'code_verifier': verifier})
    assert exchange.status_code == 200
    bearer = {'Authorization': 'Bearer ' + exchange.json()['access_token']}
    tools = client.post('/neo-wechat/mcp', headers=bearer, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    assert tools.status_code == 200
    assert len(tools.json()['result']['tools']) == 5
    initialize = client.post('/neo-wechat/mcp', headers=bearer,
        json={'jsonrpc': '2.0', 'id': 2, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25'}})
    assert initialize.json()['result']['protocolVersion'] == '2025-11-25'
    call = client.post('/neo-wechat/mcp', headers=bearer, json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
        'params': {'name': 'wechat_connection_status', '_meta': {}, 'arguments': {}}})
    assert call.json()['result']['isError'] is False
    client.post('/neo-wechat/revoke', data={'client_id': 'neo', 'token': exchange.json()['refresh_token']})
    assert client.post('/neo-wechat/mcp', headers=bearer,
        json={'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'}).status_code == 401


def test_bounded_body_duplicate_fields_and_query_token_rejected(environment):
    _, client, _ = environment
    assert client.post('/neo-wechat/mcp', content=b'x' * 16385).status_code == 413
    assert client.post('/neo-wechat/token', content='client_id=neo&client_id=neo',
        headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code == 400
    assert client.post('/neo-wechat/mcp?access_token=synthetic', json={}).status_code == 401
