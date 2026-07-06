"""System KB lifecycle tasks.

Runs global LLM Wiki V2 maintenance separately from user memory lifecycle:
lint current serving KB, decay stale claim confidence, and draft crystallized
claim candidates from repeated specialist audit observations. Crystallized
claims are never imported automatically; they remain review candidates.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models.system_knowledge import KBAudit
from app.services.dedao_kbase_export_importer import (
    compile_dedao_kbase_export_payload_artifacts,
    fetch_dedao_kbase_export_payload,
)
from app.services.dedao_kbase_evidence_pull import dry_run_dedao_kbase_evidence_pull
from app.services.system_knowledge_crystallize import draft_crystallized_claim_candidates
from app.services.system_knowledge_eval import run_system_kb_eval_cases
from app.services.system_knowledge_ingest import validate_artifact_review_gate, write_draft_artifacts
from app.services.system_knowledge_service import (
    apply_confidence_decay,
    lint_knowledge_base,
    run_system_kb_reindex_report,
)

logger = logging.getLogger(__name__)


def _default_system_kb_artifact_dir() -> Path:
    if settings.system_kb_artifact_dir:
        return Path(settings.system_kb_artifact_dir).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "system_kb_v2_seed"


def sync_dedao_kbase_export_draft_once(
    db: Session,
    *,
    export_url: str | None,
    auth_token: str | None,
    artifact_dir: str | Path,
    source_root: str | Path,
    actor: str = "system",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch the online dedao-kbase export and write draft artifacts only."""
    export_url = (export_url or "").strip()
    if not export_url:
        return {
            "status": "skipped",
            "reason": "missing_export_url",
            "artifact_dir": str(artifact_dir),
        }

    current_time = now or datetime.now(UTC)
    payload = fetch_dedao_kbase_export_payload(export_url, auth_token=auth_token)
    result = compile_dedao_kbase_export_payload_artifacts(
        source_root=source_root,
        base_artifact_dir=artifact_dir,
        payload=payload,
        export_ref=export_url,
        now=current_time,
    )
    draft_manifest = write_draft_artifacts(
        result,
        artifact_dir,
        extractor=f"dedao-kbase-export:{export_url}",
        created_at=current_time,
        note="online dedao-kbase export synced as draft; requires review before serving.",
    )
    gate = validate_artifact_review_gate(artifact_dir)
    source = result.source_stats[0] if result.source_stats else {}
    report = {
        "status": "draft_written",
        "export_url": export_url,
        "artifact_dir": str(artifact_dir),
        "source": source.get("source") or payload.get("source") or "dedao-kbase",
        "source_repo": source.get("source_repo"),
        "source_commit": source.get("source_commit"),
        "source_version": source.get("version") or payload.get("version"),
        "diff": result.diff,
        "draft_manifest": draft_manifest,
        "gate": gate,
    }
    db.add(
        KBAudit(
            doc_id=None,
            op="dedao_kbase_export_sync_draft",
            actor=actor,
            diff={
                "status": report["status"],
                "export_url": export_url,
                "artifact_dir": report["artifact_dir"],
                "source": report["source"],
                "source_repo": report["source_repo"],
                "source_commit": report["source_commit"],
                "source_version": report["source_version"],
                "diff": report["diff"],
                "gate": {
                    "serving_allowed": gate["serving_allowed"],
                    "blocking_reasons": gate["blocking_reasons"],
                },
            },
        )
    )
    db.commit()
    return report


def sync_dedao_kbase_evidence_pull_dry_run_once(
    db: Session,
    *,
    manifest_url: str | None,
    auth_token: str | None,
    actor: str = "system",
) -> dict[str, Any]:
    """Fetch a dedao-kbase evidence pull manifest and persist a redacted dry-run audit."""
    manifest_url = (manifest_url or "").strip()
    if not manifest_url:
        return {
            "status": "skipped",
            "reason": "missing_manifest_url",
            "would_write": False,
        }

    report = dry_run_dedao_kbase_evidence_pull(
        manifest_url=manifest_url,
        auth_token=auth_token,
    )
    candidate_evidence_ids = [
        str(candidate.get("evidence_id"))
        for candidate in report.get("candidates", [])
        if candidate.get("evidence_id")
    ]
    audit_diff = {
        "status": report["status"],
        "manifest_url": manifest_url,
        "consumer_contract": report["consumer_contract"],
        "project_id": report["project_id"],
        "target_system": report["target_system"],
        "pack_id": report["pack_id"],
        "source_fingerprint": report["source_fingerprint"],
        "manifest_record_count": report.get("manifest_record_count"),
        "total_records": report["total_records"],
        "accepted_candidates": report["accepted_candidates"],
        "review_required_records": report["review_required_records"],
        "blocked_records": report["blocked_records"],
        "rejected_reasons": report.get("rejected_reasons") or {},
        "gate_checks": report.get("gate_checks") or [],
        "candidate_evidence_ids": candidate_evidence_ids,
        "would_write": False,
    }
    db.add(
        KBAudit(
            doc_id=None,
            op="dedao_kbase_evidence_pull_dry_run",
            actor=actor,
            diff=audit_diff,
        )
    )
    db.commit()
    return {
        **report,
        "manifest_url": manifest_url,
        "candidate_evidence_ids": candidate_evidence_ids,
    }


def run_system_kb_lifecycle_once(
    db: Session,
    *,
    now: datetime | None = None,
    crystallize_min_count: int = 100,
    eval_limit: int = 10_000,
    actor: str = "system",
) -> dict[str, Any]:
    current_time = now or datetime.now(UTC)
    lint = lint_knowledge_base(db)
    decay = apply_confidence_decay(db, now=current_time, actor=actor)
    crystallize = draft_crystallized_claim_candidates(
        db,
        min_count=crystallize_min_count,
        now=current_time,
    )
    eval_report = run_system_kb_eval_cases(db, limit=eval_limit)
    report = {
        "lint": lint,
        "decay": decay,
        "crystallize": {
            "draft_candidates": len(crystallize["draft_claims"]),
            "min_count": crystallize["min_count"],
            "generated_at": crystallize["generated_at"],
        },
        "eval": eval_report,
    }
    db.add(
        KBAudit(
            doc_id=None,
            op="lifecycle_report",
            actor=actor,
            diff=report,
        )
    )
    db.commit()
    return report


def run_system_kb_reindex_once(db: Session, *, actor: str = "system") -> dict[str, Any]:
    """Rebuild serving search indexes and persist the pgvector health report."""

    return run_system_kb_reindex_report(db, actor=actor)


@celery_app.task(time_limit=600, name="app.tasks.system_knowledge_lifecycle.run_system_kb_lifecycle")
def run_system_kb_lifecycle() -> dict[str, Any]:
    logger.info("[system_kb_lifecycle] start")
    with SessionLocal() as db:
        result = run_system_kb_lifecycle_once(db, actor="celery:system_kb_lifecycle")
    logger.info("[system_kb_lifecycle] done: %s", result.get("crystallize"))
    return result


@celery_app.task(time_limit=900, name="app.tasks.system_knowledge_lifecycle.run_system_kb_reindex")
def run_system_kb_reindex() -> dict[str, Any]:
    logger.info("[system_kb_reindex] start")
    with SessionLocal() as db:
        result = run_system_kb_reindex_once(db, actor="celery:system_kb_reindex")
    logger.info("[system_kb_reindex] done: %s", result.get("reindex"))
    return result


@celery_app.task(time_limit=600, name="app.tasks.system_knowledge_lifecycle.sync_dedao_kbase_export_draft")
def sync_dedao_kbase_export_draft() -> dict[str, Any]:
    """Scheduled online dedao-kbase sync.

    The task only writes draft artifacts. Serving import still requires human
    review plus the normal release gate.
    """
    logger.info("[dedao_kbase_export_sync] start")
    artifact_dir = _default_system_kb_artifact_dir()
    with SessionLocal() as db:
        result = sync_dedao_kbase_export_draft_once(
            db,
            export_url=settings.dedao_kbase_export_url,
            auth_token=settings.dedao_kbase_auth_token,
            artifact_dir=artifact_dir,
            source_root=settings.dedao_kbase_source_root,
            actor="celery:dedao_kbase_export_sync",
        )
    logger.info("[dedao_kbase_export_sync] done: %s", result.get("status"))
    return result


@celery_app.task(time_limit=600, name="app.tasks.system_knowledge_lifecycle.sync_dedao_kbase_evidence_pull_dry_run")
def sync_dedao_kbase_evidence_pull_dry_run() -> dict[str, Any]:
    """Scheduled dedao-kbase evidence pull preflight.

    This task writes only a redacted dry-run audit. It never imports serving KB
    rows or draft artifacts.
    """
    logger.info("[dedao_kbase_evidence_pull_dry_run] start")
    with SessionLocal() as db:
        result = sync_dedao_kbase_evidence_pull_dry_run_once(
            db,
            manifest_url=settings.dedao_kbase_evidence_manifest_url,
            auth_token=settings.dedao_kbase_auth_token,
            actor="celery:dedao_kbase_evidence_pull_dry_run",
        )
    logger.info("[dedao_kbase_evidence_pull_dry_run] done: %s", result.get("status"))
    return result
