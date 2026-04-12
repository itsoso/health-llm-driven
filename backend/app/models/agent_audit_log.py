"""
Agent 审计日志 —— 每次 specialist 运行的可追溯记录。

用户可以查看"系统为什么告诉我这个"。
开发者可以追踪哪条规则在什么数据上触发了什么结论。
"""

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator
import json

from app.database import Base


class JSONColumn(TypeDecorator):
    """JSONB on PostgreSQL, TEXT with JSON serialization on SQLite."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name != "postgresql":
            return json.dumps(value, default=str, ensure_ascii=False)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name != "postgresql" and isinstance(value, str):
            return json.loads(value)
        return value


class AgentAuditLog(Base):
    """一次 agent/specialist 评估的审计记录。"""

    __tablename__ = "agent_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)

    agent_type = Column(String(50), nullable=False, index=True)
    specialist_name = Column(String(80))
    action = Column(String(50), nullable=False)
    query = Column(Text)

    result_summary = Column(Text)
    alerts_count = Column(Integer, default=0)
    findings_count = Column(Integer, default=0)
    result_detail = Column(JSONColumn)

    twin_build_ms = Column(Integer)
    evaluate_ms = Column(Integer)
    total_ms = Column(Integer)

    twin_sources = Column(JSONColumn)
    intent_categories = Column(JSONColumn)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
