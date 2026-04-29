"""Open-Loop API 路由测试 — /open-loop/{history,feedback,summary}."""
from datetime import datetime, timedelta, timezone, date

import pytest


def _seed_history(db, user_id: int, **overrides):
    """建一条 OpenLoopHistory 给测试用."""
    from app.models.open_loop_history import OpenLoopHistory
    defaults = dict(
        user_id=user_id,
        kind="lab_overdue",
        signal_key="LDL",
        score=70,
        title="该复查 LDL 了",
        body="上次 LDL 210 天前 (4.1 mmol/L)",
        deeplink="health://medical-exams/upload",
        delivery_ok=1,
    )
    defaults.update(overrides)
    row = OpenLoopHistory(**defaults)
    db.add(row); db.commit(); db.refresh(row)
    return row


# ────── GET /open-loop/history ──────


def test_history_returns_only_own_rows(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    _seed_history(db, user.id, signal_key="LDL")
    _seed_history(db, user.id + 999, signal_key="HBA1C")  # 别人的, 不应返回

    r = client.get("/api/v1/open-loop/history", headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["signal_key"] == "LDL"


def test_history_respects_days_window(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    from app.models.open_loop_history import OpenLoopHistory

    row_old = _seed_history(db, user.id, signal_key="old")
    row_old.sent_at = datetime.now(timezone.utc) - timedelta(days=30)
    row_new = _seed_history(db, user.id, signal_key="new")
    db.commit()

    r = client.get("/api/v1/open-loop/history?days=7", headers=headers)
    assert r.status_code == 200
    keys = {it["signal_key"] for it in r.json()}
    assert keys == {"new"}


def test_history_requires_auth(client):
    r = client.get("/api/v1/open-loop/history")
    assert r.status_code in (401, 403)


# ────── POST /open-loop/{id}/feedback ──────


def test_feedback_done(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    row = _seed_history(db, user.id)

    r = client.post(f"/api/v1/open-loop/{row.id}/feedback", headers=headers,
                    json={"action": "done"})
    assert r.status_code == 200
    data = r.json()
    assert data["user_action"] == "done"
    assert data["snoozed_until"] is None


def test_feedback_snooze_7d_sets_window(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    row = _seed_history(db, user.id)

    r = client.post(f"/api/v1/open-loop/{row.id}/feedback", headers=headers,
                    json={"action": "snooze_7d"})
    assert r.status_code == 200
    snoozed = r.json()["snoozed_until"]
    assert snoozed is not None
    # SQLite 不保 tz, 兼容有/无 tz 返回
    dt_raw = datetime.fromisoformat(snoozed.replace("Z", "+00:00"))
    dt = dt_raw.replace(tzinfo=None) if dt_raw.tzinfo else dt_raw
    expected = (datetime.now(timezone.utc) + timedelta(days=7)).replace(tzinfo=None)
    assert abs((dt - expected).total_seconds()) < 60


def test_feedback_snooze_custom_days(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    row = _seed_history(db, user.id)

    r = client.post(f"/api/v1/open-loop/{row.id}/feedback", headers=headers,
                    json={"action": "snooze_7d", "snooze_days": 14})
    assert r.status_code == 200
    dt_raw = datetime.fromisoformat(r.json()["snoozed_until"].replace("Z", "+00:00"))
    dt = dt_raw.replace(tzinfo=None) if dt_raw.tzinfo else dt_raw
    expected = (datetime.now(timezone.utc) + timedelta(days=14)).replace(tzinfo=None)
    assert abs((dt - expected).total_seconds()) < 60


def test_feedback_not_interested_sets_30d(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    row = _seed_history(db, user.id)

    r = client.post(f"/api/v1/open-loop/{row.id}/feedback", headers=headers,
                    json={"action": "not_interested"})
    assert r.status_code == 200
    dt_raw = datetime.fromisoformat(r.json()["snoozed_until"].replace("Z", "+00:00"))
    dt = dt_raw.replace(tzinfo=None) if dt_raw.tzinfo else dt_raw
    expected = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None)
    assert abs((dt - expected).total_seconds()) < 60


def test_feedback_rejects_unknown_action(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    row = _seed_history(db, user.id)

    r = client.post(f"/api/v1/open-loop/{row.id}/feedback", headers=headers,
                    json={"action": "delete_everything"})
    assert r.status_code == 422


def test_feedback_404_on_missing(client, auth_user_and_headers):
    user, headers = auth_user_and_headers
    r = client.post("/api/v1/open-loop/999999/feedback", headers=headers,
                    json={"action": "done"})
    assert r.status_code == 404


def test_feedback_404_on_cross_user_access(client, auth_user_and_headers, db):
    """LLM 编造或旧设备的 history_id 属于别人 → 404, 防越权."""
    user, headers = auth_user_and_headers
    other_row = _seed_history(db, user.id + 9999)

    r = client.post(f"/api/v1/open-loop/{other_row.id}/feedback", headers=headers,
                    json={"action": "done"})
    assert r.status_code == 404


def test_feedback_snooze_days_out_of_range_rejected(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    row = _seed_history(db, user.id)

    r = client.post(f"/api/v1/open-loop/{row.id}/feedback", headers=headers,
                    json={"action": "snooze_7d", "snooze_days": 100})
    assert r.status_code == 422


# ────── GET /open-loop/summary ──────


def test_summary_empty_when_no_signals(client, auth_user_and_headers):
    user, headers = auth_user_and_headers
    r = client.get("/api/v1/open-loop/summary", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


def test_summary_surfaces_plan_deviation(client, auth_user_and_headers, db):
    """用户有 exercise 模板 5 天没打卡 → summary 应返回 plan_drift."""
    user, headers = auth_user_and_headers
    from app.models.checkin import CheckinTemplate

    tmpl = CheckinTemplate(
        user_id=user.id,
        name="跳绳",
        category="exercise",
        frequency="daily",
        is_active=True,
        is_archived=False,
        last_checkin_date=date.today() - timedelta(days=5),
        icon="🏃",
    )
    db.add(tmpl); db.commit()

    r = client.get("/api/v1/open-loop/summary", headers=headers)
    assert r.status_code == 200
    kinds = {item["kind"] for item in r.json()}
    assert "plan_drift" in kinds


def test_summary_sorts_by_score(client, auth_user_and_headers, db):
    user, headers = auth_user_and_headers
    from app.models.checkin import CheckinTemplate

    # 低分: 运动 3 天 (score 45)
    db.add(CheckinTemplate(
        user_id=user.id, name="俯卧撑", category="exercise", frequency="daily",
        is_active=True, is_archived=False,
        last_checkin_date=date.today() - timedelta(days=3),
    ))
    # 高分: 用药 7 天 (score 90)
    db.add(CheckinTemplate(
        user_id=user.id, name="华法林", category="medicine", frequency="daily",
        is_active=True, is_archived=False,
        last_checkin_date=date.today() - timedelta(days=7),
    ))
    db.commit()

    r = client.get("/api/v1/open-loop/summary", headers=headers)
    items = r.json()
    assert len(items) >= 2
    scores = [it["score"] for it in items]
    assert scores == sorted(scores, reverse=True)
