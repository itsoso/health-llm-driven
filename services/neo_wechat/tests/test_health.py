import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from services.neo_wechat.health import HealthClient, HealthError, HealthTransport
from services.neo_wechat.store import Store


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.response = {'access_token': 'a' * 43, 'refresh_token': 'r' * 43,
                         'token_type': 'Bearer', 'expires_in': 600, 'scope': 'health:read'}
        self.failure = False
        self.before = None
        self.responses = []

    def request(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.before:
            self.before()
        if self.failure:
            raise RuntimeError('SECRET_UPSTREAM_BODY')
        return dict(self.responses.pop(0) if self.responses else self.response)


@pytest.fixture
def linked(tmp_path):
    path = tmp_path / 'state'
    path.mkdir(mode=0o700)
    with Store(path, b'k' * 32, 'owner') as store:
        clock = [10000]
        transport = FakeTransport()
        client = HealthClient(store, transport, 'https://health.example', 'bridge-health', clock=lambda: clock[0])
        yield client, transport, clock


def connect(client):
    params = parse_qs(urlsplit(client.begin()).query)
    client.complete(params['state'][0], 'c' * 43, client.issuer)
    return params


def test_fresh_pkce_and_fixed_resource_are_encrypted(linked):
    client, transport, _ = linked
    params = connect(client)
    form = transport.calls[0][1]['form']
    assert transport.calls[0][0] == client.issuer + '/token'
    assert params['code_challenge_method'] == ['S256']
    assert params['code_challenge'][0] == base64.urlsafe_b64encode(
        hashlib.sha256(form['code_verifier'].encode()).digest()).decode().rstrip('=')
    assert form['resource'] == client.resource
    assert form['redirect_uri'] == 'https://health.example/neo-wechat/admin/health/callback'
    assert client.status() == 'connected'
    assert b'a' * 43 not in (client.store.path / 'state.enc').read_bytes()


@pytest.mark.parametrize('failure', ['state', 'issuer', 'expiry', 'unicode'])
def test_callback_binding_fails_without_token_call(linked, failure):
    client, transport, clock = linked
    params = parse_qs(urlsplit(client.begin()).query)
    state, issuer = params['state'][0], client.issuer
    if failure == 'state': state = 'bad'
    if failure == 'unicode': state = '私' * 43
    if failure == 'issuer': issuer = 'https://evil.example'
    if failure == 'expiry': clock[0] += 301
    with pytest.raises(HealthError): client.complete(state, 'c' * 43, issuer)
    assert transport.calls == []


def test_code_is_one_use_and_uncertain_exchange_is_not_retried(linked):
    client, transport, _ = linked
    state = parse_qs(urlsplit(client.begin()).query)['state'][0]
    transport.failure = True
    transport.before = lambda: assert_relink(client)
    with pytest.raises(HealthError, match='health_unavailable'):
        client.complete(state, 'c' * 43, client.issuer)
    assert client.status() == 'relink_required'
    with pytest.raises(HealthError): client.complete(state, 'c' * 43, client.issuer)
    assert len(transport.calls) == 1


def assert_relink(client):
    assert client.status() == 'relink_required'


def test_query_only_fixed_rpc_and_typed_arguments(linked):
    client, transport, _ = linked
    connect(client)
    transport.response = {'jsonrpc': '2.0', 'id': 1, 'result': {'structuredContent': {'records': []}}}
    args = {'start_date': '2026-01-01', 'end_date': '2026-01-02', 'timezone': 'UTC'}
    assert client.query('get_sleep', args) == {'structuredContent': {'records': []}}
    url, request = transport.calls[-1]
    assert url == client.resource
    assert request['body'] == {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                               'params': {'name': 'get_sleep', 'arguments': args}}
    assert request['token'] == 'a' * 43
    for tool, invalid in [('write_health', args), ('get_sleep', {**args, 'user_id': 7}),
                          ('get_sleep', {**args, 'timezone': '../bad'}),
                          ('get_sleep', {**args, 'start_date': True})]:
        before = len(transport.calls)
        with pytest.raises(HealthError): client.query(tool, invalid)
        assert len(transport.calls) == before


def test_refresh_uncertainty_is_durable_and_does_not_retry(linked):
    client, transport, clock = linked
    connect(client)
    clock[0] += 601
    transport.failure = True
    transport.before = lambda: assert_relink(client)
    args = {'start_date': '2026-01-01', 'end_date': '2026-01-02', 'timezone': 'UTC'}
    with pytest.raises(HealthError): client.query('get_sleep', args)
    assert client.status() == 'relink_required'
    with pytest.raises(HealthError): client.query('get_sleep', args)
    assert len(transport.calls) == 2
    assert transport.calls[-1][1]['form']['grant_type'] == 'refresh_token'


def test_successful_refresh_rotates_before_health_query(linked):
    client, transport, clock = linked
    connect(client)
    clock[0] += 601
    transport.responses = [
        {**transport.response, 'access_token': 'b' * 43, 'refresh_token': 's' * 43},
        {'jsonrpc': '2.0', 'id': 1, 'result': {'structuredContent': {'records': []}}},
    ]
    client.query('get_diet', {'start_date': '2026-01-01', 'end_date': '2026-01-02', 'timezone': 'UTC'})
    assert transport.calls[-1][1]['token'] == 'b' * 43
    assert client.store.read()['health']['refresh_token'] == 's' * 43


def test_restart_preserves_uncertain_state_and_requires_explicit_revoke(linked):
    client, transport, _ = linked
    state = parse_qs(urlsplit(client.begin()).query)['state'][0]
    transport.failure = True
    with pytest.raises(HealthError): client.complete(state, 'c' * 43, client.issuer)
    path = client.store.path
    client.store.close()
    with Store(path, b'k' * 32, 'owner') as reopened:
        resumed = HealthClient(reopened, transport, 'https://health.example', 'bridge-health')
        assert resumed.status() == 'relink_required'
        with pytest.raises(HealthError): resumed.begin()
        resumed.revoke()
        assert resumed.status() == 'disconnected'
    assert len(transport.calls) == 1


def test_local_revoke_survives_upstream_uncertainty(linked):
    client, transport, _ = linked
    connect(client)
    transport.failure = True
    with pytest.raises(HealthError): client.revoke()
    assert client.status() == 'disconnected'
    assert transport.calls[-1][0] == client.issuer + '/revoke'
    assert 'access_token' not in str(client.store.read().get('health'))
    client.revoke()
    assert len(transport.calls) == 2


def test_health_audit_records_authority_and_reads_without_content(linked):
    client, transport, _ = linked
    connect(client)
    transport.response = {'jsonrpc': '2.0', 'id': 1, 'result': {
        'structuredContent': {'records': [{'private_health_value': 123}]}}}
    client.query('get_sleep', {'start_date': '2026-01-01',
        'end_date': '2026-01-02', 'timezone': 'UTC'})
    client.revoke()
    entries = client.store.read()['audit']
    assert [entry['event'] for entry in entries] == [
        'health_consent_started', 'health_code_exchange_reserved',
        'health_tokens_saved', 'health_read_requested', 'health_read_completed',
        'health_connection_revoked']
    assert all(set(entry) == {'event', 'at'} for entry in entries)
    assert all(entry['at'] == 10000 for entry in entries)
    serialized = str(entries)
    assert 'private_health_value' not in serialized
    assert '2026-01-01' not in serialized
    assert 'a' * 43 not in serialized and 'r' * 43 not in serialized


@pytest.mark.parametrize('response', [
    {'access_token': 'a' * 43, 'refresh_token': 'r' * 43, 'scope': 'health:write', 'expires_in': 600, 'token_type': 'Bearer'},
    {'access_token': 'a' * 43, 'refresh_token': 'r' * 43, 'scope': 'health:read', 'expires_in': 3650 * 86400, 'token_type': 'Bearer'},
    {'access_token': 'a' * 43, 'refresh_token': 'r' * 43, 'scope': 'health:read', 'expires_in': 600, 'token_type': 123},
])
def test_malformed_or_overbroad_token_response_requires_relink(linked, response):
    client, transport, _ = linked
    transport.response = response
    with pytest.raises(HealthError): connect(client)
    assert client.status() == 'relink_required'


def test_http_transport_form_headers_redirects_and_private_errors():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={'Location': 'https://evil.example'}, text='SECRET')
    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    transport = HealthTransport(client)
    with pytest.raises(HealthError) as error:
        transport.request('https://health.example/token', form={'code': 'private'})
    assert 'SECRET' not in str(error.value)
    assert len(seen) == 1
    assert seen[0].headers['content-type'] == 'application/x-www-form-urlencoded'


@pytest.mark.parametrize('content', [b'{"token":1,"token":2}', b'{"number":NaN}', b'x' * 131073])
def test_http_transport_rejects_ambiguous_or_large_response(content):
    transport = HealthTransport(httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=content)), trust_env=False))
    with pytest.raises(HealthError): transport.request('https://health.example/token', form={})
