"""成就徽章系统测试"""
import pytest
from datetime import date, timedelta, datetime
from app.models.user import User
from app.models.achievement import BadgeDefinition, UserBadge, BADGE_SEED_DATA
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.models.daily_health import WaterIntake, GarminData, DietRecord
from app.models.chat import ChatConversation
from app.services.achievement_service import AchievementService
from app.services.auth import auth_service


def _create_user(db, name="测试用户"):
    user = User(name=name, is_active=True, is_approved=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_user_with_token(db, name="测试用户"):
    user = _create_user(db, name)
    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, token


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def service(db):
    svc = AchievementService(db)
    svc.seed_badges()
    return svc


# ── Seed Tests ──

class TestSeed:
    def test_seed_creates_all_badges(self, db):
        svc = AchievementService(db)
        created = svc.seed_badges()
        assert created == len(BADGE_SEED_DATA)
        total = db.query(BadgeDefinition).count()
        assert total == len(BADGE_SEED_DATA)

    def test_seed_idempotent(self, db):
        svc = AchievementService(db)
        svc.seed_badges()
        second = svc.seed_badges()
        assert second == 0
        assert db.query(BadgeDefinition).count() == len(BADGE_SEED_DATA)


# ── Progress Calculation ──

class TestProgressCalculation:
    def test_checkin_streak(self, db, service):
        """连续打卡天数计算"""
        user = _create_user(db)
        tmpl = CheckinTemplate(user_id=user.id, name="T", category="habit", unit="次")
        db.add(tmpl)
        db.commit()

        today = date.today()
        for i in range(5):
            db.add(CheckinRecord(
                user_id=user.id, template_id=tmpl.id,
                checkin_date=today - timedelta(days=i),
                value=1, target=1,
            ))
        db.commit()

        streak = service._get_checkin_streak(user.id)
        assert streak == 5

    def test_streak_broken_by_gap(self, db, service):
        """有断档时 streak 只计连续部分"""
        user = _create_user(db)
        tmpl = CheckinTemplate(user_id=user.id, name="T", category="habit", unit="次")
        db.add(tmpl)
        db.commit()

        today = date.today()
        # 今天 + 昨天 = 连续2天
        for i in range(2):
            db.add(CheckinRecord(
                user_id=user.id, template_id=tmpl.id,
                checkin_date=today - timedelta(days=i),
                value=1, target=1,
            ))
        # 前天断档，大前天有打卡
        db.add(CheckinRecord(
            user_id=user.id, template_id=tmpl.id,
            checkin_date=today - timedelta(days=3),
            value=1, target=1,
        ))
        db.commit()

        streak = service._get_checkin_streak(user.id)
        assert streak == 2

    def test_water_count(self, db, service):
        """累计饮水次数"""
        user = _create_user(db)
        for i in range(10):
            db.add(WaterIntake(
                user_id=user.id, record_date=date.today() - timedelta(days=i % 3),
                amount_ml=250,
            ))
        db.commit()

        count = service._get_water_total_count(user.id)
        assert count == 10

    def test_run_distance(self, db, service):
        """累计跑步距离"""
        user = _create_user(db)
        db.add(GarminData(user_id=user.id, record_date=date.today(), distance_meters=5000))
        db.add(GarminData(user_id=user.id, record_date=date.today() - timedelta(days=1), distance_meters=8000))
        db.commit()

        km = service._get_total_run_distance(user.id)
        assert km == 13.0

    def test_first_checkin(self, db, service):
        """第一次打卡检测"""
        user = _create_user(db)
        assert service._has_any_checkin(user.id) is False

        tmpl = CheckinTemplate(user_id=user.id, name="T", category="habit", unit="次")
        db.add(tmpl)
        db.commit()
        db.add(CheckinRecord(
            user_id=user.id, template_id=tmpl.id,
            checkin_date=date.today(), value=1, target=1,
        ))
        db.commit()
        assert service._has_any_checkin(user.id) is True

    def test_first_ai_chat(self, db, service):
        """首次AI对话检测"""
        user = _create_user(db)
        assert service._has_any_chat(user.id) is False

        db.add(ChatConversation(user_id=user.id, title="test"))
        db.commit()
        assert service._has_any_chat(user.id) is True

    def test_diet_count(self, db, service):
        """饮食记录计数"""
        user = _create_user(db)
        for i in range(5):
            db.add(DietRecord(
                user_id=user.id, record_date=date.today(),
                meal_type="lunch", food_name=f"food_{i}",
            ))
        db.commit()

        count = service._get_diet_count(user.id)
        assert count == 5

    def test_checkin_total(self, db, service):
        """累计打卡次数"""
        user = _create_user(db)
        tmpl = CheckinTemplate(user_id=user.id, name="T", category="habit", unit="次")
        db.add(tmpl)
        db.commit()
        for i in range(15):
            db.add(CheckinRecord(
                user_id=user.id, template_id=tmpl.id,
                checkin_date=date.today() - timedelta(days=i),
                value=1, target=1,
            ))
        db.commit()

        total = service._get_checkin_total(user.id)
        assert total == 15


# ── Award Logic ──

class TestAwardLogic:
    def test_badge_awarded_when_met(self, db, service):
        """满足条件时授予徽章"""
        user = _create_user(db)
        # 创建一次对话 → first_ai_chat 条件满足
        db.add(ChatConversation(user_id=user.id, title="test"))
        db.commit()

        newly = service.check_and_award(user.id)
        codes = [
            db.query(BadgeDefinition).get(ub.badge_id).code
            for ub in newly
        ]
        assert "first_ai_chat" in codes

    def test_not_awarded_below_threshold(self, db, service):
        """未达到阈值时不授予"""
        user = _create_user(db)
        # 没有任何数据
        newly = service.check_and_award(user.id)
        assert len(newly) == 0

    def test_not_awarded_twice(self, db, service):
        """同一徽章不重复授予"""
        user = _create_user(db)
        db.add(ChatConversation(user_id=user.id, title="test"))
        db.commit()

        first = service.check_and_award(user.id)
        assert len([n for n in first if db.query(BadgeDefinition).get(n.badge_id).code == "first_ai_chat"]) == 1

        second = service.check_and_award(user.id)
        ai_chat_again = [n for n in second if db.query(BadgeDefinition).get(n.badge_id).code == "first_ai_chat"]
        assert len(ai_chat_again) == 0

    def test_multiple_badges_at_once(self, db, service):
        """一次可以解锁多个徽章"""
        user = _create_user(db)
        # first_ai_chat
        db.add(ChatConversation(user_id=user.id, title="test"))
        # first_checkin
        tmpl = CheckinTemplate(user_id=user.id, name="T", category="habit", unit="次")
        db.add(tmpl)
        db.commit()
        db.add(CheckinRecord(
            user_id=user.id, template_id=tmpl.id,
            checkin_date=date.today(), value=1, target=1,
        ))
        db.commit()

        newly = service.check_and_award(user.id)
        codes = {
            db.query(BadgeDefinition).get(ub.badge_id).code
            for ub in newly
        }
        assert "first_ai_chat" in codes
        assert "first_checkin" in codes


# ── API Tests ──

class TestAchievementAPI:
    def test_get_definitions_public(self, client, db):
        """徽章定义接口不需要认证"""
        res = client.get("/api/v1/achievements/definitions")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == len(BADGE_SEED_DATA)

    def test_get_my_achievements_auth(self, client, db):
        """成就接口需要认证"""
        user, token = _create_user_with_token(db)
        res = client.get("/api/v1/achievements/me", headers=_auth_header(token))
        assert res.status_code == 200
        data = res.json()
        assert "total" in data
        assert "unlocked" in data
        assert "achievements" in data
        assert data["total"] == len(BADGE_SEED_DATA)

    def test_get_achievements_unauth_401(self, client):
        """未认证访问成就接口返回401"""
        res = client.get("/api/v1/achievements/me")
        assert res.status_code in (401, 403)

    def test_check_endpoint(self, client, db):
        """手动检查端点"""
        user, token = _create_user_with_token(db)
        # 先创建一个对话
        db.add(ChatConversation(user_id=user.id, title="test"))
        db.commit()

        res = client.post("/api/v1/achievements/check", headers=_auth_header(token))
        assert res.status_code == 200
        data = res.json()
        assert data["newly_unlocked"] >= 1

    def test_achievements_include_progress(self, client, db):
        """成就列表包含进度"""
        user, token = _create_user_with_token(db)
        # 创建5条饮水记录
        for i in range(5):
            db.add(WaterIntake(user_id=user.id, record_date=date.today(), amount_ml=250))
        db.commit()

        res = client.get("/api/v1/achievements/me", headers=_auth_header(token))
        data = res.json()
        water_badges = [a for a in data["achievements"] if a["code"] == "water_50"]
        assert len(water_badges) == 1
        assert water_badges[0]["progress"] == 5
        assert water_badges[0]["unlocked"] is False
