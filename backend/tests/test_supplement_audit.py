"""补剂审计 service + API 冒烟测试"""
from datetime import date

import pytest

from app.models.user import User
from app.schemas.supplement_audit import (
    SupplementAuditCreate,
    SupplementAuditItemCreate,
    SupplementAuditItemUpdate,
)
from app.services.supplement_audit_service import supplement_audit_service


@pytest.fixture
def test_user(db):
    u = User(username="auditor_test", email="auditor_test@example.com", hashed_password="x", name="Auditor Test")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_payload(title="Test Audit", items=None):
    return SupplementAuditCreate(
        title=title,
        triggered_by="manual",
        data_period_start=date(2024, 1, 1),
        data_period_end=date(2026, 4, 11),
        rationale_markdown="# test\ncontent",
        summary="summary",
        items=items or [],
    )


def test_create_and_list(db, test_user):
    payload = _mk_payload(items=[
        SupplementAuditItemCreate(
            action_type="add", priority=1, title="Add Taurine",
            rationale_markdown="evidence",
            evidence_refs=[{"type": "gene", "id": "ADD1"}],
            warnings=[],
        ),
        SupplementAuditItemCreate(
            action_type="monitor", priority=2, title="PSG",
            rationale_markdown="rationale",
            target_metric="PSG",
        ),
    ])
    audit = supplement_audit_service.create_audit(db, test_user.id, payload)
    assert audit.version == 1
    assert audit.status == "active"
    assert len(audit.items) == 2

    lst = supplement_audit_service.list_audits(db, test_user.id)
    assert len(lst) == 1
    assert lst[0]["items_count"] == 2
    assert lst[0]["pending_count"] == 2


def test_create_v2_supersedes_v1(db, test_user):
    v1 = supplement_audit_service.create_audit(db, test_user.id, _mk_payload(title="v1"))
    v2 = supplement_audit_service.create_audit(db, test_user.id, _mk_payload(title="v2"))
    assert v1.version == 1 and v2.version == 2
    db.refresh(v1)
    assert v1.status == "superseded"
    assert v2.status == "active"

    active = supplement_audit_service.get_active_audit(db, test_user.id)
    assert active.id == v2.id


def test_accept_reject_complete_item(db, test_user):
    payload = _mk_payload(items=[
        SupplementAuditItemCreate(
            action_type="add", priority=1, title="Add X",
            rationale_markdown="x",
        ),
    ])
    audit = supplement_audit_service.create_audit(db, test_user.id, payload)
    item_id = audit.items[0].id

    # accept
    updated = supplement_audit_service.update_item(
        db, test_user.id, item_id,
        SupplementAuditItemUpdate(status="accepted", user_note="lgtm"),
    )
    assert updated.status == "accepted"
    assert updated.accepted_at is not None
    assert updated.user_note == "lgtm"

    # complete
    updated = supplement_audit_service.update_item(
        db, test_user.id, item_id,
        SupplementAuditItemUpdate(status="completed"),
    )
    assert updated.status == "completed"
    assert updated.completed_at is not None

    # reject
    updated = supplement_audit_service.update_item(
        db, test_user.id, item_id,
        SupplementAuditItemUpdate(status="rejected", rejected_reason="too expensive"),
    )
    assert updated.status == "rejected"
    assert updated.rejected_reason == "too expensive"


def test_user_isolation(db):
    u1 = User(username="u1", email="u1@example.com", hashed_password="x", name="U1")
    u2 = User(username="u2", email="u2@example.com", hashed_password="x", name="U2")
    db.add_all([u1, u2])
    db.commit()
    db.refresh(u1)
    db.refresh(u2)

    supplement_audit_service.create_audit(db, u1.id, _mk_payload(title="u1 audit"))
    supplement_audit_service.create_audit(db, u2.id, _mk_payload(title="u2 audit"))

    assert len(supplement_audit_service.list_audits(db, u1.id)) == 1
    assert len(supplement_audit_service.list_audits(db, u2.id)) == 1
    assert supplement_audit_service.list_audits(db, u1.id)[0]["title"] == "u1 audit"


def test_invalid_item_status(db, test_user):
    payload = _mk_payload(items=[
        SupplementAuditItemCreate(action_type="add", priority=1, title="X", rationale_markdown="."),
    ])
    audit = supplement_audit_service.create_audit(db, test_user.id, payload)
    item_id = audit.items[0].id

    with pytest.raises(Exception):
        supplement_audit_service.update_item(
            db, test_user.id, item_id,
            SupplementAuditItemUpdate(status="bogus"),
        )
