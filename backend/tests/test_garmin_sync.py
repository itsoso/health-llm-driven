"""Garmin 同步相关测试

由于 Celery 不在测试环境中安装，这里通过以下方式测试：
1. 直接测试 sync 函数的内部逻辑（mock Celery 和外部依赖）
2. 代码审查类测试（检查源码中的关键模式）
3. 端点集成测试（garmin_connect 端点已移除）
"""
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime, timedelta

import pytest
from starlette.requests import Request

from app.models.user import User


def _create_garmin_credential(db, user_id=1, sync_enabled=True, credentials_valid=True):
    """创建测试用 GarminCredential"""
    from app.models.user import User, GarminCredential
    from app.services.auth import garmin_credential_service

    # 创建用户（如果不存在）
    existing = db.query(User).filter(User.id == user_id).first()
    if not existing:
        user = User(id=user_id, name=f"测试用户{user_id}")
        db.add(user)
        db.commit()

    encrypted_pw = garmin_credential_service.encrypt_password("test_password")
    credential = GarminCredential(
        user_id=user_id,
        garmin_email=f"user{user_id}@garmin.com",
        encrypted_password=encrypted_pw,
        sync_enabled=sync_enabled,
        credentials_valid=credentials_valid,
    )
    db.add(credential)
    db.commit()
    return credential


# ============================================================
# 代码审查类测试：验证关键修复在源码中生效
# ============================================================

class TestCeleryTaskCodeReview:
    """通过检查源码验证 Celery 任务中的关键修复"""

    def test_no_sync_all_data_call(self):
        """验证 garmin_sync.py 中不再调用不存在的 sync_all_data 方法"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "garmin_sync_source",
            "app/tasks/garmin_sync.py"
        )
        with open("app/tasks/garmin_sync.py", "r") as f:
            source = f.read()

        assert "sync_all_data" not in source, \
            "garmin_sync.py 不应再调用不存在的 sync_all_data 方法"

    def test_uses_sync_date_range(self):
        """验证使用 sync_date_range 替代 sync_all_data"""
        with open("app/tasks/garmin_sync.py", "r") as f:
            source = f.read()

        assert "sync_date_range" in source, \
            "garmin_sync.py 应使用 sync_date_range 方法"

    def test_uses_garmin_credential_model(self):
        """验证使用 GarminCredential 而非旧的 DeviceCredential"""
        with open("app/tasks/garmin_sync.py", "r") as f:
            source = f.read()

        assert "GarminCredential" in source, \
            "应使用 GarminCredential 模型"
        assert "DeviceCredential" not in source, \
            "不应再使用旧的 DeviceCredential 模型"

    def test_syncs_workout_activities(self):
        """验证 Celery 任务包含运动数据同步"""
        with open("app/tasks/garmin_sync.py", "r") as f:
            source = f.read()

        assert "WorkoutSyncService" in source, \
            "应包含 WorkoutSyncService 运动同步"
        assert "sync_activities" in source, \
            "应调用 sync_activities 方法"

    def test_reuses_client_for_workout_sync(self):
        """验证运动同步复用已认证的 client"""
        with open("app/tasks/garmin_sync.py", "r") as f:
            source = f.read()

        assert "client=workout_client" in source or "client=service.client" in source, \
            "WorkoutSyncService 应传入已认证的 client"

    def test_checks_sync_enabled(self):
        """验证 sync_all_users_garmin 只查询 sync_enabled=True 的用户"""
        with open("app/tasks/garmin_sync.py", "r") as f:
            source = f.read()

        assert "sync_enabled == True" in source, \
            "应只查询 sync_enabled=True 的凭据"
        assert "credential_can_sync" in source, \
            "原生 token 有效时不应被历史 credentials_valid 状态拦截"

    def test_runtime_has_no_legacy_garth_or_cffi_authentication(self):
        """0.3.6 的所有运行时入口必须收敛到原生认证。"""
        from pathlib import Path

        backend_root = Path(__file__).resolve().parents[1]
        sources = {
            "garmin_connect": (backend_root / "app/services/data_collection/garmin_connect.py").read_text(),
            "workout_sync": (backend_root / "app/services/workout_sync.py").read_text(),
            "garmin_task": (backend_root / "app/tasks/garmin_sync.py").read_text(),
            "main": (backend_root / "main.py").read_text(),
            "celery": (backend_root / "app/celery_app.py").read_text(),
        }

        for name, source in sources.items():
            assert "client.garth" not in source, f"{name} still dereferences removed client.garth"
            assert "self.client.garth" not in source, f"{name} still dereferences removed self.client.garth"
            assert "import garth" not in source, f"{name} still imports legacy garth"
            assert "garmin_cffi_login" not in source, f"{name} still uses legacy cffi login"
            assert "patch_garth_with_cffi" not in source, f"{name} still patches garth"

        assert not (backend_root / "app/services/garmin_cffi_patch.py").exists()
        assert not (backend_root / "app/services/garmin_cffi_login.py").exists()
        assert not (backend_root / "scripts/garmin_cffi_login.py").exists()
        assert not (backend_root / "scripts/garmin_inject_session.py").exists()
        assert not (backend_root / "scripts/garmin_browser_inject.py").exists()
        assert not (backend_root / "scripts/garmin_playwright_sync.py").exists()

    def test_scheduler_native_token_bypass_does_not_require_synthetic_expiry(self):
        with open("app/scheduler.py", "r") as f:
            source = f.read()

        assert "has_native_token_store(cred.garth_session)" in source
        assert "cred.garth_session and cred.session_expires_at" not in source


class TestSyncStreamCodeReview:
    """验证 sync-stream 端点不再双重登录"""

    def test_delegates_to_shared_scheduler_truth_path(self):
        """Web stream 应复用与 Mobile 相同的同步真值路径。"""
        with open("app/api/auth.py", "r") as f:
            source = f.read()

        assert "await sync_user_garmin_data(" in source
        assert "test_connection_with_mfa()" not in source


@pytest.mark.asyncio
async def test_sync_stream_operational_failure_never_completes_or_refreshes_status(
    db,
    monkeypatch,
) -> None:
    from app import scheduler
    from app.api import auth as auth_api

    credential = _create_garmin_credential(db, user_id=1)
    user = db.query(User).filter_by(id=1).one()
    old_last_sync = datetime.now(UTC) - timedelta(days=1)
    credential.last_sync_at = old_last_sync
    db.commit()
    scheduler_calls = []

    async def fake_scheduler(*args, **kwargs):
        scheduler_calls.append((args, kwargs))
        return {
            "success": False,
            "skipped": False,
            "requires_mfa": False,
            "is_auth_error": False,
            "error_count": 1,
            "message": "Garmin 服务暂时不可用，请稍后再试",
        }

    monkeypatch.setattr(scheduler, "sync_user_garmin_data", fake_scheduler)

    response = await auth_api.sync_garmin_data_stream(
        Request({
            "type": "http",
            "method": "GET",
            "path": "/auth/garmin/sync-stream",
            "client": ("127.0.0.1", 12345),
            "headers": [],
        }),
        days=1,
        current_user=user,
        db=db,
    )
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    body = "".join(chunks)

    db.refresh(credential)
    persisted_last_sync = credential.last_sync_at
    if persisted_last_sync and persisted_last_sync.tzinfo is None:
        persisted_last_sync = persisted_last_sync.replace(tzinfo=UTC)
    assert len(scheduler_calls) == 1
    assert '"type": "error"' in body
    assert '"type": "complete"' not in body
    assert persisted_last_sync == old_last_sync


@pytest.mark.asyncio
async def test_sync_stream_mfa_session_is_returned_but_never_logged(
    db,
    monkeypatch,
    caplog,
) -> None:
    from app import scheduler
    from app.api import auth as auth_api

    _create_garmin_credential(db, user_id=1)
    user = db.query(User).filter_by(id=1).one()
    secret_session_id = "mfa-session-secret"

    async def fake_scheduler(*_args, **_kwargs):
        return {
            "success": False,
            "skipped": False,
            "requires_mfa": True,
            "is_auth_error": False,
            "mfa_session_id": secret_session_id,
            "message": "需要两步验证",
        }

    monkeypatch.setattr(scheduler, "sync_user_garmin_data", fake_scheduler)

    response = await auth_api.sync_garmin_data_stream(
        Request({
            "type": "http",
            "method": "GET",
            "path": "/auth/garmin/sync-stream",
            "client": ("127.0.0.1", 12345),
            "headers": [],
        }),
        days=1,
        current_user=user,
        db=db,
    )
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    body = "".join(chunks)

    assert secret_session_id in body
    assert secret_session_id not in caplog.text


def test_celery_workout_failure_retries_instead_of_marking_success(
    db,
    monkeypatch,
) -> None:
    from app.services import anomaly_detection_service, auth as auth_service_module, workout_sync
    from app.services.data_collection import garmin_connect
    from app.tasks import garmin_sync as garmin_task
    from app.tasks import notifications
    from app.twin import builder as twin_builder

    credential = _create_garmin_credential(db, user_id=1)
    status_updates = []

    class DbContext(AbstractContextManager):
        def __enter__(self):
            return db

        def __exit__(self, *_args):
            return False

    class FakeGarminService:
        def __init__(self, *_args, **_kwargs) -> None:
            self.client = object()
            self._authenticated = True

        def sync_date_range(self, *_args, **_kwargs):
            return {"success_count": 1, "error_count": 0, "no_data_count": 0}

    class FailingWorkoutService:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def sync_activities(self, *_args, **_kwargs):
            raise RuntimeError("workout service unavailable")

    class RetryScheduled(Exception):
        pass

    def schedule_retry(*, exc, countdown):
        raise RetryScheduled(f"{type(exc).__name__}:{countdown}")

    monkeypatch.setattr(garmin_task, "SessionLocal", lambda: DbContext())
    monkeypatch.setattr(garmin_connect, "GarminConnectService", FakeGarminService)
    monkeypatch.setattr(workout_sync, "WorkoutSyncService", FailingWorkoutService)
    monkeypatch.setattr(
        auth_service_module.garmin_credential_service,
        "update_sync_status",
        lambda *_args, **_kwargs: status_updates.append(True),
    )
    monkeypatch.setattr(
        anomaly_detection_service.AnomalyDetectionService,
        "detect_anomalies",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(twin_builder, "build_twin", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notifications.regenerate_briefing_for_user, "delay", lambda *_args: None)
    monkeypatch.setattr(garmin_task.sync_user_garmin_data, "retry", schedule_retry)

    with pytest.raises(RetryScheduled, match="GarminSyncError"):
        garmin_task.sync_user_garmin_data.run(credential.user_id, days=1)

    assert status_updates == []


class TestCeleryBeatScheduleReview:
    """验证 Celery beat 包含 Garmin 4小时同步调度"""

    def test_garmin_beat_enabled_4hourly(self):
        """验证 Celery beat 中有 Garmin 4小时同步任务"""
        from app.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        garmin_tasks = [k for k, v in schedule.items() if "sync_all_users_garmin" in v.get("task", "")]
        assert len(garmin_tasks) >= 1, "Celery beat 中应有 Garmin 同步调度"


# ============================================================
# Scheduler 逻辑测试（不依赖 Celery）
# ============================================================

class TestSchedulerWorkoutSync:
    """验证 scheduler.py 中运动同步复用 client"""

    def test_scheduler_passes_client_to_workout_sync(self):
        """验证 scheduler 的 sync_user_garmin_data 传入已认证的 client"""
        with open("app/scheduler.py", "r") as f:
            source = f.read()

        # 验证有 client= 参数传递
        assert "client=workout_client" in source, \
            "scheduler 应将 service.client 传给 WorkoutSyncService"


# ============================================================
# API 端点集成测试
# ============================================================

class TestLegacyEndpointsRemoved:
    """测试废弃的 garmin_connect 端点已移除"""

    def test_garmin_connect_login_not_registered(self, client):
        """验证 /garmin-connect/connect/login 路由已不再注册"""
        response = client.post("/api/v1/garmin-connect/connect/login", json={
            "email": "test@test.com",
            "password": "test"
        })
        assert response.status_code == 404

    def test_garmin_connect_sync_not_registered(self, client):
        """验证 /garmin-connect/connect/sync 路由已不再注册"""
        response = client.post("/api/v1/garmin-connect/connect/sync", json={
            "user_id": 1,
            "target_date": "2026-01-01",
            "email": "test@test.com",
            "password": "test"
        })
        assert response.status_code == 404

    def test_garmin_connect_sync_today_not_registered(self, client):
        """验证 /garmin-connect/connect/sync-today 路由已不再注册"""
        response = client.post("/api/v1/garmin-connect/connect/sync-today?user_id=1", json={
            "email": "test@test.com",
            "password": "test"
        })
        assert response.status_code == 404


class TestGarminSyncResponseSchema:
    """测试 GarminSyncResponse 包含运动同步字段"""

    def test_response_has_activities_count(self):
        """验证响应模型包含 activities_count 字段"""
        from app.schemas.auth import GarminSyncResponse

        resp = GarminSyncResponse(
            success=True,
            message="test",
            synced_days=1,
            activities_count=3
        )
        assert resp.activities_count == 3

    def test_response_has_activities_error(self):
        """验证响应模型包含 activities_error 字段"""
        from app.schemas.auth import GarminSyncResponse

        resp = GarminSyncResponse(
            success=True,
            message="test",
            synced_days=1,
            activities_error="429 Too Many Requests"
        )
        assert resp.activities_error == "429 Too Many Requests"

    def test_response_defaults(self):
        """验证默认值"""
        from app.schemas.auth import GarminSyncResponse

        resp = GarminSyncResponse(success=True, message="ok")
        assert resp.synced_days == 0
        assert resp.failed_days == 0
        assert resp.activities_count == 0
        assert resp.activities_error is None


# ============================================================
# GarminCredential 数据库测试
# ============================================================

class TestGarminCredentialFiltering:
    """测试 GarminCredential 查询逻辑"""

    def test_only_active_valid_credentials_returned(self, db):
        """验证只返回 sync_enabled=True 且 credentials_valid=True 的凭据"""
        from app.models.user import GarminCredential

        # 创建不同状态的凭据
        _create_garmin_credential(db, user_id=1, sync_enabled=True, credentials_valid=True)   # 应返回
        _create_garmin_credential(db, user_id=2, sync_enabled=False, credentials_valid=True)  # 不返回
        _create_garmin_credential(db, user_id=3, sync_enabled=True, credentials_valid=False)  # 不返回

        active = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True
        ).all()

        assert len(active) == 1
        assert active[0].user_id == 1

    def test_password_encryption_roundtrip(self, db):
        """验证密码加密解密正确"""
        from app.services.auth import garmin_credential_service

        credential = _create_garmin_credential(db, user_id=1)
        decrypted = garmin_credential_service.decrypt_password(credential.encrypted_password)
        assert decrypted == "test_password"
