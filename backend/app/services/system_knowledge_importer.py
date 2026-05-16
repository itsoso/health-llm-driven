"""Import reviewed LLM Wiki v2 artifacts into the serving KB tables."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.system_knowledge import KBAudit, KBDocument, KBEdge


DOC_FILES = ("entities.jsonl", "claims.jsonl", "pages.jsonl")


def import_system_kb_artifacts(db: Session, artifact_dir: str | Path, actor: str = "system") -> dict[str, int]:
    root = Path(artifact_dir)
    documents = 0
    edges = 0

    for file_name in DOC_FILES:
        for payload in _read_jsonl(root / file_name):
            _upsert_document(db, payload)
            documents += 1

    for payload in _read_jsonl(root / "relations.jsonl"):
        _upsert_edge(db, payload)
        edges += 1

    db.add(
        KBAudit(
            doc_id=None,
            op="import_system_kb_artifacts",
            actor=actor,
            diff={"artifact_dir": str(root), "documents": documents, "edges": edges},
        )
    )
    db.commit()
    return {"documents": documents, "edges": edges}


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
        "metadata_json": payload.get("metadata") or {},
    }
    existing = db.query(KBDocument).filter(KBDocument.doc_id == doc_id).first()
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        db.add(KBDocument(doc_id=doc_id, **values))


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
