"""补剂审计模型 (Supplement Audit)

审计是一份"决策文档"：完整证据链 + 五段式建议（keep/add/upgrade/remove/monitor）。
区别于日度洞察 (AIInsight) 和周报 (HealthReport type=weekly)：
- 生命周期 3-12 个月
- 按事件触发或用户手动生成
- 每条建议可追踪 accept/reject/complete 状态
"""
from sqlalchemy import JSON, Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SupplementAudit(Base):
    """补剂审计主文档"""
    __tablename__ = "supplement_audits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, comment="同 user 下自增版本号")
    triggered_by = Column(String(30), nullable=False, comment="manual|new_exam|new_gene|scheduled|changed_conditions|migration")
    parent_audit_id = Column(Integer, ForeignKey("supplement_audits.id", ondelete="SET NULL"), nullable=True)

    data_period_start = Column(Date)
    data_period_end = Column(Date)
    title = Column(String(200), nullable=False)

    input_snapshot = Column(JSON, nullable=False, default=dict, comment="profile+labs+gene+garmin+meds 快照")
    rationale_markdown = Column(Text, nullable=False, comment="完整 markdown 推理")
    summary = Column(String(500))

    status = Column(String(20), nullable=False, default="active", comment="active|superseded|archived")
    next_review_at = Column(Date, comment="建议下次复查时间")

    generated_by = Column(String(50), default="manual")
    llm_model = Column(String(50))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items = relationship(
        "SupplementAuditItem",
        back_populates="audit",
        cascade="all, delete-orphan",
        order_by="(SupplementAuditItem.action_type, SupplementAuditItem.priority)",
    )

    def __repr__(self):
        return f"<SupplementAudit(user_id={self.user_id}, v={self.version}, status={self.status})>"


class SupplementAuditItem(Base):
    """审计里的单条 action item (可追踪状态)"""
    __tablename__ = "supplement_audit_items"

    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(Integer, ForeignKey("supplement_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    action_type = Column(String(20), nullable=False, comment="keep|add|upgrade|remove|monitor|warning")
    priority = Column(Integer, nullable=False, default=3, comment="1=highest, 5=lowest")
    title = Column(String(200), nullable=False)

    product_id = Column(Integer, ForeignKey("supplement_products.id", ondelete="SET NULL"), nullable=True)
    supplement_definition_id = Column(Integer, ForeignKey("supplement_definitions.id", ondelete="SET NULL"), nullable=True)
    target_metric = Column(String(100), comment="monitor 类型时使用")

    rationale_markdown = Column(Text, nullable=False, comment="单条证据链 markdown")
    evidence_refs = Column(JSON, nullable=False, default=list)
    warnings = Column(JSON, nullable=False, default=list)

    status = Column(String(20), nullable=False, default="pending", comment="pending|accepted|rejected|completed|superseded")
    user_note = Column(Text)
    accepted_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    rejected_reason = Column(String(200))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    audit = relationship("SupplementAudit", back_populates="items")

    def __repr__(self):
        return f"<SupplementAuditItem(id={self.id}, type={self.action_type}, status={self.status})>"
