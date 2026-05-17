"""DB-backed system knowledge lookup for LLM Wiki v2 Phase 0."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
import hashlib
import operator
import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.system_knowledge import KBAudit, KBDocument, KBEdge


CLAIM_BOUNDARY = "仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。"
SPECIALIST_EVIDENCE_REF_RATE_TARGET = 0.85
VALID_REVIEW_STATUSES = {"draft", "reviewed", "needs_review", "archived"}
POSITIVE_STANCES = {"supports", "positive", "for", "yes", "true", "increase", "increases"}
NEGATIVE_STANCES = {"opposes", "negative", "against", "no", "false", "decrease", "decreases"}

_IN_RE = re.compile(r"^(?P<path>twin\.[A-Za-z0-9_.-]+)\s+in\s+(?P<values>\[.*\])$")
_EQ_RE = re.compile(r"^(?P<path>twin\.[A-Za-z0-9_.-]+)\s*(==|=)\s*(?P<value>.+)$")
_COMPARE_RE = re.compile(
    r"^(?P<path>twin\.[A-Za-z0-9_.-]+)\s*(?P<op>>=|<=|>|<)\s*(?P<value>-?\d+(?:\.\d+)?)$"
)
_NULL_RE = re.compile(r"^(?P<path>twin\.[A-Za-z0-9_.-]+)\s+is\s+(?P<negation>not\s+)?null$")
_GENE_MESSAGE_PATTERNS = {
    "MTHFR": re.compile(r"\bMTHFR\b(?:[-\s_]*(?P<mthfr>CC|CT|TT))?", re.IGNORECASE),
    "APOE": re.compile(r"\bAPOE\b(?:[-\s_]*(?P<apoe>E[234]/E[234]|E[234]E[234]))?", re.IGNORECASE),
    "FTO": re.compile(r"\bFTO\b", re.IGNORECASE),
    "ACTN3": re.compile(r"\bACTN3\b", re.IGNORECASE),
    "ALDH2": re.compile(r"\bALDH2\b(?:[-\s_]*(?P<aldh2>GA|AA|GG|\*1/\*2|\*2/\*2))?", re.IGNORECASE),
}


def serialize_document(document: KBDocument, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "doc_id": document.doc_id,
        "doc_type": document.doc_type,
        "entity_type": document.entity_type,
        "entity_id": document.entity_id,
        "title": document.title,
        "summary": document.summary,
        "body": document.body,
        "confidence": document.confidence,
        "evidence_level": document.evidence_level,
        "applies_when": document.applies_when or [],
        "recommends_lookup": document.recommends_lookup or [],
        "sources": document.sources or [],
        "last_confirmed": document.last_confirmed.isoformat() if document.last_confirmed else None,
        "decay_rate": document.decay_rate,
        "is_archived": document.is_archived,
        "metadata": document.metadata_json or {},
    }
    if extra:
        payload.update(extra)
    return payload


def get_entity_bundle(db: Session, entity_type: str, entity_id: str) -> dict[str, Any] | None:
    entity = (
        db.query(KBDocument)
        .filter(
            KBDocument.doc_type == "entity",
            KBDocument.entity_type == entity_type,
            KBDocument.entity_id == entity_id,
            KBDocument.is_archived.is_(False),
        )
        .first()
    )
    if entity is None:
        return None

    edges = (
        db.query(KBEdge)
        .filter(or_(KBEdge.src_doc_id == entity.doc_id, KBEdge.dst_doc_id == entity.doc_id))
        .all()
    )
    related_ids = {
        edge.dst_doc_id if edge.src_doc_id == entity.doc_id else edge.src_doc_id
        for edge in edges
    }
    linked_claims = []
    if related_ids:
        linked_claims = (
            db.query(KBDocument)
            .filter(
                KBDocument.doc_id.in_(related_ids),
                KBDocument.doc_type == "claim",
                KBDocument.is_archived.is_(False),
            )
            .order_by(KBDocument.confidence.desc().nullslast(), KBDocument.doc_id.asc())
            .all()
        )

    return {
        "entity": serialize_document(entity),
        "linked_claims": [serialize_document(claim) for claim in linked_claims],
        "edges": [
            {
                "edge_id": edge.edge_id,
                "src_doc_id": edge.src_doc_id,
                "dst_doc_id": edge.dst_doc_id,
                "relation": edge.relation,
                "confidence": edge.confidence,
                "source_claim_id": edge.source_claim_id,
            }
            for edge in edges
        ],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def get_claim_bundle(db: Session, claim_id: str) -> dict[str, Any] | None:
    claim = (
        db.query(KBDocument)
        .filter(
            KBDocument.doc_id == claim_id,
            KBDocument.doc_type == "claim",
            KBDocument.is_archived.is_(False),
        )
        .first()
    )
    if claim is None:
        return None

    edges = (
        db.query(KBEdge)
        .filter(or_(KBEdge.src_doc_id == claim.doc_id, KBEdge.dst_doc_id == claim.doc_id))
        .all()
    )
    neighbor_ids = {
        edge.dst_doc_id if edge.src_doc_id == claim.doc_id else edge.src_doc_id
        for edge in edges
    }
    neighbors = []
    if neighbor_ids:
        neighbors = (
            db.query(KBDocument)
            .filter(KBDocument.doc_id.in_(neighbor_ids), KBDocument.is_archived.is_(False))
            .order_by(KBDocument.doc_type.asc(), KBDocument.doc_id.asc())
            .all()
        )

    return {
        "claim": serialize_document(claim),
        "neighbors": [serialize_document(neighbor) for neighbor in neighbors],
        "edges": [_serialize_edge(edge) for edge in edges],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def search_knowledge(
    db: Session,
    query: str,
    *,
    limit: int = 10,
    doc_type: str | None = None,
    entity_type: str | None = None,
) -> dict[str, Any]:
    """Small deterministic hybrid-search placeholder for the serving KB.

    Phase 1b keeps this DB-only so it works with both local SQLite tests and
    production PostgreSQL. The next phase can replace the scorer with
    Postgres FTS + vector retrieval while keeping this response shape.
    """

    normalized_query = (query or "").strip()
    terms = [term.lower() for term in re.split(r"\s+", normalized_query) if term.strip()]

    docs_query = db.query(KBDocument).filter(KBDocument.is_archived.is_(False))
    if doc_type:
        docs_query = docs_query.filter(KBDocument.doc_type == doc_type)
    if entity_type:
        docs_query = docs_query.filter(KBDocument.entity_type == entity_type)

    scored: list[tuple[float, KBDocument]] = []
    for document in docs_query.all():
        score = _score_document(document, terms)
        if score > 0 or not terms:
            scored.append((score, document))

    scored.sort(key=lambda item: (-item[0], item[1].doc_type, item[1].doc_id))
    selected = scored[: max(1, min(limit, 50))]
    selected_ids = {document.doc_id for _score, document in selected}
    edges = []
    neighbors = []
    if selected_ids:
        edges = (
            db.query(KBEdge)
            .filter(or_(KBEdge.src_doc_id.in_(selected_ids), KBEdge.dst_doc_id.in_(selected_ids)))
            .all()
        )
        neighbor_ids = {
            edge.dst_doc_id if edge.src_doc_id in selected_ids else edge.src_doc_id
            for edge in edges
            if edge.src_doc_id not in selected_ids or edge.dst_doc_id not in selected_ids
        }
        if neighbor_ids:
            neighbors = (
                db.query(KBDocument)
                .filter(KBDocument.doc_id.in_(neighbor_ids), KBDocument.is_archived.is_(False))
                .order_by(KBDocument.doc_type.asc(), KBDocument.doc_id.asc())
                .all()
            )

    return {
        "query": normalized_query,
        "results": [
            {"score": round(score, 4), "document": serialize_document(document)}
            for score, document in selected
        ],
        "graph_context": {
            "edges": [_serialize_edge(edge) for edge in edges],
            "neighbors": [serialize_document(neighbor) for neighbor in neighbors],
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def lookup_for_twin(db: Session, twin: dict[str, Any]) -> dict[str, Any]:
    entity_keys = _extract_entity_keys(twin)
    entities = []
    if entity_keys:
        entity_filters = [
            (KBDocument.entity_type == entity_type) & (KBDocument.entity_id == entity_id)
            for entity_type, entity_id in sorted(entity_keys)
        ]
        entities = (
            db.query(KBDocument)
            .filter(
                KBDocument.doc_type == "entity",
                KBDocument.is_archived.is_(False),
                or_(*entity_filters),
            )
            .order_by(KBDocument.entity_type.asc(), KBDocument.entity_id.asc())
            .all()
        )

    matched_claims = []
    claims = (
        db.query(KBDocument)
        .filter(KBDocument.doc_type == "claim", KBDocument.is_archived.is_(False))
        .order_by(KBDocument.confidence.desc().nullslast(), KBDocument.doc_id.asc())
        .all()
    )
    for claim in claims:
        conditions = claim.applies_when or []
        matched_conditions = [condition for condition in conditions if evaluate_condition(condition, twin)]
        if matched_conditions:
            matched_claims.append(serialize_document(claim, {"matched_conditions": matched_conditions}))

    return {
        "entities": [serialize_document(entity) for entity in entities],
        "claims": matched_claims,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def reindex_knowledge_documents(db: Session, actor: str = "system") -> dict[str, int]:
    documents = db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).all()
    for document in documents:
        searchable = _document_search_text(document)
        document.tsv = searchable
        document.content_hash = hashlib.sha256(searchable.encode("utf-8")).hexdigest()

    db.add(
        KBAudit(
            doc_id=None,
            op="reindex",
            actor=actor,
            diff={"documents": len(documents)},
        )
    )
    db.commit()
    return {"documents": len(documents)}


def lint_knowledge_base(db: Session) -> dict[str, Any]:
    documents = db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).all()
    edges = db.query(KBEdge).all()
    linked_doc_ids = {edge.src_doc_id for edge in edges} | {edge.dst_doc_id for edge in edges}
    now = datetime.now(UTC)

    orphan_entities = [
        _compact_issue(document)
        for document in documents
        if document.doc_type == "entity" and document.doc_id not in linked_doc_ids
    ]
    orphan_claims = [
        _compact_issue(document)
        for document in documents
        if document.doc_type == "claim" and document.doc_id not in linked_doc_ids
    ]
    invalid_conditions = []
    invalid_review_status = []
    stale_claims = []
    for document in documents:
        if document.doc_type != "claim":
            continue
        metadata = document.metadata_json or {}
        review_status = metadata.get("review_status")
        if review_status is not None and review_status not in VALID_REVIEW_STATUSES:
            invalid_review_status.append(
                {**_compact_issue(document), "review_status": review_status}
            )
        for condition in document.applies_when or []:
            if not is_supported_condition(condition):
                invalid_conditions.append({**_compact_issue(document), "condition": condition})
        if document.last_confirmed and _ensure_aware(document.last_confirmed) < now - timedelta(days=365):
            stale_claims.append(_compact_issue(document))

    issues = {
        "orphan_entities": orphan_entities,
        "orphan_claims": orphan_claims,
        "invalid_conditions": invalid_conditions,
        "invalid_review_status": invalid_review_status,
        "stale_claims": stale_claims,
        "contradictions": _detect_claim_contradictions(documents),
    }
    return {
        "summary": {name: len(items) for name, items in issues.items()},
        "issues": issues,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def get_knowledge_coverage_report(db: Session) -> dict[str, Any]:
    """Aggregate system KB coverage signals for admin review dashboards."""
    documents = db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).all()
    by_type: dict[str, int] = {}
    by_review_status: dict[str, int] = {}
    by_evidence_level: dict[str, int] = {}
    for document in documents:
        by_type[document.doc_type] = by_type.get(document.doc_type, 0) + 1
        if document.evidence_level:
            by_evidence_level[document.evidence_level] = by_evidence_level.get(document.evidence_level, 0) + 1
        metadata = document.metadata_json or {}
        review_status = str(metadata.get("review_status") or "unreviewed")
        by_review_status[review_status] = by_review_status.get(review_status, 0) + 1

    return {
        "documents": {
            "total": len(documents),
            "by_type": dict(sorted(by_type.items())),
            "by_review_status": dict(sorted(by_review_status.items())),
            "by_evidence_level": dict(sorted(by_evidence_level.items())),
        },
        "specialist_findings": _aggregate_specialist_evidence_coverage(db),
        "feedback": {
            "disagree": db.query(KBAudit).filter(KBAudit.op == "feedback_disagree").count(),
        },
    }


def apply_confidence_decay(
    db: Session,
    *,
    now: datetime | None = None,
    actor: str = "system",
) -> dict[str, int]:
    current_time = _ensure_aware(now or datetime.now(UTC))
    windows = {
        "fast": timedelta(days=30),
        "normal": timedelta(days=120),
        "slow": timedelta(days=365),
    }
    multiplier = {
        "fast": 0.90,
        "normal": 0.96,
        "slow": 0.99,
    }
    updated = 0
    claims = (
        db.query(KBDocument)
        .filter(
            KBDocument.doc_type == "claim",
            KBDocument.is_archived.is_(False),
            KBDocument.confidence.isnot(None),
            KBDocument.last_confirmed.isnot(None),
        )
        .all()
    )
    for claim in claims:
        decay_rate = claim.decay_rate or "normal"
        window = windows.get(decay_rate, windows["normal"])
        last_confirmed = _ensure_aware(claim.last_confirmed)
        if last_confirmed > current_time - window:
            continue
        factor = multiplier.get(decay_rate, multiplier["normal"])
        claim.confidence = round(max(0.1, float(claim.confidence) * factor), 4)
        updated += 1

    if updated:
        db.add(
            KBAudit(
                doc_id=None,
                op="confidence_decay",
                actor=actor,
                diff={"updated": updated, "now": current_time.isoformat()},
            )
        )
    db.commit()
    return {"updated": updated}


def format_system_knowledge_for_prompt(
    db: Session,
    twin: dict[str, Any],
    max_claims: int = 6,
    max_chars: int = 1500,
) -> str:
    """Render a bounded system-KB block for Agent prompts."""

    result = lookup_for_twin(db, twin)
    claims = result["claims"][:max_claims]
    if not claims:
        return ""

    lines = ["## 系统知识库相关条目"]
    for claim in claims:
        sources = ", ".join(claim.get("sources") or [])
        confidence = claim.get("confidence")
        confidence_text = f"{confidence:.2f}" if isinstance(confidence, float) else "n/a"
        line = (
            f"- {claim.get('title') or claim.get('doc_id')} "
            f"[{claim.get('evidence_level') or '?'} conf={confidence_text}] "
            f"({claim.get('doc_id')})"
        )
        summary = claim.get("summary")
        if summary:
            line += f": {summary}"
        if sources:
            line += f" 来源: {sources}"
        lines.append(line)
    lines.append(f"边界: {CLAIM_BOUNDARY}")

    rendered = "\n".join(lines)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3].rstrip() + "..."


def attach_system_knowledge_evidence(
    db: Session,
    twin: dict[str, Any],
    findings: list[Any],
    *,
    max_refs_per_finding: int = 3,
) -> dict[str, int]:
    """Attach matched system-KB claim IDs to specialist findings.

    This is deliberately conservative: it only attaches claims whose
    `applies_when` conditions match the structured Twin payload. It does not
    invent evidence from semantic similarity.
    """

    result = lookup_for_twin(db, twin)
    claims = result.get("claims") or []
    if not claims:
        return {"findings_updated": 0, "claim_refs": 0}

    updated = 0
    for finding in findings:
        refs = _select_claim_refs_for_specialist(finding, claims, max_refs_per_finding)
        if not refs:
            continue
        existing_refs = list(getattr(finding, "evidence_refs", []) or [])
        merged_refs = _dedupe_preserve_order(existing_refs + refs)
        try:
            finding.evidence_refs = merged_refs
        except Exception:  # noqa: BLE001
            pass
        if isinstance(getattr(finding, "raw", None), dict):
            finding.raw["system_kb_evidence_refs"] = merged_refs
        for item in getattr(finding, "findings", []) or []:
            if isinstance(item, dict) and not item.get("evidence_refs"):
                item["evidence_refs"] = refs
        updated += 1

    return {"findings_updated": updated, "claim_refs": len(claims)}


def _select_claim_refs_for_specialist(
    finding: Any,
    claims: list[dict[str, Any]],
    max_refs: int,
) -> list[str]:
    specialist = (getattr(finding, "specialist_name", "") or "").lower()
    category = (getattr(finding, "category", "") or "").lower()
    domain_keywords = _specialist_domain_keywords(specialist, category)
    selected: list[str] = []

    for claim in claims:
        metadata = claim.get("metadata") or {}
        domain = str(metadata.get("domain") or "")
        entity_type = str(claim.get("entity_type") or "")
        entity_id = str(claim.get("entity_id") or "")
        haystack = f"{domain} {entity_type} {entity_id}".lower()
        if domain_keywords and not any(keyword in haystack for keyword in domain_keywords):
            continue
        doc_id = claim.get("doc_id")
        if doc_id:
            selected.append(doc_id)
        if len(selected) >= max_refs:
            break

    if not selected:
        selected = [claim["doc_id"] for claim in claims[:max_refs] if claim.get("doc_id")]
    return _dedupe_preserve_order(selected)


def _specialist_domain_keywords(specialist: str, category: str) -> list[str]:
    text = f"{specialist} {category}"
    if "fuel" in text or "nutrition" in text:
        return ["nutrition", "metabolic", "fiber", "protein"]
    if "supplement" in text:
        return ["supplement", "genetic", "biomarker", "metabolic"]
    if "movement" in text:
        return ["movement", "training", "recovery", "metabolic"]
    if "recovery" in text:
        return ["sleep", "recovery"]
    if "safety" in text:
        return ["safety", "medication", "gene", "biomarker"]
    if "metabolic" in text:
        return ["metabolic", "glycemic", "lipid"]
    return []


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_evidence_card_for_message(db: Session, message: str) -> dict[str, Any] | None:
    """Build a mobile evidence card for explicit gene questions.

    This is intentionally conservative for Phase 0: it only extracts clear gene
    mentions and a few common genotype spellings, then reuses structured
    `lookup_for_twin` instead of free-form embedding matches.
    """

    twin = _twin_from_message(message)
    if not twin.get("genetics"):
        return None

    result = lookup_for_twin(db, twin)
    if not result["entities"] or not result["claims"]:
        return None

    return {
        "type": "system_knowledge_evidence",
        "data": {
            "entity": result["entities"][0],
            "claims": result["claims"][:3],
            "claim_boundary": result["claim_boundary"],
        },
    }


def evaluate_condition(condition: str, twin: dict[str, Any]) -> bool:
    expression = condition.strip()
    null_match = _NULL_RE.match(expression)
    if null_match:
        value = _value_at_path(twin, null_match.group("path"))
        is_null = value is None
        return not is_null if null_match.group("negation") else is_null

    in_match = _IN_RE.match(expression)
    if in_match:
        value = _value_at_path(twin, in_match.group("path"))
        try:
            candidates = ast.literal_eval(in_match.group("values"))
        except (SyntaxError, ValueError):
            return False
        return value in candidates

    eq_match = _EQ_RE.match(expression)
    if eq_match:
        value = _value_at_path(twin, eq_match.group("path"))
        expected = _parse_literal(eq_match.group("value"))
        return value == expected

    compare_match = _COMPARE_RE.match(expression)
    if compare_match:
        value = _value_at_path(twin, compare_match.group("path"))
        if value is None:
            return False
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return False
        expected = float(compare_match.group("value"))
        op = {
            ">=": operator.ge,
            "<=": operator.le,
            ">": operator.gt,
            "<": operator.lt,
        }[compare_match.group("op")]
        return op(numeric_value, expected)

    return False


def is_supported_condition(condition: str) -> bool:
    expression = (condition or "").strip()
    return any(
        pattern.match(expression)
        for pattern in (_NULL_RE, _IN_RE, _EQ_RE, _COMPARE_RE)
    )


def _serialize_edge(edge: KBEdge) -> dict[str, Any]:
    return {
        "edge_id": edge.edge_id,
        "src_doc_id": edge.src_doc_id,
        "dst_doc_id": edge.dst_doc_id,
        "relation": edge.relation,
        "confidence": edge.confidence,
        "source_claim_id": edge.source_claim_id,
    }


def _score_document(document: KBDocument, terms: list[str]) -> float:
    if not terms:
        return 1.0
    text = _document_search_text(document).lower()
    score = 0.0
    title = (document.title or "").lower()
    entity = f"{document.entity_type or ''} {document.entity_id or ''}".lower()
    for term in terms:
        if term in title:
            score += 4.0
        if term in entity:
            score += 3.0
        if term in text:
            score += 1.0 + min(text.count(term), 5) * 0.1
    if document.doc_type == "claim":
        score += 0.2
    if document.confidence:
        score += float(document.confidence) * 0.1
    return score


def _document_search_text(document: KBDocument) -> str:
    chunks = [
        document.doc_id,
        document.doc_type,
        document.entity_type,
        document.entity_id,
        document.title,
        document.summary,
        document.body,
        document.evidence_level,
        document.decay_rate,
        " ".join(document.sources or []),
        " ".join(document.applies_when or []),
        " ".join(document.recommends_lookup or []),
    ]
    return "\n".join(str(chunk) for chunk in chunks if chunk)


def _compact_issue(document: KBDocument) -> dict[str, Any]:
    return {
        "doc_id": document.doc_id,
        "doc_type": document.doc_type,
        "entity_type": document.entity_type,
        "entity_id": document.entity_id,
        "title": document.title,
    }


def _detect_claim_contradictions(documents: list[KBDocument]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, list[KBDocument]]] = {}
    for document in documents:
        if document.doc_type != "claim":
            continue
        metadata = document.metadata_json or {}
        claim_key = metadata.get("claim_key")
        stance = _normalized_stance(metadata.get("stance"))
        if not claim_key or stance not in {"positive", "negative"}:
            continue
        buckets.setdefault(str(claim_key), {"positive": [], "negative": []})[stance].append(document)

    contradictions = []
    for claim_key, grouped in sorted(buckets.items()):
        if not grouped["positive"] or not grouped["negative"]:
            continue
        docs = grouped["positive"] + grouped["negative"]
        contradictions.append(
            {
                "claim_key": claim_key,
                "doc_ids": [document.doc_id for document in docs],
                "positive_doc_ids": [document.doc_id for document in grouped["positive"]],
                "negative_doc_ids": [document.doc_id for document in grouped["negative"]],
                "titles": {document.doc_id: document.title for document in docs},
            }
        )
    return contradictions


def _aggregate_specialist_evidence_coverage(db: Session) -> dict[str, Any]:
    from app.models.agent_audit_log import AgentAuditLog

    rows = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.agent_type == "specialist_batch", AgentAuditLog.action == "run")
        .all()
    )
    total = 0
    with_refs = 0
    unsupported = 0
    by_specialist: dict[str, dict[str, int]] = {}
    for row in rows:
        detail = row.result_detail or {}
        findings = detail.get("findings") if isinstance(detail, dict) else []
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            total += 1
            refs = _extract_finding_evidence_refs(finding)
            is_unsupported = _finding_is_unsupported(finding, refs)
            if refs:
                with_refs += 1
            if is_unsupported:
                unsupported += 1
            specialist = str(finding.get("specialist") or finding.get("specialist_name") or "unknown")
            bucket = by_specialist.setdefault(specialist, {"total": 0, "with_evidence_refs": 0, "unsupported": 0})
            bucket["total"] += 1
            bucket["with_evidence_refs"] += 1 if refs else 0
            bucket["unsupported"] += 1 if is_unsupported else 0

    return {
        "total": total,
        "with_evidence_refs": with_refs,
        "unsupported": unsupported,
        "evidence_ref_rate": round(with_refs / total, 4) if total else 0.0,
        "target_evidence_ref_rate": SPECIALIST_EVIDENCE_REF_RATE_TARGET,
        "meets_target": (with_refs / total) >= SPECIALIST_EVIDENCE_REF_RATE_TARGET if total else False,
        "unsupported_rate": round(unsupported / total, 4) if total else 0.0,
        "by_specialist": by_specialist,
    }


def _extract_finding_evidence_refs(finding: dict[str, Any]) -> list[Any]:
    refs = finding.get("evidence_refs")
    if refs is None and isinstance(finding.get("data"), dict):
        refs = finding["data"].get("evidence_refs")
    return refs if isinstance(refs, list) else []


def _finding_is_unsupported(finding: dict[str, Any], refs: list[Any]) -> bool:
    data = finding.get("data") if isinstance(finding.get("data"), dict) else {}
    return bool(finding.get("unsupported") or data.get("unsupported") or not refs)


def _normalized_stance(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in POSITIVE_STANCES:
        return "positive"
    if normalized in NEGATIVE_STANCES:
        return "negative"
    return None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _parse_literal(raw: str) -> Any:
    normalized = raw.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    if normalized in {"null", "none"}:
        return None
    try:
        return ast.literal_eval(raw.strip())
    except (SyntaxError, ValueError):
        return raw.strip().strip("\"'")


def _value_at_path(twin: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    if parts and parts[0] == "twin":
        parts = parts[1:]
    current: Any = twin
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _extract_entity_keys(twin: dict[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    genetics = twin.get("genetics") if isinstance(twin.get("genetics"), dict) else {}
    gene_prefixes = {
        "MTHFR_C677T": "MTHFR",
        "MTHFR": "MTHFR",
        "APOE": "APOE",
        "FTO": "FTO",
        "ACTN3": "ACTN3",
        "ALDH2": "ALDH2",
    }
    for field, entity_id in gene_prefixes.items():
        if genetics.get(field) is not None:
            keys.add(("gene", entity_id))

    labs = twin.get("labs") if isinstance(twin.get("labs"), dict) else {}
    if labs.get("homocysteine_umol_l") is not None or labs.get("Hcy") is not None:
        keys.add(("biomarker", "Hcy"))
    if labs.get("ldl_c_mmol_l") is not None or labs.get("LDL-C") is not None:
        keys.add(("biomarker", "LDL-C"))
    if labs.get("hba1c_percent") is not None or labs.get("HbA1c") is not None:
        keys.add(("biomarker", "HbA1c"))
    if labs.get("triglycerides_mmol_l") is not None or labs.get("TG") is not None:
        keys.add(("biomarker", "TG"))
    if labs.get("systolic_bp") is not None or labs.get("diastolic_bp") is not None:
        keys.add(("biomarker", "BP"))
    if labs.get("uric_acid_umol_l") is not None or labs.get("UA") is not None:
        keys.add(("biomarker", "uric-acid"))

    goals = twin.get("goals") if isinstance(twin.get("goals"), dict) else {}
    if _value_at_path({"goals": goals}, "twin.goals.weight_loss.active") is True:
        keys.add(("condition", "metabolic-health"))
        keys.add(("intervention", "weight-waist-tracking"))
    if _value_at_path({"goals": goals}, "twin.goals.metabolic_health.active") is True:
        keys.add(("condition", "metabolic-health"))
    if _value_at_path({"goals": goals}, "twin.goals.sleep.active") is True:
        keys.add(("condition", "sleep-recovery"))
    if _value_at_path({"goals": goals}, "twin.goals.longevity.active") is True:
        keys.add(("aging_hallmark", "mitochondrial_dysfunction"))

    return keys


def _twin_from_message(message: str) -> dict[str, Any]:
    genetics: dict[str, Any] = {}
    for gene, pattern in _GENE_MESSAGE_PATTERNS.items():
        match = pattern.search(message or "")
        if not match:
            continue
        if gene == "MTHFR":
            genetics["MTHFR_C677T"] = (match.group("mthfr") or "TT").upper()
        elif gene == "APOE":
            genotype = match.group("apoe")
            if genotype:
                genotype = genotype.upper().replace("E", "E", 1)
                if "/" not in genotype and len(genotype) == 4:
                    genotype = f"{genotype[:2]}/{genotype[2:]}"
                genetics["APOE"] = genotype
            else:
                genetics["APOE"] = "E3/E4"
        elif gene == "ALDH2":
            genetics["ALDH2"] = (match.group("aldh2") or "GA").upper()
        else:
            genetics[gene] = "present"
    return {"genetics": genetics, "labs": {}}
