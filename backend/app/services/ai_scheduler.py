"""
AI 日程编排引擎 v1.0

executor.life 核心功能 - 基于用户画像和健康数据生成个性化日程安排

功能：
1. 早间健康简报 (Morning Briefing)
2. 动态日程生成 (Daily Schedule)
3. 主动健康提醒 (Proactive Reminders)
4. 时间感知建议 (Time-aware Recommendations)
"""

import logging
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from enum import Enum

from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.daily_health import GarminData
from app.models.basic_health import BasicHealthData
from app.models.checkin import CheckinRecord
from app.utils.timezone import get_china_today, get_china_now

logger = logging.getLogger(__name__)


class ReminderType(str, Enum):
    """提醒类型"""
    NASAL_WASH = "nasal_wash"  # 洗鼻
    DRINK_WATER = "drink_water"  # 喝水
    EXERCISE = "exercise"  # 运动
    SUPPLEMENT = "supplement"  # 补剂
    MEAL = "meal"  # 饮食
    STAND_UP = "stand_up"  # 站立
    SLEEP = "sleep"  # 睡眠
    STRETCH = "stretch"  # 拉伸
    WEIGH = "weigh"  # 称重
    CUSTOM = "custom"  # 自定义


class Reminder:
    """提醒对象"""
    def __init__(
        self,
        reminder_type: ReminderType,
        title: str,
        message: str,
        scheduled_time: time,
        priority: int = 2,  # 1-5, 1最高
        is_recurring: bool = True,
        conditions: Optional[Dict] = None
    ):
        self.reminder_type = reminder_type
        self.title = title
        self.message = message
        self.scheduled_time = scheduled_time
        self.priority = priority
        self.is_recurring = is_recurring
        self.conditions = conditions or {}
    
    def to_dict(self) -> Dict:
        return {
            "type": self.reminder_type.value,
            "title": self.title,
            "message": self.message,
            "scheduled_time": self.scheduled_time.strftime("%H:%M"),
            "priority": self.priority,
            "is_recurring": self.is_recurring,
            "conditions": self.conditions
        }


class AIScheduler:
    """AI 日程编排引擎"""
    
    def __init__(self):
        """初始化调度器"""
        self.default_reminders = self._create_default_reminders()
    
    def _create_default_reminders(self) -> List[Reminder]:
        """创建默认提醒列表"""
        return [
            # 早晨流程
            Reminder(
                reminder_type=ReminderType.NASAL_WASH,
                title="🫧 早间洗鼻",
                message="早起用生理盐水清洗鼻腔，有助于清除过敏原和分泌物",
                scheduled_time=time(7, 0),
                priority=1
            ),
            Reminder(
                reminder_type=ReminderType.WEIGH,
                title="⚖️ 晨起称重",
                message="空腹排便后称重，保持每日同一时间测量以确保数据一致性",
                scheduled_time=time(7, 10),
                priority=2
            ),
            Reminder(
                reminder_type=ReminderType.DRINK_WATER,
                title="💧 早起喝水",
                message="空腹一杯温水（约250ml），唤醒肠胃，补充夜间水分流失",
                scheduled_time=time(7, 15),
                priority=1
            ),
            Reminder(
                reminder_type=ReminderType.SUPPLEMENT,
                title="💊 早餐补剂",
                message="随早餐服用日常补剂：维生素D、鱼油等脂溶性补剂",
                scheduled_time=time(8, 0),
                priority=2
            ),
            
            # 上午
            Reminder(
                reminder_type=ReminderType.DRINK_WATER,
                title="💧 上午喝水",
                message="补充水分，保持每小时喝水200ml左右",
                scheduled_time=time(10, 0),
                priority=3
            ),
            Reminder(
                reminder_type=ReminderType.STAND_UP,
                title="🧍 起身活动",
                message="久坐1小时了，站起来活动5分钟，走动一下或做简单拉伸",
                scheduled_time=time(10, 30),
                priority=2
            ),
            
            # 中午
            Reminder(
                reminder_type=ReminderType.DRINK_WATER,
                title="💧 午餐前喝水",
                message="餐前30分钟喝水有助于消化，约200ml",
                scheduled_time=time(11, 30),
                priority=3
            ),
            Reminder(
                reminder_type=ReminderType.MEAL,
                title="🍱 午餐时间",
                message="记得记录午餐内容，保持饮食平衡",
                scheduled_time=time(12, 0),
                priority=2
            ),
            
            # 下午
            Reminder(
                reminder_type=ReminderType.DRINK_WATER,
                title="💧 下午喝水",
                message="午后喝水，避免疲倦。温水最佳",
                scheduled_time=time(14, 30),
                priority=3
            ),
            Reminder(
                reminder_type=ReminderType.STAND_UP,
                title="🧍 下午活动",
                message="下午久坐了，站起来走动5-10分钟",
                scheduled_time=time(15, 30),
                priority=2
            ),
            Reminder(
                reminder_type=ReminderType.DRINK_WATER,
                title="💧 傍晚喝水",
                message="晚餐前补充水分",
                scheduled_time=time(17, 30),
                priority=3
            ),
            
            # 晚间
            Reminder(
                reminder_type=ReminderType.EXERCISE,
                title="🏃 运动时间",
                message="如果今天还没运动，现在是户外运动的好时机",
                scheduled_time=time(18, 30),
                priority=2,
                conditions={"check_workout": True}
            ),
            Reminder(
                reminder_type=ReminderType.NASAL_WASH,
                title="🫧 晚间洗鼻",
                message="睡前洗鼻，清除一天累积的过敏原和污染物",
                scheduled_time=time(21, 0),
                priority=1
            ),
            Reminder(
                reminder_type=ReminderType.SUPPLEMENT,
                title="💊 晚间补剂",
                message="睡前服用镁补剂，有助于放松和睡眠",
                scheduled_time=time(21, 30),
                priority=2
            ),
            Reminder(
                reminder_type=ReminderType.SLEEP,
                title="😴 准备休息",
                message="距离目标睡眠时间还有30分钟，关闭屏幕，准备入睡",
                scheduled_time=time(22, 30),
                priority=1
            ),
        ]
    
    def generate_morning_briefing(
        self,
        db: Session,
        user_id: int
    ) -> Dict[str, Any]:
        """
        生成早间健康简报
        
        包含：
        - 昨日睡眠总结
        - 今日天气和运动建议
        - 今日目标提醒
        - 个性化建议
        """
        china_today = get_china_today()
        yesterday = china_today - timedelta(days=1)
        
        # 获取用户画像
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        
        # 获取今日睡眠数据（记录在今天的日期下）
        # Garmin 的睡眠数据记录在醒来当天，所以今天的睡眠数据就是昨晚的睡眠
        today_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == china_today
        ).first()
        
        # 如果今天没有数据，尝试获取昨天的数据
        yesterday_data = today_data if today_data else db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == yesterday
        ).first()
        
        # 获取今日打卡记录
        today_checkin = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date == china_today
        ).first()
        
        briefing = {
            "date": china_today.isoformat(),
            "greeting": self._get_time_greeting(),
            "sections": []
        }
        
        # 1. 睡眠回顾
        if yesterday_data and yesterday_data.sleep_score:
            # 睡眠时长（分钟转小时）
            sleep_hours = yesterday_data.total_sleep_duration / 60 if yesterday_data.total_sleep_duration else None
            deep_sleep_hours = yesterday_data.deep_sleep_duration / 60 if yesterday_data.deep_sleep_duration else None
            
            # 显示数据日期
            data_date = yesterday_data.record_date
            sleep_section = {
                "title": f"😴 昨晚睡眠 ({data_date.month}月{data_date.day}日数据)",
                "status": "good" if yesterday_data.sleep_score >= 80 else "warning" if yesterday_data.sleep_score >= 60 else "poor",
                "items": [
                    f"睡眠分数: {yesterday_data.sleep_score}分",
                    f"睡眠时长: {sleep_hours:.1f}小时" if sleep_hours else "时长未记录",
                ]
            }
            if deep_sleep_hours:
                sleep_section["items"].append(f"深睡: {deep_sleep_hours:.1f}小时")
            briefing["sections"].append(sleep_section)
        
        # 2. 身体状态
        if yesterday_data:
            body_section = {
                "title": "⚡ 身体状态",
                "status": "good" if (yesterday_data.body_battery_most_charged or 0) >= 80 else "warning",
                "items": []
            }
            if yesterday_data.body_battery_most_charged:
                body_section["items"].append(f"身体电量峰值: {yesterday_data.body_battery_most_charged}")
            if yesterday_data.resting_heart_rate:
                body_section["items"].append(f"静息心率: {yesterday_data.resting_heart_rate} bpm")
            if yesterday_data.stress_level:
                body_section["items"].append(f"压力水平: {yesterday_data.stress_level}")
            if body_section["items"]:
                briefing["sections"].append(body_section)
        
        # 3. 今日目标
        goals_section = {
            "title": "🎯 今日目标",
            "status": "info",
            "items": []
        }
        if profile:
            goals_section["items"].append(f"步数目标: {profile.target_steps or 8000} 步")
            goals_section["items"].append(f"饮水目标: {profile.target_water_ml or 2000} ml")
            goals_section["items"].append(f"运动目标: {profile.target_exercise_minutes or 30} 分钟")
        else:
            goals_section["items"] = ["步数: 8000步", "饮水: 2000ml", "运动: 30分钟"]
        briefing["sections"].append(goals_section)
        
        # 4. 今日提醒
        reminders_section = {
            "title": "📋 今日提醒",
            "status": "info",
            "items": self._get_priority_reminders(profile)
        }
        briefing["sections"].append(reminders_section)
        
        return briefing
    
    def _get_time_greeting(self) -> str:
        """根据时间返回问候语"""
        hour = get_china_now().hour
        if 5 <= hour < 9:
            return "早安！新的一天开始了 🌅"
        elif 9 <= hour < 12:
            return "上午好！保持专注 💪"
        elif 12 <= hour < 14:
            return "中午好！记得休息 ☀️"
        elif 14 <= hour < 18:
            return "下午好！继续加油 🚀"
        elif 18 <= hour < 22:
            return "晚上好！放松一下 🌙"
        else:
            return "夜深了，注意休息 💤"
    
    def _get_priority_reminders(self, profile: Optional[UserProfile]) -> List[str]:
        """获取优先级提醒"""
        reminders = []
        
        # 检查用户是否有慢性鼻炎
        if profile and profile.chronic_conditions:
            if any("鼻炎" in c for c in profile.chronic_conditions):
                reminders.append("🫧 记得早晚洗鼻")
        
        reminders.extend([
            "💧 保持充足饮水",
            "🧍 久坐记得起身活动",
        ])
        
        return reminders[:5]  # 最多5条
    
    def get_reminders_for_time(
        self,
        db: Session,
        user_id: int,
        current_time: Optional[datetime] = None
    ) -> List[Dict]:
        """
        获取当前时间段的提醒
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            current_time: 当前时间（默认使用北京时间）
            
        Returns:
            当前应该显示的提醒列表
        """
        if current_time is None:
            current_time = get_china_now()
        
        current_hour = current_time.hour
        current_minute = current_time.minute
        
        # 获取用户画像
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        
        # 筛选当前时间段的提醒（前后15分钟内）
        relevant_reminders = []
        for reminder in self.default_reminders:
            reminder_minutes = reminder.scheduled_time.hour * 60 + reminder.scheduled_time.minute
            current_minutes = current_hour * 60 + current_minute
            
            # 检查是否在提醒时间的前后15分钟内
            if abs(reminder_minutes - current_minutes) <= 15:
                # 检查条件
                if self._check_reminder_conditions(db, user_id, reminder, profile):
                    relevant_reminders.append(reminder.to_dict())
        
        return relevant_reminders
    
    def _check_reminder_conditions(
        self,
        db: Session,
        user_id: int,
        reminder: Reminder,
        profile: Optional[UserProfile]
    ) -> bool:
        """检查提醒条件是否满足"""
        conditions = reminder.conditions
        
        if not conditions:
            return True
        
        # 检查今日是否已运动
        if conditions.get("check_workout"):
            china_today = get_china_today()
            from app.models.daily_health import WorkoutRecord
            today_workout = db.query(WorkoutRecord).filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date == china_today
            ).first()
            # 如果今天已经运动了，就不提醒
            if today_workout:
                return False
        
        return True
    
    def generate_daily_schedule(
        self,
        db: Session,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        生成今日日程安排
        
        基于：
        - 用户画像（工作习惯、健康目标）
        - 昨日数据（睡眠、运动）
        - 今日天气
        """
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        china_today = get_china_today()
        
        schedule = []
        
        # 获取用户的起床和睡觉时间
        wake_time = time(7, 0)
        sleep_time = time(23, 0)
        
        if profile:
            if profile.usual_wake_time:
                try:
                    parts = profile.usual_wake_time.split(":")
                    wake_time = time(int(parts[0]), int(parts[1]))
                except:
                    pass
            if profile.usual_sleep_time:
                try:
                    parts = profile.usual_sleep_time.split(":")
                    sleep_time = time(int(parts[0]), int(parts[1]))
                except:
                    pass
        
        # 生成日程
        schedule = [
            {
                "time": wake_time.strftime("%H:%M"),
                "activity": "起床",
                "category": "routine",
                "duration_minutes": 30,
                "tasks": ["洗漱", "称重", "喝水"]
            },
            {
                "time": (datetime.combine(china_today, wake_time) + timedelta(minutes=30)).strftime("%H:%M"),
                "activity": "早餐",
                "category": "meal",
                "duration_minutes": 30,
                "tasks": ["健康早餐", "服用补剂"]
            },
            {
                "time": "09:00",
                "activity": "开始工作",
                "category": "work",
                "duration_minutes": 180,
                "tasks": ["专注工作", "每小时站立活动"]
            },
            {
                "time": "12:00",
                "activity": "午餐",
                "category": "meal",
                "duration_minutes": 60,
                "tasks": ["均衡饮食", "记录饮食"]
            },
            {
                "time": "13:00",
                "activity": "午休",
                "category": "rest",
                "duration_minutes": 30,
                "tasks": ["短暂午睡或休息"]
            },
            {
                "time": "13:30",
                "activity": "下午工作",
                "category": "work",
                "duration_minutes": 240,
                "tasks": ["专注工作", "保持饮水"]
            },
            {
                "time": "18:00",
                "activity": "运动时间",
                "category": "exercise",
                "duration_minutes": 60,
                "tasks": [f"目标: {profile.target_exercise_minutes if profile else 30}分钟运动"]
            },
            {
                "time": "19:00",
                "activity": "晚餐",
                "category": "meal",
                "duration_minutes": 60,
                "tasks": ["清淡晚餐", "记录饮食"]
            },
            {
                "time": "20:00",
                "activity": "个人时间",
                "category": "leisure",
                "duration_minutes": 120,
                "tasks": ["阅读", "家庭时间", "轻度活动"]
            },
            {
                "time": "22:00",
                "activity": "睡前准备",
                "category": "routine",
                "duration_minutes": 60,
                "tasks": ["洗鼻", "服用睡前补剂", "关闭屏幕"]
            },
            {
                "time": sleep_time.strftime("%H:%M"),
                "activity": "入睡",
                "category": "sleep",
                "duration_minutes": 480,
                "tasks": [f"目标: {profile.target_sleep_hours if profile else 7.5}小时睡眠"]
            },
        ]
        
        return schedule
    
    def get_time_aware_recommendation(
        self,
        db: Session,
        user_id: int,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        获取时间感知的实时建议
        
        根据当前时间和用户状态，给出最相关的建议
        """
        if current_time is None:
            current_time = get_china_now()
        
        hour = current_time.hour
        china_today = get_china_today()
        
        # 获取今日数据
        today_data = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == china_today
        ).first()
        
        # 获取用户画像
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        
        recommendation = {
            "timestamp": current_time.isoformat(),
            "primary": None,
            "secondary": [],
            "status": {}
        }
        
        # 早晨 (5-9点)
        if 5 <= hour < 9:
            recommendation["primary"] = {
                "icon": "🌅",
                "title": "早安！开始美好的一天",
                "message": "建议：起床后喝杯温水，做简单拉伸"
            }
            recommendation["secondary"] = ["完成早间洗鼻", "称重记录"]
        
        # 上午 (9-12点)
        elif 9 <= hour < 12:
            if today_data and today_data.steps:
                step_progress = (today_data.steps / (profile.target_steps if profile else 8000)) * 100
                recommendation["status"]["steps"] = {
                    "current": today_data.steps,
                    "target": profile.target_steps if profile else 8000,
                    "progress": min(step_progress, 100)
                }
            recommendation["primary"] = {
                "icon": "💼",
                "title": "上午工作时间",
                "message": "保持专注，记得每小时站起来活动"
            }
            recommendation["secondary"] = ["喝水补充水分", "适时休息眼睛"]
        
        # 中午 (12-14点)
        elif 12 <= hour < 14:
            recommendation["primary"] = {
                "icon": "🍱",
                "title": "午餐时间",
                "message": "均衡饮食，记录摄入的食物"
            }
            recommendation["secondary"] = ["饭后短暂休息", "避免立即剧烈运动"]
        
        # 下午 (14-18点)
        elif 14 <= hour < 18:
            recommendation["primary"] = {
                "icon": "☀️",
                "title": "下午继续加油",
                "message": "保持饮水，避免久坐"
            }
            recommendation["secondary"] = ["适时喝水", "站立办公或走动"]
        
        # 傍晚 (18-21点)
        elif 18 <= hour < 21:
            # 检查今日是否已运动
            from app.models.daily_health import WorkoutRecord
            today_workout = db.query(WorkoutRecord).filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date == china_today
            ).first()
            
            if today_workout:
                recommendation["primary"] = {
                    "icon": "✅",
                    "title": "今日运动已完成",
                    "message": f"很棒！今天已经运动，注意拉伸放松"
                }
            else:
                recommendation["primary"] = {
                    "icon": "🏃",
                    "title": "运动时间到",
                    "message": "现在是户外运动的好时机，完成今日运动目标"
                }
            recommendation["secondary"] = ["清淡晚餐", "饭后散步"]
        
        # 晚间 (21-23点)
        elif 21 <= hour < 23:
            recommendation["primary"] = {
                "icon": "🌙",
                "title": "睡前准备",
                "message": "减少屏幕使用，准备入睡"
            }
            recommendation["secondary"] = ["完成睡前洗鼻", "服用镁补剂"]
        
        # 深夜 (23点-5点)
        else:
            recommendation["primary"] = {
                "icon": "😴",
                "title": "该休息了",
                "message": "充足的睡眠是健康的基础"
            }
            recommendation["secondary"] = ["保持卧室黑暗凉爽", "避免使用手机"]
        
        return recommendation


# 全局实例
ai_scheduler = AIScheduler()
