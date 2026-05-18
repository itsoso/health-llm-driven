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
    ) -> EvidenceResolution:
        from app.services.system_knowledge_service import (
            lookup_for_twin,
            _select_claim_refs_for_specialist,
        )

        result = lookup_for_twin(self.db, twin)
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
    ) -> dict[str, int]:
        from app.services.system_knowledge_service import _dedupe_preserve_order

        updated = 0
        claim_refs = 0
        for finding in findings:
            resolution = self.resolve_for_finding(
                twin,
                finding,
                max_refs=max_refs_per_finding,
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
