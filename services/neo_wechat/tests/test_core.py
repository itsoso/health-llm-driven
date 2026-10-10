import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.neo_wechat.store import Store
from services.neo_wechat.core import Bridge, BridgeError, SIGNAL


def message(mid=1, **changes):
    return dict(message_id=mid, from_user_id='peer', to_user_id='account', message_type=1,
                message_state=2, item_list=[{'type': 1, 'text_item': {'text': 'synthetic private text'}}],
                context_token='synthetic-context', **changes)


@pytest.fixture
def bridge(tmp_path):
    path = tmp_path / 'state'
    path.mkdir(mode=0o700)
    with Store(path, bytes(range(32)), 'owner') as store:
        now = [1000.0]
        b = Bridge(store, clock=lambda: now[0])
        b.bind('account', 'peer', 'synthetic-secret')
        b.now = now
        yield b


def ingest(b, batch=None):
    return b.ingest(batch or [message()], 'cursor', b.binding()['generation'])


def claimed(b):
    ingest(b)
    ident = b.inbox('owner')['messages'][0]['message_id']
    lease = b.claim('owner', ident)['lease_token']
    return ident, lease


def test_filters_dedupe_atomic_cursor(bridge):
    batch = [message(), message(), dict(message(2), from_user_id='foreign'), dict(message(3),to_user_id='foreign'), message(4, group_id='g'), dict(message(5),item_list=[{'type':2}])]
    assert ingest(bridge, batch)['stored'] == 1
    assert bridge.binding()['cursor'] == 'cursor'
    with pytest.raises(BridgeError):
        ingest(bridge, [message(8), dict(message(9), context_token='')])
    assert len(bridge.inbox('owner')['messages']) == 1


def test_foreign_owner_and_generation_denied(bridge):
    ident, lease = claimed(bridge)
    for call in [lambda: bridge.inbox('other'), lambda: bridge.claim('other',ident), lambda: bridge.ack('other',ident,lease), lambda: bridge.revoke('other')]:
        with pytest.raises(BridgeError):
            call()
    old = bridge.binding()['generation']
    bridge.revoke('owner')
    with pytest.raises(BridgeError):
        bridge.ingest([message()], 'x', old)
    bridge.bind('account', 'peer', 'new-synthetic-token')
    with pytest.raises(BridgeError):
        bridge.ingest([message()], 'x', old)
    assert bridge.inbox('owner')['messages'] == []


def test_claim_expiry_ack(bridge):
    ident, lease = claimed(bridge)
    with pytest.raises(BridgeError):
        bridge.claim('owner',ident)
    bridge.now[0] += 61
    with pytest.raises(BridgeError):
        bridge.ack('owner',ident,lease)
    next_lease = bridge.claim('owner',ident)['lease_token']
    assert lease != next_lease
    assert bridge.ack('owner',ident,next_lease) == {'status':'acknowledged'}


def test_reply_destination_saved_and_deduplicated(bridge):
    ident, lease = claimed(bridge)
    calls = []
    def send(*args):
        calls.append(args)
        return 'confirmed'
    assert bridge.reply('owner',ident,lease,'reply',send) == {'delivery':'sent','replayed':False}
    assert calls[0][:3] == ('peer','synthetic-context','reply')
    assert len(calls[0][3]) > 20
    assert bridge.reply('owner',ident,lease,'reply',send) == {'delivery':'sent','replayed':True}
    with pytest.raises(BridgeError):
        bridge.reply('owner',ident,lease,'different',send)
    assert len(calls) == 1


def test_uncertain_send_not_retried_after_restart(bridge):
    ident, lease = claimed(bridge)
    calls = []
    def fail(*args):
        calls.append(args)
        raise TimeoutError('sensitive upstream error')
    assert bridge.reply('owner',ident,lease,'reply',fail)['delivery'] == 'uncertain'
    path = bridge.store.path
    bridge.store.close()
    with Store(path,bytes(range(32)),'owner') as reopened:
        again = Bridge(reopened,clock=bridge.clock)
        assert again.reply('owner',ident,lease,'reply',fail)['delivery'] == 'uncertain'
    assert len(calls) == 1


def test_notification_only_fixed_signal_and_uncertainty(bridge):
    ingest(bridge)
    calls = []
    def fail(text):
        calls.append(text)
        return False
    assert bridge.notify_once(fail) is False
    assert bridge.notify_once(fail) is False
    assert calls == [SIGNAL]


def test_revoke_serializes_with_network_launch(bridge):
    ident, lease = claimed(bridge)
    entered, finish = threading.Event(), threading.Event()
    def send(*args):
        entered.set()
        assert finish.wait(3)
        return 'confirmed'
    with ThreadPoolExecutor(2) as pool:
        send_future = pool.submit(bridge.reply,'owner',ident,lease,'reply',send)
        assert entered.wait(3)
        revoke_future = pool.submit(bridge.revoke,'owner')
        assert not revoke_future.done()
        finish.set()
        send_future.result()
        revoke_future.result()
    with pytest.raises(BridgeError):
        bridge.reply('owner',ident,lease,'reply',send)


def test_text_limits_and_stale_claim(bridge):
    ident, lease = claimed(bridge)
    with pytest.raises(BridgeError):
        bridge.reply('owner',ident,lease,'x'*16001,lambda *x:'confirmed')
    bridge.now[0] += 61
    with pytest.raises(BridgeError):
        bridge.reply('owner',ident,lease,'reply',lambda *x:'confirmed')


def test_inbox_capacity_rolls_back_entire_batch_and_cursor(bridge, monkeypatch):
    monkeypatch.setattr('services.neo_wechat.core.MAX_MESSAGES', 1)
    with pytest.raises(BridgeError, match='inbox_capacity'):
        ingest(bridge, [message(1), message(2)])
    assert bridge.binding()['cursor'] == ''
    assert bridge.inbox('owner')['messages'] == []


def test_reply_rate_limit(bridge):
    ingest(bridge, [message(n) for n in range(21)])
    for i, row in enumerate(bridge.inbox('owner',100)['messages']):
        ident = row['message_id']
        lease = bridge.claim('owner',ident)['lease_token']
        if i < 20:
            bridge.reply('owner',ident,lease,'reply',lambda *a:'confirmed')
        else:
            with pytest.raises(BridgeError, match='reply_rate_limit'):
                bridge.reply('owner',ident,lease,'reply',lambda *a:'confirmed')


def test_unicode_untrusted_identity_and_cursor_are_safe_codes(bridge):
    with pytest.raises(BridgeError, match='owner_mismatch'):
        bridge.inbox('外人')
    with pytest.raises(BridgeError, match='invalid_cursor'):
        bridge.ingest([], '\ud800', bridge.binding()['generation'])


def test_booleans_are_not_protocol_message_types(bridge):
    assert ingest(bridge,[dict(message(),message_type=True)])['stored'] == 0


def test_notification_coalesces_then_accepts_new_messages(bridge):
    calls = []
    def confirmed(text):
        calls.append(text)
        return True
    ingest(bridge,[message(1),message(2)])
    assert bridge.notify_once(confirmed)
    assert not bridge.notify_once(confirmed)
    ingest(bridge,[message(3)])
    assert bridge.notify_once(confirmed)
    assert calls == [SIGNAL,SIGNAL]


def test_malformed_lease_uses_safe_error(bridge):
    ident, _ = claimed(bridge)
    with pytest.raises(BridgeError, match='lease_invalid'):
        bridge.ack('owner', ident, '外人')


def test_no_external_action_before_durable_reservation(bridge, monkeypatch):
    from services.neo_wechat.store import StoreError
    ident, lease = claimed(bridge)
    calls = []
    def failed(*args):
        raise OSError('synthetic durability failure')
    monkeypatch.setattr('services.neo_wechat.store.os.fsync',failed)
    with pytest.raises(StoreError, match='store_uncertain'):
        bridge.reply('owner',ident,lease,'reply',lambda *args: calls.append(args))
    assert calls == []


def test_revoke_excludes_notification_launch(bridge):
    ingest(bridge)
    bridge.revoke('owner')
    calls = []
    with pytest.raises(BridgeError, match='binding_required'):
        bridge.notify_once(lambda text: calls.append(text))
    assert calls == []
