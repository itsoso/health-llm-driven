"""KB V2 evidence metadata for generated notification surfaces."""

from __future__ import annotations

from typing import Any, Iterable


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
