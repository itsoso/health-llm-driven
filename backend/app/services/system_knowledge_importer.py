"""Import reviewed LLM Wiki v2 artifacts into the serving KB tables."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import hashlib
import json
import logging
import os
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

IMPORT_AUDIT_OP = "import_system_kb_artifacts"
WHOLE_IMPORT_PROOF_MODES = {"off", "shadow"}
DOCUMENT_VALUE_FIELDS = (
    "doc_type",
    "entity_type",
    "entity_id",
    "title",
    "summary",
    "body",
    "content_hash",
    "confidence",
    "evidence_level",
    "applies_when",
    "recommends_lookup",
    "sources",
    "last_confirmed",
    "decay_rate",
    "is_archived",
    "metadata_json",
)
DOCUMENT_MUTATION_FIELDS = tuple(
    field for field in DOCUMENT_VALUE_FIELDS if field != "content_hash"
)
EDGE_VALUE_FIELDS = (
    "confidence",
    "source_claim_id",
    "metadata_json",
)
logger = logging.getLogger(__name__)


def import_system_kb_artifacts(
    db: Session,
    artifact_dir: str | Path,
    actor: str = "system",
) -> dict[str, Any]:
    root = Path(artifact_dir)

    try:
        # Parse, validate and hash immutable file inputs before holding the DB
        # mutation lock. The in-memory artifact snapshot is what the locked
        # proof and import consume, so a concurrent filesystem change cannot
        # alter the active transaction.
        artifact = _load_artifact_state(root)
        artifact_scope = str(root.resolve())

        # This must be the first database operation. Rollback quarantine takes
        # the same transaction lock after writers are stopped, so it drains any
        # import already in flight before archiving the sealed release policy.
        acquire_system_kb_release_mutation_lock(db)

        existing_documents = {
            document.doc_id: document for document in db.query(KBDocument).all()
        }
        existing_edges: dict[tuple[str, str, str], list[KBEdge]] = {}
        for edge in db.query(KBEdge).all():
            key = (edge.src_doc_id, edge.dst_doc_id, edge.relation)
            existing_edges.setdefault(key, []).append(edge)

        existing_reviewed_ids = _reviewed_document_ids(existing_documents.values())
        declared_document_ids = set(artifact["reviewed_payloads"]) | set(
            artifact["non_reviewed_payloads"]
        )
        active_reviewed_artifact_ids = {
            doc_id
            for doc_id, values in artifact["document_values"].items()
            if not values["is_archived"]
        }
        reviewed_after_import = (
            existing_reviewed_ids - declared_document_ids
        ) | active_reviewed_artifact_ids
        valid_relations, skipped_edges = _valid_artifact_relations(
            artifact["relations"],
            reviewed_after_import,
        )

        proof = _evaluate_whole_import_proof(
            artifact=artifact,
            valid_relations=valid_relations,
            existing_documents=existing_documents,
            existing_edges=existing_edges,
        )
        base_result: dict[str, Any] = {
            "documents": len(artifact["reviewed_payloads"]),
            "edges": len(valid_relations),
            "skipped_documents": len(artifact["non_reviewed_payloads"]),
            "skipped_edges": skipped_edges,
            "changed_document_ids": [],
            "changed_document_hashes": {},
            # Artifact absence is not an ownership proof. Import never archives
            # a global KB row merely because one source stopped declaring it.
            # Reindex still removes indexes for rows archived by an authorized
            # lifecycle/reconciliation path.
            "deleted_document_ids": [],
            "artifact_digest": artifact["digest"],
            "proof": proof,
            "skipped_by_proof": False,
        }

        changed_document_hashes: dict[str, str] = {}
        for doc_id, payload in artifact["non_reviewed_payloads"].items():
            document = existing_documents.get(doc_id)
            if _demote_existing_non_reviewed_document(document, payload):
                changed_document_hashes[doc_id] = _content_hash_for_document(document)

        for doc_id, payload in artifact["reviewed_payloads"].items():
            desired_values = artifact["document_values"][doc_id]
            if _upsert_document(
                db,
                payload,
                desired_values=desired_values,
                existing=existing_documents.get(doc_id),
            ):
                changed_document_hashes[doc_id] = desired_values["content_hash"]

        db.flush()
        for edge_key, payload in valid_relations.items():
            _upsert_edge(
                db,
                payload,
                existing=(existing_edges.get(edge_key) or [None])[0],
            )

        base_result["changed_document_ids"] = sorted(changed_document_hashes)
        base_result["changed_document_hashes"] = {
            doc_id: changed_document_hashes[doc_id]
            for doc_id in sorted(changed_document_hashes)
        }
        _record_import_audit(
            db,
            root=root,
            actor=actor,
            result=base_result,
            artifact_scope=artifact_scope,
        )
        db.commit()
        return base_result
    except Exception:
        db.rollback()
        raise


def _load_artifact_state(root: Path) -> dict[str, Any]:
    _require_complete_artifact_set(root)
    manifest = _read_json_object(root / "manifest.json")
    manifest_counts = manifest.get("counts")
    if not isinstance(manifest_counts, dict):
        raise ValueError(f"System KB manifest counts must be an object: {root / 'manifest.json'}")

    reviewed_payloads: dict[str, dict[str, Any]] = {}
    non_reviewed_payloads: dict[str, dict[str, Any]] = {}
    document_values: dict[str, dict[str, Any]] = {}
    document_ids: set[str] = set()
    for file_name in DOC_FILES:
        rows = _read_jsonl(root / file_name)
        _require_manifest_count(
            manifest_counts,
            key=Path(file_name).stem,
            actual=len(rows),
            manifest_path=root / "manifest.json",
        )
        for payload in rows:
            doc_id = str(payload.get("doc_id") or "").strip()
            if not doc_id:
                raise ValueError(f"missing doc_id in {root / file_name}")
            if doc_id in document_ids:
                raise ValueError(f"duplicate System KB doc_id in artifacts: {doc_id}")
            document_ids.add(doc_id)
            if _is_reviewed_payload(payload):
                reviewed_payloads[doc_id] = payload
                document_values[doc_id] = _document_values(payload)
            else:
                non_reviewed_payloads[doc_id] = payload

    relations = _read_jsonl(root / "relations.jsonl")
    _require_manifest_count(
        manifest_counts,
        key="relations",
        actual=len(relations),
        manifest_path=root / "manifest.json",
    )
    projection = {
        "documents": document_values,
        "non_reviewed": {
            doc_id: _non_reviewed_projection(payload)
            for doc_id, payload in sorted(non_reviewed_payloads.items())
        },
        "relations": sorted(
            (_edge_projection(payload) for payload in relations),
            key=lambda item: tuple(item["key"]),
        ),
    }
    return {
        "reviewed_payloads": reviewed_payloads,
        "non_reviewed_payloads": non_reviewed_payloads,
        "document_values": document_values,
        "relations": relations,
        "digest": _canonical_digest(projection),
    }


def _require_complete_artifact_set(root: Path) -> None:
    if not root.is_dir():
        raise ValueError(f"System KB artifact directory does not exist: {root}")
    for file_name in (*DOC_FILES, "relations.jsonl", "manifest.json"):
        path = root / file_name
        if not path.is_file():
            raise ValueError(f"missing required System KB artifact file: {path}")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON object in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required in {path}")
    return value


def _require_manifest_count(
    counts: dict[str, Any],
    *,
    key: str,
    actual: int,
    manifest_path: Path,
) -> None:
    expected = counts.get(key)
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise ValueError(f"invalid manifest count for {key!r} in {manifest_path}")
    if expected != actual:
        raise ValueError(
            f"manifest count mismatch for {key!r}: expected {expected}, got {actual}"
        )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path}:{line_no}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"JSON object required in {path}:{line_no}")
            rows.append(payload)
    return rows


def _document_values(payload: dict[str, Any]) -> dict[str, Any]:
    doc_id = str(payload["doc_id"])
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
        "content_hash": None,
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
    probe = KBDocument(doc_id=doc_id, **values)
    values["content_hash"] = _content_hash_for_document(probe)
    return values


def _content_hash_for_document(document: KBDocument) -> str:
    from app.services.system_knowledge_service import system_kb_document_content_hash

    return system_kb_document_content_hash(document)


def _upsert_document(
    db: Session,
    payload: dict[str, Any],
    *,
    desired_values: dict[str, Any] | None = None,
    existing: KBDocument | None,
) -> bool:
    doc_id = str(payload["doc_id"])
    values = dict(desired_values or _document_values(payload))
    if existing:
        changed = _canonicalize(
            {field: getattr(existing, field) for field in DOCUMENT_MUTATION_FIELDS}
        ) != _canonicalize(
            {field: values[field] for field in DOCUMENT_MUTATION_FIELDS}
        )
        for key, value in values.items():
            if key == "content_hash":
                # The old hash is the stale-index marker. Reindex owns the
                # transition to the new canonical hash after every index has
                # been updated successfully.
                continue
            setattr(existing, key, value)
        return changed
    create_values = dict(values)
    create_values["content_hash"] = None
    db.add(KBDocument(doc_id=doc_id, **create_values))
    return True


def _is_reviewed_payload(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return metadata.get("review_status") == "reviewed"


def _demote_existing_non_reviewed_document(
    existing: KBDocument | None,
    payload: dict[str, Any],
) -> bool:
    doc_id = payload.get("doc_id")
    if not doc_id:
        return False
    if existing is None:
        return False
    metadata = dict(existing.metadata_json or {})
    incoming_metadata = payload.get("metadata")
    incoming_status = None
    if isinstance(incoming_metadata, dict):
        incoming_status = incoming_metadata.get("review_status")
    desired_status = incoming_status or "unreviewed"
    changed = metadata.get("review_status") != desired_status or existing.is_archived
    metadata["review_status"] = desired_status
    existing.metadata_json = metadata
    existing.is_archived = False
    return bool(changed)


def _edge_key(payload: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(payload["src_doc_id"]),
        str(payload["dst_doc_id"]),
        str(payload["relation"]),
    )


def _valid_artifact_relations(
    relations: list[dict[str, Any]],
    reviewed_doc_ids: set[str],
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], int]:
    valid: dict[tuple[str, str, str], dict[str, Any]] = {}
    skipped = 0
    for payload in relations:
        if (
            payload.get("src_doc_id") not in reviewed_doc_ids
            or payload.get("dst_doc_id") not in reviewed_doc_ids
        ):
            skipped += 1
            continue
        key = _edge_key(payload)
        if key in valid:
            raise ValueError(f"duplicate System KB relation in artifacts: {key!r}")
        valid[key] = payload
    return valid, skipped


def _record_import_audit(
    db: Session,
    *,
    root: Path,
    actor: str,
    result: dict[str, Any],
    artifact_scope: str,
) -> None:
    diff = {
        "artifact_dir": str(root),
        "artifact_scope": artifact_scope,
        **result,
    }
    db.add(
        KBAudit(
            doc_id=None,
            op=IMPORT_AUDIT_OP,
            actor=actor,
            diff=diff,
        )
    )


def _normalize_proof_mode() -> tuple[str, str | None, str]:
    raw_mode = os.getenv("SYSTEM_KB_IMPORT_PROOF_MODE", "shadow").strip().lower()
    if raw_mode in WHOLE_IMPORT_PROOF_MODES:
        return raw_mode, None, raw_mode
    if raw_mode == "on":
        logger.warning(
            "SYSTEM_KB_IMPORT_PROOF_MODE=on is not enabled without production "
            "shadow evidence; running the full import"
        )
        return "off", "unproven_skip_mode", raw_mode
    logger.warning(
        "invalid SYSTEM_KB_IMPORT_PROOF_MODE=%r; whole-import reuse disabled",
        raw_mode,
    )
    return "off", "invalid_mode", raw_mode


def _evaluate_whole_import_proof(
    *,
    artifact: dict[str, Any],
    valid_relations: dict[tuple[str, str, str], dict[str, Any]],
    existing_documents: dict[str, KBDocument],
    existing_edges: dict[tuple[str, str, str], list[KBEdge]],
) -> dict[str, Any]:
    mode, mode_error, requested_mode = _normalize_proof_mode()
    if mode == "off":
        return {
            "mode": mode,
            "requested_mode": requested_mode,
            "scope": "declared_artifact_rows",
            "skip_eligible": False,
            "decision": "not_evaluated",
            "reason": mode_error or "disabled",
            "artifact_digest": artifact["digest"],
            "database_digest": None,
        }

    artifact_projection: dict[str, Any] = {
        "documents": {
            doc_id: artifact["document_values"][doc_id]
            for doc_id in sorted(artifact["document_values"])
        },
        "non_reviewed": {
            doc_id: _non_reviewed_projection(payload)
            for doc_id, payload in sorted(artifact["non_reviewed_payloads"].items())
        },
        "relations": {
            _edge_projection_key(key): _edge_values(payload)
            for key, payload in sorted(valid_relations.items())
        },
    }
    database_projection: dict[str, Any] = {
        "documents": {},
        "non_reviewed": {},
        "relations": {},
    }
    for doc_id in artifact_projection["documents"]:
        document = existing_documents.get(doc_id)
        database_projection["documents"][doc_id] = (
            _document_projection(document) if document is not None else None
        )
    for doc_id in artifact["non_reviewed_payloads"]:
        document = existing_documents.get(doc_id)
        database_projection["non_reviewed"][doc_id] = (
            _existing_non_reviewed_projection(document)
            if document is not None
            else None
        )
    for key in valid_relations:
        rows = existing_edges.get(key) or []
        if len(rows) == 1:
            existing_value: dict[str, Any] | None = _edge_object_values(rows[0])
        elif not rows:
            existing_value = None
        else:
            # kb_edges predates a compound uniqueness constraint. Preserve
            # every row and make duplicate drift visible to the proof instead
            # of collapsing it in a dict and reporting a false hit. Cleanup
            # still requires an explicit ownership/reconciliation policy.
            existing_value = {"invalid_duplicate_count": len(rows)}
        database_projection["relations"][_edge_projection_key(key)] = existing_value

    artifact_digest = _canonical_digest(artifact_projection)
    database_digest = _canonical_digest(database_projection)
    decision = "hit" if artifact_digest == database_digest else "miss"
    reason = "match" if decision == "hit" else "drift"
    return {
        "mode": mode,
        "requested_mode": requested_mode,
        "scope": "declared_artifact_rows",
        "skip_eligible": False,
        "decision": decision,
        "reason": reason,
        "artifact_digest": artifact_digest,
        "database_digest": database_digest,
    }


def _document_projection(document: KBDocument) -> dict[str, Any]:
    return _canonicalize(
        {field: getattr(document, field) for field in DOCUMENT_VALUE_FIELDS}
    )


def _non_reviewed_projection(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    review_status = metadata.get("review_status") if isinstance(metadata, dict) else None
    return {
        "is_archived": False,
        "review_status": review_status or "unreviewed",
    }


def _existing_non_reviewed_projection(
    document: KBDocument,
) -> dict[str, Any]:
    return {
        "is_archived": bool(document.is_archived),
        "review_status": (document.metadata_json or {}).get("review_status"),
    }


def _edge_values(payload: dict[str, Any]) -> dict[str, Any]:
    return _canonicalize(
        {
            "confidence": payload.get("confidence"),
            "source_claim_id": payload.get("source_claim_id"),
            "metadata_json": payload.get("metadata") or {},
        }
    )


def _edge_object_values(edge: KBEdge) -> dict[str, Any]:
    return _canonicalize(
        {field: getattr(edge, field) for field in EDGE_VALUE_FIELDS}
    )


def _edge_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": list(_edge_key(payload)),
        "values": _edge_values(payload),
    }


def _edge_projection_key(key: tuple[str, str, str]) -> str:
    return json.dumps(list(key), ensure_ascii=False, separators=(",", ":"))


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonicalize(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = (
            value.replace(tzinfo=UTC)
            if value.tzinfo is None
            else value.astimezone(UTC)
        )
        return normalized.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def _reviewed_document_ids(documents: Iterable[KBDocument]) -> set[str]:
    return {
        document.doc_id
        for document in documents
        if not document.is_archived
        and isinstance(document.metadata_json, dict)
        and document.metadata_json.get("review_status") == "reviewed"
    }


def _upsert_edge(
    db: Session,
    payload: dict[str, Any],
    *,
    existing: KBEdge | None,
) -> None:
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
