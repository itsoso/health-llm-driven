"""健康咨询模型 (Health Consultation)

一等公民的"多层级症状咨询追踪"能力:
- 每次咨询 = 一份决策文档 + 多个 items
- items 分 4 类 (hypothesis/action/prediction/red_flag), 共用一张表, 用 meta JSONB 存多态字段
- predictions 是核心: 带 baseline/target/check_at/data_source, 可自动对比 garmin_data / medical_indicators 做回测

与 SupplementAudit 的区别:
- audits: 补剂方案决策, 五段式 (keep/add/upgrade/remove/monitor)
- consultations: 症状咨询, 四类条目 + 可验证预测
"""
from sqlalchemy import JSON, Boolean, Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class HealthConsultation(Base):
    """健康咨询主文档"""
    __tablename__ = "health_consultations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, comment="同 user 下自增版本号")
    parent_consultation_id = Column(Integer, ForeignKey("health_consultations.id", ondelete="SET NULL"), nullable=True)

    # 基本信息
    title = Column(String(200), nullable=False)
    topic = Column(String(100), comment="例如 口腔溃疡+自主神经失衡")
    consultation_type = Column(String(30), nullable=False, default="symptom_advisory",
                                comment="symptom_advisory|lifestyle_advice|preventive_review|urgent|followup")
    triggered_by = Column(String(30), nullable=False, default="manual",
                          comment="manual|new_symptom|scheduled|linked_event|followup")

    chief_complaint = Column(Text, comment="主诉")
    input_snapshot = Column(JSON, nullable=False, default=dict, comment="咨询时的健康数据快照")
    rationale_markdown = Column(Text, nullable=False, comment="完整对话 markdown")
    summary = Column(String(500))

    # 生命周期
    status = Column(String(20), nullable=False, default="active",
                    comment="active|superseded|verified|archived")
    verification_scheduled_at = Column(Date, comment="下次自动复盘时间")
    verified_at = Column(DateTime(timezone=True))

    # 来源
    generated_by = Column(String(50), default="manual", comment="manual|claude-code|llm-auto")
    llm_model = Column(String(50))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items = relationship(
        "ConsultationItem",
        back_populates="consultation",
        cascade="all, delete-orphan",
        order_by="(ConsultationItem.item_type, ConsultationItem.priority)",
    )

    def __repr__(self):
        return f"<HealthConsultation(user_id={self.user_id}, v={self.version}, topic={self.topic})>"


class ConsultationItem(Base):
    """咨询里的单条条目 (假设/行动/预测/警戒 共表)"""
    __tablename__ = "consultation_items"

    id = Column(Integer, primary_key=True, index=True)
    consultation_id = Column(Integer, ForeignKey("health_consultations.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # 核心分类
    item_type = Column(String(20), nullable=False,
                        comment="hypothesis|action|prediction|red_flag|note")
    item_code = Column(String(20), comment="H1/A1/P1/R1 - 便于 LLM 引用")
    priority = Column(Integer, nullable=False, default=3, comment="1=最高, 5=最低")

    # 内容
    title = Column(String(300), nullable=False)
    content_markdown = Column(Text)

    # 多态元数据 (不同 item_type 塞不同结构, 参考 migration 注释)
    meta = Column(JSON, nullable=False, default=dict)

    # 状态机
    status = Column(String(20), nullable=False, default="pending")

    due_date = Column(Date, comment="行动项截止 / 预测检查日")
    user_note = Column(Text)
    outcome = Column(Text, comment="验证结果描述")
    actual_value = Column(String(200), comment="prediction 的实际值 (结构化)")

    verified_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    consultation = relationship("HealthConsultation", back_populates="items")

    def __repr__(self):
        return f"<ConsultationItem(id={self.id}, type={self.item_type}, code={self.item_code}, status={self.status})>"
