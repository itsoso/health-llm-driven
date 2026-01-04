"""每日建议数据模型"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class DailyRecommendation(Base):
    """每日健康建议"""
    __tablename__ = "daily_recommendations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recommendation_date = Column(Date, nullable=False, index=True)  # 建议日期（今天）
    analysis_date = Column(Date, nullable=False)  # 分析的数据日期（昨天）
    
    # 1天建议（基于昨天的数据）
    one_day_recommendation = Column(JSON, nullable=True)  # 存储完整的1天建议JSON
    
    # 7天建议（基于最近7天的数据）
    seven_day_recommendation = Column(JSON, nullable=True)  # 存储完整的7天建议JSON
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="daily_recommendations")

