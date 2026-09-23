"""Real browser auth -> Agent -> authenticated internal API, with synthetic data.

Only model output and HTTP transport are replaced. Auth, consent, executor,
capability policy and supplement persistence remain real.
"""

import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.agent_conversation import AgentMessage
from app.models.family import FamilyGroup, FamilyMember
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user_api_key import UserApiKey
from app.services import ai_consent
from app.services.agent_executor import AgentExecutor
from app.services.auth import auth_service
from app.services.web_session import WEB_SESSION_AUTH_SENTINEL, WEB_SESSION_COOKIE
from tests.conftest import create_authenticated_user
from main import app


MESSAGE = "记录补剂：1粒营养素甲 2片营养素乙"
BATCH_PATH = "/api/v1/supplements/records/intake-batch"


@pytest.fixture
def relay(db, client, monkeypatch):
    from app.celery_app import celery_app

    # Keep ancillary post-turn work on an in-memory transport, never a worker.
    monkeypatch.setitem(celery_app.conf, "broker_url", "memory://")
    monkeypatch.setitem(celery_app.conf, "result_backend", "cache+memory://")
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False)
    monkeypatch.setattr("app.database.SessionLocal", sessions)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessions)
    monkeypatch.setattr(settings, "web_session_allowed_origins", "http://testserver")
    monkeypatch.setattr(settings, "health_api_base_url", "http://relay.test/api/v1")
    monkeypatch.setattr(settings, "agent_runtime_mode", "off")
    monkeypatch.setattr("app.utils.redis_cache.get_redis_client", lambda: None)

    owner, token = create_authenticated_user(db)
    other, _ = create_authenticated_user(db)
    ai_consent.update_ai_consent(db, owner.id, True, ai_consent.POLICY_VERSION)
    client.cookies.set(WEB_SESSION_COOKIE, token)
    state = SimpleNamespace(owner=owner, other=other, credential=token,
                            credentials=[token], calls=[], prompts=[], before_internal=None)
    original_client = httpx.AsyncClient

    class InternalTransport(httpx.ASGITransport):
        async def handle_async_request(self, request):
            assert request.url.host == "relay.test", "Unexpected external HTTP request"
            assert request.url.path == BATCH_PATH
            assert "cookie" not in request.headers
            exact_credential = request.headers.get("authorization") == f"Bearer {state.credential}"
            if state.before_internal is not None:
                state.before_internal()
            response = await super().handle_async_request(request)
            state.calls.append((request.url.path, response.status_code, exact_credential))
            return response

    def internal_client(*args, **kwargs):
        kwargs["transport"] = InternalTransport(app=app)
        return original_client(*args, **kwargs)

    async def model_response(self, messages, tools):
        serialized = json.dumps(messages, ensure_ascii=False)
        assert all(secret not in serialized for secret in state.credentials), "Credential reached model"
        state.prompts.append(True)
        return {"content": "请查看执行结果。", "tool_calls": [], "finish_reason": "stop"}

    async def model_stream(self, messages, tools):
        result = await model_response(self, messages, tools)
        yield {"type": "content", "text": result["content"]}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(httpx, "AsyncClient", internal_client)
    monkeypatch.setattr(AgentExecutor, "_call_llm", model_response)
    monkeypatch.setattr(AgentExecutor, "_call_llm_stream", model_stream)
    return state


def _headers(relay, *, sentinel=False):
    result = {"Origin": "http://testserver", "X-Reva-AI-Subject": str(relay.owner.id)}
    if sentinel:
        result["Authorization"] = f"Bearer {WEB_SESSION_AUTH_SENTINEL}"
    return result


def _post(client, route, headers, message=MESSAGE):
    return client.post(f"/api/v1/agent/{route}", headers=headers, json={
        "message": message, "client_turn_id": f"relay-{uuid4().hex}",
    })


def _assert_owned_write(db, relay, response, caplog, expected=None):
    assert response.status_code == 200
    # Fail on the actual internal HTTP boundary, not a mocked token receiver.
    assert relay.calls == [(BATCH_PATH, 200, True)]
    db.expire_all()
    definitions = db.query(SupplementDefinition).filter_by(user_id=relay.owner.id).all()
    names = {row.id: row.name for row in definitions}
    records = db.query(SupplementRecord).filter_by(user_id=relay.owner.id).all()
    assert {(names[row.supplement_id], row.actual_dosage) for row in records} == (expected or {
        ("营养素甲", "1粒"), ("营养素乙", "2片"),
    })
    assert db.query(SupplementRecord).filter_by(user_id=relay.other.id).count() == 0
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        events = [json.loads(line.removeprefix("data: "))
                  for line in response.text.splitlines() if line.startswith("data: ")]
        done = next(event["data"] for event in events if event.get("event") == "done")
        assert done["turn_outcome"]["category"] == "success"
        receipts = done["write_receipts"]
    else:
        # /send projects a compact response; its assistant row retains receipts.
        done = response.json()
        receipts = db.get(AgentMessage, done["message_id"]).meta["write_receipts"]
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["verified"] is True and receipt["status"] == "verified"
    assert receipt["resource_type"] == "supplement_log"
    assert int(receipt["resource_id"]) in {row.id for row in records}
    messages = db.query(AgentMessage).all()
    stored = json.dumps([(row.content, row.meta) for row in messages], ensure_ascii=False)
    for secret in relay.credentials:
        assert secret not in response.text, "Credential leaked in response"
        assert secret not in caplog.text, "Credential leaked in logs"
        assert secret not in stored, "Credential persisted in conversation"


@pytest.mark.parametrize("route", ["stream", "send"])
@pytest.mark.parametrize("sentinel", [False, True], ids=["cookie-only", "sentinel"])
def test_web_cookie_reaches_internal_owned_batch(client, db, relay, caplog, route, sentinel):
    response = _post(client, route, _headers(relay, sentinel=sentinel))
    _assert_owned_write(db, relay, response, caplog)


@pytest.mark.parametrize("sentinel", [False, True], ids=["cookie-only", "sentinel"])
def test_postgres_web_stream_receipt_matches_owned_rows(client, db, relay, caplog, sentinel):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated TEST_DATABASE_URL PostgreSQL")
    response = _post(client, "stream", _headers(relay, sentinel=sentinel))
    _assert_owned_write(db, relay, response, caplog)


@pytest.mark.parametrize("route", ["stream", "send"])
def test_web_qualified_supplement_batch_preserves_exact_products(client, db, relay, caplog, monkeypatch, route):
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    for owner in (relay.owner, relay.other):
        for name in ("复合维生素B", "MitoQ 心脏版", "Mitoq"):
            db.add(SupplementDefinition(user_id=owner.id, name=name, dosage="3粒", is_active=True))
    db.commit()
    response = _post(client, route, _headers(relay, sentinel=True),
                     message="记录补剂：1 粒复合VB 1 粒 Mitoq 心脏版")
    _assert_owned_write(db, relay, response, caplog,
                        expected={("复合VB", "1粒"), ("MitoQ 心脏版", "1粒")})
    assert db.query(SupplementDefinition).count() == 7
    # Abbreviations do not authorize guessing a different existing product.
    assert all(row.dosage == "3粒" for row in db.query(SupplementDefinition).all()
               if row.name != "复合VB")


@pytest.mark.parametrize("zone", ["UTC", "Asia/Shanghai", "America/New_York"])
def test_postgres_web_unit_reply_clarifies_without_model_or_write(client, db, relay, monkeypatch, zone):
    from sqlalchemy import text
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated TEST_DATABASE_URL PostgreSQL")
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    db.execute(text("SELECT set_config('TimeZone', :zone, false)"), {"zone": zone})
    db.commit()
    headers = _headers(relay, sentinel=True)
    first = _post(client, "stream", headers, message="记录补剂：1 营养素甲 1 营养素乙")
    assert first.status_code == 200
    first_done = next(json.loads(line[6:])["data"] for line in first.text.splitlines()
                      if line.startswith("data: ") and json.loads(line[6:]).get("event") == "done")
    response = client.post("/api/v1/agent/stream", headers=headers, json={
        "message": "一粒", "conversation_id": first_done["conversation_id"],
        "client_turn_id": f"relay-{uuid4().hex}",
    })
    assert response.status_code == 200
    done = next(json.loads(line[6:])["data"] for line in response.text.splitlines()
                if line.startswith("data: ") and json.loads(line[6:]).get("event") == "done")
    assert done["turn_outcome"]["reason_code"] == "supplement_unit_scope_required"
    assert done["model_call_count"] == 0
    assert relay.calls == [] and relay.prompts == []
    assert db.query(SupplementRecord).filter_by(user_id=relay.owner.id).count() == 0


@pytest.mark.parametrize("route", ["stream", "send"])
@pytest.mark.parametrize("rejection,status,reason", [
    ("named-definition", 409, "supplement_name_ambiguous"),
    ("revoked-auth", 401, "supplement_auth_rejected"),
])
def test_web_known_prewrite_rejection_is_actionable_without_reconciliation(
    client, db, relay, monkeypatch, route, rejection, status, reason,
):
    from app.models.agent_runtime import AgentRun, AgentToolOperation

    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    candidate = "营养素甲标准版"
    foreign_candidate = "营养素甲他人产品"
    if rejection == "named-definition":
        db.add_all([
            SupplementDefinition(user_id=relay.owner.id, name=candidate, dosage="3粒", is_active=True),
            SupplementDefinition(user_id=relay.other.id, name=foreign_candidate, dosage="4粒", is_active=True),
        ])
        db.commit()
    else:
        def revoke():
            # Invalidate the previously authenticated cookie only at the
            # internal HTTP boundary. Real JWT verification must reject it;
            # no auth dependency or HTTP response is mocked.
            monkeypatch.setattr("app.services.auth.SECRET_KEY", "synthetic-relay-rotated-signing-key")
        relay.before_internal = revoke

    response = _post(client, route, _headers(relay, sentinel=True))
    assert response.status_code == 200
    assert relay.calls == [(BATCH_PATH, status, True)]
    db.expire_all()
    assert db.query(SupplementRecord).count() == 0
    assert db.query(SupplementDefinition).count() == (2 if rejection == "named-definition" else 0)
    run = db.query(AgentRun).filter_by(user_id=relay.owner.id).one()
    operations = db.query(AgentToolOperation).filter_by(run_id=run.run_id).all()
    assert run.status != "reconciliation_required"
    assert run.error_code != "write_uncertain"
    assert len(operations) == 1 and operations[0].status == "failed"
    # Runtime intentionally normalizes definite pre-dispatch failures; the
    # detailed adapter reason remains on the user-visible tool result event.
    assert operations[0].error_code == "tool_rejected"

    if route == "stream":
        events = [json.loads(line.removeprefix("data: "))
                  for line in response.text.splitlines() if line.startswith("data: ")]
        done = next(event["data"] for event in events if event.get("event") == "done")
        tool_result = next(event["data"] for event in events if event.get("event") == "tool_result")
        assert tool_result["error_code"] == reason
        assert tool_result["write_outcome"] == "rejected"
        assert tool_result["dispatch_started"] is False
        reply = "".join(event["data"].get("content", "")
                        for event in events if event.get("event") == "token")
        meta = done
    else:
        done = response.json()
        reply = done["reply"]
        meta = db.get(AgentMessage, done["message_id"]).meta
    assert meta["turn_outcome"]["status"] != "reconciliation_required"
    assert meta["turn_outcome"]["category"] != "write_reconciliation_required"
    assert not meta.get("write_receipts")
    assert "write_uncertain" not in response.text
    assert all(marker not in reply for marker in ("核对记录状态", "不要重复提交", "可能已写入"))
    assert any(marker in reply for marker in ("未写入", "没有写入", "还没记下来"))
    assert relay.credential not in response.text
    if rejection == "named-definition":
        assert candidate in reply and foreign_candidate not in reply
        assert "完整名称" in reply and "剂量" in reply
    else:
        assert "重新登录" in reply


@pytest.mark.parametrize("route", ["stream", "send"])
@pytest.mark.parametrize("boundary,expected", [
    ("missing-origin", 403), ("foreign-origin", 403),
    ("missing-consent", 403), ("foreign-subject", 409),
    ("missing-subject", 409), ("invalid-bearer", 401),
])
def test_cookie_boundaries_block_before_model_or_tool(
    client, db, relay, route, boundary, expected,
):
    headers = _headers(relay, sentinel=True)
    if boundary == "missing-origin":
        headers.pop("Origin")
    elif boundary == "foreign-origin":
        headers["Origin"] = "https://foreign.example"
    elif boundary == "missing-consent":
        ai_consent.update_ai_consent(db, relay.owner.id, False, ai_consent.POLICY_VERSION)
    elif boundary == "foreign-subject":
        headers["X-Reva-AI-Subject"] = str(relay.other.id)
    elif boundary == "missing-subject":
        headers.pop("X-Reva-AI-Subject")
    elif boundary == "invalid-bearer":
        headers["Authorization"] = "Bearer invalid-synthetic-token"
    response = _post(client, route, headers)
    assert response.status_code == expected
    assert relay.calls == [] and relay.prompts == []
    assert db.query(SupplementRecord).count() == 0


@pytest.mark.parametrize("route", ["stream", "send"])
def test_native_bearer_wins_over_cookie_without_origin(client, db, relay, caplog, route):
    native, token = create_authenticated_user(db)
    ai_consent.update_ai_consent(db, native.id, True, ai_consent.POLICY_VERSION)
    relay.other, relay.owner = relay.owner, native
    relay.credential = token
    relay.credentials.append(token)
    response = _post(client, route, {"Authorization": f"bEaReR {token}"})
    _assert_owned_write(db, relay, response, caplog)


@pytest.mark.parametrize("route", ["stream", "send"])
@pytest.mark.parametrize("transport", ["bearer", "x-api-key"])
@pytest.mark.parametrize("scopes", ["read", "read,write"])
def test_scoped_api_key_is_relayed_without_elevation(
    client, db, relay, caplog, route, transport, scopes,
):
    client.cookies.clear()
    key = f"synthetic-key-{uuid4().hex}"
    db.add(UserApiKey(user_id=relay.owner.id, name="relay-test",
                      api_key=hashlib.sha256(key.encode()).hexdigest(), scopes=scopes))
    db.commit()
    relay.credential = key
    relay.credentials.append(key)
    headers = {"Authorization": f"Bearer {key}"} if transport == "bearer" else {"X-API-Key": key}
    response = _post(client, route, headers)
    if scopes == "read":
        assert response.status_code == 403
        assert relay.calls == [] and relay.prompts == []
        assert db.query(SupplementRecord).count() == 0
    else:
        _assert_owned_write(db, relay, response, caplog)


@pytest.mark.parametrize("route", ["stream", "send"])
@pytest.mark.parametrize("revoke_before_internal", [False, True])
def test_cookie_proxy_claims_survive_internal_reauthentication(
    client, db, relay, caplog, route, revoke_before_internal,
):
    origin, target = relay.owner, relay.other
    group = FamilyGroup(name="Synthetic relay family", owner_id=origin.id)
    db.add(group)
    db.flush()
    db.add_all([
        FamilyMember(family_group_id=group.id, user_id=origin.id,
                     relationship_type="self", role="owner"),
        FamilyMember(family_group_id=group.id, user_id=target.id,
                     relationship_type="other", role="member", can_edit=True),
    ])
    db.commit()
    token = auth_service.create_access_token({
        "sub": str(target.id), "acting_as": target.id, "original_user": origin.id,
    })
    ai_consent.update_ai_consent(db, target.id, True, ai_consent.POLICY_VERSION)
    relay.owner, relay.other = target, origin
    relay.credential = token
    relay.credentials.append(token)
    client.cookies.set(WEB_SESSION_COOKIE, token)
    if revoke_before_internal:
        def revoke():
            db.query(FamilyMember).filter_by(
                family_group_id=group.id, user_id=target.id,
            ).delete()
            db.commit()
        relay.before_internal = revoke
    response = _post(client, route, _headers(relay, sentinel=True))
    if revoke_before_internal:
        # Reauthentication must still enforce the original proxy grant. A new
        # subject-only JWT would incorrectly authorize this internal write.
        assert relay.calls == [(BATCH_PATH, 403, True)]
        assert db.query(SupplementRecord).count() == 0
    else:
        _assert_owned_write(db, relay, response, caplog)


@pytest.mark.parametrize("route", ["stream", "send"])
def test_cookie_credential_does_not_reach_model(client, db, relay, caplog, route):
    response = _post(client, route, _headers(relay, sentinel=True),
                     message="用一句话介绍你能提供哪些功能")
    assert response.status_code == 200
    assert relay.prompts, "Must exercise the model boundary, not a deterministic shortcut"
    assert relay.calls == []
    stored = json.dumps([(row.content, row.meta) for row in db.query(AgentMessage)],
                        ensure_ascii=False)
    assert relay.credential not in response.text
    assert relay.credential not in caplog.text
    assert relay.credential not in stored


@pytest.mark.parametrize("binding", ["absent", "wrong-user", "wrong-auth-type"])
def test_relay_requires_successful_auth_binding(binding):
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.api.deps import get_authenticated_relay_token

    request = Request({"type": "http", "headers": [
        (b"cookie", b"health_session=unverified-synthetic-token"),
    ]})
    if binding != "absent":
        request.state.auth_type = "cookie"
        request.state._authenticated_relay_credential = (
            2 if binding == "wrong-user" else 1,
            "jwt" if binding == "wrong-auth-type" else "cookie",
            "synthetic-bound-token",
        )
    with pytest.raises(HTTPException) as rejected:
        get_authenticated_relay_token(request, SimpleNamespace(id=1))
    assert rejected.value.status_code == 401
