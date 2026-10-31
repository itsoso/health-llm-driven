"""Short-lived identity proof for one explicitly linked private Edu workspace."""
import base64
import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
from app.config import settings


def _origin(value):
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and bool(url.hostname) and not url.username
                and not url.password and not url.path and not url.query and not url.fragment
                and url.port in (None, 443) and value == f'https://{url.netloc}')
    except ValueError:
        return False


def issue_ticket(user, state: str, expected_user_id: int) -> dict:
    ticket = _issue_identity_ticket(user, state, expected_user_id,
                                    purpose='edu-browser-login', prefix='edu-login-v1.')
    return {'ticket': ticket, 'callback_url': settings.edu_sso_origin + '/api/auth/health/callback'}


def issue_native_ticket(user, state: str, expected_user_id: int) -> dict:
    return {'ticket': _issue_identity_ticket(user, state, expected_user_id,
                                            purpose='edu-native-login', prefix='edu-native-login-v1.')}


def _issue_identity_ticket(user, state: str, expected_user_id: int, *, purpose: str, prefix: str) -> str:
    if (not settings.edu_sso_enabled or len(settings.edu_sso_secret) < 32
            or settings.edu_sso_owner_id <= 0 or not _origin(settings.edu_sso_origin)
            or not _origin(settings.edu_sso_issuer)):
        raise HTTPException(503, 'Edu统一登录尚未配置')
    raw_viewers = getattr(settings, 'edu_sso_viewer_ids', '')
    parts = raw_viewers.split(',') if raw_viewers else []
    if (any(not re.fullmatch(r'[1-9][0-9]*', part) for part in parts)
            or len(set(parts)) != len(parts) or str(settings.edu_sso_owner_id) in parts):
        raise HTTPException(503, 'Edu统一登录查看账户配置无效')
    allowed = {settings.edu_sso_owner_id, *(int(part) for part in parts)}
    if (not user or user.id not in allowed or user.id != expected_user_id
            or not user.is_active or not user.is_approved or user.is_managed):
        raise HTTPException(403, '当前账号未关联此Edu，请重新确认登录账号')
    if not isinstance(state, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', state):
        raise HTTPException(400, '登录请求无效，请从Edu重新发起')
    stamp = int(time.time())
    claims = dict(v=1, purpose=purpose, iss=settings.edu_sso_issuer,
        aud=settings.edu_sso_origin, sub=str(user.id), state=state, iat=stamp, exp=stamp + 60)
    encode = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip('=')
    payload = encode(json.dumps(claims, separators=(',', ':')).encode())
    signature = encode(hmac.new(settings.edu_sso_secret.encode(),
        (prefix + payload).encode(), hashlib.sha256).digest())
    return payload + '.' + signature
