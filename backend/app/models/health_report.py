"""健康报告数据模型"""
from datetime import UTC, date, datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, Index, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class HealthReport(Base):
    """健康报告"""
    __tablename__ = "health_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 报告类型: weekly / monthly / yearly
    report_type = Column(String(20), nullable=False)

    # 报告覆盖的时间范围
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # 报告标题
    title = Column(String(200), nullable=False)

    # 各维度数据摘要 (JSON)
    exercise_summary = Column(JSON, default=dict)   # 运动数据摘要
    diet_summary = Column(JSON, default=dict)       # 饮食数据摘要
    sleep_summary = Column(JSON, default=dict)      # 睡眠数据摘要
    weight_summary = Column(JSON, default=dict)     # 体重变化摘要
    mood_summary = Column(JSON, default=dict)       # 情绪数据摘要
    checkin_summary = Column(JSON, default=dict)    # 打卡完成摘要
    vital_signs_summary = Column(JSON, default=dict)  # 体征数据摘要 (心率、血压等)

    # AI 生成的综合分析
    ai_analysis = Column(Text, nullable=True)

    # AI 生成的建议
    ai_recommendations = Column(JSON, default=list)

    # 综合健康评分 (0-100)
    health_score = Column(Integer, nullable=True)

    # 与上一期的对比数据
    comparison = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # 关系
    user = relationship("User", backref="health_reports")

    __table_args__ = (
        Index('idx_report_user_type_date', 'user_id', 'report_type', 'start_date'),
        Index('idx_report_user_date', 'user_id', 'start_date', 'end_date'),
    )
