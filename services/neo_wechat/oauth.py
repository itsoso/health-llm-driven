"""Independent public-client OAuth authority; never accepts Health or Site tokens."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCOPES = frozenset({'wechat:inbox', 'wechat:reply', 'health:read'})
ACCESS_SECONDS = 600
REFRESH_SECONDS = 30 * 86400
GRANT_SECONDS = 3650 * 86400


class OAuthError(ValueError):
    pass


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    owner: str = Field(min_length=1, max_length=128, pattern=r'^[a-zA-Z0-9_-]+$')
    origin: str = Field(max_length=250)
    client_id: str = Field(min_length=1, max_length=128, pattern=r'^[a-zA-Z0-9_.-]+$')
    redirect_uri: str = Field(max_length=500)

    @model_validator(mode='after')
    def urls(self):
        for uri in (self.origin, self.redirect_uri):
            parsed = urlsplit(uri)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or '*' in uri or any(ord(c) < 33 for c in uri)):
                raise ValueError('exact_https_url_required')
        if urlsplit(self.origin).path or self.origin.endswith('/'):
            raise ValueError('origin_required')
        return self

    @property
    def issuer(self):
        return self.origin + '/neo-wechat'

    @property
    def resource(self):
        return self.issuer + '/mcp'


class Authorization(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    client_id: str
    redirect_uri: str
    response_type: str
    resource: str
    scope: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=512)
    code_challenge_method: str
    code_challenge: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class OAuth:
    def __init__(self, store, key, config, clock=time.time):
        if len(key) != 32 or store.owner != config.owner:
            raise OAuthError('authority_configuration_invalid')
        self.store, self.config, self.clock = store, config, clock
        self.key = hmac.digest(key, ('neo-wechat-oauth-v1|' + config.issuer).encode(), 'sha256')

    def _data(self, state):
        auth = state['oauth']
        for name in ('pending', 'codes', 'grants'):
            auth.setdefault(name, {})
        return auth

    def _prune(self, data):
        now = self.clock()
        for name in ('pending', 'codes', 'grants'):
            data[name] = {k: v for k, v in data[name].items() if v['expires'] > now}
        if any(len(data[name]) >= limit for name, limit in [('pending', 50), ('codes', 50), ('grants', 20)]):
            raise OAuthError('authorization_capacity')

    def authorize(self, params):
        try:
            a = Authorization.model_validate(params)
        except ValidationError:
            raise OAuthError('invalid_request') from None
        if (a.client_id != self.config.client_id or a.redirect_uri != self.config.redirect_uri
                or a.resource != self.config.resource or a.response_type != 'code'
                or a.code_challenge_method != 'S256'):
            raise OAuthError('invalid_request')
        scopes = a.scope.split(' ')
        if len(set(scopes)) != len(scopes) or not set(scopes) <= SCOPES:
            raise OAuthError('invalid_scope')
        raw = secrets.token_urlsafe(32)
        with self.store.transaction() as state:
            data = self._data(state)
            self._prune(data)
            data['pending'][digest(raw)] = {**a.model_dump(), 'expires': self.clock() + 300}
        return raw

    def preview(self, raw):
        data = self._data(self.store.read())
        row = data['pending'].get(digest(raw))
        if not row or row['expires'] <= self.clock():
            raise OAuthError('request_expired')
        return {'client_id': self.config.client_id, 'scope': row['scope'], 'grant_days': 3650}

    def consent(self, raw, owner, approved):
        if owner != self.config.owner or type(approved) is not bool:
            raise OAuthError('owner_required')
        with self.store.transaction() as state:
            data = self._data(state)
            request = data['pending'].pop(digest(raw), None)
            if not request or request['expires'] <= self.clock():
                raise OAuthError('request_expired')
            callback = {'state': request['state'], 'iss': self.config.issuer}
            if not approved:
                return {**callback, 'error': 'access_denied'}
            if len(data['grants']) >= 20:
                raise OAuthError('authorization_capacity')
            ident = secrets.token_hex(16)
            data['grants'][ident] = {'owner': owner, 'client': self.config.client_id,
                'resource': self.config.resource, 'scope': request['scope'],
                'expires': self.clock() + GRANT_SECONDS, 'revoked': False, 'refresh': None}
            code = secrets.token_urlsafe(32)
            data['codes'][digest(code)] = {**request, 'grant_id': ident,
                'expires': self.clock() + 60, 'used': False}
            return {**callback, 'code': code}

    def _grant(self, data, ident):
        grant = data['grants'].get(ident)
        if (not grant or grant['revoked'] or grant['expires'] <= self.clock()
                or grant['owner'] != self.config.owner or grant['client'] != self.config.client_id
                or grant['resource'] != self.config.resource):
            raise OAuthError('invalid_grant')
        return grant

    def _token(self, kind, ident, expiry):
        payload = b64(json.dumps([kind, ident, int(expiry), secrets.token_hex(16)], separators=(',', ':')).encode())
        return payload + '.' + b64(hmac.digest(self.key, payload.encode(), 'sha256'))

    def _decode(self, raw, kind):
        if not isinstance(raw, str) or len(raw) > 512 or raw.count('.') != 1:
            raise OAuthError('invalid_token')
        payload, signature = raw.split('.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', payload) or not hmac.compare_digest(
                signature, b64(hmac.digest(self.key, payload.encode(), 'sha256'))):
            raise OAuthError('invalid_token')
        try:
            token_kind, ident, expiry, nonce = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        except (ValueError, TypeError):
            raise OAuthError('invalid_token') from None
        if token_kind != kind or type(expiry) is not int or not isinstance(ident, str):
            raise OAuthError('invalid_token')
        return ident, expiry

    def _issue(self, data, ident):
        grant = self._grant(data, ident)
        access_expiry = min(self.clock() + ACCESS_SECONDS, grant['expires'])
        refresh_expiry = min(self.clock() + REFRESH_SECONDS, grant['expires'])
        access, refresh = self._token('access', ident, access_expiry), self._token('refresh', ident, refresh_expiry)
        grant['refresh'] = digest(refresh)
        return {'access_token': access, 'token_type': 'Bearer', 'expires_in': int(access_expiry - self.clock()),
                'refresh_token': refresh, 'scope': grant['scope']}

    def exchange(self, params):
        if (params.get('client_id') != self.config.client_id
                or params.get('resource') != self.config.resource):
            raise OAuthError('invalid_client_or_target')
        kind = params.get('grant_type')
        common = {'client_id', 'resource', 'grant_type'}
        allowed = common | ({'code', 'code_verifier', 'redirect_uri'} if kind == 'authorization_code' else {'refresh_token', 'scope'})
        if set(params) - allowed:
            raise OAuthError('invalid_request')
        error = None
        result = None
        with self.store.transaction() as state:
            data = self._data(state)
            if kind == 'authorization_code':
                row = data['codes'].get(digest(params.get('code', '')))
                if not row or row['expires'] <= self.clock():
                    raise OAuthError('invalid_grant')
                grant = self._grant(data, row['grant_id'])
                if row['used']:
                    grant['revoked'] = True
                    error = 'code_replay_revoked'
                else:
                    verifier = params.get('code_verifier', '')
                    if (not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}', verifier)
                            or params.get('redirect_uri') != self.config.redirect_uri
                            or not hmac.compare_digest(b64(hashlib.sha256(verifier.encode()).digest()), row['code_challenge'])):
                        raise OAuthError('invalid_grant')
                    row['used'] = True
                    result = self._issue(data, row['grant_id'])
            elif kind == 'refresh_token':
                raw = params.get('refresh_token', '')
                ident, expiry = self._decode(raw, 'refresh')
                grant = self._grant(data, ident)
                if not hmac.compare_digest(grant['refresh'] or '', digest(raw)):
                    grant['revoked'] = True
                    error = 'refresh_replay_revoked'
                elif expiry <= self.clock():
                    raise OAuthError('invalid_grant')
                elif params.get('scope', grant['scope']) != grant['scope']:
                    raise OAuthError('invalid_scope')
                else:
                    result = self._issue(data, ident)
            else:
                raise OAuthError('unsupported_grant_type')
        if error:
            raise OAuthError(error)
        return result

    def validate(self, raw, scope):
        ident, expiry = self._decode(raw, 'access')
        grant = self._grant(self._data(self.store.read()), ident)
        if expiry <= self.clock() or scope not in grant['scope'].split():
            raise OAuthError('invalid_token_or_scope')
        return {'owner': grant['owner'], 'grant_id': ident, 'scope': grant['scope']}

    def revoke(self, raw, client_id):
        if client_id != self.config.client_id:
            raise OAuthError('invalid_client')
        for kind in ('access', 'refresh'):
            try:
                ident, _ = self._decode(raw, kind)
                break
            except OAuthError:
                continue
        else:
            return
        with self.store.transaction() as state:
            grant = self._data(state)['grants'].get(ident)
            if grant:
                grant['revoked'] = True

    def revoke_all(self, owner):
        if owner != self.config.owner:
            raise OAuthError('owner_required')
        with self.store.transaction() as state:
            data = self._data(state)
            for grant in data['grants'].values():
                grant['revoked'] = True
            data['codes'].clear()
            data['pending'].clear()
