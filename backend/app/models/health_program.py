"""健康项目模型(Reva Personal Health OS · 第 4 个一等对象)。

HealthProgram = 比 Daily Plan 更长期(8–12 周)的目标容器,串起
HealthProblem(管什么病/目标)→ 它管理的 HealthProtocol(怎么做)→ outcome 验证(baseline→latest→target)。

对象层级:HealthProblem → **HealthProgram** → HealthProtocol → HealthAgendaItem。
协议通过 HealthProtocol.program_id 归属本 program(该列已存在)。

详见 docs/prd/reva-personal-health-os-prd.md §4(5 类:代谢/恢复训练/睡眠/用药补剂/检查)。
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


PROGRAM_TYPES = (
    "metabolic", "recovery_training", "sleep", "medication_supplement", "checkup",
)
PROGRAM_STATUS = ("active", "completed", "abandoned")


class HealthProgram(Base):
    """8–12 周健康目标容器。"""
    __tablename__ = "health_programs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(200), nullable=False)
    program_type = Column(String(30), nullable=False)     # PROGRAM_TYPES 之一
    status = Column(String(20), default="active")         # active/completed/abandoned

    problem_id = Column(Integer)                          # 关联 HealthProblem(可空)
    primary_metrics = Column(JSONB)                       # 主指标 code 列表(outcome 验证)
    secondary_metrics = Column(JSONB)
    baseline = Column(JSONB)                              # {metric: value}
    target = Column(JSONB)
    latest = Column(JSONB)

    started_on = Column(Date)
    target_end_on = Column(Date)

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="health_programs")

    __table_args__ = (
        Index("ix_health_programs_user_status", "user_id", "status"),
    )
