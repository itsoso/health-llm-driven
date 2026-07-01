"""Dry-run import checks for dedao-kbase Health Authority Pack JSONL."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable


HEALTH_AUTHORITY_PACK_CONTRACT = "health_authority_pack_v1"
HEALTH_AUTHORITY_TARGET_SYSTEM = "health-llm-driven"
REQUIRED_BLOCKED_USES = {
    "diagnosis",
    "treatment",
    "dosage",
    "medication_change",
    "emergency_guidance",
}
ACTION_SUPPORT_USES = REQUIRED_BLOCKED_USES | {
    "action_support",
    "treatment_plan",
    "medication_instruction",
}
MEDICAL_ACTION_TERMS = (
    "用药",
    "剂量",
    "药物",
    "处方",
    "治疗",
    "诊断",
    "急救",
    "急症",
    "medication",
    "medicine",
    "dose",
    "dosage",
    "treatment",
    "diagnosis",
    "emergency",
)


@dataclass(frozen=True)
class DedaoAuthorityImportItem:
    claim_id: str
    reason: str
    line_no: int
    record: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DedaoAuthorityReviewCandidate:
    claim_id: str
    title: str
    summary: str
    source_hash: str
    citations: list[str]
    allowed_uses: list[str]
    blocked_uses: list[str]
    review_status: str
    risk_reason: str
    entity_candidates: list[str]
    record: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DedaoAuthorityImportReport:
    total: int
    accepted_for_review: list[DedaoAuthorityReviewCandidate]
    blocked: list[DedaoAuthorityImportItem]
    duplicates: list[DedaoAuthorityImportItem]
    invalid: list[DedaoAuthorityImportItem]
    missing_source_refs: list[DedaoAuthorityImportItem]
    would_write: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "accepted_for_review": [candidate.__dict__ for candidate in self.accepted_for_review],
            "blocked": [item.__dict__ for item in self.blocked],
            "duplicates": [item.__dict__ for item in self.duplicates],
            "invalid": [item.__dict__ for item in self.invalid],
            "missing_source_refs": [item.__dict__ for item in self.missing_source_refs],
            "would_write": self.would_write,
        }


def dry_run_import_dedao_authority_pack(lines: Iterable[str]) -> DedaoAuthorityImportReport:
    """Validate Health Authority Pack JSONL without writing System KB rows."""

    accepted: list[DedaoAuthorityReviewCandidate] = []
    blocked: list[DedaoAuthorityImportItem] = []
    duplicates: list[DedaoAuthorityImportItem] = []
    invalid: list[DedaoAuthorityImportItem] = []
    missing_source_refs: list[DedaoAuthorityImportItem] = []
    seen_claim_ids: set[str] = set()
    total = 0

    for line_no, raw_line in enumerate(lines, start=1):
        if not str(raw_line).strip():
            continue
        total += 1
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            invalid.append(_issue("", "invalid_json", line_no, {"raw": raw_line}))
            continue
        if not isinstance(record, dict):
            invalid.append(_issue("", "invalid_record", line_no, {"raw": record}))
            continue

        claim_id = _string(record.get("claim_id"))
        reason = _invalid_reason(record)
        if reason:
            invalid.append(_issue(claim_id, reason, line_no, record))
            continue
        if claim_id in seen_claim_ids:
            duplicates.append(_issue(claim_id, "duplicate_claim_id", line_no, record))
            continue
        seen_claim_ids.add(claim_id)

        if _missing_source_refs(record):
            missing_source_refs.append(_issue(claim_id, "missing_source_refs", line_no, record))
            continue
        if _review_status(record) == "blocked":
            blocked.append(_issue(claim_id, "blocked_review_status", line_no, record))
            continue
        if _is_medical_action_claim(record):
            blocked.append(_issue(claim_id, "medical_action_claim", line_no, record))
            continue

        accepted.append(_review_candidate(record))

    return DedaoAuthorityImportReport(
        total=total,
        accepted_for_review=accepted,
        blocked=blocked,
        duplicates=duplicates,
        invalid=invalid,
        missing_source_refs=missing_source_refs,
        would_write=False,
    )


def _invalid_reason(record: dict[str, Any]) -> str:
    if record.get("consumer_contract") != HEALTH_AUTHORITY_PACK_CONTRACT:
        return "unknown_contract"
    if record.get("target_system") != HEALTH_AUTHORITY_TARGET_SYSTEM:
        return "unsupported_target_system"
    if not _string(record.get("claim_id")):
        return "missing_claim_id"
    if not _record_book_id(record):
        return "missing_book_id"
    return ""


def _missing_source_refs(record: dict[str, Any]) -> bool:
    return not _record_source_hash(record) or not _record_citations(record)


def _is_medical_action_claim(record: dict[str, Any]) -> bool:
    candidate_type = _string(record.get("candidate_type"))
    allowed_uses = set(_string_list(record.get("allowed_uses")))
    blocked_uses = set(_string_list(record.get("blocked_uses")))
    text = f"{record.get('title', '')} {record.get('summary', '')}".lower()
    has_medical_action_term = any(term.lower() in text for term in MEDICAL_ACTION_TERMS)
    requests_action_support = candidate_type == "action_support_candidate" or bool(allowed_uses & ACTION_SUPPORT_USES)
    missing_required_blocks = not REQUIRED_BLOCKED_USES.issubset(blocked_uses)
    return requests_action_support or (has_medical_action_term and missing_required_blocks)


def _review_candidate(record: dict[str, Any]) -> DedaoAuthorityReviewCandidate:
    return DedaoAuthorityReviewCandidate(
        claim_id=_string(record.get("claim_id")),
        title=_string(record.get("title")),
        summary=_string(record.get("summary")),
        source_hash=_record_source_hash(record),
        citations=_record_citations(record),
        allowed_uses=_string_list(record.get("allowed_uses")),
        blocked_uses=_string_list(record.get("blocked_uses")),
        review_status=_review_status(record),
        risk_reason=_string(record.get("risk_reason")),
        entity_candidates=_string_list(record.get("entity_candidates")),
        record=dict(record),
    )


def _issue(claim_id: str, reason: str, line_no: int, record: dict[str, Any]) -> DedaoAuthorityImportItem:
    return DedaoAuthorityImportItem(
        claim_id=claim_id,
        reason=reason,
        line_no=line_no,
        record=dict(record),
    )


def _string(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _source_refs(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source_refs")
    return value if isinstance(value, dict) else {}


def _record_book_id(record: dict[str, Any]) -> str:
    return _string(record.get("book_id")) or _string(_source_refs(record).get("book_id"))


def _record_source_hash(record: dict[str, Any]) -> str:
    return _string(record.get("source_hash")) or _string(_source_refs(record).get("source_hash"))


def _record_citations(record: dict[str, Any]) -> list[str]:
    return _string_list(record.get("citations")) or _string_list(_source_refs(record).get("citations"))


def _review_status(record: dict[str, Any]) -> str:
    return _string(record.get("review_status")) or "needs_review"
