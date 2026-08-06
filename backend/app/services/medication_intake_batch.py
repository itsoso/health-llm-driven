"""Server-owned confirmation plans for multi-medication intake facts.

The language model may help identify a medication mention, but it is never an
authorization boundary.  This module freezes the user's source message, the
parsed items, and the local intake timestamp in a manual ``WriteIntent``.  A
later explicit confirmation executes the whole batch in the caller's database
transaction and returns one verified receipt per medication log.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.medication import Medication, MedicationLog
from app.models.user import User
from app.models.write_intent import WriteIntent
from app.utils.timezone import DEFAULT_TIMEZONE_NAME, get_user_now, get_user_timezone


WRITE_INTENT_KIND = "medication_intake_batch"
_PLAN_VERSION = 2
_MAX_ITEMS = 8
_PLAN_TTL = timedelta(minutes=30)


class InvalidMedicationIntakePlan(ValueError):
    """The frozen plan or its source binding is malformed or has changed."""


class ExpiredMedicationIntakePlan(InvalidMedicationIntakePlan):
    """A still-pending manual authorization window has elapsed."""


class MedicationIntakePlanNotPresented(InvalidMedicationIntakePlan):
    """The server has not durably presented this exact plan to the user."""


class MedicationIntakeConflict(RuntimeError):
    """A different fact already occupies one of the frozen intake slots."""


_CHINESE_DIGITS = {
    "一": "1",
    "二": "2",
    "两": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
    "半": "0.5",
}
_COUNT_TOKEN = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半])"
_QUANTITY_UNIT = r"(?:粒|片|袋|支|丸|颗|滴|喷|毫升|ml|单位|iu|u)"
_QUANTITY_RE = re.compile(
    rf"(?P<count>{_COUNT_TOKEN})\s*(?P<unit>{_QUANTITY_UNIT})",
    re.IGNORECASE,
)
_SHARED_QUANTITY_RE = re.compile(
    rf"各\s*(?P<count>{_COUNT_TOKEN})\s*(?P<unit>{_QUANTITY_UNIT})",
    re.IGNORECASE,
)
_PREPOSED_QUANTITY_RE = re.compile(
    rf"(?P<count>{_COUNT_TOKEN})\s*(?P<unit>{_QUANTITY_UNIT})\s*$",
    re.IGNORECASE,
)
_STRENGTH_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|毫克|mcg|μg|ug|微克|g|克)",
    re.IGNORECASE,
)
_DECLARED_COUNT_RE = re.compile(r"(?P<count>[二两三四五六七八九十]|\d+)\s*种")
_EXPLICIT_RECORD_RE = re.compile(r"(?:记录|记下|帮我记|给我记)")
_INGESTION_RE = re.compile(r"(?:服用|服了|已服|吃了|吃过|刚吃)")
_FAIL_CLOSED_RE = re.compile(
    r"(?:不要记录|别记|不用记|取消|撤销|更正|改成|没吃|没有吃|未服|不是|并未)"
)
_QUESTION_RE = re.compile(r"[?？]|(?:是不是|是否|有没|吗(?:[呀呢啊]?$))")
_NON_CURRENT_TIME_RE = re.compile(
    r"(?:前天|昨天|昨日|昨晚|昨早|今早|今天|今日|早上|上午|中午|下午|"
    r"傍晚|晚上|夜里|凌晨|上周|本周|周[一二三四五六日天]|"
    r"\d{4}\s*[-/.年]\s*\d{1,2}|\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|"
    r"\d{1,2}\s*[:：]\s*\d{1,2}|"
    r"[零〇一二两三四五六七八九十百\d]{1,3}\s*[点时])"
)
_ITEM_SEPARATOR_RE = r"(?:[、,，;；]|和|与|及)"
_ITEM_TAIL_RE = re.compile(
    rf"^\s*[)）]?\s*"
    rf"(?:(?P<strength>\d+(?:\.\d+)?\s*(?:mg|毫克|mcg|μg|ug|微克|g|克))\s*)?"
    rf"(?:(?P<quantity>{_COUNT_TOKEN}\s*{_QUANTITY_UNIT})\s*)?"
    rf"(?P<separator>{_ITEM_SEPARATOR_RE})?\s*[。.！!]?\s*$",
    re.IGNORECASE,
)


def _alias_registry() -> Mapping[str, str]:
    # Imported lazily so this service stays independent of the originator
    # lookup implementation while sharing its curated, non-LLM name facts.
    from app.services.originator_drugs import medication_aliases

    return medication_aliases()


def _normalized_alias(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _canonical_name(value: str, aliases: Mapping[str, str] | None = None) -> str:
    aliases = aliases or _alias_registry()
    raw = _normalized_alias(value)
    if not raw:
        return ""
    exact = aliases.get(raw)
    if exact:
        return exact
    # Substring folding is unsafe for combination products: a name containing
    # two active ingredients could otherwise collapse to whichever alias sorts
    # first.  Unknown/full formulation names remain distinct until explicitly
    # curated as an exact alias.
    return str(value or "").strip()


def _normalized_decimal(token: str) -> str | None:
    raw = _CHINESE_DIGITS.get(token, token)
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0:
        return None
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _normalized_quantity(count: str, unit: str) -> str | None:
    normalized_count = _normalized_decimal(count)
    if normalized_count is None:
        return None
    lowered_unit = unit.lower()
    if lowered_unit in {"iu", "u"}:
        normalized_unit = "单位"
    elif lowered_unit == "ml":
        normalized_unit = "ml"
    else:
        normalized_unit = unit
    value = f"{normalized_count}{normalized_unit}"
    return value if len(value) <= 100 else None


def _normalized_quantity_text(value: Any) -> str | None:
    match = _QUANTITY_RE.fullmatch(str(value or "").strip())
    if match is None:
        return None
    return _normalized_quantity(match.group("count"), match.group("unit"))


def _normalized_strength_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    match = _STRENGTH_RE.fullmatch(str(value).strip())
    if match is None:
        return None
    number = _normalized_decimal(match.group("value"))
    if number is None:
        return None
    raw_unit = match.group("unit").lower()
    unit = {
        "毫克": "mg",
        "微克": "mcg",
        "μg": "mcg",
        "ug": "mcg",
        "克": "g",
    }.get(raw_unit, raw_unit)
    normalized = f"{number}{unit}"
    return normalized if len(normalized) <= 100 else None


def _supported_prefix(prefix: str) -> bool:
    """Accept only a narrow record+intake preamble before the first drug."""
    remainder = str(prefix or "")
    remainder = re.sub(
        rf"{_COUNT_TOKEN}\s*种(?:[\u4e00-\u9fff]{{0,6}})?药",
        "",
        remainder,
        flags=re.IGNORECASE,
    )
    phrases = (
        "帮我记录", "给我记录", "帮我记下", "给我记下", "帮我记", "给我记",
        "记录", "记下", "一下", "我", "刚刚", "刚才", "刚", "已经", "已",
        "服用", "服了", "吃了", "吃过", "吃",
    )
    for phrase in phrases:
        remainder = remainder.replace(phrase, "")
    remainder = re.sub(r"[\s,，:：;；。.！!]", "", remainder)
    return not remainder


def _declared_item_count(text: str) -> int | None:
    match = _DECLARED_COUNT_RE.search(text)
    if match is None:
        return None
    token = match.group("count")
    try:
        return int(_CHINESE_DIGITS.get(token, token))
    except ValueError:
        return None


def _find_name_mentions(
    text: str,
    *,
    known_names: Iterable[str],
) -> list[dict[str, Any]]:
    registry = dict(_alias_registry())
    for name in known_names:
        normalized = _normalized_alias(name)
        if normalized:
            registry.setdefault(normalized, str(name).strip())

    lowered = text.lower()
    candidates: list[tuple[int, int, str, str]] = []
    # Longest aliases win overlapping matches (e.g. 富马酸伏诺拉生 over 伏诺拉生).
    for alias in sorted(registry, key=lambda item: (-len(item), item)):
        if not alias:
            continue
        pattern = re.escape(alias)
        if alias.isascii() and alias[0].isalnum() and alias[-1].isalnum():
            pattern = rf"(?<![a-z0-9]){pattern}(?![a-z0-9])"
        for match in re.finditer(pattern, lowered, flags=re.IGNORECASE):
            candidates.append((match.start(), match.end(), alias, registry[alias]))

    selected: list[tuple[int, int, str, str]] = []
    for candidate in sorted(candidates, key=lambda row: (-(row[1] - row[0]), row[0])):
        start, end, _, _ = candidate
        if any(not (end <= old_start or start >= old_end) for old_start, old_end, _, _ in selected):
            continue
        selected.append(candidate)
    selected.sort(key=lambda row: row[0])

    by_canonical: dict[str, list[tuple[int, int, str, str]]] = {}
    for row in selected:
        by_canonical.setdefault(row[3], []).append(row)

    mentions: list[dict[str, Any]] = []
    for canonical, rows in by_canonical.items():
        if len(rows) > 1:
            first_start = rows[0][0]
            last_end = rows[-1][1]
            # Include the character immediately after the final alias so a
            # closing parenthesis is part of the cluster (the alias span itself
            # naturally ends just before it).
            cluster = text[first_start:min(len(text), last_end + 1)]
            # Generic + brand in one parenthetical is one medicine.  Repeating
            # a medication elsewhere is ambiguous and therefore rejected.
            if not (
                ("（" in cluster and "）" in cluster)
                or ("(" in cluster and ")" in cluster)
            ):
                return []
        mentions.append(
            {
                "canonical": canonical,
                "start": rows[0][0],
                "end": rows[-1][1],
            }
        )
    mentions.sort(key=lambda item: item["start"])
    return mentions


def parse_medication_intake_batch(
    text: str,
    *,
    known_names: Iterable[str] = (),
) -> dict[str, Any] | None:
    """Parse only narrow, explicit, affirmative medication intake records.

    The parser intentionally abstains on questions, negation/corrections,
    missing quantities, repeated medication names, or count mismatches.  Those
    cases remain available to the normal conversational clarification path.
    """
    raw = str(text or "").strip()
    if not raw or len(raw) > 1000:
        return None
    if not _EXPLICIT_RECORD_RE.search(raw) or not _INGESTION_RE.search(raw):
        return None
    if (
        _FAIL_CLOSED_RE.search(raw)
        or _QUESTION_RE.search(raw)
        or _NON_CURRENT_TIME_RE.search(raw)
    ):
        return None

    mentions = _find_name_mentions(raw, known_names=known_names)
    if not mentions or len(mentions) > _MAX_ITEMS:
        return None
    prefix = raw[:mentions[0]["start"]]
    preposed_quantity: str | None = None
    preposed_match = _PREPOSED_QUANTITY_RE.search(prefix)
    if preposed_match is not None:
        # Common spoken Chinese places the actual amount before one medication
        # ("吃了两粒阿奇霉素").  Restrict this grammar to a single curated name;
        # for multiple drugs the amount-to-item mapping is ambiguous.
        if len(mentions) != 1:
            return None
        preposed_quantity = _normalized_quantity(
            preposed_match.group("count"),
            preposed_match.group("unit"),
        )
        if preposed_quantity is None:
            return None
        prefix = prefix[:preposed_match.start()]
    if not _supported_prefix(prefix):
        return None
    if any(
        not raw[mentions[index]["end"]:mentions[index + 1]["start"]]
        for index in range(len(mentions) - 1)
    ):
        # Adjacent curated names with no whitespace/separator may be a fixed
        # combination product, not two independently administered medicines.
        return None
    declared_count = _declared_item_count(raw)
    if declared_count is not None and declared_count != len(mentions):
        return None

    shared_matches = list(_SHARED_QUANTITY_RE.finditer(raw))
    if len(shared_matches) > 1:
        return None
    shared_match = shared_matches[0] if shared_matches else None
    if shared_match is not None and shared_match.start() < mentions[-1]["end"]:
        return None
    shared_quantity = (
        _normalized_quantity(shared_match.group("count"), shared_match.group("unit"))
        if shared_match
        else None
    )
    if shared_match is not None and shared_quantity is None:
        return None
    items: list[dict[str, Any]] = []
    for index, mention in enumerate(mentions):
        segment_end = mentions[index + 1]["start"] if index + 1 < len(mentions) else len(raw)
        segment = raw[mention["end"]:segment_end]
        if shared_match is not None and index == len(mentions) - 1:
            relative_start = shared_match.start() - mention["end"]
            relative_end = shared_match.end() - mention["end"]
            segment = segment[:relative_start] + segment[relative_end:]
        tail_match = _ITEM_TAIL_RE.fullmatch(segment)
        if tail_match is None:
            return None
        if index == len(mentions) - 1 and tail_match.group("separator"):
            return None
        direct_quantity = _normalized_quantity_text(tail_match.group("quantity"))
        if tail_match.group("quantity") and direct_quantity is None:
            return None
        supplied_quantities = [
            value
            for value in (direct_quantity, shared_quantity, preposed_quantity)
            if value is not None
        ]
        if len(supplied_quantities) > 1:
            return None
        quantity = direct_quantity or shared_quantity or preposed_quantity
        if not quantity:
            return None
        observed_strength = _normalized_strength_text(tail_match.group("strength"))
        if tail_match.group("strength") and observed_strength is None:
            return None
        items.append(
            {
                "medication_name": mention["canonical"],
                "actual_dosage": quantity,
                "observed_strength": observed_strength,
            }
        )
    return {"items": items}


def _source_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _plan_hash(payload_without_hash: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload_without_hash,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _payload_without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "plan_sha256"}


def _validate_payload_hash(payload: Mapping[str, Any]) -> None:
    expected = str(payload.get("plan_sha256") or "")
    actual = _plan_hash(_payload_without_hash(payload))
    if not expected or expected != actual:
        raise InvalidMedicationIntakePlan("medication intake plan hash mismatch")


def _timezone_label(local_now: datetime, fallback_tz: Any) -> str:
    return (
        getattr(local_now.tzinfo, "key", None)
        or getattr(fallback_tz, "key", None)
        or DEFAULT_TIMEZONE_NAME
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _build_payload(
    *,
    conversation_id: int,
    source_message_id: int,
    source_content: str,
    local_now: datetime,
    user_tz: Any,
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    issued_at = _aware_utc(_utc_now())
    payload: dict[str, Any] = {
        "version": _PLAN_VERSION,
        "conversation_id": conversation_id,
        "source_message_id": source_message_id,
        "source_sha256": _source_sha256(source_content),
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + _PLAN_TTL).isoformat(),
        "taken_date": local_now.date().isoformat(),
        "taken_time": local_now.strftime("%H:%M"),
        "timezone": _timezone_label(local_now, user_tz),
        "items": [dict(item) for item in items],
    }
    payload["plan_sha256"] = _plan_hash(payload)
    return payload


def propose_medication_intake_batch(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    source_message_id: int,
    text: str,
    reference_now: datetime | None = None,
) -> WriteIntent | None:
    """Freeze a source-bound manual confirmation plan; never writes medication facts."""
    conversation = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        )
        .first()
    )
    if conversation is None:
        raise LookupError("agent conversation not found")
    source = (
        db.query(AgentMessage)
        .filter(
            AgentMessage.id == source_message_id,
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.role == "user",
        )
        .first()
    )
    if source is None:
        raise LookupError("source user message not found")
    if source.content != text:
        raise InvalidMedicationIntakePlan("source message content mismatch")

    known_names = [
        row[0]
        for row in db.query(Medication.name)
        .filter(Medication.user_id == user_id)
        .all()
        if row[0]
    ]
    draft = parse_medication_intake_batch(text, known_names=known_names)
    if draft is None:
        return None

    user_tz = get_user_timezone(db, user_id)
    local_now = reference_now or get_user_now(db, user_id)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=user_tz)
    else:
        local_now = local_now.astimezone(user_tz)
    payload = _build_payload(
        conversation_id=conversation_id,
        source_message_id=source_message_id,
        source_content=source.content,
        local_now=local_now,
        user_tz=user_tz,
        items=draft["items"],
    )

    existing = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.kind == WRITE_INTENT_KIND,
            WriteIntent.target_type == "agent_message",
            WriteIntent.target_id == source_message_id,
        )
        .order_by(WriteIntent.id.asc())
        .first()
    )
    if existing is not None:
        existing_payload, existing_items = _validated_plan(db, existing)
        parsed_items = [
            {
                "medication_name": _canonical_name(item["medication_name"]),
                "actual_dosage": item["actual_dosage"],
                "observed_strength": item.get("observed_strength"),
            }
            for item in draft["items"]
        ]
        if (
            existing_payload.get("conversation_id") != conversation_id
            or existing_items != parsed_items
        ):
            raise InvalidMedicationIntakePlan("source already has a different medication intake plan")
        # The source message is the idempotency key.  Its first proposal owns
        # the frozen intake timestamp; a later HTTP/stream retry must not move
        # the fact forward in time merely because the clock advanced.
        return existing

    intent = WriteIntent(
        user_id=user_id,
        kind=WRITE_INTENT_KIND,
        title=f"{len(draft['items'])}项用药记录待确认",
        description=f"确认后将按同一时间点写入{len(draft['items'])}条服药事实；未确认不写入。",
        status="pending",
        source="agent_medication_intake",
        trust_tier="manual_confirm",
        target_type="agent_message",
        target_id=source_message_id,
        payload=payload,
    )
    db.add(intent)
    try:
        db.commit()
        db.refresh(intent)
        return intent
    except IntegrityError:
        # The partial unique index resolves concurrent proposals.  Return only
        # the identical, intact winner; otherwise fail loudly.
        db.rollback()
        winner = (
            db.query(WriteIntent)
            .filter(
                WriteIntent.user_id == user_id,
                WriteIntent.kind == WRITE_INTENT_KIND,
                WriteIntent.target_type == "agent_message",
                WriteIntent.target_id == source_message_id,
            )
            .first()
        )
        if winner is None:
            raise
        winner_payload, winner_items = _validated_plan(db, winner)
        parsed_items = [
            {
                "medication_name": _canonical_name(item["medication_name"]),
                "actual_dosage": item["actual_dosage"],
                "observed_strength": item.get("observed_strength"),
            }
            for item in draft["items"]
        ]
        if (
            winner_payload.get("conversation_id") != conversation_id
            or winner_items != parsed_items
        ):
            raise InvalidMedicationIntakePlan("concurrent medication intake plan mismatch")
        return winner


def propose_medication_intake_items(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    source_message_id: int,
    items: Sequence[Mapping[str, Any]],
    reference_now: datetime | None = None,
    allow_merge_pending: bool = False,
) -> WriteIntent:
    """Freeze already-extracted tool items without accepting model authorization.

    This is a compatibility bridge for a medication ``health_record`` selected
    by an LLM.  The model may propose names and observed quantities, but the
    plan is still source-bound and manual-confirm only.  Multiple medication
    tool calls from the same model response may extend the same still-pending
    plan before its assistant confirmation is shown.  Published plans are
    immutable; callers that have multiple tool calls must aggregate them and
    invoke this function once before exposing a confirmation surface.
    """
    conversation = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        )
        .first()
    )
    if conversation is None:
        raise LookupError("agent conversation not found")
    source_message = (
        db.query(AgentMessage)
        .filter(
            AgentMessage.id == source_message_id,
            AgentMessage.conversation_id == conversation_id,
            AgentMessage.role == "user",
        )
        .first()
    )
    if source_message is None:
        raise LookupError("source user message not found")
    if _NON_CURRENT_TIME_RE.search(source_message.content or ""):
        raise InvalidMedicationIntakePlan(
            "historical medication time requires explicit deterministic parsing"
        )

    aliases = _alias_registry()
    controlled_names = {
        normalized
        for value in (*aliases.keys(), *aliases.values())
        if (normalized := _normalized_alias(value))
    }
    controlled_names.update(
        normalized
        for (value,) in (
            db.query(Medication.name)
            .filter(Medication.user_id == user_id)
            .all()
        )
        if (normalized := _normalized_alias(value))
    )
    normalized_items: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for raw_item in items:
        name = str(raw_item.get("medication_name") or "").strip()
        dosage = _normalized_quantity_text(raw_item.get("actual_dosage"))
        raw_strength = raw_item.get("observed_strength")
        observed_strength = _normalized_strength_text(raw_strength)
        if (
            not name
            or len(name) > 200
            or any(ord(char) < 32 for char in name)
            or dosage is None
            or (raw_strength not in (None, "") and observed_strength is None)
        ):
            raise InvalidMedicationIntakePlan(
                "tool medication item requires a name and explicit actual quantity"
            )
        canonical = _canonical_name(name, aliases)
        raw_key = _normalized_alias(name)
        key = _normalized_alias(canonical)
        if raw_key not in controlled_names and key not in controlled_names:
            raise InvalidMedicationIntakePlan(
                "tool medication item requires a controlled medication name"
            )
        if key in seen and seen[key] != dosage:
            raise InvalidMedicationIntakePlan("conflicting quantities for one medication")
        if key in seen:
            continue
        seen[key] = dosage
        normalized_items.append(
            {
                "medication_name": canonical,
                "actual_dosage": dosage,
                "observed_strength": observed_strength,
            }
        )
    if not normalized_items or len(normalized_items) > _MAX_ITEMS:
        raise InvalidMedicationIntakePlan("medication intake plan has no valid items")

    existing = (
        db.query(WriteIntent)
        .filter(
            WriteIntent.user_id == user_id,
            WriteIntent.kind == WRITE_INTENT_KIND,
            WriteIntent.target_type == "agent_message",
            WriteIntent.target_id == source_message_id,
        )
        .order_by(WriteIntent.id.asc())
        .first()
    )
    if existing is not None:
        _, old_items = _validated_plan(db, existing)
        old_facts = [
            (
                item["medication_name"],
                item["actual_dosage"],
                item.get("observed_strength"),
            )
            for item in old_items
        ]
        new_facts = [
            (
                item["medication_name"],
                item["actual_dosage"],
                item.get("observed_strength"),
            )
            for item in normalized_items
        ]
        if all(fact in old_facts for fact in new_facts):
            return existing
        raise InvalidMedicationIntakePlan(
            "source already has a different medication intake plan"
        )

    user_tz = get_user_timezone(db, user_id)
    local_now = reference_now or get_user_now(db, user_id)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=user_tz)
    else:
        local_now = local_now.astimezone(user_tz)
    payload = _build_payload(
        conversation_id=conversation_id,
        source_message_id=source_message_id,
        source_content=source_message.content,
        local_now=local_now,
        user_tz=user_tz,
        items=normalized_items,
    )
    intent = WriteIntent(
        user_id=user_id,
        kind=WRITE_INTENT_KIND,
        title=f"{len(normalized_items)}项用药记录待确认",
        description=(
            f"确认后将按同一时间点写入{len(normalized_items)}条服药事实；未确认不写入。"
        ),
        status="pending",
        source="agent_medication_tool",
        trust_tier="manual_confirm",
        target_type="agent_message",
        target_id=source_message_id,
        payload=payload,
    )
    db.add(intent)
    try:
        db.commit()
        db.refresh(intent)
        return intent
    except IntegrityError:
        db.rollback()
        # Re-enter through the existing-plan path so a concurrent winner is
        # checked for subset/quantity conflicts and, when explicitly allowed,
        # merged.  Never return a different concurrent plan unchecked.
        return propose_medication_intake_items(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            items=items,
            reference_now=reference_now,
            allow_merge_pending=allow_merge_pending,
        )


def _validated_plan(
    db: Session,
    wi: WriteIntent,
    *,
    require_unexpired: bool = False,
    reference_now: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = wi.payload or {}
    _validate_payload_hash(payload)
    if payload.get("version") != _PLAN_VERSION:
        raise InvalidMedicationIntakePlan("unsupported medication intake plan version")
    if wi.kind != WRITE_INTENT_KIND or wi.target_type != "agent_message":
        raise InvalidMedicationIntakePlan("invalid medication intake write intent binding")
    if payload.get("source_message_id") != wi.target_id:
        raise InvalidMedicationIntakePlan("source message binding mismatch")

    conversation_id = payload.get("conversation_id")
    source = (
        db.query(AgentMessage)
        .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
        .filter(
            AgentMessage.id == wi.target_id,
            AgentMessage.role == "user",
            AgentMessage.conversation_id == conversation_id,
            AgentConversation.user_id == wi.user_id,
        )
        .first()
    )
    if source is None or _source_sha256(source.content) != payload.get("source_sha256"):
        raise InvalidMedicationIntakePlan("source message hash mismatch")

    try:
        date.fromisoformat(str(payload["taken_date"]))
        datetime.strptime(str(payload["taken_time"]), "%H:%M")
        issued_at = _aware_utc(datetime.fromisoformat(str(payload["issued_at"])))
        expires_at = _aware_utc(datetime.fromisoformat(str(payload["expires_at"])))
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidMedicationIntakePlan("invalid frozen intake timestamp") from exc
    if expires_at <= issued_at or expires_at - issued_at != _PLAN_TTL:
        raise InvalidMedicationIntakePlan("invalid medication confirmation window")
    if require_unexpired:
        now = _aware_utc(reference_now or _utc_now())
        if now >= expires_at:
            raise ExpiredMedicationIntakePlan(
                "medication intake confirmation window expired"
            )

    raw_items = payload.get("items")
    if (
        not isinstance(raw_items, list)
        or not raw_items
        or len(raw_items) > _MAX_ITEMS
    ):
        raise InvalidMedicationIntakePlan("medication intake plan must contain at least one item")
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    aliases = _alias_registry()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise InvalidMedicationIntakePlan("invalid medication item")
        name = str(raw_item.get("medication_name") or "").strip()
        dosage = _normalized_quantity_text(raw_item.get("actual_dosage"))
        raw_strength = raw_item.get("observed_strength")
        observed_strength = _normalized_strength_text(raw_strength)
        if (
            not name
            or len(name) > 200
            or any(ord(char) < 32 for char in name)
            or dosage is None
            or (raw_strength not in (None, "") and observed_strength is None)
        ):
            raise InvalidMedicationIntakePlan("invalid medication name or actual dosage")
        canonical = _canonical_name(name, aliases)
        key = _normalized_alias(canonical)
        if not key or key in seen:
            raise InvalidMedicationIntakePlan("duplicate medication in batch")
        seen.add(key)
        items.append({
            "medication_name": canonical,
            "actual_dosage": dosage,
            "observed_strength": observed_strength,
        })
    return payload, items


def validate_medication_intake_intent(
    db: Session,
    wi: WriteIntent,
    *,
    require_unexpired: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate the frozen hash, owner/source binding, timestamp, and items."""
    return _validated_plan(db, wi, require_unexpired=require_unexpired)


def _matching_medications(
    medications: Sequence[Medication],
    canonical_name: str,
    observed_strength: str | None,
    aliases: Mapping[str, str],
) -> list[Medication]:
    target = _canonical_name(canonical_name, aliases)
    name_matches = [
        medication
        for medication in medications
        if _canonical_name(medication.name, aliases) == target
    ]
    if observed_strength is None:
        return name_matches
    return [
        medication
        for medication in name_matches
        if _normalized_strength_text(medication.dosage) == observed_strength
    ]


def _insert_medication_log(db: Session, **kwargs: Any) -> MedicationLog:
    """Small test seam; insertion remains part of the caller's transaction."""
    log = MedicationLog(**kwargs)
    db.add(log)
    db.flush()
    return log


def execute_medication_intake_batch(db: Session, wi: WriteIntent) -> str:
    """Execute a frozen plan atomically and return ``medication_logs:id,...``."""
    payload, items = _validated_plan(db, wi, require_unexpired=True)
    # Serialise all medication-definition decisions for this user.  PostgreSQL
    # honours FOR UPDATE; SQLite unit tests run single-threaded and ignore it.
    owner = (
        db.query(User)
        .filter(User.id == wi.user_id)
        .with_for_update()
        .first()
    )
    if owner is None:
        raise LookupError("write intent owner not found")
    # Waiting for the per-user lock can cross the authorization deadline.  The
    # pre-lock validation is useful for fast rejection, but it cannot be the
    # final time-of-check for a time-limited consent plan.
    payload, items = _validated_plan(db, wi, require_unexpired=True)

    aliases = _alias_registry()
    medications = (
        db.query(Medication)
        .filter(Medication.user_id == wi.user_id)
        .order_by(Medication.id.asc())
        .all()
    )
    taken_date = date.fromisoformat(payload["taken_date"])
    taken_time = payload["taken_time"]
    logs: list[MedicationLog] = []
    for index, item in enumerate(items):
        matches = _matching_medications(
            medications,
            item["medication_name"],
            item.get("observed_strength"),
            aliases,
        )
        if len(matches) > 1:
            raise MedicationIntakeConflict(
                f"multiple medication definitions match item {index + 1}"
            )
        if matches:
            medication = matches[0]
        else:
            medication = Medication(
                user_id=wi.user_id,
                name=item["medication_name"],
                dosage=item.get("observed_strength"),
                frequency=None,
                times_per_day=None,
                start_date=taken_date,
                # One observed dose is not evidence of an ongoing regimen.
                # Immediate safety evaluation includes recent inactive
                # exposures without adding reminders/adherence expectations.
                is_active=False,
            )
            db.add(medication)
            db.flush()
            # SQLAlchemy's scalar default may fill 1 even when the user never
            # supplied a schedule.  Do not turn an observed intake into a
            # prescription claim.
            if medication.times_per_day is not None:
                medication.times_per_day = None
                db.flush()
            medications.append(medication)

        existing = (
            db.query(MedicationLog)
            .filter(
                MedicationLog.user_id == wi.user_id,
                MedicationLog.medication_id == medication.id,
                MedicationLog.taken_date == taken_date,
                MedicationLog.taken_time == taken_time,
            )
            .first()
        )
        if existing is not None:
            if existing.status != "taken" or existing.actual_dosage != item["actual_dosage"]:
                raise MedicationIntakeConflict(
                    f"a different medication fact already exists for item {index + 1}"
                )
            logs.append(existing)
            continue

        try:
            with db.begin_nested():
                log = _insert_medication_log(
                    db,
                    user_id=wi.user_id,
                    medication_id=medication.id,
                    taken_date=taken_date,
                    taken_time=taken_time,
                    status="taken",
                    actual_dosage=item["actual_dosage"],
                    notes=f"write_intent:{WRITE_INTENT_KIND}:{wi.id}:{index}",
                )
            logs.append(log)
        except IntegrityError:
            duplicate = (
                db.query(MedicationLog)
                .filter(
                    MedicationLog.user_id == wi.user_id,
                    MedicationLog.medication_id == medication.id,
                    MedicationLog.taken_date == taken_date,
                    MedicationLog.taken_time == taken_time,
                )
                .first()
            )
            if (
                duplicate is None
                or duplicate.status != "taken"
                or duplicate.actual_dosage != item["actual_dosage"]
            ):
                raise MedicationIntakeConflict(
                    f"concurrent medication fact conflicts for item {index + 1}"
                )
            logs.append(duplicate)

    return "medication_logs:" + ",".join(str(log.id) for log in logs)


def _log_ids(executed_ref: str | None) -> list[int]:
    prefix = "medication_logs:"
    if not executed_ref or not executed_ref.startswith(prefix):
        raise InvalidMedicationIntakePlan("invalid medication batch executed_ref")
    tokens = executed_ref[len(prefix):].split(",")
    if any(not token or not token.isdigit() for token in tokens):
        raise InvalidMedicationIntakePlan("invalid medication batch receipt ids")
    try:
        ids = [int(token) for token in tokens]
    except ValueError as exc:
        raise InvalidMedicationIntakePlan("invalid medication batch receipt ids") from exc
    if not ids or len(ids) != len(set(ids)):
        raise InvalidMedicationIntakePlan("incomplete medication batch receipt ids")
    return ids


def write_receipts_for_intent(db: Session, wi: WriteIntent) -> list[dict[str, Any]]:
    """Return stable, owner-filtered receipts for an already executed plan."""
    _, items = _validated_plan(db, wi, require_unexpired=False)
    ids = _log_ids(wi.executed_ref)
    if len(ids) != len(items):
        raise InvalidMedicationIntakePlan("incomplete medication batch receipt ids")
    rows = (
        db.query(MedicationLog)
        .filter(MedicationLog.user_id == wi.user_id, MedicationLog.id.in_(ids))
        .all()
    )
    by_id = {row.id: row for row in rows}
    if any(log_id not in by_id for log_id in ids):
        raise InvalidMedicationIntakePlan("medication batch receipt target missing")
    receipts: list[dict[str, Any]] = []
    for log_id in ids:
        row = by_id[log_id]
        completed_at = row.created_at.isoformat() if row.created_at else None
        receipts.append(
            {
                "operation_id": f"write_intent:{WRITE_INTENT_KIND}:{wi.id}:{log_id}",
                "status": "verified",
                "resource_type": "medication_log",
                "resource_id": str(log_id),
                "completed_at": completed_at,
                "verified": True,
            }
        )
    return receipts
