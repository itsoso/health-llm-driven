"""成就徽章模型"""
from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from app.database import Base


class BadgeDefinition(Base):
    """徽章定义"""
    __tablename__ = "badge_definitions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(10), default="🏆")
    category = Column(String(20), nullable=False)  # streak / activity / milestone
    criteria_type = Column(String(50), nullable=False)  # checkin_streak / water_count / run_distance / first_checkin / first_ai_chat / diet_count / checkin_total
    criteria_value = Column(Float, nullable=False)  # 达成所需数值
    rarity = Column(String(20), default="common")  # common / rare / epic / legendary
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    user_badges = relationship("UserBadge", back_populates="badge")


class UserBadge(Base):
    """用户已获得的徽章"""
    __tablename__ = "user_badges"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    badge_id = Column(Integer, ForeignKey("badge_definitions.id"), nullable=False, index=True)
    unlocked_at = Column(DateTime, default=lambda: datetime.now(UTC))
    progress_value = Column(Float, default=0)
    notified = Column(Boolean, default=False)

    badge = relationship("BadgeDefinition", back_populates="user_badges")

    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
    )


# 15 个预置徽章
BADGE_SEED_DATA = [
    # 连续打卡 streak
    {"code": "streak_3", "name": "三天坚持", "description": "连续打卡3天", "icon": "🔥", "category": "streak", "criteria_type": "checkin_streak", "criteria_value": 3, "rarity": "common", "sort_order": 1},
    {"code": "streak_7", "name": "一周不断", "description": "连续打卡7天", "icon": "🔥", "category": "streak", "criteria_type": "checkin_streak", "criteria_value": 7, "rarity": "common", "sort_order": 2},
    {"code": "streak_30", "name": "月度达人", "description": "连续打卡30天", "icon": "🌟", "category": "streak", "criteria_type": "checkin_streak", "criteria_value": 30, "rarity": "rare", "sort_order": 3},
    {"code": "streak_100", "name": "百日不辍", "description": "连续打卡100天", "icon": "💎", "category": "streak", "criteria_type": "checkin_streak", "criteria_value": 100, "rarity": "legendary", "sort_order": 4},
    # 饮水 activity
    {"code": "water_50", "name": "饮水新手", "description": "累计记录饮水50次", "icon": "💧", "category": "activity", "criteria_type": "water_count", "criteria_value": 50, "rarity": "common", "sort_order": 10},
    {"code": "water_100", "name": "饮水达人", "description": "累计记录饮水100次", "icon": "🌊", "category": "activity", "criteria_type": "water_count", "criteria_value": 100, "rarity": "rare", "sort_order": 11},
    # 跑步 activity
    {"code": "run_10km", "name": "迈出第一步", "description": "累计跑步10公里", "icon": "🏃", "category": "activity", "criteria_type": "run_distance", "criteria_value": 10, "rarity": "common", "sort_order": 20},
    {"code": "run_100km", "name": "百公里勇士", "description": "累计跑步100公里", "icon": "🏅", "category": "activity", "criteria_type": "run_distance", "criteria_value": 100, "rarity": "rare", "sort_order": 21},
    {"code": "run_500km", "name": "马拉松之路", "description": "累计跑步500公里", "icon": "🏆", "category": "activity", "criteria_type": "run_distance", "criteria_value": 500, "rarity": "epic", "sort_order": 22},
    # 里程碑 milestone
    {"code": "first_checkin", "name": "第一次打卡", "description": "完成第一次打卡", "icon": "✅", "category": "milestone", "criteria_type": "first_checkin", "criteria_value": 1, "rarity": "common", "sort_order": 30},
    {"code": "first_ai_chat", "name": "AI初体验", "description": "首次与AI助手对话", "icon": "🤖", "category": "milestone", "criteria_type": "first_ai_chat", "criteria_value": 1, "rarity": "common", "sort_order": 31},
    {"code": "checkin_total_100", "name": "打卡百次", "description": "累计打卡100次", "icon": "💯", "category": "milestone", "criteria_type": "checkin_total", "criteria_value": 100, "rarity": "rare", "sort_order": 32},
    {"code": "diet_record_50", "name": "饮食记录员", "description": "累计记录饮食50次", "icon": "🍽️", "category": "milestone", "criteria_type": "diet_count", "criteria_value": 50, "rarity": "common", "sort_order": 33},
    {"code": "checkin_total_500", "name": "打卡五百", "description": "累计打卡500次", "icon": "🎯", "category": "milestone", "criteria_type": "checkin_total", "criteria_value": 500, "rarity": "epic", "sort_order": 34},
    {"code": "water_500", "name": "水之王者", "description": "累计记录饮水500次", "icon": "🐳", "category": "activity", "criteria_type": "water_count", "criteria_value": 500, "rarity": "epic", "sort_order": 12},
]
