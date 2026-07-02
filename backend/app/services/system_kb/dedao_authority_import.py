"""Dry-run import checks for dedao-kbase Health Authority Pack JSONL."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HEALTH_AUTHORITY_PACK_CONTRACT = "health_authority_pack_v1"
HEALTH_AUTHORITY_TARGET_SYSTEM = "health-llm-driven"
HEALTH_AUTHORITY_GATE_ARTIFACT_SCHEMA = "dedao_authority_pull_gate_v1"
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


@dataclass(frozen=True)
class DedaoAuthorityPullReport:
    status: str
    source_url: str
    http_status: int | None
    import_report: DedaoAuthorityImportReport
    error: str = ""
    source_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_url": self.source_url,
            "http_status": self.http_status,
            "error": self.error,
            "source_sha256": self.source_sha256,
            "import_report": self.import_report.to_dict(),
        }


@dataclass(frozen=True)
class DedaoAuthorityPullGate:
    status: str
    reasons: list[str]
    fail_count: int
    warn_count: int
    pull_report: DedaoAuthorityPullReport

    def to_redacted_dict(self, *, generated_at: str = "") -> dict[str, Any]:
        import_report = self.pull_report.import_report
        return {
            "artifact_schema": HEALTH_AUTHORITY_GATE_ARTIFACT_SCHEMA,
            "generated_at": generated_at,
            "status": self.status,
            "reasons": list(self.reasons),
            "fail_count": self.fail_count,
            "warn_count": self.warn_count,
            "pull": {
                "status": self.pull_report.status,
                "source_url": self.pull_report.source_url,
                "http_status": self.pull_report.http_status,
                "error": self.pull_report.error,
                "source_sha256": self.pull_report.source_sha256,
            },
            "counts": {
                "total": import_report.total,
                "accepted_for_review": len(import_report.accepted_for_review),
                "blocked": len(import_report.blocked),
                "duplicates": len(import_report.duplicates),
                "invalid": len(import_report.invalid),
                "missing_source_refs": len(import_report.missing_source_refs),
            },
            "issues": {
                "blocked": _issue_refs(import_report.blocked),
                "duplicates": _issue_refs(import_report.duplicates),
                "invalid": _issue_refs(import_report.invalid),
                "missing_source_refs": _issue_refs(import_report.missing_source_refs),
            },
            "would_write": import_report.would_write,
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


def build_dedao_authority_pack_export_url(base_url: str, limit: int = 25) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        return ""
    query = urlencode({"format": "jsonl", "limit": str(max(1, int(limit or 25)))})
    return f"{normalized}/api/projects/health/authority-pack/export?{query}"


def fetch_dedao_authority_pack_jsonl(
    base_url: str,
    token: str,
    *,
    limit: int = 25,
    timeout: float = 15,
    opener: Any | None = None,
) -> tuple[str, str, int]:
    source_url = build_dedao_authority_pack_export_url(base_url, limit)
    if not source_url:
        raise ValueError("missing_base_url")
    token = str(token or "").strip()
    if not token:
        raise ValueError("missing_token")
    request = Request(
        source_url,
        headers={
            "Accept": "application/x-ndjson",
            "Authorization": f"Bearer {token}",
        },
    )
    open_fn = opener or urlopen
    with open_fn(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 200) or 200)
        body = response.read().decode("utf-8")
    return source_url, body, status


def dry_run_import_dedao_authority_pack_from_kbase(
    base_url: str,
    token: str,
    *,
    limit: int = 25,
    timeout: float = 15,
    opener: Any | None = None,
) -> DedaoAuthorityPullReport:
    source_url = build_dedao_authority_pack_export_url(base_url, limit)
    try:
        source_url, body, http_status = fetch_dedao_authority_pack_jsonl(
            base_url,
            token,
            limit=limit,
            timeout=timeout,
            opener=opener,
        )
    except ValueError as exc:
        return DedaoAuthorityPullReport(
            status="fetch_failed",
            source_url=source_url,
            http_status=None,
            error=str(exc),
            import_report=_empty_import_report(),
        )
    except HTTPError as exc:
        return DedaoAuthorityPullReport(
            status="fetch_failed",
            source_url=source_url,
            http_status=int(exc.code),
            error=f"http_{int(exc.code)}",
            import_report=_empty_import_report(),
        )
    except URLError:
        return DedaoAuthorityPullReport(
            status="fetch_failed",
            source_url=source_url,
            http_status=None,
            error="network_error",
            import_report=_empty_import_report(),
        )

    import_report = dry_run_import_dedao_authority_pack(body.splitlines())
    return DedaoAuthorityPullReport(
        status="ok",
        source_url=source_url,
        http_status=http_status,
        import_report=import_report,
        source_sha256=sha256(body.encode("utf-8")).hexdigest(),
    )


def evaluate_dedao_authority_pull_gate(report: DedaoAuthorityPullReport) -> DedaoAuthorityPullGate:
    import_report = report.import_report
    fail_reasons: list[str] = []
    warn_reasons: list[str] = []

    if report.status != "ok":
        fail_reasons.append("fetch_failed")
    else:
        if import_report.invalid:
            fail_reasons.append("invalid_records")
        if not import_report.accepted_for_review:
            fail_reasons.append("no_accepted_candidates")
        if import_report.blocked:
            warn_reasons.append("blocked_records")
        if import_report.duplicates:
            warn_reasons.append("duplicate_records")
        if import_report.missing_source_refs:
            warn_reasons.append("missing_source_refs")

    if fail_reasons:
        status = "fail"
    elif warn_reasons:
        status = "warn"
    else:
        status = "pass"

    return DedaoAuthorityPullGate(
        status=status,
        reasons=fail_reasons + warn_reasons,
        fail_count=len(fail_reasons),
        warn_count=len(warn_reasons),
        pull_report=report,
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


def _issue_refs(items: list[DedaoAuthorityImportItem]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": item.claim_id,
            "reason": item.reason,
            "line_no": item.line_no,
        }
        for item in items
    ]


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


def _empty_import_report() -> DedaoAuthorityImportReport:
    return DedaoAuthorityImportReport(
        total=0,
        accepted_for_review=[],
        blocked=[],
        duplicates=[],
        invalid=[],
        missing_source_refs=[],
        would_write=False,
    )
