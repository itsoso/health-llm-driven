"""Session-only POI proxy: no persistence, authenticated and privacy bounded."""
from datetime import datetime, timedelta, timezone
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.deps import get_current_user_required
from app.api import share_location as api
from app.services import share_location as service
from app.utils.share_location_privacy import protect_location_event, install_location_log_filters


def nearby(**changes):
    return {"latitude": 30.2, "longitude": 120.1, "accuracy_m": 20,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "consent": "amap-share-location-v1", **changes}


@pytest.fixture
def proxy(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=17)
    monkeypatch.setattr(service.settings, "amap_web_service_key", SecretStr("synthetic-test-secret"))
    redis = Mock()
    redis.eval.return_value = 1
    monkeypatch.setattr(service, "get_redis_client", lambda: redis)
    with TestClient(app) as client:
        yield client, app, redis


@pytest.mark.parametrize("change", [
    {"consent": "wrong"}, {"latitude": 91}, {"longitude": -181}, {"latitude": True},
    {"accuracy_m": None}, {"accuracy_m": 201}, {"accuracy_m": 0}, {"unexpected": "private"},
    {"captured_at": (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()},
    {"captured_at": (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()},
    {"captured_at": "2026-09-26T12:00:00"},
    {"captured_at": datetime.now(timezone.utc).timestamp()},
])
def test_nearby_invalid_never_calls_provider(proxy, monkeypatch, change):
    client, _, _ = proxy
    provider = Mock(side_effect=AssertionError("must not call"))
    monkeypatch.setattr(service, "_request", provider)
    response = client.post("/share-location/nearby", json=nearby(**change))
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "input" not in response.text and "private" not in response.text
    provider.assert_not_called()


@pytest.mark.parametrize("body", [b'{"keyword": "private', b'null', b'[]'])
def test_invalid_json_redacted(proxy, body):
    response = proxy[0].post("/share-location/search", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert "private" not in response.text


def test_auth_required(proxy, monkeypatch):
    client, app, _ = proxy
    app.dependency_overrides.clear()
    response = client.post("/share-location/nearby", json=nearby())
    assert response.status_code in (401, 403)
    assert response.headers["cache-control"] == "no-store"


def test_missing_key_and_rate_limit_fail_closed(proxy, monkeypatch):
    client, _, redis = proxy
    monkeypatch.setattr(service.settings, "amap_web_service_key", None)
    assert client.post("/share-location/nearby", json=nearby()).status_code == 503
    monkeypatch.setattr(service.settings, "amap_web_service_key", SecretStr("synthetic-test-secret"))
    redis.eval.return_value = 0
    assert client.post("/share-location/nearby", json=nearby()).status_code == 429
    redis.eval.side_effect = RuntimeError("private-redis-error")
    response = client.post("/share-location/nearby", json=nearby())
    assert response.status_code == 503 and "private" not in response.text


def test_gps_converted_before_restaurant_lookup(proxy, monkeypatch):
    calls = []
    def request(path, params):
        calls.append((path, params))
        if "convert" in path:
            return {"locations": "120.105000,30.205000"}
        return {"regeocode": {"pois": [
            {"id": "far", "name": "远店", "address": "详细地址", "type": "餐饮服务;中餐厅", "distance": "80"},
            {"id": "near", "name": "近店", "address": "另一地址", "type": "餐饮服务;中餐厅", "distance": "12.4"},
        ]}}
    monkeypatch.setattr(service, "_request", request)
    result = proxy[0].post("/share-location/nearby", json=nearby())
    assert result.status_code == 200
    assert calls[0][1]["coordsys"] == "gps"
    assert calls[1][1]["location"] == "120.105,30.205"
    assert result.json()["suggested_id"] == "near"
    assert result.json()["items"][0]["label"] == "近店"
    assert set(result.json()["items"][0]) == {"id", "name", "address", "label", "distance_m"}
    coarse = proxy[0].post("/share-location/nearby", json=nearby(accuracy_m=100))
    assert coarse.json()["suggested_id"] is None


def test_search_bounded_no_suggestion_or_identity_sent(proxy, monkeypatch):
    calls = []
    def request(path, params):
        calls.append(params)
        return {"pois": [{"id": str(i), "name": "餐厅" * 30, "address": [], "distance": []} for i in range(25)]}
    monkeypatch.setattr(service, "_request", request)
    response = proxy[0].post("/share-location/search", json={"keyword": "饭店", "consent": "amap-share-location-v1"})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 10
    assert len(response.json()["items"][0]["label"]) <= 40
    assert response.json()["suggested_id"] is None
    assert "user" not in json.dumps(calls)


@pytest.mark.parametrize("keyword", ["", " " * 3, "x" * 81, "private\naddress"])
def test_invalid_search(proxy, keyword):
    response = proxy[0].post("/share-location/search", json={"keyword": keyword, "consent": "amap-share-location-v1"})
    assert response.status_code == 422 and "private" not in response.text


def test_sanitized_provider_failure(proxy, monkeypatch, caplog):
    monkeypatch.setattr(service, "_request", Mock(side_effect=httpx.ConnectError("secret-key 120.1 private-address")))
    with caplog.at_level(logging.INFO):
        response = proxy[0].post("/share-location/nearby", json=nearby())
    assert response.status_code == 503
    for private in ("secret-key", "120.1", "private-address"):
        assert private not in response.text and private not in caplog.text


def test_location_telemetry_dropped_but_unrelated_preserved():
    assert protect_location_event({"request": {"url": "https://host/api/v1/share-location/nearby", "data": "private"}}, {}) is None
    assert protect_location_event({"spans": [{"description": "GET https://restapi.amap.com/v3?key=secret"}]}, {}) is None
    event = {"message": "unrelated"}
    assert protect_location_event(event, {}) == event


def test_sensitive_http_logs_suppressed(caplog):
    install_location_log_filters()
    with service.private_provider_io(), caplog.at_level(logging.DEBUG):
        logging.getLogger("httpx").info("https://restapi.amap.com/v3?key=secret")
        logging.getLogger("httpcore.http11").debug("headers secret")
    assert "secret" not in caplog.text


def test_provider_transport_fixed_https_no_redirect_or_trace(proxy, monkeypatch, caplog):
    real_client = httpx.Client
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "1", "pois": []})
    def client(**kwargs):
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        return real_client(**kwargs, transport=httpx.MockTransport(handler), headers={"sentry-trace": "private-trace", "baggage": "private-account"})
    monkeypatch.setattr(service.httpx, "Client", client)
    with caplog.at_level(logging.DEBUG):
        data = service._request("/v3/place/text", {"keywords": "private-address"})
    assert data["pois"] == []
    assert seen[0].url.scheme == "https" and seen[0].url.host == "restapi.amap.com"
    assert "baggage" not in seen[0].headers and "sentry-trace" not in seen[0].headers
    assert "private-address" not in caplog.text and "synthetic-test-secret" not in caplog.text
    with pytest.raises(RuntimeError):
        service._request("https://untrusted.example", {})


@pytest.mark.parametrize("status,content", [
    (302, b""), (500, b"private"), (200, b'{"status":"0","info":"private"}'),
    (200, b'invalid-private-json'), (200, b'x' * 262145), (200, b'[]'),
], ids=["redirect", "upstream-error", "provider-rejected", "invalid-json", "oversized", "wrong-shape"])
def test_transport_errors_fail_closed(proxy, monkeypatch, status, content):
    real_client = httpx.Client
    monkeypatch.setattr(service.httpx, "Client", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(status, content=content))))
    response = proxy[0].post("/share-location/search", json={"keyword": "private", "consent": "amap-share-location-v1"})
    assert response.status_code == 503 and "private" not in response.text


def test_candidate_distance_and_type_do_not_overclaim(proxy, monkeypatch):
    def request(path, params):
        if "convert" in path:
            return {"locations": "120.1,30.2"}
        return {"regeocode": {"pois": [
            {"id": "1", "name": "住宅", "type": "商务住宅", "distance": "1"},
            {"id": "2", "name": "餐厅", "type": "餐饮服务", "distance": "100.004"},
            {"id": "3", "name": "未知", "type": "餐饮服务", "distance": "NaN"},
        ]}}
    monkeypatch.setattr(service, "_request", request)
    response = proxy[0].post("/share-location/nearby", json=nearby())
    assert response.json()["suggested_id"] is None
    assert response.json()["items"][-1]["distance_m"] is None


def test_rate_limits_are_user_scoped(proxy):
    _, _, redis = proxy
    service.admit(17)
    first = redis.eval.call_args.args
    service.admit(18)
    second = redis.eval.call_args.args
    assert first[2:] != second[2:]
    assert ":17" not in str(first) and ":18" not in str(second)


def test_main_router_registers_proxy():
    from main import app
    paths = app.openapi()["paths"]
    assert "/api/v1/share-location/nearby" in paths and "/api/v1/share-location/search" in paths


def test_authenticated_application_route_without_record_write(client, db, monkeypatch):
    from tests.conftest import create_authenticated_user
    from app.models.daily_health import DietRecord
    user, token = create_authenticated_user(db)
    monkeypatch.setattr(service.settings, "amap_web_service_key", SecretStr("synthetic-test-secret"))
    redis = Mock()
    redis.eval.return_value = 1
    monkeypatch.setattr(service, "get_redis_client", lambda: redis)
    monkeypatch.setattr(service, "_request", lambda path, params: {"pois": []})
    before = db.query(DietRecord).filter_by(user_id=user.id).count()
    response = client.post("/api/v1/share-location/search", json={"keyword": "餐厅", "consent": "amap-share-location-v1"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200 and response.json() == {"items": [], "suggested_id": None}
    assert response.headers["cache-control"] == "no-store"
    assert db.query(DietRecord).filter_by(user_id=user.id).count() == before


def test_sentry_capture_does_not_export_location_request():
    import sentry_sdk
    from sentry_sdk.transport import Transport
    envelopes = []
    class MemoryTransport(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)
    # Temporary initialized SDK uses only a memory transport; no external calls.
    with sentry_sdk.init(dsn="https://public@example.invalid/1", transport=MemoryTransport,
                         default_integrations=False, before_send=protect_location_event,
                         before_send_transaction=protect_location_event):
        sentry_sdk.capture_event({"message": "private-address", "request": {"url": "https://local/api/v1/share-location/search", "data": {"keyword": "private"}}})
        assert envelopes == []
        sentry_sdk.capture_message("unrelated-status")
        assert len(envelopes) == 1


def test_slow_stream_has_total_deadline(proxy, monkeypatch):
    real_client = httpx.Client
    clock = [100.0]
    chunks_seen = []
    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(100):
                clock[0] += 2.0
                chunks_seen.append(1)
                yield b" "
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(service.httpx, "Client", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowStream()))))
    with pytest.raises(RuntimeError):
        with service.audited_lookup(17, "search"):
            service._request("/v3/place/text", {"keywords": "private"})
    assert len(chunks_seen) == 6  # stopped at total10s, not100read-timeouts


def test_expired_total_budget_does_not_open_second_request(proxy, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    provider = Mock(side_effect=AssertionError("no new provider request"))
    monkeypatch.setattr(service.httpx, "Client", provider)
    with pytest.raises(TimeoutError):
        with service.audited_lookup(17, "nearby"):
            clock[0] = 111.0
            service._request("/v3/geocode/regeo", {})
    provider.assert_not_called()


def test_sentry_httpx_spans_and_propagation_are_private(proxy, monkeypatch):
    import sentry_sdk
    from sentry_sdk.integrations.httpx import HttpxIntegration
    from sentry_sdk.transport import Transport
    envelopes, sent_headers = [], []
    class MemoryTransport(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)
    real_client = httpx.Client
    def handler(request):
        sent_headers.append(dict(request.headers))
        return httpx.Response(200, json={"status": "1", "pois": []})
    monkeypatch.setattr(service.httpx, "Client", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)))
    with sentry_sdk.init(dsn="https://public@example.invalid/1", transport=MemoryTransport,
                         traces_sample_rate=1.0, default_integrations=False, integrations=[HttpxIntegration()],
                         before_send=protect_location_event, before_send_transaction=protect_location_event):
        with sentry_sdk.start_transaction(name="upstream-lookup-test"):
            service._request("/v3/place/text", {"keywords": "private-address"})
    assert envelopes == []
    assert sent_headers and "sentry-trace" not in sent_headers[0] and "baggage" not in sent_headers[0]
