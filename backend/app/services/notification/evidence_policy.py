"""KB V2 evidence metadata for generated notification surfaces."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session


NOTIFICATION_CLAIM_BOUNDARY = (
    "该通知用于健康管理提醒和数据复盘，不替代医生诊断、治疗或用药建议。"
)

DATA_SUMMARY_TYPES = {"trend_report", "morning_briefing", "prediction_verified"}


def _normalize_refs(refs: Iterable[Any] | None) -> list[str]:
    if not refs:
        return []
    return [str(ref) for ref in refs if ref]


def build_notification_evidence_data(
    *,
    notification_type: str,
    source: str,
    existing_data: dict[str, Any] | None = None,
    evidence_refs: Iterable[Any] | None = None,
    evidence_domain: str | None = None,
    support_status: str | None = None,
) -> dict[str, Any]:
    """Merge notification payload data with KB V2 evidence contract fields."""
    refs = _normalize_refs(evidence_refs)
    data: dict[str, Any] = dict(existing_data or {})

    if support_status:
        status = support_status
    elif refs:
        status = "supported"
    elif notification_type in DATA_SUMMARY_TYPES:
        status = "data_summary"
    else:
        status = "model_inference"

    unsupported = status == "model_inference" and not refs
    kept_reason = (
        "supported"
        if refs
        else "data_summary"
        if status == "data_summary"
        else "push_metadata_only"
    )

    data.update(
        {
            "notification_evidence_source": source,
            "evidence_refs": refs,
            "evidence_ref_count": len(refs),
            "support_status": status,
            "unsupported": unsupported,
            "unsupported_reason": (
                "missing_system_kb_evidence_refs" if unsupported else None
            ),
            "planner_evidence_policy": {
                "blocked": False,
                "kept_reason": kept_reason,
            },
            "claim_boundary": NOTIFICATION_CLAIM_BOUNDARY,
        }
    )
    if evidence_domain:
        data["evidence_domain"] = evidence_domain
    return data


def build_notification_evidence_data_for_user(
    db: Session,
    *,
    user_id: int,
    notification_type: str,
    source: str,
    existing_data: dict[str, Any] | None = None,
    evidence_refs: Iterable[Any] | None = None,
    evidence_domain: str | None = None,
    support_status: str | None = None,
    max_refs: int = 3,
) -> dict[str, Any]:
    """Build notification evidence metadata and auto-fill KB refs from Twin.

    Generated advice surfaces should not stay `model_inference` when the user
    Twin already matches reviewed system-KB claims. This helper keeps the old
    explicit-ref behavior, but adds a conservative Twin lookup for actionable
    notification types.
    """

    refs = _normalize_refs(evidence_refs)
    if not refs and not support_status and notification_type not in DATA_SUMMARY_TYPES:
        try:
            from app.services.system_knowledge_service import (
                lookup_for_twin,
                system_kb_twin_payload_from_health_twin,
            )
            from app.twin.builder import build_twin

            twin = build_twin(db, user_id, use_cache=True)
            payload = system_kb_twin_payload_from_health_twin(twin)
            result = lookup_for_twin(db, payload)
            refs = [
                claim["doc_id"]
                for claim in result.get("claims", [])[:max_refs]
                if claim.get("doc_id")
            ]
        except Exception:
            refs = []

    return build_notification_evidence_data(
        notification_type=notification_type,
        source=source,
        existing_data=existing_data,
        evidence_refs=refs,
        evidence_domain=evidence_domain,
        support_status=support_status,
    )
