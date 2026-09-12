"""Bounded, credential-free transport to the official Pi agent loop.

Pi owns loop state; Python retains provider credentials and health authority.
Frames travel only over anonymous pipes and are never logged or persisted here.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any


class PiKernelError(RuntimeError):
    """A non-sensitive failure code suitable for the existing error boundary."""


class PiKernelSession:
    MAX_FRAME_BYTES = 8 * 1024 * 1024

    def __init__(self, *, command: list[str] | None = None, timeout: float = 120):
        runtime = Path(__file__).resolve().parents[2] / "pi-runtime" / "index.mjs"
        self.command = command or [shutil.which("node") or "node", str(runtime)]
        self.timeout = timeout
        self.process: asyncio.subprocess.Process | None = None
        self._pending: dict[str, Any] | None = None
        self._seen: set[str] = set()
        self._allowed_calls: dict[str, tuple[str, dict]] = {}
        self._done = False
        self._started = False

    @property
    def returncode(self) -> int | None:
        return self.process.returncode if self.process is not None else None

    async def __aenter__(self):
        # Do not inherit database/provider credentials or Node preload hooks.
        env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT") if key in os.environ}
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
                limit=self.MAX_FRAME_BYTES,
            )
        except OSError as exc:
            raise PiKernelError("pi_runtime_unavailable") from exc
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        process = self.process
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                # Process exit won the race with shutdown; still reap it below.
                await process.wait()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def _send(self, frame: dict[str, Any]):
        payload = json.dumps(frame, ensure_ascii=False, allow_nan=False).encode() + b"\n"
        if len(payload) > self.MAX_FRAME_BYTES:
            raise PiKernelError("pi_frame_too_large")
        if self.process is None or self.process.stdin is None:
            raise PiKernelError("pi_not_started")
        try:
            self.process.stdin.write(payload)
            await asyncio.wait_for(self.process.stdin.drain(), timeout=self.timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise PiKernelError("pi_transport_failed") from exc

    async def start(self, *, messages: list[dict], tools: list[dict], max_turns: int):
        if self._started or not isinstance(max_turns, int) or max_turns < 1:
            raise PiKernelError("pi_invalid_start")
        self._started = True
        await self._send({"type": "start", "messages": messages, "tools": tools, "max_turns": max_turns})

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._done:
            raise StopAsyncIteration
        if self._pending is not None:
            raise PiKernelError("pi_response_required")
        if not self._started or self.process is None or self.process.stdout is None:
            raise PiKernelError("pi_not_started")
        try:
            raw = await asyncio.wait_for(self.process.stdout.readline(), timeout=self.timeout)
            if not raw:
                raise PiKernelError("pi_unexpected_exit")
            if len(raw) > self.MAX_FRAME_BYTES:
                raise PiKernelError("pi_frame_too_large")
            frame = json.loads(raw)
        except (ValueError, UnicodeError, asyncio.TimeoutError) as exc:
            raise PiKernelError("pi_invalid_frame") from exc
        if not isinstance(frame, dict):
            raise PiKernelError("pi_invalid_frame")
        kind = frame.get("type")
        if kind == "error":
            raise PiKernelError("pi_runtime_failed")
        if kind == "done":
            if (
                not isinstance(frame.get("content"), str)
                or not isinstance(frame.get("messages"), list)
                or frame.get("finish_reason") not in {"stop", "length", "error"}
                or not isinstance(frame.get("turns"), int)
            ):
                raise PiKernelError("pi_invalid_frame")
            self._done = True
            self.process.stdin.close()
            try:
                code = await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError as exc:
                raise PiKernelError("pi_shutdown_failed") from exc
            if code != 0:
                raise PiKernelError("pi_unsuccessful_exit")
            return frame
        if kind not in {"model_request", "tool_request"}:
            raise PiKernelError("pi_invalid_frame")
        request_id = frame.get("id")
        if not isinstance(request_id, str) or not request_id or request_id in self._seen:
            raise PiKernelError("pi_invalid_request_id")
        if kind == "model_request":
            if not isinstance(frame.get("messages"), list) or not isinstance(frame.get("tools"), list):
                raise PiKernelError("pi_invalid_frame")
            self._allowed_calls.clear()
        else:
            name, args, call_id = frame.get("name"), frame.get("arguments"), frame.get("tool_call_id")
            if not isinstance(name, str) or not isinstance(args, dict) or not isinstance(call_id, str):
                raise PiKernelError("pi_invalid_frame")
            if self._allowed_calls.pop(call_id, None) != (name, args):
                raise PiKernelError("pi_unissued_tool_call")
        self._seen.add(request_id)
        self._pending = frame
        return frame

    async def respond(self, request: dict, **payload):
        if self._pending is None or request != self._pending:
            raise PiKernelError("pi_response_mismatch")
        kind = request["type"]
        if kind == "model_request":
            for call in payload.get("tool_calls") or []:
                function = call.get("function") or {}
                args = function.get("arguments")
                try:
                    args = json.loads(args) if isinstance(args, str) else args
                except (ValueError, TypeError):
                    # Pi returns schema errors to the model; malformed calls
                    # deliberately receive no Python dispatch capability.
                    continue
                call_id = call.get("id")
                if not isinstance(call_id, str) or not call_id or call_id in self._allowed_calls:
                    raise PiKernelError("pi_invalid_tool_call_id")
                if isinstance(args, dict):
                    self._allowed_calls[call_id] = (function.get("name"), args)
        await self._send({"type": kind.replace("request", "response"), "id": request["id"], **payload})
        self._pending = None
