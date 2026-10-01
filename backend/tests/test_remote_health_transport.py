"""Exercise real SDK OAuth/Streamable HTTP routes with synthetic accounts."""
import base64
import hashlib
from urllib.parse import parse_qs, urlsplit
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.remote_health import install_remote_health
from app.database import get_db
from app.services.remote_health_oauth import RemoteHealthConfig, PREFIX, digest
from app.services.web_session import WEB_SESSION_COOKIE
from tests.conftest import create_authenticated_user

ORIGIN = "https://health.example"
RESOURCE = ORIGIN + PREFIX + "/mcp"
REDIRECT = "https://client.example/callback"
VERIFIER = "a" * 43
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


@pytest.fixture
def connected(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "web_session_allowed_origins", ORIGIN)
    app = FastAPI()
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    provider = install_remote_health(app, RemoteHealthConfig(origin=ORIGIN, clients=[
        {"client_id":"test-client", "client_name":"Test client", "redirect_uris":[REDIRECT]},
        {"client_id":"other-client", "client_name":"Other client", "redirect_uris":[REDIRECT]},
    ]), factory)
    app.dependency_overrides[get_db] = lambda: db
    user, token = create_authenticated_user(db)
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        client.cookies.set(WEB_SESSION_COOKIE, token)
        yield client, provider, user


def pending(client, **overrides):
    params = dict(client_id="test-client", redirect_uri=REDIRECT, response_type="code",
        scope="health:read", state="opaque-state", resource=RESOURCE,
        code_challenge=CHALLENGE, code_challenge_method="S256")
    params.update(overrides)
    return client.get(PREFIX + "/authorize", params=params)


def consent(client, user, approved=True):
    response = pending(client)
    assert response.status_code == 302, response.text
    raw = parse_qs(urlsplit(response.headers["location"]).query)["request"][0]
    preview = client.get(PREFIX + "/consent", params={"request":raw})
    assert preview.json()["user_id"] == user.id
    response = client.post(PREFIX + "/consent", headers={"Origin":ORIGIN},
        json={"request":raw, "expected_user_id":user.id, "approved":approved})
    assert response.status_code == 200, response.text
    query = parse_qs(urlsplit(response.json()["redirect_uri"]).query)
    assert query["iss"] == [ORIGIN + PREFIX]
    return query


def exchange(client, code, **overrides):
    data = dict(grant_type="authorization_code", client_id="test-client", code=code,
        code_verifier=VERIFIER, redirect_uri=REDIRECT, resource=RESOURCE)
    data.update(overrides)
    return client.post(PREFIX + "/token", data=data)


def rpc(client, token, method, params=None):
    return client.post(PREFIX + "/mcp", headers={"Authorization":"Bearer " + token,
        "Accept":"application/json, text/event-stream", "MCP-Protocol-Version":"2025-11-25"},
        json={"jsonrpc":"2.0", "id":1, "method":method, "params":params or {}})


def test_metadata_and_unauthenticated_challenge(connected):
    client, _, _ = connected
    meta = client.get("/.well-known/oauth-authorization-server" + PREFIX).json()
    assert meta["token_endpoint_auth_methods_supported"] == ["none"]
    assert meta["code_challenge_methods_supported"] == ["S256"]
    response = client.post(PREFIX + "/mcp", json={})
    assert response.status_code == 401
    assert "oauth-protected-resource" in response.headers["www-authenticate"]


def test_real_pkce_consent_read_tools_and_write_refusal(connected):
    client, _, user = connected
    code = consent(client,user)["code"][0]
    response = exchange(client,code)
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert response.headers["cache-control"] == "no-store, no-store"
    init = rpc(client,token,"initialize", {"protocolVersion":"2025-11-25", "capabilities":{}, "clientInfo":{"name":"test","version":"1"}})
    assert init.status_code == 200, init.text
    tools = rpc(client,token,"tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"get_sleep","get_diet","get_exercise"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    result = rpc(client,token,"tools/call",{"name":"get_sleep","arguments":{
        "start_date":"2026-01-01","end_date":"2026-01-02","timezone":"Asia/Shanghai"}})
    assert result.status_code == 200, result.text
    assert not result.json()["result"].get("isError"), result.text
    refused = rpc(client,token,"tools/call",{"name":"record_water","arguments":{}}).json()
    assert "error" in refused or refused.get("result",{}).get("isError")
    assert exchange(client,code).status_code == 400
    assert rpc(client,token,"tools/list").status_code == 401


@pytest.mark.parametrize("overrides", [
    {"redirect_uri":"https://evil.example/callback"}, {"resource":"https://evil.example/mcp"},
    {"code_challenge_method":"plain"}, {"scope":"health:write"}, {"client_id":"unknown"},
])
def test_invalid_authorization_does_not_create_pending(connected,db,overrides):
    from app.models.remote_health_oauth import RemoteHealthCredential
    client, _, _ = connected
    response = pending(client,**overrides)
    assert response.status_code in {302,400}
    assert db.query(RemoteHealthCredential).count() == 0
    if response.status_code == 302:
        assert response.headers["location"].startswith(REDIRECT + "?")


@pytest.mark.parametrize("overrides", [{"code_verifier":"b"*43},{"redirect_uri":"https://evil.example"},
    {"client_id":"other-client"},{"resource":"https://evil.example/mcp"}])
def test_token_binding_denials(connected,overrides):
    client, _, user = connected
    code = consent(client,user)["code"][0]
    assert exchange(client,code,**overrides).status_code == 400


def test_deny_creates_no_grant(connected,db):
    from app.models.remote_health_oauth import RemoteHealthGrant
    client, _, user = connected
    assert consent(client,user,False)["error"] == ["access_denied"]
    assert db.query(RemoteHealthGrant).count() == 0


def test_owner_revocation_and_other_user_isolation(connected,db):
    client, _, user = connected
    tokens = exchange(client,consent(client,user)["code"][0]).json()
    connections = client.get(PREFIX + "/connections").json()
    other, other_session = create_authenticated_user(db)
    original_session = client.cookies.get(WEB_SESSION_COOKIE)
    client.cookies.set(WEB_SESSION_COOKIE, other_session)
    assert client.get(PREFIX + "/connections").json() == []
    client.delete(PREFIX + "/connections/" + connections[0]["id"], headers={"Origin":ORIGIN})
    assert rpc(client,tokens["access_token"],"tools/list").status_code == 200
    client.cookies.set(WEB_SESSION_COOKIE, original_session)
    assert client.delete(PREFIX + "/connections/" + connections[0]["id"], headers={"Origin":ORIGIN}).status_code == 200
    assert rpc(client,tokens["access_token"],"tools/list").status_code == 401


def test_consent_csrf_and_account_change(connected):
    client, _, user = connected
    response = pending(client)
    raw = parse_qs(urlsplit(response.headers["location"]).query)["request"][0]
    body = {"request":raw,"expected_user_id":user.id,"approved":True}
    assert client.post(PREFIX + "/consent",json=body).status_code == 403
    assert client.post(PREFIX + "/consent",headers={"Origin":"https://evil.example"},json=body).status_code == 403
    body["expected_user_id"] += 1
    assert client.post(PREFIX + "/consent",headers={"Origin":ORIGIN},json=body).status_code == 400


def test_tokens_not_persisted_and_disabled_accounts_denied(connected,db):
    from app.models.remote_health_oauth import RemoteHealthCredential
    client, _, user = connected
    tokens = exchange(client,consent(client,user)["code"][0]).json()
    assert db.get(RemoteHealthCredential,digest(tokens["access_token"]))
    rows = db.query(RemoteHealthCredential).all()
    assert all(tokens["access_token"] not in str(r.payload) for r in rows)
    user.is_active=False
    db.commit()
    assert rpc(client,tokens["access_token"],"tools/list").status_code == 401


def test_body_and_origin_limits(connected):
    client, _, _ = connected
    assert client.post(PREFIX + "/mcp",content=b"x"*16385).status_code == 413
    assert client.post(PREFIX + "/mcp",headers={"Origin":"https://evil.example"}).status_code == 403
    assert client.post(PREFIX + "/consent",content=b"x"*16385).status_code == 413


def test_public_client_rfc7009_revocation(connected):
    client, _, user = connected
    tokens = exchange(client,consent(client,user)["code"][0]).json()
    response = client.post(PREFIX + "/revoke",data={"client_id":"test-client","token":tokens["refresh_token"]})
    assert response.status_code == 200
    assert rpc(client,tokens["access_token"],"tools/list").status_code == 401
    assert client.post(PREFIX + "/token",data={"grant_type":"refresh_token","client_id":"test-client",
        "resource":RESOURCE,"refresh_token":tokens["refresh_token"]}).status_code == 400


def test_http_refresh_rotation_replay(connected):
    client, _, user = connected
    tokens = exchange(client,consent(client,user)["code"][0]).json()
    data = {"grant_type":"refresh_token","client_id":"test-client","resource":RESOURCE,"refresh_token":tokens["refresh_token"]}
    response = client.post(PREFIX + "/token",data=data)
    assert response.status_code == 200
    latest = response.json()
    assert latest["refresh_token"] != tokens["refresh_token"]
    assert client.post(PREFIX + "/token",data=data).status_code == 400
    assert rpc(client,latest["access_token"],"tools/list").status_code == 401


@pytest.mark.parametrize("payload",[
    {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"PRIVATE_MARKER","arguments":{}}},
    {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":{"PRIVATE_MARKER":True}}},
    {"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":{"PRIVATE_MARKER":True}}},
])
def test_sdk_diagnostics_never_log_private_inputs(connected,caplog,payload):
    import logging
    client, _, user = connected
    tokens = exchange(client,consent(client,user)["code"][0]).json()
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        client.post(PREFIX + "/mcp",headers={"Authorization":"Bearer " + tokens["access_token"],
            "Accept":"application/json, text/event-stream"},json=payload)
    assert "PRIVATE_MARKER" not in caplog.text


def test_pending_expiry_cleanup_and_ingress_limits(connected,db,monkeypatch):
    import time
    from app.models.remote_health_oauth import RemoteHealthCredential
    client, provider, _ = connected
    assert pending(client).status_code == 302
    db.query(RemoteHealthCredential).update({"expires_at":int(time.time())-1})
    db.commit()
    assert provider.rate_limit("cleanup",1)
    assert db.query(RemoteHealthCredential).count() == 0
    assert not provider.rate_limit("cleanup",1)
    monkeypatch.setattr(provider,"rate_limit",lambda *args:False)
    assert client.get(PREFIX + "/connections").status_code == 429


def test_default_off_in_main():
    from main import app
    assert not any(getattr(route,"path","").startswith(PREFIX) for route in app.routes)
