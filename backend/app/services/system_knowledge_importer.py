"""Import reviewed LLM Wiki v2 artifacts into the serving KB tables."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBAudit, KBDocument, KBEdge
from app.services.system_knowledge_release_policy import (
    acquire_system_kb_release_mutation_lock,
)


DOC_FILES = (
    "entities.jsonl",
    "claims.jsonl",
    "pages.jsonl",
    "protocols.jsonl",
    "contraindications.jsonl",
    "eval_cases.jsonl",
)

CONTRACT_METADATA_KEYS = {
    "protocol_id",
    "source_claims",
    "source_types",
    "forbidden_when",
    "verification",
    "paid_source_policy",
    "trigger",
    "blocks",
    "fallback",
    "severity",
    "case_id",
    "input",
    "expected",
}


def import_system_kb_artifacts(db: Session, artifact_dir: str | Path, actor: str = "system") -> dict[str, int]:
    root = Path(artifact_dir)
    documents = 0
    edges = 0
    skipped_documents = 0
    skipped_edges = 0

    try:
        # This must be the first database operation. Rollback quarantine takes
        # the same transaction lock after writers are stopped, so it drains any
        # import already in flight before archiving the sealed release policy.
        acquire_system_kb_release_mutation_lock(db)

        for file_name in DOC_FILES:
            for payload in _read_jsonl(root / file_name):
                if not _is_reviewed_payload(payload):
                    _demote_existing_non_reviewed_document(db, payload)
                    skipped_documents += 1
                    continue
                _upsert_document(db, payload)
                documents += 1

        db.flush()
        reviewed_doc_ids = _reviewed_document_ids(db)
        for payload in _read_jsonl(root / "relations.jsonl"):
            if (
                payload.get("src_doc_id") not in reviewed_doc_ids
                or payload.get("dst_doc_id") not in reviewed_doc_ids
            ):
                skipped_edges += 1
                continue
            _upsert_edge(db, payload)
            edges += 1

        diff = {
            "artifact_dir": str(root),
            "documents": documents,
            "edges": edges,
            "skipped_documents": skipped_documents,
            "skipped_edges": skipped_edges,
        }
        db.add(
            KBAudit(
                doc_id=None,
                op="import_system_kb_artifacts",
                actor=actor,
                diff=diff,
            )
        )
        db.commit()
        return {
            "documents": documents,
            "edges": edges,
            "skipped_documents": skipped_documents,
            "skipped_edges": skipped_edges,
        }
    except Exception:
        db.rollback()
        raise


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path}:{line_no}: {exc}") from exc
    return rows


def _upsert_document(db: Session, payload: dict[str, Any]) -> None:
    doc_id = payload["doc_id"]
    metadata = dict(payload.get("metadata") or {})
    for key in CONTRACT_METADATA_KEYS:
        if key in payload:
            metadata[key] = payload[key]
    values = {
        "doc_type": payload["doc_type"],
        "entity_type": payload.get("entity_type"),
        "entity_id": payload.get("entity_id"),
        "title": payload.get("title"),
        "summary": payload.get("summary"),
        "body": payload.get("body") or payload.get("summary"),
        "content_hash": payload.get("content_hash"),
        "confidence": payload.get("confidence"),
        "evidence_level": payload.get("evidence_level"),
        "applies_when": payload.get("applies_when") or [],
        "recommends_lookup": payload.get("recommends_lookup") or [],
        "sources": payload.get("sources") or [],
        "last_confirmed": _parse_datetime(payload.get("last_confirmed")),
        "decay_rate": payload.get("decay_rate") or "normal",
        "is_archived": payload.get("is_archived", False),
        "metadata_json": metadata,
    }
    existing = db.query(KBDocument).filter(KBDocument.doc_id == doc_id).first()
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        db.add(KBDocument(doc_id=doc_id, **values))


def _is_reviewed_payload(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return metadata.get("review_status") == "reviewed"


def _demote_existing_non_reviewed_document(db: Session, payload: dict[str, Any]) -> None:
    doc_id = payload.get("doc_id")
    if not doc_id:
        return
    existing = db.query(KBDocument).filter(KBDocument.doc_id == doc_id).first()
    if existing is None:
        return
    metadata = dict(existing.metadata_json or {})
    incoming_metadata = payload.get("metadata")
    incoming_status = None
    if isinstance(incoming_metadata, dict):
        incoming_status = incoming_metadata.get("review_status")
    metadata["review_status"] = incoming_status or "unreviewed"
    existing.metadata_json = metadata
    existing.is_archived = False


def _reviewed_document_ids(db: Session) -> set[str]:
    return {
        document.doc_id
        for document in db.query(KBDocument).all()
        if not document.is_archived
        and isinstance(document.metadata_json, dict)
        and document.metadata_json.get("review_status") == "reviewed"
    }


def _upsert_edge(db: Session, payload: dict[str, Any]) -> None:
    existing = (
        db.query(KBEdge)
        .filter(
            KBEdge.src_doc_id == payload["src_doc_id"],
            KBEdge.dst_doc_id == payload["dst_doc_id"],
            KBEdge.relation == payload["relation"],
        )
        .first()
    )
    values = {
        "confidence": payload.get("confidence"),
        "source_claim_id": payload.get("source_claim_id"),
        "metadata_json": payload.get("metadata") or {},
    }
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        db.add(
            KBEdge(
                src_doc_id=payload["src_doc_id"],
                dst_doc_id=payload["dst_doc_id"],
                relation=payload["relation"],
                **values,
            )
        )


def _parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
