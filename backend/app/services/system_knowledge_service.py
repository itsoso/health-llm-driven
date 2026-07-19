"""DB-backed system knowledge lookup for LLM Wiki v2 Phase 0."""

from __future__ import annotations

import ast
from collections import Counter
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import logging
import math
import operator
from pathlib import Path
import re
from typing import Any

from sqlalchemy import bindparam, desc, func, or_, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.system_knowledge import KBAudit, KBDocument, KBDocumentVector, KBEdge
from app.services.retrieval_guard import guard_retrieval_query
from app.services.system_knowledge_ingest import validate_artifact_review_gate
from app.services.kbase_review_workspace import (
    adjudicate_review_claim,
    finalize_review_workspace,
    generate_review_verification_packet,
    list_review_claims,
    list_review_verification_packets,
    review_workspace_lock,
    workspace_artifacts_valid,
    workspace_content_fingerprint,
)


logger = logging.getLogger(__name__)
CLAIM_BOUNDARY = "仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。"
SPARSE_VECTOR_BACKEND = "sparse_term_cosine_v1"
VECTOR_BACKEND = SPARSE_VECTOR_BACKEND
PGVECTOR_TABLE = "kb_document_embeddings"
VECTOR_MAX_TERMS = 512
SPECIALIST_EVIDENCE_REF_RATE_TARGET = 0.85
EXTERNAL_EVIDENCE_SOURCE_RATE_TARGET = 0.2
VALID_REVIEW_STATUSES = {"draft", "reviewed", "needs_review", "archived"}
POSITIVE_STANCES = {"supports", "positive", "for", "yes", "true", "increase", "increases"}
NEGATIVE_STANCES = {"opposes", "negative", "against", "no", "false", "decrease", "decreases"}
SOURCE_FRESHNESS_WINDOWS_DAYS = {
    "guideline": 365,
    "database": 180,
    "research": 1095,
    "course": 730,
    "book": 1095,
    "article": 365,
    "other": 365,
}
_ACID_SUPPRESSION_MED_TOKENS = (
    "ppi",
    "p-cab",
    "omeprazole",
    "esomeprazole",
    "lansoprazole",
    "pantoprazole",
    "rabeprazole",
    "vonoprazan",
    "奥美拉唑",
    "艾司奥美拉唑",
    "兰索拉唑",
    "泮托拉唑",
    "雷贝拉唑",
    "伏诺拉生",
    "抑酸",
)

_CONDITION_PATH = r"twin\.[A-Za-z0-9_.:*+-]+"
_IN_RE = re.compile(rf"^(?P<path>{_CONDITION_PATH})\s+in\s+(?P<values>\[.*\])$")
_INTERSECTS_RE = re.compile(rf"^(?P<path>{_CONDITION_PATH})\s+intersects\s+(?P<values>\[.*\])$")
_HAS_RE = re.compile(rf"^(?P<path>{_CONDITION_PATH})\s+has\s+(?P<value>.+)$")
_HAS_ANY_RE = re.compile(r"^any\s+of\s+(?P<values>\[.*\])$")
_EQ_RE = re.compile(rf"^(?P<path>{_CONDITION_PATH})\s*(==|=)\s*(?P<value>.+)$")
_COMPARE_RE = re.compile(
    rf"^(?P<path>{_CONDITION_PATH})\s*(?P<op>>=|<=|>|<)\s*(?P<value>-?\d+(?:\.\d+)?)$"
)
_NULL_RE = re.compile(rf"^(?P<path>{_CONDITION_PATH})\s+is\s+(?P<negation>not\s+)?null$")
_GENE_MESSAGE_PATTERNS = {
    "MTHFR": re.compile(r"\bMTHFR\b(?:[-\s_]*(?P<mthfr>CC|CT|TT))?", re.IGNORECASE),
    "APOE": re.compile(r"\bAPOE\b(?:[-\s_]*(?P<apoe>E[234]/E[234]|E[234]E[234]))?", re.IGNORECASE),
    "9p21": re.compile(r"\b(?:9p21|rs10757274)\b(?:[-\s_]*(?P<ninep21>AA|AG|GG))?", re.IGNORECASE),
    "FTO": re.compile(r"\bFTO\b", re.IGNORECASE),
    "ACTN3": re.compile(r"\bACTN3\b", re.IGNORECASE),
    "ALDH2": re.compile(r"\bALDH2\b(?:[-\s_]*(?P<aldh2>GA|AA|GG|\*1/\*2|\*2/\*2))?", re.IGNORECASE),
}


EVIDENCE_LEVEL_DETAILS = {
    "A": {
        "level": "A",
        "label": "A级",
        "description": "高等级证据：来自指南、系统综述、Meta 分析或随机对照研究，可作为强证据参考。",
    },
    "B": {
        "level": "B",
        "label": "B级",
        "description": "中等证据：来自人群研究、临床观察、机制研究或有明确来源的专家课程，适合做健康管理参考。",
    },
    "C": {
        "level": "C",
        "label": "C级",
        "description": "有限证据：多来自科普、专家解释或间接机制，需要结合个人数据和更高等级来源复核。",
    },
    "D": {
        "level": "D",
        "label": "D级",
        "description": "低等级证据：多为个案、经验或待验证观察，只能作为探索线索。",
    },
}

SOURCE_KIND_ORDER = {
    "guideline": 0,
    "research": 1,
    "database": 2,
    "course": 3,
    "book": 4,
    "article": 5,
    "other": 9,
}
EVIDENCE_LEVEL_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}


def _reviewed_document_filter():
    return KBDocument.metadata_json["review_status"].as_string() == "reviewed"


def _serving_document_filters():
    return (
        KBDocument.is_archived.is_(False),
        _reviewed_document_filter(),
    )


def evidence_level_detail(level: str | None) -> dict[str, str] | None:
    if not level:
        return None
    normalized = str(level).strip().upper()
    detail = EVIDENCE_LEVEL_DETAILS.get(normalized)
    if detail:
        return detail.copy()
    return {
        "level": normalized,
        "label": f"{normalized}级",
        "description": "未登记的证据等级，请查看原始来源并谨慎使用。",
    }


def _humanize_source_tail(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").strip()


def source_detail(source: str) -> dict[str, str]:
    raw = str(source or "").strip()
    lowered = raw.lower()
    prefix, _, value = raw.partition(":")
    normalized_prefix = prefix.lower()

    if normalized_prefix in {"pubmed", "pmid"}:
        return {
            "source": raw,
            "kind": "research",
            "label": "PubMed",
            "trust_tier": "clinical_research",
            "display_name": f"PubMed {value or raw}",
        }
    if normalized_prefix in {"guideline", "nih", "cdc", "who", "nmpa", "fda"}:
        label = normalized_prefix.upper() if normalized_prefix != "guideline" else "临床指南"
        return {
            "source": raw,
            "kind": "guideline",
            "label": label,
            "trust_tier": "clinical_guideline",
            "display_name": _humanize_source_tail(value or raw),
        }
    if normalized_prefix == "examine":
        return {
            "source": raw,
            "kind": "database",
            "label": "Examine",
            "trust_tier": "evidence_database",
            "display_name": _humanize_source_tail(value or raw),
        }
    if normalized_prefix in {"dedao", "得到"}:
        return {
            "source": raw,
            "kind": "course",
            "label": "得到课程",
            "trust_tier": "expert_course",
            "display_name": _humanize_source_tail(value or raw),
        }
    if normalized_prefix in {"book", "course"}:
        return {
            "source": raw,
            "kind": normalized_prefix,
            "label": "书籍" if normalized_prefix == "book" else "课程",
            "trust_tier": "expert_content",
            "display_name": _humanize_source_tail(value or raw),
        }
    if "pubmed" in lowered:
        return {
            "source": raw,
            "kind": "research",
            "label": "PubMed",
            "trust_tier": "clinical_research",
            "display_name": raw,
        }
    return {
        "source": raw,
        "kind": "other",
        "label": "其他来源",
        "trust_tier": "unclassified",
        "display_name": raw,
    }


def source_details(sources: list[str] | None) -> list[dict[str, str]]:
    return [source_detail(source) for source in sources or [] if str(source or "").strip()]


def source_groups(sources: list[str] | None) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for detail in source_details(sources):
        kind = detail["kind"]
        if kind not in grouped:
            grouped[kind] = {
                "kind": kind,
                "label": detail["label"],
                "trust_tier": detail["trust_tier"],
                "count": 0,
                "sources": [],
            }
        grouped[kind]["count"] += 1
        grouped[kind]["sources"].append(detail)

    return sorted(
        grouped.values(),
        key=lambda group: (SOURCE_KIND_ORDER.get(group["kind"], 9), group["label"]),
    )


def serialize_document(document: KBDocument, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    sources = document.sources or []
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
        "evidence_level_detail": evidence_level_detail(document.evidence_level),
        "applies_when": document.applies_when or [],
        "recommends_lookup": document.recommends_lookup or [],
        "sources": sources,
        "source_details": source_details(sources),
        "source_groups": source_groups(sources),
        "last_confirmed": document.last_confirmed.isoformat() if document.last_confirmed else None,
        "decay_rate": document.decay_rate,
        "is_archived": document.is_archived,
        "metadata": document.metadata_json or {},
    }
    if extra:
        payload.update(extra)
    return payload


def _normalize_knowledge_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _claim_semantic_key(claim: KBDocument) -> tuple[str, str]:
    title_key = _normalize_knowledge_text(claim.title)
    summary_key = _normalize_knowledge_text(claim.summary)
    if title_key or summary_key:
        return title_key, summary_key
    return str(claim.doc_id), ""


def _claim_quality_rank(claim: KBDocument) -> tuple[int, float, str]:
    level = str(claim.evidence_level or "").strip().upper()
    return (
        EVIDENCE_LEVEL_RANK.get(level, 0),
        float(claim.confidence or 0),
        str(claim.doc_id),
    )


def dedupe_semantic_claims(claims: list[KBDocument]) -> list[KBDocument]:
    best_by_key: dict[tuple[str, str], KBDocument] = {}
    for claim in claims:
        key = _claim_semantic_key(claim)
        current = best_by_key.get(key)
        if current is None or _claim_quality_rank(claim) > _claim_quality_rank(current):
            best_by_key[key] = claim

    return sorted(
        best_by_key.values(),
        key=lambda claim: (-(claim.confidence or 0), str(claim.doc_id)),
    )


def get_entity_bundle(db: Session, entity_type: str, entity_id: str) -> dict[str, Any] | None:
    entity = (
        db.query(KBDocument)
        .filter(
            KBDocument.doc_type == "entity",
            KBDocument.entity_type == entity_type,
            KBDocument.entity_id == entity_id,
            *_serving_document_filters(),
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
                *_serving_document_filters(),
            )
            .order_by(KBDocument.confidence.desc().nullslast(), KBDocument.doc_id.asc())
            .all()
        )
        linked_claims = dedupe_semantic_claims(linked_claims)
    linked_claim_ids = {claim.doc_id for claim in linked_claims}
    response_edges = [
        edge
        for edge in edges
        if (edge.src_doc_id == entity.doc_id and edge.dst_doc_id in linked_claim_ids)
        or (edge.dst_doc_id == entity.doc_id and edge.src_doc_id in linked_claim_ids)
    ]

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
            for edge in response_edges
        ],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def get_claim_bundle(
    db: Session,
    claim_id: str,
    *,
    include_archived: bool = False,
) -> dict[str, Any] | None:
    claim = (
        db.query(KBDocument)
        .filter(
            KBDocument.doc_id == claim_id,
            KBDocument.doc_type == "claim",
        )
        .first()
    )
    if claim is None:
        return None
    if claim.is_archived and not include_archived:
        return None
    if not include_archived and (claim.metadata_json or {}).get("review_status") != "reviewed":
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
            .filter(KBDocument.doc_id.in_(neighbor_ids), *_serving_document_filters())
            .order_by(KBDocument.doc_type.asc(), KBDocument.doc_id.asc())
            .all()
        )
    neighbor_ids = {neighbor.doc_id for neighbor in neighbors}
    response_edges = [
        edge
        for edge in edges
        if (edge.src_doc_id == claim.doc_id and edge.dst_doc_id in neighbor_ids)
        or (edge.dst_doc_id == claim.doc_id and edge.src_doc_id in neighbor_ids)
    ]

    return {
        "claim": serialize_document(claim),
        "neighbors": [serialize_document(neighbor) for neighbor in neighbors],
        "edges": [_serialize_edge(edge) for edge in response_edges],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def update_claim_review(
    db: Session,
    claim_id: str,
    *,
    actor: str,
    review_status: str | None = None,
    evidence_level: str | None = None,
    confidence: float | None = None,
    external_source: dict[str, Any] | None = None,
    clear_candidate_duplicates: bool = False,
    resolve_feedback: bool = False,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Apply a governed reviewer decision to one compiled claim.

    This mutates serving metadata only. Raw course material and reviewed JSONL
    artifacts remain the source-of-truth authoring plane.
    """

    claim = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id == claim_id, KBDocument.doc_type == "claim")
        .first()
    )
    if claim is None:
        return None

    if review_status is not None and review_status not in VALID_REVIEW_STATUSES:
        raise ValueError(f"invalid review_status: {review_status}")

    before = {
        "review_status": (claim.metadata_json or {}).get("review_status"),
        "evidence_level": claim.evidence_level,
        "confidence": claim.confidence,
        "is_archived": claim.is_archived,
        "sources": list(claim.sources or []),
        "metadata": dict(claim.metadata_json or {}),
    }
    metadata = dict(claim.metadata_json or {})

    if review_status is not None:
        metadata["review_status"] = review_status
        claim.is_archived = review_status == "archived"
        if review_status == "reviewed":
            metadata["reviewed_at"] = datetime.now(UTC).isoformat()
            metadata["reviewed_by"] = actor
            claim.last_confirmed = datetime.now(UTC)
        elif review_status == "archived":
            metadata["archived_at"] = datetime.now(UTC).isoformat()
            metadata["archived_by"] = actor

    if evidence_level is not None:
        claim.evidence_level = evidence_level.strip().upper()
    if confidence is not None:
        claim.confidence = max(0.0, min(1.0, float(confidence)))

    if external_source:
        normalized_source = _normalize_external_source(external_source, actor=actor)
        if normalized_source:
            raw_external_sources = metadata.get("external_sources")
            existing = [
                source
                for source in (raw_external_sources if isinstance(raw_external_sources, list) else [])
                if isinstance(source, dict)
            ]
            source_key = normalized_source.get("source")
            if source_key and all(source.get("source") != source_key for source in existing):
                existing.append(normalized_source)
            metadata["external_sources"] = existing

            sources = list(claim.sources or [])
            if source_key and source_key not in sources:
                sources.append(str(source_key))
            claim.sources = sources

    if clear_candidate_duplicates:
        metadata["candidate_duplicates"] = []

    if resolve_feedback:
        metadata["feedback_resolution"] = {
            "resolved": True,
            "resolved_at": datetime.now(UTC).isoformat(),
            "resolved_by": actor,
            "note": note,
        }

    if note:
        metadata["review_note"] = note

    claim.metadata_json = metadata
    db.add(claim)
    db.flush()

    after = {
        "review_status": metadata.get("review_status"),
        "evidence_level": claim.evidence_level,
        "confidence": claim.confidence,
        "is_archived": claim.is_archived,
        "sources": list(claim.sources or []),
        "metadata": metadata,
    }
    db.add(
        KBAudit(
            doc_id=claim.doc_id,
            op="review_update",
            actor=actor,
            diff={
                "before": before,
                "after": after,
                "note": note,
                "clear_candidate_duplicates": clear_candidate_duplicates,
                "resolve_feedback": resolve_feedback,
            },
        )
    )
    db.commit()
    return get_claim_bundle(db, claim.doc_id, include_archived=True)


def _write_kb_observability_audit(db: Session, op: str, diff: dict[str, Any]) -> None:
    """Bypass audit writer for retrieval observability (kb_zero_hit / kb_citation_usage).

    Mirrors app/agents/audit.py: audit is a side channel — a failure here must
    NEVER break the calling retrieval/synthesis path. Logs a WARNING and rolls
    back on failure, then returns.
    """
    try:
        db.add(KBAudit(doc_id=None, op=op, actor="system", diff=diff))
        db.commit()
    except Exception as exc:  # noqa: BLE001 - audit is best-effort, never fail the caller
        logger.warning("[system_kb] %s audit write failed (bypassed): %s", op, exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def _claim_appears_in_text(title: str, entity_id: str, text: str) -> bool:
    """Cheap heuristic: did this KB claim visibly inform the answer text?

    Not exact attribution — an observability signal. A claim counts as "used" when
    its entity_id (e.g. a biomarker/drug id) or a distinctive term from its title
    surfaces in the answer:
      * English/numeric title tokens of length >= 3 → whole-token substring;
      * Chinese title spans → any 3-gram of the span appears in the answer
        (3-gram, not the whole sentence, since answers paraphrase).
    """
    if not text:
        return False
    haystack = text.lower()
    if entity_id and len(entity_id) >= 3 and entity_id.lower() in haystack:
        return True
    title = (title or "").strip()
    if not title:
        return False
    for token in re.findall(r"[A-Za-z0-9]{3,}", title):
        if token.lower() in haystack:
            return True
    for span in re.findall(r"[一-鿿]{3,}", title):
        for i in range(len(span) - 2):
            if span[i : i + 3] in text:
                return True
    return False


def record_kb_citation_usage(
    db: Session,
    provided_claim_ids: list[str],
    answer_text: str,
    *,
    source: str = "orchestrator",
) -> dict[str, Any] | None:
    """Bypass-audit how many provided KB claims visibly informed the final answer.

    ``provided`` = distinct claim doc_ids that were handed to the LLM as evidence.
    ``used`` = subset whose title/entity_id text appears in ``answer_text`` (cheap
    substring check). Writes op="kb_citation_usage". Never raises — audit failure
    must not affect the caller. Returns the diff dict (or None if nothing provided).
    """
    provided = _dedupe_preserve_order([cid for cid in (provided_claim_ids or []) if cid])
    if not provided:
        return None
    try:
        rows = (
            db.query(KBDocument.doc_id, KBDocument.title, KBDocument.entity_id)
            .filter(KBDocument.doc_id.in_(provided))
            .all()
        )
        meta = {r.doc_id: (r.title or "", r.entity_id or "") for r in rows}
        used_ids = [
            cid
            for cid in provided
            if _claim_appears_in_text(meta.get(cid, ("", ""))[0], meta.get(cid, ("", ""))[1], answer_text)
        ]
        diff = {
            "source": source,
            "provided": len(provided),
            "used": len(used_ids),
            "used_ids": used_ids,
        }
    except Exception as exc:  # noqa: BLE001 - resolution failure must not break synthesis
        logger.warning("[system_kb] kb_citation_usage computation failed (bypassed): %s", exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None

    _write_kb_observability_audit(db, op="kb_citation_usage", diff=diff)
    return diff


def search_knowledge(
    db: Session,
    query: str,
    *,
    limit: int = 10,
    doc_type: str | None = None,
    entity_type: str | None = None,
) -> dict[str, Any]:
    """DB-backed hybrid search for the serving KB.

    The serving implementation stays DB-only so it works with both local
    SQLite tests and production PostgreSQL. It fuses lexical, precomputed FTS
    text, semantic-alias, and one-hop graph streams using reciprocal-rank
    fusion. Production PostgreSQL can replace the alias stream with embeddings
    later without changing the response shape.
    """

    guarded_query = guard_retrieval_query(query)
    normalized_query = guarded_query.query
    terms = _query_terms(normalized_query)

    docs_query = db.query(KBDocument).filter(*_serving_document_filters())
    if doc_type:
        docs_query = docs_query.filter(KBDocument.doc_type == doc_type)
    if entity_type:
        docs_query = docs_query.filter(KBDocument.entity_type == entity_type)

    documents = docs_query.all()
    documents_by_id = {document.doc_id: document for document in documents}

    lexical_ranked: list[tuple[float, KBDocument]] = _bm25_rank_documents(documents, terms)
    fts_ranked: list[tuple[float, KBDocument]] = []
    vector_ranked, vector_backend = _rank_vector_documents(
        db,
        documents_by_id,
        normalized_query,
        limit=max(50, limit),
    )
    fts_backend = _fts_backend_for_session(db)
    postgres_fts_ranked: list[tuple[float, KBDocument]] = []
    if fts_backend == "postgres_tsv":
        postgres_fts_ranked = _postgres_fts_rank_documents(
            db,
            normalized_query,
            limit=max(50, limit),
            doc_type=doc_type,
            entity_type=entity_type,
        )
    for document in documents:
        if fts_backend != "postgres_tsv":
            fts_score = _score_precomputed_search_text(document, terms)
            if fts_score > 0 or not terms:
                fts_ranked.append((fts_score, document))
    if fts_backend == "postgres_tsv":
        fts_ranked = postgres_fts_ranked

    lexical_ranked.sort(key=lambda item: (-item[0], item[1].doc_type, item[1].doc_id))
    fts_ranked.sort(key=lambda item: (-item[0], item[1].doc_type, item[1].doc_id))
    vector_ranked.sort(key=lambda item: (-item[0], item[1].doc_type, item[1].doc_id))
    seed_limit = max(1, min(max(limit, 10), 50))
    seed_ids = {
        document.doc_id
        for ranked in (lexical_ranked, fts_ranked, vector_ranked)
        for _score, document in ranked[:seed_limit]
    }
    edges = []
    neighbors: list[KBDocument] = []
    graph_ranked: list[tuple[float, KBDocument]] = []
    graph_meta_by_doc: dict[str, dict[str, Any]] = {}
    if seed_ids:
        edges = (
            db.query(KBEdge)
            .filter(or_(KBEdge.src_doc_id.in_(seed_ids), KBEdge.dst_doc_id.in_(seed_ids)))
            .all()
        )
        edges = [
            edge
            for edge in edges
            if edge.src_doc_id in documents_by_id and edge.dst_doc_id in documents_by_id
        ]
        neighbor_ids = {
            edge.dst_doc_id if edge.src_doc_id in seed_ids else edge.src_doc_id
            for edge in edges
        }
        if neighbor_ids:
            neighbors = (
                db.query(KBDocument)
                .filter(KBDocument.doc_id.in_(neighbor_ids), *_serving_document_filters())
                .order_by(KBDocument.doc_type.asc(), KBDocument.doc_id.asc())
                .all()
            )
            for edge in edges:
                neighbor_id = edge.dst_doc_id if edge.src_doc_id in seed_ids else edge.src_doc_id
                document = documents_by_id.get(neighbor_id)
                if document is None:
                    continue
                edge_confidence = float(edge.confidence or 0.0)
                doc_confidence = float(document.confidence or 0.0)
                graph_score = 1.0 + edge_confidence + doc_confidence * 0.1
                graph_ranked.append((graph_score, document))
                meta = graph_meta_by_doc.setdefault(
                    document.doc_id,
                    {"graph_distance": 1, "relations": []},
                )
                if edge.relation not in meta["relations"]:
                    meta["relations"].append(edge.relation)
            graph_ranked.sort(key=lambda item: (-item[0], item[1].doc_type, item[1].doc_id))

    fused = _fuse_search_rankings(
        lexical_ranked,
        fts_ranked,
        vector_ranked,
        graph_ranked,
        graph_meta_by_doc,
    )
    selected = fused[: max(1, min(limit, 50))]

    # Observability: a zero-hit search is a KB coverage gap signal. Bypass-audit it
    # (never blocks the caller). channel_stats show which legs also came up empty.
    if not selected:
        _write_kb_observability_audit(
            db,
            op="kb_zero_hit",
            diff={
                "query": (normalized_query or "")[:200],
                "source": "search_knowledge",
                "channel_stats": {
                    "lexical": len(lexical_ranked),
                    "fts": len(fts_ranked),
                    "vector": len(vector_ranked),
                    "graph": len(graph_ranked),
                },
            },
        )

    return {
        "query": normalized_query,
        "results": [
            {
                "score": round(score, 4),
                "document": serialize_document(document),
                "retrieval": retrieval,
            }
            for score, document, retrieval in selected
        ],
        "graph_context": {
            "edges": [_serialize_edge(edge) for edge in edges],
            "neighbors": [serialize_document(neighbor) for neighbor in neighbors],
        },
        "retrieval_plan": {
            "channels": ["lexical", "fts", "vector", "graph"],
            "lexical_backend": "python_bm25_v1",
            "fts_backend": fts_backend,
            "vector_backend": vector_backend,
            "graph_backend": "kb_edges_one_hop",
            "rrf_backend": "python_rrf_v1",
            "input_guard": guarded_query.metadata(),
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _fts_backend_for_session(db: Session) -> str:
    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    dialect_name = getattr(dialect_name, "name", "")
    return "postgres_tsv" if dialect_name == "postgresql" else "sqlite_precomputed_text"


def _postgres_fts_rank_documents(
    db: Session,
    query: str,
    *,
    limit: int,
    doc_type: str | None,
    entity_type: str | None,
) -> list[tuple[float, KBDocument]]:
    """Use PostgreSQL tsvector search when serving on production Postgres."""

    normalized_query = (query or "").strip()
    if not normalized_query:
        return []

    # Segment the query into words before websearch_to_tsquery. With the indexed
    # text also segmented (_document_search_text), the "simple" config now matches
    # Chinese word-for-word instead of treating a whole multi-word clause as one
    # opaque token. No PG extension is installed. Falls back to the raw query if
    # jieba is unavailable (loud failure is the boot-time probe).
    tsquery_input = normalized_query
    try:
        from app.services.zh_tokenize import seg_text

        segmented_query = seg_text(normalized_query)
        if segmented_query:
            tsquery_input = segmented_query
    except Exception:  # noqa: BLE001
        logger.warning("[system_kb] jieba segmentation unavailable for FTS query; using raw query")

    ts_query = func.websearch_to_tsquery("simple", tsquery_input)
    rank = func.ts_rank_cd(KBDocument.tsv, ts_query)
    query_builder = (
        db.query(KBDocument, rank.label("rank"))
        .filter(*_serving_document_filters(), KBDocument.tsv.op("@@")(ts_query))
    )
    if doc_type:
        query_builder = query_builder.filter(KBDocument.doc_type == doc_type)
    if entity_type:
        query_builder = query_builder.filter(KBDocument.entity_type == entity_type)

    rows = query_builder.order_by(desc("rank"), KBDocument.doc_type.asc(), KBDocument.doc_id.asc()).limit(limit).all()
    return [(float(rank_value or 0.0), document) for document, rank_value in rows]


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
                *_serving_document_filters(),
                or_(*entity_filters),
            )
            .order_by(KBDocument.entity_type.asc(), KBDocument.entity_id.asc())
            .all()
        )

    matched_claims = []
    claims = (
        db.query(KBDocument)
        .filter(KBDocument.doc_type == "claim", *_serving_document_filters())
        .order_by(KBDocument.confidence.desc().nullslast(), KBDocument.doc_id.asc())
        .all()
    )
    matched_claim_ids: set[str] = set()
    for claim in claims:
        matched_conditions = _matched_conditions_for_claim(claim.applies_when or [], twin)
        if matched_conditions:
            matched_claims.append(
                serialize_document(
                    claim,
                    {
                        "matched_conditions": matched_conditions,
                        "match_type": "condition",
                    },
                )
            )
            matched_claim_ids.add(claim.doc_id)

    contextual_entities, graph_claims = _lookup_graph_context_for_entities(
        db,
        entities,
        excluded_claim_ids=matched_claim_ids,
    )
    matched_claims.extend(graph_claims)

    # Observability: a Twin lookup that matched no claim is a KB coverage gap for
    # the user's current state. Bypass-audit it (never blocks the caller).
    if not matched_claims:
        _write_kb_observability_audit(
            db,
            op="kb_zero_hit",
            diff={
                "query": ",".join(f"{et}:{eid}" for et, eid in sorted(entity_keys))[:200],
                "source": "lookup_for_twin",
                "channel_stats": {
                    "entity_keys": len(entity_keys),
                    "entities": len(entities),
                    "contextual_entities": len(contextual_entities),
                },
            },
        )

    return {
        "entities": [serialize_document(entity) for entity in entities],
        "contextual_entities": [serialize_document(entity) for entity in contextual_entities],
        "claims": matched_claims,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _matched_conditions_for_claim(conditions: list[str], twin: dict[str, Any]) -> list[str]:
    matched_conditions = [condition for condition in conditions if evaluate_condition(condition, twin)]
    if not matched_conditions:
        return []
    if _requires_all_condition_matches(conditions) and len(matched_conditions) != len(conditions):
        return []
    membership_conditions = [
        condition for condition in conditions
        if _HAS_RE.match((condition or "").strip())
        or _INTERSECTS_RE.match((condition or "").strip())
    ]
    if membership_conditions and len(matched_conditions) != len(conditions):
        return []
    return matched_conditions


def _requires_all_condition_matches(conditions: list[str]) -> bool:
    """High-risk genetic confirmation boundaries must not match on gene presence alone."""

    return any("_variant_class" in str(condition or "") for condition in conditions)


def _lookup_graph_context_for_entities(
    db: Session,
    entities: list[KBDocument],
    *,
    excluded_claim_ids: set[str],
) -> tuple[list[KBDocument], list[dict[str, Any]]]:
    """Promote claim context reachable from structured Twin entity matches."""

    direct_entity_ids = {entity.doc_id for entity in entities}
    if not direct_entity_ids:
        return [], []

    context_edges = (
        db.query(KBEdge)
        .filter(
            KBEdge.relation == "contextualizes",
            or_(KBEdge.src_doc_id.in_(direct_entity_ids), KBEdge.dst_doc_id.in_(direct_entity_ids)),
        )
        .all()
    )
    context_entity_ids = {
        edge.dst_doc_id if edge.src_doc_id in direct_entity_ids else edge.src_doc_id
        for edge in context_edges
        if (edge.dst_doc_id if edge.src_doc_id in direct_entity_ids else edge.src_doc_id).startswith("entity:")
    }
    contextual_entities = []
    if context_entity_ids:
        contextual_entities = (
            db.query(KBDocument)
            .filter(
                KBDocument.doc_id.in_(context_entity_ids),
                KBDocument.doc_type == "entity",
                *_serving_document_filters(),
            )
            .order_by(KBDocument.entity_type.asc(), KBDocument.entity_id.asc())
            .all()
        )

    candidate_entity_ids = {entity.doc_id for entity in contextual_entities}
    if not candidate_entity_ids:
        return contextual_entities, []

    claim_edges = (
        db.query(KBEdge)
        .filter(or_(KBEdge.src_doc_id.in_(candidate_entity_ids), KBEdge.dst_doc_id.in_(candidate_entity_ids)))
        .all()
    )
    claim_context_by_id: dict[str, dict[str, Any]] = {}
    for edge in claim_edges:
        if edge.src_doc_id in candidate_entity_ids and edge.dst_doc_id.startswith("claim:"):
            claim_id = edge.dst_doc_id
            via_entity = edge.src_doc_id
        elif edge.dst_doc_id in candidate_entity_ids and edge.src_doc_id.startswith("claim:"):
            claim_id = edge.src_doc_id
            via_entity = edge.dst_doc_id
        else:
            continue
        if claim_id in excluded_claim_ids:
            continue
        current = claim_context_by_id.get(claim_id)
        if current:
            continue
        claim_context_by_id[claim_id] = {
            "match_type": "graph_context",
            "matched_conditions": [],
            "matched_context": {
                "via_entity": via_entity,
                "relation": edge.relation,
                "source_claim_id": edge.source_claim_id,
            },
        }

    if not claim_context_by_id:
        return contextual_entities, []

    graph_claims = (
        db.query(KBDocument)
        .filter(
            KBDocument.doc_id.in_(claim_context_by_id.keys()),
            KBDocument.doc_type == "claim",
            *_serving_document_filters(),
        )
        .order_by(KBDocument.confidence.desc().nullslast(), KBDocument.doc_id.asc())
        .all()
    )
    return contextual_entities, [
        serialize_document(claim, claim_context_by_id[claim.doc_id])
        for claim in graph_claims
    ]


def reindex_knowledge_documents(db: Session, actor: str = "system") -> dict[str, int]:
    documents = db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).all()
    use_postgres_tsvector = _fts_backend_for_session(db) == "postgres_tsv"
    active_doc_ids = {document.doc_id for document in documents}
    searchable_by_doc_id: dict[str, tuple[str, str]] = {}
    pgvector_table_ready = _ensure_pgvector_table(db)
    for document in documents:
        searchable = _document_search_text(document)
        content_hash = hashlib.sha256(searchable.encode("utf-8")).hexdigest()
        searchable_by_doc_id[document.doc_id] = (searchable, content_hash)
        _upsert_document_vector(db, document.doc_id, searchable, content_hash)
        if use_postgres_tsvector:
            db.execute(_build_postgres_reindex_statement(document.doc_id, searchable, content_hash))
            continue
        document.tsv = searchable
        document.content_hash = content_hash

    dense_vectors = _reindex_pgvector_documents(
        db,
        searchable_by_doc_id,
        table_ready=pgvector_table_ready,
    )

    if active_doc_ids:
        db.query(KBDocumentVector).filter(KBDocumentVector.doc_id.notin_(active_doc_ids)).delete(
            synchronize_session=False
        )
    else:
        db.query(KBDocumentVector).delete(synchronize_session=False)

    db.add(
        KBAudit(
            doc_id=None,
            op="reindex",
            actor=actor,
            diff={
                "documents": len(documents),
                "vector_backend": VECTOR_BACKEND,
                "dense_vector_backend": _pgvector_backend_name(),
                "dense_vectors": dense_vectors,
            },
        )
    )
    db.commit()
    return {"documents": len(documents), "dense_vectors": dense_vectors}


def run_system_kb_reindex_report(db: Session, actor: str = "system") -> dict[str, Any]:
    """Rebuild KB search indexes and persist an operations-grade health report."""

    reindex = reindex_knowledge_documents(db, actor=actor)
    pgvector = get_system_kb_pgvector_health(db)
    report = {
        "reindex": reindex,
        "pgvector": {
            key: value
            for key, value in pgvector.items()
            if key != "latest_reindex_report"
        },
    }
    db.add(
        KBAudit(
            doc_id=None,
            op="system_kb_reindex_report",
            actor=actor,
            diff=report,
        )
    )
    db.commit()
    return report


def _build_postgres_reindex_statement(doc_id: str, searchable: str, content_hash: str):
    return (
        update(KBDocument)
        .where(KBDocument.doc_id == doc_id)
        .values(
            tsv=func.to_tsvector("simple", searchable),
            content_hash=content_hash,
        )
    )


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


def get_knowledge_coverage_report(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Aggregate system KB coverage signals for admin review dashboards."""
    documents = db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).all()
    current_time = _ensure_aware(now or datetime.now(UTC))
    by_type: dict[str, int] = {}
    by_review_status: dict[str, int] = {}
    by_evidence_level: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    for document in documents:
        by_type[document.doc_type] = by_type.get(document.doc_type, 0) + 1
        if document.evidence_level:
            by_evidence_level[document.evidence_level] = by_evidence_level.get(document.evidence_level, 0) + 1
        metadata = document.metadata_json or {}
        review_status = str(metadata.get("review_status") or "unreviewed")
        by_review_status[review_status] = by_review_status.get(review_status, 0) + 1
        origin = str(metadata.get("origin") or "unknown")
        by_origin[origin] = by_origin.get(origin, 0) + 1

    return {
        "documents": {
            "total": len(documents),
            "by_type": dict(sorted(by_type.items())),
            "by_review_status": dict(sorted(by_review_status.items())),
            "by_evidence_level": dict(sorted(by_evidence_level.items())),
            "by_origin": dict(sorted(by_origin.items())),
        },
        "external_evidence": _aggregate_external_evidence_coverage(documents),
        "domain_coverage": _aggregate_domain_coverage(documents, now=current_time),
        "protocol_review": _aggregate_protocol_review_coverage(documents),
        "specialist_findings": _aggregate_specialist_evidence_coverage(db),
        "notification_evidence": _aggregate_notification_evidence_coverage(db),
        "feedback": {
            "disagree": db.query(KBAudit).filter(KBAudit.op == "feedback_disagree").count(),
        },
        # 融合可见:entity_type × origin 覆盖矩阵 + 权威校验(count 不变量)+ 跨源重复候选。
        # 懒导入断循环(coverage 模块反向引用本 service 的 _normalize_knowledge_text)。
        "coverage_matrix": _coverage_matrix(db),
    }


def _coverage_matrix(db: Session) -> dict[str, Any]:
    from app.services.system_knowledge_coverage import build_coverage_matrix

    return build_coverage_matrix(db)


def _aggregate_domain_coverage(
    documents: list[KBDocument],
    *,
    now: datetime,
) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {}
    claim_domains: dict[str, set[str]] = {}
    eval_claim_ids: set[str] = set()

    for document in documents:
        domains = _document_domains(document)
        if document.doc_type == "claim":
            claim_domains[document.doc_id] = set(domains)
        if document.doc_type == "eval_case":
            eval_claim_ids.update(_eval_case_required_claim_ids(document))

        for domain in domains:
            bucket = _domain_coverage_bucket(buckets, domain)
            _add_domain_document(bucket, document, now=now)

    for claim_id, domains in claim_domains.items():
        for domain in domains:
            _domain_coverage_bucket(buckets, domain)["eval_coverage"]["_claim_ids"].add(claim_id)

    for claim_id in eval_claim_ids:
        for domain in claim_domains.get(claim_id, set()):
            _domain_coverage_bucket(buckets, domain)["eval_coverage"]["_covered_claim_ids"].add(
                claim_id
            )

    return {
        domain: _finalize_domain_coverage_bucket(bucket)
        for domain, bucket in sorted(buckets.items())
    }


def _domain_coverage_bucket(
    buckets: dict[str, dict[str, Any]],
    domain: str,
) -> dict[str, Any]:
    return buckets.setdefault(
        domain,
        {
            "documents": {"total": 0, "by_type": Counter()},
            "review_status": Counter(),
            "source_coverage": {
                "claim_total": 0,
                "claims_with_external_sources": 0,
                "by_kind": Counter(),
                "missing_external_source_claims": [],
            },
            "source_freshness": {
                "source_total": 0,
                "stale_sources": 0,
                "missing_last_reviewed_sources": 0,
                "by_kind": Counter(),
                "items": [],
                "_seen_sources": set(),
            },
            "eval_coverage": {
                "eval_cases_total": 0,
                "_claim_ids": set(),
                "_covered_claim_ids": set(),
            },
            "stale_risk": {
                "claim_total": 0,
                "stale_claims": 0,
                "missing_last_confirmed_claims": 0,
                "by_decay_rate": {"fast": 0, "normal": 0, "slow": 0},
                "items": [],
            },
        },
    )


def _add_domain_document(bucket: dict[str, Any], document: KBDocument, *, now: datetime) -> None:
    bucket["documents"]["total"] += 1
    bucket["documents"]["by_type"][document.doc_type] += 1
    review_status = str((document.metadata_json or {}).get("review_status") or "unreviewed")
    bucket["review_status"][review_status] += 1

    if document.doc_type == "eval_case":
        bucket["eval_coverage"]["eval_cases_total"] += 1

    if document.doc_type != "claim":
        return

    source_coverage = bucket["source_coverage"]
    source_coverage["claim_total"] += 1
    external_sources = _document_external_sources(document)
    if external_sources:
        source_coverage["claims_with_external_sources"] += 1
    elif review_status == "reviewed":
        source_coverage["missing_external_source_claims"].append(_compact_issue(document))
    for source in external_sources:
        kind = str(source.get("kind") or "other")
        source_coverage["by_kind"][kind] += 1
        _add_domain_source_freshness(
            bucket["source_freshness"],
            source,
            document,
            now=now,
        )

    _add_domain_stale_risk(bucket["stale_risk"], document, now=now, review_status=review_status)


def _add_domain_source_freshness(
    source_freshness: dict[str, Any],
    source: dict[str, Any],
    document: KBDocument,
    *,
    now: datetime,
) -> None:
    source_key = str(source.get("source") or "").strip()
    if not source_key:
        return
    kind = str(source.get("kind") or source_detail(source_key).get("kind") or "other")
    seen_key = (kind, source_key)
    seen_sources = source_freshness.setdefault("_seen_sources", set())
    if seen_key in seen_sources:
        return
    seen_sources.add(seen_key)

    source_freshness["source_total"] += 1
    source_freshness["by_kind"][kind] += 1

    raw_reviewed_at = (
        source.get("last_reviewed_at")
        or source.get("reviewed_at")
        or source.get("last_confirmed_at")
    )
    reviewed_date = _date_from_value(raw_reviewed_at)
    if reviewed_date is None:
        source_freshness["missing_last_reviewed_sources"] += 1
        source_freshness["items"].append(
            {
                "source": source_key,
                "kind": kind,
                "reason": "missing_last_reviewed_at",
                "doc_id": document.doc_id,
                "title": document.title,
            }
        )
        return

    window_days = SOURCE_FRESHNESS_WINDOWS_DAYS.get(kind, SOURCE_FRESHNESS_WINDOWS_DAYS["other"])
    days_since_reviewed = (now.date() - reviewed_date).days
    if days_since_reviewed <= window_days:
        return

    source_freshness["stale_sources"] += 1
    source_freshness["items"].append(
        {
            "source": source_key,
            "kind": kind,
            "reason": "stale_source",
            "doc_id": document.doc_id,
            "title": document.title,
            "last_reviewed_at": reviewed_date.isoformat(),
            "days_since_reviewed": days_since_reviewed,
            "freshness_window_days": window_days,
        }
    )


def _add_domain_stale_risk(
    stale_risk: dict[str, Any],
    document: KBDocument,
    *,
    now: datetime,
    review_status: str,
) -> None:
    stale_risk["claim_total"] += 1
    if not document.last_confirmed:
        stale_risk["missing_last_confirmed_claims"] += 1
        return

    windows = {
        "fast": timedelta(days=30),
        "normal": timedelta(days=120),
        "slow": timedelta(days=365),
    }
    decay_rate = str(document.decay_rate or "normal")
    window = windows.get(decay_rate, windows["normal"])
    last_confirmed = _ensure_aware(document.last_confirmed)
    if last_confirmed >= now - window:
        return

    stale_risk["stale_claims"] += 1
    stale_risk["by_decay_rate"][decay_rate] = stale_risk["by_decay_rate"].get(decay_rate, 0) + 1
    stale_risk["items"].append(
        {
            **_compact_issue(document),
            "review_status": review_status,
            "decay_rate": decay_rate,
            "last_confirmed": last_confirmed.isoformat(),
            "days_since_confirmed": (now.date() - last_confirmed.date()).days,
        }
    )


def _finalize_domain_coverage_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    source_coverage = bucket["source_coverage"]
    claim_total = int(source_coverage.get("claim_total") or 0)
    claims_with_external_sources = int(source_coverage.get("claims_with_external_sources") or 0)

    eval_coverage = bucket["eval_coverage"]
    claim_ids = set(eval_coverage.pop("_claim_ids", set()))
    covered_claim_ids = set(eval_coverage.pop("_covered_claim_ids", set())) & claim_ids
    eval_claim_total = len(claim_ids)
    claims_with_eval = len(covered_claim_ids)

    source_coverage["external_source_rate"] = (
        round(claims_with_external_sources / claim_total, 4) if claim_total else 0.0
    )
    source_coverage["by_kind"] = dict(sorted(source_coverage["by_kind"].items()))
    source_coverage["missing_external_source_claims"].sort(
        key=lambda item: str(item.get("doc_id") or "")
    )
    source_coverage["missing_external_source_claims"] = source_coverage[
        "missing_external_source_claims"
    ][:10]

    eval_coverage["claim_total"] = eval_claim_total
    eval_coverage["claims_with_eval"] = claims_with_eval
    eval_coverage["eval_coverage_rate"] = (
        round(claims_with_eval / eval_claim_total, 4) if eval_claim_total else 0.0
    )
    eval_coverage["missing_eval_claims"] = sorted(claim_ids - covered_claim_ids)[:10]

    source_freshness = bucket["source_freshness"]
    source_freshness.pop("_seen_sources", None)
    source_freshness["by_kind"] = dict(sorted(source_freshness["by_kind"].items()))
    source_freshness["items"].sort(
        key=lambda item: (
            str(item.get("kind") or ""),
            str(item.get("source") or ""),
            str(item.get("doc_id") or ""),
        )
    )
    source_freshness["items"] = source_freshness["items"][:10]

    bucket["stale_risk"]["items"].sort(key=lambda item: str(item.get("doc_id") or ""))
    bucket["stale_risk"]["items"] = bucket["stale_risk"]["items"][:10]
    bucket["stale_risk"]["by_decay_rate"] = dict(sorted(bucket["stale_risk"]["by_decay_rate"].items()))
    bucket["documents"]["by_type"] = dict(sorted(bucket["documents"]["by_type"].items()))
    bucket["review_status"] = dict(sorted(bucket["review_status"].items()))
    return bucket


def _document_domains(document: KBDocument) -> list[str]:
    metadata = document.metadata_json or {}
    raw_domains = metadata.get("domains")
    domains: list[str] = []
    if isinstance(raw_domains, list):
        domains.extend(str(item).strip() for item in raw_domains if str(item).strip())
    domain = str(metadata.get("domain") or "").strip()
    if domain:
        domains.append(domain)
    if not domains and document.entity_type:
        domains.append(str(document.entity_type))
    if not domains:
        domains.append("unknown")
    return sorted(set(domains))


def _eval_case_required_claim_ids(document: KBDocument) -> set[str]:
    metadata = document.metadata_json or {}
    expected = metadata.get("expected") if isinstance(metadata.get("expected"), dict) else {}
    required_ids: set[str] = set()
    for key in ("required_claim_ids", "required_doc_ids"):
        values = expected.get(key)
        if isinstance(values, list):
            required_ids.update(str(value) for value in values if str(value).startswith("claim:"))
    return required_ids


def get_knowledge_review_queue(
    db: Session,
    *,
    limit: int = 100,
    reason: str | None = None,
    review_status: str | None = None,
) -> dict[str, Any]:
    """Return claim-level items that need human system-KB review.

    This is the serving-plane counterpart of the offline PR-style diff. It only
    exposes transformed claim metadata and reviewer reasons, never raw course
    text.
    """

    feedback_counts = {
        str(doc_id): int(count)
        for doc_id, count in (
            db.query(KBAudit.doc_id, func.count(KBAudit.id))
            .filter(KBAudit.op == "feedback_disagree", KBAudit.doc_id.isnot(None))
            .group_by(KBAudit.doc_id)
            .all()
        )
        if doc_id
    }
    claims = (
        db.query(KBDocument)
        .filter(KBDocument.doc_type == "claim", KBDocument.is_archived.is_(False))
        .all()
    )
    items: list[dict[str, Any]] = []
    by_reason: dict[str, int] = {}
    by_review_status: dict[str, int] = {}

    for claim in claims:
        metadata = claim.metadata_json or {}
        status = str(metadata.get("review_status") or "unreviewed")
        candidate_duplicates = [
            str(item)
            for item in (metadata.get("candidate_duplicates") or [])
            if item
        ]
        external_sources = _document_external_sources(claim)
        feedback_disagree_count = feedback_counts.get(claim.doc_id, 0)
        reasons = _review_queue_reasons(
            review_status=status,
            external_source_count=len(external_sources),
            candidate_duplicates=candidate_duplicates,
            feedback_disagree_count=feedback_disagree_count,
        )
        if not reasons:
            continue
        if reason and reason not in reasons:
            continue
        if review_status and status != review_status:
            continue

        for queue_reason in reasons:
            by_reason[queue_reason] = by_reason.get(queue_reason, 0) + 1
        by_review_status[status] = by_review_status.get(status, 0) + 1
        items.append(
            {
                "doc_id": claim.doc_id,
                "title": claim.title,
                "entity_type": claim.entity_type,
                "entity_id": claim.entity_id,
                "evidence_level": claim.evidence_level,
                "confidence": claim.confidence,
                "review_status": status,
                "reasons": reasons,
                "sources": claim.sources or [],
                "external_source_count": len(external_sources),
                "candidate_duplicates": candidate_duplicates,
                "feedback_disagree_count": feedback_disagree_count,
                "updated_at": claim.updated_at.isoformat() if claim.updated_at else None,
                "created_at": claim.created_at.isoformat() if claim.created_at else None,
            }
        )

    items.sort(key=_review_queue_sort_key)
    limited_items = items[:limit]
    return {
        "summary": {
            "total": len(items),
            "returned": len(limited_items),
            "by_reason": dict(sorted(by_reason.items())),
            "by_review_status": dict(sorted(by_review_status.items())),
        },
        "items": limited_items,
        "filters": {
            "reason": reason,
            "review_status": review_status,
            "limit": limit,
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def get_knowledge_operations_dashboard(db: Session) -> dict[str, Any]:
    """Single admin-facing snapshot for KB governance operations."""

    coverage = get_knowledge_coverage_report(db)
    lint = lint_knowledge_base(db)
    latest_lifecycle = _latest_lifecycle_report(db)
    latest_dedao_sync = _latest_dedao_kbase_export_sync_draft(db)
    pgvector = get_system_kb_pgvector_health(db)
    action_items = _knowledge_operations_action_items(
        coverage,
        lint,
        latest_lifecycle,
        latest_dedao_sync,
        pgvector,
    )
    return {
        "status": "ok" if not action_items else "attention",
        "coverage": coverage,
        "lint": lint,
        "latest_lifecycle_report": latest_lifecycle,
        "latest_dedao_kbase_export_sync": latest_dedao_sync,
        "pgvector": pgvector,
        "action_items": action_items,
    }


def get_dedao_kbase_draft_review_bundle(
    *,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
    preview_limit: int = 20,
) -> dict[str, Any]:
    """Return a bounded review preview for configured dedao-kbase draft artifacts."""
    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    with review_workspace_lock(root):
        _require_system_kb_artifact_dir(root)
        _require_valid_review_workspace(root)
        gate = validate_artifact_review_gate(root)
        manifest = _read_json_file(root / "manifest.json")
        return {
            "artifact_dir": str(root),
            "workspace_fingerprint": workspace_content_fingerprint(root),
            "gate": gate,
            "draft_manifest": _read_json_file(root / "draft_manifest.json"),
            "manifest": {
                "ingest": manifest.get("ingest") if isinstance(manifest.get("ingest"), dict) else None,
                "draft_gate": manifest.get("draft_gate") if isinstance(manifest.get("draft_gate"), dict) else None,
                "review": manifest.get("review") if isinstance(manifest.get("review"), dict) else None,
                "counts": manifest.get("counts") if isinstance(manifest.get("counts"), dict) else None,
                "diff": manifest.get("diff") if isinstance(manifest.get("diff"), dict) else None,
            },
            "preview": _artifact_preview(root, limit=preview_limit),
        }


def list_dedao_kbase_review_claims(
    *,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
    offset: int = 0,
    limit: int = 50,
    decision: str | None = None,
) -> dict[str, Any]:
    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    _require_system_kb_artifact_dir(root)
    return list_review_claims(root, offset=offset, limit=limit, decision=decision)


def adjudicate_dedao_kbase_review_claim(
    *,
    doc_id: str,
    decision: str,
    reviewer: str,
    expected_workspace_fingerprint: str,
    note: str | None = None,
    evidence: dict[str, Any] | None = None,
    evidence_level: str | None = None,
    confidence: float | None = None,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
) -> dict[str, Any]:
    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    _require_system_kb_artifact_dir(root)
    return adjudicate_review_claim(
        root,
        doc_id=doc_id,
        decision=decision,
        reviewer=reviewer,
        expected_workspace_fingerprint=expected_workspace_fingerprint,
        note=note,
        evidence=evidence,
        evidence_level=evidence_level,
        confidence=confidence,
    )


def generate_dedao_kbase_review_verification_packet(
    *,
    doc_id: str,
    expected_workspace_fingerprint: str,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
) -> dict[str, Any]:
    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    _require_system_kb_artifact_dir(root)
    return generate_review_verification_packet(
        root,
        doc_id=doc_id,
        expected_workspace_fingerprint=expected_workspace_fingerprint,
    )


def list_dedao_kbase_review_verification_packets(
    *,
    doc_id: str,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
) -> dict[str, Any]:
    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    _require_system_kb_artifact_dir(root)
    return list_review_verification_packets(root, doc_id=doc_id)


def apply_dedao_kbase_review_verification_packet(
    *,
    doc_id: str,
    packet_id: str,
    reviewer: str,
    expected_workspace_fingerprint: str,
    note: str | None = None,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
) -> dict[str, Any]:
    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    _require_system_kb_artifact_dir(root)
    packet_list = list_review_verification_packets(root, doc_id=doc_id)
    if packet_list["workspace_fingerprint"] != expected_workspace_fingerprint:
        raise ValueError("dedao-kbase review workspace changed since preview; reload before approval")
    packet = next(
        (item for item in packet_list["items"] if item.get("packet_id") == packet_id),
        None,
    )
    if packet is None:
        raise ValueError("verification packet not found")
    if packet.get("stale"):
        raise ValueError("verification packet is stale; reload before approval")
    if packet.get("status") != "ready":
        raise ValueError("verification packet is not eligible for application")
    decision = str(packet.get("proposed_decision") or "")
    if decision not in {"approve", "needs_evidence", "reject", "background_only"}:
        raise ValueError("verification packet has an invalid proposed decision")
    result = adjudicate_review_claim(
        root,
        doc_id=doc_id,
        decision=decision,
        reviewer=reviewer,
        expected_workspace_fingerprint=expected_workspace_fingerprint,
        note=note,
    )
    result["packet_id"] = packet_id
    return result


def approve_dedao_kbase_draft_review(
    *,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
    reviewer: str,
    expected_workspace_fingerprint: str,
) -> dict[str, Any]:
    """Finalize configured artifacts after every draft claim is adjudicated."""
    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    _require_system_kb_artifact_dir(root)
    result = finalize_review_workspace(
        root,
        reviewer=reviewer,
        expected_workspace_fingerprint=expected_workspace_fingerprint,
    )
    result["approved_workspace_fingerprint"] = result["previous_workspace_fingerprint"]
    return result


def publish_dedao_kbase_reviewed_artifacts(
    db: Session,
    *,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
    actor: str = "system",
) -> dict[str, Any]:
    """Import reviewed dedao-kbase artifacts into serving KB and refresh indexes."""

    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    with review_workspace_lock(root):
        _require_system_kb_artifact_dir(root)
        _require_valid_review_workspace(root)
        gate = validate_artifact_review_gate(root)
        if not gate.get("serving_allowed"):
            reasons = ", ".join(str(reason) for reason in gate.get("blocking_reasons") or [])
            raise ValueError(f"dedao-kbase artifacts are not reviewed for serving: {reasons}")

        from app.services.system_knowledge_importer import import_system_kb_artifacts

        import_report = import_system_kb_artifacts(db, root, actor=actor)
        reindex_report = run_system_kb_reindex_report(db, actor=actor)
        return {
            "artifact_dir": str(root),
            "import": import_report,
            "reindex": reindex_report,
        }


def preview_dedao_kbase_reviewed_artifacts_publish(
    db: Session,
    *,
    artifact_dir: str | Path | None = None,
    workspace: str = "release",
) -> dict[str, Any]:
    """Preview reviewed dedao-kbase artifact import/reindex impact without serving mutation."""

    root = _configured_system_kb_artifact_dir(artifact_dir, workspace=workspace)
    with review_workspace_lock(root):
        _require_system_kb_artifact_dir(root)
        _require_valid_review_workspace(root)
        gate = validate_artifact_review_gate(root)
        if not gate.get("serving_allowed"):
            reasons = ", ".join(str(reason) for reason in gate.get("blocking_reasons") or [])
            raise ValueError(f"dedao-kbase artifacts are not reviewed for serving: {reasons}")

        import_preview = _preview_reviewed_artifact_import(db, root)
        pgvector = get_system_kb_pgvector_health(db)
        return {
            "dry_run": True,
            "artifact_dir": str(root),
            "gate": gate,
            "import": import_preview,
            "reindex": {
                "would_run": True,
                "current": {
                    "expected_documents": pgvector.get("expected_documents"),
                    "embedding_rows": pgvector.get("embedding_rows"),
                    "current_vector_backend": pgvector.get("current_vector_backend"),
                    "latest_reindex_report": pgvector.get("latest_reindex_report"),
                },
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


def system_kb_twin_payload_from_health_twin(twin: Any) -> dict[str, Any]:
    """Map HealthTwin into the compact condition namespace used by KB claims.

    The KB contract is intentionally small and stable (`twin.genetics.*`,
    `twin.labs.*`, `twin.goals.*`). Keeping this mapper in the KB service avoids
    each agent path drifting into a slightly different interpretation.
    """

    labs = getattr(twin, "labs", None)
    physiological = getattr(twin, "physiological", None)
    behavioral = getattr(twin, "behavioral", None)
    chronic = getattr(twin, "chronic", None)
    medication = getattr(twin, "medication", None)
    supplement = getattr(twin, "supplement", None)
    goals_state = getattr(twin, "goals", None)
    acute = getattr(twin, "acute", None)

    goals_text = " ".join(
        str(goal.get("name") or goal.get("title") or goal.get("goal_type") or goal)
        for goal in getattr(goals_state, "active_goals", []) or []
        if isinstance(goal, dict)
    )
    goals = {
        "weight_loss": {"active": any(token in goals_text for token in ("减重", "减肥", "体重", "腰围"))},
        "metabolic_health": {
            "active": any(token in goals_text for token in ("代谢", "血糖", "血脂", "血压", "尿酸", "健康"))
        },
        "sleep": {"active": any(token in goals_text for token in ("睡眠", "恢复", "精力"))},
        "longevity": {"active": any(token in goals_text for token in ("长寿", "衰老", "抗衰", "老化"))},
    }

    active_meds = getattr(medication, "active_meds", []) if medication is not None else []

    return {
        "genetics": _system_kb_genetics_from_health_twin(twin),
        "labs": {
            "hba1c_percent": getattr(labs, "hba1c", None),
            "fasting_glucose_mmol_l": getattr(labs, "blood_glucose", None),
            "ldl_c_mmol_l": getattr(labs, "ldl", None),
            "triglycerides_mmol_l": getattr(labs, "triglycerides", None),
            "systolic_bp": getattr(labs, "blood_pressure_systolic", None),
            "diastolic_bp": getattr(labs, "blood_pressure_diastolic", None),
            "uric_acid_umol_l": getattr(labs, "uric_acid", None),
            "eGFR": getattr(labs, "egfr", None),
        },
        "wearable": {
            "sleep_duration_hours": getattr(physiological, "sleep_duration_h_latest", None),
            "hrv_latest": getattr(physiological, "hrv_latest", None),
            "resting_hr": getattr(physiological, "resting_hr", None),
            "spo2_avg": getattr(physiological, "spo2_avg", None),
            "spo2_min_overnight": getattr(physiological, "spo2_min_overnight", None),
            "spo2_odi": getattr(physiological, "spo2_odi", None),
            "spo2_below_90_pct": getattr(physiological, "spo2_below_90_pct", None),
            "training_readiness_score": getattr(physiological, "training_readiness_score", None),
            "training_readiness_level": getattr(physiological, "training_readiness_level", None),
        },
        "behavioral": {
            "diet_calories_today": getattr(behavioral, "diet_calories_today", None),
            "diet_protein_g_today": getattr(behavioral, "diet_protein_g_today", None),
            "diet_carbs_g_today": getattr(behavioral, "diet_carbs_g_today", None),
            "diet_sodium_mg_today": getattr(behavioral, "diet_sodium_mg_today", None),
            "high_sodium_foods_today": getattr(behavioral, "high_sodium_foods_today", []),
            "water_ml_today": getattr(behavioral, "water_ml_today", None),
            "water_goal_ml": getattr(behavioral, "water_goal_ml", None),
            "water_progress_pct": getattr(behavioral, "water_progress_pct", None),
            "training_load_7d": getattr(behavioral, "training_load_7d", None),
            "acute_chronic_ratio": getattr(behavioral, "acute_chronic_ratio", None),
            "acwr_zone": getattr(behavioral, "acwr_zone", None),
        },
        "acute": {
            "has_active_illness": bool(getattr(acute, "has_active_illness", False)),
            "illness_names": getattr(acute, "illness_names", []) if acute is not None else [],
            "illness_severity_max": getattr(acute, "illness_severity_max", None),
            "symptoms": (
                _dedupe_preserve_order(
                    list(getattr(acute, "recent_symptoms", []) or [])
                    + list(getattr(acute, "symptom_texts_all", []) or [])
                )
                if acute is not None
                else []
            ),
            "suspected_cold": bool(getattr(acute, "suspected_cold", False)),
            "fever_reported": bool(getattr(acute, "fever_reported", False)),
            "should_rest_from_training": bool(getattr(acute, "should_rest_from_training", False)),
            "training_guardrail": getattr(acute, "training_guardrail", None),
        },
        "conditions": {
            "active": getattr(chronic, "active_conditions", []) if chronic is not None else [],
            "rhinitis": {
                "active": bool(
                    (getattr(chronic, "rhinitis_today", None) if chronic is not None else None)
                    or any(
                        "rhinitis" in str(condition).lower() or "鼻炎" in str(condition)
                        for condition in (getattr(chronic, "active_conditions", []) if chronic is not None else [])
                    )
                ),
            },
        },
        "medications": active_meds,
        "medication_context": _system_kb_medication_context_from_health_twin(twin, active_meds),
        "supplements": getattr(supplement, "active_supplements", []) if supplement is not None else [],
        "goals": goals,
    }


def _system_kb_medication_context_from_health_twin(
    twin: Any,
    active_meds: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    generated_at = getattr(getattr(twin, "meta", None), "generated_at", None)
    reference_date = _date_from_value(generated_at) or datetime.now(UTC).date()
    acid_suppression_seen = False
    acid_suppression_names: list[str] = []
    acid_suppression_weeks: list[float] = []

    for med in active_meds or []:
        if not isinstance(med, dict):
            continue
        if not _is_acid_suppression_med(med):
            continue
        acid_suppression_seen = True
        name = str(med.get("name") or med.get("generic_name") or med.get("drug_name") or "").strip()
        if name:
            acid_suppression_names.append(name)
        start_date = _date_from_value(
            med.get("start_date")
            or med.get("started_at")
            or med.get("startDate")
            or med.get("startedAt")
        )
        if start_date is None or start_date > reference_date:
            continue
        acid_suppression_weeks.append((reference_date - start_date).days / 7)

    return {
        "acid_suppression_active": acid_suppression_seen,
        "acid_suppression_names": _dedupe_preserve_order(acid_suppression_names),
        "acid_suppression_weeks_max": max(acid_suppression_weeks) if acid_suppression_weeks else None,
    }


def _is_acid_suppression_med(med: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(med.get(key) or "")
        for key in ("name", "generic_name", "drug_name", "medication_name", "title", "label", "class")
    ).lower()
    return any(token in haystack for token in _ACID_SUPPRESSION_MED_TOKENS)


def _date_from_value(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _system_kb_genetics_from_health_twin(twin: Any) -> dict[str, Any]:
    genetic = getattr(twin, "genetic", None)
    if genetic is None:
        return {}

    variants: list[dict[str, Any]] = []
    for attr in (
        "drug_sensitivity",
        "risk_variants",
        "protective_variants",
        "nutrition_variants",
        "recovery_variants",
        "exercise_variants",
        "cognition_variants",
        "personality_variants",
        "sleep_variants",
    ):
        values = getattr(genetic, attr, None) or []
        variants.extend(item for item in values if isinstance(item, dict))

    out: dict[str, Any] = {}
    for variant in variants:
        gene = str(variant.get("gene_name") or "").upper()
        genotype = str(variant.get("genotype") or "").upper()
        risk_level = str(variant.get("risk_level") or "").lower()
        result_label = str(variant.get("result_label") or "").lower()
        is_risk = risk_level in {"medium", "high"} or any(
            token in result_label for token in ("减弱", "下降", "风险", "poor", "reduced")
        )

        if gene == "MTHFR":
            if "TT" in genotype:
                out["MTHFR_C677T"] = "TT"
            elif "CT" in genotype:
                out["MTHFR_C677T"] = "CT"
            elif "CC" in genotype:
                out["MTHFR_C677T"] = "CC"
            elif is_risk:
                out["MTHFR_C677T"] = "CT"
            out["MTHFR"] = genotype or "present"
        elif gene == "APOE":
            out["APOE"] = genotype or "present"
        elif gene == "9P21":
            out["9p21"] = genotype or "present"
            out["rs10757274"] = genotype or "present"
        elif gene in {"FTO", "ACTN3"}:
            out[gene] = genotype or "present"
        elif gene == "ALDH2":
            out["ALDH2"] = genotype or ("GA" if is_risk else "present")
        elif gene in {"CYP2C19", "CYP2D6", "CYP2C9"}:
            out[gene] = genotype or "present"
            phenotype = _infer_pgx_phenotype(gene, genotype, result_label, risk_level)
            if phenotype:
                out[f"{gene}_phenotype"] = phenotype
        elif gene in {"TPMT", "NUDT15"}:
            out[gene] = genotype or "present"
            phenotype, function = _infer_thiopurine_pgx_status(gene, genotype, result_label, risk_level)
            if phenotype:
                out[f"{gene}_phenotype"] = phenotype
            if function:
                out["TPMT_activity" if gene == "TPMT" else "NUDT15_function"] = function
        elif gene == "DPYD":
            out["DPYD"] = genotype or "present"
            phenotype, activity_score = _infer_dpyd_pgx_status(genotype, result_label, risk_level)
            if phenotype:
                out["DPYD_phenotype"] = phenotype
            if activity_score:
                out["DPD_activity_score"] = activity_score
        elif gene == "SLCO1B1":
            out["SLCO1B1"] = genotype or "present"
            if genotype in {"CT", "CC", "TT"}:
                out["SLCO1B1_rs4149056"] = genotype
        elif gene == "VKORC1":
            out["VKORC1"] = genotype or "present"
            vkorc1_genotype = _normalize_vkorc1_genotype(genotype, result_label, risk_level)
            if vkorc1_genotype:
                out["VKORC1_1639G_A"] = vkorc1_genotype
                out["VKORC1_rs9923231"] = vkorc1_genotype
        elif gene == "HLA-A":
            out["HLA-A"] = genotype or "present"
            if _hla_allele_is_positive("31:01", genotype, result_label, risk_level):
                out["HLA_A_31_01"] = "positive"
                out["HLA_A_3101"] = "positive"
                out["HLA-A*31:01"] = "positive"
        elif gene == "HLA-B":
            out["HLA-B"] = genotype or "present"
            if _hla_allele_is_positive("15:02", genotype, result_label, risk_level):
                out["HLA_B_15_02"] = "positive"
                out["HLA-B*15:02"] = "positive"
            if _hla_allele_is_positive("58:01", genotype, result_label, risk_level):
                out["HLA_B_58_01"] = "positive"
                out["HLA-B*58:01"] = "positive"
        elif gene == "G6PD":
            status = _infer_g6pd_status(genotype, result_label, risk_level)
            out["G6PD"] = status or genotype or "present"
            if status:
                out["G6PD_phenotype"] = status
        elif gene == "HFE":
            out["HFE"] = genotype or "present"
            if genotype:
                out["HFE_rs1800562"] = genotype
        elif gene == "LCT":
            out["LCT"] = genotype or "present"
            if genotype:
                out["LCT_rs4988235"] = genotype
        elif gene in {"ADORA2A", "FADS1"}:
            out[gene] = genotype or ("high" if is_risk else "present")

    return out


def _infer_pgx_phenotype(gene: str, genotype: str, result_label: str, risk_level: str) -> str | None:
    text = f"{genotype} {result_label} {risk_level}".lower()
    if any(token in text for token in ("poor", "慢", "弱", "显著下降", "high")):
        return "poor"
    if any(token in text for token in ("intermediate", "中间", "轻度", "medium")):
        return "intermediate"
    if any(token in text for token in ("rapid", "ultrarapid", "快", "增强")):
        return "rapid"

    alleles = [part.strip().upper() for part in re.split(r"[/|]", genotype or "") if part.strip()]
    inactive = {
        "CYP2C19": {"*2", "*3"},
        "CYP2D6": {"*3", "*4", "*5", "*6"},
        "CYP2C9": {"*2", "*3"},
    }.get(gene, set())
    inactive_count = sum(1 for allele in alleles if allele in inactive)
    if inactive_count >= 2:
        return "poor"
    if inactive_count == 1:
        return "intermediate"
    return None


def _infer_thiopurine_pgx_status(
    gene: str,
    genotype: str,
    result_label: str,
    risk_level: str,
) -> tuple[str | None, str | None]:
    """Map TPMT/NUDT15 labels into the existing KB condition vocabulary."""

    text = f"{genotype} {result_label} {risk_level}".lower()
    no_function_tokens = (
        "poor",
        "低活性",
        "无活性",
        "缺乏",
        "no function",
        "no_function",
        "absent",
        "deficient",
        "high",
        "高风险",
    )
    decreased_tokens = (
        "intermediate",
        "中间",
        "活性降低",
        "功能降低",
        "decreased",
        "reduced",
        "medium",
        "中风险",
    )
    if any(token in text for token in no_function_tokens):
        function = "absent" if gene == "TPMT" else "no_function"
        return "poor_metabolizer", function
    if any(token in text for token in decreased_tokens):
        function = "low" if gene == "TPMT" else "decreased_function"
        return "intermediate_metabolizer", function
    return None, None


def _infer_dpyd_pgx_status(
    genotype: str,
    result_label: str,
    risk_level: str,
) -> tuple[str | None, str | None]:
    text = f"{genotype} {result_label} {risk_level}".lower()
    poor_tokens = (
        "poor",
        "no function",
        "no_function",
        "complete deficiency",
        "完全缺乏",
        "无活性",
        "低活性",
        "缺乏",
    )
    intermediate_tokens = (
        "intermediate",
        "decreased",
        "reduced",
        "partial",
        "中间",
        "活性降低",
        "功能降低",
        "中风险",
    )
    if any(token in text for token in poor_tokens):
        return "poor_metabolizer", "0"
    if any(token in text for token in intermediate_tokens):
        return "intermediate_metabolizer", "1"

    normalized = re.sub(r"[\s_]+", "", f"{genotype} {result_label}").upper()
    reduced_markers = (
        "*2A",
        "DPYD*2A",
        "RS3918290",
        "RS67376798",
        "RS55886062",
        "HAPB3",
        "C.1905+1G>A",
        "C.1679T>G",
        "C.2846A>T",
        "C.1129-5923C>G",
    )
    if any(re.sub(r"[\s_]+", "", marker).upper() in normalized for marker in reduced_markers):
        return "intermediate_metabolizer", "1"
    return None, None


def _normalize_vkorc1_genotype(genotype: str, result_label: str, risk_level: str) -> str | None:
    raw = str(genotype or "").strip().upper().replace(" ", "")
    genotype_aliases = {
        "AA": "AA",
        "A/A": "A/A",
        "AG": "AG",
        "A/G": "A/G",
        "GA": "A/G",
        "G/A": "A/G",
        "GG": "GG",
        "G/G": "G/G",
    }
    if raw in genotype_aliases:
        return genotype_aliases[raw]

    text = f"{genotype} {result_label} {risk_level}".lower()
    if any(token in text for token in ("warfarin sensitive", "华法林敏感", "敏感位点", "sensitive allele")):
        return "A/G"
    return None


def _infer_g6pd_status(genotype: str, result_label: str, risk_level: str) -> str | None:
    text = f"{genotype} {result_label} {risk_level}".lower()
    deficient_tokens = (
        "deficient",
        "deficiency",
        "缺乏",
        "低活性",
        "low activity",
        "low enzyme",
        "class i",
        "class ii",
        "class iii",
        "high",
        "高风险",
    )
    variable_tokens = (
        "variable",
        "intermediate",
        "partial",
        "borderline",
        "中间",
        "部分",
        "medium",
        "中风险",
    )
    if any(token in text for token in deficient_tokens):
        return "deficient"
    if any(token in text for token in variable_tokens):
        return "variable"
    return None


def _hla_allele_is_positive(
    allele_token: str,
    genotype: str,
    result_label: str,
    risk_level: str,
) -> bool:
    text = f"{genotype} {result_label} {risk_level}"
    lower = text.lower()
    if any(token in lower for token in ("negative", "not detected", "absent", "阴性", "未检出")):
        return False
    normalized = re.sub(r"[\s_:\-*]+", "", text).upper()
    allele_digits = re.sub(r"[^0-9]", "", allele_token)
    return bool(allele_digits and allele_digits in normalized)


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

    from app.services.evidence_resolver import EvidenceResolver

    return EvidenceResolver(db).apply_to_findings(
        twin,
        findings,
        max_refs_per_finding=max_refs_per_finding,
    )


def _select_claim_refs_for_specialist(
    finding: Any,
    claims: list[dict[str, Any]],
    max_refs: int,
) -> list[str]:
    specialist = (getattr(finding, "specialist_name", "") or "").lower()
    category = (getattr(finding, "category", "") or "").lower()
    domain_keywords = _specialist_domain_keywords(specialist, category)
    finding_terms = _finding_relevance_terms(finding)
    selected: list[str] = []

    for claim in claims:
        metadata = claim.get("metadata") or {}
        domain = str(metadata.get("domain") or "")
        entity_type = str(claim.get("entity_type") or "")
        entity_id = str(claim.get("entity_id") or "")
        haystack = f"{domain} {entity_type} {entity_id}".lower()
        if domain_keywords and not any(keyword in haystack for keyword in domain_keywords):
            continue
        if finding_terms and not _claim_matches_finding_terms(claim, finding_terms):
            continue
        if not finding_terms:
            continue
        doc_id = claim.get("doc_id")
        if doc_id:
            selected.append(doc_id)
        if len(selected) >= max_refs:
            break

    return _dedupe_preserve_order(selected)


def _finding_relevance_terms(finding: Any) -> set[str]:
    fields: list[str] = [
        str(getattr(finding, "summary", "") or ""),
    ]
    raw = getattr(finding, "raw", None)
    if isinstance(raw, dict):
        for value in raw.values():
            if isinstance(value, (str, int, float)):
                fields.append(str(value))
            elif isinstance(value, list):
                fields.extend(str(item) for item in value if isinstance(item, (str, int, float)))
    for item in getattr(finding, "findings", []) or []:
        if not isinstance(item, dict):
            continue
        for key in ("title", "action", "recommendation", "summary", "metric", "name"):
            value = item.get(key)
            if value:
                fields.append(str(value))
    return {
        term
        for term in _semantic_query_terms(" ".join(fields))
        if term not in _KB_RELEVANCE_STOP_TERMS and len(term) >= 2
    }


def _claim_matches_finding_terms(claim: dict[str, Any], finding_terms: set[str]) -> bool:
    claim_text = _claim_search_text_from_serialized(claim)
    claim_terms = {
        term
        for term in _semantic_query_terms(claim_text)
        if term not in _KB_RELEVANCE_STOP_TERMS and len(term) >= 2
    }
    if finding_terms & claim_terms:
        return True
    return any(term in claim_text for term in finding_terms)


def _specialist_domain_keywords(specialist: str, category: str) -> list[str]:
    text = f"{specialist} {category}"
    if "fuel" in text or "nutrition" in text:
        return ["nutrition", "metabolic", "fiber", "protein", "hydration", "water"]
    if "supplement" in text:
        return ["supplement", "genetic", "biomarker", "metabolic"]
    if "movement" in text:
        return ["movement", "training", "recovery", "metabolic"]
    if "recovery" in text:
        return ["sleep", "recovery", "readiness", "training"]
    if "rhinitis" in text or "鼻炎" in text:
        return ["rhinitis", "reflux", "gerd", "lpr", "gastro", "upper_airway"]
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


# 证据卡专属排除: 治理元声明不是健康知识, 不该占用户可见的 claim 席位
# (卡底免责行已是 boundary 的专属展示位)。谓词收窄到元句/元实体,
# 绝不误伤 CBT-I 等正经含"医学边界"字样的临床 claim。Prompt 侧不受影响。
_EVIDENCE_CARD_META_SENTENCE = "健康建议必须保留医学边界"
_EVIDENCE_CARD_META_ENTITY_IDS = {"medical-boundary"}


def _is_meta_boundary_claim(claim: dict[str, Any]) -> bool:
    title = str(claim.get("title") or "")
    entity_id = str(claim.get("entity_id") or "")
    return (
        _EVIDENCE_CARD_META_SENTENCE in title
        or entity_id in _EVIDENCE_CARD_META_ENTITY_IDS
    )


def _drop_meta_boundary_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in claims if not _is_meta_boundary_claim(c)]


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
    claims = _drop_meta_boundary_claims(result["claims"])
    if not claims:
        return None

    # 与 twin-fallback 卡同一实体解析:标题必须是首条 claim 的主题实体,
    # 不是 entities[0](显式基因问答里也可能错位到无关生标)。
    entity = _resolve_card_entity(db, result["entities"], claims)
    if entity is None:
        return None

    return {
        "type": "system_knowledge_evidence",
        "data": {
            "entity": entity,
            "claims": claims[:3],
            "claim_boundary": result["claim_boundary"],
        },
    }


def build_evidence_card_for_twin(
    db: Session,
    twin: dict[str, Any],
    *,
    message: str | None = None,
) -> dict[str, Any] | None:
    """Build a mobile evidence card from structured Twin matches.

    This is used when the user asks a general question ("怎么补叶酸") and the
    relevant gene/lab context comes from the user's HealthTwin rather than from
    an explicit entity mention in the message. Keeping the card shape identical
    to message-scoped cards makes mobile evidence rendering consistent.
    """

    result = lookup_for_twin(db, twin)
    claims = _drop_meta_boundary_claims(result["claims"])
    relevance = _filter_claims_for_message_relevance(claims, message)
    if message is not None:
        claims = relevance["claims"]
    # 多来源导入(dedao 批次)会出现同题 claim 重复;同一张卡里只留一份。
    claims = _dedupe_claims_by_title(claims)
    if not claims:
        return None

    # 卡标题实体 = 排序后首条 claim 的【自身主题实体】,解不出宁可不出卡。
    entity = _resolve_card_entity(db, result["entities"], claims)
    if entity is None:
        return None

    return {
        "type": "system_knowledge_evidence",
        "data": {
            "entity": entity,
            "claims": claims[:3],
            "claim_boundary": result["claim_boundary"],
            "retrieval": {
                "trigger": "twin_fallback",
                "filtered_by_message": message is not None,
                "matched_message_terms": relevance.get("matched_terms", [])[:8],
            },
        },
    }


def _dedupe_claims_by_title(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for claim in claims:
        key = re.sub(r"\s+", "", str(claim.get("title") or claim.get("doc_id") or "")).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(claim)
    return unique


def _resolve_card_entity(
    db: Session,
    entities: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """卡标题实体 = 排序后首条 claim 的【自身主题实体】,不是无关的 entities[0]。

    prod 实锤:entities 来自 twin 结构字段(生标/基因),claims 来自 applies_when
    条件命中(常是 condition 实体),两个池天然不相交 → 老逻辑 fallback 到
    entities[0](用户首个 lab = 血压)→ 尿酸/鼻炎 claim 也顶着"血压"标题。
    解析优先级:
      ① claims[0].entity_id 命中 entities 池 → 用池内实体(字段最全)
      ② 否则按 entity_id(+ entity_type)取 reviewed KB entity doc(真主题标题)
      ③ 解不出 → None(fail-closed:宁可不出卡,绝不错标)
    """
    if not claims:
        return None
    top = claims[0]
    top_entity_id = str(top.get("entity_id") or "")
    top_entity_type = str(top.get("entity_type") or "")
    if not top_entity_id:
        return None

    for entity in entities or []:
        if str(entity.get("entity_id") or "") == top_entity_id:
            return entity

    query = db.query(KBDocument).filter(
        KBDocument.doc_type == "entity",
        KBDocument.entity_id == top_entity_id,
        *_serving_document_filters(),
    )
    if top_entity_type:
        query = query.filter(KBDocument.entity_type == top_entity_type)
    entity_doc = query.order_by(KBDocument.entity_type.asc()).first()
    if entity_doc is None:
        return None
    return serialize_document(entity_doc)


_KB_RELEVANCE_STOP_TERMS = {
    # 万金油词: 任何 advice 类消息都含, 会把「医学边界」类元 claim 锚进证据卡
    # (prod 实锤: 建议 chip 文本命中「健康建议必须保留医学边界」标题)。
    "建议",
    "健康",
    "医学",
    "我",
    "我的",
    "最近",
    "今天",
    "现在",
    "应该",
    "一下",
    "一个",
    "这个",
    "那个",
    "记录",
    "录入",
    "保存",
    "新增",
    "删除",
    "修改",
    "撤销",
    "更新",
    "分析",
    "解读",
    "建议",
    "方案",
    "是否",
    "合理",
    "帮我",
    "结合",
    "基于",
    # 闭类功能/疑问词(非领域词,开集领域词绝不进这里)。prod 实测
    # "适合"命中《HbA1c 适合作为 8-12 周复查闭环》标题 → 运动问题弹血糖卡。
    "适合",
    "怎样",
    "怎么",
    "如何",
    "什么",
    "哪些",
    "可以",
    "需要",
    "注意",
    "作为",
    "优先",
    "为什么",
    "多少",
}

# CJK 滑窗 bigram 会产出跨词垃圾("样的"/"的运"/"天我")。含这些高频功能字的
# 组合几乎不可能是领域词,直接丢弃 —— 领域词(血压/叶酸/尿酸/睡眠)不含它们。
_KB_RELEVANCE_JUNK_CHARS = set("的我了吗呢你他她它是在把给被就都还很请和与或及等这那")


def _is_junk_relevance_term(term: str) -> bool:
    return any(ch in _KB_RELEVANCE_JUNK_CHARS for ch in term)


# 强度修饰词:L = 修饰+主题(高血压)或 主题+修饰(血压高)时,2 字主题(血压)是
# 真主题,不能当碎片丢 —— 否则"高尿酸/高血脂/血压高"这类问法会误杀出卡。
_INTENSITY_MODIFIERS = ("高", "低", "偏", "超", "重度", "轻度", "中度", "重", "轻", "过", "正常", "异常")


def _is_modifier_bounded_fragment(short: str, longer: str) -> bool:
    """longer 是否只是「short + 强度修饰」或「强度修饰 + short」(此时 short 是主题)。"""
    if longer.startswith(short) and longer[len(short):] in _INTENSITY_MODIFIERS:
        return True
    if longer.endswith(short) and longer[: len(longer) - len(short)] in _INTENSITY_MODIFIERS:
        return True
    return False


# 证据卡消息相关性【专用】停用词 —— 只作用于 twin-fallback 证据卡的主题锚点,
# 不进 specialist finding 匹配(那条路径 用药/风险 可能是真实领域信号)。
#
# 这些是 health-advice turn 的【指令样板 / 边界元词】:它们出现在几乎每个
# "给建议但别当诊断、别直接给用药、列出不确定性边界、未来 N 天可执行" 的样板
# 指令里,同时又出现在几乎每条 *_risk / *_boundary claim 的标题里 → 拿来当主题
# 锚点必然把完全无关的慢病 claim 钓进证据卡。
#
# prod 实锤(founder CFTR 基因问答):消息主题是 CFTR/囊性纤维化(reviewed KB
# 里无此 claim),但样板词 用药/边界/风险/临床/相关 命中 鼻炎/尿酸/血压/糖尿病
# 边界 claim → 卡标题错位成"血压"。领域主题词(血压/叶酸/尿酸/CFTR)绝不进此表。
_KB_CARD_RELEVANCE_STOP_TERMS = {
    # —— health-advice turn 的边界/指令样板词 ——
    "用药",
    "边界",
    "临床",
    "风险",
    "相关",
    "诊断",
    "建议",
    "评估",
    "监测",
    "必须",  # prod 实锤主犯:几乎每条 *_boundary claim 标题都含"…建议必须保留…边界"
    "复核",
    "保留",
    "治疗",
    "决策",
    "医生",
    "沟通",
    "决定",
    "注意",
    "结合",
    # —— 结构化"基因发现"模板的字段标签词(中文)——
    "标题",
    "分类",
    "结果",
    "等级",
    "位点",
    "数据",
    "动作",
    "可执行",
    "不确定性",
    "性质",
    "描述",
    "关键",
    "字段",
    "类型",
    "摘要",
    "当前",
    "上下文",
    # —— 机器序列化的英文脚手架(gene_name/clinical_status/evidence_level/…)——
    # 这些是字段名/分类值,不是用户主题;真正的英文主题词(生标名 HbA1c/LDL、
    # 基因符号 MTHFR/APOE)不在此表,仍可作锚点。
    "risk",
    "disease",
    "gene",
    "genotype",
    "genomic",
    "finding",
    "category",
    "clinical",
    "status",
    "evidence",
    "level",
    "name",
    "type",
    "value",
    "result",
    "confirmation",
    "requires",
    "neutral",
    "present",
    "active",
    "dtc",
    "high",
    "low",
}


def _is_card_relevance_stop_term(term: str) -> bool:
    """卡片相关性锚点专用停用。

    结构化"基因发现"块把大量【非主题】token 灌进消息:边界样板词、字段标签、
    英文脚手架。它们与 *_boundary claim 标题/doc_id 的样板部分重叠 → 误命中。
    规则(领域主题词:血压/叶酸/尿酸/HbA1c/MTHFR 均不被这些规则误伤):
      · 显式样板/脚手架词表
      · 纯数字("30 天"里的 30、基因型 "1200")
      · 含下划线的 token(disease_risk / gene_name / clinical_status —— 机器字段名)
      · 长度 <3 的纯 ASCII(id/gg/bp… 太短易撞;3+ 的脚手架 dtc/low 走上面词表,
        真英文主题词 ldl/hdl/hba1c 得以保留)
    """
    if term in _KB_CARD_RELEVANCE_STOP_TERMS:
        return True
    if term.isdigit():
        return True
    if "_" in term:
        return True
    if term.isascii() and term.isalnum() and len(term) < 3:
        return True
    return False


def _filter_claims_for_message_relevance(
    claims: list[dict[str, Any]],
    message: str | None,
) -> dict[str, Any]:
    """Keep Twin fallback claims only when they are relevant to the turn text.

    Twin matches are useful, but too broad for mixed record+analysis turns: a
    user can record dinner while their Twin contains MTHFR/9p21 risks. In that
    case the evidence card should appear only if the message actually asks
    about the matching topic.

    准入只认「锚点字段」(doc_id/标题/entity/matched_conditions);正文/摘要/
    metadata 命中只参与排序、不作准入 —— 慢病 claim 正文普遍含"运动/饮食"等
    生活方式词,按全文准入会让任何泛生活方式问题钓出无关慢病卡(prod 实锤:
    "今天我适合怎样的运动?" → 血压/HbA1c 卡)。方向同 anchored-allowlist 教训:
    身份匹配用锚点,不用子串扫全文。
    """

    if not message:
        return {"claims": claims, "matched_terms": []}

    terms = [
        term
        for term in _semantic_query_terms(message)
        if term not in _KB_RELEVANCE_STOP_TERMS
        and len(term) >= 2
        and not _is_junk_relevance_term(term)
        and not _is_card_relevance_stop_term(term)
    ]
    # CJK 滑窗 bigram 会从更长共现词里漏出 2 字碎片:囊性"纤维"化 → 碎片"纤维",
    # 撞上"膳食纤维"的 claim(prod 实锤:CFTR 问答弹膳食纤维卡)。若某 2 字词是
    # 同批另一更长词的真子串,视为碎片丢弃 —— 但排除「强度修饰+主题」的情形
    # (高尿酸/高血脂/血压高:主题词本身才是锚点,不能当碎片),否则误杀真问法。
    longer_terms = [t for t in terms if len(t) >= 3]
    terms = [
        t
        for t in terms
        if not (
            len(t) == 2
            and any(
                t != lt and t in lt and not _is_modifier_bounded_fragment(t, lt)
                for lt in longer_terms
            )
        )
    ]
    if not terms:
        return {"claims": [], "matched_terms": []}

    ranked: list[tuple[float, dict[str, Any], list[str]]] = []
    for claim in claims:
        anchor_text = _claim_anchor_text_from_serialized(claim)
        anchor_matched = [term for term in terms if term in anchor_text]
        if not anchor_matched:
            continue
        body_text = _claim_search_text_from_serialized(claim)
        body_matched = [term for term in terms if term in body_text]
        confidence = claim.get("confidence")
        confidence_bonus = float(confidence or 0.0) * 0.05
        score = len(anchor_matched) * 2 + len(body_matched) + confidence_bonus
        ranked.append((score, claim, anchor_matched))

    ranked.sort(key=lambda item: (-item[0], str(item[1].get("doc_id") or "")))
    return {
        "claims": [claim for _score, claim, _terms in ranked],
        "matched_terms": _dedupe_preserve_order(
            term for _score, _claim, matched in ranked for term in matched
        ),
    }


def _claim_anchor_text_from_serialized(claim: dict[str, Any]) -> str:
    """主题锚点字段:决定 claim 是否与本轮消息相关的准入文本。

    刻意不含 summary/body/sources/metadata —— 那些是内容,不是身份。
    也【刻意不含 entity_type】—— 它是分类标签(gene/condition/biomarker),
    不是用户主题;一旦纳入,机器序列化的"基因发现"块里的英文脚手架
    (gene/condition/…)会命中它,把整类无关 claim 钓进证据卡
    (prod 实锤:CFTR 基因发现块的 "gene"/"condition" 命中鼻炎/他汀 claim)。
    主题身份留给 doc_id / title / entity_id / matched_conditions。
    """
    fields: list[str] = [
        str(claim.get("doc_id") or ""),
        str(claim.get("title") or ""),
        str(claim.get("entity_id") or ""),
    ]
    conditions = claim.get("matched_conditions") or []
    if isinstance(conditions, list):
        fields.extend(str(item) for item in conditions)
    else:
        fields.append(str(conditions))
    return " ".join(fields).lower()


def _claim_search_text_from_serialized(claim: dict[str, Any]) -> str:
    fields: list[str] = [
        str(claim.get("doc_id") or ""),
        str(claim.get("title") or ""),
        str(claim.get("summary") or ""),
        str(claim.get("body") or ""),
        str(claim.get("entity_type") or ""),
        str(claim.get("entity_id") or ""),
    ]
    for key in ("sources", "recommends_lookup", "matched_conditions"):
        value = claim.get(key) or []
        if isinstance(value, list):
            fields.extend(str(item) for item in value)
        else:
            fields.append(str(value))
    metadata = claim.get("metadata") or {}
    if isinstance(metadata, dict):
        fields.extend(str(value) for value in metadata.values() if isinstance(value, (str, int, float)))
    return " ".join(fields).lower()


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

    intersects_match = _INTERSECTS_RE.match(expression)
    if intersects_match:
        collection = _value_at_path(twin, intersects_match.group("path"))
        try:
            candidates = ast.literal_eval(intersects_match.group("values"))
        except (SyntaxError, ValueError):
            return False
        if not isinstance(candidates, (list, tuple, set)):
            return False
        return any(_collection_contains(collection, candidate) for candidate in candidates)

    has_match = _HAS_RE.match(expression)
    if has_match:
        collection = _value_at_path(twin, has_match.group("path"))
        value_expression = has_match.group("value").strip()
        any_match = _HAS_ANY_RE.match(value_expression)
        if any_match:
            try:
                candidates = ast.literal_eval(any_match.group("values"))
            except (SyntaxError, ValueError):
                return False
            return any(_collection_contains(collection, candidate) for candidate in candidates)
        return _collection_contains(collection, _parse_literal(value_expression))

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
        for pattern in (_NULL_RE, _IN_RE, _INTERSECTS_RE, _HAS_RE, _EQ_RE, _COMPARE_RE)
    )


def _collection_contains(collection: Any, candidate: Any) -> bool:
    needle = str(candidate or "").strip().lower()
    if not needle:
        return False
    for value in _flatten_membership_values(collection):
        text = str(value or "").strip().lower()
        if text == needle or needle in text:
            return True
    return False


def _flatten_membership_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, int, float, bool)):
        return [value]
    if isinstance(value, dict):
        values: list[Any] = []
        preferred_keys = (
            "name",
            "generic_name",
            "drug",
            "drug_name",
            "medication_name",
            "title",
            "label",
            "ingredient",
        )
        for key in preferred_keys:
            if key in value:
                values.extend(_flatten_membership_values(value.get(key)))
        if not values:
            for item in value.values():
                values.extend(_flatten_membership_values(item))
        return values
    if isinstance(value, (list, tuple, set)):
        values: list[Any] = []
        for item in value:
            values.extend(_flatten_membership_values(item))
        return values
    return [value]


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
        return 1.0 + float(document.confidence or 0.0) * 0.1
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
    if score <= 0:
        return 0.0
    if document.doc_type == "claim":
        score += 0.2
    if document.confidence:
        score += float(document.confidence) * 0.1
    return score


def _bm25_rank_documents(documents: list[KBDocument], terms: list[str]) -> list[tuple[float, KBDocument]]:
    if not documents:
        return []
    if not terms:
        return [
            (1.0 + float(document.confidence or 0.0) * 0.1, document)
            for document in documents
        ]

    tokenized = {
        document.doc_id: _query_terms(_document_search_text(document))
        for document in documents
    }
    document_lengths = {doc_id: max(1, len(tokens)) for doc_id, tokens in tokenized.items()}
    average_length = sum(document_lengths.values()) / max(1, len(document_lengths))
    document_frequencies: Counter[str] = Counter()
    for tokens in tokenized.values():
        document_frequencies.update(set(tokens))

    k1 = 1.5
    b = 0.75
    corpus_size = len(documents)
    ranked: list[tuple[float, KBDocument]] = []
    for document in documents:
        tokens = tokenized[document.doc_id]
        token_counts = Counter(tokens)
        length = document_lengths[document.doc_id]
        title = (document.title or "").lower()
        entity = f"{document.entity_type or ''} {document.entity_id or ''}".lower()
        score = 0.0
        for term in terms:
            term_frequency = token_counts.get(term, 0)
            if term in title:
                term_frequency += 3
            if term in entity:
                term_frequency += 2
            if term_frequency <= 0:
                continue
            document_frequency = max(1, document_frequencies.get(term, 0))
            idf = math.log(1 + (corpus_size - document_frequency + 0.5) / (document_frequency + 0.5))
            denominator = term_frequency + k1 * (1 - b + b * length / max(1.0, average_length))
            score += idf * (term_frequency * (k1 + 1)) / denominator
        if score <= 0:
            continue
        if document.doc_type == "claim":
            score += 0.15
        if document.confidence:
            score += float(document.confidence) * 0.05
        ranked.append((score, document))
    return ranked


def _score_precomputed_search_text(document: KBDocument, terms: list[str]) -> float:
    if not terms:
        return 1.0 + float(document.confidence or 0.0) * 0.1
    text = (document.tsv or _document_search_text(document)).lower()
    score = 0.0
    for term in terms:
        if term in text:
            score += 1.0 + min(text.count(term), 5) * 0.1
    if score <= 0:
        return 0.0
    if document.doc_type == "claim":
        score += 0.15
    if document.confidence:
        score += float(document.confidence) * 0.05
    return score


def _query_terms(query: str) -> list[str]:
    """Tokenize mixed Chinese/English KB queries.

    Primary terms come from jieba word segmentation (drug-name aware); the
    existing char-bigram sliding window is UNIONED in as additional fallback
    terms (\u52a0\u5c42\u4e0d\u51cf\u5c42) so recall never regresses relative to the pre-jieba
    behavior. jieba is a hard dependency \u2014 if it is somehow unavailable at
    runtime this degrades to bigrams-only rather than crashing the query path
    (the loud failure is a boot-time ``check_zh_tokenizer_available()`` probe).
    """

    seen: set[str] = set()
    terms: list[str] = []

    def add(term: str) -> None:
        value = term.strip().lower()
        if not value or value in seen:
            return
        seen.add(value)
        terms.append(value)

    # Primary: jieba word tokens (keeps \u9ad8\u8840\u538b/\u8fd0\u52a8/\u5efa\u8bae and drug names intact).
    # Skip length-1 Chinese tokens: a single hanzi (\u51cf/\u5242/\u5417) carries almost no
    # discriminative signal and only adds BM25 noise that dilutes specific hits
    # (measured: including them regressed contraindication ranks on the eval set);
    # the char-bigram fallback below already covers 2-grams. English/numeric
    # single-char tokens are kept (they can be meaningful, e.g. a lab code).
    try:
        from app.services.zh_tokenize import seg_text

        for token in seg_text(query or "").split():
            if len(token) == 1 and "\u4e00" <= token <= "\u9fff":
                continue
            add(token)
    except Exception:  # noqa: BLE001 - boot probe is the loud path; here stay resilient
        logger.warning("[system_kb] jieba segmentation unavailable in _query_terms; using bigrams only")

    # Additional (unioned, never replacing): regex words + Chinese char bigrams.
    for token in re.findall(r"[A-Za-z0-9_+.-]+|[\u4e00-\u9fff]+", query or ""):
        add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 2:
            for i in range(len(token) - 1):
                add(token[i : i + 2])
    return terms


SEMANTIC_QUERY_ALIASES = {
    "homocysteine": ("hcy", "同型半胱氨酸"),
    "hcy": ("homocysteine", "同型半胱氨酸"),
    "folate": ("叶酸", "5-mthf", "mthfr"),
    "methylfolate": ("5-mthf", "活性叶酸", "叶酸"),
    "ldl": ("ldl-c", "低密度脂蛋白", "胆固醇"),
    "ldl-c": ("ldl", "低密度脂蛋白", "胆固醇"),
    "apob": ("apo b", "载脂蛋白b", "血脂"),
    "hba1c": ("糖化血红蛋白", "血糖"),
    "glucose": ("血糖", "空腹血糖", "餐后血糖"),
    "sleep": ("睡眠", "恢复"),
    "recovery": ("恢复", "睡眠", "hrv"),
    "statin": ("他汀", "降脂药", "ldl-c"),
    "metformin": ("二甲双胍", "降糖药", "血糖"),
    "mthfr": ("叶酸", "同型半胱氨酸", "hcy"),
    "apoe": ("血脂", "ldl-c", "胆固醇"),
}


def _semantic_query_terms(query: str) -> list[str]:
    terms = _query_terms(query)
    seen = set(terms)
    expanded = list(terms)
    for term in terms:
        for alias in SEMANTIC_QUERY_ALIASES.get(term, ()):
            value = alias.strip().lower()
            if value and value not in seen:
                seen.add(value)
                expanded.append(value)
                for subterm in _query_terms(value):
                    if subterm in seen:
                        continue
                    seen.add(subterm)
                    expanded.append(subterm)
    return expanded


def _vector_terms(text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []

    def add(raw: str) -> None:
        term = raw.strip().lower()
        if not term or term in seen:
            return
        seen.add(term)
        terms.append(term)

    for term in _semantic_query_terms(text):
        add(term)
    for span in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        max_n = min(8, len(span))
        for n in range(2, max_n + 1):
            for index in range(len(span) - n + 1):
                add(span[index : index + n])
    return terms


def _build_sparse_term_vector(text: str) -> dict[str, float]:
    counts = Counter(_vector_terms(text))
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:VECTOR_MAX_TERMS]
    return {
        term: round(1.0 + math.log(count), 6)
        for term, count in ranked
        if term
    }


def _sparse_vector_magnitude(vector: dict[str, float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in vector.values()))


def _upsert_document_vector(db: Session, doc_id: str, searchable: str, content_hash: str) -> None:
    vector = _build_sparse_term_vector(searchable)
    magnitude = _sparse_vector_magnitude(vector)
    existing = db.query(KBDocumentVector).filter(KBDocumentVector.doc_id == doc_id).first()
    values = {
        "embedding_model": VECTOR_BACKEND,
        "content_hash": content_hash,
        "vector_json": vector,
        "magnitude": magnitude,
        "updated_at": datetime.now(UTC),
    }
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return
    db.add(KBDocumentVector(doc_id=doc_id, **values))


def _pgvector_backend_name() -> str:
    return f"pgvector:{settings.system_kb_embedding_model}"


def _is_postgres_session(db: Session) -> bool:
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    return getattr(dialect, "name", "") == "postgresql"


def _system_kb_embedding_api_key() -> str | None:
    return settings.system_kb_embedding_api_key or settings.openai_api_key


def _system_kb_embedding_base_url() -> str | None:
    return settings.system_kb_embedding_base_url or settings.openai_base_url


def _system_kb_embedding_provider_available() -> bool:
    return bool(_system_kb_embedding_api_key())


def _pgvector_backend_for_session(db: Session) -> str | None:
    if not settings.system_kb_pgvector_enabled:
        return None
    if not _is_postgres_session(db):
        return None
    if not _system_kb_embedding_provider_available():
        return None
    if not _pgvector_table_exists(db):
        return None
    return _pgvector_backend_name()


def _pgvector_table_exists(db: Session) -> bool:
    try:
        return bool(
            db.execute(
                text("SELECT to_regclass('public.kb_document_embeddings')")
            ).scalar()
        )
    except SQLAlchemyError:
        db.rollback()
        return False


def _ensure_pgvector_table(db: Session) -> bool:
    if not settings.system_kb_pgvector_enabled or not _is_postgres_session(db):
        return False
    dimensions = int(settings.system_kb_embedding_dimensions)
    try:
        engine = db.get_bind()
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {PGVECTOR_TABLE} (
                        doc_id TEXT PRIMARY KEY REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
                        embedding_model VARCHAR(120) NOT NULL,
                        content_hash VARCHAR(64) NOT NULL,
                        embedding vector({dimensions}) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_{PGVECTOR_TABLE}_model_doc
                    ON {PGVECTOR_TABLE}(embedding_model, doc_id)
                    """
                )
            )
            connection.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS ix_{PGVECTOR_TABLE}_embedding_cosine
                    ON {PGVECTOR_TABLE}
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                    """
                )
            )
        return True
    except SQLAlchemyError as exc:
        logger.warning("system KB pgvector table unavailable; sparse vector fallback remains active: %s", exc)
        return False


import threading as _emb_threading
from datetime import date as _emb_date_cls
_emb_guard_lock = _emb_threading.Lock()
_emb_guard_state = {"day": None, "calls": 0}


def _embedding_count_and_warn() -> None:
    """日级 embedding 调用计数 —— 超阈值【只告警, 不降级】: 继续按量嵌入保检索质量,
    仅跨过阈值时 log 一次 warning 作 runaway 预警。env EMBEDDING_DAILY_CALL_CAP=0/未设 → 不计数。"""
    import os as _os
    try:
        cap = int(_os.environ.get("EMBEDDING_DAILY_CALL_CAP", "0") or 0)
    except ValueError:
        cap = 0
    if cap <= 0:
        return
    today = _emb_date_cls.today().isoformat()
    with _emb_guard_lock:
        if _emb_guard_state.get("day") != today:
            _emb_guard_state.update(day=today, calls=0, warned=False)
        _emb_guard_state["calls"] += 1
        if _emb_guard_state["calls"] > cap and not _emb_guard_state.get("warned"):
            _emb_guard_state["warned"] = True
            logger.warning(
                "system KB embedding 今日调用超阈值 %s (EMBEDDING_DAILY_CALL_CAP), 继续按量不降级; 排查 runaway 重嵌", cap)


def _embed_system_kb_texts(texts: list[str], *, batch_size: int | None = None) -> list[list[float]] | None:
    prepared_texts = [str(text or "").strip() or " " for text in texts]
    if not prepared_texts or not _system_kb_embedding_provider_available():
        return None
    _embedding_count_and_warn()  # 超阈值只告警不降级, 继续按量嵌入
    effective_batch_size = max(1, int(batch_size or settings.system_kb_embedding_batch_size))
    try:
        from openai import OpenAI

        client_kwargs: dict[str, Any] = {"api_key": _system_kb_embedding_api_key()}
        embedding_base_url = _system_kb_embedding_base_url()
        if embedding_base_url:
            client_kwargs["base_url"] = embedding_base_url
        client = OpenAI(**client_kwargs)
        embeddings: list[list[float]] = []
        for index in range(0, len(prepared_texts), effective_batch_size):
            batch = prepared_texts[index : index + effective_batch_size]
            response = client.embeddings.create(
                model=settings.system_kb_embedding_model,
                input=batch,
            )
            embeddings.extend([list(item.embedding) for item in response.data])
        if len(embeddings) != len(prepared_texts):
            return None
        return embeddings
    except Exception as exc:  # External provider failure must not break reviewed KB serving.
        logger.warning("system KB embedding provider unavailable; sparse vector fallback remains active: %s", exc)
        return None


def _pgvector_literal(vector: list[float]) -> str:
    dimensions = int(settings.system_kb_embedding_dimensions)
    if len(vector) != dimensions:
        raise ValueError(f"embedding dimension mismatch: expected {dimensions}, got {len(vector)}")
    values = []
    for value in vector:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("embedding contains non-finite value")
        values.append(format(number, ".8g"))
    return "[" + ",".join(values) + "]"


def _reindex_pgvector_documents(
    db: Session,
    searchable_by_doc_id: dict[str, tuple[str, str]],
    *,
    table_ready: bool | None = None,
) -> int:
    if not searchable_by_doc_id:
        return 0
    if table_ready is None:
        table_ready = _ensure_pgvector_table(db)
    if not table_ready:
        return 0

    doc_ids = list(searchable_by_doc_id.keys())
    texts = [searchable_by_doc_id[doc_id][0] for doc_id in doc_ids]
    embeddings = _embed_system_kb_texts(texts)
    if not embeddings:
        return 0

    upsert_sql = text(
        f"""
        INSERT INTO {PGVECTOR_TABLE} (doc_id, embedding_model, content_hash, embedding, updated_at)
        VALUES (:doc_id, :embedding_model, :content_hash, CAST(:embedding AS vector), NOW())
        ON CONFLICT (doc_id) DO UPDATE SET
            embedding_model = EXCLUDED.embedding_model,
            content_hash = EXCLUDED.content_hash,
            embedding = EXCLUDED.embedding,
            updated_at = NOW()
        """
    )
    try:
        params = [
            {
                "doc_id": doc_id,
                "embedding_model": settings.system_kb_embedding_model,
                "content_hash": searchable_by_doc_id[doc_id][1],
                "embedding": _pgvector_literal(embedding),
            }
            for doc_id, embedding in zip(doc_ids, embeddings, strict=True)
        ]
    except ValueError as exc:
        logger.warning("system KB pgvector upsert skipped: %s", exc)
        return 0

    try:
        engine = db.get_bind()
        with engine.begin() as connection:
            connection.execute(upsert_sql, params)
    except SQLAlchemyError as exc:
        logger.warning("system KB pgvector upsert skipped; sparse vector fallback remains active: %s", exc)
        return 0
    return len(params)


def _rank_vector_documents(
    db: Session,
    documents_by_id: dict[str, KBDocument],
    query: str,
    *,
    limit: int,
) -> tuple[list[tuple[float, KBDocument]], str]:
    if not documents_by_id:
        return [], VECTOR_BACKEND

    dense_backend = _pgvector_backend_for_session(db)
    if dense_backend:
        dense_ranked = _rank_pgvector_documents(
            db,
            documents_by_id,
            query,
            limit=limit,
        )
        if dense_ranked:
            return dense_ranked, dense_backend

    query_vector = _build_sparse_term_vector(query)
    query_magnitude = _sparse_vector_magnitude(query_vector)
    if not query_vector or query_magnitude == 0:
        return [], VECTOR_BACKEND

    try:
        rows = (
            db.query(KBDocumentVector)
            .filter(
                KBDocumentVector.doc_id.in_(documents_by_id.keys()),
                KBDocumentVector.embedding_model == VECTOR_BACKEND,
            )
            .all()
        )
    except SQLAlchemyError:
        db.rollback()
        return [], VECTOR_BACKEND

    ranked: list[tuple[float, KBDocument]] = []
    for row in rows:
        document = documents_by_id.get(row.doc_id)
        if document is None:
            continue
        score = _cosine_sparse_vectors(
            query_vector,
            query_magnitude,
            row.vector_json or {},
            float(row.magnitude or 0.0),
        )
        if score > 0:
            ranked.append((score, document))
    return ranked, VECTOR_BACKEND


def _rank_pgvector_documents(
    db: Session,
    documents_by_id: dict[str, KBDocument],
    query: str,
    *,
    limit: int,
) -> list[tuple[float, KBDocument]]:
    embedding_rows = _embed_system_kb_texts([query])
    if not embedding_rows:
        return []
    try:
        query_embedding = _pgvector_literal(embedding_rows[0])
    except ValueError:
        return []

    statement = text(
        f"""
        SELECT doc_id, 1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
        FROM {PGVECTOR_TABLE}
        WHERE embedding_model = :embedding_model
          AND doc_id IN :doc_ids
        ORDER BY embedding <=> CAST(:query_embedding AS vector)
        LIMIT :limit
        """
    ).bindparams(bindparam("doc_ids", expanding=True))
    try:
        rows = db.execute(
            statement,
            {
                "query_embedding": query_embedding,
                "embedding_model": settings.system_kb_embedding_model,
                "doc_ids": list(documents_by_id.keys()),
                "limit": max(1, min(limit, 100)),
            },
        ).fetchall()
    except SQLAlchemyError as exc:
        logger.warning("system KB pgvector rank failed; sparse vector fallback remains active: %s", exc)
        db.rollback()
        return []

    ranked: list[tuple[float, KBDocument]] = []
    for row in rows:
        document = documents_by_id.get(str(row.doc_id))
        if document is None:
            continue
        score = float(row.score or 0.0)
        if score > 0:
            ranked.append((score, document))
    return ranked


def _cosine_sparse_vectors(
    query_vector: dict[str, float],
    query_magnitude: float,
    document_vector: dict[str, Any],
    document_magnitude: float,
) -> float:
    if query_magnitude == 0 or document_magnitude == 0:
        return 0.0
    dot = 0.0
    for term, query_weight in query_vector.items():
        document_weight = document_vector.get(term)
        if document_weight is None:
            continue
        dot += float(query_weight) * float(document_weight)
    if dot <= 0:
        return 0.0
    return dot / (query_magnitude * document_magnitude)


def _fuse_search_rankings(
    lexical_ranked: list[tuple[float, KBDocument]],
    fts_ranked: list[tuple[float, KBDocument]],
    vector_ranked: list[tuple[float, KBDocument]],
    graph_ranked: list[tuple[float, KBDocument]],
    graph_meta_by_doc: dict[str, dict[str, Any]],
) -> list[tuple[float, KBDocument, dict[str, Any]]]:
    """Fuse lexical and graph rankings with deterministic RRF.

    The raw lexical and graph scores are kept as metadata. The public `score`
    is the fused score so future vector retrieval can join as another rank
    stream without changing API shape.
    """

    rrf_k = 60.0
    by_doc: dict[str, dict[str, Any]] = {}

    def _entry(document: KBDocument) -> dict[str, Any]:
        return by_doc.setdefault(
            document.doc_id,
            {
                "document": document,
                "score": 0.0,
                "channels": set(),
                "lexical_score": None,
                "fts_score": None,
                "vector_score": None,
                "graph_score": None,
                "graph_distance": None,
                "relations": [],
            },
        )

    for rank, (score, document) in enumerate(lexical_ranked, start=1):
        entry = _entry(document)
        entry["score"] += 1.0 / (rrf_k + rank)
        entry["channels"].add("lexical")
        entry["lexical_score"] = round(score, 4)

    for rank, (score, document) in enumerate(fts_ranked, start=1):
        entry = _entry(document)
        entry["score"] += 1.0 / (rrf_k + rank)
        entry["channels"].add("fts")
        entry["fts_score"] = round(score, 4)

    for rank, (score, document) in enumerate(vector_ranked, start=1):
        entry = _entry(document)
        entry["score"] += 1.0 / (rrf_k + rank)
        entry["channels"].add("vector")
        entry["vector_score"] = round(score, 4)

    for rank, (score, document) in enumerate(graph_ranked, start=1):
        entry = _entry(document)
        entry["score"] += 1.0 / (rrf_k + rank)
        entry["channels"].add("graph")
        entry["graph_score"] = round(score, 4)
        graph_meta = graph_meta_by_doc.get(document.doc_id, {})
        entry["graph_distance"] = graph_meta.get("graph_distance", 1)
        entry["relations"] = sorted(graph_meta.get("relations", []))

    fused: list[tuple[float, KBDocument, dict[str, Any]]] = []
    for doc_id, entry in by_doc.items():
        channels = sorted(entry["channels"])
        retrieval = {
            "channels": channels,
            "lexical_score": entry["lexical_score"],
            "fts_score": entry["fts_score"],
            "vector_score": entry["vector_score"],
            "graph_score": entry["graph_score"],
            "graph_distance": entry["graph_distance"],
            "relations": entry["relations"],
        }
        fused.append((float(entry["score"]), entry["document"], retrieval))

    fused.sort(key=lambda item: (-item[0], item[1].doc_type, item[1].doc_id))
    return fused


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
    raw = "\n".join(str(chunk) for chunk in chunks if chunk)
    # Append a jieba-segmented (space-separated) view so PostgreSQL
    # to_tsvector("simple", ...) and the precomputed-text scorer see real word
    # boundaries for Chinese. The raw text is kept verbatim so English tokens /
    # doc_ids / numbers are untouched (加层不减层). Reindexing must be re-run
    # after deploy for existing rows to pick up the segmented text.
    try:
        from app.services.zh_tokenize import seg_text

        segmented = seg_text(raw)
        if segmented:
            return raw + "\n" + segmented
    except Exception:  # noqa: BLE001 - boot probe is the loud path; indexing stays resilient
        logger.warning("[system_kb] jieba segmentation unavailable in _document_search_text; indexing raw only")
    return raw


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
    not_applicable = 0
    with_refs = 0
    unsupported = 0
    by_specialist: dict[str, dict[str, Any]] = {}
    by_category: dict[str, dict[str, Any]] = {}
    by_support_status: dict[str, int] = {}
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
            support_status = _finding_support_status(finding, refs, is_unsupported)
            is_not_applicable = _support_status_is_not_applicable(support_status)
            if is_not_applicable:
                not_applicable += 1
            if refs:
                with_refs += 1
            if is_unsupported:
                unsupported += 1
            specialist = str(finding.get("specialist") or finding.get("specialist_name") or "unknown")
            category = str(finding.get("category") or finding.get("kind") or "unknown")
            _add_evidence_bucket(
                by_specialist,
                specialist,
                refs=refs,
                is_unsupported=is_unsupported,
                is_not_applicable=is_not_applicable,
            )
            _add_evidence_bucket(
                by_category,
                category,
                refs=refs,
                is_unsupported=is_unsupported,
                is_not_applicable=is_not_applicable,
            )
            by_support_status[support_status] = by_support_status.get(support_status, 0) + 1

    _finalize_evidence_buckets(by_specialist)
    _finalize_evidence_buckets(by_category)
    applicable_total = total - not_applicable
    raw_evidence_ref_rate = round(with_refs / total, 4) if total else 0.0
    evidence_ref_rate = round(with_refs / applicable_total, 4) if applicable_total else 0.0

    return {
        "total": total,
        "applicable_total": applicable_total,
        "not_applicable": not_applicable,
        "with_evidence_refs": with_refs,
        "unsupported": unsupported,
        "evidence_ref_rate": evidence_ref_rate,
        "raw_evidence_ref_rate": raw_evidence_ref_rate,
        "target_evidence_ref_rate": SPECIALIST_EVIDENCE_REF_RATE_TARGET,
        "meets_target": (
            (with_refs / applicable_total) >= SPECIALIST_EVIDENCE_REF_RATE_TARGET
            if applicable_total
            else False
        ),
        "unsupported_rate": round(unsupported / total, 4) if total else 0.0,
        "by_specialist": dict(sorted(by_specialist.items())),
        "by_category": dict(sorted(by_category.items())),
        "by_support_status": dict(sorted(by_support_status.items())),
    }


def _aggregate_notification_evidence_coverage(db: Session) -> dict[str, Any]:
    from app.models.notification import NotificationLog

    rows = db.query(NotificationLog).all()
    total = 0
    with_refs = 0
    unsupported = 0
    by_type: dict[str, dict[str, Any]] = {}
    by_support_status: dict[str, int] = {}

    for row in rows:
        data = row.data if isinstance(row.data, dict) else {}
        support_status = data.get("support_status")
        if not support_status:
            continue

        total += 1
        refs = data.get("evidence_refs")
        refs = refs if isinstance(refs, list) else []
        is_unsupported = bool(data.get("unsupported"))
        notification_type = str(row.notification_type or "unknown")
        support_status_key = str(support_status or "unknown")

        if refs:
            with_refs += 1
        if is_unsupported:
            unsupported += 1

        _add_evidence_bucket(by_type, notification_type, refs=refs, is_unsupported=is_unsupported)
        by_support_status[support_status_key] = by_support_status.get(support_status_key, 0) + 1

    _finalize_evidence_buckets(by_type)

    return {
        "total": total,
        "with_evidence_refs": with_refs,
        "unsupported": unsupported,
        "evidence_ref_rate": round(with_refs / total, 4) if total else 0.0,
        "unsupported_rate": round(unsupported / total, 4) if total else 0.0,
        "by_type": dict(sorted(by_type.items())),
        "by_support_status": dict(sorted(by_support_status.items())),
    }


def _add_evidence_bucket(
    buckets: dict[str, dict[str, Any]],
    key: str,
    *,
    refs: list[Any],
    is_unsupported: bool,
    is_not_applicable: bool = False,
) -> None:
    bucket = buckets.setdefault(
        key or "unknown",
        {"total": 0, "not_applicable": 0, "with_evidence_refs": 0, "unsupported": 0},
    )
    bucket["total"] += 1
    bucket["not_applicable"] += 1 if is_not_applicable else 0
    bucket["with_evidence_refs"] += 1 if refs else 0
    bucket["unsupported"] += 1 if is_unsupported else 0


def _finalize_evidence_buckets(buckets: dict[str, dict[str, Any]]) -> None:
    for bucket in buckets.values():
        total = int(bucket.get("total") or 0)
        not_applicable = int(bucket.get("not_applicable") or 0)
        applicable_total = total - not_applicable
        with_refs = int(bucket.get("with_evidence_refs") or 0)
        unsupported = int(bucket.get("unsupported") or 0)
        bucket["applicable_total"] = applicable_total
        bucket["evidence_ref_rate"] = (
            round(with_refs / applicable_total, 4) if applicable_total else 0.0
        )
        bucket["raw_evidence_ref_rate"] = round(with_refs / total, 4) if total else 0.0
        bucket["unsupported_rate"] = round(unsupported / total, 4) if total else 0.0


def _aggregate_external_evidence_coverage(documents: list[KBDocument]) -> dict[str, Any]:
    claim_total = 0
    claims_with_external_sources = 0
    by_kind: dict[str, int] = {}
    missing_external_source_claims: list[dict[str, Any]] = []
    for document in documents:
        if document.doc_type != "claim":
            continue
        claim_total += 1
        external_sources = _document_external_sources(document)
        if external_sources:
            claims_with_external_sources += 1
        elif (document.metadata_json or {}).get("review_status") == "reviewed":
            missing_external_source_claims.append(
                {
                    "doc_id": document.doc_id,
                    "title": document.title,
                    "entity_type": document.entity_type,
                    "entity_id": document.entity_id,
                }
            )
        for source in external_sources:
            kind = str(source.get("kind") or "other")
            by_kind[kind] = by_kind.get(kind, 0) + 1

    external_source_rate = round(claims_with_external_sources / claim_total, 4) if claim_total else 0.0
    missing_external_source_claims.sort(key=lambda item: item["doc_id"])
    return {
        "claim_total": claim_total,
        "claims_with_external_sources": claims_with_external_sources,
        "external_source_rate": external_source_rate,
        "target_external_source_rate": EXTERNAL_EVIDENCE_SOURCE_RATE_TARGET,
        "meets_target": external_source_rate >= EXTERNAL_EVIDENCE_SOURCE_RATE_TARGET if claim_total else False,
        "missing_external_source_claims": missing_external_source_claims[:10],
        "by_kind": dict(sorted(by_kind.items())),
    }


def _aggregate_protocol_review_coverage(documents: list[KBDocument]) -> dict[str, Any]:
    protocols = [document for document in documents if document.doc_type == "protocol"]
    contraindications = [document for document in documents if document.doc_type == "contraindication"]
    eval_cases = [document for document in documents if document.doc_type == "eval_case"]
    draft_protocols = []
    needs_review_protocols = []
    paid_content_lint_violations = []
    high_risk_protocols_missing_external_evidence = []
    by_review_status: dict[str, int] = {}
    by_risk_level: dict[str, int] = {}

    for protocol in protocols:
        metadata = protocol.metadata_json or {}
        review_status = str(metadata.get("review_status") or "unreviewed")
        risk_level = str(metadata.get("risk_level") or "unknown")
        by_review_status[review_status] = by_review_status.get(review_status, 0) + 1
        by_risk_level[risk_level] = by_risk_level.get(risk_level, 0) + 1

        issue = {
            **_compact_issue(protocol),
            "review_status": review_status,
            "risk_level": risk_level,
        }
        if review_status == "draft":
            draft_protocols.append(issue)
        if review_status == "needs_review":
            needs_review_protocols.append(issue)
        if _has_paid_content_lint_violation(protocol):
            paid_content_lint_violations.append(issue)
        if risk_level == "high" and not _document_external_sources(protocol):
            high_risk_protocols_missing_external_evidence.append(issue)

    for issue_list in (
        draft_protocols,
        needs_review_protocols,
        paid_content_lint_violations,
        high_risk_protocols_missing_external_evidence,
    ):
        issue_list.sort(key=lambda item: str(item.get("doc_id") or ""))

    return {
        "protocols_total": len(protocols),
        "draft_protocols": len(draft_protocols),
        "needs_review_protocols": len(needs_review_protocols),
        "contraindications_total": len(contraindications),
        "eval_cases_total": len(eval_cases),
        "paid_content_lint_violations": len(paid_content_lint_violations),
        "high_risk_protocols_missing_external_evidence": len(high_risk_protocols_missing_external_evidence),
        "by_review_status": dict(sorted(by_review_status.items())),
        "by_risk_level": dict(sorted(by_risk_level.items())),
        "issues": {
            "draft_protocols": draft_protocols[:10],
            "needs_review_protocols": needs_review_protocols[:10],
            "paid_content_lint_violations": paid_content_lint_violations[:10],
            "high_risk_protocols_missing_external_evidence": high_risk_protocols_missing_external_evidence[:10],
        },
    }


def _has_paid_content_lint_violation(document: KBDocument) -> bool:
    metadata = document.metadata_json or {}
    policy = str(metadata.get("paid_source_policy") or "").strip()
    if policy and policy != "transformed_summary_only":
        return True

    text = "\n".join(
        str(part)
        for part in (
            document.title,
            document.summary,
            document.body,
            metadata.get("raw_excerpt"),
            metadata.get("source_excerpt"),
            metadata.get("lesson_excerpt"),
        )
        if part
    )
    paid_markers = (
        "付费课程正文",
        "原样放入",
        "raw_excerpt",
        "source_excerpt",
        "逐字稿",
        "transcript",
    )
    return any(marker in text for marker in paid_markers)


def _review_queue_reasons(
    *,
    review_status: str,
    external_source_count: int,
    candidate_duplicates: list[str],
    feedback_disagree_count: int,
) -> list[str]:
    reasons: list[str] = []
    if review_status == "draft":
        reasons.append("draft")
    if review_status == "needs_review":
        reasons.append("needs_review")
    if external_source_count == 0:
        reasons.append("missing_external_evidence")
    if candidate_duplicates:
        reasons.append("candidate_duplicate")
    if feedback_disagree_count > 0:
        reasons.append("user_feedback")
    return reasons


def _review_queue_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    priority = {
        "needs_review": 0,
        "draft": 1,
        "user_feedback": 2,
        "candidate_duplicate": 3,
        "missing_external_evidence": 4,
    }
    reasons = item.get("reasons") if isinstance(item.get("reasons"), list) else []
    reason_rank = min((priority.get(str(reason), 9) for reason in reasons), default=9)
    return (reason_rank, str(item.get("doc_id") or ""))


def _normalize_external_source(source: dict[str, Any], *, actor: str) -> dict[str, Any] | None:
    source_id = str(source.get("source") or "").strip()
    if not source_id:
        return None

    now = datetime.now(UTC).isoformat()
    return {
        "kind": str(source.get("kind") or source_detail(source_id)["kind"]).strip() or "external",
        "source": source_id,
        "title": str(source.get("title") or "").strip() or None,
        "url": str(source.get("url") or "").strip() or None,
        "review_status": str(source.get("review_status") or "reviewed").strip() or "reviewed",
        "reviewed_at": str(source.get("reviewed_at") or now),
        "reviewed_by": str(source.get("reviewed_by") or actor),
    }


def _document_external_sources(document: KBDocument) -> list[dict[str, Any]]:
    metadata = document.metadata_json or {}
    external_sources = metadata.get("external_sources")
    if isinstance(external_sources, list):
        return [source for source in external_sources if isinstance(source, dict)]
    result: list[dict[str, Any]] = []
    for source in document.sources or []:
        source_text = str(source)
        if source_text.startswith("pubmed:"):
            result.append({"kind": "research", "source": source_text})
        elif source_text.startswith("guideline:"):
            result.append({"kind": "guideline", "source": source_text})
    return result


def _latest_lifecycle_report(db: Session) -> dict[str, Any] | None:
    audit = (
        db.query(KBAudit)
        .filter(KBAudit.op == "lifecycle_report")
        .order_by(KBAudit.ts.desc(), KBAudit.id.desc())
        .first()
    )
    if audit is None:
        return None
    return {
        "id": audit.id,
        "op": audit.op,
        "actor": audit.actor,
        "ts": audit.ts.isoformat() if audit.ts else None,
        "diff": audit.diff or {},
    }


def _configured_system_kb_artifact_dir(
    artifact_dir: str | Path | None = None,
    *,
    workspace: str = "release",
) -> Path:
    if workspace not in {"release", "agent_package"}:
        raise ValueError(f"invalid dedao-kbase review workspace: {workspace}")
    if artifact_dir is not None:
        root = Path(artifact_dir)
    elif workspace == "agent_package":
        if not settings.dedao_kbase_review_artifact_dir:
            raise ValueError(
                "DEDAO_KBASE_REVIEW_ARTIFACT_DIR is required for the Agent Package review workspace"
            )
        root = Path(settings.dedao_kbase_review_artifact_dir) / "agent-packages"
    elif settings.dedao_kbase_review_artifact_dir:
        root = Path(settings.dedao_kbase_review_artifact_dir)
    elif settings.system_kb_artifact_dir:
        root = Path(settings.system_kb_artifact_dir)
    else:
        root = Path(__file__).resolve().parents[2] / "data" / "system_kb_v2_seed"
    return root.expanduser()


def _require_system_kb_artifact_dir(root: Path) -> None:
    if not root.exists():
        raise ValueError(f"system KB artifact dir does not exist: {root}")


def _require_valid_review_workspace(root: Path) -> None:
    if not workspace_artifacts_valid(root):
        raise ValueError(f"dedao-kbase review workspace is incomplete or corrupt: {root}")


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read_artifact_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _artifact_preview(root: Path, *, limit: int) -> dict[str, Any]:
    sections = {
        "pages": "pages.jsonl",
        "entities": "entities.jsonl",
        "claims": "claims.jsonl",
        "protocols": "protocols.jsonl",
        "contraindications": "contraindications.jsonl",
        "eval_cases": "eval_cases.jsonl",
        "relations": "relations.jsonl",
    }
    preview: dict[str, Any] = {"counts": {}}
    for section, file_name in sections.items():
        rows = _read_artifact_jsonl(root / file_name)
        preview["counts"][section] = len(rows)
        if section == "relations":
            preview[section] = [_relation_preview(row) for row in rows[:limit]]
        else:
            preview[section] = [_document_preview(row) for row in rows[:limit]]
    return preview


def _preview_reviewed_artifact_import(db: Session, root: Path) -> dict[str, int]:
    from app.services.system_knowledge_importer import DOC_FILES

    reviewed_existing_doc_ids = {
        document.doc_id
        for document in db.query(KBDocument.doc_id, KBDocument.metadata_json, KBDocument.is_archived).all()
        if not document.is_archived
        and isinstance(document.metadata_json, dict)
        and document.metadata_json.get("review_status") == "reviewed"
    }
    reviewed_artifact_doc_ids: set[str] = set()
    non_reviewed_artifact_doc_ids: set[str] = set()
    documents = 0
    skipped_documents = 0
    for file_name in DOC_FILES:
        for payload in _read_artifact_jsonl(root / file_name):
            doc_id = str(payload.get("doc_id") or "")
            if _artifact_payload_review_status(payload) == "reviewed":
                documents += 1
                if doc_id:
                    reviewed_artifact_doc_ids.add(doc_id)
                continue
            skipped_documents += 1
            if doc_id:
                non_reviewed_artifact_doc_ids.add(doc_id)

    reviewed_doc_ids_after_import = (
        reviewed_existing_doc_ids - non_reviewed_artifact_doc_ids
    ) | reviewed_artifact_doc_ids
    edges = 0
    skipped_edges = 0
    for payload in _read_artifact_jsonl(root / "relations.jsonl"):
        if (
            payload.get("src_doc_id") in reviewed_doc_ids_after_import
            and payload.get("dst_doc_id") in reviewed_doc_ids_after_import
        ):
            edges += 1
        else:
            skipped_edges += 1

    return {
        "documents": documents,
        "edges": edges,
        "skipped_documents": skipped_documents,
        "skipped_edges": skipped_edges,
    }


def _artifact_payload_review_status(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("review_status")
    return str(value) if value is not None else None


def _document_preview(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return {
        "doc_id": row.get("doc_id"),
        "doc_type": row.get("doc_type"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "entity_type": row.get("entity_type"),
        "entity_id": row.get("entity_id"),
        "evidence_level": row.get("evidence_level"),
        "confidence": row.get("confidence"),
        "sources": row.get("sources") or [],
        "review_status": metadata.get("review_status"),
        "origin": metadata.get("origin"),
    }


def _relation_preview(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return {
        "src_doc_id": row.get("src_doc_id"),
        "dst_doc_id": row.get("dst_doc_id"),
        "relation": row.get("relation"),
        "confidence": row.get("confidence"),
        "review_status": metadata.get("review_status"),
    }


def _latest_dedao_kbase_export_sync_draft(db: Session) -> dict[str, Any] | None:
    audit = (
        db.query(KBAudit)
        .filter(KBAudit.op == "dedao_kbase_export_sync_draft")
        .order_by(KBAudit.ts.desc(), KBAudit.id.desc())
        .first()
    )
    if audit is None:
        return None
    return {
        "id": audit.id,
        "op": audit.op,
        "actor": audit.actor,
        "ts": audit.ts.isoformat() if audit.ts else None,
        "diff": audit.diff or {},
    }


def get_system_kb_pgvector_health(db: Session) -> dict[str, Any]:
    """Return pgvector readiness and dense-index coverage for admin operations."""

    expected_dimensions = int(settings.system_kb_embedding_dimensions)
    health: dict[str, Any] = {
        "enabled": bool(settings.system_kb_pgvector_enabled),
        "postgres": _is_postgres_session(db),
        "extension_version": None,
        "table_exists": False,
        "embedding_type": None,
        "embedding_model": settings.system_kb_embedding_model,
        "embedding_dimensions": expected_dimensions,
        "embedding_batch_size": int(settings.system_kb_embedding_batch_size),
        "embedding_rows": 0,
        "embedding_model_counts": {},
        "expected_documents": db.query(KBDocument).filter(KBDocument.is_archived.is_(False)).count(),
        "current_vector_backend": _pgvector_backend_for_session(db) or VECTOR_BACKEND,
        "latest_reindex_report": _latest_system_kb_reindex_report(db),
        "error": None,
    }
    if not health["enabled"] or not health["postgres"]:
        return health

    try:
        health["extension_version"] = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = :name"),
            {"name": "vector"},
        ).scalar()
        table_name = db.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": f"public.{PGVECTOR_TABLE}"},
        ).scalar()
        health["table_exists"] = table_name is not None
        if table_name is None:
            health["current_vector_backend"] = VECTOR_BACKEND
            return health

        health["embedding_type"] = db.execute(
            text(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = :schema
                  AND c.relname = :table
                  AND a.attname = :column
                """
            ),
            {"schema": "public", "table": PGVECTOR_TABLE, "column": "embedding"},
        ).scalar()
        rows = db.execute(
            text(
                f"""
                SELECT embedding_model, COUNT(*)
                FROM {PGVECTOR_TABLE}
                GROUP BY embedding_model
                ORDER BY embedding_model
                """
            )
        ).fetchall()
        model_counts = {str(model): int(count or 0) for model, count in rows}
        health["embedding_model_counts"] = model_counts
        health["embedding_rows"] = sum(model_counts.values())
        health["current_vector_backend"] = _pgvector_backend_for_session(db) or VECTOR_BACKEND
    except SQLAlchemyError as exc:
        health["error"] = str(exc)
        health["current_vector_backend"] = VECTOR_BACKEND
    return health


def _latest_system_kb_reindex_report(db: Session) -> dict[str, Any] | None:
    audit = (
        db.query(KBAudit)
        .filter(KBAudit.op == "system_kb_reindex_report")
        .order_by(KBAudit.ts.desc(), KBAudit.id.desc())
        .first()
    )
    if audit is None:
        return None
    return {
        "id": audit.id,
        "op": audit.op,
        "actor": audit.actor,
        "ts": audit.ts.isoformat() if audit.ts else None,
        "diff": audit.diff or {},
    }


def _knowledge_operations_action_items(
    coverage: dict[str, Any],
    lint: dict[str, Any],
    latest_lifecycle_report: dict[str, Any] | None,
    latest_dedao_sync: dict[str, Any] | None = None,
    pgvector: dict[str, Any] | None = None,
) -> list[str]:
    action_items: list[str] = []
    specialist = coverage.get("specialist_findings") or {}
    if not specialist.get("meets_target", False):
        action_items.append("specialist_evidence_below_target")
    external = coverage.get("external_evidence") or {}
    if external.get("claim_total", 0) and not external.get("meets_target", False):
        action_items.append("external_evidence_coverage_low")
    notification_evidence = coverage.get("notification_evidence") or {}
    if (
        notification_evidence.get("total", 0)
        and notification_evidence.get("unsupported_rate", 0.0) > 0.2
    ):
        action_items.append("notification_evidence_unsupported_high")
    protocol_review = coverage.get("protocol_review") or {}
    if protocol_review.get("draft_protocols", 0) or protocol_review.get("needs_review_protocols", 0):
        action_items.append("protocol_review_needed")
    if protocol_review.get("paid_content_lint_violations", 0):
        action_items.append("protocol_paid_content_lint_violations")
    if protocol_review.get("high_risk_protocols_missing_external_evidence", 0):
        action_items.append("high_risk_protocol_external_evidence_missing")
    domain_coverage = coverage.get("domain_coverage") or {}
    if any(
        int((bucket.get("source_freshness") or {}).get("stale_sources") or 0) > 0
        or int((bucket.get("source_freshness") or {}).get("missing_last_reviewed_sources") or 0) > 0
        for bucket in domain_coverage.values()
        if isinstance(bucket, dict)
    ):
        action_items.append("kb_stale_sources_present")
    lint_summary = lint.get("summary") if isinstance(lint, dict) else {}
    if isinstance(lint_summary, dict) and any(int(count or 0) > 0 for count in lint_summary.values()):
        action_items.append("kb_lint_issues_present")
    if latest_lifecycle_report is None:
        action_items.append("lifecycle_report_missing")
    else:
        lifecycle_diff = latest_lifecycle_report.get("diff")
        eval_report = lifecycle_diff.get("eval") if isinstance(lifecycle_diff, dict) else None
        if not isinstance(eval_report, dict):
            action_items.append("kb_eval_report_missing")
        else:
            if int(eval_report.get("failed") or 0) > 0:
                action_items.append("kb_eval_failures_present")
            if int(eval_report.get("total") or 0) == 0:
                action_items.append("kb_eval_cases_missing")
    if latest_dedao_sync is not None:
        dedao_diff = latest_dedao_sync.get("diff")
        gate = dedao_diff.get("gate") if isinstance(dedao_diff, dict) else None
        blocking_reasons = gate.get("blocking_reasons") if isinstance(gate, dict) else []
        if isinstance(gate, dict) and gate.get("serving_allowed") is False and blocking_reasons:
            action_items.append("dedao_kbase_draft_review_needed")
    if pgvector:
        action_items.extend(_pgvector_action_items(pgvector))
    return action_items


def _pgvector_action_items(pgvector: dict[str, Any]) -> list[str]:
    latest = pgvector.get("latest_reindex_report")
    if not isinstance(latest, dict):
        return []
    diff = latest.get("diff") if isinstance(latest.get("diff"), dict) else {}
    reindex = diff.get("reindex") if isinstance(diff.get("reindex"), dict) else {}
    reported_pgvector = diff.get("pgvector") if isinstance(diff.get("pgvector"), dict) else {}
    documents = int(reindex.get("documents") or 0)
    dense_vectors = int(reindex.get("dense_vectors") or 0)
    items: list[str] = []
    if documents > 0 and dense_vectors < documents:
        items.append("kb_pgvector_dense_coverage_low")
    reported_postgres = reported_pgvector.get("postgres")
    if reported_postgres is None:
        reported_postgres = pgvector.get("postgres")
    reported_backend = reported_pgvector.get("current_vector_backend") or pgvector.get("current_vector_backend")
    if documents > 0 and reported_postgres and reported_backend == VECTOR_BACKEND:
        items.append("kb_pgvector_backend_fallback")
    return items


def _extract_finding_evidence_refs(finding: dict[str, Any]) -> list[Any]:
    refs = finding.get("evidence_refs")
    if refs is None and isinstance(finding.get("data"), dict):
        refs = finding["data"].get("evidence_refs")
    if not refs and isinstance(finding.get("data"), dict):
        refs = finding["data"].get("system_kb_evidence_refs")
    return refs if isinstance(refs, list) else []


def _finding_is_unsupported(finding: dict[str, Any], refs: list[Any]) -> bool:
    data = finding.get("data") if isinstance(finding.get("data"), dict) else {}
    evidence_resolution = data.get("evidence_resolution") if isinstance(data.get("evidence_resolution"), dict) else {}
    explicit_status = (
        finding.get("support_status")
        or data.get("support_status")
        or evidence_resolution.get("support_status")
    )
    non_advice_statuses = {"not_applicable", "data_gap", "data_summary"}
    if explicit_status and str(explicit_status).strip().lower() in non_advice_statuses:
        return False

    explicit_unsupported = finding.get("unsupported")
    if explicit_unsupported is None:
        explicit_unsupported = data.get("unsupported")
    if explicit_unsupported is None:
        explicit_unsupported = evidence_resolution.get("unsupported")
    if explicit_unsupported is not None:
        return bool(explicit_unsupported)

    return not refs


def _finding_support_status(
    finding: dict[str, Any],
    refs: list[Any],
    is_unsupported: bool,
) -> str:
    data = finding.get("data") if isinstance(finding.get("data"), dict) else {}
    evidence_resolution = data.get("evidence_resolution") if isinstance(data.get("evidence_resolution"), dict) else {}
    explicit = (
        finding.get("support_status")
        or data.get("support_status")
        or evidence_resolution.get("support_status")
    )
    if explicit:
        return str(explicit)
    if refs:
        return "supported"
    if is_unsupported:
        return "model_inference"
    return "not_applicable"


def _support_status_is_not_applicable(support_status: Any) -> bool:
    return str(support_status or "").strip().lower() in {
        "not_applicable",
        "data_gap",
        "data_summary",
    }


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
        "9p21": "9p21",
        "rs10757274": "9p21",
        "FTO": "FTO",
        "ACTN3": "ACTN3",
        "ALDH2": "ALDH2",
        "TPMT": "TPMT",
        "TPMT_phenotype": "TPMT",
        "NUDT15": "NUDT15",
        "NUDT15_phenotype": "NUDT15",
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
        elif gene == "9p21":
            genotype = (match.group("ninep21") or "AA").upper()
            genetics["9p21"] = genotype
            genetics["rs10757274"] = genotype
        else:
            genetics[gene] = "present"
    return {"genetics": genetics, "labs": {}}
