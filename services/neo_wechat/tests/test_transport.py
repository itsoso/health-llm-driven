import httpx
import pytest
from services.neo_wechat.transport import Transport, TransportError, validate_webhook


def test_webhook_restricts_workspace_and_host():
    validate_webhook('https://hooks.slack.com/services/T6TNPEFLY/B123/abcdefgh')
    for url in ['https://evil.example/services/T6TNPEFLY/B123/abcdefgh',
                'https://hooks.slack.com/services/TOTHER/B123/abcdefgh',
                'http://hooks.slack.com/services/T6TNPEFLY/B123/abcdefgh',
                'https://hooks.slack.com@evil.example/x']:
        with pytest.raises(TransportError): validate_webhook(url)


def test_generic_payload_and_no_redirect():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, text='ok')
    transport = Transport('2.4.9', httpx.Client(transport=httpx.MockTransport(handler)))
    assert transport.notify('https://hooks.slack.com/services/T6TNPEFLY/B123/abcdefgh')
    assert seen[0].content == '{"text":"Neo 有新的微信消息，请读取微信桥接收件箱。"}'.encode()
    assert 'authorization' not in seen[0].headers


def test_redirect_rejected_and_upstream_error_redacted():
    transport = Transport('2.4.9', httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(302, headers={'location': 'https://evil.example/secret'}))))
    with pytest.raises(TransportError, match='upstream_http'):
        transport.updates('synthetic-token', '')
