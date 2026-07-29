#!/usr/bin/env python3
"""Fail-closed rollback quarantine for runtime-only System KB packs.

The release that introduces a runtime-only authority pack may be rolled back to
code that predates its in-code generic-serving hold. Before any rollback target
starts, this script archives the exact pack documents recorded in the failed
release manifest. Existing import tooling reactivates them on a later successful
deployment, so the compensation is reversible without restoring the whole
database or losing unrelated user writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session

from app.models.system_knowledge import KBAudit, KBDocument


# rollback_release.sh stages this script and executes it after checking out the
# older target revision. Keep the sealed fallback in the hash-verified script so
# rollback does not depend on modules that the old commit cannot contain. On the
# current revision, the canonical policy remains clinical_claim_release via the
# shared helper, and import-time equality prevents the staged fallback drifting.
_STAGED_SEALED_RUNTIME_ONLY_DOCUMENT_TYPES = {
    "claim:c_low_back_emergency_neurologic_red_flags": "claim",
    "claim:c_low_back_serious_cause_screening_boundary": "claim",
    "claim:c_low_back_self_management_activity_boundary": "claim",
    "claim:c_low_back_imaging_not_routine_boundary": "claim",
    "claim:c_chronic_low_back_holistic_care_boundary": "claim",
    "entity:condition:low-back-pain": "entity",
    "eval:low_back_neurologic_red_flags": "eval_case",
    "eval:low_back_serious_cause_screening": "eval_case",
    "eval:low_back_self_management": "eval_case",
    "eval:low_back_imaging_boundary": "eval_case",
    "eval:chronic_low_back_holistic_care": "eval_case",
}
_STAGED_SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY = -2015097304430908920
_RELEASE_POLICY_MODULE = "app.services.system_knowledge_release_policy"

try:
    from app.services.system_knowledge_release_policy import (
        SEALED_RUNTIME_ONLY_DOCUMENT_TYPES as _CURRENT_SEALED_DOCUMENT_TYPES,
        SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY as _CURRENT_MUTATION_LOCK_KEY,
        acquire_system_kb_release_mutation_lock,
    )
except ModuleNotFoundError as exc:
    if exc.name != _RELEASE_POLICY_MODULE:
        raise
    SEALED_RUNTIME_ONLY_DOCUMENT_TYPES = (
        _STAGED_SEALED_RUNTIME_ONLY_DOCUMENT_TYPES
    )
    SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY = (
        _STAGED_SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY
    )

    def acquire_system_kb_release_mutation_lock(db: Session) -> None:
        if db.get_bind().dialect.name != "postgresql":
            return
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                ":system_kb_release_lock_key)"
            ),
            {
                "system_kb_release_lock_key": (
                    SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY
                )
            },
        )
else:
    if (
        dict(_CURRENT_SEALED_DOCUMENT_TYPES)
        != _STAGED_SEALED_RUNTIME_ONLY_DOCUMENT_TYPES
        or _CURRENT_MUTATION_LOCK_KEY
        != _STAGED_SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY
    ):
        raise RuntimeError("staged System KB release policy drift")
    SEALED_RUNTIME_ONLY_DOCUMENT_TYPES = _CURRENT_SEALED_DOCUMENT_TYPES
    SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY = _CURRENT_MUTATION_LOCK_KEY


RUNTIME_ONLY_SERVING_SCOPE = "health_evidence_runtime"
PACK_DOCUMENT_ID_KEYS = (
    ("claim_ids", "claim", "claim:"),
    ("entity_ids", "entity", "entity:"),
    ("eval_case_ids", "eval_case", "eval:"),
)
ROLLBACK_QUARANTINE_AUDIT_OP = "rollback_kb_quarantine"


def runtime_only_document_policy(
    manifest: Mapping[str, Any],
) -> tuple[tuple[str, str], ...]:
    """Validate the release artifact against the immutable ID + type policy."""

    packs = manifest.get("authority_packs", [])
    if not isinstance(packs, list):
        raise ValueError("authority_packs must be a list")

    document_types: dict[str, str] = {}
    for index, pack in enumerate(packs):
        if not isinstance(pack, Mapping):
            raise ValueError(f"authority_packs[{index}] must be an object")
        if pack.get("serving_scope") != RUNTIME_ONLY_SERVING_SCOPE:
            continue
        if pack.get("generic_serving_allowed") is not False:
            raise ValueError(
                f"authority_packs[{index}] must declare "
                "generic_serving_allowed=false"
            )

        pack_document_count = 0
        for key, doc_type, prefix in PACK_DOCUMENT_ID_KEYS:
            values = pack.get(key, [])
            if not isinstance(values, list):
                raise ValueError(f"authority_packs[{index}].{key} must be a list")
            for raw_id in values:
                if (
                    not isinstance(raw_id, str)
                    or not raw_id
                    or raw_id != raw_id.strip()
                ):
                    raise ValueError(
                        f"authority_packs[{index}].{key} contains an invalid ID"
                    )
                if raw_id in document_types:
                    raise ValueError(
                        "runtime-only release contains a duplicate document ID"
                    )
                sealed_type = SEALED_RUNTIME_ONLY_DOCUMENT_TYPES.get(raw_id)
                if sealed_type is not None and sealed_type != doc_type:
                    raise ValueError(
                        "runtime-only sealed document type mismatch"
                    )
                if not raw_id.startswith(prefix):
                    raise ValueError(
                        f"authority_packs[{index}].{key} contains an invalid ID"
                    )
                document_types[raw_id] = doc_type
                pack_document_count += 1
        if not pack_document_count:
            raise ValueError(
                f"authority_packs[{index}] has no runtime-only document IDs"
            )

    if document_types != dict(SEALED_RUNTIME_ONLY_DOCUMENT_TYPES):
        raise ValueError(
            "runtime-only policy drift: sealed document policy mismatch"
        )
    return tuple(sorted(document_types.items()))


def runtime_only_document_ids(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """Return IDs only after the exact sealed ID + doc_type policy validates."""

    return tuple(doc_id for doc_id, _ in runtime_only_document_policy(manifest))


def quarantine_runtime_only_documents(
    db: Session,
    *,
    manifest: Mapping[str, Any],
    actor: str,
) -> dict[str, int]:
    """Archive exact runtime-only documents atomically and audit counts only."""

    normalized_actor = str(actor or "").strip()
    if not normalized_actor or len(normalized_actor) > 120:
        raise ValueError("actor must be 1..120 characters")

    document_policy = runtime_only_document_policy(manifest)
    document_ids = tuple(doc_id for doc_id, _ in document_policy)
    try:
        acquire_system_kb_release_mutation_lock(db)
        typed_target_filter = or_(
            *(
                and_(
                    KBDocument.doc_id == doc_id,
                    KBDocument.doc_type == doc_type,
                )
                for doc_id, doc_type in document_policy
            )
        )
        matched = (
            db.query(KBDocument)
            .filter(typed_target_filter)
            .all()
        )
        archived_documents = 0
        for document in matched:
            if not document.is_archived:
                document.is_archived = True
                archived_documents += 1

        report = {
            "target_documents": len(document_ids),
            "matched_documents": len(matched),
            "archived_documents": archived_documents,
        }
        db.flush()
        remaining_active = (
            db.query(KBDocument)
            .filter(
                KBDocument.doc_id.in_(document_ids),
                KBDocument.is_archived.is_(False),
            )
            .count()
        )
        if remaining_active:
            raise RuntimeError(
                f"runtime-only KB quarantine incomplete: active={remaining_active}"
            )

        db.add(
            KBAudit(
                doc_id=None,
                op=ROLLBACK_QUARANTINE_AUDIT_OP,
                actor=normalized_actor,
                diff=report,
            )
        )
        db.commit()
        return report
    except Exception:
        db.rollback()
        raise


def _load_manifest(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("review manifest must be a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review_manifest")
    parser.add_argument("--actor", default="rollback:runtime-only-kb")
    args = parser.parse_args()

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        report = quarantine_runtime_only_documents(
            db,
            manifest=_load_manifest(Path(args.review_manifest)),
            actor=args.actor,
        )
    finally:
        db.close()

    print(
        "ROLLBACK_KB_QUARANTINE_OK "
        f"targets={report['target_documents']} "
        f"matched={report['matched_documents']} "
        f"archived={report['archived_documents']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
