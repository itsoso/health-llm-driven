"""医学问题登记模型(Reva Personal Health OS · R13)。

HealthProblem = 用户的医学问题清单(慢病/结节/异常),带风险分层 + 红线阈值 + 负责科室 +
随访 cadence + 升级路径。这是 Health OS 与普通 habit tracker 的分水岭:慢病/结节不是
「每日打卡」,而是「标准化随访 + 红线 + 升级」。

对象层级:HealthProblem(目标/边界) → HealthProgram → HealthProtocol → HealthAgendaItem。
follow_up.next_due 自动投影成议程;红线命中/到期/恶化 → 升级到医生。

定位:系统呈现风险分层 + 随访,**不替代医生诊断、不开方**(详见 docs/prd/reva-personal-health-os-prd.md §4.1)。
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


RISK_LEVELS = ("P0", "P1", "P2")
PROBLEM_STATUS = ("active", "monitoring", "resolved")


class HealthProblem(Base):
    """一条医学问题/慢病/结节的登记。"""
    __tablename__ = "health_problems"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(200), nullable=False)            # "胃溃疡(Hp 阴性,胃窦后壁)"
    risk_level = Column(String(4), default="P1")          # P0/P1/P2(医学优先级,压过抗衰/外观)
    status = Column(String(20), default="active")         # active/monitoring/resolved

    diagnosis = Column(JSONB)                             # {分型, 证据, hp_status, evidence_grade, source_exam}
    risk_stratification = Column(String(60))             # 标准化框架:TI-RADS / Fleischner / NAFLD 分期
    red_lines = Column(JSONB)                             # [{condition, action}] 命中即升级(对接 Safety)
    responsible = Column(String(120))                    # 负责医生/科室
    follow_up = Column(JSONB)                             # {last_checkup, cadence, next_due, what_to_check}
    escalation_path = Column(Text)                        # 异常/到期/恶化 → 谁、做什么
    evidence_tier = Column(String(4))                    # A/B/C/D

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="health_problems")

    __table_args__ = (
        Index("ix_health_problems_user_status", "user_id", "status"),
    )
