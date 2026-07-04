"""健康趋势预测报告模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Index, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class HealthTrendReport(Base):
    """健康趋势预测报告"""
    __tablename__ = "health_trend_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 报告维度和周期
    report_date = Column(Date, nullable=False, index=True)
    dimension = Column(String(20), nullable=False)  # weight, sleep, exercise, overall
    period = Column(String(10), nullable=False, default="7d")  # 7d, 14d, 30d

    # 趋势结果
    trend_direction = Column(String(20), nullable=True)  # improving, declining, stable
    raw_data_summary = Column(JSON, nullable=True)  # 原始数据摘要
    insights = Column(JSON, nullable=True)  # LLM 洞察列表
    suggestions = Column(JSON, nullable=True)  # LLM 建议列表
    risk_alerts = Column(JSON, nullable=True)  # 风险提醒
    full_report = Column(Text, nullable=True)  # 完整报告文本

    # 多模型分析元数据。物理列名沿用历史字段，避免线上迁移阻断。
    analysis_batch_id = Column("openclaw_batch_id", String(100), nullable=True)
    model_results = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="health_trend_reports")

    __table_args__ = (
        Index('idx_trend_user_date_dim_period', 'user_id', 'report_date', 'dimension', 'period', unique=True),
    )

    def __repr__(self):
        return f"<HealthTrendReport {self.dimension}/{self.period} user={self.user_id} date={self.report_date}>"
