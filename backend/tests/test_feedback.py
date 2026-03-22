"""交互反馈 API 测试"""
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from app.models.user import User
from app.models.interaction_feedback import InteractionFeedback, SkillMetrics


@pytest.fixture
def test_user(db):
    user = User(
        username="feedbackuser",
        email="feedback@example.com",
        hashed_password="hashed_password",
        name="反馈测试用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db):
    user = User(
        username="adminuser",
        email="admin@example.com",
        hashed_password="hashed_password",
        name="管理员",
        is_active=True,
        is_approved=True,
        is_admin=True,
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
def admin_headers(client, admin_user):
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


# ===== 反馈提交 API 测试 =====

class TestFeedbackAPI:

    def test_submit_thumbs_up(self, client, auth_headers):
        """测试提交 👍 评分"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "chat",
                "conversation_id": 1,
                "message_id": 10,
                "rating": 5,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 5
        assert data["id"] > 0

    def test_submit_thumbs_down_with_text(self, client, auth_headers):
        """测试提交 👎 + 文字反馈"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "openclaw",
                "conversation_id": 2,
                "message_id": 20,
                "rating": 1,
                "feedback_text": "回答不准确",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 1
        assert data["feedback_text"] == "回答不准确"

    def test_update_existing_feedback(self, client, auth_headers):
        """测试更新已有反馈（先 👎 后改 👍）"""
        payload = {
            "conversation_type": "chat",
            "conversation_id": 1,
            "message_id": 100,
            "rating": 1,
        }
        resp1 = client.post("/api/v1/feedback", json=payload, headers=auth_headers)
        assert resp1.status_code == 200
        first_id = resp1.json()["id"]

        payload["rating"] = 5
        resp2 = client.post("/api/v1/feedback", json=payload, headers=auth_headers)
        assert resp2.status_code == 200
        assert resp2.json()["rating"] == 5
        # 应该是同一条记录被更新，而不是新建
        assert resp2.json()["id"] == first_id

    def test_invalid_rating_too_high(self, client, auth_headers):
        """测试评分超出范围被拒绝"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "chat",
                "conversation_id": 1,
                "message_id": 1,
                "rating": 10,
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_invalid_rating_too_low(self, client, auth_headers):
        """测试评分低于最小值被拒绝"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "chat",
                "conversation_id": 1,
                "message_id": 1,
                "rating": 0,
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_invalid_conversation_type(self, client, auth_headers):
        """测试非法 conversation_type 被拒绝"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "invalid",
                "conversation_id": 1,
                "message_id": 1,
                "rating": 5,
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_unauthorized(self, client):
        """测试未登录被拒绝"""
        response = client.post(
            "/api/v1/feedback",
            json={
                "conversation_type": "chat",
                "conversation_id": 1,
                "message_id": 1,
                "rating": 5,
            },
        )
        assert response.status_code == 401


# ===== 管理员 API 测试 =====

class TestAdminAPIs:

    def test_skill_performance_admin_only(self, client, auth_headers, admin_headers):
        """测试 Skill 性能查询仅管理员可用"""
        response = client.get("/api/v1/feedback/skills", headers=auth_headers)
        assert response.status_code == 403

        response = client.get("/api/v1/feedback/skills", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_optimization_logs_admin_only(self, client, auth_headers, admin_headers):
        """测试优化日志仅管理员可用"""
        response = client.get("/api/v1/feedback/optimization-logs", headers=auth_headers)
        assert response.status_code == 403

        response = client.get("/api/v1/feedback/optimization-logs", headers=admin_headers)
        assert response.status_code == 200

    def test_low_performing_admin_only(self, client, auth_headers, admin_headers):
        """测试低效 Skill 查询仅管理员可用"""
        response = client.get("/api/v1/feedback/skills/low-performing", headers=auth_headers)
        assert response.status_code == 403

        response = client.get("/api/v1/feedback/skills/low-performing", headers=admin_headers)
        assert response.status_code == 200

    def test_skill_registry_list(self, client, admin_headers):
        """测试列出 Skill 注册表"""
        response = client.get("/api/v1/feedback/skills/registry", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # 应该能看到已有的 5 个 skill
        names = [s["name"] for s in data]
        assert "health-query" in names

    def test_skill_registry_detail(self, client, admin_headers):
        """测试获取单个 Skill 详情"""
        response = client.get("/api/v1/feedback/skills/registry/health-query", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "health-query"
        assert "current_version" in data

    def test_skill_registry_not_found(self, client, admin_headers):
        """测试不存在的 Skill 返回 404"""
        response = client.get("/api/v1/feedback/skills/registry/nonexistent-skill", headers=admin_headers)
        assert response.status_code == 404

    def test_skill_registry_path_traversal_rejected(self, client, admin_headers):
        """测试路径遍历攻击被拒绝"""
        # 名称中含有点号应被拒绝
        response = client.get("/api/v1/feedback/skills/registry/..config", headers=admin_headers)
        assert response.status_code == 400
        # 空名称（虽然会匹配到 /skills/registry/ 返回 405，换一种方式测试）
        # 使用含特殊字符的名称
        response = client.get("/api/v1/feedback/skills/registry/foo.bar", headers=admin_headers)
        assert response.status_code == 400


# ===== 隐式信号服务测试 =====

class TestImplicitSignals:

    def test_record_implicit_signal(self, db, test_user):
        """测试记录隐式信号"""
        from app.services.feedback_service import feedback_service

        feedback = feedback_service.record_implicit(
            db=db,
            user_id=test_user.id,
            conversation_type="chat",
            conversation_id=1,
            message_id=10,
            skill_used="health-query",
            skill_version="1.0.0",
            success=True,
            response_time_ms=350,
        )
        assert feedback.skill_used == "health-query"
        assert feedback.success is True
        assert feedback.response_time_ms == 350

    def test_record_implicit_then_add_rating(self, db, test_user):
        """测试先记录隐式信号，再补充用户评分"""
        from app.services.feedback_service import feedback_service

        # 先记录隐式信号
        feedback_service.record_implicit(
            db=db,
            user_id=test_user.id,
            conversation_type="chat",
            conversation_id=1,
            message_id=20,
            skill_used="health-query",
            success=True,
        )

        # 再补充评分
        feedback = feedback_service.submit_rating(
            db=db,
            user_id=test_user.id,
            conversation_type="chat",
            conversation_id=1,
            message_id=20,
            rating=5,
        )
        # 同一条记录，skill 信息保留
        assert feedback.rating == 5
        assert feedback.skill_used == "health-query"
        assert feedback.success is True

    def test_response_time_zero_not_dropped(self, db, test_user):
        """测试 response_time_ms=0 不会被忽略"""
        from app.services.feedback_service import feedback_service

        feedback = feedback_service.record_implicit(
            db=db,
            user_id=test_user.id,
            conversation_type="chat",
            conversation_id=1,
            message_id=30,
            response_time_ms=0,
        )
        assert feedback.response_time_ms == 0

    def test_update_implicit_preserves_fields(self, db, test_user):
        """测试更新隐式信号时不覆盖已有字段"""
        from app.services.feedback_service import feedback_service

        # 第一次记录
        feedback_service.record_implicit(
            db=db,
            user_id=test_user.id,
            conversation_type="openclaw",
            conversation_id=5,
            message_id=50,
            skill_used="health-record",
            success=True,
        )

        # 第二次更新（只传 error_type，不应清空 skill_used）
        feedback = feedback_service.record_implicit(
            db=db,
            user_id=test_user.id,
            conversation_type="openclaw",
            conversation_id=5,
            message_id=50,
            error_type="timeout",
        )
        assert feedback.skill_used == "health-record"
        assert feedback.error_type == "timeout"


# ===== 聚合测试 =====

class TestAggregation:

    def test_aggregate_daily_metrics(self, db, test_user):
        """测试每日指标聚合"""
        from app.services.feedback_service import feedback_service

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # 创建一些反馈数据
        for i in range(5):
            fb = InteractionFeedback(
                user_id=test_user.id,
                conversation_type="chat",
                conversation_id=1,
                message_id=i + 1,
                skill_used="health-query",
                skill_version="1.0.0",
                success=i < 4,  # 4 成功 1 失败
                rating=5 if i < 3 else 1,  # 3个👍 2个👎（包括i=3和i=4）
                response_time_ms=100 + i * 50,
                created_at=today + timedelta(hours=i),
            )
            db.add(fb)
        db.commit()

        # 执行聚合
        feedback_service.aggregate_daily_metrics(db, date=today)

        # 验证结果
        metrics = db.query(SkillMetrics).filter(
            SkillMetrics.skill_name == "health-query",
        ).first()
        assert metrics is not None
        assert metrics.total_calls == 5
        assert metrics.success_count == 4
        assert metrics.failure_count == 1
        assert metrics.success_rate == pytest.approx(0.8)
        assert metrics.thumbs_up == 3
        assert metrics.thumbs_down == 2

    def test_aggregate_empty_day(self, db, test_user):
        """测试空数据日的聚合不报错"""
        from app.services.feedback_service import feedback_service
        yesterday = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        # 不应报错
        feedback_service.aggregate_daily_metrics(db, date=yesterday)


# ===== Skill Registry 服务测试 =====

class TestSkillRegistry:

    @pytest.fixture
    def temp_skills_dir(self):
        """创建临时 skill 目录用于测试"""
        tmp = tempfile.mkdtemp()
        skill_dir = Path(tmp) / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\nversion: 1.0.0\ndescription: A test skill\n---\nTest content\n",
            encoding="utf-8",
        )
        yield Path(tmp)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_list_skills(self, temp_skills_dir):
        from app.services.skill_registry import SkillRegistry
        registry = SkillRegistry(temp_skills_dir)
        skills = registry.list_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "test-skill"
        assert skills[0]["current_version"] == "1.0.0"

    def test_get_skill(self, temp_skills_dir):
        from app.services.skill_registry import SkillRegistry
        registry = SkillRegistry(temp_skills_dir)
        info = registry.get_skill("test-skill")
        assert info is not None
        assert info["name"] == "test-skill"

    def test_get_skill_nonexistent(self, temp_skills_dir):
        from app.services.skill_registry import SkillRegistry
        registry = SkillRegistry(temp_skills_dir)
        assert registry.get_skill("nope") is None

    def test_path_traversal_rejected(self, temp_skills_dir):
        from app.services.skill_registry import SkillRegistry
        registry = SkillRegistry(temp_skills_dir)
        with pytest.raises(ValueError, match="非法"):
            registry.get_skill("../../etc")
        with pytest.raises(ValueError, match="非法"):
            registry.get_skill("foo/bar")
        with pytest.raises(ValueError, match="非法"):
            registry.get_skill("")

    def test_save_and_rollback(self, temp_skills_dir):
        from app.services.skill_registry import SkillRegistry
        registry = SkillRegistry(temp_skills_dir)

        # 保存新版本
        result = registry.save_new_version(
            "test-skill",
            "---\nname: test-skill\nversion: 1.0.0\ndescription: Updated\n---\nNew content\n",
            changelog="测试更新",
        )
        assert result["old_version"] == "1.0.0"
        assert result["new_version"] == "1.0.1"
        assert result["status"] == "canary"

        # 验证存档文件存在
        assert (temp_skills_dir / "test-skill" / "SKILL.v1.0.0.md").exists()

        # 当前内容是新版本
        content = registry.get_skill_content("test-skill")
        assert "1.0.1" in content

        # 回滚
        rolled_back = registry.rollback_version("test-skill")
        assert rolled_back == "1.0.0"

        # 验证回滚后的内容
        content = registry.get_skill_content("test-skill")
        assert "Test content" in content

    def test_promote_version(self, temp_skills_dir):
        from app.services.skill_registry import SkillRegistry
        registry = SkillRegistry(temp_skills_dir)

        # 先创建新版本
        registry.save_new_version("test-skill", "---\nname: test-skill\nversion: 1.0.0\n---\nV2\n")

        # 升级为 production
        result = registry.promote_version("test-skill", "1.0.1")
        assert result is True

        # 验证 manifest
        info = registry.get_skill("test-skill")
        versions = info["manifest"]["versions"]
        v101 = next(v for v in versions if v["version"] == "1.0.1")
        assert v101["status"] == "production"

    def test_promote_nonexistent_version(self, temp_skills_dir):
        from app.services.skill_registry import SkillRegistry
        registry = SkillRegistry(temp_skills_dir)
        with pytest.raises(ValueError, match="不存在"):
            registry.promote_version("test-skill", "99.99.99")

    def test_rollback_no_archive(self, temp_skills_dir):
        from app.services.skill_registry import SkillRegistry
        registry = SkillRegistry(temp_skills_dir)
        # 只有一个版本，无法回滚
        result = registry.rollback_version("test-skill")
        assert result is None

    def test_corrupt_manifest_recovery(self, temp_skills_dir):
        """测试损坏的 manifest.json 能自动恢复"""
        from app.services.skill_registry import SkillRegistry
        # 写入损坏的 manifest
        (temp_skills_dir / "test-skill" / "manifest.json").write_text("{invalid json", encoding="utf-8")
        registry = SkillRegistry(temp_skills_dir)
        info = registry.get_skill("test-skill")
        # 应该自动重新初始化
        assert info is not None
        assert info["current_version"] == "1.0.0"
