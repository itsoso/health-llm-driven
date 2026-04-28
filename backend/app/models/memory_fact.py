"""
Memory Fact — LLM Wiki v2 风格的"事实级"记忆.

设计理念 (参考 https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2):
- Working memory:    刚出现的观察, 未压缩
- Episodic memory:   单次 session 摘要 (我们的 clinical_journal_entries 已是)
- Semantic memory:   跨 session 事实 (本表)
- Procedural memory: 反复有效的模式

confidence + supersession + 遗忘曲线让 wiki "活起来" — 不再是静态笔记,
而是会自我修正的知识库.

字段约定:
- (subject, predicate, object_value) 三元组表达一个 atom 事实
  例: ("用户的 LDL", "is_above", "3.4 mmol/L")
       ("用户体重", "exceeds_target", "5kg")
       ("用户对鱼油", "shows_response", "ALT 30 天后下降 8%")
- confidence ∈ [0, 1], 默认 0.5
- 每次新源支持 → reinforce_fact() 提升 confidence + last_reinforced_at
- decay_rate × days_since_last_reinforced 自动衰减
- supersedes_id: 旧事实被覆盖时, 链式版本控制
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

# 跨 PG/SQLite 的 JSON 类型: prod 用 JSONB, 测试用 JSON
JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")

from app.database import Base


class MemoryFact(Base):
    """单条事实级记忆."""
    __tablename__ = "memory_facts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    # 记忆层级
    tier = Column(String(20), nullable=False, index=True)
    # 'working' / 'episodic' / 'semantic' / 'procedural'

    # 事实三元组 (LLM extraction 产物)
    subject = Column(String(200), nullable=False)
    predicate = Column(String(80), nullable=False, index=True)
    # 标准 predicates (会随使用扩展):
    #   is_value / is_above / is_below / equals
    #   causes / treats / contradicts / interacts_with
    #   improves / worsens / triggers
    #   has_history / takes_medication / has_genotype
    #   responds_to / does_not_respond_to
    object_value = Column(Text, nullable=False)
    object_unit = Column(String(20))  # 'mmol/L' / 'mmHg' / 'days' / ...

    # === Lifecycle ===
    confidence = Column(Float, nullable=False, default=0.5)
    # sources: list of {type, id, weight, ingested_at}
    # type: 'medical_exam' / 'soap_entry' / 'action_card_outcome' /
    #       'user_directive' / 'manual' / 'specialist_finding'
    sources = Column(JSON_TYPE, nullable=False, default=list)

    last_reinforced_at = Column(DateTime(timezone=True),
                                server_default=func.now(), nullable=False)
    reinforcement_count = Column(Integer, nullable=False, default=1)
    # decay_rate per day. 0=永不衰减 (架构事实/家族史), 0.01=慢 (慢病诊断), 0.05=中, 0.1=快 (临时观察)
    decay_rate = Column(Float, nullable=False, default=0.02)

    # === Supersession ===
    supersedes_id = Column(Integer, ForeignKey("memory_facts.id", ondelete="SET NULL"))
    superseded_by_id = Column(Integer, ForeignKey("memory_facts.id", ondelete="SET NULL"))
    superseded_at = Column(DateTime(timezone=True))

    # === 隐私 / 权限 ===
    is_private = Column(Boolean, nullable=False, default=True)
    is_sensitive = Column(Boolean, nullable=False, default=False)
    # is_sensitive: PII / 用药 / 基因 — 上传 Sentry / 第三方时必须屏蔽

    # === Free-form 标注 ===
    tags = Column(JSON_TYPE, default=list)
    # ["liver", "cardiovascular", "rhinitis"] 等主题标签 — 与 case_thread.theme 同步

    # === 时间戳 ===
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    # 自引用
    supersedes = relationship(
        "MemoryFact", remote_side=[id], foreign_keys=[supersedes_id],
        post_update=True,
    )

    __table_args__ = (
        Index("idx_memory_user_tier", "user_id", "tier"),
        Index("idx_memory_user_predicate", "user_id", "predicate"),
        Index("idx_memory_active", "user_id", "superseded_at",
              postgresql_where=Column("superseded_at").is_(None)),
        Index("idx_memory_reinforced", "user_id", "last_reinforced_at"),
    )

    @property
    def is_active(self) -> bool:
        return self.superseded_at is None

    @property
    def effective_confidence(self) -> float:
        """考虑遗忘曲线后的当前 confidence (Ebbinghaus 简化)."""
        if self.decay_rate <= 0:
            return self.confidence
        # SQLite 测试 DB 不保留 tz info → naive; PG 是 aware. 都标 UTC.
        ref = self.last_reinforced_at
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - ref).total_seconds() / 86400
        # confidence_t = confidence_0 × exp(-decay_rate × days)
        # floor: reinforcement_count 越高, floor 越高 (反复见过的事实不容易完全遗忘)
        import math
        decayed = self.confidence * math.exp(-self.decay_rate * days)
        floor = min(0.4, 0.05 * self.reinforcement_count)
        return max(decayed, floor)
