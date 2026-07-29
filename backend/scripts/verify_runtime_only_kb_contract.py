#!/usr/bin/env python3
"""Fail-loud release probe for runtime-only System KB serving boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.system_knowledge import KBDocument, KBEdge
from app.services.clinical_claim_release import (
    CLINICAL_RELEASE_HOLD_DOCUMENT_IDS,
    HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS,
    HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE,
    is_clinical_claim_serving_allowed,
)
from app.services.system_knowledge_service import (
    generic_serving_document_filters,
    health_evidence_runtime_document_filters,
)
from app.services.system_knowledge_release_policy import (
    SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY,
    acquire_system_kb_release_mutation_lock,
)
from scripts.quarantine_runtime_only_kb import runtime_only_document_ids


DEFAULT_RUNTIME_ARTIFACT_DIR = (
    Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
)


def _runtime_packs(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_packs = manifest.get("authority_packs", [])
    if not isinstance(raw_packs, list):
        raise RuntimeError("authority_packs must be a list")
    packs: list[Mapping[str, Any]] = []
    for index, pack in enumerate(raw_packs):
        if not isinstance(pack, Mapping):
            raise RuntimeError(f"authority_packs[{index}] must be an object")
        if pack.get("serving_scope") == HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE:
            if pack.get("generic_serving_allowed") is not False:
                raise RuntimeError(
                    f"authority_packs[{index}] must declare "
                    "generic_serving_allowed=false"
                )
            if (
                pack.get("serving_allowed") is not True
                and pack.get("serving_allowed") is not False
            ):
                raise RuntimeError(
                    f"authority_packs[{index}] must declare serving_allowed as boolean"
                )
            packs.append(pack)
    if not packs:
        raise RuntimeError("no runtime-only authority pack")
    return packs


def _claim_ids(packs: list[Mapping[str, Any]]) -> frozenset[str]:
    claim_ids: set[str] = set()
    for index, pack in enumerate(packs):
        if pack.get("serving_allowed") is not True:
            continue
        raw_ids = pack.get("claim_ids", [])
        if not isinstance(raw_ids, list):
            raise RuntimeError(f"runtime pack {index} claim_ids must be a list")
        for raw_id in raw_ids:
            if not isinstance(raw_id, str) or not raw_id.strip():
                raise RuntimeError(f"runtime pack {index} contains an invalid claim ID")
            claim_ids.add(raw_id.strip())
    return frozenset(claim_ids)


def _expected_document_types(
    packs: list[Mapping[str, Any]],
) -> dict[str, str]:
    expected: dict[str, str] = {}
    for index, pack in enumerate(packs):
        for key, doc_type in (
            ("claim_ids", "claim"),
            ("entity_ids", "entity"),
            ("eval_case_ids", "eval_case"),
        ):
            raw_ids = pack.get(key, [])
            if not isinstance(raw_ids, list):
                raise RuntimeError(f"runtime pack {index} {key} must be a list")
            for raw_id in raw_ids:
                doc_id = str(raw_id or "").strip()
                if not doc_id:
                    raise RuntimeError(
                        f"runtime pack {index} contains an invalid document ID"
                    )
                if doc_id in expected:
                    raise RuntimeError(
                        "runtime-only policy drift: duplicate document ID "
                        f"{doc_id!r}"
                    )
                expected[doc_id] = doc_type
    return expected


def verify_runtime_only_policy(
    manifest: Mapping[str, Any],
    *,
    allow_fully_revoked: bool = False,
) -> dict[str, int]:
    """Prove manifest, generic hold, and phase-aware runtime release agree.

    ``allow_fully_revoked`` is only for flag-off guard/staged phases. Any non-empty
    manifest release remains exactly equal to the code-sealed release set.
    """

    packs = _runtime_packs(manifest)
    _expected_document_types(packs)
    try:
        target_ids = frozenset(runtime_only_document_ids(manifest))
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    released_claim_ids = _claim_ids(packs)
    fully_revoked = all(
        pack.get("serving_allowed") is False for pack in packs
    )
    revoked_disabled_phase = (
        allow_fully_revoked
        and fully_revoked
        and not released_claim_ids
    )

    if target_ids != CLINICAL_RELEASE_HOLD_DOCUMENT_IDS:
        raise RuntimeError("runtime-only policy drift: hold set mismatch")
    if (
        not revoked_disabled_phase
        and released_claim_ids != HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS
    ):
        raise RuntimeError("runtime-only policy drift: sealed claim set mismatch")
    if not released_claim_ids.issubset(target_ids):
        raise RuntimeError("runtime-only policy drift: released claim outside pack")
    if any(is_clinical_claim_serving_allowed(doc_id) for doc_id in target_ids):
        raise RuntimeError("runtime-only policy drift: generic serving is allowed")
    if not revoked_disabled_phase:
        if any(
            not is_clinical_claim_serving_allowed(
                claim_id,
                HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE,
            )
            for claim_id in released_claim_ids
        ):
            raise RuntimeError("runtime-only policy drift: sealed claim is unavailable")
        if any(
            is_clinical_claim_serving_allowed(
                doc_id,
                HEALTH_EVIDENCE_RUNTIME_SERVING_SCOPE,
            )
            for doc_id in target_ids - released_claim_ids
        ):
            raise RuntimeError(
                "runtime-only policy drift: non-claim document was released"
            )

    return {
        "runtime_packs": len(packs),
        "target_documents": len(target_ids),
        "released_claims": len(released_claim_ids),
    }


def _verify_surface_projections(
    db: Session,
    *,
    target_ids: frozenset[str],
    expected_types: Mapping[str, str],
) -> tuple[int, int]:
    """Probe Desktop and Genetic positive/negative paths in one savepoint."""

    from app.api.desktop import _knowledge_summary
    from app.services import genetic_report

    held_claim_ids = sorted(
        doc_id
        for doc_id in target_ids
        if expected_types.get(doc_id) == "claim"
    )
    if not held_claim_ids:
        raise RuntimeError("runtime-only pack has no held claim for surface probe")
    held_claim_id = held_claim_ids[0]
    probe_suffix = uuid.uuid4().hex
    probe_gene = f"RELEASE_PROBE_{probe_suffix}"
    visible_entity_id = f"000:runtime-visible-entity:{probe_suffix}"
    visible_claim_id = f"claim:runtime-visible:{probe_suffix}"
    nested = db.begin_nested()
    try:
        held_claim = (
            db.query(KBDocument)
            .filter(KBDocument.doc_id == held_claim_id)
            .first()
        )
        if held_claim is None:
            held_claim = KBDocument(
                doc_id=held_claim_id,
                doc_type="claim",
                title="release probe held claim",
                metadata_json={"review_status": "reviewed"},
                is_archived=False,
            )
            db.add(held_claim)
        else:
            held_claim.doc_type = "claim"
            held_claim.is_archived = False
            held_claim.metadata_json = {
                **(held_claim.metadata_json or {}),
                "review_status": "reviewed",
            }
        db.add(
            KBDocument(
                doc_id=visible_entity_id,
                doc_type="entity",
                entity_type="gene",
                entity_id=probe_gene,
                title="runtime visible probe gene",
                metadata_json={"review_status": "reviewed"},
                is_archived=False,
            )
        )
        db.add(
            KBDocument(
                doc_id=visible_claim_id,
                doc_type="claim",
                title="runtime visible probe claim",
                confidence=1.0,
                metadata_json={"review_status": "reviewed"},
                is_archived=False,
            )
        )
        db.add(
            KBEdge(
                src_doc_id=visible_entity_id,
                dst_doc_id=held_claim_id,
                relation="release_probe_must_not_serve",
                confidence=1.0,
            )
        )
        db.add(
            KBEdge(
                src_doc_id=visible_entity_id,
                dst_doc_id=visible_claim_id,
                relation="release_probe_must_serve",
                confidence=1.0,
            )
        )
        db.flush()

        desktop_summary = _knowledge_summary(db)
        generic_doc_ids = frozenset(
            row.doc_id
            for row in db.query(KBDocument.doc_id)
            .filter(*generic_serving_document_filters())
            .all()
        )
        if desktop_summary["document_count"] != len(generic_doc_ids):
            raise RuntimeError(
                "Desktop knowledge projection diverges from generic serving"
            )
        expected_edge_count = (
            db.query(KBEdge.edge_id)
            .filter(
                KBEdge.src_doc_id.in_(generic_doc_ids),
                KBEdge.dst_doc_id.in_(generic_doc_ids),
            )
            .count()
            if generic_doc_ids
            else 0
        )
        if desktop_summary["edge_count"] != expected_edge_count:
            raise RuntimeError(
                "Desktop edge projection diverges from generic serving"
            )
        desktop_recent_ids = {
            item["doc_id"] for item in desktop_summary["recent_documents"]
        }
        if visible_entity_id not in desktop_recent_ids:
            raise RuntimeError(
                "Desktop knowledge projection dropped visible sentinel"
            )
        desktop_held_ids = desktop_recent_ids.intersection(target_ids)
        if desktop_held_ids:
            raise RuntimeError(
                "Desktop knowledge projection exposed runtime-only documents"
            )

        items = [{"gene": probe_gene, "hit": True}]
        genetic_report._attach_evidence_refs(db, items)
        evidence_refs = list(items[0].get("evidence_refs") or [])
        exposed = set(evidence_refs).intersection(target_ids)
        if exposed:
            raise RuntimeError(
                "Genetic evidence projection exposed runtime-only claim"
            )
        if evidence_refs != [visible_claim_id]:
            raise RuntimeError(
                "Genetic evidence projection dropped visible sentinel"
            )
        return len(desktop_held_ids), len(exposed)
    finally:
        nested.rollback()
        db.expire_all()


def verify_runtime_only_database(
    db: Session,
    *,
    manifest: Mapping[str, Any],
    require_present: bool,
    allow_fully_revoked: bool = False,
) -> dict[str, int]:
    """Prove DB rows obey generic and sealed-runtime projections."""

    packs = _runtime_packs(manifest)
    verify_runtime_only_policy(
        manifest,
        allow_fully_revoked=allow_fully_revoked,
    )
    target_ids = frozenset(runtime_only_document_ids(manifest))
    expected_types = _expected_document_types(packs)
    matched_documents = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id.in_(target_ids))
        .all()
    )
    matched_ids = frozenset(document.doc_id for document in matched_documents)
    if require_present and matched_ids != target_ids:
        raise RuntimeError(
            "runtime-only KB import incomplete: "
            f"expected={len(target_ids)} matched={len(matched_ids)}"
        )
    active_reviewed_ids = frozenset(
        document.doc_id
        for document in matched_documents
        if (
            not document.is_archived
            and (document.metadata_json or {}).get("review_status") == "reviewed"
            and document.doc_type == expected_types.get(document.doc_id)
        )
    )
    if require_present and active_reviewed_ids != target_ids:
        raise RuntimeError(
            "runtime-only KB active reviewed pack mismatch: "
            f"expected={len(target_ids)} eligible={len(active_reviewed_ids)}"
        )

    generic_eligible_ids = frozenset(
        row.doc_id
        for row in db.query(KBDocument.doc_id)
        .filter(
            KBDocument.doc_id.in_(target_ids),
            *generic_serving_document_filters(),
        )
        .all()
    )
    if generic_eligible_ids:
        raise RuntimeError(
            "runtime-only KB generic hold failed: "
            f"eligible={len(generic_eligible_ids)}"
        )

    runtime_eligible_ids = frozenset(
        row.doc_id
        for row in db.query(KBDocument.doc_id)
        .filter(*health_evidence_runtime_document_filters())
        .all()
    )
    if require_present and (
        runtime_eligible_ids != HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS
    ):
        raise RuntimeError(
            "runtime-only KB exact release failed: "
            f"expected={len(HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS)} "
            f"eligible={len(runtime_eligible_ids)}"
        )
    if require_present:
        from app.services.health_evidence.authority import (
            is_current_health_evidence_document,
        )
        from app.services.system_knowledge_service import serialize_document

        invalid_sealed_claims = [
            document.doc_id
            for document in matched_documents
            if (
                document.doc_id
                in HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS
                and not is_current_health_evidence_document(
                    serialize_document(document)
                )
            )
        ]
        if invalid_sealed_claims:
            raise RuntimeError(
                "runtime-only KB sealed artifact mismatch: "
                f"invalid={len(invalid_sealed_claims)}"
            )

    desktop_held_documents, genetic_held_claims = _verify_surface_projections(
        db,
        target_ids=target_ids,
        expected_types=expected_types,
    )

    return {
        "target_documents": len(target_ids),
        "matched_documents": len(matched_ids),
        "generic_eligible_documents": len(generic_eligible_ids),
        "runtime_eligible_claims": len(runtime_eligible_ids),
        "desktop_held_documents": desktop_held_documents,
        "genetic_held_claims": genetic_held_claims,
    }


def _eval_artifact_material(
    *,
    doc_id: object,
    case_id: object,
    case_input: object,
    expected: object,
) -> dict[str, Any]:
    normalized_doc_id = str(doc_id or "").strip()
    normalized_case_id = str(case_id or "").strip()
    if not normalized_doc_id or normalized_case_id != normalized_doc_id:
        raise RuntimeError("runtime eval artifact identity mismatch")
    if not isinstance(expected, Mapping) or not expected:
        raise RuntimeError("runtime eval artifact expected metadata is empty")
    if not isinstance(case_input, Mapping) or not case_input:
        raise RuntimeError("runtime eval artifact input metadata is empty")
    search_query = case_input.get("search_query")
    lookup_twin = case_input.get("lookup_twin")
    has_search_query = isinstance(search_query, str) and bool(
        search_query.strip()
    )
    has_lookup_twin = isinstance(lookup_twin, Mapping) and bool(lookup_twin)
    if not (has_search_query or has_lookup_twin):
        raise RuntimeError(
            "runtime eval artifact input has no executable behavior"
        )
    if (
        "search_query" in expected
        and expected.get("search_query") != search_query
    ):
        raise RuntimeError(
            "runtime eval artifact executable search query mismatch"
        )
    if (
        "lookup_twin" in expected
        and expected.get("lookup_twin") != lookup_twin
    ):
        raise RuntimeError(
            "runtime eval artifact executable Twin lookup mismatch"
        )
    required_doc_ids = expected.get("required_doc_ids")
    if (
        not isinstance(required_doc_ids, list)
        or len(required_doc_ids) != 1
        or any(
            not isinstance(raw_id, str) or not raw_id.strip()
            for raw_id in required_doc_ids
        )
    ):
        raise RuntimeError(
            "runtime eval artifact must seal exactly one required document ID"
        )
    return {
        "doc_id": normalized_doc_id,
        "case_id": normalized_case_id,
        "input": case_input,
        "expected": expected,
    }


def _eval_artifact_sha256(material: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_runtime_eval_artifact_contract(
    *,
    artifact_dir: Path,
    eval_case_ids: frozenset[str],
) -> tuple[dict[str, str], int]:
    eval_path = artifact_dir / "eval_cases.jsonl"
    if not eval_path.is_file():
        raise RuntimeError(f"runtime eval artifact is missing: {eval_path}")

    artifact_hashes: dict[str, str] = {}
    measurable_targets = 0
    with eval_path.open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"invalid runtime eval artifact JSON at line {line_no}"
                ) from exc
            if not isinstance(payload, Mapping):
                raise RuntimeError(
                    f"runtime eval artifact line {line_no} must be an object"
                )
            doc_id = str(payload.get("doc_id") or "").strip()
            if doc_id not in eval_case_ids:
                continue
            if doc_id in artifact_hashes:
                raise RuntimeError(
                    f"runtime eval artifact duplicate document ID {doc_id!r}"
                )
            material = _eval_artifact_material(
                doc_id=doc_id,
                case_id=payload.get("case_id"),
                case_input=payload.get("input"),
                expected=payload.get("expected"),
            )
            artifact_hashes[doc_id] = _eval_artifact_sha256(material)
            measurable_targets += len(material["expected"]["required_doc_ids"])

    if frozenset(artifact_hashes) != eval_case_ids:
        raise RuntimeError(
            "runtime eval artifact set mismatch: "
            f"expected={len(eval_case_ids)} matched={len(artifact_hashes)}"
        )
    return artifact_hashes, measurable_targets


def verify_enabled_runtime(
    db: Session,
    *,
    manifest: Mapping[str, Any],
    artifact_dir: Path | None = None,
) -> dict[str, int]:
    """Exercise the real sealed retrieval path through every released eval."""

    eval_case_ids: set[str] = set()
    for index, pack in enumerate(_runtime_packs(manifest)):
        if pack.get("serving_allowed") is not True:
            continue
        raw_ids = pack.get("eval_case_ids", [])
        if not isinstance(raw_ids, list):
            raise RuntimeError(f"runtime pack {index} eval_case_ids must be a list")
        for raw_id in raw_ids:
            eval_id = str(raw_id or "").strip()
            if not eval_id:
                raise RuntimeError(
                    f"runtime pack {index} contains an invalid eval case ID"
                )
            eval_case_ids.add(eval_id)
    if not eval_case_ids:
        raise RuntimeError("enabled runtime has no release eval cases")
    sealed_eval_ids = frozenset(eval_case_ids)
    artifact_hashes, expected_targets = _load_runtime_eval_artifact_contract(
        artifact_dir=artifact_dir or DEFAULT_RUNTIME_ARTIFACT_DIR,
        eval_case_ids=sealed_eval_ids,
    )
    eval_documents = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id.in_(sealed_eval_ids))
        .all()
    )
    if (
        len(eval_documents) != len(sealed_eval_ids)
        or frozenset(document.doc_id for document in eval_documents)
        != sealed_eval_ids
    ):
        raise RuntimeError("enabled runtime eval artifact set mismatch")
    for document in eval_documents:
        metadata = document.metadata_json or {}
        try:
            material = _eval_artifact_material(
                doc_id=document.doc_id,
                case_id=metadata.get("case_id"),
                case_input=metadata.get("input"),
                expected=metadata.get("expected"),
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"enabled runtime eval artifact mismatch: {document.doc_id}"
            ) from exc
        if (
            document.doc_type != "eval_case"
            or document.is_archived
            or metadata.get("review_status") != "reviewed"
            or _eval_artifact_sha256(material)
            != artifact_hashes[document.doc_id]
        ):
            raise RuntimeError(
                f"enabled runtime eval artifact mismatch: {document.doc_id}"
            )

    from app.services.system_knowledge_eval import run_system_kb_eval_cases

    report = run_system_kb_eval_cases(
        db,
        exact_doc_ids=sealed_eval_ids,
        limit=len(eval_case_ids),
    )
    total = int(report.get("total") or 0)
    failed = int(report.get("failed") or 0)
    cases = report.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("enabled runtime eval report has no case details")
    actual_doc_ids = [
        str(case.get("doc_id") or "").strip()
        for case in cases
        if isinstance(case, Mapping)
    ]
    actual_case_ids = [
        str(case.get("case_id") or "").strip()
        for case in cases
        if isinstance(case, Mapping)
    ]
    exact_case_set = (
        len(actual_doc_ids) == len(sealed_eval_ids)
        and len(actual_case_ids) == len(sealed_eval_ids)
        and frozenset(actual_doc_ids) == sealed_eval_ids
        and frozenset(actual_case_ids) == sealed_eval_ids
        and all(
            doc_id == case_id
            for doc_id, case_id in zip(actual_doc_ids, actual_case_ids)
        )
    )
    metrics = report.get("metrics")
    exact_metrics = (
        isinstance(metrics, Mapping)
        and int(metrics.get("measurable_cases") or 0) == len(sealed_eval_ids)
        and int(metrics.get("measurable_targets") or 0) == expected_targets
        and float(metrics.get("recall@5") or 0.0) == 1.0
        and float(metrics.get("recall@10") or 0.0) == 1.0
        and float(metrics.get("mrr") or 0.0) == 1.0
        and all(
            isinstance(case, Mapping)
            and case.get("rank_measurable") is True
            and case.get("hit_rank") == 1
            for case in cases
        )
    )
    if (
        total != len(sealed_eval_ids)
        or failed
        or not exact_case_set
        or not exact_metrics
    ):
        raise RuntimeError(
            "enabled runtime eval failed: "
            f"expected={len(sealed_eval_ids)} total={total} failed={failed}"
        )
    return {
        "runtime_eval_cases": total,
        "runtime_eval_failures": failed,
    }


def _load_manifest(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError("review manifest must be a JSON object")
    return payload


class _TransactionPreservingProbeSession:
    """Delegate reads while forbidding transaction-ending probe fallbacks.

    The release advisory lock is transaction-scoped. A serving helper that
    catches a read error and calls ``Session.rollback()`` would otherwise
    silently release the lock and let an importer mutate the KB while the probe
    keeps running. In release-probe mode such fallbacks must fail loud; the
    outer ``main`` cleanup still rolls back the real session exactly once.
    """

    def __init__(self, db: Session):
        self._db = db
        begin_nested = getattr(db, "begin_nested", None)
        self._savepoint = (
            begin_nested() if callable(begin_nested) else None
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)

    def commit(self) -> None:
        raise RuntimeError(
            "runtime-only KB contract probe attempted to commit its "
            "lock-holding transaction"
        )

    def rollback(self) -> None:
        self._rollback_probe_savepoint()
        raise RuntimeError(
            "runtime-only KB contract probe attempted to rollback its "
            "lock-holding transaction"
        )

    def close(self) -> None:
        raise RuntimeError(
            "runtime-only KB contract probe attempted to close its "
            "lock-holding session"
        )

    def finish(self) -> None:
        """Discard the read-only probe savepoint without ending the lock txn."""

        self._rollback_probe_savepoint()

    def _rollback_probe_savepoint(self) -> None:
        savepoint = self._savepoint
        if savepoint is not None and savepoint.is_active:
            savepoint.rollback()


def _assert_system_kb_release_mutation_lock_held(db: Session) -> None:
    """Fail if the exact transaction advisory lock is no longer held."""

    if db.get_bind().dialect.name != "postgresql":
        return
    unsigned_key = SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY & ((1 << 64) - 1)
    class_id = unsigned_key >> 32
    object_id = unsigned_key & ((1 << 32) - 1)
    held = db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_locks
                WHERE locktype = 'advisory'
                  AND pid = pg_backend_pid()
                  AND granted
                  AND objsubid = 1
                  AND classid::bigint = :class_id
                  AND objid::bigint = :object_id
            )
            """
        ),
        {"class_id": class_id, "object_id": object_id},
    ).scalar()
    if held is not True:
        raise RuntimeError(
            "system KB release mutation transaction lock was lost during probe"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        required=True,
        choices=("guard", "staged", "enabled"),
    )
    parser.add_argument(
        "--review-manifest",
        default="data/system_kb_v2_seed/review_manifest.json",
    )
    args = parser.parse_args()

    expected_enabled = args.phase == "enabled"
    if bool(settings.health_evidence_runtime_enabled) != expected_enabled:
        raise RuntimeError(
            "health evidence runtime flag does not match release phase"
        )

    review_manifest_path = Path(args.review_manifest)
    manifest = _load_manifest(review_manifest_path)
    allow_fully_revoked = args.phase != "enabled"
    policy_report = verify_runtime_only_policy(
        manifest,
        allow_fully_revoked=allow_fully_revoked,
    )

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        acquire_system_kb_release_mutation_lock(db)
        _assert_system_kb_release_mutation_lock_held(db)
        probe_db = _TransactionPreservingProbeSession(db)
        database_report = verify_runtime_only_database(
            probe_db,
            manifest=manifest,
            require_present=args.phase != "guard",
            allow_fully_revoked=allow_fully_revoked,
        )
        _assert_system_kb_release_mutation_lock_held(db)
        enabled_report = (
            verify_enabled_runtime(
                probe_db,
                manifest=manifest,
                artifact_dir=review_manifest_path.resolve().parent,
            )
            if expected_enabled
            else {
                "runtime_eval_cases": 0,
                "runtime_eval_failures": 0,
            }
        )
        probe_db.finish()
        _assert_system_kb_release_mutation_lock_held(db)
    finally:
        try:
            db.rollback()
        finally:
            db.close()

    print(
        "RUNTIME_ONLY_KB_CONTRACT_OK "
        f"phase={args.phase} "
        f"packs={policy_report['runtime_packs']} "
        f"targets={database_report['target_documents']} "
        f"matched={database_report['matched_documents']} "
        f"generic={database_report['generic_eligible_documents']} "
        f"runtime={database_report['runtime_eligible_claims']} "
        f"desktop_held={database_report['desktop_held_documents']} "
        f"genetic_held={database_report['genetic_held_claims']} "
        f"eval_cases={enabled_report['runtime_eval_cases']} "
        f"eval_failures={enabled_report['runtime_eval_failures']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
