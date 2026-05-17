"""System KB lifecycle tasks.

Runs global LLM Wiki V2 maintenance separately from user memory lifecycle:
lint current serving KB, decay stale claim confidence, and draft crystallized
claim candidates from repeated specialist audit observations. Crystallized
claims are never imported automatically; they remain review candidates.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.system_knowledge import KBAudit
from app.services.system_knowledge_crystallize import draft_crystallized_claim_candidates
from app.services.system_knowledge_service import apply_confidence_decay, lint_knowledge_base

logger = logging.getLogger(__name__)


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
