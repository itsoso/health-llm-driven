"""跑步动态指导 (Live Run Coach) API测试"""
import pytest
from datetime import datetime, timedelta, date
from app.models.user import User


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="runuser",
        email="run@example.com",
        hashed_password="hashed_password",
        name="跑步测试用户",
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    """获取认证 headers"""
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


class TestLiveRunAPI:
    """跑步会话API测试类"""

    def test_start_run_easy(self, client, auth_headers):
        """测试开始跑步 - easy 预设"""
        payload = {"target_label": "easy"}
        response = client.post(
            "/api/v1/live-run/start",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["target_pace_seconds"] == 360  # 6:00
        assert data["target_label"] == "easy"
        assert data["started_at"] is not None
        assert data["ended_at"] is None
        assert data["narrative_status"] == "pending"

    def test_start_run_includes_readiness_snapshot(self, client, auth_headers, db, test_user):
        """测试开始跑步 - 返回 readiness_score 快照（来自 Garmin 数据）"""
        from app.models.daily_health import GarminData

        db.add(GarminData(
            user_id=test_user.id,
            record_date=date.today(),
            training_readiness_score=42,
        ))
        db.commit()

        response = client.post(
            "/api/v1/live-run/start",
            json={"target_label": "easy"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["readiness_score"] == 42
        assert data["max_z4_minutes"] == 30

    def test_start_run_tempo(self, client, auth_headers):
        """测试开始跑步 - tempo 预设"""
        payload = {"target_label": "tempo"}
        response = client.post(
            "/api/v1/live-run/start",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["target_pace_seconds"] == 330  # 5:30
        assert data["target_label"] == "tempo"

    def test_start_run_custom(self, client, auth_headers):
        """测试开始跑步 - 自定义配速"""
        payload = {
            "target_label": "custom",
            "target_pace_seconds": 300,  # 5:00
            "notes": "晨跑"
        }
        response = client.post(
            "/api/v1/live-run/start",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["target_pace_seconds"] == 300
        assert data["target_label"] == "custom"
        assert data["notes"] == "晨跑"

    def test_start_run_custom_missing_pace_400(self, client, auth_headers):
        """测试 custom 模式缺配速"""
        payload = {"target_label": "custom"}
        response = client.post(
            "/api/v1/live-run/start",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 400
        assert "target_pace_seconds" in response.json()["detail"]

    def test_start_run_invalid_pace_range(self, client, auth_headers):
        """测试配速超出范围"""
        for bad_pace in [179, 901]:  # 2:59 ~ 15:01 out
            payload = {
                "target_label": "custom",
                "target_pace_seconds": bad_pace,
            }
            response = client.post(
                "/api/v1/live-run/start",
                json=payload,
                headers=auth_headers
            )
            assert response.status_code == 422

    def test_end_run(self, client, auth_headers):
        """测试结束跑步"""
        # 先开始
        start_resp = client.post("/api/v1/live-run/start", json={"target_label": "tempo"}, headers=auth_headers)
        run_id = start_resp.json()["id"]

        # 结束
        end_payload = {
            "total_distance_m": 5000.0,
            "total_duration_s": 1800,  # 30分钟
            "avg_pace_seconds": 345,   # 5:45
            "avg_hr": 152,
            "max_hr": 175,
            "z4_plus_minutes": 5.5,
            "calories": 350,
            "events": [
                {
                    "ts": datetime.utcnow().isoformat(),
                    "rule_id": "pace_drift",
                    "message": "配速偏快,建议降到 5:30"
                }
            ],
            "gps_samples": [
                {
                    "ts": datetime.utcnow().isoformat(),
                    "lat": 39.9,
                    "lon": 116.4,
                    "pace": 360
                }
            ]
        }
        response = client.post(
            f"/api/v1/live-run/{run_id}/end",
            json=end_payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ended_at"] is not None
        assert data["total_distance_m"] == 5000.0
        assert data["avg_pace_seconds"] == 345
        assert len(data["events"]) == 1
        assert len(data["gps_samples"]) == 1

    def test_end_run_aborted(self, client, auth_headers):
        """测试放弃跑步"""
        start_resp = client.post("/api/v1/live-run/start", json={"target_label": "easy"}, headers=auth_headers)
        run_id = start_resp.json()["id"]

        response = client.post(
            f"/api/v1/live-run/{run_id}/end",
            json={
                "total_distance_m": 80.0,
                "total_duration_s": 30,
                "aborted": True
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["aborted"] is True

    def test_end_nonexistent_run_404(self, client, auth_headers):
        """测试结束不存在的跑步"""
        response = client.post(
            "/api/v1/live-run/99999/end",
            json={"total_distance_m": 1000, "total_duration_s": 300},
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_get_my_runs_default_range(self, client, auth_headers):
        """测试获取我的跑步记录 (默认 30 天)"""
        # 创建一条跑步
        start_resp = client.post("/api/v1/live-run/start", json={"target_label": "tempo"}, headers=auth_headers)
        run_id = start_resp.json()["id"]
        client.post(
            f"/api/v1/live-run/{run_id}/end",
            json={"total_distance_m": 3000, "total_duration_s": 900},
            headers=auth_headers
        )

        # 获取列表
        response = client.get("/api/v1/live-run/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["target_label"] == "tempo"

    def test_get_run_detail(self, client, auth_headers):
        """测试获取单次跑步详情"""
        start_resp = client.post("/api/v1/live-run/start", json={"target_label": "easy"}, headers=auth_headers)
        run_id = start_resp.json()["id"]
        client.post(
            f"/api/v1/live-run/{run_id}/end",
            json={"total_distance_m": 2000, "total_duration_s": 600},
            headers=auth_headers
        )

        response = client.get(f"/api/v1/live-run/{run_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run_id
        assert data["target_pace_seconds"] == 360

    def test_delete_run(self, client, auth_headers):
        """测试删除跑步记录"""
        start_resp = client.post("/api/v1/live-run/start", json={"target_label": "fast"}, headers=auth_headers)
        run_id = start_resp.json()["id"]
        client.post(
            f"/api/v1/live-run/{run_id}/end",
            json={"total_distance_m": 1000, "total_duration_s": 240},
            headers=auth_headers
        )

        delete_response = client.delete(f"/api/v1/live-run/{run_id}", headers=auth_headers)
        assert delete_response.status_code == 204

    def test_unauthorized_access(self, client):
        """测试未授权访问"""
        response = client.post("/api/v1/live-run/start", json={"target_label": "easy"})
        assert response.status_code == 401


class TestLiveRunEventStructures:
    """测试事件和 GPS 样本结构"""

    def test_minimal_end_payload(self, client, auth_headers):
        """测试最小结束 payload"""
        start_resp = client.post("/api/v1/live-run/start", json={"target_label": "tempo"}, headers=auth_headers)
        run_id = start_resp.json()["id"]

        minimal = {
            "total_distance_m": 1000.0,
            "total_duration_s": 300,
        }
        response = client.post(f"/api/v1/live-run/{run_id}/end", json=minimal, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["gps_samples"] == []

    def test_event_with_metric_snapshot(self, client, auth_headers):
        """测试事件带指标快照"""
        start_resp = client.post("/api/v1/live-run/start", json={"target_label": "easy"}, headers=auth_headers)
        run_id = start_resp.json()["id"]

        event_with_snapshot = {
            "ts": datetime.utcnow().isoformat(),
            "rule_id": "hr_zone_overload",
            "message": "心率进入高区",
            "metric_snapshot": {"current_hr": 165, "zone": "Z4"}
        }
        response = client.post(
            f"/api/v1/live-run/{run_id}/end",
            json={
                "total_distance_m": 500,
                "total_duration_s": 60,
                "events": [event_with_snapshot]
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["metric_snapshot"]["current_hr"] == 165
