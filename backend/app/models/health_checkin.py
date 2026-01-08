"""健康打卡模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class HealthCheckin(Base):
    """健康打卡记录"""
    __tablename__ = "health_checkins"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    checkin_date = Column(Date, nullable=False, index=True)  # 打卡日期（每个用户每天一条）
    
    # 专项锻炼记录
    running_distance = Column(Float)  # 跑步距离 (km)
    running_duration = Column(Integer)  # 跑步时长 (分钟)
    squats_count = Column(Integer)  # 深蹲次数
    leg_raises_count = Column(Integer)  # 踢腿次数
    tai_chi_duration = Column(Integer)  # 太极拳时长 (分钟)
    ba_duan_jin_duration = Column(Integer)  # 八段锦时长 (分钟)
    
    # 其他专项锻炼（JSON格式存储）
    other_exercises = Column(JSON)  # {"exercise_name": {"duration": 30, "count": 10}}
    
    # 鼻炎管理
    sneeze_count = Column(Integer)  # 打喷嚏次数
    sneeze_times = Column(JSON)  # 打喷嚏时间记录 [{"time": "09:00", "count": 3}, ...]
    nasal_wash_count = Column(Integer)  # 洗鼻次数
    nasal_wash_times = Column(JSON)  # 洗鼻时间记录 [{"time": "08:00", "type": "wash"}, {"time": "20:00", "type": "soak"}]
    
    # 综合评分
    daily_score = Column(Integer)  # 每日健康评分 (0-100)
    
    # 完成情况
    goals_completed = Column(JSON)  # 完成的目标列表
    
    # 备注
    notes = Column(Text)  # 备注
    
    # 个性化建议（由LLM生成）
    personalized_advice = Column(Text)  # 个性化建议
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="health_checkins")

