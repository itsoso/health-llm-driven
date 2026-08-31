"""Content-free HTTP access logging.

Only route templates and bounded operational fields may cross this telemetry
boundary. Raw request targets can contain health data, private filenames, and
signed capabilities, so they must never be used as a fallback.
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send


logger = logging.getLogger("app.http_access")


def safe_route_template(scope: Scope) -> str:
    """Return the resolved static route template or a content-free fallback."""

    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path.startswith("/"):
        return path
    return "<unmatched>"


class SafeAccessLogMiddleware:
    """Log HTTP method, route template, status, and duration only."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            duration_ms = max(0.0, (time.perf_counter() - started_at) * 1000)
            method = scope.get("method")
            safe_method = method if isinstance(method, str) else "UNKNOWN"
            logger.info(
                "http_access method=%s route=%s status=%d duration_ms=%.2f",
                safe_method,
                safe_route_template(scope),
                status_code,
                duration_ms,
            )
