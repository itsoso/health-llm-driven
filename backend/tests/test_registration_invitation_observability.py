"""PII-minimized rollout observability for invited registration."""

import json
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.models.registration_invitation import RegistrationAuthAttemptAudit
from app.services.observability_service import (
    collect_dashboard,
    registration_invitation_stats,
)
from app.services.registration_invitation import create_registration_invitation


def test_registration_observability_contains_only_bounded_counts_and_enums(
    db, monkeypatch
):
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "registration-invitation-observability-32-byte-key",
    )
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", True)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    sent = create_registration_invitation(db, "13800138211").invitation
    failed = create_registration_invitation(db, "13800138212").invitation
    sent.status = "sent"
    sent.send_attempt_count = 1
    failed.status = "send_failed"
    failed.send_attempt_count = 2
    failed.last_send_error_code = "provider_timeout"
    db.add_all(
        [
            RegistrationAuthAttemptAudit(
                outcome="success",
                invitation_id=sent.id,
                grant_id=71001,
                user_id=72001,
                phone_masked="+86 138****8211",
                source_hmac="source-secret-marker",
            ),
            RegistrationAuthAttemptAudit(
                outcome="rejected",
                error_code="INVITATION_PHONE_MISMATCH",
                invitation_id=failed.id,
                grant_id=71002,
                user_id=72002,
                phone_masked="+86 138****8212",
                source_hmac="source-secret-marker-2",
            ),
            RegistrationAuthAttemptAudit(
                outcome="rejected",
                error_code="unbounded-secret-error-13800138212",
                phone_masked="+86 138****8212",
            ),
        ]
    )
    db.commit()

    stats = registration_invitation_stats(
        db,
        datetime.now(UTC) - timedelta(days=1),
    )

    assert stats == {
        "mode": "enforced",
        "invitations_total": 2,
        "invitations_by_status": {"send_failed": 1, "sent": 1},
        "send_attempts_total": 3,
        "send_failures_by_error": {"provider_timeout": 1},
        "registration_attempts_total": 3,
        "registration_attempts_by_outcome": {"rejected": 2, "success": 1},
        "registration_rejections_by_error": {
            "INVITATION_PHONE_MISMATCH": 1,
            "unknown": 1,
        },
    }
    serialized = json.dumps(stats, ensure_ascii=False)
    for forbidden in (
        "13800138211",
        "13800138212",
        "138****8211",
        "138****8212",
        "source-secret-marker",
        "71001",
        "72001",
        "unbounded-secret-error",
        "phone",
        "ticket",
        "code",
        "user_id",
        "health",
    ):
        assert forbidden not in serialized


def test_dashboard_exposes_only_the_safe_registration_aggregate(db, monkeypatch):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", False)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)

    report = collect_dashboard(db, days=1, user_id=None)

    assert report["registration_invitation"] == {
        "mode": "rollback_closed",
        "invitations_total": 0,
        "invitations_by_status": {},
        "send_attempts_total": 0,
        "send_failures_by_error": {},
        "registration_attempts_total": 0,
        "registration_attempts_by_outcome": {},
        "registration_rejections_by_error": {},
    }


def test_user_filtered_dashboard_omits_global_registration_aggregate(db):
    report = collect_dashboard(db, days=1, user_id=42)

    assert "registration_invitation" not in report
