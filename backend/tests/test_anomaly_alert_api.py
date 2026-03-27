"""异常预警 API 测试"""
import pytest
from datetime import date, timedelta
from app.models.user import User
from app.models.anomaly_alert import AnomalyAlert


@pytest.fixture
def test_user(db):
    user = User(
        username="alertuser",
        email="alert@example.com",
        hashed_password="hashed_password",
        name="预警测试用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_alerts(db, test_user):
    alerts = [
        AnomalyAlert(
            user_id=test_user.id,
            alert_type="hrv_drop",
            severity="warning",
            metric_name="hrv",
            current_value=22,
            baseline_value=45,
            deviation_pct=-51.0,
            detection_date=date.today(),
            message="HRV 连续偏低",
            acknowledged=False,
        ),
        AnomalyAlert(
            user_id=test_user.id,
            alert_type="rhr_spike",
            severity="critical",
            metric_name="resting_heart_rate",
            current_value=85,
            baseline_value=65,
            deviation_pct=30.0,
            detection_date=date.today() - timedelta(days=1),
            message="静息心率异常升高",
            acknowledged=False,
        ),
        AnomalyAlert(
            user_id=test_user.id,
            alert_type="sleep_low",
            severity="info",
            metric_name="sleep_score",
            current_value=45,
            baseline_value=70,
            deviation_pct=-35.0,
            detection_date=date.today() - timedelta(days=10),
            message="睡眠质量下降（超出查询范围）",
            acknowledged=True,
        ),
    ]
    db.add_all(alerts)
    db.commit()
    return alerts


class TestAnomalyAlertAPI:

    def test_get_alerts_default(self, client, auth_headers, sample_alerts):
        response = client.get("/api/v1/anomaly-alerts/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # 默认 7 天，第 3 条超出范围但 acknowledged 未过滤
        assert data["count"] >= 2

    def test_get_alerts_unacknowledged(self, client, auth_headers, sample_alerts):
        response = client.get(
            "/api/v1/anomaly-alerts/me?days=7&acknowledged=false",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for alert in data["alerts"]:
            assert alert["acknowledged"] is False

    def test_get_alerts_by_severity(self, client, auth_headers, sample_alerts):
        response = client.get(
            "/api/v1/anomaly-alerts/me?severity=critical",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for alert in data["alerts"]:
            assert alert["severity"] == "critical"

    def test_acknowledge_alert(self, client, auth_headers, sample_alerts):
        alert_id = sample_alerts[0].id
        response = client.patch(
            f"/api/v1/anomaly-alerts/{alert_id}/acknowledge",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_acknowledge_nonexistent(self, client, auth_headers, sample_alerts):
        response = client.patch(
            "/api/v1/anomaly-alerts/99999/acknowledge",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_acknowledge_all(self, client, auth_headers, sample_alerts):
        response = client.patch(
            "/api/v1/anomaly-alerts/acknowledge-all?days=7",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] >= 1

    def test_no_auth(self, client):
        response = client.get("/api/v1/anomaly-alerts/me")
        assert response.status_code in (401, 403)
