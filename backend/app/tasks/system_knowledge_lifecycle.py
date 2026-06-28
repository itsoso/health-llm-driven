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
from app.services.system_knowledge_crystallize import draft_crystallized_claim_candidates
from app.services.system_knowledge_ingest import validate_artifact_review_gate, write_draft_artifacts
from app.services.system_knowledge_service import apply_confidence_decay, lint_knowledge_base

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


def run_system_kb_lifecycle_once(
    db: Session,
    *,
    now: datetime | None = None,
    crystallize_min_count: int = 100,
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
    report = {
        "lint": lint,
        "decay": decay,
        "crystallize": {
            "draft_candidates": len(crystallize["draft_claims"]),
            "min_count": crystallize["min_count"],
            "generated_at": crystallize["generated_at"],
        },
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


@celery_app.task(time_limit=600, name="app.tasks.system_knowledge_lifecycle.run_system_kb_lifecycle")
def run_system_kb_lifecycle() -> dict[str, Any]:
    logger.info("[system_kb_lifecycle] start")
    with SessionLocal() as db:
        result = run_system_kb_lifecycle_once(db, actor="celery:system_kb_lifecycle")
    logger.info("[system_kb_lifecycle] done: %s", result.get("crystallize"))
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
