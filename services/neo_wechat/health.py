"""Fresh, owner-consented Health OAuth upstream; no Health database or app secrets."""
import base64
from datetime import date
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx


class HealthError(ValueError):
    """Only fixed, non-sensitive errors cross this boundary."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise HealthError('health_response_invalid')
        result[key] = value
    return result


class HealthTransport:
    def __init__(self, client=None):
        self.client = client or httpx.Client(trust_env=False, follow_redirects=False,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1))

    def request(self, url, *, form=None, body=None, token=None):
        headers = {'Accept': 'application/json, text/event-stream'}
        if form is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            content = urlencode(form).encode()
        else:
            headers.update({'Content-Type': 'application/json', 'MCP-Protocol-Version': '2025-11-25'})
            content = json.dumps(body, allow_nan=False, separators=(',', ':')).encode()
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        try:
            with self.client.stream('POST', url, content=content, headers=headers,
                    follow_redirects=False, timeout=httpx.Timeout(10, connect=5, pool=2)) as response:
                if response.status_code != 200:
                    raise HealthError('health_unavailable')
                raw = bytearray()
                for part in response.iter_bytes():
                    raw.extend(part)
                    if len(raw) > 131072:
                        raise HealthError('health_response_too_large')
            value = json.loads(raw, object_pairs_hook=_object,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise HealthError('health_response_invalid')
            return value
        except (httpx.HTTPError, ValueError, UnicodeError, RecursionError):
            raise HealthError('health_unavailable') from None


class HealthClient:
    def __init__(self, store, transport, origin, client_id, clock=time.time):
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query
                or parsed.fragment or parsed.username or parsed.password or '*' in origin
                or any(ord(c) < 33 or ord(c) > 126 for c in origin)
                or not re.fullmatch(r'[A-Za-z0-9._-]{1,200}', client_id)):
            raise HealthError('health_configuration_invalid')
        self.store, self.transport, self.clock = store, transport, clock
        self.issuer = origin + '/api/v1/remote-health'
        self.resource = self.issuer + '/mcp'
        self.callback = origin + '/neo-wechat/admin/health/callback'
        self.client_id = client_id

    def _binding(self):
        return {'issuer': self.issuer, 'resource': self.resource, 'client_id': self.client_id}

    def _state(self):
        state = self.store.read().get('health') or {'status': 'disconnected'}
        if state.get('status') != 'disconnected' and any(
                state.get(key) != value for key, value in self._binding().items()):
            raise HealthError('health_configuration_changed')
        return state

    def status(self):
        with self.store.lock:
            return self._state()['status']

    def begin(self):
        with self.store.lock:
            if self._state()['status'] in {'connected', 'relink_required'}:
                raise HealthError('health_revoke_required')
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            with self.store.transaction() as snapshot:
                snapshot['health'] = {**self._binding(), 'status': 'pending', 'state': state,
                    'verifier': verifier, 'expires': int(self.clock()) + 300}
            return self.issuer + '/authorize?' + urlencode({'client_id': self.client_id,
                'response_type': 'code', 'redirect_uri': self.callback, 'resource': self.resource,
                'scope': 'health:read', 'state': state, 'code_challenge_method': 'S256',
                'code_challenge': challenge})

    def _request(self, url, **kwargs):
        try:
            return self.transport.request(url, **kwargs)
        except Exception:
            raise HealthError('health_unavailable') from None

    def _save_tokens(self, response, previous_refresh=None):
        if (not isinstance(response, dict) or response.get('scope') != 'health:read'
                or not isinstance(response.get('token_type'), str) or response['token_type'].lower() != 'bearer'
                or type(response.get('expires_in')) is not int
                or not 1 <= response['expires_in'] <= 600
                or any(not isinstance(response.get(key), str) or not re.fullmatch(
                    r'[A-Za-z0-9_-]{43,128}', response[key]) for key in ('access_token', 'refresh_token'))
                or response.get('refresh_token') == previous_refresh):
            raise HealthError('health_token_invalid')
        with self.store.transaction() as snapshot:
            snapshot['health'] = {**self._binding(), 'status': 'connected',
                'access_token': response['access_token'], 'refresh_token': response['refresh_token'],
                'expires': int(self.clock()) + response['expires_in']}

    def complete(self, state, code, issuer):
        with self.store.lock:
            pending = self._state()
            if (pending['status'] != 'pending' or pending.get('expires', 0) <= self.clock()
                    or not isinstance(state, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', state)
                    or not hmac.compare_digest(pending['state'], state)
                    or issuer != self.issuer or not isinstance(code, str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{43}', code)):
                raise HealthError('health_callback_invalid')
            # A code may be consumed even if the response is lost. Durable intent
            # precedes launch; a crash or malformed response requires fresh consent.
            with self.store.transaction() as snapshot:
                snapshot['health'] = {**self._binding(), 'status': 'relink_required'}
            response = self._request(self.issuer + '/token', form={'grant_type': 'authorization_code',
                'client_id': self.client_id, 'code': code, 'code_verifier': pending['verifier'],
                'redirect_uri': self.callback, 'resource': self.resource})
            self._save_tokens(response)

    def _access(self):
        current = self._state()
        if current['status'] != 'connected':
            raise HealthError('health_not_connected')
        if current['expires'] > self.clock() + 30:
            return current['access_token']
        with self.store.transaction() as snapshot:
            snapshot['health'] = {**self._binding(), 'status': 'relink_required',
                                  'refresh_token': current['refresh_token']}
        response = self._request(self.issuer + '/token', form={'grant_type': 'refresh_token',
            'client_id': self.client_id, 'refresh_token': current['refresh_token'],
            'resource': self.resource, 'scope': 'health:read'})
        self._save_tokens(response, previous_refresh=current['refresh_token'])
        return self._state()['access_token']

    def query(self, tool, args):
        if (not isinstance(tool, str) or tool not in {'get_sleep', 'get_diet', 'get_exercise'} or not isinstance(args, dict)
                or set(args) != {'start_date', 'end_date', 'timezone'}
                or any(not isinstance(value, str) for value in args.values())
                or any(not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args[key]) for key in ('start_date', 'end_date'))
                or not 1 <= len(args['timezone']) <= 64):
            raise HealthError('health_query_invalid')
        try:
            start, end = date.fromisoformat(args['start_date']), date.fromisoformat(args['end_date'])
            ZoneInfo(args['timezone'])
            if not 0 <= (end - start).days < 31:
                raise ValueError()
        except (ValueError, ZoneInfoNotFoundError):
            raise HealthError('health_query_invalid') from None
        with self.store.lock:
            result = self._request(self.resource, token=self._access(), body={'jsonrpc': '2.0',
                'id': 1, 'method': 'tools/call', 'params': {'name': tool, 'arguments': dict(args)}})
            if (not isinstance(result, dict) or result.get('jsonrpc') != '2.0'
                    or type(result.get('id')) is not int or result['id'] != 1 or 'error' in result
                    or not isinstance(result.get('result'), dict) or result['result'].get('isError')):
                raise HealthError('health_query_unavailable')
            return result['result']

    def revoke(self):
        with self.store.lock:
            current = self._state()
            with self.store.transaction() as snapshot:
                snapshot['health'] = {'status': 'disconnected'}
            token = current.get('refresh_token')
            if token:
                self._request(self.issuer + '/revoke', form={'client_id': self.client_id, 'token': token})
