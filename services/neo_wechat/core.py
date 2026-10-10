"""Owner-pinned durable inbox, claims and at-most-once external dispatch."""
from __future__ import annotations

import hashlib
import secrets
import time

SIGNAL = 'Neo 有新的微信消息，请读取微信桥接收件箱。'
MAX_MESSAGES = 4000
MAX_BATCH = 1000
TEXT_BYTES = 16000


class BridgeError(ValueError):
    """Only constant non-sensitive error codes cross the service boundary."""


def _text(value, maximum, code='invalid_input'):
    if not isinstance(value, str) or not value.strip():
        raise BridgeError(code)
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise BridgeError(code) from None
    if size > maximum:
        raise BridgeError(code)
    return value


def _audit(state, event, now):
    state['audit'].append({'event': event, 'at': now})
    state['audit'] = state['audit'][-1000:]


class Bridge:
    def __init__(self, store, clock=time.time):
        self.store, self.clock, self.owner = store, clock, store.owner

    def _owner(self, owner):
        if not isinstance(owner, str) or owner != self.owner:
            raise BridgeError('owner_mismatch')

    def _bound(self, state, generation=None):
        binding = state['binding']
        if not binding or not binding['active']:
            raise BridgeError('binding_required')
        if generation is not None and generation != binding['generation']:
            raise BridgeError('binding_changed')
        return binding

    def binding(self):
        """Internal transport credentials. Never expose via MCP or HTTP response."""
        return self._bound(self.store.read())

    def bind(self, account, peer, token):
        """Only the authenticated, CSRF-protected, confirmed QR flow may call this."""
        _text(account, 512)
        _text(peer, 512)
        _text(token, 8192)
        if '@chatroom' in peer or '@chatroom' in account:
            raise BridgeError('invalid_binding')
        with self.store.transaction() as state:
            state['binding'] = {'account': account, 'peer': peer, 'token': token,
                                'generation': secrets.token_hex(16), 'active': True, 'cursor': '',
                                'reply_times': []}
            _audit(state, 'binding_activated', self.clock())
        return {'status': 'bound'}

    def ingest(self, batch, cursor, generation):
        if not isinstance(batch, list) or len(batch) > MAX_BATCH:
            raise BridgeError('invalid_batch')
        try:
            valid_cursor = isinstance(cursor, str) and len(cursor.encode()) <= 65536
        except UnicodeError:
            valid_cursor = False
        if not valid_cursor:
            raise BridgeError('invalid_cursor')
        count = 0
        with self.store.transaction() as state:
            binding = self._bound(state, generation)
            for msg in batch:
                if not isinstance(msg, dict):
                    raise BridgeError('invalid_message')
                if (msg.get('from_user_id') != binding['peer'] or msg.get('to_user_id') != binding['account']
                        or msg.get('group_id') or msg.get('chatroom_id')
                        or type(msg.get('message_type')) is not int or msg.get('message_type') != 1
                        or type(msg.get('message_state')) is not int or msg.get('message_state') != 2):
                    continue
                items = msg.get('item_list')
                if (not isinstance(items, list) or not items or len(items) > 32
                        or any(not isinstance(i, dict) or i.get('type') != 1 for i in items)):
                    continue
                parts = []
                for item in items:
                    entry = item.get('text_item')
                    if not isinstance(entry, dict):
                        raise BridgeError('invalid_message')
                    parts.append(_text(entry.get('text'), TEXT_BYTES, 'invalid_message'))
                text = _text('\n'.join(parts), TEXT_BYTES, 'invalid_message')
                context = _text(msg.get('context_token'), 8192, 'invalid_message')
                raw_id = msg.get('message_id')
                if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
                    raise BridgeError('invalid_message')
                raw_id = str(raw_id)
                if not raw_id.isascii() or not raw_id.isdecimal() or len(raw_id) > 20 or int(raw_id) > 2**64-1:
                    raise BridgeError('invalid_message')
                ident = hashlib.sha256((binding['generation'] + ':' + str(int(raw_id))).encode()).hexdigest()
                if ident in state['messages']:
                    continue
                if len(state['messages']) >= MAX_MESSAGES:
                    raise BridgeError('inbox_capacity')
                state['messages'][ident] = {'generation': binding['generation'], 'text': text,
                    'context': context, 'status': 'pending', 'lease': None, 'until': 0,
                    'reply': None, 'signal': 'pending', 'received': self.clock()}
                count += 1
            binding['cursor'] = cursor
            if count:
                _audit(state, 'messages_received', self.clock())
        return {'stored': count}

    def inbox(self, owner, limit=20):
        self._owner(owner)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise BridgeError('invalid_limit')
        with self.store.transaction() as state:
            binding = self._bound(state)
            rows = [{'message_id': ident, 'text': row['text'], 'status': row['status'],
                     'reply_status': row['reply']['status'] if row['reply'] else None}
                    for ident, row in state['messages'].items()
                    if row['generation'] == binding['generation'] and row['status'] != 'acknowledged'][:limit]
            _audit(state, 'inbox_read', self.clock())
        return {'messages': rows}

    def _row(self, state, ident):
        binding = self._bound(state)
        if not isinstance(ident, str):
            raise BridgeError('message_missing')
        row = state['messages'].get(ident)
        if not row or row['generation'] != binding['generation']:
            raise BridgeError('message_missing')
        return binding, row

    def claim(self, owner, ident):
        self._owner(owner)
        with self.store.transaction() as state:
            _, row = self._row(state, ident)
            if row['status'] == 'acknowledged' or (row['status'] == 'claimed' and row['until'] > self.clock()):
                raise BridgeError('claim_conflict')
            row.update(status='claimed', lease=secrets.token_urlsafe(32), until=self.clock()+60)
            result = {'lease_token': row['lease'], 'expires_at': row['until']}
            _audit(state, 'message_claimed', self.clock())
        return result

    def _lease(self, row, lease):
        if (not isinstance(lease, str) or not lease.isascii() or len(lease) > 128 or not row['lease']
                or not secrets.compare_digest(row['lease'], lease)
                or row['status'] != 'claimed' or row['until'] <= self.clock()):
            raise BridgeError('lease_invalid')

    def ack(self, owner, ident, lease):
        self._owner(owner)
        with self.store.transaction() as state:
            _, row = self._row(state, ident)
            self._lease(row, lease)
            row.update(status='acknowledged', lease=None, until=0)
            _audit(state, 'message_acknowledged', self.clock())
        return {'status': 'acknowledged'}

    def reply(self, owner, ident, lease, text, transport):
        self._owner(owner)
        _text(text, TEXT_BYTES, 'invalid_reply')
        fingerprint = hashlib.sha256(text.encode()).hexdigest()
        # Hold the same mutex as revoke across durable reservation and network
        # launch/completion. A successful revoke therefore excludes later launch.
        with self.store.lock:
            with self.store.transaction() as state:
                binding, row = self._row(state, ident)
                self._lease(row, lease)
                if row['reply']:
                    if row['reply']['fingerprint'] != fingerprint:
                        raise BridgeError('reply_payload_conflict')
                    return {'delivery': row['reply']['status'], 'replayed': True}
                now = self.clock()
                times = [t for t in binding['reply_times'] if t > now-60]
                if len(times) >= 20:
                    raise BridgeError('reply_rate_limit')
                binding['reply_times'] = times + [now]
                client_id = 'neo-' + secrets.token_hex(16)
                row['reply'] = {'fingerprint': fingerprint, 'status': 'uncertain', 'client_id': client_id}
                peer, context = binding['peer'], row['context']
                _audit(state, 'reply_reserved', now)
            try:
                receipt = transport(peer, context, text, client_id)
            except Exception:
                # Explicit uncertain status informs caller; never expose upstream
                # exception text or retry an action that may already have happened.
                receipt = None
            delivery = 'sent' if receipt == 'confirmed' else 'uncertain'
            with self.store.transaction() as state:
                state['messages'][ident]['reply']['status'] = delivery
                _audit(state, 'reply_' + delivery, self.clock())
            return {'delivery': delivery, 'replayed': False}

    def notify_once(self, notifier):
        with self.store.lock:
            with self.store.transaction() as state:
                binding = self._bound(state)
                pending = [key for key, row in state['messages'].items()
                           if row['generation'] == binding['generation'] and row['signal'] == 'pending']
                if not pending:
                    return False
                for key in pending:
                    state['messages'][key]['signal'] = 'uncertain'
                _audit(state, 'signal_reserved', self.clock())
            try:
                confirmed = notifier(SIGNAL) is True
            except Exception:
                confirmed = False
            if confirmed:
                with self.store.transaction() as state:
                    for key in pending:
                        state['messages'][key]['signal'] = 'sent'
                    _audit(state, 'signal_sent', self.clock())
            return confirmed

    def revoke(self, owner):
        self._owner(owner)
        with self.store.transaction() as state:
            binding = state['binding']
            if binding:
                binding.update(active=False, token='')
            state['login'] = None
            for row in state['messages'].values():
                row.update(lease=None, until=0)
            _audit(state, 'binding_revoked', self.clock())
        return {'status': 'revoked'}
