"""OAuth provider security contracts (all credentials are synthetic)."""
import base64
import hashlib
import time

import pytest
from pydantic import AnyUrl, ValidationError

from app.services.remote_health_oauth import RemoteHealthOAuth, RemoteHealthConfig
from mcp.server.auth.provider import AuthorizationParams, TokenError


@pytest.fixture
def provider(db):
    config = RemoteHealthConfig(origin="https://health.example", clients=[{
        "client_id": "test-client", "client_name": "Test client",
        "redirect_uris": ["https://client.example/callback"],
    }])
    from sqlalchemy.orm import sessionmaker
    return RemoteHealthOAuth(config, sessionmaker(bind=db.get_bind(), expire_on_commit=False))


@pytest.fixture
def owner(db):
    from tests.conftest import create_authenticated_user
    return create_authenticated_user(db)[0]


async def issue(provider, owner):
    client, pending = await pending_request(provider)
    redirect = provider.consent(pending, owner.id, owner.id, True)
    from urllib.parse import urlsplit, parse_qs
    code = parse_qs(urlsplit(redirect).query)["code"][0]
    loaded = await provider.load_authorization_code(client, code)
    return client, loaded


async def pending_request(provider):
    client = await provider.get_client("test-client")
    verifier = "a" * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = AuthorizationParams(state="opaque-state", scopes=["health:read"],
        code_challenge=challenge, redirect_uri=AnyUrl("https://client.example/callback"),
        redirect_uri_provided_explicitly=True, resource=provider.config.resource)
    url = await provider.authorize(client, params)
    pending = url.split("request=")[1]
    return client, pending


def configure_client(provider, **policy):
    config = provider.config.model_dump()
    config["clients"][0].update(policy)
    provider.config = RemoteHealthConfig(**config)


@pytest.mark.parametrize("policy", [
    {"grant_days": 0}, {"grant_days": 3651}, {"grant_days": True},
    {"grant_days": "3650"}, {"grant_days": 30.5},
    {"grant_days": 31}, {"grant_days": 3650},
    {"allowed_user_id": 0}, {"allowed_user_id": -1},
    {"allowed_user_id": True}, {"allowed_user_id": "1"},
])
def test_client_policy_rejects_invalid_or_unpinned_long_grants(provider, policy):
    with pytest.raises(ValidationError):
        configure_client(provider, **policy)


async def test_client_policy_defaults_and_sdk_metadata_stay_public(provider):
    configured = provider.config.clients[0]
    assert configured.grant_days == 30
    assert configured.allowed_user_id is None
    configure_client(provider, grant_days=3650, allowed_user_id=123)
    client = await provider.get_client("test-client")
    assert "grant_days" not in client.model_dump()
    assert "allowed_user_id" not in client.model_dump()
    assert client.scope == "health:read"
    assert client.token_endpoint_auth_method == "none"


@pytest.mark.parametrize("days", [1, 30, 3650])
async def test_consent_preview_and_new_grant_lifetime_match_policy(provider, owner, days):
    from app.models.remote_health_oauth import RemoteHealthGrant
    configure_client(provider, grant_days=days, allowed_user_id=owner.id)
    _, pending = await pending_request(provider)
    assert provider.preview(pending)["expires_in_days"] == days
    client, code = await issue(provider, owner)
    token = await provider.exchange_authorization_code(client, code)
    access = await provider.load_access_token(token.access_token)
    with provider.session() as session:
        grant = session.get(RemoteHealthGrant, access.claims["grant_id"])
        assert grant.expires_at - grant.created_at == days * 86400
    refresh = await provider.load_refresh_token(client, token.refresh_token)
    assert refresh.expires_at <= int(time.time()) + 30 * 86400
    assert token.expires_in == 600


async def test_owner_pin_rejects_wrong_account_before_creating_grant(provider, owner, db):
    from app.models.remote_health_oauth import RemoteHealthGrant
    from tests.conftest import create_authenticated_user
    other = create_authenticated_user(db)[0]
    configure_client(provider, grant_days=3650, allowed_user_id=owner.id)
    _, pending = await pending_request(provider)
    with pytest.raises(ValueError, match="account"):
        provider.consent(pending, other.id, other.id, True)
    assert db.query(RemoteHealthGrant).count() == 0
    # A failed wrong-account attempt does not consume the rightful owner's consent.
    assert "code=" in provider.consent(pending, owner.id, owner.id, True)


async def test_owner_pin_is_rechecked_for_existing_code_access_and_refresh(provider, owner):
    client, first_code = await issue(provider, owner)
    tokens = await provider.exchange_authorization_code(client, first_code)
    _, pending_code = await issue(provider, owner)
    refresh = await provider.load_refresh_token(client, tokens.refresh_token)
    configure_client(provider, allowed_user_id=owner.id + 1)
    assert await provider.load_access_token(tokens.access_token) is None
    assert await provider.load_refresh_token(client, tokens.refresh_token) is None
    assert await provider.load_authorization_code(client, pending_code.code) is None
    with pytest.raises(TokenError):
        await provider.exchange_refresh_token(client, refresh, ["health:read"])
    with pytest.raises(TokenError):
        await provider.exchange_authorization_code(client, pending_code)


async def test_pending_consent_rejects_policy_change_before_approval(provider, owner, db):
    from app.models.remote_health_oauth import RemoteHealthGrant
    _, pending = await pending_request(provider)
    assert provider.preview(pending)["expires_in_days"] == 30
    configure_client(provider, grant_days=3650, allowed_user_id=owner.id)
    with pytest.raises(ValueError, match="changed"):
        provider.preview(pending)
    with pytest.raises(ValueError, match="changed"):
        provider.consent(pending, owner.id, owner.id, True)
    assert db.query(RemoteHealthGrant).count() == 0


@pytest.mark.parametrize("original_days,new_days", [(30, 3650), (3650, 30)])
async def test_lifetime_policy_changes_do_not_rewrite_existing_grants(provider, owner, original_days, new_days):
    from app.models.remote_health_oauth import RemoteHealthGrant
    configure_client(provider, grant_days=original_days, allowed_user_id=owner.id)
    client, code = await issue(provider, owner)
    tokens = await provider.exchange_authorization_code(client, code)
    access = await provider.load_access_token(tokens.access_token)
    with provider.session() as session:
        original = session.get(RemoteHealthGrant, access.claims["grant_id"])
        original_expiry = original.expires_at
        assert original_expiry - original.created_at == original_days * 86400
    configure_client(provider, grant_days=new_days, allowed_user_id=owner.id)
    refresh = await provider.load_refresh_token(client, tokens.refresh_token)
    rotated = await provider.exchange_refresh_token(client, refresh, ["health:read"])
    assert await provider.load_access_token(rotated.access_token) is not None
    with provider.session() as session:
        assert session.get(RemoteHealthGrant, access.claims["grant_id"]).expires_at == original_expiry


async def test_code_single_use_and_tokens_are_user_bound(provider, owner):
    client, code = await issue(provider, owner)
    token = await provider.exchange_authorization_code(client, code)
    access = await provider.load_access_token(token.access_token)
    assert access.subject == str(owner.id)
    assert access.resource == provider.config.resource
    assert access.scopes == ["health:read"]
    with pytest.raises(TokenError):
        await provider.exchange_authorization_code(client, code)


@pytest.mark.parametrize("grant_days", [30, 3650])
async def test_refresh_replay_revokes_grant(provider, owner, grant_days):
    configure_client(provider, grant_days=grant_days, allowed_user_id=owner.id)
    client, code = await issue(provider, owner)
    first = await provider.exchange_authorization_code(client, code)
    refresh = await provider.load_refresh_token(client, first.refresh_token)
    second = await provider.exchange_refresh_token(client, refresh, ["health:read"])
    with pytest.raises(TokenError):
        await provider.exchange_refresh_token(client, refresh, ["health:read"])
    assert await provider.load_access_token(second.access_token) is None


async def test_revoke_and_expiry(provider, owner, db):
    from app.models.remote_health_oauth import RemoteHealthGrant
    client, code = await issue(provider, owner)
    token = await provider.exchange_authorization_code(client, code)
    access = await provider.load_access_token(token.access_token)
    await provider.revoke_token(access)
    assert await provider.load_access_token(token.access_token) is None
    client, code = await issue(provider, owner)
    token = await provider.exchange_authorization_code(client, code)
    db.query(RemoteHealthGrant).update({"expires_at": int(time.time()) - 1})
    db.commit()
    assert await provider.load_access_token(token.access_token) is None


async def test_postgres_concurrent_code_exchange_single_winner(provider, owner, db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock semantics")
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    client, code = await issue(provider, owner)
    barrier = Barrier(2)
    def exchange():
        barrier.wait(timeout=5)
        try:
            return asyncio.run(provider.exchange_authorization_code(client, code))
        except TokenError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(exchange) for _ in range(2)]
        results = [f.result(timeout=10) for f in futures]
    assert sum(r is not None for r in results) == 1
    issued = next(r for r in results if r is not None)
    assert await provider.load_access_token(issued.access_token) is None


def test_managed_migration_replays_and_matches_model(db):
    from pathlib import Path
    from sqlalchemy import inspect, text
    from app.models.remote_health_oauth import RemoteHealthGrant, RemoteHealthCredential, RemoteHealthRateBucket
    engine = db.get_bind()
    dialect = engine.dialect.name
    sql = Path(f"migrations/managed/20261001_150000_remote_health_oauth.{dialect}.sql").read_text()
    with engine.begin() as connection:
        for model in (RemoteHealthRateBucket, RemoteHealthCredential, RemoteHealthGrant):
            model.__table__.drop(connection)
        for _ in range(2):
            for statement in sql.split(";"):
                if statement.strip():
                    connection.execute(text(statement))
        inspector = inspect(connection)
        for model in (RemoteHealthGrant, RemoteHealthCredential, RemoteHealthRateBucket):
            assert {c["name"] for c in inspector.get_columns(model.__tablename__)} == set(model.__table__.columns.keys())
        assert inspector.get_foreign_keys("remote_health_credentials")[0]["referred_table"] == "remote_health_grants"
