"""Offline, payload-redacting acceptance of a sanitized /agent/stream capture.

Usage: python scripts/release_acceptance.py analyze < sanitized-events.sse

Reads stdin only; performs no network calls, authentication, writes or retries.
The wire contract follows mobile/services/chat.ts and writeReceipt.ts: SSE data
contains JSON {event, data}, not a separate SSE event field. Python cannot import
that TypeScript client, so synthetic contract fixtures cover the shared shapes.
This is deliberately stricter than the interactive client's recovery parser.

Exit 0 means a completed turn produced an actionable order confirmation OR a
server write receipt. Neither proves an independently read-back database record,
UI navigation, account isolation, or App Review readiness. Never use this helper
alone as a release gate. Only feed synthetic or pre-sanitized captures; it is not
a general-purpose health-data sanitizer. Output contains fixed labels/counts only.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from typing import Any


class AcceptanceError(ValueError):
    """Only fixed, payload-free error codes may cross the CLI boundary."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AcceptanceError("invalid_json")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise AcceptanceError("invalid_json")


def _decode_frame(frame: bytes) -> dict[str, Any] | None:
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError:
        raise AcceptanceError("invalid_utf8") from None
    data = []
    for line in text.splitlines():
        if not line or line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if field == "data" and separator:
            data.append(value.removeprefix(" "))
        elif field not in ("event", "id", "retry"):
            raise AcceptanceError("invalid_sse_field")
    if not data:
        return None
    payload = "\n".join(data)
    if payload == "[DONE]":
        return {"event": "sentinel", "data": {}}
    try:
        parsed = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (ValueError, RecursionError):
        raise AcceptanceError("invalid_json") from None
    if isinstance(parsed, dict) and parsed.get("type") == "status" and "event" not in parsed:
        return {"event": "status", "data": {}}
    if (not isinstance(parsed, dict) or not isinstance(parsed.get("event"), str)
            or not parsed["event"] or not isinstance(parsed.get("data"), dict)):
        raise AcceptanceError("invalid_envelope")
    return parsed


def iter_agent_events(
    chunks: Iterable[bytes], *, max_frame_bytes: int = 262144, max_total_bytes: int = 8388608,
) -> Iterator[dict[str, Any]]:
    """Decode LF/CRLF frames across arbitrary byte and UTF-8 chunk boundaries."""
    if max_frame_bytes < 1 or max_total_bytes < 1:
        raise AcceptanceError("invalid_limits")
    buffer = bytearray()
    frame = bytearray()
    total = 0
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise AcceptanceError("invalid_chunk")
        total += len(chunk)
        if total > max_total_bytes:
            raise AcceptanceError("stream_too_large")
        buffer.extend(chunk)
        while (newline := buffer.find(b"\n")) >= 0:
            line = bytes(buffer[:newline + 1])
            del buffer[:newline + 1]
            frame.extend(line)
            if len(frame) > max_frame_bytes:
                raise AcceptanceError("frame_too_large")
            if line in (b"\n", b"\r\n"):
                event = _decode_frame(bytes(frame))
                frame.clear()
                if event is not None:
                    yield event
        if len(buffer) + len(frame) > max_frame_bytes:
            raise AcceptanceError("frame_too_large")
    if buffer or frame:
        raise AcceptanceError("truncated_frame")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _diet_receipt(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    # Match the native normalizer's snake/camel aliases, without truthy coercion.
    def field(camel: str, snake: str) -> Any:
        return raw[camel] if camel in raw else raw.get(snake)

    resource_id = field("resourceId", "resource_id")
    return (
        raw.get("verified") is True
        and raw.get("status", "verified") == "verified"
        and raw.get("action", "create") in ("create", "update")
        and field("resourceType", "resource_type") == "diet_record"
        and _nonempty_string(field("operationId", "operation_id"))
        and _nonempty_string(field("completedAt", "completed_at"))
        and (_nonempty_string(resource_id) or (type(resource_id) is int and resource_id > 0))
    )


def _order_confirmation(raw: Any) -> bool:
    if not isinstance(raw, dict) or raw.get("type") != "diet_draft":
        return False
    data = raw.get("data")
    if not isinstance(data, dict) or data.get("recorded") is True:
        return False
    foods = data.get("food_items")
    if isinstance(foods, str):
        recognition = data.get("ai_raw_result")
        if isinstance(recognition, str):
            try:
                recognition = json.loads(recognition, object_pairs_hook=_unique_object,
                                         parse_constant=_invalid_constant)
            except (ValueError, RecursionError):
                raise AcceptanceError("invalid_recognition_json") from None
        foods = recognition.get("foods") if isinstance(recognition, dict) else None
    actions = raw.get("actions")
    return (
        isinstance(foods, list) and bool(foods)
        and all(isinstance(food, dict) and bool(food.get("quantity")) for food in foods)
        and any(food.get("portion_basis") == "order_quantity" or food.get("source") == "order_estimate" for food in foods)
        and isinstance(actions, list)
        and any(isinstance(action, dict) and action.get("action") == "diet_record.create"
                and action.get("requires_manual_confirm") is True for action in actions)
    )


def analyze_order_stream(chunks: Iterable[bytes], **limits: int) -> dict[str, Any]:
    """Accept only explicit structured evidence; prose never establishes a write."""
    terminal = False
    sentinel = False
    confirmation = False
    receipt = False
    count = 0
    for event in iter_agent_events(chunks, **limits):
        name, data = event["event"], event["data"]
        if name == "sentinel":
            if not terminal or sentinel:
                raise AcceptanceError("unexpected_sentinel")
            sentinel = True
            continue
        if terminal:
            raise AcceptanceError("event_after_terminal")
        count += 1
        if name == "error" or data.get("error") or data.get("error_code"):
            raise AcceptanceError("stream_error")
        if name in ("card", "proposed_card"):
            confirmation |= _order_confirmation(data.get("descriptor", data.get("card", data)))
        elif name == "tool_result":
            if data.get("success") is False or data.get("write_outcome") in ("failed", "uncertain", "rejected"):
                raise AcceptanceError("stream_error")
            receipt |= _diet_receipt(data.get("receipt"))
        elif name == "done":
            outcome = data.get("turn_outcome", {})
            if not isinstance(outcome, dict):
                raise AcceptanceError("invalid_terminal")
            if ("status" in outcome and outcome["status"] not in ("complete", "waiting_for_user")):
                raise AcceptanceError("stream_error")
            if "completion_status" in data and data["completion_status"] != "complete":
                raise AcceptanceError("stream_error")
            cards, receipts = data.get("cards", []), data.get("write_receipts", [])
            if not isinstance(cards, list) or not isinstance(receipts, list):
                raise AcceptanceError("invalid_terminal")
            confirmation |= any(_order_confirmation(card) for card in cards)
            receipt |= any(_diet_receipt(item) for item in receipts)
            terminal = True
    if not terminal:
        raise AcceptanceError("terminal_missing")
    if not receipt and not confirmation:
        raise AcceptanceError("order_outcome_missing")
    return {
        "status": "recorded_receipt" if receipt else "pending_confirmation",
        "event_count": count,
        "write_verified": False,
        "requires_confirmation": not receipt,
        "requires_readback": receipt,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("analyze",))
    parser.parse_args()
    try:
        result = analyze_order_stream(iter(lambda: sys.stdin.buffer.read(8192), b""))
    except AcceptanceError as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1
    except OSError:
        print(json.dumps({"status": "failed", "error": "input_unavailable"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
