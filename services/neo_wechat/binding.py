"""Fresh owner-confirmed QR lifecycle. No credential migration or upstream unbind."""
import secrets
import time
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class BindingError(ValueError):
    pass


class Credentials(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)
    bot_token: str = Field(min_length=1, max_length=8192, pattern=r'^[^\r\n]+$')
    ilink_bot_id: str = Field(min_length=1, max_length=256)
    ilink_user_id: str = Field(min_length=1, max_length=256)


def check_response(value):
    if not isinstance(value, dict) or any(
            key in value and (type(value[key]) is not int or value[key] != 0) for key in ('ret', 'errcode')):
        raise BindingError('provider_rejected')


class Binding:
    def __init__(self, store, bridge, transport, clock=time.time):
        self.store, self.bridge, self.transport, self.clock = store, bridge, transport, clock

    def start(self, accepted):
        if accepted is not True:
            raise BindingError('fresh_binding_consent_required')
        with self.store.lock:
            with self.store.transaction() as state:
                if state['binding'] or state['login']:
                    raise BindingError('existing_binding_or_attempt')
                attempt = secrets.token_urlsafe(24)
                state['login'] = {'attempt': attempt, 'status': 'uncertain', 'expires': self.clock() + 300}
            # A timeout cannot prove no QR was issued. Keep uncertain until an
            # owner cancels this attempt; never issue again automatically.
            response = self.transport.qr()
            check_response(response)
            code, display = response.get('qrcode'), response.get('qrcode_img_content')
            if (not isinstance(code, str) or not 1 <= len(code) <= 8192
                    or not isinstance(display, str) or not 1 <= len(display) <= 512
                    or any(ord(c) < 32 or ord(c) > 126 for c in display)):
                raise BindingError('qr_format_requires_review')
            with self.store.transaction() as state:
                state['login'].update(status='waiting', qrcode=code, display=display)
            return self.view()

    def view(self):
        state = self.store.read()
        login = state['login']
        if not login:
            return {'status': 'unconfigured'}
        if login['expires'] <= self.clock():
            return {'status': 'expired', 'attempt': login['attempt']}
        result = {'status': login['status'], 'attempt': login['attempt']}
        if login['status'] == 'waiting':
            result['display'] = login['display']
        if login['status'] == 'confirmed':
            # Show full provider identity only on authenticated owner setup so
            # owner can explicitly compare; never return token or QR secret.
            result['peer'] = login['credentials']['ilink_user_id']
            result['account'] = login['credentials']['ilink_bot_id']
        return result

    def poll(self, attempt):
        with self.store.lock:
            login = self.store.read()['login']
            if (not login or login['attempt'] != attempt or login['status'] != 'waiting'
                    or login['expires'] <= self.clock()):
                raise BindingError('qr_attempt_invalid')
            response = self.transport.poll_qr(login['qrcode'])
            check_response(response)
            status = response.get('status')
            if status in ('wait', 'scaned'):
                return self.view()
            if status == 'expired':
                with self.store.transaction() as state:
                    state['login'] = {'attempt': attempt, 'status': 'expired', 'expires': 0}
                return self.view()
            if status != 'confirmed':
                raise BindingError('qr_state_requires_review')
            if response.get('baseurl', 'https://ilinkai.weixin.qq.com') not in (
                    'https://ilinkai.weixin.qq.com', 'https://ilinkai.weixin.qq.com/'):
                raise BindingError('qr_baseurl_requires_review')
            try:
                creds = Credentials.model_validate(response).model_dump()
            except ValidationError:
                raise BindingError('qr_credentials_invalid') from None
            with self.store.transaction() as state:
                state['login'].update(status='confirmed', credentials=creds)
                state['login'].pop('qrcode', None)
                state['login'].pop('display', None)
            return self.view()

    def activate(self, attempt, peer):
        with self.store.lock:
            state = self.store.read()
            login = state['login']
            if (state['binding'] or not login or login['attempt'] != attempt
                    or login['status'] != 'confirmed' or login['expires'] <= self.clock()
                    or peer != login['credentials']['ilink_user_id']):
                raise BindingError('owner_identity_confirmation_required')
            creds = login['credentials']
            self.bridge.bind(creds['ilink_bot_id'], creds['ilink_user_id'], creds['bot_token'])
            with self.store.transaction() as state:
                state['login'] = None
            return {'status': 'bound'}

    def cancel(self, attempt):
        with self.store.transaction() as state:
            login = state['login']
            if not login or login['attempt'] != attempt:
                raise BindingError('qr_attempt_invalid')
            state['login'] = None
