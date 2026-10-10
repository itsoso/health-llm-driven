"""Storage adapter for the official MCP SDK's OAuth authorization server."""
import hashlib
import logging
import re
import secrets
import time
import uuid
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import update
from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
    RefreshToken, TokenError, construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from app.models.remote_health_oauth import RemoteHealthCredential, RemoteHealthGrant, RemoteHealthRateBucket
from app.models.user import User

logger = logging.getLogger(__name__)
SCOPE = "health:read"
PREFIX = "/api/v1/remote-health"
ACCESS_SECONDS = 600
REFRESH_SECONDS = 30 * 86400


class RegisteredClient(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._-]+$")
    client_name: str = Field(min_length=1, max_length=80)
    redirect_uris: list[str] = Field(min_length=1, max_length=4)
    grant_days: int = Field(default=30, ge=1, le=3650, strict=True)
    allowed_user_id: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def validate_redirects(self):
        if self.grant_days > 30 and self.allowed_user_id is None:
            raise ValueError("Grants longer than 30 days require an explicit account owner")
        for uri in self.redirect_uris:
            p = urlsplit(uri)
            if p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment or p.query or "*" in uri or len(uri) > 500:
                raise ValueError("Register exact HTTPS redirects without query, fragment or credentials")
        return self

    def consent_policy(self):
        return {"grant_days": self.grant_days, "allowed_user_id": self.allowed_user_id}


class RemoteHealthConfig(BaseModel):
    origin: str
    clients: list[RegisteredClient] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_origin(self):
        p = urlsplit(self.origin)
        if p.scheme != "https" or not p.hostname or p.path or p.query or p.fragment or p.username or p.password:
            raise ValueError("Remote health origin must be an HTTPS origin without a trailing slash")
        if len({c.client_id for c in self.clients}) != len(self.clients):
            raise ValueError("Duplicate client ID")
        return self

    @property
    def issuer(self):
        return self.origin + PREFIX

    @property
    def resource(self):
        return self.issuer + "/mcp"


def digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class RemoteHealthOAuth:
    def __init__(self, config: RemoteHealthConfig, session_factory):
        self.config = config
        self.session_factory = session_factory

    def session(self):
        return self.session_factory()

    async def get_client(self, client_id):
        item = next((c for c in self.config.clients if c.client_id == client_id), None)
        if item is None:
            return None
        return OAuthClientInformationFull(
            **item.model_dump(exclude={"grant_days", "allowed_user_id"}),
            token_endpoint_auth_method="none", scope=SCOPE,
            grant_types=["authorization_code", "refresh_token"], response_types=["code"],
        )

    async def register_client(self, client_info):
        raise NotImplementedError("Clients require operator pre-registration")

    def _store(self, db, kind, expires_at, grant_id=None, payload=None):
        raw = secrets.token_urlsafe(32)
        db.add(RemoteHealthCredential(digest=digest(raw), kind=kind, expires_at=expires_at,
                                    grant_id=grant_id, payload=payload or {}))
        return raw

    async def authorize(self, client, params: AuthorizationParams):
        if params.resource != self.config.resource or params.scopes != [SCOPE]:
            raise AuthorizeError("invalid_scope", "Only the registered read-only resource is supported")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", params.code_challenge):
            raise AuthorizeError("invalid_request", "S256 PKCE is required")
        configured = next(c for c in self.config.clients if c.client_id == client.client_id)
        if str(params.redirect_uri) not in configured.redirect_uris or not params.redirect_uri_provided_explicitly:
            raise AuthorizeError("invalid_request", "Exact registered redirect required")
        if params.state is None or not 1 <= len(params.state) <= 512:
            raise AuthorizeError("invalid_request", "State is required")
        with self.session() as db:
            raw = self._store(db, "pending", int(time.time()) + 300,
                              payload={**params.model_dump(mode="json"), "client_id": client.client_id,
                                       "client_policy": configured.consent_policy()})
            db.commit()
        return self.config.origin + "/connect/health?request=" + raw

    def _pending(self, db, raw):
        row = db.get(RemoteHealthCredential, digest(raw))
        if not row or row.kind != "pending" or row.used_at is not None or row.expires_at <= time.time():
            raise ValueError("Authorization request expired or already used")
        client = next((c for c in self.config.clients if c.client_id == row.payload["client_id"]), None)
        if client is None or row.payload.get("client_policy") != client.consent_policy():
            raise ValueError("Client policy changed; restart authorization")
        return row

    def preview(self, raw):
        with self.session() as db:
            row = self._pending(db, raw)
            client = next((c for c in self.config.clients if c.client_id == row.payload["client_id"]), None)
            if client is None:
                raise ValueError("Client is no longer registered")
            return {"client_name": client.client_name, "scope": SCOPE,
                    "expires_in_days": client.grant_days, "data_categories": ["sleep", "diet", "exercise"]}

    def consent(self, raw, user_id, expected_user_id, approved):
        if user_id != expected_user_id:
            raise ValueError("Account changed; review consent again")
        now = int(time.time())
        with self.session() as db:
            row = self._pending(db, raw)
            params = row.payload
            client = next((c for c in self.config.clients if c.client_id == params["client_id"]), None)
            if client is None or params["redirect_uri"] not in client.redirect_uris:
                raise ValueError("Client is no longer registered")
            if client.allowed_user_id is not None and client.allowed_user_id != user_id:
                raise ValueError("This account is not authorized for the registered client")
            user = db.get(User, user_id)
            if not user or not user.is_active or not user.is_approved:
                raise ValueError("Account unavailable")
            claimed = db.execute(update(RemoteHealthCredential).where(
                RemoteHealthCredential.digest == row.digest, RemoteHealthCredential.used_at.is_(None),
                RemoteHealthCredential.expires_at > now).values(used_at=now)).rowcount
            if claimed != 1:
                raise ValueError("Authorization request already used")
            callback = {"state": params["state"], "iss": self.config.issuer}
            if approved:
                grant = RemoteHealthGrant(id=str(uuid.uuid4()), user_id=user_id, client_id=client.client_id,
                    scope=SCOPE, resource=self.config.resource, created_at=now,
                    expires_at=now + client.grant_days * 86400)
                db.add(grant)
                db.flush()
                callback["code"] = self._store(db, "code", now + 60, grant.id, params)
                logger.info("remote_health consent_approved grant=%s", grant.id)
            else:
                callback["error"] = "access_denied"
                logger.info("remote_health consent_denied")
            db.commit()
            return construct_redirect_uri(params["redirect_uri"], **callback)

    def _grant(self, db, row):
        if row is None or not row.grant_id:
            return None
        grant = db.get(RemoteHealthGrant, row.grant_id)
        if not grant or grant.revoked_at is not None or grant.expires_at <= time.time():
            return None
        if grant.scope != SCOPE or grant.resource != self.config.resource:
            return None
        client = next((c for c in self.config.clients if c.client_id == grant.client_id), None)
        if client is None or (client.allowed_user_id is not None and client.allowed_user_id != grant.user_id):
            return None
        user = db.get(User, grant.user_id)
        if not user or not user.is_active or not user.is_approved:
            return None
        return grant

    async def load_authorization_code(self, client, authorization_code):
        with self.session() as db:
            row = db.get(RemoteHealthCredential, digest(authorization_code))
            grant = self._grant(db, row)
            if not grant or row.kind != "code" or grant.client_id != client.client_id:
                return None
            return AuthorizationCode(code=authorization_code, expires_at=row.expires_at,
                subject=str(grant.user_id), **{k: row.payload[k] for k in (
                    "scopes", "client_id", "code_challenge", "redirect_uri",
                    "redirect_uri_provided_explicitly", "resource")})

    def _tokens(self, db, grant):
        now = int(time.time())
        access = self._store(db, "access", min(now + ACCESS_SECONDS, grant.expires_at), grant.id)
        refresh = self._store(db, "refresh", min(now + REFRESH_SECONDS, grant.expires_at), grant.id)
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=min(ACCESS_SECONDS, grant.expires_at-now),
                          refresh_token=refresh, scope=SCOPE)

    def _exchange(self, client, raw, kind):
        now = int(time.time())
        with self.session() as db:
            row = db.get(RemoteHealthCredential, digest(raw))
            grant = self._grant(db, row)
            if not grant or row.kind != kind or row.expires_at <= now or grant.client_id != client.client_id:
                raise TokenError("invalid_grant", "Credential unavailable")
            claimed = db.execute(update(RemoteHealthCredential).where(
                RemoteHealthCredential.digest == row.digest, RemoteHealthCredential.used_at.is_(None),
                RemoteHealthCredential.expires_at > now).values(used_at=now)).rowcount
            if claimed != 1:
                grant.revoked_at = now
                db.commit()
                logger.warning("remote_health credential_replay grant=%s", grant.id)
                raise TokenError("invalid_grant", "Credential already used")
            token = self._tokens(db, grant)
            db.commit()
            logger.info("remote_health token_issued grant=%s", grant.id)
            return token

    async def exchange_authorization_code(self, client, authorization_code):
        return self._exchange(client, authorization_code.code, "code")

    async def load_refresh_token(self, client, refresh_token):
        with self.session() as db:
            row = db.get(RemoteHealthCredential, digest(refresh_token))
            grant = self._grant(db, row)
            if not grant or row.kind != "refresh" or grant.client_id != client.client_id:
                return None
            return RefreshToken(token=refresh_token, client_id=client.client_id, scopes=[SCOPE],
                expires_at=row.expires_at, resource=grant.resource, subject=str(grant.user_id))

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if scopes != [SCOPE]:
            raise TokenError("invalid_scope", "Read-only scope required")
        return self._exchange(client, refresh_token.token, "refresh")

    async def load_access_token(self, token):
        if len(token) > 128:
            return None
        with self.session() as db:
            row = db.get(RemoteHealthCredential, digest(token))
            grant = self._grant(db, row)
            if not grant or row.kind != "access" or row.expires_at <= time.time() or row.used_at is not None:
                return None
            return AccessToken(token=token, client_id=grant.client_id, scopes=[SCOPE], expires_at=row.expires_at,
                resource=grant.resource, subject=str(grant.user_id), claims={"grant_id": grant.id})

    async def verify_token(self, token):
        return await self.load_access_token(token)

    async def revoke_token(self, token):
        with self.session() as db:
            row = db.get(RemoteHealthCredential, digest(token.token))
            if row and row.grant_id:
                db.execute(update(RemoteHealthGrant).where(RemoteHealthGrant.id == row.grant_id).values(revoked_at=int(time.time())))
                db.commit()
                logger.info("remote_health revoked grant=%s", row.grant_id)

    def grants(self, user_id):
        with self.session() as db:
            rows = db.query(RemoteHealthGrant).filter(RemoteHealthGrant.user_id == user_id,
                RemoteHealthGrant.revoked_at.is_(None), RemoteHealthGrant.expires_at > time.time()).order_by(RemoteHealthGrant.created_at.desc()).limit(100).all()
            names = {c.client_id: c.client_name for c in self.config.clients}
            return [{"id": g.id, "client_name": names.get(g.client_id, "Removed client"),
                     "created_at": g.created_at, "expires_at": g.expires_at, "scope": g.scope} for g in rows]

    def revoke_grant(self, user_id, grant_id):
        with self.session() as db:
            db.execute(update(RemoteHealthGrant).where(RemoteHealthGrant.id == grant_id,
                RemoteHealthGrant.user_id == user_id).values(revoked_at=int(time.time())))
            db.commit()
        logger.info("remote_health owner_revocation")

    def rate_limit(self, key, limit):
        """One atomic database bucket, shared by every worker; no IP is persisted."""
        now = int(time.time())
        with self.session() as db:
            if db.bind.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            stmt = insert(RemoteHealthRateBucket).values(key=digest(key), window=now//60, count=1)
            stmt = stmt.on_conflict_do_update(index_elements=["key", "window"],
                set_={"count": RemoteHealthRateBucket.count + 1}).returning(RemoteHealthRateBucket.count)
            count = db.execute(stmt).scalar_one()
            db.query(RemoteHealthRateBucket).filter(RemoteHealthRateBucket.window < now//60 - 2).delete()
            db.query(RemoteHealthCredential).filter(RemoteHealthCredential.expires_at < now).delete()
            db.commit()
            return count <= limit
