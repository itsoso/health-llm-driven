"""Route-specific request body limits enforced before FastAPI parsing."""

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse


MAX_MEDICAL_REPORT_REQUEST_BYTES = 10 * 1024 * 1024
MEDICAL_REPORT_UPLOAD_PATH = "/api/v1/family-health/medical-reports/upload"

ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[dict]], Callable[..., Awaitable[None]]], Awaitable[None]]


class RequestBodyLimitMiddleware:
    """Buffer at most the route limit before schema/base64 parsing starts."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != MEDICAL_REPORT_UPLOAD_PATH
        ):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                await JSONResponse(
                    status_code=400,
                    content={"detail": "Content-Length 无效"},
                )(scope, receive, send)
                return
            if declared_size < 0 or declared_size > MAX_MEDICAL_REPORT_REQUEST_BYTES:
                await self._reject(scope, receive, send)
                return

        buffered: list[dict[str, Any]] = []
        received_size = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message.get("type") != "http.request":
                break
            received_size += len(message.get("body", b""))
            if received_size > MAX_MEDICAL_REPORT_REQUEST_BYTES:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive():
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(scope, receive, send) -> None:
        await JSONResponse(
            status_code=413,
            content={"detail": "体检报告请求体超过 10 MB 限制"},
        )(scope, receive, send)
