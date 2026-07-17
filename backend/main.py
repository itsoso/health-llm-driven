"""主应用入口"""
import logging
import os
import time
import uuid
import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.database import engine, Base
from app.api.main import api_router
from app.scheduler import start_scheduler
from app.utils.logging_config import setup_beijing_logging
from app.config import settings
from app.services.garmin_cffi_patch import patch_garth_with_cffi
import app.models.smart_reminder  # noqa: F401 - ensure table creation
import app.models.interaction_feedback  # noqa: F401 - Agent 反馈系统
import app.models.genetic_data  # noqa: F401 - 基因数据表
import app.models.llm_usage  # noqa: F401 - LLM 用量追踪表
import app.models.open_loop_history  # noqa: F401 - Open-Loop 推送历史 + dedup
import app.models.clinical_journal  # noqa: F401 - Clinical Journal SOAP + case threads
import app.models.user_directive  # noqa: F401 - 医生指令 / 用户硬约束
import app.models.memory_fact  # noqa: F401 - LLM Wiki v2 事实级记忆
import app.models.health_kg  # noqa: F401 - 知识图谱 entities + relations
import app.models.system_knowledge  # noqa: F401 - System LLM Wiki v2 KB docs + graph
import app.models.monthly_report  # noqa: F401 - 月度复盘报告
import app.api.nfc  # noqa: F401 - ensure BowelTimer table creation

logger = logging.getLogger(__name__)
_IS_PRODUCTION = (settings.app_env or "").strip().lower() == "production"

# 设置日志，使用北京时间
setup_beijing_logging()

# Sentry 错误监控（仅当配置了 DSN 才启用，未配置时是 noop）
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # 健康数据合规：不上传 PII（IP / cookie / headers）
        send_default_pii=False,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            CeleryIntegration(),
        ],
        # 把 logging.error 自动转成 Sentry event
        _experiments={"continuous_profiling_auto_start": False},
    )
    logger.info(f"[Sentry] 错误监控已启用，环境={settings.sentry_environment}")

# Patch garth 使用 Chrome TLS 指纹（绕过 Cloudflare bot 检测）
patch_garth_with_cffi()

# 创建数据库表(SKIP_DB_INIT=1 时跳过 —— 供 OpenAPI dump / 纯 import 用,不连 DB,
# 也让 type-drift CI 能在无 DB 的 runner 上 dump app.openapi())
if os.getenv("SKIP_DB_INIT") != "1":
    Base.metadata.create_all(bind=engine)

# 配置请求频率限制器（使用 Redis 存储，支持多实例部署）
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    default_limits=["200/minute"],
)

app = FastAPI(
    title="健康管理系统 API",
    description="""
## 基于 LLM 的个性化健康管理系统

这是一个AI驱动的多平台健康管理平台，集成了Garmin设备数据、体检报告分析、健康建议生成等功能。

### 核心功能
- 🏃 **Garmin 数据同步**: 自动同步运动、睡眠、心率等数据
- 🩺 **体检报告分析**: PDF智能解析与健康风险评估
- 🤖 **AI 健康分析**: 基于 OpenAI GPT-4o-mini 的个性化建议
- 📊 **多维度追踪**: 饮食、运动、补剂、体重等数据记录
- 📱 **多平台支持**: Web、微信小程序、iOS/Android App
- ⚡ **高性能**: Redis 缓存 + 数据库索引优化

### 认证方式
- **Bearer Token (JWT)**: 7天有效期
- **微信小程序 OAuth2**: 自动用户合并

### 限流规则
- 登录: 5次/分钟
- 注册: 3次/小时
- 微信登录: 10次/分钟

### 技术栈
- FastAPI 0.115.0
- PostgreSQL / SQLite
- Redis (缓存层)
- OpenAI GPT-4o-mini
- Celery (异步任务)
    """,
    version="1.0.0",
    # Production does not expose the complete API surface publicly. Local and
    # test environments keep the docs for development ergonomics.
    docs_url=None if _IS_PRODUCTION else "/api/docs",
    redoc_url=None if _IS_PRODUCTION else "/api/redoc",
    openapi_url=None if _IS_PRODUCTION else "/api/openapi.json",
    contact={
        "name": "健康管理系统",
        "url": "https://github.com/yourusername/health-llm-driven",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {"name": "auth", "description": "用户认证与授权"},
        {"name": "wechat", "description": "微信小程序登录"},
        {"name": "users", "description": "用户管理"},
        {"name": "garmin", "description": "Garmin 数据同步"},
        {"name": "health", "description": "健康数据记录"},
        {"name": "recommendation", "description": "AI 健康建议"},
        {"name": "diet", "description": "饮食管理"},
        {"name": "workout", "description": "运动管理"},
        {"name": "admin", "description": "管理员功能"},
    ]
)

# 将限流器添加到应用状态，供路由使用
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 启动后台同步调度器（每天08:01北京时间同步一次，避免频繁登录导致账户锁定）
@app.on_event("startup")
async def startup_event():
    import app.models.family  # noqa: F401 — 确保家庭管理表被创建
    import app.models.family_health  # noqa: F401 — 确保体检报告/用药/复查表被创建
    settings.validate_required_security()
    try:
        from app.database import SessionLocal as _ChatCleanupSession
        from app.services.agent_conversation_service import AgentConversationService

        cleanup_db = _ChatCleanupSession()
        try:
            removed_tombstones = AgentConversationService(
                cleanup_db,
            ).retry_staged_chat_image_deletions()
        finally:
            cleanup_db.close()
        if removed_tombstones:
            logger.info(
                "[startup] retried %s staged private chat image deletions",
                removed_tombstones,
            )
    except Exception:
        logger.error(
            "[startup] private chat image tombstone cleanup failed",
            exc_info=True,
        )
    # 中文分词器启动探针: System KB 检索依赖 jieba(硬依赖)。在启动时一次性 warm
    # (付掉字典构建 + userdict 成本, 而非每次查询), 并在缺失时 fail-loud(ERROR 级),
    # 不静默退化到未分词的坏检索行为。缺失不 crash 启动(检索层会降级到 bigram), 但日志
    # 必须响亮, 让运维立即察觉依赖漏装。
    try:
        import logging as _logging
        from app.services.zh_tokenize import check_zh_tokenizer_available
        check_zh_tokenizer_available()
        _logging.getLogger("main").info("[startup] 中文分词器(jieba)就绪")
    except Exception as _e:  # noqa: BLE001
        import logging as _logging
        _logging.getLogger("main").error(
            f"[startup] 中文分词器(jieba)不可用 —— System KB 中文多词检索将退化到 bigram, "
            f"命中率下降。请安装 jieba==0.42.1。原因: {_e}")
    # 基因租户隔离前置校验: Postgres superuser 会绕过 RLS(含 FORCE)→ genetic_raw_files
    # 行级隔离退化为仅应用层 WHERE。基因是最敏感数据, 启动时 fail-loud 告警(不静默)。
    try:
        import logging as _logging
        from app.database import SessionLocal as _SL
        from sqlalchemy import text as _t
        _db = _SL()
        try:
            if _db.bind is not None and _db.bind.dialect.name == "postgresql":
                _is_super = _db.execute(_t("SELECT current_setting('is_superuser')")).scalar()
                if _is_super == "on":
                    _logging.getLogger("main").error(
                        "[SECURITY] DB 连接角色为 superuser —— Postgres RLS(含 FORCE)被绕过, "
                        "genetic_raw_files 等表的 DB 层租户隔离失效(仅剩应用层 WHERE)。"
                        "生产必须改用非 superuser 角色连接。")
        finally:
            _db.close()
    except Exception as _e:  # noqa: BLE001
        import logging as _logging
        _logging.getLogger("main").warning(f"[startup] RLS superuser 校验跳过: {_e}")
    # 自动迁移：添加新列（PostgreSQL）
    try:
        from app.database import SessionLocal, engine
        from sqlalchemy import text, inspect
        db = SessionLocal()
        insp = inspect(engine)

        def _add_col(table: str, col: str, col_type: str):
            if not insp.has_table(table):
                return
            existing = [c["name"] for c in insp.get_columns(table)]
            if col not in existing:
                db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))

        _add_col("chat_conversations", "mode", "VARCHAR(20) DEFAULT NULL")
        _add_col("garmin_credentials", "sync_in_progress", "BOOLEAN DEFAULT false")
        _add_col("garmin_credentials", "sync_started_at", "TIMESTAMP DEFAULT NULL")
        _add_col("agent_messages", "rating", "INTEGER DEFAULT NULL")
        _add_col("agent_messages", "image_url", "VARCHAR(500) DEFAULT NULL")
        _add_col("users", "is_managed", "BOOLEAN DEFAULT false")
        _add_col("users", "managed_by", "INTEGER DEFAULT NULL")
        # H1-B: 推送规则分级 + 用户偏好
        _add_col("user_notification_settings", "alert_severity_threshold",
                 "VARCHAR(20) DEFAULT 'warning'")
        _add_col("user_notification_settings", "alert_rule_opt_outs",
                 "JSONB DEFAULT '[]'::jsonb")
        _add_col("genetic_variants", "rsid", "VARCHAR(30) DEFAULT NULL")
        _add_col("genetic_variants", "raw_genotype", "VARCHAR(200) DEFAULT NULL")
        _add_col("genetic_variants", "mapping_source", "VARCHAR(50) DEFAULT 'known_snp'")
        _add_col("genetic_variants", "evidence_level", "VARCHAR(50) DEFAULT 'screening'")
        db.commit()
        db.close()
        logger.info("数据库迁移检查完成")
    except Exception as e:
        logger.warning(f"数据库迁移检查跳过: {e}")
    # Scheduler 只在一个 worker 中运行（DB 原子操作竞争 leader）
    import os
    from sqlalchemy import text as sa_text
    worker_pid = str(os.getpid())
    is_leader = False
    try:
        leader_db = SessionLocal()
        # 创建 leader 表（如果不存在）
        leader_db.execute(sa_text(
            "CREATE TABLE IF NOT EXISTS scheduler_leader ("
            "  id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),"
            "  worker_pid VARCHAR(50),"
            "  acquired_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ))
        # 原子性竞争：只有当无 leader 或 leader 已过期（5分钟）时才能获取
        leader_db.execute(sa_text(
            "INSERT INTO scheduler_leader (id, worker_pid, acquired_at) VALUES (1, :pid, NOW()) "
            "ON CONFLICT (id) DO UPDATE SET worker_pid = :pid, acquired_at = NOW() "
            "WHERE scheduler_leader.acquired_at < NOW() - INTERVAL '5 minutes'"
        ), {"pid": worker_pid})
        leader_db.commit()
        # 检查是否真的是自己
        row = leader_db.execute(sa_text("SELECT worker_pid FROM scheduler_leader WHERE id = 1")).fetchone()
        is_leader = row and row[0] == worker_pid
        leader_db.close()
    except Exception as e:
        logger.warning(f"Scheduler leader election failed: {e}")

    if is_leader:
        start_scheduler(app, use_daily_schedule=True)
        logger.info(f"✅ Scheduler leader (PID {worker_pid})")
    else:
        logger.info(f"⏭️ 非 scheduler worker，跳过 (PID {worker_pid})")


# 配置CORS - 严格限制跨域访问
# 如果未配置允许的来源，则拒绝所有跨域请求
cors_origins = settings.cors_allow_origins_list if settings.cors_allow_origins_list else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    # 只允许必要的 HTTP 方法
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    # 只允许必要的请求头
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-API-Key",  # 外部系统 API Key 认证
    ],
    # 浏览器可以访问的响应头
    expose_headers=["X-Response-Time"],
    # 预检请求的缓存时间（秒）
    max_age=600,
)

# 安全响应头中间件
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Web Agent 需要在用户明确操作后使用同源相机/麦克风；跨源页面仍被禁止。
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
        if not request.url.path.startswith("/api/docs"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# 请求超时 + 慢请求日志中间件
REQUEST_TIMEOUT = 60  # 普通请求超时 60 秒（从 120 降低，避免 worker 饥饿）
SLOW_REQUEST_THRESHOLD = 5  # 超过 5 秒记录慢请求警告
# SSE/流式端点不受超时限制
STREAMING_PATHS = {
    "/api/v1/chat/stream",
    "/api/v1/agent/stream",
    "/api/v1/orchestrator/chat/stream",
}
# LLM-bound 长任务端点:单条请求需多次/大输出 LLM 调用,远超 60s 但**非**流式
# (不能进 STREAMING_PATHS 全豁免——全豁免会让真卡死的请求永不超时、饿死 worker)。
# 给单独的更长超时上限,既容下合法长解析、又保留兜底。
# 体检报告 PDF 导入:大报告 LLM 解析 + 服务端分段(CHUNK_CHARS=35000)多次调用,实测 76s+。
# image 走 vision OCR、text 走同一分段解析路径,同样 LLM-bound 可能 >60s。
# csv/json 是确定性解析(快),不进此表。
LONG_REQUEST_PATHS = {
    "/api/v1/medical-exams/import/pdf": 300,
    "/api/v1/medical-exams/import/image": 300,
    "/api/v1/medical-exams/import/text": 300,
}
# /api/v1/agent/send 与 /api/v1/orchestrator/chat 刻意不在上面两表里:深分析回合
# 超过各自快窗(agent.py AGENT_SEND_KEEPALIVE_SECONDS / api/orchestrator.py
# ORCH_CHAT_KEEPALIVE_SECONDS)时自切 chunked keep-alive 流(response start 立即
# 发出,下面的 wait_for 只计到 start),端点内各自带 300s 硬上限兜底。
# 别把它们加进 LONG_REQUEST_PATHS——非流式整段等待会同时撞 nginx、Siri URLSession
# (timeoutInterval=25, idle 语义)与浏览器/urllib 的 idle 超时。


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        path = request.url.path
        method = request.method
        is_streaming = path in STREAMING_PATHS
        req_timeout = LONG_REQUEST_PATHS.get(path, REQUEST_TIMEOUT)

        try:
            if is_streaming:
                response = await call_next(request)
            else:
                response = await asyncio.wait_for(
                    call_next(request),
                    timeout=req_timeout
                )

            duration = time.time() - start_time
            duration_ms = duration * 1000
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"

            # 慢请求日志
            if duration > SLOW_REQUEST_THRESHOLD:
                logger.warning(
                    f"[SLOW] [{request_id}] {method} {path} "
                    f"took {duration_ms:.0f}ms (status={response.status_code})"
                )

            return response

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[TIMEOUT] [{request_id}] {method} {path} "
                f"timed out after {duration_ms:.0f}ms (limit={req_timeout}s)"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "detail": "请求处理超时，请稍后重试",
                    "request_id": request_id,
                },
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"[ERROR] [{request_id}] {method} {path} "
                f"failed after {duration_ms:.0f}ms: {type(e).__name__}: {e}"
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "服务器内部错误，请稍后重试",
                    "request_id": request_id,
                },
            )

app.add_middleware(RequestContextMiddleware)

# 注册路由
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["系统"])
def root():
    """根路径 - API 信息"""
    return {
        "message": "健康管理系统 API",
        "version": "1.0.0",
        "status": "running",
        "docs": {} if _IS_PRODUCTION else {
            "swagger": "/api/docs",
            "redoc": "/api/redoc",
            "openapi_schema": "/api/openapi.json"
        },
        "endpoints": {
            "health_check": "/api/v1/health",
            "user_auth": "/api/v1/auth",
            "wechat_login": "/api/v1/wechat/login"
        }
    }


_CELERY_STATUS_TTL_SEC = 30.0
_celery_status_cache: dict = {"value": "unknown", "ts": 0.0}


def _get_celery_status_cached() -> str:
    """30s 内复用上次结果. inspect(timeout=N) 不管几个 worker 都等满 N 秒,
    放低到 0.3s 就够单 worker 拓扑响应; 真要更深的检查走 /admin/observability/health."""
    import time
    now = time.monotonic()
    if now - _celery_status_cache["ts"] < _CELERY_STATUS_TTL_SEC:
        return _celery_status_cache["value"]
    try:
        from app.celery_app import celery_app
        active = celery_app.control.inspect(timeout=0.3).active()
        status = "connected" if active else "no_workers"
    except Exception as e:
        logger.warning(f"Celery health check failed: {e}")
        status = "error"
    _celery_status_cache["value"] = status
    _celery_status_cache["ts"] = now
    return status


@app.get("/health", tags=["系统"])
@app.get("/api/v1/health", tags=["系统"])
def health_check():
    """健康检查 - 用于监控和负载均衡"""
    from app.utils.redis_cache import get_redis_client
    from app.database import SessionLocal
    from sqlalchemy import text

    overall = "healthy"

    # Redis 检查
    redis_status = "connected"
    try:
        client = get_redis_client()
        if client:
            client.ping()
        else:
            redis_status = "disconnected"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        redis_status = "error"

    # 数据库实际连接检查
    db_status = "connected"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        db_status = "error"
        overall = "degraded"

    # Celery worker 检查 — 带 30s 进程内缓存. 每个 /health 都广播 inspect
    # 会被 timeout 拉满 (broadcast 不知道有几个 worker, 等满 timeout 才返).
    # LB 探活高频, 之前每次扣 2s, p95 直接掉 20 分.
    celery_status = _get_celery_status_cached()

    if redis_status == "error":
        overall = "degraded"

    result = {
        "status": overall,
        "services": {
            "api": "running",
            "database": db_status,
            "redis": redis_status,
            "celery": celery_status,
        }
    }

    if overall != "healthy":
        return JSONResponse(status_code=503, content=result)

    return result
