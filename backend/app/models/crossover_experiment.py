"""R16 P4 A·B·A·B 交叉实验模型 —— 把一串 on/off 的 InterventionCycle 相串成一个重复实验。

phases = [{cycle_id, arm, level}] 有序;arm ∈ on/off(干预开/停);level = 该相该指标代表值
(取该 cycle 的 OutcomeMetric.latest_value)。verdict/confidence 由 crossover_verdict 重复感知裁决算出。
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func

from app.database import Base
from app.models.agent_audit_log import JSONColumn


class CrossoverExperiment(Base):
    __tablename__ = "crossover_experiments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    metric_code = Column(String(40), nullable=False)   # canonical biomarker code
    direction = Column(String(8), default="down")      # down(降为好)/up
    status = Column(String(16), nullable=False, default="active")  # active/completed

    phases = Column(JSONColumn)        # [{cycle_id, arm:on/off, level}] 有序
    verdict = Column(String(20))       # replicated/suggestive/not_replicated/insufficient/clinician_review
    confidence = Column(String(12))    # moderate/low/clinician_review

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_crossover_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CrossoverExperiment id={self.id} user={self.user_id} {self.metric_code} {self.verdict}>"
