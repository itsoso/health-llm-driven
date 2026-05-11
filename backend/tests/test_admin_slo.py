"""test_admin_slo —— P4-4 SLO 端点 + 颜色分级."""

from datetime import datetime, timedelta, timezone
import uuid

from app.models.agent_audit_log import AgentAuditLog
from app.models.notification import NotificationLog, NotificationStatus
from app.models.user import User
from app.services.auth import auth_service


def _admin_headers(db):
    admin = User(
        username=f"slo_admin_{uuid.uuid4().hex[:8]}",
        email=f"slo_admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="slo_admin",
        is_active=True,
        is_admin=True,
        is_approved=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    token = auth_service.create_access_token({"sub": str(admin.id)})
    return admin, {"Authorization": f"Bearer {token}"}


def test_slo_requires_admin(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    resp = client.get("/api/v1/admin/slo", headers=headers)
    assert resp.status_code == 403


def test_slo_empty_returns_unknown(client, db):
    _, headers = _admin_headers(db)
    resp = client.get("/api/v1/admin/slo", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "slos" in body
    assert len(body["slos"]) == 3
    keys = {s["key"] for s in body["slos"]}
    assert keys == {"apns_delivery", "twin_build_p99", "orchestrator_p99"}
    # 空数据 → 全 unknown
    for s in body["slos"]:
        assert s["grade"] == "unknown"
        assert s["value"] is None


def test_apns_delivery_green(client, db):
    admin, headers = _admin_headers(db)
    # 100 sent / 0 failed = 100% → green
    for _ in range(100):
        db.add(NotificationLog(
            user_id=admin.id,
            notification_type="health_alert",
            channel="multi",
            title="t", content="c",
            status=NotificationStatus.SENT.value,
        ))
    db.commit()
    resp = client.get("/api/v1/admin/slo", headers=headers)
    apns = next(s for s in resp.json()["slos"] if s["key"] == "apns_delivery")
    assert apns["grade"] == "green"
    assert apns["value"] == 1.0


def test_apns_delivery_red(client, db):
    admin, headers = _admin_headers(db)
    # 5 sent / 95 failed = 5% → red
    for _ in range(5):
        db.add(NotificationLog(
            user_id=admin.id, notification_type="x", channel="m",
            title="t", content="c", status=NotificationStatus.SENT.value,
        ))
    for _ in range(95):
        db.add(NotificationLog(
            user_id=admin.id, notification_type="x", channel="m",
            title="t", content="c", status=NotificationStatus.FAILED.value,
        ))
    db.commit()
    resp = client.get("/api/v1/admin/slo", headers=headers)
    apns = next(s for s in resp.json()["slos"] if s["key"] == "apns_delivery")
    assert apns["grade"] == "red"


def test_apns_delivery_yellow(client, db):
    admin, headers = _admin_headers(db)
    # 85 sent / 15 failed = 85% → yellow
    for _ in range(85):
        db.add(NotificationLog(
            user_id=admin.id, notification_type="x", channel="m",
            title="t", content="c", status=NotificationStatus.SENT.value,
        ))
    for _ in range(15):
        db.add(NotificationLog(
            user_id=admin.id, notification_type="x", channel="m",
            title="t", content="c", status=NotificationStatus.FAILED.value,
        ))
    db.commit()
    resp = client.get("/api/v1/admin/slo", headers=headers)
    apns = next(s for s in resp.json()["slos"] if s["key"] == "apns_delivery")
    assert apns["grade"] == "yellow"


def test_twin_p99_grades(client, db):
    admin, headers = _admin_headers(db)
    # 50 条 3000ms + 50 条 5000ms, P99 落在尾部 5000 → red
    for ms in [3000] * 50 + [5000] * 50:
        db.add(AgentAuditLog(
            user_id=admin.id, agent_type="orchestrator",
            action="evaluate", twin_build_ms=ms,
        ))
    db.commit()
    resp = client.get("/api/v1/admin/slo", headers=headers)
    twin = next(s for s in resp.json()["slos"] if s["key"] == "twin_build_p99")
    assert twin["grade"] == "red"
    assert twin["value"] == 5000


def test_twin_p99_green(client, db):
    admin, headers = _admin_headers(db)
    for ms in [400, 500, 600, 700, 750]:
        db.add(AgentAuditLog(
            user_id=admin.id, agent_type="orchestrator",
            action="evaluate", twin_build_ms=ms,
        ))
    db.commit()
    resp = client.get("/api/v1/admin/slo", headers=headers)
    twin = next(s for s in resp.json()["slos"] if s["key"] == "twin_build_p99")
    assert twin["grade"] == "green"


def test_orchestrator_p99(client, db):
    admin, headers = _admin_headers(db)
    # 仅 agent_type='orchestrator' 计入
    for ms in [3000, 4000, 5000]:
        db.add(AgentAuditLog(
            user_id=admin.id, agent_type="orchestrator",
            action="run", total_ms=ms,
        ))
    # 噪声: 别的 agent_type 不算
    db.add(AgentAuditLog(
        user_id=admin.id, agent_type="safety_guardian",
        action="evaluate", total_ms=99999,
    ))
    db.commit()
    resp = client.get("/api/v1/admin/slo", headers=headers)
    orch = next(s for s in resp.json()["slos"] if s["key"] == "orchestrator_p99")
    assert orch["grade"] == "green"
    assert orch["value"] == 5000


def test_24h_window_excludes_old(client, db):
    """超过 24h 的记录不算入 SLO."""
    admin, headers = _admin_headers(db)
    old_log = NotificationLog(
        user_id=admin.id, notification_type="x", channel="m",
        title="t", content="c", status=NotificationStatus.FAILED.value,
        created_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )
    fresh_log = NotificationLog(
        user_id=admin.id, notification_type="x", channel="m",
        title="t", content="c", status=NotificationStatus.SENT.value,
    )
    db.add_all([old_log, fresh_log])
    db.commit()
    resp = client.get("/api/v1/admin/slo", headers=headers)
    apns = next(s for s in resp.json()["slos"] if s["key"] == "apns_delivery")
    # 24h 窗口内只有 1 条 sent / 0 failed = 100% green
    assert apns["value"] == 1.0
    assert apns["grade"] == "green"
