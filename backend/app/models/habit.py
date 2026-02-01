"""习惯追踪模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Boolean, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class HabitDefinition(Base):
    """习惯定义 - 用户的习惯列表"""
    __tablename__ = "habit_definitions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String, nullable=False)  # 习惯名称
    category = Column(String)  # 分类（健康/运动/学习/生活等）
    description = Column(Text)  # 描述
    icon = Column(String)  # 图标（emoji）

    target_frequency = Column(String, default="daily")  # 目标频率（daily/weekly）
    target_count = Column(Integer, default=1)  # 每周/每日目标次数

    is_active = Column(Boolean, default=True)  # 是否启用
    sort_order = Column(Integer, default=0)  # 排序顺序

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="habit_definitions")
    records = relationship("HabitRecord", back_populates="habit", cascade="all, delete-orphan")

    # 复合索引：优化按用户和状态查询
    __table_args__ = (
        Index('idx_habit_def_user_active', 'user_id', 'is_active'),
    )


class HabitRecord(Base):
    """习惯打卡记录"""
    __tablename__ = "habit_records"

    id = Column(Integer, primary_key=True, index=True)
    habit_id = Column(Integer, ForeignKey("habit_definitions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    record_date = Column(Date, nullable=False, index=True)
    completed = Column(Boolean, default=False)  # 是否完成
    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    habit = relationship("HabitDefinition", back_populates="records")
    user = relationship("User", backref="habit_records")

    # 复合索引：优化按习惯和日期查询
    __table_args__ = (
        Index('idx_habit_rec_habit_date', 'habit_id', 'record_date'),
        Index('idx_habit_rec_user_date', 'user_id', 'record_date'),
    )

