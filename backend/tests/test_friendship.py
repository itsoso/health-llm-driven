"""好友关系和PK挑战 API 测试"""
import pytest
from datetime import datetime, timedelta, timezone, date

from app.models.user import User
from app.models.friendship import Friendship, PKChallenge, ChallengeParticipant
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.models.activity_status import ActivityStatus
from app.api.deps import get_current_user_required
from main import app


# ===== Fixtures =====

@pytest.fixture
def user_a(db):
    """创建测试用户A"""
    user = User(
        name="用户A",
        username="user_a",
        email="a@test.com",
        hashed_password="hashed",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def user_b(db):
    """创建测试用户B"""
    user = User(
        name="用户B",
        username="user_b",
        email="b@test.com",
        hashed_password="hashed",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def user_c(db):
    """创建测试用户C"""
    user = User(
        name="用户C",
        username="user_c",
        email="c@test.com",
        hashed_password="hashed",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _set_auth(user):
    """切换当前认证用户"""
    async def override():
        return user
    app.dependency_overrides[get_current_user_required] = override


@pytest.fixture
def client_a(client, user_a):
    """以用户A身份认证的客户端"""
    _set_auth(user_a)
    yield client
    app.dependency_overrides.pop(get_current_user_required, None)


# ===== 好友关系测试 =====

class TestFriendship:
    """好友关系API测试"""

    def test_send_friend_request(self, client_a, user_b):
        """测试发送好友请求"""
        resp = client_a.post("/api/v1/friends/request", json={
            "friend_id": user_b.id,
            "message": "你好！"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["friend_id"] == user_b.id
        assert data["message"] == "你好！"
        assert data["friend_name"] == "用户B"

    def test_cannot_add_self(self, client_a, user_a):
        """测试不能添加自己"""
        resp = client_a.post("/api/v1/friends/request", json={
            "friend_id": user_a.id
        })
        assert resp.status_code == 400
        assert "自己" in resp.json()["detail"]

    def test_cannot_add_nonexistent_user(self, client_a):
        """测试不能添加不存在的用户"""
        resp = client_a.post("/api/v1/friends/request", json={
            "friend_id": 99999
        })
        assert resp.status_code == 404

    def test_accept_friend_request(self, client_a, user_a, user_b):
        """测试接受好友请求"""
        # A发送给B
        client_a.post("/api/v1/friends/request", json={"friend_id": user_b.id})

        # 切换到B来接受
        _set_auth(user_b)

        # B查看待处理请求
        pending = client_a.get("/api/v1/friends/requests/pending")
        assert pending.status_code == 200
        requests = pending.json()
        assert len(requests) == 1

        # B接受请求
        request_id = requests[0]["id"]
        accept_resp = client_a.put(f"/api/v1/friends/request/{request_id}/accept")
        assert accept_resp.status_code == 200
        assert accept_resp.json()["status"] == "accepted"

    def test_reject_friend_request(self, client_a, user_a, user_b):
        """测试拒绝好友请求"""
        # A发送给B
        client_a.post("/api/v1/friends/request", json={"friend_id": user_b.id})

        # 切换到B
        _set_auth(user_b)
        pending = client_a.get("/api/v1/friends/requests/pending")
        request_id = pending.json()[0]["id"]

        reject_resp = client_a.put(f"/api/v1/friends/request/{request_id}/reject")
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"

    def test_duplicate_request(self, client_a, user_b):
        """测试重复发送请求"""
        client_a.post("/api/v1/friends/request", json={"friend_id": user_b.id})
        resp = client_a.post("/api/v1/friends/request", json={"friend_id": user_b.id})
        assert resp.status_code == 400
        assert "等待" in resp.json()["detail"]

    def test_already_friends(self, client_a, user_a, user_b, db):
        """测试已经是好友时再次添加"""
        friendship = Friendship(
            user_id=user_a.id,
            friend_id=user_b.id,
            status="accepted",
        )
        db.add(friendship)
        db.commit()

        resp = client_a.post("/api/v1/friends/request", json={"friend_id": user_b.id})
        assert resp.status_code == 400
        assert "已经是好友" in resp.json()["detail"]

    def test_list_friends(self, client_a, user_a, user_b, db):
        """测试好友列表"""
        friendship = Friendship(
            user_id=user_a.id,
            friend_id=user_b.id,
            status="accepted",
        )
        db.add(friendship)
        db.commit()

        resp = client_a.get("/api/v1/friends/list")
        assert resp.status_code == 200
        friends = resp.json()
        assert len(friends) == 1
        assert friends[0]["name"] == "用户B"
        assert friends[0]["user_id"] == user_b.id

    def test_remove_friend(self, client_a, user_a, user_b, db):
        """测试删除好友"""
        friendship = Friendship(
            user_id=user_a.id,
            friend_id=user_b.id,
            status="accepted",
        )
        db.add(friendship)
        db.commit()
        db.refresh(friendship)

        resp = client_a.delete(f"/api/v1/friends/{friendship.id}")
        assert resp.status_code == 200

        # 确认已删除
        list_resp = client_a.get("/api/v1/friends/list")
        assert len(list_resp.json()) == 0

    def test_search_users(self, client_a, user_b):
        """测试搜索用户"""
        resp = client_a.get("/api/v1/friends/search?q=用户B")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["name"] == "用户B"
        assert results[0]["is_friend"] is False

    def test_search_users_shows_friend_status(self, client_a, user_a, user_b, db):
        """测试搜索结果显示好友状态"""
        friendship = Friendship(
            user_id=user_a.id,
            friend_id=user_b.id,
            status="accepted",
        )
        db.add(friendship)
        db.commit()

        resp = client_a.get("/api/v1/friends/search?q=用户B")
        results = resp.json()
        assert len(results) == 1
        assert results[0]["is_friend"] is True

    def test_search_does_not_return_self(self, client_a, user_a):
        """测试搜索不返回自己"""
        resp = client_a.get("/api/v1/friends/search?q=用户A")
        results = resp.json()
        user_ids = [r["id"] for r in results]
        assert user_a.id not in user_ids

    def test_cross_request_auto_accept(self, client_a, user_a, user_b):
        """测试互相发送请求时自动接受（B先发给A，A再发给B → 自动接受）"""
        # B先发给A
        _set_auth(user_b)
        client_a.post("/api/v1/friends/request", json={"friend_id": user_a.id})

        # A再发给B → 应该自动接受
        _set_auth(user_a)
        resp = client_a.post("/api/v1/friends/request", json={"friend_id": user_b.id})
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_re_send_after_rejection(self, client_a, user_a, user_b, db):
        """测试被拒绝后重新发送"""
        # 先创建一个被拒绝的关系
        friendship = Friendship(
            user_id=user_a.id,
            friend_id=user_b.id,
            status="rejected",
        )
        db.add(friendship)
        db.commit()

        resp = client_a.post("/api/v1/friends/request", json={
            "friend_id": user_b.id,
            "message": "再试一次"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"


# ===== PK挑战测试 =====

class TestPKChallenge:
    """PK挑战API测试"""

    @pytest.fixture
    def friendship_ab(self, db, user_a, user_b):
        """A和B是好友"""
        f = Friendship(
            user_id=user_a.id,
            friend_id=user_b.id,
            status="accepted",
        )
        db.add(f)
        db.commit()
        return f

    @pytest.fixture
    def checkin_template(self, db, user_a):
        """A的打卡模板"""
        tmpl = CheckinTemplate(
            user_id=user_a.id,
            name="俯卧撑",
            category="exercise",
            icon="💪",
            unit="个",
            default_target=20,
        )
        db.add(tmpl)
        db.commit()
        db.refresh(tmpl)
        return tmpl

    def test_create_study_time_challenge(self, client_a, user_a, user_b, friendship_ab):
        """测试创建学习时长PK挑战"""
        resp = client_a.post("/api/v1/pk-challenges", json={
            "title": "7天学习PK",
            "challenge_type": "study_time",
            "activity_category": "studying",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "7天学习PK"
        assert data["challenge_type"] == "study_time"
        assert data["status"] == "active"
        assert len(data["participants"]) == 2

    def test_create_checkin_challenge(self, client_a, user_a, user_b, friendship_ab, checkin_template):
        """测试创建打卡PK挑战"""
        resp = client_a.post("/api/v1/pk-challenges", json={
            "title": "俯卧撑PK",
            "challenge_type": "checkin",
            "checkin_template_id": checkin_template.id,
            "metric": "count",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["challenge_type"] == "checkin"
        assert data["checkin_template_id"] == checkin_template.id

    def test_create_challenge_requires_friend(self, client_a, user_c):
        """测试创建挑战必须是好友"""
        resp = client_a.post("/api/v1/pk-challenges", json={
            "title": "PK",
            "challenge_type": "study_time",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_c.id],
        })
        assert resp.status_code == 400
        assert "好友" in resp.json()["detail"]

    def test_create_checkin_challenge_requires_template(self, client_a, user_b, friendship_ab):
        """测试打卡PK需要指定模板"""
        resp = client_a.post("/api/v1/pk-challenges", json={
            "title": "PK",
            "challenge_type": "checkin",
            "metric": "count",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })
        assert resp.status_code == 400
        assert "打卡模板" in resp.json()["detail"]

    def test_list_challenges(self, client_a, user_a, user_b, friendship_ab):
        """测试挑战列表"""
        # 先创建一个
        client_a.post("/api/v1/pk-challenges", json={
            "title": "测试PK",
            "challenge_type": "study_time",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })

        resp = client_a.get("/api/v1/pk-challenges")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "测试PK"

    def test_get_challenge_detail(self, client_a, user_a, user_b, friendship_ab):
        """测试挑战详情"""
        create_resp = client_a.post("/api/v1/pk-challenges", json={
            "title": "详情测试",
            "challenge_type": "study_time",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })
        challenge_id = create_resp.json()["id"]

        resp = client_a.get(f"/api/v1/pk-challenges/{challenge_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "详情测试"
        assert "leaderboard" in data
        assert len(data["leaderboard"]) == 2

    def test_non_participant_cannot_view(self, client_a, user_a, user_b, user_c, friendship_ab):
        """测试非参与者不能查看详情"""
        create_resp = client_a.post("/api/v1/pk-challenges", json={
            "title": "PK",
            "challenge_type": "study_time",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })
        challenge_id = create_resp.json()["id"]

        # 切换到C
        _set_auth(user_c)
        resp = client_a.get(f"/api/v1/pk-challenges/{challenge_id}")
        assert resp.status_code == 403

    def test_cancel_challenge(self, client_a, user_a, user_b, friendship_ab):
        """测试取消挑战"""
        create_resp = client_a.post("/api/v1/pk-challenges", json={
            "title": "取消测试",
            "challenge_type": "study_time",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })
        challenge_id = create_resp.json()["id"]

        resp = client_a.delete(f"/api/v1/pk-challenges/{challenge_id}")
        assert resp.status_code == 200

        # 确认状态
        detail = client_a.get(f"/api/v1/pk-challenges/{challenge_id}")
        assert detail.json()["status"] == "cancelled"

    def test_non_creator_cannot_cancel(self, client_a, user_a, user_b, friendship_ab):
        """测试非创建者不能取消"""
        create_resp = client_a.post("/api/v1/pk-challenges", json={
            "title": "PK",
            "challenge_type": "study_time",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })
        challenge_id = create_resp.json()["id"]

        # 切换到B
        _set_auth(user_b)
        resp = client_a.delete(f"/api/v1/pk-challenges/{challenge_id}")
        assert resp.status_code == 404  # "不存在或无权操作"

    def test_my_stats(self, client_a, user_a, user_b, friendship_ab):
        """测试PK统计"""
        # 创建一个挑战
        client_a.post("/api/v1/pk-challenges", json={
            "title": "统计测试",
            "challenge_type": "study_time",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })

        resp = client_a.get("/api/v1/pk-challenges/stats/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_challenges"] == 1
        assert data["active_challenges"] == 1
        assert data["wins"] == 0

    def test_refresh_scores(self, client_a, user_a, user_b, friendship_ab, db):
        """测试刷新分数（学习时长类型）"""
        # 创建一个从3天前开始的挑战，这样活动记录落在挑战期间内
        now = datetime.now(timezone.utc)
        challenge = PKChallenge(
            creator_id=user_a.id,
            title="分数测试",
            challenge_type="study_time",
            activity_category="studying",
            metric="total_minutes",
            duration_days=7,
            start_date=now - timedelta(days=3),
            end_date=now + timedelta(days=4),
            status="active",
        )
        db.add(challenge)
        db.flush()

        for uid in [user_a.id, user_b.id]:
            p = ChallengeParticipant(
                challenge_id=challenge.id,
                user_id=uid,
                score=0,
            )
            db.add(p)

        # 为用户A添加一个1小时的学习活动
        activity = ActivityStatus(
            user_id=user_a.id,
            status_text="学习",
            category="studying",
            start_time=now - timedelta(hours=2),
            actual_end_time=now - timedelta(hours=1),
            is_active=False,
        )
        db.add(activity)
        db.commit()

        # 刷新分数
        resp = client_a.post(f"/api/v1/pk-challenges/{challenge.id}/refresh")
        assert resp.status_code == 200
        data = resp.json()

        # A应该有60分钟的分数
        a_participant = next(p for p in data["leaderboard"] if p["user_id"] == user_a.id)
        assert a_participant["score"] == 60.0
        assert a_participant["rank"] == 1

    def test_checkin_challenge_scoring(self, client_a, user_a, user_b, friendship_ab, checkin_template, db):
        """测试打卡PK分数计算"""
        # 创建一个从5天前开始的挑战
        now = datetime.now(timezone.utc)
        challenge = PKChallenge(
            creator_id=user_a.id,
            title="打卡PK",
            challenge_type="checkin",
            checkin_template_id=checkin_template.id,
            metric="count",
            duration_days=7,
            start_date=now - timedelta(days=5),
            end_date=now + timedelta(days=2),
            status="active",
        )
        db.add(challenge)
        db.flush()

        for uid in [user_a.id, user_b.id]:
            p = ChallengeParticipant(
                challenge_id=challenge.id,
                user_id=uid,
                score=0,
            )
            db.add(p)

        # 为A添加3天打卡记录（都在挑战期间内）
        today = date.today()
        for i in range(3):
            record = CheckinRecord(
                template_id=checkin_template.id,
                user_id=user_a.id,
                checkin_date=today - timedelta(days=i),
                value=20,
                target=20,
                completion_rate=100.0,
            )
            db.add(record)
        db.commit()

        # 刷新
        resp = client_a.post(f"/api/v1/pk-challenges/{challenge.id}/refresh")
        assert resp.status_code == 200
        data = resp.json()

        a_participant = next(p for p in data["leaderboard"] if p["user_id"] == user_a.id)
        assert a_participant["score"] == 3.0  # 3次打卡

    def test_streak_metric(self, client_a, user_a, user_b, friendship_ab, checkin_template, db):
        """测试连续天数指标"""
        # 创建一个从5天前开始的挑战
        now = datetime.now(timezone.utc)
        challenge = PKChallenge(
            creator_id=user_a.id,
            title="连续PK",
            challenge_type="checkin",
            checkin_template_id=checkin_template.id,
            metric="streak",
            duration_days=7,
            start_date=now - timedelta(days=5),
            end_date=now + timedelta(days=2),
            status="active",
        )
        db.add(challenge)
        db.flush()

        for uid in [user_a.id, user_b.id]:
            p = ChallengeParticipant(
                challenge_id=challenge.id,
                user_id=uid,
                score=0,
            )
            db.add(p)

        # 连续3天打卡
        today = date.today()
        for i in range(3):
            record = CheckinRecord(
                template_id=checkin_template.id,
                user_id=user_a.id,
                checkin_date=today - timedelta(days=i),
                value=20,
            )
            db.add(record)
        db.commit()

        resp = client_a.post(f"/api/v1/pk-challenges/{challenge.id}/refresh")
        data = resp.json()

        a_participant = next(p for p in data["leaderboard"] if p["user_id"] == user_a.id)
        assert a_participant["score"] == 3.0  # 3天连续

    def test_filter_challenges_by_status(self, client_a, user_a, user_b, friendship_ab):
        """测试按状态筛选挑战"""
        # 创建一个活跃的
        client_a.post("/api/v1/pk-challenges", json={
            "title": "活跃PK",
            "challenge_type": "study_time",
            "metric": "total_minutes",
            "duration_days": 7,
            "friend_ids": [user_b.id],
        })

        # 筛选活跃
        resp = client_a.get("/api/v1/pk-challenges?status=active")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # 筛选已完成（应该为空）
        resp = client_a.get("/api/v1/pk-challenges?status=completed")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_auto_complete_expired_challenge(self, client_a, user_a, user_b, friendship_ab, db):
        """测试过期挑战自动标记为完成"""
        # 直接创建一个过期的挑战
        now = datetime.now(timezone.utc)
        challenge = PKChallenge(
            creator_id=user_a.id,
            title="过期PK",
            challenge_type="study_time",
            activity_category="studying",
            metric="total_minutes",
            duration_days=1,
            start_date=now - timedelta(days=3),
            end_date=now - timedelta(days=2),
            status="active",
        )
        db.add(challenge)
        db.flush()

        for uid in [user_a.id, user_b.id]:
            p = ChallengeParticipant(
                challenge_id=challenge.id,
                user_id=uid,
                score=0,
            )
            db.add(p)
        db.commit()

        # 查看列表时应该自动标记为完成
        resp = client_a.get("/api/v1/pk-challenges")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "completed"
