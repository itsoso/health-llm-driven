"""Fixed upstreams, bounded IO, no redirects/proxies/body diagnostics."""
import base64
import json
import re
import secrets
import time
from urllib.parse import urlsplit, urlencode
import httpx

SIGNAL = 'Neo 有新的微信消息，请读取微信桥接收件箱。'
ILINK = 'https://ilinkai.weixin.qq.com'


class TransportError(ValueError):
    pass


def validate_webhook(url):
    if not isinstance(url, str) or not re.fullmatch(
            r'https://hooks\.slack\.com/services/T6TNPEFLY/[A-Za-z0-9]+/[A-Za-z0-9_-]+', url):
        raise TransportError('webhook_configuration_invalid')
    return url


class Transport:
    def __init__(self, version, client=None):
        if not re.fullmatch(r'\d{1,3}\.\d{1,3}\.\d{1,3}', version):
            raise TransportError('version_invalid')
        parts = [int(x) for x in version.split('.')]
        if any(x > 255 for x in parts):
            raise TransportError('version_invalid')
        self.version = version
        self.number = (parts[0] << 16) | (parts[1] << 8) | parts[2]
        self.client = client or httpx.Client(trust_env=False, follow_redirects=False,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2))

    def request(self, method, url, *, headers=None, body=None, timeout=8, raw=False):
        started = time.monotonic()
        try:
            with self.client.stream(method, url, headers=headers,
                content=None if body is None else json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode(),
                timeout=httpx.Timeout(timeout, connect=5, pool=2), follow_redirects=False) as response:
                if response.status_code != 200:
                    raise TransportError('upstream_http')
                result = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() - started > timeout:
                        raise TransportError('upstream_deadline')
                    result.extend(chunk)
                    if len(result) > 1048576:
                        raise TransportError('upstream_size')
            if raw:
                return bytes(result)
            data = json.loads(result)
            if not isinstance(data, dict):
                raise TransportError('upstream_format')
            return data
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            if isinstance(exc, TransportError):
                raise
            raise TransportError('upstream_unavailable') from None

    def headers(self, token=None):
        headers = {'Content-Type': 'application/json', 'iLink-App-Id': 'bot',
                   'iLink-App-ClientVersion': str(self.number)}
        if token is not None:
            headers.update(Authorization='Bearer ' + token, AuthorizationType='ilink_bot_token',
                           **{'X-WECHAT-UIN': base64.b64encode(str(secrets.randbits(32)).encode()).decode()})
        return headers

    def bot(self, operation, token, payload, timeout=8):
        return self.request('POST', ILINK + '/ilink/bot/' + operation, headers=self.headers(token),
            body={**payload, 'base_info': {'channel_version': self.version, 'bot_agent': 'NeoHealthBridge/1'}}, timeout=timeout)

    def updates(self, token, cursor):
        return self.bot('getupdates', token, {'get_updates_buf': cursor}, timeout=35)

    def send(self, token, peer, context, text, client_id):
        result = self.bot('sendmessage', token, {'msg': {'from_user_id': '', 'to_user_id': peer,
            'client_id': client_id, 'message_type': 2, 'message_state': 2, 'context_token': context,
            'item_list': [{'type': 1, 'text_item': {'text': text}}]}})
        return 'confirmed' if type(result.get('ret')) is int and result['ret'] == 0 and (
            'errcode' not in result or type(result['errcode']) is int and result['errcode'] == 0) else 'uncertain'

    def qr(self):
        return self.request('POST', ILINK + '/ilink/bot/get_bot_qrcode?bot_type=3',
                            headers=self.headers(), body={'local_token_list': []})

    def poll_qr(self, qr):
        return self.request('GET', ILINK + '/ilink/bot/get_qrcode_status?' + urlencode({'qrcode': qr}),
                            headers=self.headers())

    def notify(self, webhook):
        result = self.request('POST', validate_webhook(webhook), headers={'Content-Type': 'application/json'},
                              body={'text': SIGNAL}, raw=True)
        return result == b'ok'
