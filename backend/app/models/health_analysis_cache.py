"""健康分析缓存数据模型"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class HealthAnalysisCache(Base):
    """健康分析缓存"""
    __tablename__ = "health_analysis_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    analysis_date = Column(Date, nullable=False, index=True)  # 分析日期（今天）
    
    # 分析结果（完整的JSON）
    analysis_result = Column(JSON, nullable=True)
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="health_analysis_cache")

