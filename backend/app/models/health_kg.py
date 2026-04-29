"""
Health Knowledge Graph — entities + typed relations.

LLM Wiki v2 关键升级: 不只是平铺 facts (memory_facts),
还要建立 typed graph 让 specialist 可以"沿关系遍历":
  "升级降压药" → entity:美托洛尔 → treats → entity:hypertension
                                  → interacts_with → entity:布洛芬 (NSAID)
                                  → 推荐路径: 复查 + 留意 NSAID

设计:
- HealthEntity: 节点, 单 user 内 type+canonical_name 唯一
- EntityRelation: 有向边, (subject, predicate, object) 三元组 + confidence + sources
- alias 列表: 同一 entity 的多种叫法 ('美托洛尔'/'倍他乐克'/'metoprolol')
- 跟 memory_facts 互补: facts 是非结构化"句子", entities 是结构化"节点"
  (一条 fact 可能引用多个 entities; entities 之间的 relation 也是一种 fact)
"""
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer,
    JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

# 跨 PG/SQLite JSON 兼容
JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


# 节点类型 — specialist 抽取时使用
ENTITY_TYPES = {
    "medication",          # 用户在服 / 历史用药
    "symptom",             # 鼻塞 / 头痛 / 失眠
    "lab_value",           # LDL / HbA1c / ALT
    "vital",               # SBP / DBP / HRV
    "condition",           # 高血压 / 鼻炎 / 代谢综合征
    "intervention",        # ActionCard 落地的具体行动 (减重 protocol / 7天 HRV 实验)
    "lifestyle_factor",    # 戒酒 / 低钠 / 早睡
    "gene_variant",        # MTHFR rs1801133 CT
    "supplement",          # 鱼油 / 钙片
    "anatomical_target",   # 肝 / 肾 / 心脏 (drug target / risk organ)
}

# 边类型 — typed predicates
RELATION_TYPES = {
    # 治疗 / 因果
    "treats", "causes", "triggers", "prevents", "worsens", "improves",
    # 相互
    "interacts_with", "contraindicates",
    # 结构
    "depends_on", "is_part_of", "is_a",
    # 用户态
    "owns",                # User → entity (有这种症状 / 在服这种药)
    "has_genotype",        # User → gene_variant (携带该基因型, 终生不衰减)
    "responds_to",         # Patient → intervention (有效)
    "does_not_respond_to", # Patient → intervention (无效)
    "exposed_to",          # Patient → lifestyle_factor / trigger
    # 知识
    "supersedes", "contradicts", "associated_with",
}


class HealthEntity(Base):
    """图节点."""
    __tablename__ = "health_entities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    # 同 user 内同 (type, canonical_name) 唯一
    type = Column(String(40), nullable=False)
    canonical_name = Column(String(200), nullable=False)
    aliases = Column(JSON_TYPE, default=list)  # ['倍他乐克', 'metoprolol', ...]

    attributes = Column(JSON_TYPE, default=dict)  # type-specific 属性
    # 例: medication → {dosage: '25mg', schedule: 'qd'}
    #     lab_value → {latest: 4.2, unit: 'mmol/L', last_measured: '2026-04-15'}
    #     gene_variant → {rs_id: 'rs1801133', genotype: 'CT'}

    confidence = Column(Float, nullable=False, default=0.7)
    # 来源溯源: [{type: 'medical_exam', id: 5}, ...]
    sources = Column(JSON_TYPE, default=list)

    # 软删除/合并支持
    is_active = Column(Boolean, nullable=False, default=True)
    merged_into_id = Column(Integer,
                            ForeignKey("health_entities.id", ondelete="SET NULL"))

    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "type", "canonical_name", name="uq_entity_user_type_name"),
        Index("idx_entity_user_type", "user_id", "type"),
        Index("idx_entity_user_active", "user_id", "is_active"),
    )


class EntityRelation(Base):
    """图边."""
    __tablename__ = "entity_relations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    subject_id = Column(Integer,
                        ForeignKey("health_entities.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    predicate = Column(String(40), nullable=False, index=True)
    object_id = Column(Integer,
                       ForeignKey("health_entities.id", ondelete="CASCADE"),
                       nullable=False, index=True)

    confidence = Column(Float, nullable=False, default=0.5)
    evidence_count = Column(Integer, nullable=False, default=1)
    sources = Column(JSON_TYPE, default=list)

    # 时态
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, nullable=False, default=True)

    notes = Column(Text)

    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "subject_id", "predicate", "object_id",
                        name="uq_relation_triple"),
        Index("idx_relation_user_pred", "user_id", "predicate"),
        Index("idx_relation_subject_pred", "subject_id", "predicate"),
        Index("idx_relation_object_pred", "object_id", "predicate"),
    )

    subject = relationship("HealthEntity", foreign_keys=[subject_id])
    object = relationship("HealthEntity", foreign_keys=[object_id])
