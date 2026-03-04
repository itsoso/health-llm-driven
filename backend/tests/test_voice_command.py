"""语音指令快速执行服务测试"""
import pytest
from datetime import date

from app.models.user import User
from app.models.daily_health import WaterIntake
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.services.voice_command_service import VoiceCommandService
from app.utils.timezone import get_china_today


@pytest.fixture
def test_user(db):
    user = User(name="语音测试用户", phone="13800138001")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def service(db, test_user):
    return VoiceCommandService(db, test_user.id)


@pytest.fixture
def checkin_template(db, test_user):
    """创建打卡模板"""
    t = CheckinTemplate(
        user_id=test_user.id,
        name="跑步",
        category="exercise",
        icon="🏃",
        unit="分钟",
        default_target=30,
        is_active=True,
        total_checkins=0,
        total_value=0,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


class TestWaterCommand:
    """饮水指令"""

    def test_drink_water_cup(self, db, test_user, service):
        """'喝了一杯水' -> 250ml"""
        result = service.try_execute("喝了一杯水")
        assert result is not None
        assert result["command_type"] == "water"
        assert result["data"]["amount_ml"] == 250

        # 验证DB记录
        record = db.query(WaterIntake).filter(WaterIntake.user_id == test_user.id).first()
        assert record is not None
        assert record.amount == 250

    def test_drink_water_two_cups(self, db, test_user, service):
        """'喝了两杯水' -> 500ml"""
        result = service.try_execute("喝了两杯水")
        assert result is not None
        assert result["data"]["amount_ml"] == 500

    def test_drink_water_ml(self, db, test_user, service):
        """'喝水300' -> 300ml"""
        result = service.try_execute("喝水300")
        assert result is not None
        assert result["data"]["amount_ml"] == 300

    def test_drink_water_with_ml_unit(self, db, test_user, service):
        """'喝了500ml水' -> 500ml"""
        result = service.try_execute("喝了500ml水")
        assert result is not None
        assert result["data"]["amount_ml"] == 500

    def test_drink_water_default(self, db, test_user, service):
        """'喝水' (无数量) -> 默认250ml"""
        result = service.try_execute("喝水")
        assert result is not None
        assert result["data"]["amount_ml"] == 250

    def test_drink_water_bottle(self, db, test_user, service):
        """'喝了一瓶水' -> 500ml"""
        result = service.try_execute("喝了一瓶水")
        assert result is not None
        assert result["data"]["amount_ml"] == 500


class TestWeightCommand:
    """体重指令"""

    def test_weight_kg(self, db, test_user, service):
        """'体重72公斤' -> 72.0kg"""
        result = service.try_execute("体重72公斤")
        assert result is not None
        assert result["command_type"] == "weight"
        assert result["data"]["weight_kg"] == 72.0

        record = db.query(WeightRecord).filter(WeightRecord.user_id == test_user.id).first()
        assert record is not None
        assert record.weight == 72.0

    def test_weight_decimal(self, db, test_user, service):
        """'体重72.5kg' -> 72.5kg"""
        result = service.try_execute("体重72.5kg")
        assert result is not None
        assert result["data"]["weight_kg"] == 72.5

    def test_weight_with_kg_unit(self, db, test_user, service):
        """'65kg' -> 65.0kg"""
        result = service.try_execute("65kg")
        assert result is not None
        assert result["data"]["weight_kg"] == 65.0

    def test_weight_jin(self, db, test_user, service):
        """'体重130斤' -> 65.0kg"""
        result = service.try_execute("130斤")
        assert result is not None
        assert result["data"]["weight_kg"] == 65.0

    def test_weight_updates_existing(self, db, test_user, service):
        """同一天重复记录体重应更新"""
        service.try_execute("体重72公斤")
        service.try_execute("体重73公斤")

        records = db.query(WeightRecord).filter(WeightRecord.user_id == test_user.id).all()
        assert len(records) == 1
        assert records[0].weight == 73.0


class TestBloodPressureCommand:
    """血压指令"""

    def test_bp_normal(self, db, test_user, service):
        """'血压115/75' -> 正常"""
        result = service.try_execute("血压115/75")
        assert result is not None
        assert result["command_type"] == "blood_pressure"
        assert result["data"]["systolic"] == 115
        assert result["data"]["diastolic"] == 75
        assert result["data"]["category"] == "正常"

    def test_bp_elevated(self, db, test_user, service):
        """'血压120/80' -> 正常偏高"""
        result = service.try_execute("血压120/80")
        assert result is not None
        assert result["data"]["systolic"] == 120
        assert result["data"]["diastolic"] == 80
        assert result["data"]["category"] == "正常偏高"

        record = db.query(BloodPressureRecord).filter(BloodPressureRecord.user_id == test_user.id).first()
        assert record is not None
        assert record.systolic == 120

    def test_bp_high(self, db, test_user, service):
        """'血压145/95' -> 高血压"""
        result = service.try_execute("血压145/95")
        assert result is not None
        assert result["data"]["category"] == "高血压"

    def test_bp_text_format(self, db, test_user, service):
        """'高压130低压85' -> 130/85"""
        result = service.try_execute("高压130低压85")
        assert result is not None
        assert result["data"]["systolic"] == 130
        assert result["data"]["diastolic"] == 85


class TestCheckinCommand:
    """打卡指令"""

    def test_checkin_match(self, db, test_user, service, checkin_template):
        """'跑步打卡' -> 匹配跑步模板"""
        result = service.try_execute("跑步打卡")
        assert result is not None
        assert result["command_type"] == "checkin"
        assert result["data"]["template_name"] == "跑步"

        record = db.query(CheckinRecord).filter(CheckinRecord.user_id == test_user.id).first()
        assert record is not None
        assert record.template_id == checkin_template.id

    def test_checkin_reverse_order(self, db, test_user, service, checkin_template):
        """'打卡跑步' 也能匹配"""
        result = service.try_execute("打卡跑步")
        assert result is not None
        assert result["command_type"] == "checkin"

    def test_checkin_already_done(self, db, test_user, service, checkin_template):
        """今天已打卡时提示"""
        service.try_execute("跑步打卡")
        result = service.try_execute("跑步打卡")
        assert result is not None
        assert result["data"]["already_done"] is True

    def test_checkin_no_template(self, db, test_user, service):
        """无匹配模板不触发"""
        result = service.try_execute("游泳打卡")
        assert result is None

    def test_checkin_pure_word_single_template(self, db, test_user, service, checkin_template):
        """'打卡' + 只有一个模板 -> 执行该模板"""
        result = service.try_execute("打卡")
        assert result is not None
        assert result["data"]["template_name"] == "跑步"


class TestEdgeCases:
    """边界情况"""

    def test_no_match_returns_none(self, db, test_user, service):
        """不匹配任何指令返回None"""
        result = service.try_execute("今天天气怎么样")
        assert result is None

    def test_empty_text(self, db, test_user, service):
        """空文本返回None"""
        assert service.try_execute("") is None
        assert service.try_execute("   ") is None

    def test_none_text(self, db, test_user, service):
        """None文本返回None"""
        assert service.try_execute(None) is None

    def test_water_creates_record_in_db(self, db, test_user, service):
        """验证饮水记录确实创建到数据库"""
        service.try_execute("喝了一杯水")
        count = db.query(WaterIntake).filter(WaterIntake.user_id == test_user.id).count()
        assert count == 1

    def test_weight_creates_record_in_db(self, db, test_user, service):
        """验证体重记录确实创建到数据库"""
        service.try_execute("体重75公斤")
        count = db.query(WeightRecord).filter(WeightRecord.user_id == test_user.id).count()
        assert count == 1


class TestVoiceCommandAPI:
    """API端点测试"""

    def test_api_matched(self, client, db):
        """API 返回匹配结果"""
        from app.services.auth import auth_service
        user = User(name="API测试用户", phone="13800138002", is_active=True, is_approved=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        token = auth_service.create_access_token({"sub": str(user.id)})

        response = client.post(
            "/api/v1/chat/voice-command",
            json={"text": "喝了一杯水"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["matched"] is True
        assert data["command_type"] == "water"

    def test_api_not_matched(self, client, db):
        """API 返回未匹配"""
        from app.services.auth import auth_service
        user = User(name="API测试用户2", phone="13800138003", is_active=True, is_approved=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        token = auth_service.create_access_token({"sub": str(user.id)})

        response = client.post(
            "/api/v1/chat/voice-command",
            json={"text": "今天天气怎么样"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["matched"] is False

    def test_api_requires_auth(self, client):
        """API 需要认证"""
        response = client.post(
            "/api/v1/chat/voice-command",
            json={"text": "喝水"},
        )
        assert response.status_code in [401, 403]
