import pytest
from services.neo_wechat.binding import Binding, BindingError
from services.neo_wechat.core import Bridge
from services.neo_wechat.store import Store


class Provider:
    def __init__(self):
        self.requests = 0
        self.response = {'status': 'confirmed', 'ilink_user_id': 'owner-peer',
                         'ilink_bot_id': 'new-bot', 'bot_token': 'synthetic-token'}
    def qr(self):
        self.requests += 1
        return {'qrcode': 'synthetic-code', 'qrcode_img_content': 'https://synthetic.example/qr'}
    def poll_qr(self, code): return self.response


@pytest.fixture
def setup(tmp_path):
    tmp_path.chmod(0o700)
    with Store(tmp_path, b'x' * 32, 'owner') as store:
        bridge, provider, now = Bridge(store), Provider(), [1000]
        flow = Binding(store, bridge, provider, clock=lambda: now[0])
        yield store, bridge, provider, now, flow


def test_fresh_qr_requires_confirmation_and_fixed_peer(setup):
    store, bridge, provider, _, flow = setup
    with pytest.raises(BindingError): flow.start(False)
    assert provider.requests == 0
    result = flow.start(True)
    with pytest.raises(BindingError): flow.activate(result['attempt'], 'owner-peer')
    result = flow.poll(result['attempt'])
    assert result['status'] == 'confirmed'
    assert 'token' not in repr(result)
    assert store.read()['binding'] is None
    with pytest.raises(BindingError): flow.activate(result['attempt'], 'another-peer')
    flow.activate(result['attempt'], 'owner-peer')
    assert bridge.binding()['peer'] == 'owner-peer'
    with pytest.raises(BindingError): flow.start(True)
    assert provider.requests == 1


@pytest.mark.parametrize('response', [{'status': 'binded_redirect'}, {'status': 'need_verifycode'},
    {'status': 'confirmed', 'baseurl': 'https://evil.example'}, {'status': 'confirmed', 'ret': True},
    {'status': 'confirmed', 'errcode': 1}, {'status': 'unknown'}])
def test_unknown_login_state_never_binds(setup, response):
    store, _, provider, _, flow = setup
    pending = flow.start(True)
    provider.response = response
    with pytest.raises(BindingError): flow.poll(pending['attempt'])
    assert store.read()['binding'] is None


def test_expiry_cancel_and_revoke_invalidate_qr(setup):
    store, bridge, _, now, flow = setup
    pending = flow.start(True)
    flow.poll(pending['attempt'])
    now[0] += 301
    with pytest.raises(BindingError): flow.activate(pending['attempt'], 'owner-peer')
    flow.cancel(pending['attempt'])
    fresh = flow.start(True)
    bridge.revoke('owner')
    with pytest.raises(BindingError): flow.poll(fresh['attempt'])
    assert store.read()['binding'] is None


def test_uncertain_qr_cannot_auto_retry(setup):
    store, _, provider, _, flow = setup
    def fail(): raise TimeoutError('SENSITIVE_DO_NOT_LOG')
    provider.qr = fail
    with pytest.raises(TimeoutError): flow.start(True)
    assert store.read()['login']['status'] == 'uncertain'
    with pytest.raises(BindingError): flow.start(True)
