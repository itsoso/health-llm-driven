"""AI 生成的健康洞察模型（自动化）"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class AIInsight(Base):
    """AI 自动生成的每日健康洞察"""
    __tablename__ = "ai_insights"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    review_date = Column(Date, nullable=False, index=True, comment="复盘日期")

    # 复盘内容
    content = Column(Text, nullable=False, comment="AI 生成的复盘内容")
    summary = Column(String(500), comment="简短摘要")

    # 数据快照
    health_snapshot = Column(JSON, comment="当日健康数据快照")

    # 元数据
    generated_at = Column(DateTime, server_default=func.now(), comment="生成时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AIInsight(user_id={self.user_id}, date={self.review_date})>"


class RealtimeRecommendation(Base):
    """实时健康建议"""
    __tablename__ = "realtime_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 建议内容
    content = Column(Text, nullable=False, comment="AI 生成的建议内容")
    recommendation_type = Column(String(50), comment="建议类型: exercise, diet, rest, alert")
    priority = Column(String(20), comment="优先级: high, medium, low")

    # 上下文信息
    context_data = Column(JSON, comment="生成建议时的上下文数据")

    # 位置和天气
    location = Column(JSON, comment="位置信息 {latitude, longitude, city}")
    weather_data = Column(JSON, comment="天气数据")
    air_quality_data = Column(JSON, comment="空气质量数据")

    # 元数据
    generated_at = Column(DateTime, server_default=func.now(), comment="生成时间")
    expires_at = Column(DateTime, comment="过期时间")
    is_active = Column(Integer, default=1, comment="是否有效")

    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<RealtimeRecommendation(user_id={self.user_id}, type={self.recommendation_type})>"
