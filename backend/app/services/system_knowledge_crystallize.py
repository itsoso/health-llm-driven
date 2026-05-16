"""Crystallize repeated agent audit observations into reviewable KB drafts."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import difflib
import hashlib
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_audit_log import AgentAuditLog


CLAIM_BOUNDARY = "Health management guidance only; not diagnosis, prescription, or treatment."


def draft_crystallized_claim_candidates(
    db: Session,
    *,
    min_count: int = 100,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Draft claim candidates from repeated, consistent specialist findings.

    This function intentionally does not write into the system KB. The output is
    a PR-style artifact for human review before any global knowledge changes.
    """
    now = now or datetime.now(tz=UTC)
    buckets: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    rows = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.agent_type == "specialist_batch", AgentAuditLog.action == "run")
        .all()
    )
    for row in rows:
        detail = row.result_detail or {}
        findings = detail.get("findings") if isinstance(detail, dict) else []
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            summary = str(finding.get("summary") or "").strip()
            if not summary:
                continue
            outcome = _outcome_for_finding(finding)
            key = (
                str(finding.get("specialist") or finding.get("specialist_name") or "unknown"),
                str(finding.get("kind") or finding.get("category") or "general"),
                _normalize_summary(summary),
                outcome,
            )
            buckets[key].append(finding)

    draft_claims = [
        _draft_claim_for_bucket(key, findings, now)
        for key, findings in sorted(buckets.items())
        if len(findings) >= min_count
    ]
    return {
        "draft_claims": draft_claims,
        "min_count": min_count,
        "generated_at": now.isoformat(),
        "diff": _draft_claims_diff(draft_claims),
    }


def _draft_claim_for_bucket(
    key: tuple[str, str, str, str],
    findings: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    specialist, kind, normalized_summary, outcome = key
    sample_summary = str(findings[0].get("summary") or normalized_summary)
    doc_hash = hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:12]
    return {
        "doc_id": f"claim:c_crystallized_{doc_hash}",
        "doc_type": "claim",
        "entity_type": "agent_pattern",
        "entity_id": _slug(kind),
        "title": f"候选规则：{sample_summary[:80]}",
        "summary": f"Agent 审计中 {len(findings)} 次一致触发：{sample_summary}",
        "body": f"该候选来自多次 agent audit 聚合，需人工审核后才能进入系统级知识库。{CLAIM_BOUNDARY}",
        "confidence": min(0.72, 0.40 + len(findings) / 500),
        "evidence_level": "D",
        "applies_when": [],
        "recommends_lookup": _common_evidence_refs(findings),
        "sources": ["system:agent-audit-log"],
        "last_confirmed": now.isoformat(),
        "decay_rate": "fast",
        "supersedes": [],
        "metadata": {
            "review_status": "draft",
            "extraction_method": "agent_audit_crystallize_v1",
            "observed_count": len(findings),
            "outcome": outcome,
            "specialist": specialist,
            "kind": kind,
            "claim_boundary": CLAIM_BOUNDARY,
        },
    }


def _draft_claims_diff(draft_claims: list[dict[str, Any]]) -> str:
    after = [
        json.dumps(claim, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for claim in draft_claims
    ]
    return "\n".join(
        difflib.unified_diff(
            [],
            after,
            fromfile="crystallized_claims.jsonl",
            tofile="crystallized_claims.jsonl",
            lineterm="",
        )
    )


def _outcome_for_finding(finding: dict[str, Any]) -> str:
    data = finding.get("data") if isinstance(finding.get("data"), dict) else {}
    refs = finding.get("evidence_refs")
    if refs is None:
        refs = data.get("evidence_refs")
    unsupported = bool(finding.get("unsupported") or data.get("unsupported") or not refs)
    return "unsupported" if unsupported else "supported"


def _common_evidence_refs(findings: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for finding in findings:
        refs = finding.get("evidence_refs")
        if refs is None and isinstance(finding.get("data"), dict):
            refs = finding["data"].get("evidence_refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if isinstance(ref, str) and ref.startswith("claim:"):
                counts[ref] = counts.get(ref, 0) + 1
    return [ref for ref, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]]


def _normalize_summary(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip().lower()).strip("-")
    return slug or "general"
