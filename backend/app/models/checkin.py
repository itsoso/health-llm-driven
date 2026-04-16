"""
打卡系统模型 - executor.life 健康模块
支持自定义打卡项目，追踪微小可叠加的进步
"""
from datetime import UTC, date, datetime, time
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Time, JSON, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import relationship
from app.database import Base


class CheckinTemplate(Base):
    """打卡模板 - 定义打卡项目"""
    __tablename__ = "checkin_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # 基本信息
    name = Column(String(100), nullable=False)  # "俯卧撑", "深蹲", "洗鼻"
    description = Column(Text, nullable=True)  # 详细描述
    icon = Column(String(50), default="✅")  # 图标emoji
    color = Column(String(20), default="#4f46e5")  # 主题色
    
    # 分类
    category = Column(String(50), nullable=False)  # exercise/health/habit/medicine/custom
    # exercise: 运动锻炼
    # health: 健康检测
    # habit: 生活习惯
    # medicine: 用药提醒
    # custom: 自定义
    
    # 计量配置
    unit = Column(String(20), default="次")  # 次/组/分钟/ml/mg
    default_target = Column(Float, default=1)  # 默认目标值
    min_value = Column(Float, default=0)  # 最小值
    max_value = Column(Float, nullable=True)  # 最大值
    step_value = Column(Float, default=1)  # 步进值
    
    # 提醒配置
    reminder_enabled = Column(Boolean, default=False)
    reminder_time = Column(Time, nullable=True)  # 提醒时间 "08:00"
    reminder_days = Column(JSON, default=list)  # 提醒日期 [1,2,3,4,5] 周一到周五
    
    # 频率配置
    frequency = Column(String(20), default="daily")  # daily/weekly/monthly/custom
    frequency_target = Column(Integer, default=1)  # 每周期目标次数
    
    # 统计数据（冗余存储，方便查询）
    total_checkins = Column(Integer, default=0)  # 总打卡次数
    total_value = Column(Float, default=0)  # 总完成量
    current_streak = Column(Integer, default=0)  # 当前连续天数
    best_streak = Column(Integer, default=0)  # 最长连续天数
    last_checkin_date = Column(Date, nullable=True)  # 最后打卡日期
    
    # 状态
    is_active = Column(Boolean, default=True)  # 是否启用
    is_archived = Column(Boolean, default=False)  # 是否归档
    sort_order = Column(Integer, default=0)  # 排序顺序
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    # 关系
    records = relationship("CheckinRecord", back_populates="template", cascade="all, delete-orphan")

    # 复合索引：优化按用户和分类查询
    __table_args__ = (
        Index('idx_checkin_tmpl_user_category', 'user_id', 'category', 'is_active'),
        Index('idx_checkin_tmpl_user_active', 'user_id', 'is_active', 'sort_order'),
    )


class CheckinRecord(Base):
    """打卡记录 - 每次打卡的详细记录"""
    __tablename__ = "checkin_records"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("checkin_templates.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # 打卡日期和时间
    checkin_date = Column(Date, nullable=False, index=True)
    checkin_time = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # 完成情况
    value = Column(Float, nullable=False)  # 实际完成量
    target = Column(Float, nullable=True)  # 当日目标
    completion_rate = Column(Float, nullable=True)  # 完成率 (value/target * 100)
    
    # 附加数据
    duration_seconds = Column(Integer, nullable=True)  # 持续时间（秒）
    calories_burned = Column(Float, nullable=True)  # 消耗卡路里
    heart_rate_avg = Column(Integer, nullable=True)  # 平均心率
    
    # 主观感受
    difficulty = Column(String(20), nullable=True)  # easy/normal/hard/very_hard
    mood_before = Column(String(20), nullable=True)  # 打卡前心情: great/good/neutral/bad
    mood_after = Column(String(20), nullable=True)  # 打卡后心情
    energy_level = Column(Integer, nullable=True)  # 精力等级 1-10
    
    # 备注和标签
    notes = Column(Text, nullable=True)  # 备注
    tags = Column(JSON, default=list)  # 标签 ["室内", "晨练"]
    
    # 位置信息（可选）
    location = Column(String(200), nullable=True)  # 打卡位置
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # 媒体附件
    photos = Column(JSON, default=list)  # 图片URL列表
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    # 关系
    template = relationship("CheckinTemplate", back_populates="records")

    # 复合索引：优化按用户、模板和日期查询
    __table_args__ = (
        Index('idx_checkin_rec_user_date', 'user_id', 'checkin_date'),
        Index('idx_checkin_rec_template_date', 'template_id', 'checkin_date'),
        Index('idx_checkin_rec_user_template_date', 'user_id', 'template_id', 'checkin_date'),
    )


# 预定义的打卡模板（系统默认）
DEFAULT_CHECKIN_TEMPLATES = [
    # 运动类
    {
        "name": "俯卧撑",
        "category": "exercise",
        "icon": "💪",
        "unit": "个",
        "default_target": 20,
        "description": "标准俯卧撑，增强上肢力量",
    },
    {
        "name": "深蹲",
        "category": "exercise",
        "icon": "🦵",
        "unit": "个",
        "default_target": 30,
        "description": "标准深蹲，增强下肢力量",
    },
    {
        "name": "仰卧起坐",
        "category": "exercise",
        "icon": "🏋️",
        "unit": "个",
        "default_target": 30,
        "description": "增强腹部核心力量",
    },
    {
        "name": "平板支撑",
        "category": "exercise",
        "icon": "🧘",
        "unit": "秒",
        "default_target": 60,
        "description": "增强核心稳定性",
    },
    {
        "name": "跳绳",
        "category": "exercise",
        "icon": "🏃",
        "unit": "个",
        "default_target": 200,
        "description": "有氧运动，提升心肺功能",
    },
    {
        "name": "爬楼梯",
        "category": "exercise",
        "icon": "🏢",
        "unit": "层",
        "default_target": 10,
        "description": "日常有氧运动",
    },
    {
        "name": "拉伸",
        "category": "exercise",
        "icon": "🤸",
        "unit": "分钟",
        "default_target": 10,
        "description": "运动前后拉伸，预防受伤",
    },
    {
        "name": "王川踢腿法",
        "category": "exercise",
        "icon": "🦵",
        "unit": "回",
        "default_target": 2,
        "step_value": 1,
        "description": "源自太极热身的极简锻炼：双臂张开呈T字，正踢→顺时针踢→逆时针踢，每向8次共48次为1回。保持上身中正，踢高过头。每日2回约100次，耗时<4分钟。核心心法：微量高频，能坚持到明天就够了。",
    },

    # 健康类
    {
        "name": "洗鼻",
        "category": "health",
        "icon": "👃",
        "unit": "次",
        "default_target": 2,
        "description": "使用生理盐水清洗鼻腔，缓解鼻炎",
    },
    {
        "name": "测血压",
        "category": "health",
        "icon": "❤️",
        "unit": "次",
        "default_target": 1,
        "description": "每日血压监测",
    },
    {
        "name": "测血糖",
        "category": "health",
        "icon": "🩸",
        "unit": "次",
        "default_target": 1,
        "description": "血糖监测",
    },
    {
        "name": "称体重",
        "category": "health",
        "icon": "⚖️",
        "unit": "次",
        "default_target": 1,
        "description": "每日体重记录",
    },
    
    # 生活习惯类
    {
        "name": "喝水",
        "category": "habit",
        "icon": "💧",
        "unit": "ml",
        "default_target": 2000,
        "description": "每日饮水量追踪",
    },
    {
        "name": "冥想",
        "category": "habit",
        "icon": "🧘‍♂️",
        "unit": "分钟",
        "default_target": 10,
        "description": "正念冥想，缓解压力",
    },
    {
        "name": "早睡",
        "category": "habit",
        "icon": "🌙",
        "unit": "次",
        "default_target": 1,
        "description": "23点前入睡",
    },
    {
        "name": "不看手机",
        "category": "habit",
        "icon": "📵",
        "unit": "小时",
        "default_target": 1,
        "description": "睡前1小时不看手机",
    },
    {
        "name": "户外活动",
        "category": "habit",
        "icon": "🌳",
        "unit": "分钟",
        "default_target": 30,
        "description": "每日户外活动时间",
    },
    
    # 用药类
    {
        "name": "维生素D",
        "category": "medicine",
        "icon": "💊",
        "unit": "粒",
        "default_target": 1,
        "description": "每日维生素D补充",
    },
    {
        "name": "益生菌",
        "category": "medicine",
        "icon": "🦠",
        "unit": "粒",
        "default_target": 1,
        "description": "肠道健康补充",
    },
]
