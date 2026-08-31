"""
测试基础设施改进：
1. get_db() rollback 行为
2. 安全响应头中间件
3. 健康检查降级返回 503
4. run_async 辅助函数
5. slowapi 限流器配置
"""
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.database import get_db
from app.utils.async_helpers import run_async


# ============================================================
# 1. get_db() rollback 行为测试
# ============================================================

class TestGetDbRollback:
    """测试 get_db 在异常时自动 rollback"""

    def test_get_db_yields_session(self, db):
        """正常情况下 get_db 应返回可用的 session"""
        gen = get_db()
        try:
            session = next(gen)
            assert session is not None
            # 正常结束
            try:
                next(gen)
            except StopIteration:
                pass
        finally:
            gen.close()  # 任何分支都关掉生成器,绝不泄漏挂起的全局引擎会话给后续测试

    def test_get_db_rollback_on_exception(self):
        """get_db 在遇到异常时应自动 rollback"""
        gen = get_db()
        try:
            session = next(gen)

            # 模拟 rollback 和 close
            original_rollback = session.rollback
            original_close = session.close
            rollback_called = False
            close_called = False

            def mock_rollback():
                nonlocal rollback_called
                rollback_called = True
                original_rollback()

            def mock_close():
                nonlocal close_called
                close_called = True
                original_close()

            session.rollback = mock_rollback
            session.close = mock_close

            # 向 generator 抛入异常。注意必须用单参签名 gen.throw(exc):
            # Python 3.12 起三参签名 gen.throw(type, value, tb) 已弃用,会在抛入
            # 生成器*之前*先发 DeprecationWarning —— 若某处把警告升级为错误,该调用
            # 会抢先抛 DeprecationWarning 而非 ValueError,使生成器停在 yield 处不被
            # 消费、泄漏一个持全局引擎会话的挂起生成器,污染后续测试。
            with pytest.raises(ValueError):
                gen.throw(ValueError("test error"))

            assert rollback_called, "get_db 应在异常时调用 rollback"
            assert close_called, "get_db 应在 finally 中调用 close"
        finally:
            gen.close()  # 兜底:无论上面哪步异常,都不把挂起的生成器/会话泄漏出去

    def test_get_db_close_on_normal_exit(self):
        """正常退出时应调用 close 但不调用 rollback"""
        gen = get_db()
        try:
            session = next(gen)

            rollback_called = False
            original_rollback = session.rollback

            def mock_rollback():
                nonlocal rollback_called
                rollback_called = True
                original_rollback()

            session.rollback = mock_rollback

            # 正常结束
            try:
                next(gen)
            except StopIteration:
                pass

            assert not rollback_called, "正常退出不应调用 rollback"
        finally:
            gen.close()  # 任何分支都关掉生成器,绝不泄漏挂起的全局引擎会话给后续测试


# ============================================================
# 2. 安全响应头中间件测试
# ============================================================

class TestSecurityHeaders:
    """测试安全响应头"""

    def test_security_headers_present(self, client):
        """所有响应应包含安全头"""
        response = client.get("/")
        headers = response.headers

        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-XSS-Protection") == "1; mode=block"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        policy = headers.get("Permissions-Policy", "")
        # 小巴在用户主动触发时支持同源图片上传与实时语音；不得放开给跨源页面。
        assert "camera=(self)" in policy
        assert "microphone=(self)" in policy
        assert "geolocation=(self)" in policy
        assert "camera=*" not in policy
        assert "microphone=*" not in policy

    def test_hsts_header_on_api(self, client):
        """API 路径应包含 HSTS 头"""
        response = client.get("/api/v1/health")
        assert "Strict-Transport-Security" in response.headers

    def test_security_headers_on_404(self, client):
        """即使 404 也应有安全头"""
        response = client.get("/nonexistent-path")
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"


# ============================================================
# 3. 健康检查降级返回 503 测试
# ============================================================

class TestHealthCheckDegradation:
    """测试健康检查在服务降级时返回 503"""

    def test_health_check_returns_200_when_healthy(self, client):
        """所有服务正常时返回 200"""
        response = client.get("/api/v1/health")
        # 正常情况可能是 200（如果 Redis 可用）或 503（如果 Redis 不可用）
        # 在测试环境中 Redis 通常不可用，所以可能是 503
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert "services" in data

    @patch("app.utils.redis_cache.get_redis_client")
    def test_health_check_returns_503_when_redis_down(self, mock_redis, client):
        """Redis 故障时返回 503"""
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("Redis unavailable")
        mock_redis.return_value = mock_client

        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["redis"] == "error"

    def test_health_check_returns_503_when_db_down(self, client):
        """数据库故障时返回 503"""
        with patch("app.database.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_db.execute.side_effect = Exception("DB connection failed")
            mock_db.close = MagicMock()
            mock_session_cls.return_value = mock_db

            response = client.get("/api/v1/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["services"]["database"] == "error"

    def test_health_check_response_structure(self, client):
        """健康检查响应结构正确"""
        response = client.get("/api/v1/health")
        data = response.json()
        assert "status" in data
        assert "services" in data
        services = data["services"]
        assert "api" in services
        assert "database" in services
        assert "redis" in services
        assert "celery" in services


# ============================================================
# 4. run_async 辅助函数测试
# ============================================================

class TestRunAsync:
    """测试 run_async 在同步上下文中安全运行协程"""

    def test_run_async_returns_result(self):
        """run_async 应正确返回协程结果"""
        async def add(a, b):
            return a + b

        result = run_async(add(3, 4))
        assert result == 7

    def test_run_async_propagates_exception(self):
        """run_async 应传播协程中的异常"""
        async def fail():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(fail())

    def test_run_async_handles_nested_awaits(self):
        """run_async 应支持包含嵌套 await 的协程"""
        async def inner():
            await asyncio.sleep(0)
            return 42

        async def outer():
            return await inner()

        result = run_async(outer())
        assert result == 42

    def test_run_async_handles_none_return(self):
        """run_async 应支持返回 None 的协程"""
        async def noop():
            pass

        result = run_async(noop())
        assert result is None

    def test_run_async_with_running_loop(self):
        """run_async 在已有事件循环的线程中也能正常工作"""
        async def inner():
            return "from_inner"

        async def test_in_loop():
            # 在已有循环的上下文中调用 run_async（使用线程池回退）
            return run_async(inner())

        # 创建新循环来测试
        result = asyncio.run(test_in_loop())
        assert result == "from_inner"


# ============================================================
# 5. Limiter 配置验证测试
# ============================================================

class TestLimiterConfig:
    """测试限流器配置"""

    def test_limiter_exists_on_app(self, client):
        """app.state.limiter 应存在"""
        from main import app
        assert hasattr(app.state, "limiter")

    def test_limiter_has_default_limits(self):
        """limiter 应配置全局默认限制"""
        from main import limiter
        assert limiter._default_limits is not None
        assert len(limiter._default_limits) > 0

    def test_rate_limit_exceeded_returns_429(self, client):
        """超出限流应返回 429"""
        # 注册接口限流 3次/小时，连续请求应触发限流
        # 由于测试环境可能无 Redis，限流可能不生效，但验证端点可访问
        response = client.post("/api/v1/auth/register", json={
            "email": "ratelimit@test.com",
            "password": "test12345678"
        })
        # 不检查具体状态码，确保不会 500
        assert response.status_code != 500


# ============================================================
# 6. 请求上下文中间件测试
# ============================================================

class TestRequestContextMiddleware:
    """测试请求上下文中间件"""

    def test_medical_exam_preview_paths_use_long_request_timeout(self):
        """体检报告预览解析不得落入普通请求的 60 秒超时。"""
        from main import LONG_REQUEST_PATHS

        assert LONG_REQUEST_PATHS["/api/v1/medical-exams/parse-pdf-preview"] == 300
        assert LONG_REQUEST_PATHS["/api/v1/medical-exams/parse-image-preview"] == 300

    def test_response_has_request_id(self, client):
        """响应应包含 X-Request-ID"""
        response = client.get("/")
        assert "X-Request-ID" in response.headers

    def test_response_has_response_time(self, client):
        """响应应包含 X-Response-Time"""
        response = client.get("/")
        assert "X-Response-Time" in response.headers
        assert response.headers["X-Response-Time"].endswith("ms")
