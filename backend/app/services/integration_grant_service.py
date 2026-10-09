"""Minimal authorization-code flow for a verified, confidential recipient.

No refresh token, family proxy, configurable field set or health write authority.
Recipient registration and verification are an operator-controlled allowlist.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.config import settings
from app.models.user import User
from app.models.lifenav_grant import LifeNavAccessAudit, LifeNavGrant
from app.schemas.lifenav_grant import LifeNavGrantCreated, LifeNavGrantView, LifeNavToken

POLICY_VERSION = 'lifenav-generic-v1'
TOKEN_PREFIX = 'ln1_'


def credential_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _deny():
    raise HTTPException(status_code=403, detail='LifeNav 授权无效或已失效')


def require_enabled():
    if not getattr(settings, 'lifenav_integration_enabled', False):
        raise HTTPException(status_code=503, detail='LifeNav 连接尚未启用')


def registered_recipient(recipient_id: str) -> dict:
    require_enabled()
    try:
        registry = json.loads(getattr(settings, 'lifenav_recipients_json', '{}'))
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail='LifeNav 接收方配置无效') from exc
    if not isinstance(registry, dict):
        raise HTTPException(status_code=503, detail='LifeNav 接收方配置无效')
    item = registry.get(recipient_id)
    if not isinstance(item, dict) or item.get('verified') is not True:
        _deny()
    callback, origin = item.get('redirect_uri'), item.get('origin')
    secret_hash = item.get('client_secret_sha256', '')
    if not isinstance(callback, str) or not isinstance(origin, str) or not isinstance(secret_hash, str):
        _deny()
    try:
        url, base = urlsplit(callback), urlsplit(origin)
        valid = (url.scheme == 'https' and base.scheme == 'https' and bool(url.hostname)
                 and bool(base.hostname) and not url.username and not url.password
                 and not base.username and not base.password and not url.query and not url.fragment
                 and not base.query and not base.fragment and base.path in ('', '/')
                 and (url.scheme, url.netloc) == (base.scheme, base.netloc)
                 and re.fullmatch(r'[a-f0-9]{64}', secret_hash))
    except ValueError:
        _deny()
    if not valid:
        _deny()
    return item


def _check_owner(user):
    if not user or not user.is_active or not user.is_approved or user.is_managed:
        _deny()


def _check_grant(db: Session, grant: LifeNavGrant | None):
    if not grant:
        _deny()
    recipient = registered_recipient(grant.recipient_id)
    if (grant.audience != 'lifenav' or grant.scope != 'navigation:generic'
            or grant.window_policy != 'current_trailing7' or grant.policy_version != POLICY_VERSION
            or grant.revoked_at is not None or utc(grant.expires_at) <= now_utc()
            or grant.redirect_uri != recipient['redirect_uri']
            or not hmac.compare_digest(grant.recipient_secret_hash, recipient['client_secret_sha256'])):
        _deny()
    _check_owner(db.query(User).filter(User.id == grant.user_id).first())
    return recipient


def audit(db: Session, grant_id: str | None, outcome: str, request_id: str | None = None):
    db.add(LifeNavAccessAudit(grant_id=grant_id, request_id=request_id or str(uuid.uuid4()),
                             field_category='navigation:generic', outcome=outcome))


def create_grant(db, user, payload):
    _check_owner(user)
    recipient = registered_recipient(payload.recipient_id)
    if payload.redirect_uri != recipient['redirect_uri']:
        _deny()
    stamp = now_utc()
    code = secrets.token_urlsafe(32)
    row = LifeNavGrant(id=str(uuid.uuid4()), user_id=user.id, recipient_id=payload.recipient_id,
        audience='lifenav', scope=payload.scope, window_policy=payload.window_policy,
        policy_version=POLICY_VERSION, redirect_uri=recipient['redirect_uri'],
        recipient_secret_hash=recipient['client_secret_sha256'], state_hash=credential_hash(payload.state),
        code_challenge=payload.code_challenge, code_hash=credential_hash(code),
        code_expires_at=stamp + timedelta(minutes=5), created_at=stamp,
        expires_at=stamp + timedelta(days=payload.expires_in_days))
    db.add(row)
    db.flush()
    audit(db, row.id, 'created')
    db.commit()
    return LifeNavGrantCreated(grant_id=row.id, expires_at=utc(row.expires_at),
        authorization_url=recipient['redirect_uri'] + '?' + urlencode({'code': code, 'state': payload.state}))


def list_grants(db, user_id):
    rows = db.query(LifeNavGrant).filter(LifeNavGrant.user_id == user_id).order_by(LifeNavGrant.created_at.desc()).all()
    return [LifeNavGrantView(grant_id=g.id, recipient_id=g.recipient_id,
        created_at=utc(g.created_at), expires_at=utc(g.expires_at), revoked_at=utc(g.revoked_at) if g.revoked_at else None,
        connected=bool(g.token_hash and not g.revoked_at and utc(g.expires_at) > now_utc())) for g in rows]


def revoke_grant(db, user_id, grant_id):
    row = db.query(LifeNavGrant).filter(LifeNavGrant.id == grant_id, LifeNavGrant.user_id == user_id).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail='未找到授权')
    row.revoked_at = now_utc()
    row.token_hash = None
    audit(db, row.id, 'revoked')
    db.commit()


def exchange_code(db, payload):
    recipient = registered_recipient(payload.client_id)
    if not hmac.compare_digest(credential_hash(payload.client_secret.get_secret_value()), recipient['client_secret_sha256']):
        _deny()
    grant = db.query(LifeNavGrant).filter(LifeNavGrant.code_hash == credential_hash(payload.code.get_secret_value())).with_for_update().first()
    _check_grant(db, grant)
    verifier = payload.code_verifier.get_secret_value()
    if not re.fullmatch(r'[a-zA-Z0-9._~-]{43,128}', verifier):
        _deny()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    if (grant.recipient_id != payload.client_id or grant.redirect_uri != payload.redirect_uri
            or grant.code_used_at is not None or utc(grant.code_expires_at) <= now_utc()
            or not hmac.compare_digest(grant.state_hash, credential_hash(payload.state))
            or not hmac.compare_digest(grant.code_challenge, challenge)):
        _deny()
    stamp = now_utc()
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    # Conditional consumption protects one-time semantics on SQLite as well as PostgreSQL.
    result = db.execute(update(LifeNavGrant).where(LifeNavGrant.id == grant.id,
        LifeNavGrant.code_used_at.is_(None), LifeNavGrant.revoked_at.is_(None),
        LifeNavGrant.code_expires_at > stamp, LifeNavGrant.expires_at > stamp)
        .values(code_used_at=stamp, token_hash=credential_hash(token))
        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        _deny()
    audit(db, grant.id, 'exchanged')
    expires_at = utc(grant.expires_at)
    db.commit()
    return LifeNavToken(access_token=token, expires_at=expires_at)


def authenticate_grant(db, token):
    require_enabled()
    if not isinstance(token, str) or not re.fullmatch(r'ln1_[a-zA-Z0-9_-]{43}', token):
        _deny()
    grant = db.query(LifeNavGrant).filter(LifeNavGrant.token_hash == credential_hash(token)).first()
    _check_grant(db, grant)
    return grant
