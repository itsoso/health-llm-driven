"""目标管理模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class GoalType(str, enum.Enum):
    """目标类型"""
    DIET = "diet"  # 饮食
    EXERCISE = "exercise"  # 锻炼
    SLEEP = "sleep"  # 睡眠
    WATER = "water"  # 饮水
    SUPPLEMENT = "supplement"  # 补剂
    OUTDOOR = "outdoor"  # 户外活动
    WEIGHT = "weight"  # 体重
    OTHER = "other"  # 其他


class GoalPeriod(str, enum.Enum):
    """目标周期"""
    DAILY = "daily"  # 每日
    WEEKLY = "weekly"  # 每周
    MONTHLY = "monthly"  # 每月
    YEARLY = "yearly"  # 每年


class GoalStatus(str, enum.Enum):
    """目标状态"""
    ACTIVE = "active"  # 进行中
    COMPLETED = "completed"  # 已完成
    PAUSED = "paused"  # 已暂停
    CANCELLED = "cancelled"  # 已取消


class Goal(Base):
    """健康目标"""
    __tablename__ = "goals"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 目标基本信息
    goal_type = Column(Enum(GoalType), nullable=False)  # 目标类型
    goal_period = Column(Enum(GoalPeriod), nullable=False)  # 目标周期
    title = Column(String, nullable=False)  # 目标标题
    description = Column(Text)  # 目标描述
    
    # 目标值
    target_value = Column(Float)  # 目标值
    target_unit = Column(String)  # 目标单位
    current_value = Column(Float, default=0)  # 当前值
    
    # 时间范围
    start_date = Column(Date, nullable=False)  # 开始日期
    end_date = Column(Date)  # 结束日期
    
    # 实现步骤（JSON格式）
    implementation_steps = Column(Text)  # 实现步骤（JSON字符串或文本）
    
    # 状态
    status = Column(Enum(GoalStatus), default=GoalStatus.ACTIVE)  # 目标状态
    
    # 优先级
    priority = Column(Integer, default=5)  # 优先级 (1-10)
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="goals")
    progress_records = relationship("GoalProgress", back_populates="goal", cascade="all, delete-orphan")


class GoalProgress(Base):
    """目标进展记录"""
    __tablename__ = "goal_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id"), nullable=False)
    
    progress_date = Column(Date, nullable=False, index=True)  # 进展日期
    progress_value = Column(Float)  # 进展值
    completion_percentage = Column(Float)  # 完成百分比
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    goal = relationship("Goal", back_populates="progress_records")

