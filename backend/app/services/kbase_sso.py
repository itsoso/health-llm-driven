"""Short-lived identity proof for one explicitly linked private KBase workspace."""
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
    if (not settings.kbase_sso_enabled or len(settings.kbase_sso_secret) < 32
            or settings.kbase_sso_owner_id <= 0 or not _origin(settings.kbase_sso_origin)
            or not _origin(settings.kbase_sso_issuer)):
        raise HTTPException(503, '知识库统一登录尚未配置')
    if (not user or user.id != settings.kbase_sso_owner_id or user.id != expected_user_id
            or not user.is_active or not user.is_approved or user.is_managed):
        raise HTTPException(403, '当前账号未关联此知识库，请重新确认登录账号')
    if not isinstance(state, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', state):
        raise HTTPException(400, '登录请求无效，请从知识库重新发起')
    stamp = int(time.time())
    claims = dict(v=1, purpose='kbase-browser-login', iss=settings.kbase_sso_issuer,
        aud=settings.kbase_sso_origin, sub=str(user.id), state=state, iat=stamp, exp=stamp + 60)
    encode = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip('=')
    payload = encode(json.dumps(claims, separators=(',', ':')).encode())
    signature = encode(hmac.new(settings.kbase_sso_secret.encode(),
        ('kbase-login-v1.' + payload).encode(), hashlib.sha256).digest())
    return {'ticket': payload + '.' + signature,
            'callback_url': settings.kbase_sso_origin + '/browser/health/callback'}
