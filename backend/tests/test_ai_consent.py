"""Explicit AI disclosure must precede sharing; withdrawal is not cached."""
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from tests.conftest import create_authenticated_user
from app.models.user_profile import UserProfile
from app.models.agent_audit_log import AgentAuditLog


def _headers(db):
    user, token = create_authenticated_user(db)
    return user, {"Authorization": f"Bearer {token}"}


def test_consent_requires_explicit_current_policy_and_supports_revocation(client, db):
    user, headers = _headers(db)
    initial = client.get("/api/v1/auth/ai-consent", headers=headers)
    assert initial.status_code == 200
    state = initial.json()
    assert state["accepted"] is False
    assert state["accepted_at"] is None
    assert state["recipients"] and state["data_types"]
    stale = client.put("/api/v1/auth/ai-consent", headers=headers,
                       json={"accepted": True, "policy_version": "outdated"})
    assert stale.status_code == 409
    granted = client.put("/api/v1/auth/ai-consent", headers=headers,
                         json={"accepted": True, "policy_version": state["policy_version"]})
    assert granted.status_code == 200
    assert granted.json()["accepted"] is True
    assert granted.json()["accepted_at"]
    revoked = client.put("/api/v1/auth/ai-consent", headers=headers,
                         json={"accepted": False, "policy_version": "outdated"})
    assert revoked.status_code == 200
    assert revoked.json()["accepted"] is False
    assert db.query(AgentAuditLog).filter_by(user_id=user.id, agent_type="ai_consent").count() == 2


def test_consent_is_authenticated_user_isolated_and_not_profile_editable(client, db):
    user, headers = _headers(db)
    other, other_headers = _headers(db)
    assert client.get("/api/v1/auth/ai-consent").status_code == 401
    state = client.get("/api/v1/auth/ai-consent", headers=headers).json()
    assert "policy_version" in state
    body = {"accepted": True, "policy_version": state["policy_version"]}
    assert client.put("/api/v1/auth/ai-consent", headers=headers,
                      json={**body, "user_id": other.id}).status_code == 422
    assert client.put("/api/v1/auth/ai-consent", headers=headers, json=body).status_code == 200
    assert client.get("/api/v1/auth/ai-consent", headers=other_headers).json()["accepted"] is False
    assert client.put("/api/v1/profile/me", headers=headers,
                      json={"privacy_settings": {"weight": False}}).status_code == 200
    assert client.get("/api/v1/auth/ai-consent", headers=headers).json()["accepted"] is True
    forged = client.put("/api/v1/profile/me", headers=other_headers,
                        json={"privacy_settings": {"_ai_consent_v1": body}})
    assert forged.status_code == 422


def test_provider_guard_uses_fresh_consent_and_denies_unknown_recipient(db, monkeypatch):
    from app.services import ai_consent
    user, _ = _headers(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    with pytest.raises(HTTPException) as denied:
        ai_consent.require_ai_consent(user.id, destination="https://dashscope.aliyuncs.com/api/v1")
    assert denied.value.status_code == 403
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    ai_consent.require_ai_consent(user.id, destination="https://dashscope.aliyuncs.com/api/v1")
    for url in ("https://unknown.example/v1", "https://dashscope.aliyuncs.com.attacker.test/v1", "http://dashscope.aliyuncs.com/v1"):
        with pytest.raises(HTTPException):
            ai_consent.require_ai_consent(user.id, destination=url)
    ai_consent.update_ai_consent(db, user.id, False, ai_consent.POLICY_VERSION)
    with pytest.raises(HTTPException):
        ai_consent.require_ai_consent(user.id)


def test_provider_guard_denies_missing_identity_stale_policy_and_db_failure(db, monkeypatch):
    from app.services import ai_consent
    user, _ = _headers(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    with ai_consent.ai_user_scope(None):
        with pytest.raises(HTTPException):
            ai_consent.require_ai_consent()
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    monkeypatch.setattr(ai_consent, "POLICY_VERSION", "next-policy")
    with pytest.raises(HTTPException):
        ai_consent.require_ai_consent(user.id)
    def unavailable():
        raise RuntimeError("private database failure")
    monkeypatch.setattr(ai_consent, "SessionLocal", unavailable)
    with pytest.raises(HTTPException) as denied:
        ai_consent.require_ai_consent(user.id)
    assert denied.value.status_code == 503
    assert "private" not in str(denied.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["chat", "chat_stream", "vision", "legacy_stream"])
async def test_openai_provider_never_dispatches_without_consent(monkeypatch, method):
    from app.services.llm.providers.openai_provider import OpenAIProvider
    from app.services.ai_consent import ai_user_scope
    provider = OpenAIProvider(api_key="test-only", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    def forbidden_client():
        pytest.fail("provider reached network client before consent")
    monkeypatch.setattr(provider, "_get_client", forbidden_client)
    monkeypatch.setattr(provider, "_get_async_client", forbidden_client)
    with ai_user_scope(None), pytest.raises(HTTPException) as denied:
        if method == "chat":
            await provider.chat([{"role": "user", "content": "private"}])
        elif method == "vision":
            await provider.chat_with_vision([], "data:image/png;base64,cHJpdmF0ZQ==")
        elif method == "legacy_stream":
            stream = await provider.chat([], stream=True)
            await anext(stream)
        else:
            await anext(provider.chat_stream([]))
    assert denied.value.status_code == 403


def test_model_options_do_not_offer_undisclosed_hosts(monkeypatch):
    from app.api.user_llm_preference import _list_options
    from app.services.llm.model_registry import ModelEntry
    from app.services.llm import model_registry
    entries = [
        ModelEntry(id="ali", label="Ali", provider="tokenplan", model="qwen", speed_tier="fast"),
        ModelEntry(id="unknown", label="Unknown", provider="openai-proxy", model="unknown", speed_tier="fast"),
    ]
    monkeypatch.setattr(model_registry, "list_models", lambda **kw: entries)
    assert [m.id for m in _list_options()] == ["ali"]


def test_explicit_clear_caller_does_not_reuse_previous_user():
    from app.services.llm.usage_tracker import set_caller, get_caller_user_id
    set_caller("job-one", user_id=7)
    set_caller("job-two", user_id=None)
    assert get_caller_user_id() is None


@pytest.mark.asyncio
async def test_retry_rechecks_withdrawal_before_second_dispatch(db, monkeypatch):
    from types import SimpleNamespace
    from app.services import ai_consent
    from app.services.llm.providers.openai_provider import OpenAIProvider
    user, _ = _headers(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    sent = []
    async def first_dispatch(**kwargs):
        sent.append(kwargs)
        ai_consent.update_ai_consent(db, user.id, False, ai_consent.POLICY_VERSION)
        raise ValueError("retryable upstream error")
    provider = OpenAIProvider(api_key="test-only", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    provider._async_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=first_dispatch)))
    with ai_consent.ai_user_scope(user.id), pytest.raises(HTTPException):
        await anext(provider.chat_stream([{"role": "user", "content": "private"}]))
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_request_identity_is_cleared_and_does_not_leak_to_next_request(db, monkeypatch):
    from app.services import ai_consent
    from app.services.llm.usage_tracker import set_caller
    user, _ = _headers(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    scope = ai_consent.ai_request_scope()
    await anext(scope)
    ai_consent.bind_ai_user(user.id)
    ai_consent.require_ai_consent()
    await scope.aclose()
    set_caller("unbound-background", user_id=None)
    with pytest.raises(HTTPException):
        ai_consent.require_ai_consent()


@pytest.mark.asyncio
async def test_stale_profile_edit_cannot_resurrect_revoked_permission(db):
    from app.services import ai_consent
    from app.api.user_profile import update_my_profile
    from app.schemas.user_profile import UserProfileUpdate
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL independent transactions")
    user, _ = _headers(db)
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    sessions = sessionmaker(bind=db.get_bind())
    with sessions() as stale, sessions() as withdraw:
        old = stale.query(UserProfile).filter_by(user_id=user.id).first()
        assert old.privacy_settings[ai_consent.CONSENT_KEY]["accepted"] is True
        ai_consent.update_ai_consent(withdraw, user.id, False, ai_consent.POLICY_VERSION)
        await update_my_profile(UserProfileUpdate(privacy_settings={"weight": False}), current_user=user, db=stale)
    assert ai_consent.get_ai_consent(db, user.id)["accepted"] is False


def test_concurrent_first_grants_are_serialized_and_both_audited(db):
    from concurrent.futures import ThreadPoolExecutor
    from app.services import ai_consent
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locks")
    user, _ = _headers(db)
    uid = user.id
    db.rollback()
    sessions = sessionmaker(bind=db.get_bind())
    def grant():
        with sessions() as session:
            return ai_consent.update_ai_consent(session, uid, True, ai_consent.POLICY_VERSION)["accepted"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(grant), pool.submit(grant)]
        assert [future.result(timeout=10) for future in futures] == [True, True]
    assert db.query(UserProfile).filter_by(user_id=uid).count() == 1
    assert db.query(AgentAuditLog).filter_by(user_id=uid, agent_type="ai_consent").count() == 2


def test_sdk_transport_hook_rechecks_internal_retry(db, monkeypatch):
    import httpx
    from openai import OpenAI, APIConnectionError
    from app.services import ai_consent
    user, _ = _headers(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    sent = []
    def upstream(request):
        sent.append(request)
        ai_consent.update_ai_consent(db, user.id, False, ai_consent.POLICY_VERSION)
        return httpx.Response(500, json={"error": "retry"})
    sdk = OpenAI(api_key="test-only", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                 http_client=httpx.Client(transport=httpx.MockTransport(upstream)), max_retries=1)
    ai_consent.guard_openai_client(sdk)
    with ai_consent.ai_user_scope(user.id), pytest.raises(APIConnectionError):
        sdk.chat.completions.create(model="test", messages=[{"role": "user", "content": "private"}])
    assert len(sent) == 1
    sdk.close()


@pytest.mark.asyncio
async def test_remote_ollama_cannot_claim_local_exemption(monkeypatch):
    from app.services.llm.providers.ollama_provider import OllamaProvider
    from app.services.ai_consent import ai_user_scope
    def network(*args, **kwargs):
        pytest.fail("untrusted remote Ollama received user data")
    monkeypatch.setattr("app.services.llm.providers.ollama_provider.httpx.AsyncClient", network)
    with ai_user_scope(None), pytest.raises(HTTPException):
        await OllamaProvider(base_url="https://external.example").chat([])


def test_authenticated_http_request_binds_only_its_own_consent(db, monkeypatch):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user_required
    from app.database import get_db
    from app.services import ai_consent
    user, headers = _headers(db)
    other, other_headers = _headers(db)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: db
    @app.get("/probe")
    async def probe(_user=Depends(get_current_user_required)):
        ai_consent.require_ai_consent(destination="https://dashscope.aliyuncs.com/api/v1")
        return {"allowed": True}
    with TestClient(app) as http:
        assert http.get("/probe", headers=headers).status_code == 200
        assert http.get("/probe", headers=other_headers).status_code == 403
        assert http.get("/probe").status_code == 401
        ai_consent.update_ai_consent(db, user.id, False, ai_consent.POLICY_VERSION)
        assert http.get("/probe", headers=headers).status_code == 403


def test_legacy_undisclosed_preference_is_not_selected_or_reported_effective(db, monkeypatch):
    from app.api.user_llm_preference import get_preference
    from app.services.llm import factory, model_registry
    user, _ = _headers(db)
    db.add(UserProfile(user_id=user.id, llm_model_id="legacy-proxy"))
    db.commit()
    entry = model_registry.ModelEntry(id="legacy-proxy", label="Legacy", provider="openai-proxy", model="unknown", speed_tier="fast")
    monkeypatch.setattr(model_registry, "get_model", lambda key: entry)
    monkeypatch.setattr(model_registry, "list_models", lambda **kw: [entry])
    def unknown_entry(*args):
        pytest.fail("selected an undisclosed legacy preference")
    from types import SimpleNamespace
    safe_default = SimpleNamespace(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setattr(factory, "_create_from_entry", unknown_entry)
    monkeypatch.setattr(factory, "get_llm_provider", lambda: safe_default)
    assert factory.create_provider_for_user(user.id, db) is safe_default
    assert get_preference(current_user=user, db=db).model_id is None
