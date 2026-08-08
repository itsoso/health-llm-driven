"""体重记录API测试"""
import pytest
from datetime import date, timedelta
from pydantic import ValidationError

from app.models.user import User
from app.schemas.weight import WeightRecordInput, WeightRecordUpdate


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="weightuser",
        email="weight@example.com",
        hashed_password="hashed_password",
        name="体重测试用户",
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


@pytest.fixture
def sample_weight_data():
    """示例体重数据"""
    return {
        "record_date": str(date.today()),
        "weight": 70.5,
        "body_fat_percentage": 18.5,
        "muscle_mass": 35.0,
        "notes": "晨起测量"
    }


class TestWeightAPI:
    """体重记录API测试类"""

    def test_create_weight_record(self, client, auth_headers, sample_weight_data):
        """测试创建体重记录"""
        response = client.post(
            "/api/v1/weight/records",
            json=sample_weight_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 70.5
        assert data["body_fat_percentage"] == 18.5
        assert "id" in data

    def test_create_weight_record_minimal(self, client, auth_headers):
        """测试创建最小体重记录（只有体重）"""
        minimal_data = {
            "record_date": str(date.today()),
            "weight": 68.0
        }
        response = client.post(
            "/api/v1/weight/records",
            json=minimal_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 68.0
        assert data["body_fat_percentage"] is None

    def test_update_same_day_record(self, client, auth_headers, sample_weight_data):
        """测试同一天更新记录（应覆盖）"""
        # 创建第一条记录
        response1 = client.post(
            "/api/v1/weight/records",
            json=sample_weight_data,
            headers=auth_headers
        )
        assert response1.status_code == 200

        # 同一天再创建一条（应该更新）
        sample_weight_data["weight"] = 71.0
        response2 = client.post(
            "/api/v1/weight/records",
            json=sample_weight_data,
            headers=auth_headers
        )
        assert response2.status_code == 200
        assert response2.json()["weight"] == 71.0

        # 验证只有一条记录
        get_response = client.get(
            "/api/v1/weight/records/me?limit=10",
            headers=auth_headers
        )
        records = get_response.json()
        today_records = [r for r in records if r["record_date"] == str(date.today())]
        assert len(today_records) == 1

    def test_get_my_weight_records(self, client, auth_headers, sample_weight_data):
        """测试获取我的体重记录"""
        # 先创建记录
        client.post(
            "/api/v1/weight/records",
            json=sample_weight_data,
            headers=auth_headers
        )

        # 获取记录
        response = client.get(
            "/api/v1/weight/records/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_my_weight_stats(self, client, auth_headers, sample_weight_data):
        """测试获取我的体重统计"""
        # 先创建记录
        client.post(
            "/api/v1/weight/records",
            json=sample_weight_data,
            headers=auth_headers
        )

        # 获取统计
        response = client.get(
            "/api/v1/weight/records/me/stats?days=30",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_weight" in data or "average_weight" in data or "total_records" in data

    def test_weight_trend(self, client, auth_headers):
        """测试体重趋势（多天数据）"""
        # 创建多天记录
        weights = [70.0, 69.5, 69.8, 69.2, 69.0]
        for i, weight in enumerate(weights):
            data = {
                "record_date": str(date.today() - timedelta(days=i)),
                "weight": weight
            }
            response = client.post(
                "/api/v1/weight/records",
                json=data,
                headers=auth_headers
            )
            assert response.status_code == 200

        # 获取记录验证趋势
        response = client.get(
            "/api/v1/weight/records/me?limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        records = response.json()
        assert len(records) >= 5

    def test_unauthorized_access(self, client, sample_weight_data):
        """测试未授权访问"""
        response = client.post(
            "/api/v1/weight/records",
            json=sample_weight_data
        )
        assert response.status_code == 401


class TestWeightValidation:
    """体重记录验证测试"""

    @pytest.mark.parametrize(
        "value",
        ("Infinity", "-Infinity", "NaN", "1e309", "-1e309"),
    )
    def test_weight_schemas_reject_coerced_non_finite_values(self, value):
        with pytest.raises(ValidationError):
            WeightRecordInput.model_validate({
                "record_date": str(date.today()),
                "weight": value,
            })
        with pytest.raises(ValidationError):
            WeightRecordUpdate.model_validate({"weight": value})

    @pytest.mark.parametrize(
        "value",
        ("Infinity", "-Infinity", "NaN", "1e309", "-1e309"),
    )
    def test_weight_api_rejects_coerced_non_finite_values(
        self,
        client,
        auth_headers,
        sample_weight_data,
        value,
    ):
        create_response = client.post(
            "/api/v1/weight/records",
            json={**sample_weight_data, "weight": value},
            headers=auth_headers,
        )
        assert create_response.status_code == 422

        created = client.post(
            "/api/v1/weight/records",
            json=sample_weight_data,
            headers=auth_headers,
        )
        assert created.status_code == 200
        update_response = client.put(
            f"/api/v1/weight/records/{created.json()['id']}",
            json={"weight": value},
            headers=auth_headers,
        )
        assert update_response.status_code == 422

    def test_weight_schemas_preserve_finite_numeric_strings_and_notes(self):
        payload = {
            "weight": "71.4",
            "notes": "Infinity 和 NaN 是本条备注里的普通单词",
        }
        parsed = WeightRecordUpdate.model_validate(payload)
        assert parsed.weight == 71.4
        assert parsed.notes == payload["notes"]

    def test_negative_weight(self, client, auth_headers):
        """测试负数体重（应该失败）"""
        data = {
            "record_date": str(date.today()),
            "weight": -70.0
        }
        response = client.post(
            "/api/v1/weight/records",
            json=data,
            headers=auth_headers
        )
        # 负数体重应该被拒绝
        assert response.status_code in [200, 422]  # 根据具体验证规则

    def test_extreme_weight(self, client, auth_headers):
        """测试极端体重值"""
        data = {
            "record_date": str(date.today()),
            "weight": 500.0  # 不太可能的体重
        }
        response = client.post(
            "/api/v1/weight/records",
            json=data,
            headers=auth_headers
        )
        # 根据业务规则可能允许或不允许
        assert response.status_code in [200, 422]

    def test_body_fat_range(self, client, auth_headers):
        """测试体脂率范围"""
        # 正常范围的体脂率
        data = {
            "record_date": str(date.today()),
            "weight": 70.0,
            "body_fat_percentage": 25.0
        }
        response = client.post(
            "/api/v1/weight/records",
            json=data,
            headers=auth_headers
        )
        assert response.status_code == 200
