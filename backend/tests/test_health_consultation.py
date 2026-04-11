"""健康咨询 service 冒烟测试"""
from datetime import date, timedelta

import pytest

from app.models.user import User
from app.schemas.health_consultation import (
    ConsultationItemCreate,
    ConsultationItemUpdate,
    HealthConsultationCreate,
)
from app.services.health_consultation_service import health_consultation_service


@pytest.fixture
def test_user(db):
    u = User(username="consult_test", email="consult_test@example.com", hashed_password="x", name="Consult")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_payload(title="Test Consultation", items=None):
    return HealthConsultationCreate(
        title=title,
        topic="test topic",
        consultation_type="symptom_advisory",
        triggered_by="manual",
        chief_complaint="test complaint",
        rationale_markdown="# test",
        summary="summary",
        verification_scheduled_at=date.today() + timedelta(days=28),
        items=items or [],
    )


def test_create_with_all_item_types(db, test_user):
    items = [
        ConsultationItemCreate(
            item_type="hypothesis", item_code="H1", priority=1,
            title="假设 1: 机械创伤",
            content_markdown="tooth sharp edge",
            meta={"confidence": "high", "verify_method": "self_check"},
        ),
        ConsultationItemCreate(
            item_type="action", item_code="A1", priority=1,
            title="自检牙齿",
            meta={"action_category": "immediate", "frequency": "once"},
            due_date=date.today(),
        ),
        ConsultationItemCreate(
            item_type="prediction", item_code="P1", priority=2,
            title="深睡眠涨到 90min",
            meta={
                "metric_name": "deep_sleep_minutes",
                "baseline": 80,
                "target": ">=90",
                "data_source": "garmin_data.deep_sleep_duration",
                "check_after_days": 28,
            },
            due_date=date.today() + timedelta(days=28),
        ),
        ConsultationItemCreate(
            item_type="red_flag", item_code="R1", priority=1,
            title="溃疡>2周不愈",
            meta={"severity": "critical", "trigger_condition": "14天"},
        ),
    ]
    c = health_consultation_service.create(db, test_user.id, _mk_payload(items=items))
    assert c.version == 1
    assert c.status == "active"
    assert len(c.items) == 4
    # red_flag 应该默认 watching, 其他 pending
    by_type = {i.item_type: i for i in c.items}
    assert by_type["hypothesis"].status == "pending"
    assert by_type["action"].status == "pending"
    assert by_type["prediction"].status == "pending"
    assert by_type["red_flag"].status == "watching"


def test_list_with_stats(db, test_user):
    items = [
        ConsultationItemCreate(item_type="hypothesis", title="H1", meta={}),
        ConsultationItemCreate(item_type="hypothesis", title="H2", meta={}),
        ConsultationItemCreate(item_type="action", title="A1", meta={}),
        ConsultationItemCreate(item_type="prediction", title="P1", meta={}),
        ConsultationItemCreate(item_type="red_flag", title="R1", meta={}),
    ]
    health_consultation_service.create(db, test_user.id, _mk_payload(items=items))
    lst = health_consultation_service.list_consultations(db, test_user.id)
    assert len(lst) == 1
    assert lst[0]["total_items"] == 5
    assert lst[0]["hypothesis_count"] == 2
    assert lst[0]["action_count"] == 1
    assert lst[0]["prediction_count"] == 1
    assert lst[0]["red_flag_count"] == 1
    # 4 pending (hypothesis x2, action, prediction) + 1 watching (red_flag)
    assert lst[0]["pending_count"] == 4


def test_update_item_status_machine(db, test_user):
    items = [
        ConsultationItemCreate(item_type="hypothesis", item_code="H1", title="h", meta={}),
        ConsultationItemCreate(item_type="action", item_code="A1", title="a", meta={}),
        ConsultationItemCreate(item_type="prediction", item_code="P1", title="p", meta={}),
    ]
    c = health_consultation_service.create(db, test_user.id, _mk_payload(items=items))
    by_type = {i.item_type: i for i in c.items}

    # hypothesis: pending -> confirmed
    updated = health_consultation_service.update_item(
        db, test_user.id, by_type["hypothesis"].id,
        ConsultationItemUpdate(status="confirmed", outcome="摸到尖锐点"),
    )
    assert updated.status == "confirmed"
    assert updated.outcome == "摸到尖锐点"
    assert updated.verified_at is not None

    # action: pending -> completed
    updated = health_consultation_service.update_item(
        db, test_user.id, by_type["action"].id,
        ConsultationItemUpdate(status="completed"),
    )
    assert updated.status == "completed"
    assert updated.completed_at is not None

    # prediction: pending -> met + actual_value
    updated = health_consultation_service.update_item(
        db, test_user.id, by_type["prediction"].id,
        ConsultationItemUpdate(status="met", actual_value="93", outcome="深睡 93min"),
    )
    assert updated.status == "met"
    assert updated.actual_value == "93"


def test_invalid_status_for_type(db, test_user):
    items = [ConsultationItemCreate(item_type="hypothesis", item_code="H1", title="h", meta={})]
    c = health_consultation_service.create(db, test_user.id, _mk_payload(items=items))
    item_id = c.items[0].id

    # 给 hypothesis 用 action 的状态
    with pytest.raises(Exception):
        health_consultation_service.update_item(
            db, test_user.id, item_id,
            ConsultationItemUpdate(status="completed"),
        )


def test_meta_patch_merge(db, test_user):
    items = [ConsultationItemCreate(
        item_type="prediction", item_code="P1", title="p",
        meta={"metric_name": "deep_sleep", "baseline": 80},
    )]
    c = health_consultation_service.create(db, test_user.id, _mk_payload(items=items))
    item_id = c.items[0].id

    updated = health_consultation_service.update_item(
        db, test_user.id, item_id,
        ConsultationItemUpdate(meta_patch={"verified_at_value": 93, "note": "good"}),
    )
    assert updated.meta["metric_name"] == "deep_sleep"  # 保留
    assert updated.meta["baseline"] == 80  # 保留
    assert updated.meta["verified_at_value"] == 93  # 新增
    assert updated.meta["note"] == "good"  # 新增


def test_user_isolation(db):
    u1 = User(username="u1c", email="u1c@example.com", hashed_password="x", name="U1")
    u2 = User(username="u2c", email="u2c@example.com", hashed_password="x", name="U2")
    db.add_all([u1, u2])
    db.commit()
    db.refresh(u1)
    db.refresh(u2)

    health_consultation_service.create(db, u1.id, _mk_payload(title="u1's"))
    health_consultation_service.create(db, u2.id, _mk_payload(title="u2's"))

    assert len(health_consultation_service.list_consultations(db, u1.id)) == 1
    assert health_consultation_service.list_consultations(db, u1.id)[0]["title"] == "u1's"
    assert len(health_consultation_service.list_consultations(db, u2.id)) == 1


def test_suggest_status_helper():
    fn = health_consultation_service._suggest_status
    assert fn(93, ">=90", 80) == "met"
    assert fn(85, ">=90", 80) == "not_met"
    assert fn(25, "<30", None) == "met"
    assert fn(50, "<30", None) == "not_met"
    assert fn(None, ">=90", None) == "pending"
    assert fn(75, "qualitative", None) == "inconclusive"
