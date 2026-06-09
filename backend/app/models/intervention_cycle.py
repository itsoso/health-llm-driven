"""InterventionCycle / OutcomeMetric — 8–12 周干预闭环 (PRD P2, G4).

把原本散落在 Episode + ActionCard + personal-outcome 的"干预→复查→效果"概念,
收口成一等公民:
- InterventionCycle: 一次代谢干预周期 (基线快照 + 目标指标 + 停止条件 + 复查快照).
- OutcomeMetric: 周期内单个指标的 baseline → latest → delta 追踪.

基线/复查都绑定 TwinSnapshot (G1), 目标指标的 baseline/latest 取自 BiomarkerObservation (G3)。
对应交互稿 ② 90 天干预周期 + ④ 复查对比。
"""
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.agent_audit_log import JSONColumn


CYCLE_STATUS = {"active", "completed", "abandoned"}
# 复元第一阶段默认停止/升级条件 (与 Safety Guardian 监控呼应)
DEFAULT_STOP_CONDITIONS = [
    "肌痛 + 肌酸激酶(CK)升高",
    "转氨酶 > 3×ULN",
    "尿酸性关节痛发作",
]


class InterventionCycle(Base):
    __tablename__ = "intervention_cycles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    cycle_type = Column(String(40), nullable=False, default="metabolic_90d")
    status = Column(String(16), nullable=False, default="active", index=True)  # see CYCLE_STATUS

    start_date = Column(Date, nullable=False)
    planned_end_date = Column(Date)

    baseline_snapshot_id = Column(Integer, ForeignKey("twin_snapshots.id"))
    latest_snapshot_id = Column(Integer, ForeignKey("twin_snapshots.id"))

    # [{code, target, direction}] — 周期目标指标
    target_metrics = Column(JSONColumn)
    # [str] — 停止/升级条件
    stop_conditions = Column(JSONColumn)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    outcomes = relationship("OutcomeMetric", back_populates="cycle", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_intervention_cycles_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InterventionCycle id={self.id} user={self.user_id} {self.cycle_type} {self.status}>"


class OutcomeMetric(Base):
    __tablename__ = "outcome_metrics"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("intervention_cycles.id", ondelete="CASCADE"), nullable=False, index=True)

    metric_code = Column(String(40), nullable=False)   # canonical biomarker code
    unit = Column(String(32))

    baseline_value = Column(Float)
    target_value = Column(Float)
    latest_value = Column(Float)
    delta = Column(Float)
    delta_pct = Column(Float)

    direction = Column(String(8), default="down")       # 期望方向: down(降为好) / up(升为好)
    status = Column(String(12), default="pending")       # pending/improving/worsening/flat/met

    baseline_observed_at = Column(DateTime(timezone=True))
    latest_observed_at = Column(DateTime(timezone=True))

    cycle = relationship("InterventionCycle", back_populates="outcomes")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OutcomeMetric {self.metric_code} {self.baseline_value}->{self.latest_value} {self.status}>"
