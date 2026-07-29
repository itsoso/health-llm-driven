"""测试配置和fixtures"""
import os
import uuid
import pytest
from datetime import date

os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=")

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.database import Base, get_db


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    """测试库使用 SQLite, 将 PostgreSQL JSONB 降级成 JSON."""
    return "JSON"


from main import app  # noqa: E402 - env vars and JSONB SQLite compiler must be registered first


@pytest.fixture(autouse=True)
def _reset_in_memory_rate_limiters():
    """Prevent one TestClient case from consuming another case's IP quota."""
    from app.api import auth, data_export, speech, wechat, workout

    limiters = (
        auth.limiter,
        data_export.limiter,
        speech.limiter,
        wechat.limiter,
        workout.limiter,
    )
    for limiter in limiters:
        limiter.reset()
    yield
    for limiter in limiters:
        limiter.reset()


@pytest.fixture(autouse=True)
def _isolate_twin_cache():
    """测试隔离:每个测试前后清空 Twin 及派生 Safety 缓存。

    每个测试用全新内存 SQLite,user_id 自增从 1 重启;但 Redis twin 缓存
    (key `twin:v2:{user_id}`) 是进程级全局的,不随测试重置。本地 Redis 存活时,
    上一个测试为 user_id=1 写入的 twin 会污染下一个测试(读到陈旧 twin),
    导致只在本地有 Redis 时才复现的偶发失败(CI 无 Redis service,故被掩盖)。

    派生 Safety 报告同样跨测试持久化,因此同时清理 `safety:v3:*`。不动
    get_redis_client 本身(避免 shadow 掉 test_redis_cache 等直接断言)。
    Redis 不在时 client 为 None,fixture 静默 no-op,与 CI 行为一致。
    """
    def _flush_twin_keys():
        try:
            from app.utils.redis_cache import get_redis_client

            client = get_redis_client()
            if client is None:
                return
            keys = []
            for pattern in ("twin:v2:*", "safety:v3:*"):
                keys.extend(client.scan_iter(match=pattern))
            if keys:
                client.delete(*keys)
        except Exception:
            pass

    _flush_twin_keys()
    yield
    _flush_twin_keys()


@pytest.fixture(autouse=True)
def _noop_twin_cache(monkeypatch):
    """测试隔离(第二层):把 twin 缓存 get/set/invalidate 直接 no-op。

    上面的 `_isolate_twin_cache` 只在用例边界 flush,管不住两类残留:
    (a) 用例内部先请求(缓存了空 twin)、再写数据后重读——命中的还是用例内
    刚缓存的陈旧 twin;(b) 上一用例触发的后台线程在边界 flush 之后才把
    twin 写回 Redis。no-op 让 build_twin(use_cache=True) 在测试内永远
    miss→重建,读端对任何 Redis 残留免疫,且行为与无 Redis 的 CI 完全一致。

    builder/API 都是调用时 `from app.twin.cache import ...`,按模块属性
    解析,patch 模块属性即可生效。保留 `_isolate_twin_cache` 不动:它仍负责
    清掉进程外残留,且 test_safety_failloud_consumers 的注释依赖其语义。
    """
    from app.twin import cache as twin_cache

    monkeypatch.setattr(twin_cache, "get_cached_twin", lambda user_id: None)
    monkeypatch.setattr(
        twin_cache,
        "set_cached_twin",
        lambda user_id, twin_json, ttl=twin_cache.TWIN_CACHE_TTL_SECONDS: False,
    )
    monkeypatch.setattr(twin_cache, "invalidate_twin", lambda user_id: None)


@pytest.fixture(scope="function")
def db():
    """创建测试数据库.

    默认保持现有 SQLite 单测速度; 设置 TEST_DATABASE_URL=postgresql://...test...
    时使用真实 PostgreSQL 语义。Postgres 路径会 drop/create schema, 因此强制库名包含 test。
    """
    import app.models  # noqa: F401 - ensure all model tables/columns are registered before create_all

    test_database_url = os.getenv("TEST_DATABASE_URL")
    if test_database_url:
        url = make_url(test_database_url)
        if url.get_backend_name() != "postgresql" or "test" not in (url.database or ""):
            raise RuntimeError("TEST_DATABASE_URL must point to a PostgreSQL database with 'test' in its name")
        engine = create_engine(test_database_url, pool_pre_ping=True)
    else:
        # 使用 StaticPool 确保所有连接使用同一个内存数据库
        # 使用 check_same_thread=False 允许多线程访问
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )

    # 清除可能存在的元数据缓存
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(scope="function")
def client(db):
    """创建测试客户端"""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_user_data():
    """示例用户数据"""
    return {
        "name": "测试用户",
        "birth_date": "1990-01-01",
        "gender": "男"
    }


def create_authenticated_user(db):
    """创建一个已认证的测试用户，返回 (user, token)"""
    from app.models.user import User
    from app.services.auth import auth_service

    user = User(
        username=f"testuser_{uuid.uuid4().hex[:8]}",
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        name="测试用户",
        birth_date=date(1990, 1, 1),
        gender="男",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, token


def grant_healthkit_consent(db, user, scopes=None):
    """Create the server-side Apple Health connection + self consent used by imports."""
    from app.services.data_connections import create_consent_grant, upsert_data_connection

    hk_scopes = scopes or [
        "healthkit.daily.read",
        "healthkit.ecg.read",
        "healthkit.blood_pressure.read",
        "healthkit.spo2.read",
        "healthkit.body.read",
    ]
    connection = upsert_data_connection(
        db,
        user_id=user.id,
        provider="healthkit",
        provider_type="healthkit",
        display_name="Apple Health",
        scopes=hk_scopes,
        token_status="not_required",
        source_ref="ios-healthkit",
    )
    create_consent_grant(
        db,
        user_id=user.id,
        connection_id=connection.id,
        grantee_type="self",
        grantee_id=str(user.id),
        scopes=hk_scopes,
        purpose="sync HealthKit data into Reva",
    )
    return connection


@pytest.fixture
def auth_user_and_headers(db):
    """创建已认证用户，返回 (user, headers)"""
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


@pytest.fixture
def sample_basic_health_data():
    """示例基础健康数据"""
    return {
        "user_id": 1,
        "height": 175.0,
        "weight": 70.0,
        "bmi": 22.86,
        "systolic_bp": 120,
        "diastolic_bp": 80,
        "total_cholesterol": 5.0,
        "ldl_cholesterol": 3.0,
        "hdl_cholesterol": 1.5,
        "triglycerides": 1.2,
        "blood_glucose": 5.5,
        "record_date": "2024-01-01",
        "notes": "测试数据"
    }


@pytest.fixture
def sample_medical_exam_data():
    """示例体检数据"""
    return {
        "user_id": 1,
        "exam_date": "2024-01-01",
        "exam_type": "blood_routine",
        "body_system": "circulatory",
        "hospital_name": "测试医院",
        "doctor_name": "测试医生",
        "overall_assessment": "总体良好",
        "items": [
            {
                "item_name": "白细胞",
                "value": 6.5,
                "unit": "10^9/L",
                "reference_range": "3.5-9.5",
                "result": "正常",
                "is_abnormal": "normal"
            },
            {
                "item_name": "红细胞",
                "value": 4.5,
                "unit": "10^12/L",
                "reference_range": "4.0-5.5",
                "result": "正常",
                "is_abnormal": "normal"
            }
        ]
    }
