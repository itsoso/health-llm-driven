"""用户模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """用户基础信息"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 认证信息
    email = Column(String, unique=True, index=True, nullable=True)  # 登录邮箱
    username = Column(String, unique=True, index=True, nullable=True)  # 用户名
    hashed_password = Column(String, nullable=True)  # 加密后的密码
    is_active = Column(Boolean, default=True)  # 账户是否激活
    
    # 基础信息
    name = Column(String, nullable=False)
    birth_date = Column(Date, nullable=True)  # 用于计算年龄
    gender = Column(String, nullable=True)  # 男/女
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    daily_recommendations = relationship("DailyRecommendation", back_populates="user")
    health_analysis_cache = relationship("HealthAnalysisCache", back_populates="user")
    garmin_credentials = relationship("GarminCredential", back_populates="user", uselist=False)


class GarminCredential(Base):
    """用户Garmin凭证（加密存储）"""
    __tablename__ = "garmin_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Garmin登录凭证（加密存储）
    garmin_email = Column(String, nullable=False)  # Garmin邮箱
    encrypted_password = Column(Text, nullable=False)  # 加密后的Garmin密码
    
    # 同步状态
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    sync_enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="garmin_credentials")

