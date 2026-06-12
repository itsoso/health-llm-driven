"""系统自我监控:数据完整性检查。钉:量纲/层断连/空目标命中;正常数据不误报。"""
from datetime import date

from sqlalchemy import text

from app.services.data_integrity import range_issue, check_user_integrity


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


def test_healthy_user_no_issues(client, db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    # 正常 HRV(ms)+ 归一层与化验一致(都空)→ 无 issue
    db.execute(text(
        "INSERT INTO garmin_data (user_id, record_date, hrv, spo2_avg) VALUES (:u, :d, 52, 97)"
    ), {"u": user.id, "d": date.today()})
    db.commit()
    assert check_user_integrity(db, user.id) == []


def test_integrity_endpoint(client, db):
    from tests.conftest import create_authenticated_user
    user, token = create_authenticated_user(db)
    r = client.get("/api/v1/data-health/integrity",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "healthy" in body and "issues" in body
    assert client.get("/api/v1/data-health/integrity").status_code in (401, 403)
