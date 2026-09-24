"""Decision transport contracts and safety boundaries (no external network)."""

import json

import httpx
import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.decisions import (
    DecisionError,
    DecisionRequest,
    SystemOneProvider,
    provider_from_settings,
)
from app.services.decisions.config import configured_decision


@pytest.fixture
def decision_config(monkeypatch):
    for name, value in {
        "decision_mode": "on",
        "decision_provider": "laya",
        "decision_base_url": None,
        "decision_model": None,
        "decision_api_key": None,
        "decision_recipient_name": None,
    }.items():
        monkeypatch.setattr(settings, name, value)


def request():
    return DecisionRequest(
        state="test",
        questions={
            "route": {
                "type": "choice",
                "instructions": "Choose",
                "criteria": {"a": "A", "b": "B"},
            },
            "needed": {"type": "noul", "instructions": "Needed?"},
            "depth": {
                "type": "score",
                "instructions": "Depth?",
                "criteria": ["Low", "High"],
            },
        },
    )


def response():
    return {
        "model": "multilingual",
        "answers": {
            "route": {
                "type": "choice",
                "choice": "a",
                "probabilities": {"a": 0.9, "b": 0.1},
                "confidence": 0.5,
            },
            "needed": {"type": "noul", "noul": 0.8},
            "depth": {
                "type": "score",
                "score": 0.7,
                "probabilities": {"0": 0.3, "1": 0.7},
                "legend": {"0": "Low", "1": "High"},
                "confidence": 0.2,
            },
        },
        "usage": {"input_tokens": 25, "output_tokens": 0},
    }


@pytest.mark.asyncio
async def test_local_protocol_all_primitives_and_pii_scrub(decision_config):
    seen = []

    def handle(req):
        seen.append(req)
        return httpx.Response(200, json=response())

    provider = SystemOneProvider(
        configured_decision(), transport=httpx.MockTransport(handle)
    )
    payload = request().model_copy(update={"state": "call 13800138000"})
    result = await provider.evaluate(payload, user_id=1)
    assert result.answers["route"]["choice"] == "a"
    assert result.input_tokens == 25
    assert str(seen[0].url) == "http://127.0.0.1:8092/v1/systemone"
    assert json.loads(seen[0].content)["model"] == "multilingual"
    assert b"13800138000" not in seen[0].content
    assert b"[PHONE]" in seen[0].content


@pytest.mark.asyncio
async def test_local_decision_does_not_initialize_remote_consent(
    decision_config, monkeypatch
):
    import builtins

    original_import = builtins.__import__

    def require_local_dependencies(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app.services" and "ai_consent" in fromlist:
            pytest.fail("Local inference must not initialize remote consent and its DB dependencies")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", require_local_dependencies)
    provider = SystemOneProvider(
        configured_decision(),
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response())),
    )
    result = await provider.evaluate(request(), user_id=1)
    assert result.answers["route"]["choice"] == "a"


@pytest.mark.parametrize(
    ("provider", "base", "model"),
    [
        ("jev", "https://api.typesafe.ai/v1/systemone", "jev-1.13.0"),
        ("laya", "http://127.0.0.1:8092/v1/systemone", "multilingual"),
        ("systemone", "https://decisions.example/v1/systemone", "custom-model"),
    ],
)
def test_configurable_provider_profiles(
    decision_config, monkeypatch, provider, base, model
):
    monkeypatch.setattr(settings, "decision_provider", provider)
    if provider == "systemone":
        monkeypatch.setattr(settings, "decision_base_url", base)
        monkeypatch.setattr(settings, "decision_model", model)
        monkeypatch.setattr(settings, "decision_recipient_name", "Example decisions")
    cfg = configured_decision()
    assert cfg.endpoint == base
    assert cfg.model == model
    assert isinstance(provider_from_settings(), SystemOneProvider)


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1/v1",
        "https://u:p@host/v1",
        "https://host/v1?key=x",
        "https://host/v1#fragment",
        "file:///tmp/llm",
        "http://127.0.0.1.evil/v1",
    ],
)
def test_unsafe_endpoint_rejected(decision_config, monkeypatch, url):
    monkeypatch.setattr(settings, "decision_base_url", url)
    with pytest.raises(DecisionError, match="configuration"):
        configured_decision()


@pytest.mark.asyncio
async def test_remote_consent_denial_precedes_network(decision_config, monkeypatch):
    from app.services import ai_consent

    monkeypatch.setattr(settings, "decision_provider", "jev")
    monkeypatch.setattr(settings, "decision_api_key", "test-only")
    calls = []

    def deny(*args, **kwargs):
        calls.append(kwargs["destination"])
        raise HTTPException(403, detail={"code": "ai_consent_required"})

    monkeypatch.setattr(ai_consent, "require_ai_consent", deny)
    transport = httpx.MockTransport(lambda req: pytest.fail("unauthorized network"))
    with pytest.raises(HTTPException):
        await SystemOneProvider(configured_decision(), transport=transport).evaluate(
            request(), user_id=1
        )
    assert calls == ["https://api.typesafe.ai/v1/systemone"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 401, 429, 500, 529])
async def test_failure_does_not_redirect_retry_or_switch_provider(
    decision_config, status
):
    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(
            status,
            headers={"location": "https://other.example"},
            text="private-response",
        )

    with pytest.raises(DecisionError) as error:
        await SystemOneProvider(
            configured_decision(), transport=httpx.MockTransport(handle)
        ).evaluate(request(), user_id=1)
    assert len(calls) == 1
    assert "private-response" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    ["choice", "probability", "missing", "score", "usage", "model", "huge_integer"],
)
async def test_malformed_answers_fail_closed(decision_config, bad):
    data = response()
    if bad == "choice":
        data["answers"]["route"]["choice"] = "health_record"
    if bad == "probability":
        data["answers"]["route"]["probabilities"]["a"] = float("nan")
    if bad == "missing":
        del data["answers"]["needed"]
    if bad == "score":
        data["answers"]["depth"]["score"] = 100
    if bad == "usage":
        data["usage"]["input_tokens"] = -1
    if bad == "model":
        data["model"] = "private\nhealth data"
    if bad == "huge_integer":
        data["answers"]["needed"]["noul"] = 10**400

    def handle(req):
        return httpx.Response(200, content=json.dumps(data))

    with pytest.raises(DecisionError, match="invalid_response"):
        await SystemOneProvider(
            configured_decision(), transport=httpx.MockTransport(handle)
        ).evaluate(request(), user_id=1)


@pytest.mark.asyncio
async def test_oversized_input_is_rejected_not_truncated(decision_config):
    payload = request().model_copy(update={"state": "很长的健康上下文" * 500})
    transport = httpx.MockTransport(lambda req: pytest.fail("oversized input sent"))
    with pytest.raises(DecisionError, match="input_too_large"):
        await SystemOneProvider(configured_decision(), transport=transport).evaluate(
            payload, user_id=1
        )


@pytest.mark.asyncio
async def test_local_missing_identity_denied(decision_config):
    transport = httpx.MockTransport(lambda req: pytest.fail("unbound request sent"))
    with pytest.raises(DecisionError, match="identity_required"):
        await SystemOneProvider(configured_decision(), transport=transport).evaluate(
            request(), user_id=None
        )


@pytest.mark.asyncio
async def test_timeout_is_safe_and_no_retry(decision_config):
    def handle(req):
        raise httpx.ReadTimeout("private request", request=req)

    with pytest.raises(DecisionError, match="^timeout$"):
        await SystemOneProvider(
            configured_decision(), transport=httpx.MockTransport(handle)
        ).evaluate(request(), user_id=1)


@pytest.mark.asyncio
async def test_deeply_nested_json_response_falls_back_without_breaking_route(decision_config, monkeypatch):
    from app.services.decisions import routing
    malformed = b"[" * 10000 + b"0" + b"]" * 10000
    provider = SystemOneProvider(configured_decision(), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=malformed)
    ))
    monkeypatch.setattr(routing, "provider_from_settings", lambda: provider)
    result = await routing.decide_route("synthetic", user_id=1, baseline_tier="balanced")
    assert result.status == "fallback"
    assert result.reason == "invalid_response"
    assert result.effective_tier == "balanced" and result.prompt_hint() == ""


@pytest.mark.asyncio
async def test_remote_grant_and_revocation_checked_each_send(
    decision_config, db, monkeypatch
):
    from sqlalchemy.orm import sessionmaker
    from app.services import ai_consent
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(settings, "decision_provider", "jev")
    monkeypatch.setattr(settings, "decision_api_key", "test-only")
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    state = ai_consent.get_ai_consent(db, user.id)
    ai_consent.update_ai_consent(db, user.id, True, state["policy_version"])
    sent = []

    def handle(req):
        sent.append(req)
        assert req.headers["authorization"] == "Bearer test-only"
        return httpx.Response(200, json=response())

    provider = SystemOneProvider(
        configured_decision(), transport=httpx.MockTransport(handle)
    )
    await provider.evaluate(request(), user_id=user.id)
    ai_consent.update_ai_consent(db, user.id, False, state["policy_version"])
    with pytest.raises(HTTPException):
        await provider.evaluate(request(), user_id=user.id)
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_real_loopback_http_transport(decision_config, monkeypatch):
    """Real socket verifies serialization/hooks; server is a protocol fixture."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response()).encode())

        def log_message(self, *args):
            return  # fixture never logs request payloads

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        settings, "decision_base_url", f"http://127.0.0.1:{server.server_port}/v1"
    )
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    try:
        result = await provider_from_settings().evaluate(request(), user_id=1)
        assert result.input_tokens == 25
        assert captured[0]["questions"]["needed"]["type"] == "noul"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
