"""Unified system-KB evidence resolver.

This module is the single place that translates a candidate health suggestion
plus a compact Twin payload into claim-backed evidence metadata. Specialist
code, planner code, push generation, and mobile card surfaces should converge
here instead of each inventing separate `evidence_refs` logic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class EvidenceResolution:
    evidence_refs: list[str]
    support_status: str
    unsupported: bool
    unsupported_reason: str | None
    matched_claim_count: int
    resolver: str = "system_kb_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceResolver:
    """Resolve reviewed system-KB claim refs for structured suggestions."""

    def __init__(self, db: Session):
        self.db = db

    def resolve_for_finding(
        self,
        twin: dict[str, Any],
        finding: Any,
        *,
        max_refs: int = 3,
        lookup_result: dict[str, Any] | None = None,
    ) -> EvidenceResolution:
        if _finding_is_evidence_not_applicable(finding):
            return EvidenceResolution(
                evidence_refs=[],
                support_status="not_applicable",
                unsupported=False,
                unsupported_reason=None,
                matched_claim_count=0,
            )

        from app.services.system_knowledge_service import (
            lookup_for_twin,
            _select_claim_refs_for_specialist,
        )

        result = (
            lookup_for_twin(self.db, twin)
            if lookup_result is None
            else lookup_result
        )
        claims = result.get("claims") or []
        refs = _select_claim_refs_for_specialist(finding, claims, max_refs)
        if refs:
            return EvidenceResolution(
                evidence_refs=refs,
                support_status="supported",
                unsupported=False,
                unsupported_reason=None,
                matched_claim_count=len(claims),
            )
        return EvidenceResolution(
            evidence_refs=[],
            support_status="model_inference",
            unsupported=True,
            unsupported_reason="missing_system_kb_evidence_refs",
            matched_claim_count=len(claims),
        )

    def apply_to_findings(
        self,
        twin: dict[str, Any],
        findings: list[Any],
        *,
        max_refs_per_finding: int = 3,
        lookup_result: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        from app.services.system_knowledge_service import _dedupe_preserve_order

        updated = 0
        claim_refs = 0
        batch_lookup_result = lookup_result
        for finding in findings:
            if (
                batch_lookup_result is None
                and not _finding_is_evidence_not_applicable(finding)
            ):
                from app.services.system_knowledge_service import lookup_for_twin

                batch_lookup_result = lookup_for_twin(self.db, twin)
            resolution = self.resolve_for_finding(
                twin,
                finding,
                max_refs=max_refs_per_finding,
                lookup_result=batch_lookup_result,
            )
            claim_refs = max(claim_refs, resolution.matched_claim_count)
            raw = getattr(finding, "raw", None)
            if isinstance(raw, dict):
                raw["evidence_resolution"] = resolution.to_dict()
                raw["support_status"] = resolution.support_status
                raw["unsupported"] = resolution.unsupported
                raw["unsupported_reason"] = resolution.unsupported_reason
            if not resolution.evidence_refs:
                continue

            existing_refs = list(getattr(finding, "evidence_refs", []) or [])
            merged_refs = _dedupe_preserve_order(existing_refs + resolution.evidence_refs)
            try:
                finding.evidence_refs = merged_refs
            except Exception:  # noqa: BLE001
                pass
            if isinstance(raw, dict):
                raw["system_kb_evidence_refs"] = merged_refs
            for item in getattr(finding, "findings", []) or []:
                if isinstance(item, dict) and not item.get("evidence_refs"):
                    item["evidence_refs"] = resolution.evidence_refs
            updated += 1

        return {"findings_updated": updated, "claim_refs": claim_refs}


_NON_ADVICE_ITEM_TYPES = {
    "record",
    "logged",
    "log",
    "data_gap",
    "data_summary",
    "summary",
    "trend_report",
    "prediction_verified",
}
_NON_ADVICE_OPERATIONS = {
    "record",
    "record_meal",
    "log_meal",
    "create_record",
    "update_record",
    "delete_record",
    "data_summary",
}


def _finding_is_evidence_not_applicable(finding: Any) -> bool:
    """Return true for CRUD/data-summary findings that are not advice claims.

    These surfaces still need audit metadata, but counting them as
    `unsupported` would distort KB coverage and make record-confirmation turns
    look like medical advice without evidence.
    """

    raw = getattr(finding, "raw", None)
    if isinstance(raw, dict):
        operation = str(raw.get("operation") or raw.get("intent") or raw.get("type") or "").lower()
        if operation in _NON_ADVICE_OPERATIONS:
            return True
        if raw.get("data_summary") is True:
            return True
        if raw.get("data_gap") is True:
            return True

    items = getattr(finding, "findings", None) or []
    if not items:
        return False
    item_types = {
        str(item.get("type") or "").lower()
        for item in items
        if isinstance(item, dict) and item.get("type")
    }
    if item_types and item_types.issubset(_NON_ADVICE_ITEM_TYPES):
        return True

    text = f"{getattr(finding, 'summary', '')} {getattr(finding, 'category', '')}".lower()
    if any(
        token in text
        for token in ("已记录", "已删除", "已更新", "记录完成", "数据暂缺", "数据不足")
    ):
        return True

    return False
