"""Rejected water-description candidate, isolated for opt-in offline replay.

Live flash A/B regressed on explicit ml amounts. Never import from app runtime.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import re
from typing import Any

from app.services.agent_kernel.types import TurnSnapshot
from app.services.tool_schema_registry import HEALTH_TOOLS

_RECORD_HEADER = "记录的具体数据. 每种 type 的 schema:\n\n"
_RECORD_ENTRY = re.compile(r"(?m)^([a-z_]+):")
# This is deliberately narrower than the goal compiler. A full sentence match
# proves there is no second task, quoted subject, clinical clause or reference.
_CLOSED_WATER_RECORD = re.compile(
    r"(?P<date_prefix>今天|昨天|前天)?(?:请)?(?:帮我|给我)?"
    r"(?:记录|记下|记一下|录入|保存)(?:一下)?(?:我)?"
    r"(?P<date_body>今天|昨天|前天)?"
    r"(?:(?P<water_before>喝水|饮水)(?:了)?|喝(?:了)?)[ \t]*"
    r"(?P<amount>[0-9]{1,4}(?:\.[0-9]{1,3})?)[ \t]*"
    r"(?P<unit>毫升|ml)(?(water_before)|水)[。.!！]?", re.IGNORECASE,
)


def _owned_closed_water(snapshot: TurnSnapshot | None, user_id: int | None, message: str, has_attachment: bool) -> bool:
    if (
        not isinstance(snapshot, TurnSnapshot) or user_id is None
        or snapshot.envelope.user_id != user_id or snapshot.context.user_id != user_id
        or snapshot.envelope.text != message or snapshot.envelope.media or has_attachment
        or snapshot.actionable_references or snapshot.intent.ambiguity
        or snapshot.policy_mode != "enforce" or snapshot.goal is None
    ):
        return False
    match = _CLOSED_WATER_RECORD.fullmatch(message.strip())
    if match is None or (match["date_prefix"] and match["date_body"]):
        return False
    amount = Decimal(match["amount"])
    if not 1 <= amount <= 5000 or amount != amount.to_integral_value():
        return False
    expected_date = (snapshot.context.current_time.date() - timedelta(
        days={None: 0, "今天": 0, "昨天": 1, "前天": 2}[match["date_prefix"] or match["date_body"]],
    )).isoformat()
    goal = snapshot.goal
    if (
        goal.kind != "simple_health_record" or goal.domain != "water"
        or goal.operation != "create" or goal.target_record_type != "water"
        or goal.target_values != (("amount_ml", str(int(amount))),)
        or goal.target_date != expected_date or not goal.requires_verification
        or goal.requires_lookup or goal.requires_clarification
        or goal.evidence != ("current_user_turn",)
        or goal.postconditions != ("verified_receipt",)
    ):
        return False
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame

    intent = build_intent_frame(snapshot.envelope, snapshot.context)
    return intent == snapshot.intent and goal == compile_goal_spec(
        envelope=snapshot.envelope, context=snapshot.context, intent=intent,
    )


def _record_data_description(parameters: dict[str, Any]) -> str | None:
    properties = parameters.get("properties") or {}
    description = (properties.get("data") or {}).get("description")
    record_types = (properties.get("record_type") or {}).get("enum")
    if (
        not isinstance(description, str) or not description.startswith(_RECORD_HEADER)
        or not isinstance(record_types, list) or not all(isinstance(item, str) for item in record_types)
        or "water" not in record_types
    ):
        return None
    body = description[len(_RECORD_HEADER):]
    entries = list(_RECORD_ENTRY.finditer(body))
    names = [entry[1] for entry in entries]
    if (
        not entries or entries[0].start() != 0 or len(names) != len(set(names))
        or set(names) != set(record_types)
        or any(line and not line[0].isspace() and not _RECORD_ENTRY.match(line) for line in body.splitlines())
    ):
        return None
    water = names.index("water")
    stop = entries[water + 1].start() if water + 1 < len(entries) else len(body)
    return _RECORD_HEADER + body[entries[water].start():stop].rstrip()


def project_owned_record_data_descriptions(
    tools: list[dict[str, Any]], snapshot: TurnSnapshot | None, *,
    user_id: int | None, current_message: str, has_attachment: bool = False,
) -> list[dict[str, Any]]:
    """Trim only data examples for a closed, owner-bound water create goal.

    This is provider material selection, never a write or authorization gate.
    The caller must also exclude later repair rounds and pending runtime work.
    All routing/safety prose and executable argument schemas stay intact.
    Liter units retain the full examples after a live fast-model regression.
    Natural wording without an existing simple-record goal (including the
    current compiler's "喝了500ml水" case) keeps the full material.
    """
    if not _owned_closed_water(snapshot, user_id, current_message, has_attachment):
        return tools
    canonical = next((tool for tool in HEALTH_TOOLS if tool["function"]["name"] == "health_record"), None)
    if canonical is None:
        return tools
    original = canonical["function"]
    description = _record_data_description(original["parameters"])
    if description is None:
        return tools
    result = []
    for tool in tools:
        function = tool.get("function") or {}
        if (
            tool.get("type") != "function" or function.get("name") != "health_record"
            or function.get("description") != original["description"]
            or function.get("parameters") != original["parameters"]
        ):
            result.append(tool)
            continue
        projected = deepcopy(tool)
        projected["function"]["parameters"]["properties"]["data"]["description"] = description
        result.append(projected)
    return result
