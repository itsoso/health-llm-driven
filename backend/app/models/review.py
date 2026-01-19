"""
每日/周/月/季/年复盘模型
"""
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Float, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from app.database import Base


class ReviewPeriod(str, enum.Enum):
    """复盘周期类型"""
    DAILY = "daily"       # 每日复盘
    WEEKLY = "weekly"     # 周复盘
    MONTHLY = "monthly"   # 月复盘
    QUARTERLY = "quarterly"  # 季度复盘
    YEARLY = "yearly"     # 年度复盘


class DailyReview(Base):
    """每日复盘记录"""
    __tablename__ = "daily_reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    review_date = Column(Date, nullable=False, index=True)  # 复盘日期
    
    # ========== 自动汇总的健康数据 ==========
    # 睡眠数据
    sleep_score = Column(Integer)  # 睡眠分数
    sleep_duration_hours = Column(Float)  # 睡眠时长(小时)
    sleep_quality = Column(String(50))  # 睡眠质量评价
    
    # 运动数据
    workout_count = Column(Integer, default=0)  # 运动次数
    workout_duration_minutes = Column(Integer, default=0)  # 运动总时长(分钟)
    workout_calories = Column(Integer, default=0)  # 运动消耗热量
    workout_types = Column(String(200))  # 运动类型列表(逗号分隔)
    
    # 小睡数据
    nap_count = Column(Integer, default=0)  # 小睡次数
    nap_duration_minutes = Column(Integer, default=0)  # 小睡总时长
    
    # 步数和活动
    steps = Column(Integer, default=0)  # 步数
    active_calories = Column(Integer, default=0)  # 活动消耗
    
    # 饮食数据
    meals_count = Column(Integer, default=0)  # 餐数
    total_calories_in = Column(Integer, default=0)  # 摄入热量
    total_protein = Column(Float, default=0)  # 蛋白质(g)
    total_carbs = Column(Float, default=0)  # 碳水(g)
    total_fat = Column(Float, default=0)  # 脂肪(g)
    
    # 饮水数据
    water_intake_ml = Column(Integer, default=0)  # 饮水量(ml)
    water_goal_met = Column(Boolean, default=False)  # 是否达标
    
    # 洗鼻数据
    nasal_wash_count = Column(Integer, default=0)  # 洗鼻次数
    nasal_wash_done = Column(Boolean, default=False)  # 是否完成洗鼻
    
    # 打卡数据
    checkin_completed = Column(Integer, default=0)  # 完成的打卡项数
    checkin_total = Column(Integer, default=0)  # 总打卡项数
    checkin_items = Column(Text)  # 打卡详情(JSON)
    
    # 补剂数据
    supplements_taken = Column(Integer, default=0)  # 服用补剂数
    supplements_list = Column(Text)  # 补剂列表(JSON)
    
    # 身体状态
    body_battery_high = Column(Integer)  # 身体电量最高
    body_battery_low = Column(Integer)  # 身体电量最低
    stress_avg = Column(Integer)  # 平均压力
    resting_hr = Column(Integer)  # 静息心率
    
    # ========== 用户手动输入 ==========
    mood_score = Column(Integer)  # 心情评分(1-5)
    energy_score = Column(Integer)  # 精力评分(1-5)
    productivity_score = Column(Integer)  # 效率评分(1-5)
    
    highlights = Column(Text)  # 今日亮点/成就
    challenges = Column(Text)  # 今日挑战/困难
    learnings = Column(Text)  # 今日收获/学习
    gratitude = Column(Text)  # 感恩的事
    tomorrow_plan = Column(Text)  # 明日计划
    
    # 总结
    summary = Column(Text)  # 用户手写总结
    ai_summary = Column(Text)  # AI生成的总结
    
    # 元数据
    is_completed = Column(Boolean, default=False)  # 是否完成复盘
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    user = relationship("User", backref="daily_reviews")
    
    class Config:
        from_attributes = True


class PeriodReview(Base):
    """周期性复盘记录(周/月/季/年)"""
    __tablename__ = "period_reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    period_type = Column(SQLEnum(ReviewPeriod), nullable=False)  # 周期类型
    
    # 周期范围
    start_date = Column(Date, nullable=False)  # 开始日期
    end_date = Column(Date, nullable=False)  # 结束日期
    period_label = Column(String(50))  # 周期标签，如 "2026年第3周", "2026年1月"
    
    # ========== 汇总统计 ==========
    # 睡眠统计
    avg_sleep_score = Column(Float)
    avg_sleep_duration = Column(Float)
    best_sleep_date = Column(Date)
    worst_sleep_date = Column(Date)
    
    # 运动统计
    total_workouts = Column(Integer, default=0)
    total_workout_minutes = Column(Integer, default=0)
    total_workout_calories = Column(Integer, default=0)
    workout_days = Column(Integer, default=0)  # 运动天数
    
    # 步数统计
    total_steps = Column(Integer, default=0)
    avg_steps = Column(Integer, default=0)
    best_steps_date = Column(Date)
    
    # 饮食统计
    avg_calories_in = Column(Integer, default=0)
    avg_protein = Column(Float, default=0)
    
    # 饮水统计
    avg_water_intake = Column(Integer, default=0)
    water_goal_days = Column(Integer, default=0)  # 达标天数
    
    # 打卡统计
    avg_checkin_rate = Column(Float)  # 平均打卡完成率
    perfect_days = Column(Integer, default=0)  # 全部完成的天数
    
    # 复盘完成情况
    review_days = Column(Integer, default=0)  # 完成复盘的天数
    total_days = Column(Integer, default=0)  # 总天数
    
    # ========== 用户输入 ==========
    achievements = Column(Text)  # 本周期成就
    challenges = Column(Text)  # 本周期挑战
    learnings = Column(Text)  # 本周期收获
    goals_review = Column(Text)  # 目标回顾
    next_period_goals = Column(Text)  # 下周期目标
    
    # 总结
    summary = Column(Text)  # 用户手写总结
    ai_summary = Column(Text)  # AI生成的总结
    
    # 元数据
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关系
    user = relationship("User", backref="period_reviews")
    
    class Config:
        from_attributes = True
