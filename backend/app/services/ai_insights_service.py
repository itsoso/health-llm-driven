"""AI 健康洞察服务 - 整合多维度数据生成个性化建议"""
import httpx
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models import (
    AIInsight, RealtimeRecommendation,
    GarminData, CheckinRecord, WeightRecord, BloodPressureRecord,
    UserProfile, HealthGoal, DietRecord
)
from app.schemas.ai_insights import (
    AIInsightCreate, RealtimeRecommendationCreate
)
from app.services.environment import weather_service
import logging

logger = logging.getLogger(__name__)


class AIInsightsService:
    """AI 健康洞察服务"""

    def __init__(self, db: Session):
        self.db = db
        self.openclaw_url = settings.openclaw_base_url
        self.openclaw_key = settings.openclaw_api_key
        self.openclaw_model = settings.openclaw_model

    # ========== 数据聚合方法 ==========

    async def _aggregate_health_snapshot(self, user_id: int, target_date: date) -> Dict[str, Any]:
        """
        聚合指定日期的健康数据快照
        """
        snapshot = {
            "date": target_date.isoformat(),
            "garmin": {},
            "checkins": [],
            "weight": None,
            "blood_pressure": None,
        }

        # Garmin 数据
        garmin = self.db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == target_date
        ).first()
        if garmin:
            snapshot["garmin"] = {
                "steps": garmin.steps,
                "distance_km": round(garmin.distance_meters / 1000, 2) if garmin.distance_meters else None,
                "calories_burned": garmin.calories_burned,
                "active_calories": garmin.active_calories,
                "resting_heart_rate": garmin.resting_heart_rate,
                "max_heart_rate": garmin.max_heart_rate,
                "avg_heart_rate": garmin.avg_heart_rate,
                "sleep_score": garmin.sleep_score,
                "sleep_hours": round(garmin.total_sleep_duration / 60, 2) if garmin.total_sleep_duration else None,
                "deep_sleep_minutes": garmin.deep_sleep_duration,
                "light_sleep_minutes": garmin.light_sleep_duration,
                "rem_sleep_minutes": garmin.rem_sleep_duration,
                "stress_level": garmin.stress_level,
                "body_battery_most_charged": garmin.body_battery_most_charged,
                "body_battery_lowest": garmin.body_battery_lowest,
            }

        # 打卡记录
        checkins = self.db.query(CheckinRecord).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date == target_date
        ).all()
        snapshot["checkins"] = [
            {
                "template_name": c.template.name if c.template else "Unknown",
                "category": c.template.category if c.template else None,
                "value": c.value,
                "time": c.checkin_time.isoformat() if c.checkin_time else None,
                "note": c.notes
            }
            for c in checkins
        ]

        # 体重记录
        weight = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id,
            WeightRecord.record_date == target_date
        ).first()
        if weight:
            snapshot["weight"] = {
                "weight_kg": float(weight.weight),
                "body_fat_percentage": float(weight.body_fat_percentage) if weight.body_fat_percentage else None
            }

        # 血压记录
        bp = self.db.query(BloodPressureRecord).filter(
            BloodPressureRecord.user_id == user_id,
            BloodPressureRecord.record_date == target_date
        ).first()
        if bp:
            snapshot["blood_pressure"] = {
                "systolic": bp.systolic,
                "diastolic": bp.diastolic,
                "pulse": bp.pulse
            }

        return snapshot

    async def _get_user_profile_context(self, user_id: int) -> Dict[str, Any]:
        """获取用户画像上下文"""
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            return {}

        return {
            "age": profile.age,
            "gender": profile.gender,
            "height_cm": float(profile.height_cm) if profile.height_cm else None,
            "current_weight_kg": float(profile.current_weight_kg) if profile.current_weight_kg else None,
            "target_weight_kg": float(profile.target_weight_kg) if profile.target_weight_kg else None,
            "chronic_conditions": profile.chronic_conditions or [],
            "allergies": profile.allergies or [],
            "current_medications": profile.current_medications or [],
        }

    async def _get_health_goals(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户健康目标"""
        goals = self.db.query(HealthGoal).filter(
            HealthGoal.user_id == user_id,
            HealthGoal.status == "active"
        ).all()

        return [
            {
                "goal_type": g.goal_type,
                "target_value": float(g.target_value) if g.target_value else None,
                "current_value": float(g.current_value) if g.current_value else None,
                "description": g.description
            }
            for g in goals
        ]

    async def _get_recent_meals(self, user_id: int, days: int = 1) -> List[Dict[str, Any]]:
        """获取近期饮食记录"""
        cutoff_date = date.today() - timedelta(days=days)
        diet_records = self.db.query(DietRecord).filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= cutoff_date
        ).order_by(DietRecord.record_date.desc(), DietRecord.meal_time.desc()).all()

        return [
            {
                "type": d.meal_type,
                "time": d.meal_time.isoformat() if d.meal_time else None,
                "food_items": d.food_items,
                "calories": d.calories,
                "note": d.notes
            }
            for d in diet_records
        ]

    # ========== OpenClaw 调用方法 ==========

    async def _call_openclaw(self, system_prompt: str, user_message: str) -> Optional[str]:
        """调用 OpenClaw API 生成内容"""
        if not self.openclaw_key:
            logger.error("OpenClaw API key not configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.openclaw_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openclaw_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.openclaw_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    }
                )

                if response.status_code != 200:
                    logger.error(f"OpenClaw API error: {response.status_code} - {response.text}")
                    return None

                data = response.json()
                return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"Failed to call OpenClaw API: {e}")
            return None

    # ========== 每日复盘生成 ==========

    async def generate_daily_insight(self, user_id: int, target_date: date = None, force_regenerate: bool = False) -> Optional[AIInsight]:
        """
        生成每日健康洞察

        Args:
            user_id: 用户ID
            target_date: 目标日期，默认为昨天
            force_regenerate: 是否强制重新生成（覆盖已有洞察）
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)  # 默认昨天

        # 检查是否已经生成过
        existing = self.db.query(AIInsight).filter(
            AIInsight.user_id == user_id,
            AIInsight.review_date == target_date
        ).first()
        if existing:
            if force_regenerate:
                # 删除旧的洞察，重新生成
                logger.info(f"Force regenerating daily insight for user {user_id} on {target_date}")
                self.db.delete(existing)
                self.db.commit()
            else:
                logger.info(f"Daily insight already exists for user {user_id} on {target_date}")
                return existing

        # 聚合健康数据
        snapshot = await self._aggregate_health_snapshot(user_id, target_date)
        profile = await self._get_user_profile_context(user_id)
        goals = await self._get_health_goals(user_id)

        # 构建 AI 提示词
        system_prompt = self._build_daily_review_system_prompt()
        user_message = self._build_daily_review_user_message(target_date, snapshot, profile, goals)

        # 调用 AI 生成复盘
        content = await self._call_openclaw(system_prompt, user_message)
        if not content:
            logger.error(f"Failed to generate daily insight for user {user_id}")
            return None

        # 提取摘要（第一段或前100字）
        summary = content.split('\n\n')[0][:200] if content else ""

        # 保存到数据库
        insight = AIInsight(
            user_id=user_id,
            review_date=target_date,
            content=content,
            summary=summary,
            health_snapshot=snapshot
        )
        self.db.add(insight)
        self.db.commit()
        self.db.refresh(insight)

        logger.info(f"Generated daily insight for user {user_id} on {target_date}")
        return insight

    def _build_daily_review_system_prompt(self) -> str:
        """构建每日复盘的系统提示词"""
        return """你是一个专业的健康顾问。你的任务是基于用户的健康数据，生成一份简洁、实用的每日健康复盘。

复盘要求：
1. 使用中文，语气温暖友好，像朋友聊天一样
2. 重点关注数据中的亮点和需要改进的地方
3. 给出 2-3 条具体、可执行的建议
4. 使用 Markdown 格式，包含标题、列表、表格（如适用）
5. 总长度控制在 500 字以内

输出格式：
## 📊 昨日表现

[简要总结昨日整体表现]

### ✨ 做得好的地方

- [亮点1]
- [亮点2]

### 💪 可以改进

- [改进点1]
- [改进点2]

## 🎯 今日建议

1. [具体建议1]
2. [具体建议2]
3. [具体建议3]"""

    def _build_daily_review_user_message(
        self,
        target_date: date,
        snapshot: Dict[str, Any],
        profile: Dict[str, Any],
        goals: List[Dict[str, Any]]
    ) -> str:
        """构建每日复盘的用户消息"""
        msg = f"请为用户生成 {target_date} 的健康复盘。\n\n"

        # 用户画像
        if profile:
            msg += "**用户信息：**\n"
            if profile.get("age"):
                msg += f"- 年龄：{profile['age']} 岁\n"
            if profile.get("gender"):
                msg += f"- 性别：{profile['gender']}\n"
            if profile.get("current_weight_kg") and profile.get("target_weight_kg"):
                msg += f"- 体重：当前 {profile['current_weight_kg']} kg，目标 {profile['target_weight_kg']} kg\n"
            msg += "\n"

        # 健康目标
        if goals:
            msg += "**健康目标：**\n"
            for g in goals:
                msg += f"- {g.get('goal_type')}: {g.get('description', '')}\n"
            msg += "\n"

        # Garmin 数据
        garmin = snapshot.get("garmin", {})
        if garmin:
            msg += "**昨日数据：**\n"
            if garmin.get("steps"):
                msg += f"- 步数：{garmin['steps']} 步\n"
            if garmin.get("sleep_score"):
                msg += f"- 睡眠分数：{garmin['sleep_score']}（{garmin.get('sleep_hours', 0)}小时）\n"
            if garmin.get("resting_heart_rate"):
                msg += f"- 静息心率：{garmin['resting_heart_rate']} bpm\n"
            if garmin.get("stress_level"):
                msg += f"- 压力水平：{garmin['stress_level']}\n"
            if garmin.get("body_battery_most_charged"):
                msg += f"- 身体电量：{garmin['body_battery_lowest']}-{garmin['body_battery_most_charged']}\n"
            msg += "\n"

        # 打卡记录
        checkins = snapshot.get("checkins", [])
        if checkins:
            msg += f"**打卡记录：** 完成 {len(checkins)} 项\n\n"

        # 体重血压
        if snapshot.get("weight"):
            msg += f"**体重：** {snapshot['weight']['weight_kg']} kg\n"
        if snapshot.get("blood_pressure"):
            bp = snapshot["blood_pressure"]
            msg += f"**血压：** {bp['systolic']}/{bp['diastolic']} mmHg\n"

        return msg

    # ========== 实时建议生成 ==========

    async def generate_realtime_recommendation(
        self,
        user_id: int,
        latitude: float = None,
        longitude: float = None,
        city: str = None
    ) -> Optional[RealtimeRecommendation]:
        """
        生成实时健康建议
        基于：当前时间、天气、空气质量、身体状态、近期饮食等
        """
        # 获取天气和空气质量
        weather_context = await weather_service.get_comprehensive_context(city, latitude, longitude)

        # 获取用户最新健康数据
        latest_garmin = self.db.query(GarminData).filter(
            GarminData.user_id == user_id
        ).order_by(GarminData.record_date.desc()).first()

        # 获取近期饮食
        recent_meals = await self._get_recent_meals(user_id, days=1)

        # 获取用户画像和目标
        profile = await self._get_user_profile_context(user_id)
        goals = await self._get_health_goals(user_id)

        # 构建上下文
        context_data = {
            "current_time": datetime.now().isoformat(),
            "weather": weather_context.get("weather"),
            "air_quality": weather_context.get("air_quality"),
            "latest_health": self._extract_latest_health(latest_garmin),
            "recent_meals": recent_meals,
            "profile": profile,
            "goals": goals
        }

        # 构建 AI 提示词
        system_prompt = self._build_realtime_recommendation_system_prompt()
        user_message = self._build_realtime_recommendation_user_message(context_data)

        # 调用 AI 生成建议
        content = await self._call_openclaw(system_prompt, user_message)
        if not content:
            logger.error(f"Failed to generate recommendation for user {user_id}")
            return None

        # 分析建议类型和优先级
        rec_type, priority = self._analyze_recommendation(content, context_data)

        # 保存到数据库
        recommendation = RealtimeRecommendation(
            user_id=user_id,
            content=content,
            recommendation_type=rec_type,
            priority=priority,
            context_data=context_data,
            location=weather_context.get("location"),
            weather_data=weather_context.get("weather"),
            air_quality_data=weather_context.get("air_quality"),
            expires_at=datetime.now() + timedelta(hours=3)  # 3小时后过期
        )
        self.db.add(recommendation)
        self.db.commit()
        self.db.refresh(recommendation)

        logger.info(f"Generated realtime recommendation for user {user_id}")
        return recommendation

    def _extract_latest_health(self, garmin: Optional[GarminData]) -> Dict[str, Any]:
        """提取最新健康数据"""
        if not garmin:
            return {}
        return {
            "date": garmin.record_date.isoformat() if garmin.record_date else None,
            "steps": garmin.steps,
            "sleep_score": garmin.sleep_score,
            "resting_heart_rate": garmin.resting_heart_rate,
            "stress_level": garmin.stress_level,
            "body_battery": garmin.body_battery_most_charged
        }

    def _build_realtime_recommendation_system_prompt(self) -> str:
        """构建实时建议的系统提示词"""
        return """你是一个贴心的健康助手。基于用户当前的时间、天气、身体状态、饮食等多维度信息，给出实时的、个性化的健康建议。

建议要求：
1. 简洁明了，3-5句话
2. 具体可执行
3. 考虑当前时间和环境
4. 语气温暖友好
5. 使用 Markdown 格式

示例：
🌤️ **现在是下午3点，天气晴朗**

根据你今天的数据和当前环境：
- 身体电量充足（92），压力水平低（12）
- 空气质量优（AQI: 35）
- 适合进行30-45分钟的户外跑步或快走

💡 **建议：** 趁着好天气出去运动！记得补充水分。"""

    def _build_realtime_recommendation_user_message(self, context: Dict[str, Any]) -> str:
        """构建实时建议的用户消息"""
        msg = "请基于以下信息，给出实时健康建议：\n\n"

        # 时间
        current_time = datetime.fromisoformat(context["current_time"])
        msg += f"**当前时间：** {current_time.strftime('%Y-%m-%d %H:%M')}\n\n"

        # 天气
        weather = context.get("weather")
        if weather:
            msg += f"**天气：** {weather.get('weather_condition')}，{weather.get('temperature')}°C（体感{weather.get('feels_like')}°C），湿度{weather.get('humidity')}%\n\n"

        # 空气质量
        air = context.get("air_quality")
        if air:
            msg += f"**空气质量：** AQI {air.get('aqi')} - {air.get('quality_level')}\n\n"

        # 最新健康数据
        health = context.get("latest_health", {})
        if health:
            msg += "**今日身体状态：**\n"
            if health.get("steps"):
                msg += f"- 已走 {health['steps']} 步\n"
            if health.get("stress_level"):
                msg += f"- 压力水平：{health['stress_level']}\n"
            if health.get("body_battery"):
                msg += f"- 身体电量峰值：{health['body_battery']}\n"
            msg += "\n"

        # 近期饮食
        meals = context.get("recent_meals", [])
        if meals:
            msg += f"**近期饮食：** 最近摄入 {len(meals)} 餐\n\n"

        # 目标
        goals = context.get("goals", [])
        if goals:
            msg += "**健康目标：**\n"
            for g in goals:
                msg += f"- {g.get('goal_type')}\n"
            msg += "\n"

        return msg

    def _analyze_recommendation(self, content: str, context: Dict[str, Any]) -> tuple[str, str]:
        """分析建议类型和优先级"""
        # 简单的规则判断
        rec_type = "general"
        priority = "medium"

        content_lower = content.lower()

        # 根据内容判断类型
        if any(word in content_lower for word in ["运动", "锻炼", "活动", "跑步", "走路"]):
            rec_type = "exercise"
        elif any(word in content_lower for word in ["饮食", "吃", "餐", "营养"]):
            rec_type = "diet"
        elif any(word in content_lower for word in ["休息", "睡觉", "放松"]):
            rec_type = "rest"
        elif any(word in content_lower for word in ["注意", "警惕", "避免"]):
            rec_type = "alert"

        # 根据上下文判断优先级
        air = context.get("air_quality")
        if air and air.get("aqi", 0) > 150:
            priority = "high"
        health = context.get("latest_health", {})
        if health.get("stress_level", 0) > 70:
            priority = "high"

        return rec_type, priority
