"""Safety and consistency gate for user-visible health advice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.advice_ledger import AdviceLedger


REQUIRED_FIELDS = (
    "domain",
    "title",
    "body",
    "evidence_tier",
    "confidence",
    "claim_boundary",
)

REDUCE_INTENSITY_TARGETS = {
    "reduce_intensity",
    "rest",
    "recovery",
    "avoid_high_intensity",
    "pause_running",
}
INCREASE_ACTIVITY_TARGETS = {
    "increase_activity",
    "increase_intensity",
    "150min_weekly",
    "run_more",
}


class AdviceGuardError(ValueError):
    """Raised when an advice candidate violates the science/safety contract."""


@dataclass(frozen=True)
class AdviceCandidate:
    user_id: int
    source: str
    source_id: str
    domain: str
    title: str
    body: str
    metric_key: str | None = None
    target_value: str | None = None
    evidence_tier: str | None = None
    confidence: str | None = None
    claim_boundary: str | None = None
    evidence_refs: list[str] | None = None
    evidence_source_types: list[str] | None = None
    verification_metric: str | None = None
    verification_window_days: int | None = None
    risk_level: str | None = None
    contraindications: list[dict] | None = None
    valid_for_date: date | None = None
    created_at: datetime | None = None

    @property
    def advice_key(self) -> str:
        return normalize_advice_key(
            user_id=self.user_id,
            domain=self.domain,
            metric_key=self.metric_key,
            target_value=self.target_value,
            valid_for_date=self.valid_for_date,
        )


@dataclass(frozen=True)
class AdviceDecision:
    allowed: bool
    reason: str
    advice_key: str
    conflicts_with_source_id: str | None = None


def normalize_advice_key(
    *,
    user_id: int,
    domain: str,
    metric_key: str | None,
    target_value: str | None,
    valid_for_date: date | None,
) -> str:
    raw = "|".join(
        [
            str(user_id),
            (domain or "").strip().lower(),
            (metric_key or "").strip().lower(),
            (target_value or "").strip().lower(),
            valid_for_date.isoformat() if valid_for_date else "",
        ]
    )
    return sha256(raw.encode("utf-8")).hexdigest()[:32]


def _target_bucket(candidate: AdviceCandidate) -> str | None:
    target = (candidate.target_value or "").strip().lower()
    title = candidate.title.lower()
    if target in REDUCE_INTENSITY_TARGETS or "暂停跑" in title or "降低跑步" in title:
        return "reduce_intensity"
    if target in INCREASE_ACTIVITY_TARGETS or "提高运动" in title or "运动不足" in title:
        return "increase_activity"
    return None


class AdviceGuard:
    def __init__(self, existing: Iterable[AdviceCandidate]):
        self.existing = list(existing)

    def evaluate(self, candidate: AdviceCandidate) -> AdviceDecision:
        self._validate_contract(candidate)

        health_verification = self._verify_health_contract(candidate)
        if not health_verification.allowed:
            return AdviceDecision(
                allowed=False,
                reason=health_verification.reason,
                advice_key=candidate.advice_key,
            )

        for item in self.existing:
            if item.advice_key == candidate.advice_key:
                return AdviceDecision(
                    allowed=False,
                    reason="duplicate",
                    advice_key=candidate.advice_key,
                    conflicts_with_source_id=item.source_id,
                )

        conflict = self._find_conflict(candidate)
        if conflict is not None:
            return AdviceDecision(
                allowed=False,
                reason="conflict",
                advice_key=candidate.advice_key,
                conflicts_with_source_id=conflict.source_id,
            )

        return AdviceDecision(allowed=True, reason="allowed", advice_key=candidate.advice_key)

    def _validate_contract(self, candidate: AdviceCandidate) -> None:
        missing = [
            field
            for field in REQUIRED_FIELDS
            if not str(getattr(candidate, field, "") or "").strip()
        ]
        if missing:
            raise AdviceGuardError(f"Advice candidate missing required fields: {', '.join(missing)}")

    def _verify_health_contract(self, candidate: AdviceCandidate):
        from app.services.health_advice_verifier import verify_advice

        return verify_advice(
            candidate,
            evidence_resolution={"evidence_refs": candidate.evidence_refs or []},
            personal_matrix={},
            contraindications=candidate.contraindications or [],
        )

    def _find_conflict(self, candidate: AdviceCandidate) -> AdviceCandidate | None:
        if candidate.domain != "movement":
            return None

        bucket = _target_bucket(candidate)
        if bucket is None:
            return None

        for item in self.existing:
            if item.domain != candidate.domain:
                continue
            existing_bucket = _target_bucket(item)
            if {bucket, existing_bucket} == {"reduce_intensity", "increase_activity"}:
                return item
        return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_candidate(row: AdviceLedger) -> AdviceCandidate:
    return AdviceCandidate(
        user_id=row.user_id,
        source=row.source,
        source_id=row.source_id,
        domain=row.domain,
        title=row.title,
        body=row.body,
        metric_key=row.metric_key,
        target_value=row.target_value,
        evidence_tier=row.evidence_tier,
        confidence=row.confidence,
        claim_boundary=row.claim_boundary,
        valid_for_date=row.valid_for_date,
        created_at=row.created_at,
    )


def load_active_advice_candidates(
    db: Session,
    user_id: int,
    *,
    domain: str | None = None,
) -> list[AdviceCandidate]:
    query = db.query(AdviceLedger).filter(
        AdviceLedger.user_id == user_id,
        AdviceLedger.status == "active",
        AdviceLedger.decision == "allowed",
    )
    if domain:
        query = query.filter(AdviceLedger.domain == domain)
    rows = query.order_by(AdviceLedger.created_at.desc()).limit(50).all()
    return [_row_to_candidate(row) for row in rows]


def guard_and_record_advice(db: Session, candidate: AdviceCandidate) -> AdviceDecision:
    """Evaluate advice against active user advice and persist the decision."""

    existing_same_source = (
        db.query(AdviceLedger)
        .filter(
            AdviceLedger.user_id == candidate.user_id,
            AdviceLedger.advice_key == candidate.advice_key,
            AdviceLedger.source == candidate.source,
            AdviceLedger.source_id == candidate.source_id,
        )
        .first()
    )
    if existing_same_source:
        return AdviceDecision(
            allowed=existing_same_source.decision == "allowed",
            reason=f"existing_{existing_same_source.reason}",
            advice_key=candidate.advice_key,
        )

    existing = load_active_advice_candidates(db, candidate.user_id, domain=candidate.domain)
    decision = AdviceGuard(existing).evaluate(candidate)
    conflict_row_id = None
    if decision.conflicts_with_source_id:
        conflict = (
            db.query(AdviceLedger)
            .filter(
                AdviceLedger.user_id == candidate.user_id,
                AdviceLedger.source_id == decision.conflicts_with_source_id,
            )
            .order_by(AdviceLedger.id.desc())
            .first()
        )
        conflict_row_id = conflict.id if conflict else None

    row = AdviceLedger(
        user_id=candidate.user_id,
        advice_key=decision.advice_key,
        source=candidate.source,
        source_id=candidate.source_id,
        domain=candidate.domain,
        title=candidate.title,
        body=candidate.body,
        metric_key=candidate.metric_key,
        target_value=candidate.target_value,
        evidence_tier=candidate.evidence_tier or "",
        confidence=candidate.confidence or "",
        claim_boundary=candidate.claim_boundary or "",
        decision="allowed" if decision.allowed else "blocked",
        reason=decision.reason,
        conflicts_with_id=conflict_row_id,
        valid_for_date=candidate.valid_for_date,
        status="active" if decision.allowed else "blocked",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return AdviceDecision(
            allowed=False,
            reason="duplicate",
            advice_key=decision.advice_key,
            conflicts_with_source_id=decision.conflicts_with_source_id,
        )

    return decision
