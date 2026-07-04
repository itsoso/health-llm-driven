"""LLM 调用使用追踪 - 每次 chat 完成后写一条, 用于成本聚合."""
from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base


class LlmUsageLog(Base):
    """每一次 LLM chat 调用的 usage 记录."""
    __tablename__ = "llm_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(32), nullable=False)   # tokenplan / openai / ollama / langbridge-proxy
    model = Column(String(64), nullable=False)
    # 哪个调用方触发: orchestrator / safety_explain / weekly_report / ...
    caller = Column(String(64), nullable=True)
    user_id = Column(Integer, nullable=True)        # 不强制外键, 防 caller 漏传
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    # 单次估算成本 (USD), 由 model 价格表算出
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=True)
    success = Column(Integer, nullable=False, default=1)  # 0/1, 失败也记
    run_id = Column(String(64), nullable=True)
    error_class = Column(String(64), nullable=True)
    error_type = Column(String(64), nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(String(500), nullable=True)
    recovery_action = Column(String(64), nullable=True)
    recovery_model = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('idx_llm_usage_created', 'created_at'),
        Index('idx_llm_usage_user_created', 'user_id', 'created_at'),
        Index('idx_llm_usage_caller', 'caller'),
        Index('idx_llm_usage_run_id', 'run_id'),
    )
