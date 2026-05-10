"""跑步动态指导会话 (Live Run Coach).

设计要点 (V1, 2026-05-13):
- 一次跑步 = 一条 LiveRunSession 记录
- in-session 触发的规则事件全部存在 events JSON 里 (不另开表, 跑步内事件最多
  几十个, 单个 session 整体读出/写入即可)
- target_pace 跑前由用户选 (轻松/节奏/快) 或基于 specialists 推荐, 落盘以便
  跑后复盘对比
- gps_track 抽样存储, 不是 1Hz 全量 — 每 30s 一个抽样点已经够看路线
- narrative 跑后 LLM 生成, 异步, 失败也不影响 session 写入
"""
from datetime import UTC, datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Text, Index, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class LiveRunSession(Base):
    __tablename__ = "live_run_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 时间窗口
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # 跑前目标 (用户选 or specialist 推荐)
    target_pace_seconds = Column(Integer, nullable=True)   # 目标配速 (秒/公里), 例如 330 = 5:30
    target_label = Column(String, nullable=True)           # easy / tempo / fast / custom
    max_z4_minutes = Column(Integer, nullable=True)        # 今日 Z4+ 累计上限 (recovery_coach 输入)
    readiness_score = Column(Integer, nullable=True)       # 跑前 readiness 快照 0-100

    # 跑
    total_distance_m = Column(Float, default=0.0)          # 米
    total_duration_s = Column(Integer, default=0)          # 秒, 不含暂停
    avg_pace_seconds = Column(Integer, nullable=True)      # 平均配速 (秒/公里)
    avg_hr = Column(Integer, nullable=True)
    max_hr = Column(Integer, nullable=True)
    z4_plus_minutes = Column(Float, default=0.0)           # Z4+ 累计分钟
    calories = Column(Integer, nullable=True)

    # 事件列表: [{ts, rule_id, message, metric_snapshot}]
    events = Column(JSON, default=list)

    # GPS 抽样轨迹: [{ts, lat, lon, pace, hr}], 每 30s 一个点
    gps_samples = Column(JSON, default=list)

    # 跑后 LLM 复盘
    narrative = Column(Text, nullable=True)
    narrative_status = Column(String, default="pending")   # pending / done / failed

    # 元数据
    source = Column(String, default="mobile")              # mobile / siri / watch
    aborted = Column(Boolean, default=False)               # 用户主动放弃 (距离 < 100m)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    user = relationship("User", backref="live_run_sessions")

    __table_args__ = (
        Index('idx_live_run_user_started', 'user_id', 'started_at'),
    )
