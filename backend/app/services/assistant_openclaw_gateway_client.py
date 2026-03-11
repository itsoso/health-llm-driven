"""智能助理专用 OpenClaw Gateway 客户端"""
import asyncio
import json
import uuid
from collections import deque
from typing import Any, AsyncGenerator, Deque, Optional

import httpx
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed


class AssistantOpenClawGatewayError(Exception):
    """Gateway 调用异常"""


class AssistantOpenClawGatewayAuthError(AssistantOpenClawGatewayError):
    """Gateway 鉴权异常"""


class AssistantOpenClawGatewayClient:
    """通过 OpenClaw Gateway WebSocket RPC 调用 chat.* 能力"""

    def __init__(self, gateway_url: str, gateway_token: str):
        self.gateway_url = gateway_url.rstrip("/")
        self.gateway_token = gateway_token.strip()
        self.ws_url = self.gateway_url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        self._ws = None
        self._event_queue: Deque[dict[str, Any]] = deque()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def check_health(self) -> tuple[int, Any]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            response = await client.get(f"{self.gateway_url}/health")
            try:
                payload = response.json()
            except Exception:
                payload = response.text
            return response.status_code, payload

    async def connect(self) -> dict[str, Any]:
        self._ws = await ws_connect(
            self.ws_url,
            open_timeout=5,
            close_timeout=3,
            max_size=4 * 1024 * 1024,
        )

        await self._await_connect_challenge()
        hello = await self.request(
            "connect",
            {
                "minProtocol": 3,
                "maxProtocol": 3,
                "client": {
                    "id": "gateway-client",
                    "version": "assistant-openclaw",
                    "platform": "python",
                    "mode": "backend",
                    "instanceId": uuid.uuid4().hex[:12],
                },
                "role": "operator",
                "scopes": [
                    "operator.admin",
                    "operator.approvals",
                    "operator.pairing",
                ],
                "caps": ["tool-events"],
                "auth": {"token": self.gateway_token},
                "userAgent": "health-platform-backend",
                "locale": "zh-CN",
            },
            timeout=10,
        )
        return hello

    async def close(self):
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._event_queue.clear()

    async def request(
        self,
        method: str,
        params: Optional[dict[str, Any]] = None,
        *,
        timeout: float = 10,
    ) -> Any:
        if self._ws is None:
            raise AssistantOpenClawGatewayError("gateway not connected")

        req_id = uuid.uuid4().hex
        await self._ws.send(
            json.dumps(
                {
                    "type": "req",
                    "id": req_id,
                    "method": method,
                    "params": params or {},
                },
                ensure_ascii=False,
            )
        )

        while True:
            message = await self._recv_json(timeout=timeout)
            if not isinstance(message, dict):
                continue

            msg_type = message.get("type")
            if msg_type == "event":
                self._event_queue.append(message)
                continue

            if msg_type != "res" or message.get("id") != req_id:
                continue

            if message.get("ok"):
                return message.get("payload")

            error = message.get("error") or {}
            error_code = str(error.get("code") or "")
            error_message = str(error.get("message") or "request failed")
            if "AUTH" in error_code.upper() or "UNAUTHORIZED" in error_code.upper():
                raise AssistantOpenClawGatewayAuthError(error_message)
            raise AssistantOpenClawGatewayError(error_message)

    async def send_chat(
        self,
        *,
        session_key: str,
        message: str,
        idempotency_key: str,
    ):
        await self.request(
            "chat.send",
            {
                "sessionKey": session_key,
                "message": message,
                "deliver": False,
                "idempotencyKey": idempotency_key,
            },
            timeout=15,
        )

    async def stream_chat(
        self,
        *,
        session_key: str,
        run_id: str,
        timeout: float = 120,
    ) -> AsyncGenerator[dict[str, Any], None]:
        while True:
            event = await self.next_event(timeout=timeout)
            if event.get("event") != "chat":
                continue

            payload = event.get("payload") or {}

            event_run_id = payload.get("runId")
            if event_run_id:
                if event_run_id != run_id:
                    continue
            elif not self._session_matches(session_key, payload.get("sessionKey")):
                continue

            state = payload.get("state")
            yield payload
            if state in {"final", "error", "aborted"}:
                break

    async def next_event(self, timeout: float = 120) -> dict[str, Any]:
        if self._event_queue:
            return self._event_queue.popleft()

        while True:
            message = await self._recv_json(timeout=timeout)
            if isinstance(message, dict) and message.get("type") == "event":
                return message

    async def _await_connect_challenge(self) -> Optional[str]:
        try:
            message = await self._recv_json(timeout=0.75)
        except asyncio.TimeoutError:
            return None

        if (
            isinstance(message, dict)
            and message.get("type") == "event"
            and message.get("event") == "connect.challenge"
        ):
            payload = message.get("payload") or {}
            nonce = payload.get("nonce")
            return str(nonce) if nonce else None

        if isinstance(message, dict):
            self._event_queue.append(message)
        return None

    async def _recv_json(self, timeout: float) -> Any:
        if self._ws is None:
            raise AssistantOpenClawGatewayError("gateway not connected")
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
        except ConnectionClosed as exc:
            raise AssistantOpenClawGatewayError(f"gateway closed: {exc.code}") from exc

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _session_matches(expected: str, actual: Any) -> bool:
        if not isinstance(actual, str):
            return False
        if actual == expected:
            return True
        return actual.endswith(f":{expected}")
