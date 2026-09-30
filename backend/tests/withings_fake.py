"""In-process fake of the Withings HTTP API for tests.

Patch it in with `route_adapter_http_to(monkeypatch, FakeWithings(...))`. It replaces the
aiohttp session inside the Withings adapter module, so every adapter request (data calls
and token refresh alike) stays in the process; nothing can reach Withings.

Fake at this layer rather than replacing `WithingsHealthAdapter`: routes build the adapter
through `withings_token_store.build_withings_adapter`, so a patched class in a route module
is silently bypassed and the real adapter goes to the network.
"""
import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import aiohttp

from app.services.device_adapters import withings as withings_adapter

# One heart-pulse group, as a blood-pressure monitor reports it.
PULSE_ONLY_GROUPS = [
    {"date": 1700000000, "category": 1, "measures": [{"type": 11, "value": 62, "unit": 0}]},
]


class FakeWithings:
    """In-process Withings API: rejects the stored access token and rotates both tokens on refresh.

    fail_after_refresh: None (retries succeed), "status" (retries get a non-zero status) or
    "network" (retries raise a connection error).
    """

    def __init__(self, refresh_token, fail_after_refresh=None, measure_groups=None):
        self.access_token = None
        self.refresh_token = refresh_token
        self.fail_after_refresh = fail_after_refresh
        self.measure_groups = PULSE_ONLY_GROUPS if measure_groups is None else measure_groups
        self.requests = []

    @property
    def refresh_count(self):
        return sum(1 for url, _, _ in self.requests if url == withings_adapter.WITHINGS_TOKEN_URL)

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
            return {"status": 0, "body": {"measuregrps": self.measure_groups}}
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


def route_adapter_http_to(monkeypatch, withings):
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
