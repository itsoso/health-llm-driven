"""Withings: tokens refreshed during a request must be saved the moment Withings rotates them.

`_api_request` refreshes an expired access token, and Withings can rotate the refresh
token at the same time, which kills the old one. If the new pair is only saved at the end
of a route, a retried request that then fails loses it: the credential keeps a dead refresh
token and the weight / blood pressure / sleep webhooks stop syncing once the next access
token expires. The webhook handler is the unattended path, so there nobody sees the error.
"""
import asyncio
import logging
from datetime import date, timedelta
from types import SimpleNamespace

import aiohttp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.daily_health import GarminData
from app.models.device_credential import DeviceCredential
from app.services.device_adapters import withings as withings_adapter
from app.services.device_adapters.withings import WithingsHealthAdapter
from main import app

LIST_URL = "/api/v1/devices/withings/webhooks/list"
WITHINGS_USERID = "9001"


class _FakeWithings:
    """In-process Withings API: rejects the stored access token and rotates both tokens on refresh.

    fail_after_refresh: None (retries succeed), "status" (retries get a non-zero status) or
    "network" (retries raise a connection error).
    """

    def __init__(self, refresh_token, fail_after_refresh=None):
        self.access_token = None
        self.refresh_token = refresh_token
        self.fail_after_refresh = fail_after_refresh
        self.requests = []

    def handle(self, url, data, headers):
        self.requests.append((url, data.get("action"), data.get("grant_type")))
        if url == withings_adapter.WITHINGS_TOKEN_URL:
            if data.get("refresh_token") != self.refresh_token:
                return {"status": 503, "error": "invalid refresh_token"}
            self.access_token, self.refresh_token = "rotated-access", "rotated-refresh"
            return {"status": 0, "body": {
                "access_token": self.access_token, "refresh_token": self.refresh_token, "expires_in": 10800,
            }}
        if self.access_token is None or headers.get("Authorization") != f"Bearer {self.access_token}":
            return {"status": 401, "error": "invalid_token"}
        if self.fail_after_refresh == "network":
            raise aiohttp.ClientConnectionError("connection reset")
        if self.fail_after_refresh == "status":
            return {"status": 2554, "error": "unavailable"}
        action = data.get("action")
        if action == "getmeas":
            return {"status": 0, "body": {"measuregrps": [
                {"date": 1700000000, "category": 1, "measures": [{"type": 11, "value": 62, "unit": 0}]},
            ]}}
        if action == "getsummary":
            # The query spans two days, so Withings returns the night that ends on each of them.
            woke = date.fromisoformat(data["startdateymd"])
            return {"status": 0, "body": {"series": [
                {"date": woke.isoformat(), "data": {
                    "total_sleep_time": 25200, "deepsleepduration": 5400, "remsleepduration": 6000,
                    "lightsleepduration": 13800, "wakeupduration": 1200, "wakeupcount": 3, "sleep_score": 81,
                    "hr_average": 52, "rr_average": 14,
                }},
                {"date": (woke + timedelta(days=1)).isoformat(), "data": {
                    "total_sleep_time": 18000, "wakeupduration": 3600, "sleep_score": 60,
                }},
            ]}}
        return {"status": 0, "body": {"profiles": [{"appli": 1, "callbackurl": "https://example.test/webhook"}]}}


def _route_adapter_http_to(monkeypatch, withings):
    """Replace the adapter's aiohttp session so no request leaves the process."""

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def json(self):
            await asyncio.sleep(0)  # yield like real I/O so concurrent requests interleave
            return self._payload

    class _Session:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        def post(self, url, data=None, headers=None):
            return _Response(withings.handle(url, data or {}, headers or {}))

    monkeypatch.setattr(
        withings_adapter, "aiohttp",
        SimpleNamespace(ClientSession=_Session, ClientTimeout=aiohttp.ClientTimeout),
    )


def _add_credential(db, user):
    credential = DeviceCredential(
        user_id=user.id, device_type="withings", auth_type="oauth2", is_valid=True, sync_enabled=True,
    )
    credential.set_oauth_tokens(access_token="expired-access", refresh_token="original-refresh")
    credential.set_config({"withings_userid": WITHINGS_USERID})
    db.add(credential)
    db.commit()
    return credential.id


def _assert_rotated_pair_saved(db, credential_id):
    db.rollback()  # discard anything the route changed without committing
    saved = db.get(DeviceCredential, credential_id)
    db.refresh(saved)
    assert saved.get_access_token() == "rotated-access"
    assert saved.get_refresh_token() == "rotated-refresh"
    assert saved.token_expires_at is not None


def test_withings_webhooks_list_with_expired_token_saves_rotated_tokens(
    client, db, auth_user_and_headers, monkeypatch
):
    user, headers = auth_user_and_headers
    credential_id = _add_credential(db, user)
    withings = _FakeWithings(refresh_token="original-refresh")
    _route_adapter_http_to(monkeypatch, withings)

    response = client.get(LIST_URL, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["body"]["profiles"][0]["appli"] == 1
    assert withings.requests == [
        (withings_adapter.WITHINGS_NOTIFY_URL, "list", None),
        (withings_adapter.WITHINGS_TOKEN_URL, "requesttoken", "refresh_token"),
        (withings_adapter.WITHINGS_NOTIFY_URL, "list", None),
    ]
    _assert_rotated_pair_saved(db, credential_id)


@pytest.mark.parametrize("failure", ["status", "network"])
def test_withings_webhooks_list_saves_rotated_tokens_when_retry_fails(
    client, db, auth_user_and_headers, monkeypatch, failure
):
    user, headers = auth_user_and_headers
    credential_id = _add_credential(db, user)
    _route_adapter_http_to(monkeypatch, _FakeWithings("original-refresh", fail_after_refresh=failure))

    response = TestClient(app, raise_server_exceptions=False).get(LIST_URL, headers=headers)

    assert response.status_code == 500
    _assert_rotated_pair_saved(db, credential_id)


@pytest.mark.parametrize("failure", ["status", "network"])
def test_withings_sync_saves_rotated_tokens_when_retry_fails(
    client, db, auth_user_and_headers, monkeypatch, failure
):
    user, headers = auth_user_and_headers
    credential_id = _add_credential(db, user)
    _route_adapter_http_to(monkeypatch, _FakeWithings("original-refresh", fail_after_refresh=failure))

    response = client.post("/api/v1/devices/withings/sync?days=1", headers=headers)

    assert response.status_code == 500
    _assert_rotated_pair_saved(db, credential_id)


def test_withings_subscribe_saves_rotated_tokens_when_retry_fails(
    client, db, auth_user_and_headers, monkeypatch
):
    user, headers = auth_user_and_headers
    credential_id = _add_credential(db, user)
    _route_adapter_http_to(monkeypatch, _FakeWithings("original-refresh", fail_after_refresh="status"))

    response = client.post("/api/v1/devices/withings/webhooks/subscribe", headers=headers)

    assert response.status_code == 200, response.text
    assert not any(r["success"] for r in response.json()["results"])
    _assert_rotated_pair_saved(db, credential_id)


@pytest.mark.parametrize("appli", ["1", "4", "44"])
@pytest.mark.parametrize("failure", ["status", "network"])
def test_withings_webhook_saves_rotated_tokens_when_retry_fails(
    client, db, auth_user_and_headers, monkeypatch, failure, appli
):
    """Unattended path: Withings posts, nobody sees the error, the binding must survive."""
    user, _ = auth_user_and_headers
    credential_id = _add_credential(db, user)
    _route_adapter_http_to(monkeypatch, _FakeWithings("original-refresh", fail_after_refresh=failure))

    response = client.post(
        "/api/v1/devices/withings/webhook",
        data={"userid": WITHINGS_USERID, "appli": appli, "startdate": "1700000000", "enddate": "1700003600"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "error"
    _assert_rotated_pair_saved(db, credential_id)


def test_withings_token_persist_log_names_user_without_token_values(
    client, db, auth_user_and_headers, monkeypatch, caplog
):
    user, headers = auth_user_and_headers
    _add_credential(db, user)
    _route_adapter_http_to(monkeypatch, _FakeWithings("original-refresh"))

    with caplog.at_level(logging.INFO):
        assert client.get(LIST_URL, headers=headers).status_code == 200

    persisted = [r.getMessage() for r in caplog.records if "persisted" in r.getMessage()]
    assert persisted and f"user_id={user.id}" in persisted[0]
    for secret in ("expired-access", "original-refresh", "rotated-access", "rotated-refresh"):
        assert secret not in caplog.text


def test_concurrent_requests_on_one_credential_refresh_once(db, auth_user_and_headers, monkeypatch):
    """Two webhooks for one measurement arrive together: the second must reuse the first
    refresh instead of spending the refresh token Withings has just rotated away.

    Each request has its own session, as in production, so the second one only sees the
    new pair through the database."""
    from app.services.device_adapters.withings_token_store import build_withings_adapter

    user, _ = auth_user_and_headers
    credential_id = _add_credential(db, user)
    withings = _FakeWithings("original-refresh")
    _route_adapter_http_to(monkeypatch, withings)
    other_db = Session(bind=db.get_bind())

    async def both():
        first = build_withings_adapter(db, db.get(DeviceCredential, credential_id))
        second = build_withings_adapter(other_db, other_db.get(DeviceCredential, credential_id))
        return await asyncio.gather(first.list_webhooks(), second.list_webhooks())

    try:
        results = asyncio.run(both())
    finally:
        other_db.close()

    assert all(r["status"] == 0 for r in results)
    refreshes = [r for r in withings.requests if r[0] == withings_adapter.WITHINGS_TOKEN_URL]
    assert len(refreshes) == 1
    _assert_rotated_pair_saved(db, credential_id)


def _sync_all(client, headers):
    response = client.post("/api/v1/devices/sync-all", json={"days": 1}, headers=headers)
    assert response.status_code == 200, response.text
    return next(r for r in response.json()["results"] if r["device"] == "withings")


def test_sync_all_withings_saves_daily_data_and_rotated_tokens(client, db, auth_user_and_headers, monkeypatch):
    user, headers = auth_user_and_headers
    credential_id = _add_credential(db, user)
    _route_adapter_http_to(monkeypatch, _FakeWithings("original-refresh"))

    result = _sync_all(client, headers)

    assert result["success"] is True, result
    assert (result["synced_days"], result["failed_days"]) == (1, 0)
    row = db.query(GarminData).filter(GarminData.user_id == user.id).one()
    assert row.data_source == "withings"
    assert row.record_date == date.today()
    # the night that ended on the synced day, not the following one
    assert (row.total_sleep_duration, row.awake_duration, row.sleep_score) == (420, 20, 81)
    # a blood-pressure cuff pulse is not a resting heart rate; sleep averages are not daily ones
    assert row.resting_heart_rate is None
    assert row.avg_heart_rate is None
    assert row.avg_respiration_awake is None
    _assert_rotated_pair_saved(db, credential_id)


def test_sync_all_withings_all_fetches_failing_is_not_success(client, db, auth_user_and_headers, monkeypatch):
    user, headers = auth_user_and_headers
    credential_id = _add_credential(db, user)
    _route_adapter_http_to(monkeypatch, _FakeWithings("original-refresh", fail_after_refresh="network"))

    result = _sync_all(client, headers)

    assert result["success"] is False, result
    assert (result["synced_days"], result["failed_days"]) == (0, 1)
    assert db.query(GarminData).filter(GarminData.user_id == user.id).count() == 0
    _assert_rotated_pair_saved(db, credential_id)
    saved = db.get(DeviceCredential, credential_id)
    assert saved.is_valid is True  # a failed sync must not unbind the webhooks
    assert saved.last_sync_at is None
    assert saved.last_error


def test_withings_sleep_summary_without_duration_fields_writes_no_zero_minutes():
    """A summary missing a field must leave it unknown, not report 0 minutes of sleep."""
    adapter = WithingsHealthAdapter(client_id="id", client_secret="secret")
    normalized = withings_adapter.NormalizedHealthData(record_date=date(2026, 9, 1), source="withings")

    found = adapter._parse_sleep_to_normalized(
        {"series": [{"date": "2026-09-01", "data": {"sleep_score": 70}}]}, normalized, date(2026, 9, 1),
    )

    assert found is True
    assert normalized.sleep_score == 70
    assert normalized.total_sleep_minutes is None
    assert normalized.deep_sleep_minutes is None
    assert normalized.awake_minutes is None


def test_withings_sleep_summary_without_the_requested_night_writes_nothing():
    adapter = WithingsHealthAdapter(client_id="id", client_secret="secret")
    normalized = withings_adapter.NormalizedHealthData(record_date=date(2026, 9, 1), source="withings")

    found = adapter._parse_sleep_to_normalized(
        {"series": [{"date": "2026-09-02", "data": {"total_sleep_time": 25200}}]}, normalized, date(2026, 9, 1),
    )

    assert found is False
    assert normalized.total_sleep_minutes is None


def test_webhook_token_commit_failure_is_logged_without_details(
    client, db, auth_user_and_headers, monkeypatch, caplog
):
    """If saving the rotated pair fails the webhook reports an error without echoing
    database or token details to the unauthenticated caller."""
    user, _ = auth_user_and_headers
    _add_credential(db, user)
    _route_adapter_http_to(monkeypatch, _FakeWithings("original-refresh"))

    def _fail(self, **kwargs):
        raise RuntimeError("rotated-access could not be written")

    monkeypatch.setattr(DeviceCredential, "set_oauth_tokens", _fail)

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/devices/withings/webhook",
            data={"userid": WITHINGS_USERID, "appli": "1", "startdate": "1700000000", "enddate": "1700003600"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "error", "message": "RuntimeError"}
    not_persisted = [r.getMessage() for r in caplog.records if "NOT persisted" in r.getMessage()]
    assert not_persisted and f"user_id={user.id}" in not_persisted[0]
    assert "rotated-access" not in caplog.text
