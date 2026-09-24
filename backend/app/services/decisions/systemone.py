"""Jev / Laya wire adapter, independent of chat-completion providers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import math
import re
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.config import settings
from app.services.decisions.config import DecisionConfig, DecisionError
from app.services.decisions.control import runtime_mode
from app.services.llm.pii_scrub import scrub_pii


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["choice", "score", "noul"]
    instructions: str = Field(min_length=1, max_length=8000)
    criteria: dict[str, str] | list[str] | None = None

    @model_validator(mode="after")
    def validate_criteria(self):
        c = self.criteria
        valid = (
            (self.type == "choice" and isinstance(c, dict) and 1 <= len(c) <= 255)
            or (self.type == "score" and isinstance(c, list) and 2 <= len(c) <= 10)
            or (
                self.type == "noul"
                and (c is None or isinstance(c, dict) and set(c) == {"true", "false"})
            )
        )
        if not valid:
            raise ValueError("invalid question criteria")
        return self


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    state: JsonValue
    questions: dict[str, Question] = Field(min_length=1, max_length=64)


@dataclass(frozen=True)
class DecisionResult:
    model: str
    answers: dict
    input_tokens: int
    output_tokens: int


class DecisionProvider(Protocol):
    async def evaluate(
        self, request: DecisionRequest, *, user_id: int
    ) -> DecisionResult: ...


def _number(value, low=0, high=1):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def _require(condition):
    if not condition:
        raise ValueError("invalid response")


def _result(data, request):
    """Reject partial, out-of-vocabulary or invalid distributions as a whole."""
    try:
        model, answers, usage = data["model"], data["answers"], data["usage"]
        _require(
            isinstance(model, str)
            and re.fullmatch(r"[\w./:@+-]{1,128}", model, flags=re.ASCII)
        )
        _require(isinstance(answers, dict) and set(answers) == set(request.questions))
        for key in ("input_tokens", "output_tokens"):
            _require(type(usage[key]) is int and usage[key] >= 0)
        clean = {}
        for name, q in request.questions.items():
            a = answers[name]
            _require(a["type"] == q.type)
            if q.type == "noul":
                _require(_number(a["noul"]))
                clean[name] = {"type": "noul", "noul": a["noul"]}
                continue
            p = a["probabilities"]
            keys = (
                set(q.criteria)
                if q.type == "choice"
                else {str(i) for i in range(len(q.criteria))}
            )
            _require(isinstance(p, dict) and set(p) == keys)
            _require(
                all(_number(v) for v in p.values()) and abs(sum(p.values()) - 1) <= 0.02
            )
            _require(_number(a["confidence"]))
            if q.type == "choice":
                _require(
                    a["choice"] in keys and p[a["choice"]] >= max(p.values()) - 1e-6
                )
                clean[name] = {
                    "type": q.type,
                    "choice": a["choice"],
                    "probabilities": p,
                    "confidence": a["confidence"],
                }
            else:
                _require(_number(a["score"], 0, len(q.criteria) - 1))
                _require(
                    abs(a["score"] - sum(int(k) * v for k, v in p.items())) <= 0.02
                )
                clean[name] = {
                    "type": q.type,
                    "score": a["score"],
                    "probabilities": p,
                    "confidence": a["confidence"],
                }
        return DecisionResult(
            model, clean, usage["input_tokens"], usage["output_tokens"]
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DecisionError("invalid_response") from None


def _scrub(value):
    if isinstance(value, str):
        return scrub_pii(value)[0]
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return value


class SystemOneProvider:
    def __init__(self, config: DecisionConfig, *, transport=None):
        self.config = config
        self._transport = transport

    async def evaluate(
        self, request: DecisionRequest, *, user_id: int
    ) -> DecisionResult:
        if type(user_id) is not int or user_id <= 0:
            raise DecisionError("identity_required")
        cfg = self.config
        body = request.model_dump(exclude_none=True)
        body = _scrub(body)
        # Conservatively bound UTF-8 bytes, never silently truncate model context.
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        limit = (
            min(settings.decision_max_input_bytes, 960)
            if cfg.provider == "laya"
            else settings.decision_max_input_bytes
        )
        if len(raw) > limit:
            raise DecisionError("input_too_large")
        if cfg.provider == "laya":
            for q in body["questions"].values():
                if (
                    len(
                        json.dumps(
                            q, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    )
                    > 240
                ):
                    raise DecisionError("question_too_large")
        body["model"] = cfg.model
        key = settings.decision_api_key
        key = key.get_secret_value() if hasattr(key, "get_secret_value") else key
        if cfg.provider == "jev" and not key:
            raise DecisionError("api_key_missing")
        headers = {"Authorization": f"Bearer {key}"} if key else {}

        async def authorize(req):
            # Re-check current configuration and consent at the actual send.
            from app.services.decisions.config import configured_decision

            if (
                await asyncio.to_thread(runtime_mode) == "off"
                or configured_decision() != cfg
                or str(req.url) != cfg.endpoint
            ):
                raise DecisionError("configuration_changed")
            if not cfg.local:
                from app.services import ai_consent

                await asyncio.to_thread(
                    ai_consent.require_ai_consent, user_id, destination=cfg.endpoint
                )

        try:
            # No automatic retries/failover. No env proxy for local data; no redirects.
            async with asyncio.timeout(settings.decision_timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=settings.decision_timeout_seconds,
                    trust_env=False,
                    follow_redirects=False,
                    transport=self._transport,
                    event_hooks={"request": [authorize]},
                ) as client:
                    async with client.stream(
                        "POST", cfg.endpoint, json=body, headers=headers
                    ) as res:
                        if res.status_code != 200:
                            raise DecisionError(f"http_{res.status_code}")
                        chunks = bytearray()
                        async for chunk in res.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > 262144:
                                raise DecisionError("response_too_large")
                        try:
                            decoded = json.loads(chunks)
                        except RecursionError:
                            raise DecisionError("invalid_response") from None
                        return _result(decoded, request)
        except (TimeoutError, httpx.TimeoutException):
            raise DecisionError("timeout") from None
        except httpx.RequestError:
            raise DecisionError("transport_error") from None
        except (ValueError, UnicodeError):
            raise DecisionError("invalid_response") from None
