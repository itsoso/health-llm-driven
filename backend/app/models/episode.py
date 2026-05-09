"""Agent-Native v3 — Episode 闭环数据模型.

九对象模型核心 4 表:
- HealthEpisode: 闭环触发事件 (run/sleep/meal/symptom/...). Episode 是 v3 的基本单位.
- EpisodeAction: ActionGraph 的节点 (template_id / evidence_id / time_window / completion_check / risk_condition).
- EpisodeFeedback: followup 回流 (action_done / pain_report / rpe / inline check-in answer).
- EpisodeOutcome: 闭环结果 (完成率 / 生理指标变化 / Reflection 摘要).

Protocol 不入库, 走 YAML registry (backend/protocols/) — 引用通过 protocol_slug + protocol_version 字符串.

JSONColumn 同 agent_audit_log: PostgreSQL 用 JSONB, SQLite 退化 TEXT(JSON).
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Index, Float,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.agent_audit_log import JSONColumn


# ─────────────────────────────────────────────────────────
# 枚举常量 (字符串, 避免 ENUM 类型 + 跨库兼容)
# ─────────────────────────────────────────────────────────

EPISODE_TYPES = {"run", "sleep", "meal", "weight", "symptom", "bp", "glucose", "manual"}

# 风险分层 L0-L4: L0/L1 高 Agent 自主权; L4 熔断 emergency template.
RISK_LEVELS = {"L0", "L1", "L2", "L3", "L4"}

# Episode 生命周期.
EPISODE_STATUS = {"open", "closed", "expired", "escalated"}

# Action 状态.
ACTION_STATUS = {"pending", "done", "skipped", "expired"}


# ─────────────────────────────────────────────────────────
# HealthEpisode
# ─────────────────────────────────────────────────────────

class HealthEpisode(Base):
    """v3 闭环触发事件 — 跑后 / 睡眠 / 偶发症状 等都建一条 Episode."""

    __tablename__ = "health_episodes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    episode_type = Column(String(32), nullable=False, index=True)  # see EPISODE_TYPES
    # source: 哪条记录触发的. workout_records / symptom_entries / sleep_records / manual.
    source_type = Column(String(40))
    source_id = Column(Integer)

    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True))

    status = Column(String(16), nullable=False, default="open")  # see EPISODE_STATUS
    risk_level = Column(String(4), nullable=False, default="L0")  # L0-L4
    risk_flags = Column(JSONColumn)  # ["redflag:chest_pain", "training_overload:acwr_1.6"]

    # 命中的 Protocol (YAML registry 里的 slug + version, 不做外键)
    protocol_slug = Column(String(80), index=True)
    protocol_version = Column(String(20))

    # 触发时刻的快照, 用于 Reflection 时回看
    context_snapshot = Column(JSONColumn)   # weather / aqi / hrv / sleep_prior / acwr / readiness
    baseline_snapshot = Column(JSONColumn)  # 7d avg HR / 7d avg pace / 30d sleep median

    # 教练话 (一句话摘要, 给 mobile UI 直接展示)
    headline = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="health_episodes")
    actions = relationship("EpisodeAction", back_populates="episode", cascade="all, delete-orphan")
    feedbacks = relationship("EpisodeFeedback", back_populates="episode", cascade="all, delete-orphan")
    outcome = relationship("EpisodeOutcome", uselist=False, back_populates="episode", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_episode_user_occurred", "user_id", "occurred_at"),
        Index("idx_episode_user_status", "user_id", "status"),
        Index("idx_episode_user_type", "user_id", "episode_type"),
    )


# ─────────────────────────────────────────────────────────
# EpisodeAction (Action Graph 节点)
# ─────────────────────────────────────────────────────────

class EpisodeAction(Base):
    """ActionGraph 节点 — 一句教练话 + time_window + completion_check + risk_condition."""

    __tablename__ = "episode_actions"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("health_episodes.id"), nullable=False, index=True)

    sequence = Column(Integer, nullable=False, default=0)  # ActionGraph 顺序

    # 用户可见
    title = Column(Text, nullable=False)        # 一句教练话, mobile 直接展示
    body = Column(Text)                         # 可选展开说明
    icon = Column(String(40))                   # ionicon 名 (water/fitness/bed/...)

    # 后端结构 (用户不看)
    action_type = Column(String(40), nullable=False)  # rehydrate/cool_down/protein/rest/check_in/...
    template_id = Column(String(80))                  # protocol 里的 template id
    evidence_id = Column(String(80))                  # 证据引用, audit 用

    # 时间窗
    time_window_start = Column(DateTime(timezone=True))
    time_window_end = Column(DateTime(timezone=True))
    # 备用条件触发表达式 (如 'breathing_calm AND hr_below_baseline+10') — v3 文案规则:
    # 条件触发优于固定分钟. 但要有个能机器解释的占位.
    condition_expr = Column(String(200))

    completion_check = Column(JSONColumn)  # {kind:'self_report'|'metric'|'inline_question', ...}
    risk_condition = Column(JSONColumn)    # 触发降级/熔断的条件

    # 状态
    status = Column(String(16), nullable=False, default="pending")  # see ACTION_STATUS
    completed_at = Column(DateTime(timezone=True))
    skipped_at = Column(DateTime(timezone=True))
    skip_reason = Column(String(40))  # user_skip / expired / replaced_by_replan

    # 推送相关 (Increment 3 用)
    push_sent_at = Column(DateTime(timezone=True))
    push_dedup_key = Column(String(120))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    episode = relationship("HealthEpisode", back_populates="actions")

    __table_args__ = (
        Index("idx_action_episode_seq", "episode_id", "sequence"),
        Index("idx_action_status_window", "status", "time_window_start"),
    )


# ─────────────────────────────────────────────────────────
# EpisodeFeedback
# ─────────────────────────────────────────────────────────

class EpisodeFeedback(Base):
    """followup 回流 — action_done / pain / rpe / inline answer."""

    __tablename__ = "episode_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("health_episodes.id"), nullable=False, index=True)
    action_id = Column(Integer, ForeignKey("episode_actions.id"), index=True)

    kind = Column(String(40), nullable=False)
    # action_done / action_skipped / pain_report / rpe / sleep_quality / inline_answer / replan_request

    payload = Column(JSONColumn)  # {pain_score: 4, body_part: 'knee'} / {rpe: 7} / {answer: '完成'}
    source = Column(String(20), nullable=False, default="mobile")
    # mobile / voice / siri / push_inline

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    episode = relationship("HealthEpisode", back_populates="feedbacks")

    __table_args__ = (
        Index("idx_feedback_episode_created", "episode_id", "created_at"),
    )


# ─────────────────────────────────────────────────────────
# EpisodeOutcome
# ─────────────────────────────────────────────────────────

class EpisodeOutcome(Base):
    """Episode 关闭时计算的结果 — 完成率 / 指标变化 / Reflection 摘要."""

    __tablename__ = "episode_outcomes"

    id = Column(Integer, primary_key=True, index=True)
    episode_id = Column(Integer, ForeignKey("health_episodes.id"), unique=True, nullable=False, index=True)

    actions_total = Column(Integer, nullable=False, default=0)
    actions_done = Column(Integer, nullable=False, default=0)
    actions_skipped = Column(Integer, nullable=False, default=0)
    completion_rate = Column(Float)  # actions_done / actions_total

    # Reflection Worker 写入 (Increment 4)
    metrics_delta = Column(JSONColumn)  # {"hrv_next_morning": 52, "delta_vs_baseline": +5, ...}
    summary = Column(Text)              # 一段中文 Reflection
    notes = Column(JSONColumn)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    episode = relationship("HealthEpisode", back_populates="outcome")
