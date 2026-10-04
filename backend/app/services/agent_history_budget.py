"""Lossless references for repeated historical answers; never truncate prose.

The soft budget is diagnostic. Unknown, unfinished and nonidentical content is
retained even when it exceeds the budget. Every reference points to an exact
full body in the same history projection, after health-delivery sanitization.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


HISTORY_SOFT_BUDGET_CHARS = 16_000
_MIN_DUPLICATE_CHARS = 1_000


@dataclass(frozen=True)
class HistoryBudgetProjection:
    contents: tuple[str, ...]
    referenced_messages: int
    source_indices: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ProviderHistoryReference:
    source_content: str
    original_content: str
    replacement_content: str


def apply_provider_history_references(
    messages: list[dict], references: Sequence[ProviderHistoryReference],
) -> list[dict]:
    """Apply prepared references only while their full earlier source survives.

    Pi, parsing and consent consumers must use the original messages. Provider
    projections can remove/rewrite history independently, so presence and order
    are checked again here rather than trusting an earlier history window.
    """
    by_original = {reference.original_content: reference for reference in references}
    retained: set[str] = set()
    result: list[dict] = []
    for message in messages:
        content = message.get("content")
        if (
            message.get("role") == "assistant" and isinstance(content, str)
            and set(message) <= {"role", "content"}
        ):
            reference = by_original.get(content)
            if reference is not None and reference.source_content in retained:
                result.append({**message, "content": reference.replacement_content})
                continue
            retained.add(content)
        result.append(message)
    return result


def _completed_non_action_answer(meta: Any) -> bool:
    if not isinstance(meta, dict):
        return False
    outcome = meta.get("turn_outcome")
    if (
        meta.get("client_turn_finalized") is not True
        or meta.get("completion_status") != "complete"
        or meta.get("finish_reason") != "stop"
        or not isinstance(outcome, dict)
        or outcome.get("status") != "complete"
    ):
        return False
    # A finished transport does not prove a task, receipt or UI continuation
    # can be abbreviated. Keep those source messages available verbatim.
    return "garmin_sync_job" not in meta and not any(meta.get(key) for key in (
        "write_receipts", "pending_write_intent_ids", "pending_write_intent_kinds",
        "pending_choice", "read_task", "cards", "recovery_action",
    )) and not any(outcome.get(key) for key in (
        "verified_receipt_count", "dispatch_started", "confirmation_required",
        "actions", "goals",
    ))


def project_history_budget(
    history: Sequence[tuple[Any, Any]],
) -> HistoryBudgetProjection:
    """Preserve order/occurrences, replacing only exact completed-answer copies.

    ``history`` contains (persisted row, policy-sanitized projection) pairs.
    No summary, fuzzy matching, medical classification or user-text reduction
    participates. The latest assistant stays verbatim for follow-up resolution.
    """
    latest_assistant = next(
        (i for i in range(len(history) - 1, -1, -1)
         if history[i][1].role == "assistant"),
        None,
    )
    retained_bodies: dict[str, tuple[int, int]] = {}
    contents: list[str] = []
    references = 0
    source_indices: list[tuple[int, int]] = []
    for index, (row, projection) in enumerate(history):
        body = projection.content
        eligible = (
            projection.role == "assistant"
            and not projection.sanitized
            and len(body) >= _MIN_DUPLICATE_CHARS
            and type(row.id) is int
            and _completed_non_action_answer(projection.meta)
        )
        source = retained_bodies.get(body) if eligible else None
        if source is not None and index != latest_assistant:
            source_id, source_index = source
            body = (
                f"[该条历史助手回复与本上下文中消息编号：{source_id}的正文完全相同；"
                "请读取该消息保留的完整原文。本条仍是独立的历史回复，"
                "不代表再次执行、当前核验、医嘱或新的读写授权。]"
            )
            references += 1
            source_indices.append((index, source_index))
        elif eligible:
            retained_bodies.setdefault(body, (row.id, index))
        contents.append(body)
    return HistoryBudgetProjection(tuple(contents), references, tuple(source_indices))
