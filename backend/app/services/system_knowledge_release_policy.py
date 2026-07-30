"""Sealed System KB release policy and write-side transaction lock."""

from __future__ import annotations

import hashlib
from types import MappingProxyType
from typing import Final

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.clinical_claim_release import (
    CLINICAL_RELEASE_HOLD_DOCUMENT_IDS,
)


_DOCUMENT_TYPE_BY_PREFIX: Final = {
    "claim:": "claim",
    "entity:": "entity",
    "eval:": "eval_case",
}


def _sealed_document_type(doc_id: str) -> str:
    for prefix, doc_type in _DOCUMENT_TYPE_BY_PREFIX.items():
        if doc_id.startswith(prefix):
            return doc_type
    raise RuntimeError("clinical release hold contains an unsupported document ID")


# IDs remain single-sourced in clinical_claim_release. The type is derived from
# the stable artifact ID namespace, yielding an immutable ID + doc_type policy
# for release/quarantine validation without duplicating the medical allowlist.
SEALED_RUNTIME_ONLY_DOCUMENT_TYPES = MappingProxyType(
    {
        doc_id: _sealed_document_type(doc_id)
        for doc_id in CLINICAL_RELEASE_HOLD_DOCUMENT_IDS
    }
)


def _lock_key() -> int:
    digest = hashlib.blake2b(
        b"reva:system-kb-release-mutation:v1",
        digest_size=8,
    ).digest()
    unsigned = int.from_bytes(digest, byteorder="big", signed=False)
    return unsigned if unsigned < 2**63 else unsigned - 2**64


SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY: Final = _lock_key()


def acquire_system_kb_release_mutation_lock(db: Session) -> None:
    """Serialize release imports and rollback quarantine on PostgreSQL.

    The lock is transaction-scoped, so the import/quarantine commit or rollback
    releases it automatically. SQLite is test/development-only and deliberately
    remains a no-op rather than pretending to coordinate multiple processes.
    """

    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(:system_kb_release_lock_key)"),
        {"system_kb_release_lock_key": SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY},
    )
