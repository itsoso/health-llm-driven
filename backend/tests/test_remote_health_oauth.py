"""OAuth provider security contracts (all credentials are synthetic)."""
import base64
import hashlib
import time

import pytest
from pydantic import AnyUrl

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
    client = await provider.get_client("test-client")
    verifier = "a" * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = AuthorizationParams(state="opaque-state", scopes=["health:read"],
        code_challenge=challenge, redirect_uri=AnyUrl("https://client.example/callback"),
        redirect_uri_provided_explicitly=True, resource=provider.config.resource)
    url = await provider.authorize(client, params)
    pending = url.split("request=")[1]
    redirect = provider.consent(pending, owner.id, owner.id, True)
    from urllib.parse import urlsplit, parse_qs
    code = parse_qs(urlsplit(redirect).query)["code"][0]
    loaded = await provider.load_authorization_code(client, code)
    return client, loaded


async def test_code_single_use_and_tokens_are_user_bound(provider, owner):
    client, code = await issue(provider, owner)
    token = await provider.exchange_authorization_code(client, code)
    access = await provider.load_access_token(token.access_token)
    assert access.subject == str(owner.id)
    assert access.resource == provider.config.resource
    assert access.scopes == ["health:read"]
    with pytest.raises(TokenError):
        await provider.exchange_authorization_code(client, code)


async def test_refresh_replay_revokes_grant(provider, owner):
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
