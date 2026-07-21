"""Write 层 v0 — 写意图账本(Health OS 的 syscall 雏形)。

见 docs/design/health-os/architecture-lens.md「唯一真缺 = Write 层」。

Agent/确定性规则提出「该替你写一件事」→ 落本表(pending)→ 用户一键确认才执行。
- v0 全部 `trust_tier="manual_confirm"`:**不自治写**,先攒信任(冷启动先验先于 Write)。
- 未来按 R16 外环 CI 收敛逐类升级到 auto(留 trust_tier 字段,本期不放开)。
- 执行是**良性写**:v0 只「复查到点 → 提议建提醒」(SmartReminder),不改药/不开方,医疗低风险。
- 安全:user_id 一律取自 token;确认按 (id,user_id,status=pending) 原子门,防双击双执行。
"""
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)

from app.database import Base


class WriteIntent(Base):
    __tablename__ = "write_intents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    kind = Column(String(40), nullable=False)          # checkup_reminder / ...
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # pending → executed / dismissed / failed
    status = Column(String(20), nullable=False, default="pending", index=True)
    # Logical terminal outcome. Medication expiry is stored physically as
    # dismissed (so stale authorizations cannot execute) but remains
    # distinguishable from an explicit user dismissal across crash recovery.
    decision_status = Column(String(20), nullable=True)
    source = Column(String(50), nullable=True)         # 谁提议: followup_recall / ...
    trust_tier = Column(String(20), nullable=False, default="manual_confirm")  # v0 恒 manual_confirm

    # 关联对象(可追溯 + 幂等去重:同 user+kind+target 已有 pending 不重复提)
    target_type = Column(String(40), nullable=True)    # health_problem / ...
    target_id = Column(Integer, nullable=True)

    payload = Column(JSON, nullable=True)              # 执行参数(remind_at / what_to_check / next_due)
    # 批次执行引用可包含最多 8 个 PostgreSQL INTEGER id（最坏 103 字符）。
    executed_ref = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_write_intents_user_status", "user_id", "status"),
        Index(
            "uq_write_intents_medication_batch_source",
            "user_id",
            "kind",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text(
                "kind = 'medication_intake_batch' AND target_type = 'agent_message'"
            ),
            sqlite_where=text(
                "kind = 'medication_intake_batch' AND target_type = 'agent_message'"
            ),
        ),
    )
