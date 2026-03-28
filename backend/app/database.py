"""数据库配置"""
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

logger = logging.getLogger(__name__)

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

