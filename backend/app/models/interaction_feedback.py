"""交互反馈模型 — OpenClaw Native 自我优化基础设施"""
from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean, ForeignKey, Index
from app.database import Base


class InteractionFeedback(Base):
    """用户对 AI 回复的反馈，用于 Skill 自动优化"""
    __tablename__ = "interaction_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 关联的消息（支持两种对话来源）
    conversation_type = Column(String(20), nullable=False)  # "chat" / "openclaw"
    conversation_id = Column(Integer, nullable=False)
    message_id = Column(Integer, nullable=False)

    # Skill 追踪
    skill_used = Column(String(100), nullable=True)  # 哪个 skill 被调用
    skill_version = Column(String(20), nullable=True)  # skill 版本号

    # 显式反馈
    rating = Column(Integer, nullable=True)  # 1=👎, 5=👍（先只用这两档）
    feedback_text = Column(Text, nullable=True)  # 可选的文字反馈

    # 隐式信号（由后端自动检测）
    implicit_signal = Column(String(50), nullable=True)
    # followup_question=追问（不满意）, thanked=感谢, action_taken=执行了建议

    # 执行结果
    success = Column(Boolean, nullable=True)  # skill 是否成功执行
    error_type = Column(String(50), nullable=True)  # timeout/api_error/hallucination/irrelevant

    # 响应质量指标
    response_time_ms = Column(Integer, nullable=True)  # 响应耗时

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_feedback_skill_version", "skill_used", "skill_version"),
        Index("ix_feedback_created", "created_at"),
        Index(
            "ix_feedback_user_msg_unique",
            "user_id", "conversation_type", "conversation_id", "message_id",
            unique=True,
        ),
    )


class SkillMetrics(Base):
    """Skill 版本性能指标（每日聚合）"""
    __tablename__ = "skill_metrics"

    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(100), nullable=False)
    skill_version = Column(String(20), nullable=False)
    date = Column(DateTime, nullable=False)  # 聚合日期

    # 调用统计
    total_calls = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    success_rate = Column(Float, nullable=True)

    # 评分统计
    rated_count = Column(Integer, default=0)  # 有评分的交互数
    avg_rating = Column(Float, nullable=True)
    thumbs_up = Column(Integer, default=0)
    thumbs_down = Column(Integer, default=0)

    # 响应时间
    avg_response_time_ms = Column(Integer, nullable=True)

    # 版本状态
    is_production = Column(Boolean, default=False)  # 是否为当前生产版本
    is_canary = Column(Boolean, default=False)  # 是否为灰度测试版本

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_skill_metrics_lookup", "skill_name", "skill_version", "date", unique=True),
    )


class SkillOptimizationLog(Base):
    """Skill 优化历史记录"""
    __tablename__ = "skill_optimization_logs"

    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(100), nullable=False)
    old_version = Column(String(20), nullable=False)
    new_version = Column(String(20), nullable=False)

    # 优化原因
    trigger = Column(String(50), nullable=False)  # low_success_rate / low_rating / scheduled
    analysis = Column(Text, nullable=True)  # LLM 分析的根因
    changes_summary = Column(Text, nullable=True)  # 改了什么

    # 优化结果
    status = Column(String(20), nullable=False, default="canary")
    # canary → promoted / rolled_back
    old_success_rate = Column(Float, nullable=True)
    new_success_rate = Column(Float, nullable=True)
    old_avg_rating = Column(Float, nullable=True)
    new_avg_rating = Column(Float, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_opt_log_skill", "skill_name", "created_at"),
    )
