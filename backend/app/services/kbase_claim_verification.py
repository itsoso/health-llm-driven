"""Deterministic verification packets for claims awaiting KBase review."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from typing import Any, Callable


VERIFICATION_PACKET_CONTRACT = "kbase_claim_verification_packet_v1"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_STALE_AFTER = timedelta(days=730)
_MODEL_DECISIONS = frozenset({"approve", "needs_evidence", "reject", "background_only"})
_MODEL_REQUIRED_FIELDS = frozenset(
    {"decision", "confidence", "rationale", "citation_ids", "missing_evidence"}
)


def claim_content_hash(claim: dict[str, Any]) -> str:
    """Hash review-relevant claim content without workspace-only state."""
    metadata = claim.get("metadata") if isinstance(claim.get("metadata"), dict) else {}
    payload = {
        "doc_id": str(claim.get("doc_id") or ""),
        "title": str(claim.get("title") or ""),
        "summary": str(claim.get("summary") or claim.get("body") or ""),
        "evidence_level": claim.get("evidence_level"),
        "confidence": claim.get("confidence"),
        "sources": sorted(str(item) for item in claim.get("sources") or [] if str(item).strip()),
        "citation_ids": sorted(
            str(item) for item in metadata.get("citation_ids") or [] if str(item).strip()
        ),
        "external_sources": metadata.get("external_sources") or [],
        "last_confirmed": metadata.get("last_confirmed"),
        "contradiction_ids": sorted(
            str(item) for item in metadata.get("contradiction_ids") or [] if str(item).strip()
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_deterministic_verification_packet(
    claim: dict[str, Any],
    *,
    workspace_fingerprint: str,
    peer_claims: list[dict[str, Any]] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a fail-closed, non-mutating review recommendation."""
    if not _SHA256_PATTERN.fullmatch(workspace_fingerprint):
        raise ValueError("workspace fingerprint must be a lowercase SHA-256 digest")
    doc_id = str(claim.get("doc_id") or "").strip()
    if not doc_id:
        raise ValueError("claim doc_id is required")

    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    metadata = claim.get("metadata") if isinstance(claim.get("metadata"), dict) else {}
    sources = sorted(str(item) for item in claim.get("sources") or [] if str(item).strip())
    external_sources = [
        item
        for item in metadata.get("external_sources") or []
        if isinstance(item, dict) and str(item.get("source") or "").strip()
    ]
    duplicates = _duplicate_claim_ids(claim, peer_claims or [])
    contradictions = sorted(
        str(item) for item in metadata.get("contradiction_ids") or [] if str(item).strip()
    )

    missing_evidence: list[str] = []
    blocking_reasons: list[str] = []
    checks: list[dict[str, str]] = []

    if sources:
        checks.append(_check("source_completeness", "pass", "Claim has source references."))
    else:
        checks.append(_check("source_completeness", "block", "Claim has no source references."))
        blocking_reasons.append("missing_source_references")

    evidence_level = str(claim.get("evidence_level") or "").upper()
    if external_sources:
        checks.append(_check("external_evidence", "pass", "Independent external evidence is attached."))
    elif evidence_level in {"C", "D", ""}:
        checks.append(_check("external_evidence", "warn", "Independent external evidence is missing."))
        missing_evidence.append("independent_external_source")
    else:
        checks.append(_check("external_evidence", "pass", "Evidence level does not require an extra source."))

    freshness_status, freshness_message = _freshness_check(metadata.get("last_confirmed"), now)
    checks.append(_check("freshness", freshness_status, freshness_message))
    if freshness_status == "warn":
        missing_evidence.append("fresh_external_source")

    if duplicates:
        checks.append(_check("duplicate", "block", "Equivalent claim already exists."))
        blocking_reasons.append("duplicate_claim")
    else:
        checks.append(_check("duplicate", "pass", "No equivalent claim was found."))

    if contradictions:
        checks.append(_check("contradiction", "block", "Claim has unresolved contradictions."))
        blocking_reasons.append("claim_contradiction")
    else:
        checks.append(_check("contradiction", "pass", "No explicit contradiction is recorded."))

    proposed_decision = "approve"
    if "missing_source_references" in blocking_reasons:
        proposed_decision = "reject"
    elif "duplicate_claim" in blocking_reasons:
        proposed_decision = "background_only"
    elif blocking_reasons or missing_evidence:
        proposed_decision = "needs_evidence"

    return {
        "contract": VERIFICATION_PACKET_CONTRACT,
        "packet_id": _packet_id(doc_id, workspace_fingerprint, claim_content_hash(claim)),
        "doc_id": doc_id,
        "workspace_fingerprint": workspace_fingerprint,
        "claim_content_hash": claim_content_hash(claim),
        "status": "blocked" if blocking_reasons else "ready",
        "proposed_decision": proposed_decision,
        "confidence": 1.0,
        "rationale": _rationale(proposed_decision),
        "checks": checks,
        "blocking_reasons": blocking_reasons,
        "missing_evidence": list(dict.fromkeys(missing_evidence)),
        "citation_ids": sources,
        "related_claim_ids": sorted(set(duplicates + contradictions)),
        "generator": "deterministic:kbase-claim-verification-v1",
        "generated_at": now.astimezone(UTC).isoformat(),
    }


def enrich_verification_packet_with_model(
    packet: dict[str, Any],
    *,
    claim: dict[str, Any],
    model_adapter: Callable[[dict[str, Any]], dict[str, Any] | str],
) -> dict[str, Any]:
    """Add a strict model proposal without relaxing deterministic findings."""
    result = dict(packet)
    if result.get("status") == "blocked":
        result["model_status"] = "skipped_deterministic_blocker"
        return result

    request = _model_request(claim, result)
    try:
        raw_response = model_adapter(request)
        proposal = _validate_model_proposal(raw_response, result)
    except Exception:
        result.update(
            {
                "status": "blocked",
                "model_status": "error",
                "model_error": "model_adapter_failed",
            }
        )
        return result

    if isinstance(proposal, str):
        result.update(
            {
                "status": "blocked",
                "model_status": "blocked",
                "model_error": proposal,
            }
        )
        return result

    result["model_status"] = "ready"
    result["model_proposal"] = proposal
    current_decision = str(result.get("proposed_decision") or "needs_evidence")
    proposed_decision = str(proposal["decision"])
    if current_decision == "approve" or proposed_decision != "approve":
        result["proposed_decision"] = proposed_decision
    result["missing_evidence"] = list(
        dict.fromkeys([*(result.get("missing_evidence") or []), *proposal["missing_evidence"]])
    )
    result["rationale"] = proposal["rationale"]
    return result


def _model_request(claim: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract": "kbase_claim_verification_model_request_v1",
        "claim": {
            "doc_id": str(claim.get("doc_id") or ""),
            "statement": str(claim.get("summary") or claim.get("body") or claim.get("title") or ""),
            "evidence_level": claim.get("evidence_level"),
            "confidence": claim.get("confidence"),
        },
        "citation_ids": list(packet.get("citation_ids") or []),
        "checks": list(packet.get("checks") or []),
        "allowed_decisions": sorted(_MODEL_DECISIONS),
        "response_contract": {
            "required": sorted(_MODEL_REQUIRED_FIELDS),
            "minimum_confidence": 0.7,
        },
    }


def _validate_model_proposal(
    raw_response: dict[str, Any] | str,
    packet: dict[str, Any],
) -> dict[str, Any] | str:
    if isinstance(raw_response, str):
        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError:
            return "invalid_model_json"
    else:
        payload = raw_response
    if not isinstance(payload, dict) or set(payload) != _MODEL_REQUIRED_FIELDS:
        return "invalid_model_schema"

    decision = str(payload.get("decision") or "")
    if decision not in _MODEL_DECISIONS:
        return "invalid_model_decision"
    confidence = payload.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return "invalid_model_confidence"
    if not 0 <= float(confidence) <= 1:
        return "invalid_model_confidence"
    if float(confidence) < 0.7:
        return "low_model_confidence"
    rationale = str(payload.get("rationale") or "").strip()
    if not rationale or len(rationale) > 2000:
        return "invalid_model_rationale"

    citation_ids = _string_list(payload.get("citation_ids"))
    if citation_ids is None:
        return "invalid_model_citations"
    if not citation_ids:
        return "missing_model_citations"
    supported_citations = set(str(item) for item in packet.get("citation_ids") or [])
    if not set(citation_ids).issubset(supported_citations):
        return "unsupported_model_citations"
    missing_evidence = _string_list(payload.get("missing_evidence"))
    if missing_evidence is None:
        return "invalid_model_missing_evidence"

    return {
        "decision": decision,
        "confidence": float(confidence),
        "rationale": rationale,
        "citation_ids": citation_ids,
        "missing_evidence": missing_evidence,
    }


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    normalized = [str(item).strip() for item in value]
    if any(not item for item in normalized):
        return None
    return list(dict.fromkeys(normalized))


def _check(code: str, status: str, message: str) -> dict[str, str]:
    return {"code": code, "status": status, "message": message}


def _freshness_check(raw_value: Any, now: datetime) -> tuple[str, str]:
    value = str(raw_value or "").strip()
    if not value:
        return "unknown", "No last-confirmed timestamp is available."
    try:
        confirmed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "warn", "Last-confirmed timestamp is invalid."
    if confirmed.tzinfo is None:
        confirmed = confirmed.replace(tzinfo=UTC)
    if now.astimezone(UTC) - confirmed.astimezone(UTC) > _STALE_AFTER:
        return "warn", "External evidence is stale."
    return "pass", "External evidence is current."


def _duplicate_claim_ids(claim: dict[str, Any], peers: list[dict[str, Any]]) -> list[str]:
    doc_id = str(claim.get("doc_id") or "")
    normalized = _normalized_statement(claim)
    if not normalized:
        return []
    return sorted(
        str(peer.get("doc_id") or "")
        for peer in peers
        if str(peer.get("doc_id") or "") not in {"", doc_id}
        and _normalized_statement(peer) == normalized
    )


def _normalized_statement(claim: dict[str, Any]) -> str:
    value = str(claim.get("summary") or claim.get("body") or claim.get("title") or "")
    return "".join(value.lower().split()).rstrip("。.!！?")


def _packet_id(doc_id: str, workspace_fingerprint: str, content_hash: str) -> str:
    value = f"{doc_id}\x00{workspace_fingerprint}\x00{content_hash}".encode()
    return f"verify:{hashlib.sha256(value).hexdigest()}"


def _rationale(decision: str) -> str:
    return {
        "approve": "Deterministic checks found sufficient current evidence.",
        "needs_evidence": "Evidence gaps or contradictions require reviewer attention.",
        "reject": "The claim lacks the minimum source provenance.",
        "background_only": "An equivalent claim already exists in the workspace.",
    }[decision]
