"""系统自我监控:数据完整性检查。钉:量纲/层断连/空目标命中;正常数据不误报。"""
from datetime import date, datetime, timezone

from sqlalchemy import text

import pytest

from app.services.data_integrity import (
    DataIntegrityScanError,
    check_user_integrity,
    range_issue,
)


# ── 纯 range 函数 ──
def test_range_issue_hrv_seconds_bug():
    assert range_issue("hrv_ms", 0.0576) is not None   # 按秒存的 bug
    assert range_issue("hrv_ms", 52) is None            # 正常 ms
    assert range_issue("spo2_pct", 0.97) is not None    # 按小数存
    assert range_issue("spo2_pct", 97) is None
    assert range_issue("resting_hr", 200) is not None
    assert range_issue("hrv_ms", None) is None
    assert range_issue("unknown_metric", 999) is None


# ── 端到端检查 ──
def _codes(db, uid):
    return {i["code"] for i in check_user_integrity(db, uid)}


def test_hrv_unit_suspect(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    db.execute(text(
        "INSERT INTO garmin_data (user_id, record_date, hrv) VALUES (:u, :d, 0.0576)"
    ), {"u": user.id, "d": date.today()})
    db.commit()
    assert "hrv_unit_suspect" in _codes(db, user.id)


def test_biomarker_layer_disconnected(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    # 有化验指标,但无归一观测 → 断连(这次 session 的真 bug)
    db.execute(text(
        "INSERT INTO medical_indicators (user_id, name, value, record_date) "
        "VALUES (:u, '谷氨酰转肽酶', 78, :d)"
    ), {"u": user.id, "d": date.today()})
    db.commit()
    assert "biomarker_layer_disconnected" in _codes(db, user.id)


def test_cycle_empty_targets(client, db):
    from tests.conftest import create_authenticated_user
    from app.models.intervention_cycle import InterventionCycle
    user, _ = create_authenticated_user(db)
    c = InterventionCycle(user_id=user.id, cycle_type="metabolic_90d", status="active",
                          start_date=date(2026, 6, 1), planned_end_date=date(2026, 9, 1),
                          target_metrics=[])
    db.add(c)
    db.commit()
    assert "cycle_empty_targets" in _codes(db, user.id)


def test_cycle_with_targets_not_flagged(client, db):
    """回归:有 1 个目标的周期不应被误判为空(list 长度 1,曾被 <=2 误报)。"""
    from tests.conftest import create_authenticated_user
    from app.models.intervention_cycle import InterventionCycle
    user, _ = create_authenticated_user(db)
    c = InterventionCycle(user_id=user.id, cycle_type="metabolic_90d", status="active",
                          start_date=date(2026, 6, 1), planned_end_date=date(2026, 9, 1),
                          target_metrics=[{"code": "glucose_hba1c", "target": 5.7, "direction": "down"}])
    db.add(c)
    db.commit()
    assert "cycle_empty_targets" not in _codes(db, user.id)


def test_healthy_user_no_issues(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    # 正常 HRV(ms)+ 归一层与化验一致(都空)→ 无 issue
    db.execute(text(
        "INSERT INTO garmin_data (user_id, record_date, hrv, spo2_avg) VALUES (:u, :d, 52, 97)"
    ), {"u": user.id, "d": date.today()})
    db.commit()
    assert check_user_integrity(db, user.id) == []


def test_diet_photo_asset_without_exactly_one_parent_is_detected(client, db):
    from tests.conftest import create_authenticated_user
    from app.models.daily_health import DietPhotoAsset

    user, _ = create_authenticated_user(db)
    db.add(DietPhotoAsset(
        id="orphan-photo",
        user_id=user.id,
        storage_key=f"/uploads/diet/{user.id}/orphan.jpg",
        content_sha256="a" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=901,
        ordinal=0,
        captured_at=datetime.now(timezone.utc),
        captured_timezone="Asia/Shanghai",
        classification="food",
        recognition_confidence=0.9,
        intent_decision="auto_record",
        recognition_snapshot={},
        lifecycle="pending",
    ))
    db.commit()

    assert "diet_photo_asset_parent_invalid" in _codes(db, user.id)


def test_contextual_diet_record_without_photo_asset_is_detected(client, db):
    from tests.conftest import create_authenticated_user
    from app.models.daily_health import DietRecord

    user, _ = create_authenticated_user(db)
    db.add(DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="breakfast",
        food_name="煎饼",
        food_items="煎饼",
        source="chat_photo",
        client_action_id="contextual-meal-photo:902",
    ))
    db.commit()

    assert "diet_photo_record_asset_missing" in _codes(db, user.id)


def test_diet_photo_parent_owner_mismatch_is_detected(client, db):
    from tests.conftest import create_authenticated_user
    from app.models.daily_health import DietPhotoAsset, DietRecord

    record_owner, _ = create_authenticated_user(db)
    asset_owner, _ = create_authenticated_user(db)
    record = DietRecord(
        user_id=record_owner.id,
        record_date=date.today(),
        meal_type="breakfast",
        food_name="煎饼",
        food_items="煎饼",
        source="chat_photo",
    )
    db.add(record)
    db.flush()
    db.add(DietPhotoAsset(
        id="cross-owner-photo",
        user_id=asset_owner.id,
        diet_record_id=record.id,
        storage_key=f"/api/v1/upload/files/diet/{asset_owner.id}/cross-owner.jpg",
        content_sha256="b" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=903,
        ordinal=0,
        captured_at=datetime.now(timezone.utc),
        captured_timezone="Asia/Shanghai",
        classification="food",
        recognition_confidence=0.9,
        intent_decision="auto_record",
        recognition_snapshot={},
        lifecycle="attached",
    ))
    db.commit()

    assert "diet_photo_parent_owner_mismatch" in _codes(db, asset_owner.id)


def test_diet_photo_draft_source_mismatch_is_detected(client, db):
    from datetime import timedelta

    from tests.conftest import create_authenticated_user
    from app.models.daily_health import DietPhotoAsset, DietPhotoDraft

    user, _ = create_authenticated_user(db)
    draft = DietPhotoDraft(
        token="integrity-source-mismatch",
        user_id=user.id,
        source_message_id=904,
        image_url=f"/api/v1/upload/files/diet/{user.id}/draft.jpg",
        image_type="jpeg",
        recognition_result={"food_items": "煎饼"},
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    asset = DietPhotoAsset(
        id="source-mismatch-photo",
        user_id=user.id,
        photo_draft_token=draft.token,
        storage_key=f"/api/v1/upload/files/diet/{user.id}/draft.jpg",
        content_sha256="c" * 64,
        media_type="image/jpeg",
        origin="chat",
        origin_message_id=905,
        ordinal=0,
        captured_at=datetime.now(timezone.utc),
        captured_timezone="Asia/Shanghai",
        classification="food",
        recognition_confidence=0.9,
        intent_decision="confirm",
        recognition_snapshot={},
        lifecycle="pending",
    )
    db.add_all([draft, asset])
    db.commit()

    assert "diet_photo_draft_source_mismatch" in _codes(db, user.id)


def test_diet_photo_integrity_query_failure_is_fail_loud(
    client, db, monkeypatch
):
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    real_execute = db.execute

    def fail_diet_photo_scan(statement, *args, **kwargs):
        if "FROM diet_photo_assets" in str(statement):
            raise RuntimeError("simulated diet photo ledger outage")
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", fail_diet_photo_scan)

    with pytest.raises(
        DataIntegrityScanError,
        match="diet_photo_integrity_scan_failed",
    ):
        check_user_integrity(db, user.id)


def test_integrity_endpoint(client, db):
    from tests.conftest import create_authenticated_user
    user, token = create_authenticated_user(db)
    r = client.get("/api/v1/data-health/integrity",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "healthy" in body and "issues" in body
    assert client.get("/api/v1/data-health/integrity").status_code in (401, 403)
