"""新手引导流程测试"""
import pytest
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.checkin import CheckinTemplate, DEFAULT_CHECKIN_TEMPLATES
from app.services.auth import auth_service


def _create_user(db, name="测试用户", **kwargs):
    """创建测试用户并返回 (user, token)"""
    user = User(name=name, is_active=True, is_approved=True, **kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, token


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


class TestOnboardingStatus:
    """引导状态接口"""

    def test_status_new_user(self, client, db):
        """新用户所有状态为 False"""
        user, token = _create_user(db)
        res = client.get("/api/v1/onboarding/status", headers=_auth_header(token))
        assert res.status_code == 200
        data = res.json()
        assert data["onboarding_completed"] is False
        assert data["has_profile"] is False
        assert data["has_health_goals"] is False
        assert data["has_checkin_templates"] is False

    def test_status_after_step1(self, client, db):
        """完成step1后 has_profile=True"""
        user, token = _create_user(db)
        client.post(
            "/api/v1/onboarding/step1",
            json={"height_cm": 175, "current_weight_kg": 70},
            headers=_auth_header(token),
        )
        res = client.get("/api/v1/onboarding/status", headers=_auth_header(token))
        assert res.json()["has_profile"] is True

    def test_status_after_step2_custom_goals(self, client, db):
        """修改健康目标后 has_health_goals=True"""
        user, token = _create_user(db)
        client.post(
            "/api/v1/onboarding/step2",
            json={"target_steps": 10000, "target_sleep_hours": 8, "target_water_ml": 2500, "target_exercise_minutes": 45},
            headers=_auth_header(token),
        )
        res = client.get("/api/v1/onboarding/status", headers=_auth_header(token))
        assert res.json()["has_health_goals"] is True

    def test_status_after_complete(self, client, db):
        """完成引导后 onboarding_completed=True"""
        user, token = _create_user(db)
        client.post(
            "/api/v1/onboarding/complete",
            json={"init_default_templates": False},
            headers=_auth_header(token),
        )
        res = client.get("/api/v1/onboarding/status", headers=_auth_header(token))
        assert res.json()["onboarding_completed"] is True


class TestStep1:
    """基本信息保存"""

    def test_step1_creates_profile(self, client, db):
        """step1创建新的UserProfile"""
        user, token = _create_user(db)
        res = client.post(
            "/api/v1/onboarding/step1",
            json={"height_cm": 175, "current_weight_kg": 70, "gender": "male", "birth_date": "1990-05-15"},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        assert profile is not None
        assert profile.height_cm == 175
        assert profile.current_weight_kg == 70
        assert profile.gender == "male"
        assert str(profile.birth_date) == "1990-05-15"

    def test_step1_updates_existing(self, client, db):
        """step1更新已存在的profile"""
        user, token = _create_user(db)
        # 先创建 profile
        profile = UserProfile(user_id=user.id, height_cm=170)
        db.add(profile)
        db.commit()

        res = client.post(
            "/api/v1/onboarding/step1",
            json={"height_cm": 180},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        db.refresh(profile)
        assert profile.height_cm == 180

    def test_step1_partial_data(self, client, db):
        """step1只提交部分字段"""
        user, token = _create_user(db)
        res = client.post(
            "/api/v1/onboarding/step1",
            json={"height_cm": 175},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        assert profile.height_cm == 175
        assert profile.current_weight_kg is None

    def test_step1_validation_range(self, client, db):
        """step1校验字段范围"""
        user, token = _create_user(db)
        res = client.post(
            "/api/v1/onboarding/step1",
            json={"height_cm": 10},  # 太矮，min=50
            headers=_auth_header(token),
        )
        assert res.status_code == 422


class TestStep2:
    """健康目标保存"""

    def test_step2_saves_goals(self, client, db):
        """step2保存健康目标"""
        user, token = _create_user(db)
        res = client.post(
            "/api/v1/onboarding/step2",
            json={"target_steps": 10000, "target_sleep_hours": 8, "target_water_ml": 2500, "target_exercise_minutes": 45},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        assert profile.target_steps == 10000
        assert profile.target_sleep_hours == 8
        assert profile.target_water_ml == 2500
        assert profile.target_exercise_minutes == 45

    def test_step2_creates_profile_if_missing(self, client, db):
        """step2在没有profile时自动创建"""
        user, token = _create_user(db)
        res = client.post(
            "/api/v1/onboarding/step2",
            json={"target_steps": 12000, "target_sleep_hours": 7, "target_water_ml": 3000, "target_exercise_minutes": 60},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        assert profile is not None
        assert profile.target_steps == 12000

    def test_step2_default_values(self, client, db):
        """step2使用默认值"""
        user, token = _create_user(db)
        res = client.post(
            "/api/v1/onboarding/step2",
            json={},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        assert profile.target_steps == 8000
        assert profile.target_sleep_hours == 7.5


class TestComplete:
    """完成引导"""

    def test_complete_initializes_templates(self, client, db):
        """完成时初始化全部默认模板"""
        user, token = _create_user(db)
        res = client.post(
            "/api/v1/onboarding/complete",
            json={"init_default_templates": True},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["onboarding_completed"] is True
        assert data["templates_created"] == len(DEFAULT_CHECKIN_TEMPLATES)

        templates = db.query(CheckinTemplate).filter(CheckinTemplate.user_id == user.id).all()
        assert len(templates) == len(DEFAULT_CHECKIN_TEMPLATES)

    def test_complete_selected_only(self, client, db):
        """只初始化选中的模板"""
        user, token = _create_user(db)
        selected = ["俯卧撑", "深蹲"]
        res = client.post(
            "/api/v1/onboarding/complete",
            json={"init_default_templates": True, "selected_template_names": selected},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        assert res.json()["templates_created"] == 2

        templates = db.query(CheckinTemplate).filter(CheckinTemplate.user_id == user.id).all()
        names = {t.name for t in templates}
        assert names == {"俯卧撑", "深蹲"}

    def test_complete_skips_if_templates_exist(self, client, db):
        """已有模板时不重复创建"""
        user, token = _create_user(db)
        # 先创建一个模板
        db.add(CheckinTemplate(user_id=user.id, name="已有模板", category="custom", unit="次"))
        db.commit()

        res = client.post(
            "/api/v1/onboarding/complete",
            json={"init_default_templates": True},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        assert res.json()["templates_created"] == 0

    def test_complete_without_templates(self, client, db):
        """不初始化模板也能完成"""
        user, token = _create_user(db)
        res = client.post(
            "/api/v1/onboarding/complete",
            json={"init_default_templates": False},
            headers=_auth_header(token),
        )
        assert res.status_code == 200
        assert res.json()["onboarding_completed"] is True
        assert res.json()["templates_created"] == 0

    def test_complete_marks_user_flag(self, client, db):
        """完成后User.onboarding_completed=True"""
        user, token = _create_user(db)
        assert user.onboarding_completed is False

        client.post(
            "/api/v1/onboarding/complete",
            json={"init_default_templates": False},
            headers=_auth_header(token),
        )
        db.refresh(user)
        assert user.onboarding_completed is True


class TestSkip:
    """跳过引导"""

    def test_skip_does_not_mark_complete(self, client, db):
        """跳过不标记完成"""
        user, token = _create_user(db)
        res = client.post("/api/v1/onboarding/skip", headers=_auth_header(token))
        assert res.status_code == 200
        assert res.json()["onboarding_completed"] is False
        db.refresh(user)
        assert user.onboarding_completed is False


class TestAuth:
    """认证检查"""

    def test_endpoints_require_auth(self, client):
        """所有端点需要认证"""
        endpoints = [
            ("GET", "/api/v1/onboarding/status"),
            ("POST", "/api/v1/onboarding/step1"),
            ("POST", "/api/v1/onboarding/step2"),
            ("POST", "/api/v1/onboarding/complete"),
            ("POST", "/api/v1/onboarding/skip"),
        ]
        for method, url in endpoints:
            if method == "GET":
                res = client.get(url)
            else:
                res = client.post(url, json={})
            assert res.status_code in (401, 403), f"{method} {url} should require auth, got {res.status_code}"
