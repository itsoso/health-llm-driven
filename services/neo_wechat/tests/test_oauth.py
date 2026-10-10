import base64
import hashlib
from contextlib import contextmanager
from copy import deepcopy
import pytest

from services.neo_wechat.oauth import OAuth, OAuthError, Settings


class MemoryStore:
    owner = 'synthetic-owner'
    def __init__(self):
        self.data = {'oauth': {}}
    def read(self):
        return deepcopy(self.data)
    @contextmanager
    def transaction(self):
        value = deepcopy(self.data)
        yield value
        self.data = value


@pytest.fixture
def auth():
    now = [1000000]
    config = Settings(owner='synthetic-owner', origin='https://bridge.example',
                      client_id='neo', redirect_uri='https://client.example/callback')
    provider = OAuth(MemoryStore(), b'x' * 32, config, clock=lambda: now[0])
    return provider, now


def pending(auth, **changes):
    provider, _ = auth
    verifier = 'a' * 43
    params = dict(client_id='neo', redirect_uri=provider.config.redirect_uri,
                  response_type='code', resource=provider.config.resource,
                  scope='wechat:inbox wechat:reply', state='state',
                  code_challenge_method='S256', code_challenge=base64.urlsafe_b64encode(
                      hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='))
    return provider.authorize({**params, **changes}), verifier


def tokens(auth):
    provider, _ = auth
    request, verifier = pending(auth)
    callback = provider.consent(request, provider.config.owner, True)
    return provider.exchange(dict(grant_type='authorization_code', client_id='neo',
        resource=provider.config.resource, redirect_uri=provider.config.redirect_uri,
        code=callback['code'], code_verifier=verifier))


def test_short_access_and_long_fixed_grant(auth):
    p, now = auth
    token = tokens(auth)
    assert token['expires_in'] == 600
    claims = p.validate(token['access_token'], 'wechat:inbox')
    grant = p.store.read()['oauth']['grants'][claims['grant_id']]
    assert grant['expires'] == now[0] + 3650 * 86400
    now[0] += 601
    with pytest.raises(OAuthError): p.validate(token['access_token'], 'wechat:inbox')


def test_refresh_rotates_replay_revokes_family(auth):
    p, _ = auth
    first = tokens(auth)
    params = dict(grant_type='refresh_token', client_id='neo', resource=p.config.resource,
                  refresh_token=first['refresh_token'])
    second = p.exchange(params)
    assert first['refresh_token'] != second['refresh_token']
    with pytest.raises(OAuthError): p.exchange(params)
    with pytest.raises(OAuthError): p.validate(second['access_token'], 'wechat:inbox')


@pytest.mark.parametrize('changes', [dict(resource='https://other.example/mcp'),
    dict(redirect_uri='https://client.example/callback?evil=1'), dict(client_id='other'),
    dict(code_challenge_method='plain'), dict(scope='health:write'), dict(state='')])
def test_authorization_rejects_confused_deputy(auth, changes):
    with pytest.raises(OAuthError): pending(auth, **changes)


def test_wrong_owner_and_pkce(auth):
    p, _ = auth
    request, _ = pending(auth)
    with pytest.raises(OAuthError): p.consent(request, 'another-owner', True)
    code = p.consent(request, p.config.owner, True)['code']
    with pytest.raises(OAuthError):
        p.exchange(dict(grant_type='authorization_code', client_id='neo', resource=p.config.resource,
            redirect_uri=p.config.redirect_uri, code=code, code_verifier='b' * 43))


def test_scope_and_revoke(auth):
    p, _ = auth
    token = tokens(auth)
    with pytest.raises(OAuthError): p.validate(token['access_token'], 'health:read')
    p.revoke(token['refresh_token'], 'neo')
    with pytest.raises(OAuthError): p.validate(token['access_token'], 'wechat:reply')


def test_refresh_never_extends_grant_and_invalid_mac_cannot_revoke(auth):
    p, now = auth
    first = tokens(auth)
    with pytest.raises(OAuthError):
        p.exchange(dict(grant_type='refresh_token', client_id='neo', resource=p.config.resource,
                        refresh_token=first['refresh_token'][:-4] + 'AAAA'))
    p.validate(first['access_token'], 'wechat:inbox')
    original = p.store.read()['oauth']['grants']
    now[0] += 100
    p.exchange(dict(grant_type='refresh_token', client_id='neo', resource=p.config.resource,
                    refresh_token=first['refresh_token']))
    assert [x['expires'] for x in original.values()] == [x['expires'] for x in p.store.read()['oauth']['grants'].values()]
