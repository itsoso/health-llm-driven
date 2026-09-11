"""Pure offline aggregation of anonymous, explicitly correlated task snapshots.

This module neither queries production nor judges health advice. Human outcomes
and reviewed tool blocks must be supplied by an independent evaluation process.
Each input row is one attempt snapshot, not an arbitrary telemetry event.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import math
import re
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "agent-task-evaluation.v1"
P95_MIN_SAMPLES = 20
TASK_TYPES = frozenset({
    "simple_query", "simple_record", "complex_analysis", "supplement_record",
    "medication_record", "diet_record", "diet_photo", "generic", "clarification",
    "other",
})
TECHNICAL_STATUSES = (
    "succeeded", "failed", "waiting_for_user", "cancelled", "queued", "running",
    "reconciliation_required", "unknown",
)
# Explicit upstream resolution metadata, never inferred from a successful run,
# a tool block, or clinical text. Appropriate refusal requires upstream review.
RESOLUTION_STATUSES = (
    "completed", "no_data", "appropriate_refusal", "blocked",
    "pending_confirmation", "unknown",
)
OUTCOMES = ("satisfied", "failed", "unknown")
LATENCY_FIELDS = (
    "task_elapsed_ms", "verified_content_latency_ms", "confirmation_wait_ms",
    "first_key_content_latency_ms",
)
TOOL_FIELDS = ("tool_failures", "reviewed_appropriate_blocks", "unreviewed_blocks")
_ALLOWED_FIELDS = frozenset({
    "scope_id", "attempt_id", "logical_task_id", "revision", "task_type",
    "attempt_index", "technical_status", "resolution_status", "human_verified", "task_outcome",
    "cost_cny", "cost_source", *LATENCY_FIELDS, *TOOL_FIELDS,
})
_OPAQUE_ID = re.compile(r"[a-f0-9]{64}\Z")
_REVISION = re.compile(r"[a-f0-9]{40}\Z")


def _number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        # JSON integers may exceed float range; reject them as invalid data.
        return False


def _validate(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    # Error messages never reflect rejected values or unknown field names.
    def reject() -> None:
        raise ValueError(f"row {index}: invalid or unsupported metadata")

    if not isinstance(raw, Mapping) or set(raw) - _ALLOWED_FIELDS:
        reject()
    row = dict(raw)
    for key in ("scope_id", "attempt_id"):
        if not isinstance(row.get(key), str) or not _OPAQUE_ID.fullmatch(row[key]):
            reject()
    logical = row.setdefault("logical_task_id", None)
    if logical is not None and (
        not isinstance(logical, str) or not _OPAQUE_ID.fullmatch(logical)
    ):
        reject()
    revision = row.get("revision")
    if not isinstance(revision, str) or not (
        revision == "unknown" or _REVISION.fullmatch(revision)
    ):
        reject()
    if not isinstance(row.get("task_type"), str) or row["task_type"] not in TASK_TYPES:
        reject()
    attempt = row.get("attempt_index")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        reject()
    if row.setdefault("technical_status", "unknown") not in TECHNICAL_STATUSES:
        reject()
    if row.setdefault("resolution_status", "unknown") not in RESOLUTION_STATUSES:
        reject()
    if not isinstance(row.setdefault("human_verified", False), bool):
        reject()
    outcome = row.setdefault("task_outcome", "unknown")
    if outcome not in OUTCOMES or (outcome != "unknown" and not row["human_verified"]):
        reject()
    for key in LATENCY_FIELDS:
        value = row.setdefault(key, None)
        if value is not None and not _number(value):
            reject()
    for key in TOOL_FIELDS:
        value = row.setdefault(key, None)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            reject()
    cost = row.setdefault("cost_cny", None)
    source = row.setdefault("cost_source", "missing")
    if cost is None:
        if source != "missing":
            reject()
    elif not _number(cost) or source not in ("priced_usage", "estimate"):
        reject()
    return row


def _percentile(values: list[float], percentile: float) -> float:
    position = (len(values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 2)


def _latency(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = sorted(row[field] for row in rows if row[field] is not None)
    return {
        "sample_count": len(values),
        "missing_count": len(rows) - len(values),
        "p50_ms": _percentile(values, 0.5) if values else None,
        "p95_ms": _percentile(values, 0.95) if len(values) >= P95_MIN_SAMPLES else None,
        "p95_status": "available" if len(values) >= P95_MIN_SAMPLES else "insufficient_samples",
    }


def _group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tasks: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        # Namespace absent logical IDs so they cannot collide with a real ID.
        key = (row["scope_id"], "logical" if row["logical_task_id"] else "attempt",
               row["logical_task_id"] or row["attempt_id"])
        tasks[key].append(row)
    finals = []
    for attempts in tasks.values():
        indices = [row["attempt_index"] for row in attempts]
        if len(indices) != len(set(indices)):
            raise ValueError("ambiguous attempt ordering within a logical task")
        finals.append(max(attempts, key=lambda row: row["attempt_index"]))
    states = Counter(row["technical_status"] for row in finals)
    resolutions = Counter(row["resolution_status"] for row in finals)
    outcomes = Counter(row["task_outcome"] for row in finals)
    verified = outcomes["satisfied"] + outcomes["failed"]
    known_cost = [row for row in rows if row["cost_cny"] is not None]
    subtotal = float(sum((Decimal(str(row["cost_cny"])) for row in known_cost), Decimal(0)))
    if not math.isfinite(subtotal):
        raise ValueError("cost aggregate exceeds the supported numeric range")
    subtotal = round(subtotal, 2)
    return {
        "revision": rows[0]["revision"],
        "task_type": rows[0]["task_type"],
        "task_count": len(finals),
        "attempt_count": len(rows),
        "unlinked_attempt_count": sum(row["logical_task_id"] is None for row in rows),
        "technical_statuses": {state: states[state] for state in TECHNICAL_STATUSES},
        "resolution_statuses": {state: resolutions[state] for state in RESOLUTION_STATUSES},
        "task_outcomes": {outcome: outcomes[outcome] for outcome in OUTCOMES},
        "verified_task_count": verified,
        "verified_satisfaction_rate": round(outcomes["satisfied"] / verified, 2) if verified else None,
        "outcome_review_coverage": round(verified / len(finals), 2),
        "technical_success_but_verified_failure": sum(
            row["technical_status"] == "succeeded" and row["task_outcome"] == "failed"
            for row in finals
        ),
        "tool_events": {
            key: sum(row[key] for row in rows if row[key] is not None)
            if any(row[key] is not None for row in rows) else None
            for key in TOOL_FIELDS
        },
        "tool_event_coverage": {
            key: {
                "observed_attempt_count": sum(row[key] is not None for row in rows),
                "missing_attempt_count": sum(row[key] is None for row in rows),
            }
            for key in TOOL_FIELDS
        },
        # These are explicit task measurements on the final attempt. Retry
        # durations or progress paints cannot manufacture end-to-end latency.
        "latency": {key: _latency(finals, key) for key in LATENCY_FIELDS},
        "cost": {
            "currency": "CNY",
            "known_subtotal_cny": subtotal if known_cost else None,
            "total_cny": subtotal if len(known_cost) == len(rows) else None,
            "known_attempt_count": len(known_cost),
            "missing_attempt_count": len(rows) - len(known_cost),
            "coverage": round(len(known_cost) / len(rows), 2),
            "sources": dict(sorted(Counter(row["cost_source"] for row in rows).items())),
        },
    }


def evaluate_tasks(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate strict anonymous snapshots, without inferring clinical quality.

    IDs must be opaque 64-character hex pseudonyms produced by the exporter;
    never pass a user ID, conversation body, clinical value, or credential.
    A logical task's latest explicit attempt supplies its technical state and
    human verdict. Revisions and task types are separate reporting boundaries.
    """
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates = 0
    for index, raw in enumerate(records, 1):
        row = _validate(raw, index)
        key = (row["scope_id"], row["attempt_id"])
        if key in unique:
            if unique[key] != row:
                raise ValueError(f"row {index}: conflicting attempt snapshot")
            duplicates += 1
        else:
            unique[key] = row
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    task_types: dict[tuple[str, str, str], str] = {}
    for row in unique.values():
        if row["logical_task_id"]:
            task_key = (row["scope_id"], row["revision"], row["logical_task_id"])
            if task_key in task_types and task_types[task_key] != row["task_type"]:
                raise ValueError("inconsistent task type within a logical task")
            task_types[task_key] = row["task_type"]
        grouped[(row["revision"], row["task_type"])].append(row)
    groups = [_group(grouped[key]) for key in sorted(grouped)]
    return {
        "schema_version": SCHEMA_VERSION,
        "p95_min_samples": P95_MIN_SAMPLES,
        "attempt_count": len(unique),
        "duplicate_snapshot_count": duplicates,
        "revision_scoped_task_count": sum(group["task_count"] for group in groups),
        "groups": groups,
        "limitations": [
            "Offline metadata only; no production connection or clinical adjudication.",
            "Only matching owner, revision, task type and logical task ID merge attempts.",
            "Missing logical IDs stay separate; event streams need an upstream correlation step.",
            "Latest attempt supplies task verdict; technical success never implies satisfaction.",
            "Resolution statuses are explicit upstream metadata, not inferred clinical outcomes; missing stays unknown.",
            "Tool counts are events across attempts, not disjoint task outcomes.",
            "Costs are known subtotals unless every attempt has priced or estimated cost.",
            "Percentiles describe the observed sample; the minimum sample policy is not a confidence interval.",
        ],
    }
