"""TwinSnapshot — 版本化的 Digital Health Twin 快照.

PRD「个人健康操作系统」P1 数据底座 #1 (G1).

Twin 本身是临时构建 (Redis 60s TTL, 用后即弃). 这导致一个核心问题:
**无法回溯"这条计划/报告/建议当时基于什么健康状态"** —— 不可审计、不可复盘。

TwinSnapshot 在生成计划 / 报告 / 干预周期基线时, 持久化一份当时 Twin 的序列化状态,
并被下游对象通过 twin_snapshot_id 引用。content_hash 用于去重 (同一用户短时间内
状态没变就复用同一快照, 不重复落库)。

JSONColumn 同 agent_audit_log: PostgreSQL 用 JSONB, SQLite 退化 TEXT(JSON).
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


# 快照用途 — 谁触发了这次快照 (便于审计 + 检索)
SNAPSHOT_PURPOSES = {
    "manual",          # 手动 / 调试
    "plan",            # 生成周计划 / 日计划时
    "report",          # 生成健康报告时
    "audit",           # agent 评估时
    "cycle_baseline",  # 干预周期基线
    "cycle_latest",    # 干预周期复查
}

# 数据质量分档 (来自 Twin 的 freshness / 来源完整度, 由 snapshot 服务计算)
QUALITY_GRADES = {"A", "B", "C", "D"}


class TwinSnapshot(Base):
    """某一时刻 Digital Health Twin 的不可变快照."""

    __tablename__ = "twin_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    schema_version = Column(String(16), nullable=False, default="1")
    # sha256(twin_json) — 同状态去重; 配合 user_id 检索"最近一次相同状态".
    content_hash = Column(String(64), index=True)

    purpose = Column(String(40), nullable=False, default="manual", index=True)  # see SNAPSHOT_PURPOSES
    quality_grade = Column(String(2))  # A/B/C/D — see QUALITY_GRADES

    # Twin 活跃数据源列表 (twin.meta.data_sources 的拷贝, 便于不解 twin_json 就检索).
    sources = Column(JSONColumn)
    # 序列化的 HealthTwin (pydantic model_dump(mode="json")).
    twin_json = Column(JSONColumn)

    __table_args__ = (
        Index("idx_twin_snapshots_user_created", "user_id", "created_at"),
        Index("idx_twin_snapshots_user_purpose", "user_id", "purpose"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TwinSnapshot id={self.id} user={self.user_id} purpose={self.purpose} grade={self.quality_grade}>"
