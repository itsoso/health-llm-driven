"""Voice shortcut parsing that delegates execution to the XiaoBa Agent Kernel.

This module converts a small, bounded set of explicit spoken observations into
tool arguments.  Low-risk, slot-complete water records can be written directly
after ToolGateway preflight and a verified receipt; higher-risk health records
still use the shared confirmation boundary.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.context import build_turn_snapshot
from app.services.agent_kernel.types import TurnSnapshot
from app.services.agent_write_outcome import (
    classify_write_execution,
    write_result_declares_non_success,
)

logger = logging.getLogger(__name__)

WATER_AMOUNT_MAP = {
    "一杯": 250,
    "两杯": 500,
    "三杯": 750,
    "半杯": 125,
    "一瓶": 500,
    "半瓶": 250,
}


class VoiceCommandService:
    """Build a voice record draft; never let phrase matching authorize a write."""

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def build_draft(self, text: str) -> Optional[dict[str, Any]]:
        """Return a bounded record draft only for an explicit semantic write.

        The slot extractors below may recognize measurements, but they cannot
        authorize persistence.  A shared intent frame is created first; read,
        advice, ambiguous, and negated turns do not produce a write draft.
        """
        clean = str(text or "").strip()
        if not clean:
            return None
        snapshot = build_turn_snapshot(
            self.db,
            user_id=self.user_id,
            channel="voice",
            text=clean,
        )
        return self._build_draft_from_snapshot(clean, snapshot)

    async def execute(
        self,
        text: str,
        *,
        user_auth_token: Optional[str] = None,
        client_turn_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Route a parsed voice observation through the normal tool boundary.

        A shortcut response must only report completion after a verified write
        receipt.  Bounded water records may complete immediately; higher-risk
        observations remain confirmation-bound.
        """
        clean = str(text or "").strip()
        if not clean:
            return None

        executor = AgentExecutor(self.db)
        executor._current_user_id = self.user_id
        executor._current_turn_user_message = clean
        executor._turn_channel = "voice"
        snapshot = executor._start_agent_kernel_turn(
            user_id=self.user_id,
            message=clean,
            channel="voice",
        )
        draft = self._build_draft_from_snapshot(clean, snapshot)
        if draft is None:
            executor._finish_agent_kernel_turn(status="no_action")
            return None

        tool_arguments = dict(draft["arguments"])
        if draft["command_type"] != "water":
            executor._finish_agent_kernel_turn(status="pending_confirmation")
            return {
                "command_type": draft["command_type"],
                "message": f"已识别{draft['message'].removeprefix('准备记录 ')}，请确认后写入。",
                "data": draft["data"],
                "requires_confirmation": True,
                "execution_status": "pending_confirmation",
            }

        try:
            from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

            result = await CloudAgentRuntimeFacade(self.db).execute_tool(
                user_id=self.user_id,
                message=clean,
                origin="voice_command",
                channel="voice",
                tool_name="health_record",
                arguments=tool_arguments,
                user_auth_token=user_auth_token,
                client_turn_id=client_turn_id,
                run_id=snapshot.context.run_id,
                executor=executor,
                source="voice_command",
            )
        except Exception as exc:  # noqa: BLE001 - client receives no false completion
            logger.exception(
                "Voice shortcut dispatch failed user=%s command=%s error_type=%s",
                self.user_id,
                draft["command_type"],
                type(exc).__name__,
            )
            executor._finish_agent_kernel_turn(status="failed")
            return {
                "command_type": draft["command_type"],
                "message": "语音记录暂未完成，请在小巴对话中重试。",
                "data": draft["data"],
                "requires_confirmation": False,
                "execution_status": "failed",
            }

        receipt = _verified_record_receipt(
            result,
            fallback_message=draft["message"].replace("准备记录 ", "已记录 ", 1),
        )
        write_outcome = classify_write_execution(result, receipt=receipt)
        if str(result).startswith("[NEEDS_CONFIRMATION]"):
            executor._finish_agent_kernel_turn(status="pending_confirmation")
            return {
                "command_type": draft["command_type"],
                "message": "已识别这条记录，请在小巴对话中确认后写入。",
                "data": draft["data"],
                "requires_confirmation": True,
                "execution_status": "pending_confirmation",
            }
        if (
            str(result).startswith(("Error:", "[NEEDS_CLARIFICATION]"))
            or write_outcome.status in {"rejected", "failed"}
        ):
            executor._finish_agent_kernel_turn(status="blocked_or_failed")
            return {
                "command_type": draft["command_type"],
                "message": "这条语音记录未写入，请在小巴对话中补充或确认。",
                "data": draft["data"],
                "requires_confirmation": False,
                "execution_status": "blocked_or_failed",
            }

        if receipt is not None:
            executor._finish_agent_kernel_turn(status="recorded")
            return {
                "command_type": draft["command_type"],
                "message": receipt["message"],
                "data": draft["data"],
                "requires_confirmation": False,
                "execution_status": "recorded",
                "record_id": receipt["record_id"],
                "undo_path": receipt.get("undo_path"),
            }

        # Preserve fail-loud semantics if a future tool contract changes instead
        # of reporting a fabricated receipt.
        executor._finish_agent_kernel_turn(status="unverified_result")
        return {
            "command_type": draft["command_type"],
            "message": "记录尚未取得可验证回执，请在小巴对话中确认结果。",
            "data": draft["data"],
            "requires_confirmation": False,
            "execution_status": "unverified_result",
        }

    def _build_draft_from_snapshot(
        self,
        text: str,
        snapshot: TurnSnapshot,
    ) -> Optional[dict[str, Any]]:
        if snapshot.intent.primary != "write" or snapshot.intent.operation != "create":
            return None

        for extractor in (_extract_water, _extract_weight, _extract_blood_pressure):
            draft = extractor(text)
            if draft is not None:
                draft["snapshot"] = snapshot
                return draft
        return None


def _extract_water(text: str) -> Optional[dict[str, Any]]:
    normalized = _normalize(text)
    if "水" not in normalized or not any(token in normalized for token in ("喝", "饮")):
        return None
    amount = next((value for phrase, value in WATER_AMOUNT_MAP.items() if phrase in normalized), None)
    if amount is None:
        amount = _first_number(normalized, low=10, high=5000)
    if amount is None:
        return None
    return _record_draft(
        "water",
        {"amount": int(amount), "drink_type": "水"},
        f"饮水 {int(amount)}ml",
    )


def _verified_record_receipt(
    result: Any,
    *,
    fallback_message: str | None = None,
) -> dict[str, Any] | None:
    if isinstance(result, str):
        try:
            payload = json.loads(result)
        except (TypeError, ValueError):
            return None
    elif isinstance(result, dict):
        payload = result
    else:
        return None
    if not isinstance(payload, dict):
        return None
    if write_result_declares_non_success(payload):
        return None
    if payload.get("success") is not True:
        return None
    record_id = payload.get("record_id")
    if record_id is None and payload.get("replayed") is True:
        record_id = payload.get("resource_id")
    if isinstance(record_id, str) and record_id.isdigit():
        record_id = int(record_id)
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
        return None
    message = str(payload.get("message") or fallback_message or "").strip()
    if not message:
        return None
    return {
        "record_id": record_id,
        "message": message,
        "undo_path": payload.get("undo_path"),
    }
def _extract_weight(text: str) -> Optional[dict[str, Any]]:
    normalized = _normalize(text)
    has_weight_signal = "体重" in normalized or any(unit in normalized for unit in ("kg", "公斤", "千克", "斤"))
    if not has_weight_signal:
        return None
    number = _first_number(normalized, low=20, high=600)
    if number is None:
        return None
    weight = number / 2 if "斤" in normalized else number
    if not 20 <= weight <= 300:
        return None
    return _record_draft("weight", {"weight": round(weight, 1)}, f"体重 {round(weight, 1)}kg")


def _extract_blood_pressure(text: str) -> Optional[dict[str, Any]]:
    normalized = _normalize(text)
    has_pressure_signal = any(
        marker in normalized
        for marker in ("血压", "高压", "低压", "收缩压", "舒张压")
    )
    if not has_pressure_signal:
        return None
    values = _numbers(normalized)
    if len(values) < 2:
        return None
    systolic, diastolic = int(values[0]), int(values[1])
    if not 60 <= systolic <= 250 or not 30 <= diastolic <= 150:
        return None
    return _record_draft(
        "blood_pressure",
        {"systolic": systolic, "diastolic": diastolic},
        f"血压 {systolic}/{diastolic}",
    )


def _record_draft(command_type: str, data: dict[str, Any], summary: str) -> dict[str, Any]:
    return {
        "command_type": command_type,
        "message": f"准备记录 {summary}",
        "data": dict(data),
        "arguments": {"record_type": command_type, "data": dict(data)},
    }


def _normalize(text: str) -> str:
    return "".join(str(text or "").split()).lower()


def _numbers(text: str) -> list[float]:
    """Extract decimal numbers without using phrase-level regular expressions."""
    values: list[float] = []
    buffer: list[str] = []
    for char in text:
        if char.isdigit() or (char == "." and buffer and "." not in buffer):
            buffer.append(char)
            continue
        if buffer:
            values.append(float("".join(buffer)))
            buffer = []
    if buffer:
        values.append(float("".join(buffer)))
    return values


def _first_number(text: str, *, low: float, high: float) -> Optional[float]:
    return next((value for value in _numbers(text) if low <= value <= high), None)
