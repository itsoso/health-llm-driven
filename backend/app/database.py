"""数据库配置"""
import contextvars
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

logger = logging.getLogger(__name__)

# ── 多租户 RLS 会话注入 ──
# current_tenant_id 由 deps.tenant_scope 在请求生命周期内设置; after_begin 事件把它
# 注入 Postgres 会话变量 app.user_id, RLS policy 据此过滤行 (DB 层强制隔离)。
current_tenant_id: contextvars.ContextVar = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def set_current_tenant(user_id: int):
    """设置当前租户, 返回之前的值供恢复。

    返回 previous value 而非 ContextVar token: FastAPI 同步生成器依赖的 setup 与
    teardown 可能跑在不同的 copied context 里, token 是 context-bound 的, 跨 context
    reset 会抛 'Token was created in a different Context'。改用「存旧值 → finally 写回」
    在任何 context 下都安全。
    """
    previous = current_tenant_id.get()
    current_tenant_id.set(int(user_id))
    return previous


def reset_current_tenant(previous) -> None:
    """把租户上下文恢复到 set_current_tenant 之前的值 (None 或上一个 uid)。"""
    current_tenant_id.set(previous)

# 获取实际数据库URL
database_url = settings.effective_database_url
is_sqlite = "sqlite" in database_url

# 优化数据库连接池配置
connect_args = {"check_same_thread": False} if is_sqlite else {}

# SQLite不支持pool_size和max_overflow
if is_sqlite:
    engine = create_engine(
        database_url,
        connect_args=connect_args,
        echo=False
    )
    logger.info("使用 SQLite 数据库")
else:
    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_size=10,  # 连接池大小
        max_overflow=20,  # 最大溢出连接数
        pool_timeout=30,  # 获取连接超时 30 秒（防止连接池耗尽时无限等待）
        pool_pre_ping=True,  # 连接前ping，确保连接有效
        pool_recycle=3600,  # 1小时后回收连接
        echo=False  # 关闭SQL日志
    )
    logger.info(f"使用 PostgreSQL 数据库: {settings.postgres_host}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


@event.listens_for(Session, "after_begin")
def _set_rls_tenant(session, transaction, connection):
    """每个事务开始时把当前租户写进 Postgres 会话变量, 供 RLS policy 用。

    用 after_begin 而非一次性 SET: SET LOCAL 只在当前事务有效, commit 后失效;
    after_begin 保证每个事务 (含 commit 后开启的新事务) 都重设, 同时避免连接池里
    残留上一个请求的租户值。SQLite 无 RLS, 跳过。漏设时 policy 的 current_setting
    返回 NULL → 0 行 (fail-closed, 全拒而非泄漏)。
    """
    if connection.dialect.name != "postgresql":
        return
    uid = current_tenant_id.get()
    if uid is None:
        return
    # int() 强转防注入 (set_current_tenant 已强转, 此处双保险)。
    connection.exec_driver_sql(f"SET LOCAL app.user_id = '{int(uid)}'")


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
