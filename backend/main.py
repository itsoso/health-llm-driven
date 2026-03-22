"""主应用入口"""
import logging
import time
import uuid
import asyncio
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.database import engine, Base
from app.api.main import api_router
from app.scheduler import start_scheduler
from app.utils.logging_config import setup_beijing_logging
from app.config import settings
import app.models.smart_reminder  # noqa: F401 - ensure table creation
import app.models.interaction_feedback  # noqa: F401 - OpenClaw Native 反馈系统

# 设置日志，使用北京时间
setup_beijing_logging()

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 配置请求频率限制器
limiter = Limiter(key_func=get_remote_address)

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
    docs_url="/api/docs",  # Swagger UI 路径
    redoc_url="/api/redoc",  # ReDoc 路径
    openapi_url="/api/openapi.json",  # OpenAPI schema 路径
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
    settings.validate_required_security()
    # 自动迁移：添加新列（如果不存在）
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS mode VARCHAR(20) DEFAULT NULL"))
        db.commit()
        db.close()
        logger.info("数据库迁移检查完成")
    except Exception as e:
        logger.warning(f"数据库迁移检查跳过: {e}")
    start_scheduler(app, use_daily_schedule=True)


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

# 请求超时 + 慢请求日志中间件
REQUEST_TIMEOUT = 120  # 普通请求超时 120 秒
SLOW_REQUEST_THRESHOLD = 10  # 超过 10 秒记录慢请求警告
# SSE/流式端点不受超时限制
STREAMING_PATHS = {
    "/api/v1/openclaw/stream",
    "/api/v1/chat/stream",
    "/api/v1/assistant-openclaw/stream",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        path = request.url.path
        method = request.method
        is_streaming = path in STREAMING_PATHS

        try:
            if is_streaming:
                response = await call_next(request)
            else:
                response = await asyncio.wait_for(
                    call_next(request),
                    timeout=REQUEST_TIMEOUT
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
                f"timed out after {duration_ms:.0f}ms (limit={REQUEST_TIMEOUT}s)"
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
        "docs": {
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

    # Celery worker 检查
    celery_status = "unknown"
    try:
        from app.celery_app import celery_app
        inspector = celery_app.control.inspect(timeout=2)
        active = inspector.active()
        celery_status = "connected" if active else "no_workers"
    except Exception as e:
        logger.warning(f"Celery health check failed: {e}")
        celery_status = "error"

    if redis_status == "error":
        overall = "degraded"

    return {
        "status": overall,
        "services": {
            "api": "running",
            "database": db_status,
            "redis": redis_status,
            "celery": celery_status,
        }
    }
