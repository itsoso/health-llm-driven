"""
聊天服务 - 通过 OpenClaw 提供 AI 对话能力
利用 OpenClaw 的 OpenAI 兼容 API，注入用户健康上下文
"""
import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.basic_health import BasicHealthData
from app.models.daily_health import GarminData
from app.models.checkin import CheckinRecord, CheckinTemplate
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.chat import ChatConversation, ChatMessage
from app.services.environment.weather_service import weather_service

logger = logging.getLogger(__name__)

# OpenClaw 配置
OPENCLAW_BASE_URL = settings.openclaw_base_url
OPENCLAW_API_KEY = settings.openclaw_api_key or ""
OPENCLAW_MODEL = settings.openclaw_model


class ChatService:
    """聊天服务"""

    def __init__(self, db: Session):
        self.db = db

    def _build_health_context(self, user_id: int) -> str:
        """构建用户健康上下文，注入为 system prompt"""
        parts = []
        today = date.today()

        # 用户基本信息
        user = self.db.query(User).filter(User.id == user_id).first()
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

        # 用户位置信息
        user_city = None
        if profile:
            # 优先使用手动设置的位置
            if profile.use_manual_location and profile.manual_location:
                manual_loc = profile.manual_location
                if isinstance(manual_loc, dict):
                    user_city = manual_loc.get('city')
                    if user_city:
                        location_info = f"位置: {manual_loc.get('province', '')}{user_city}"
                        parts.append(location_info)
            # 其次使用IP检测的位置
            elif profile.detected_location:
                detected_loc = profile.detected_location
                if isinstance(detected_loc, dict):
                    user_city = detected_loc.get('city')
                    if user_city:
                        location_info = f"位置: {detected_loc.get('province', '')}{user_city}"
                        parts.append(location_info)
            # 兜底使用city字段
            elif profile.city:
                user_city = profile.city
                parts.append(f"位置: {user_city}")

        # 获取当前天气信息
        if user_city:
            try:
                weather = weather_service.get_current_weather(user_city)
                if weather:
                    weather_info = f"当前天气: {weather.get('text', '')}, 温度{weather.get('temp', '')}℃"
                    if weather.get('feelsLike'):
                        weather_info += f", 体感{weather.get('feelsLike')}℃"
                    if weather.get('humidity'):
                        weather_info += f", 湿度{weather.get('humidity')}%"
                    if weather.get('windDir') and weather.get('windScale'):
                        weather_info += f", {weather.get('windDir')}{weather.get('windScale')}级"
                    parts.append(weather_info)
            except Exception as e:
                logger.warning(f"获取天气信息失败: {e}")

        if user:
            info = f"用户: {user.name or user.username}"
            if user.gender:
                info += f", 性别: {user.gender}"
            if user.birth_date:
                age = today.year - user.birth_date.year
                info += f", 年龄: {age}岁"
            parts.append(info)

        if profile:
            if profile.height_cm:
                parts.append(f"身高: {profile.height_cm}cm")
            if profile.chronic_conditions:
                parts.append(f"慢性病: {', '.join(profile.chronic_conditions)}")
            if profile.allergies:
                parts.append(f"过敏: {', '.join(profile.allergies)}")
            if profile.current_medications:
                med_names = []
                for m in profile.current_medications:
                    if isinstance(m, dict):
                        med_names.append(m.get("name", str(m)))
                    else:
                        med_names.append(str(m))
                if med_names:
                    parts.append(f"用药: {', '.join(med_names)}")
            goals = []
            if profile.target_weight_kg:
                goals.append(f"目标体重{profile.target_weight_kg}kg")
            if profile.target_steps:
                goals.append(f"目标步数{profile.target_steps}")
            if profile.target_sleep_hours:
                goals.append(f"目标睡眠{profile.target_sleep_hours}h")
            if goals:
                parts.append(f"健康目标: {', '.join(goals)}")

        # 最近体重
        weight = self.db.query(WeightRecord).filter(
            WeightRecord.user_id == user_id
        ).order_by(WeightRecord.record_date.desc()).first()
        if weight:
            parts.append(f"最近体重: {weight.weight}kg ({weight.record_date})")

        # 最近血压
        bp = self.db.query(BloodPressureRecord).filter(
            BloodPressureRecord.user_id == user_id
        ).order_by(BloodPressureRecord.record_date.desc()).first()
        if bp:
            parts.append(f"最近血压: {bp.systolic}/{bp.diastolic}mmHg ({bp.record_date})")

        # 最近 Garmin 数据
        garmin = self.db.query(GarminData).filter(
            GarminData.user_id == user_id
        ).order_by(GarminData.record_date.desc()).first()
        if garmin:
            g_parts = [f"Garmin数据({garmin.record_date})"]
            if garmin.steps:
                g_parts.append(f"步数:{garmin.steps}")
            if garmin.resting_heart_rate:
                g_parts.append(f"静息心率:{garmin.resting_heart_rate}")
            if garmin.sleep_score:
                g_parts.append(f"睡眠分数:{garmin.sleep_score}")
            if garmin.stress_level:
                g_parts.append(f"压力水平:{garmin.stress_level}")
            if garmin.body_battery_most_charged:
                g_parts.append(f"身体电量峰值:{garmin.body_battery_most_charged}")
            parts.append(", ".join(g_parts))

        # 今日打卡记录
        checkins = self.db.query(CheckinRecord, CheckinTemplate).join(
            CheckinTemplate, CheckinRecord.template_id == CheckinTemplate.id
        ).filter(
            CheckinRecord.user_id == user_id,
            CheckinRecord.checkin_date == today
        ).all()
        if checkins:
            checkin_items = [f"{t.name}({r.value}{t.unit})" for r, t in checkins]
            if checkin_items:
                parts.append(f"今日打卡: {', '.join(checkin_items)}")

        if not parts:
            return ""

        return "以下是该用户的最新健康数据：\n" + "\n".join(parts)

    def _get_system_prompt(self, user_id: int) -> str:
        """组装完整的 system prompt"""
        base = (
            "你是一个专业的私人健康顾问。你的名字叫「健康顾问」。\n"
            "请基于用户的健康数据，提供个性化、科学、实用的健康建议。\n"
            "回答要简洁友好，避免过度医学化。如涉及严重健康问题请建议就医。\n"
            "使用中文回答。"
        )

        health_ctx = self._build_health_context(user_id)
        if health_ctx:
            return f"{base}\n\n{health_ctx}"
        return base

    async def send_message(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """发送消息到 OpenClaw 并返回回复"""

        # 获取或创建对话
        if conversation_id:
            conv = self.db.query(ChatConversation).filter(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id
            ).first()
            if not conv:
                raise ValueError("对话不存在")
        else:
            conv = ChatConversation(user_id=user_id, title=message[:50])
            self.db.add(conv)
            self.db.commit()
            self.db.refresh(conv)

        # 保存用户消息
        user_msg = ChatMessage(conversation_id=conv.id, role="user", content=message)
        self.db.add(user_msg)
        self.db.commit()

        # 构建消息列表（最近 20 条作为上下文）
        history = self.db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id
        ).order_by(ChatMessage.created_at.asc()).all()

        # 只取最近 20 条消息避免超长
        recent = history[-20:] if len(history) > 20 else history

        messages = [{"role": "system", "content": self._get_system_prompt(user_id)}]
        for msg in recent:
            messages.append({"role": msg.role, "content": msg.content})

        # 调用 OpenClaw API
        try:
            reply_content = await self._call_openclaw(messages)
        except Exception as e:
            logger.error(f"OpenClaw 调用失败: {e}")
            reply_content = "抱歉，健康顾问暂时无法响应，请稍后再试。"

        # 保存 AI 回复
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=reply_content)
        self.db.add(ai_msg)

        # 更新对话标题（首次对话用用户消息做标题）
        conv.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(ai_msg)

        return {
            "conversation_id": conv.id,
            "reply": reply_content,
            "message_id": ai_msg.id
        }

    async def _call_openclaw(self, messages: list) -> str:
        """调用 OpenClaw 的 OpenAI 兼容 API"""
        url = f"{OPENCLAW_BASE_URL}/chat/completions"

        headers = {
            "Content-Type": "application/json",
        }
        if OPENCLAW_API_KEY:
            headers["Authorization"] = f"Bearer {OPENCLAW_API_KEY}"

        payload = {
            "model": OPENCLAW_MODEL,
            "messages": messages,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        return choice.get("message", {}).get("content", "").strip()

    def get_conversations(self, user_id: int, limit: int = 20) -> List[ChatConversation]:
        """获取用户的对话列表"""
        return self.db.query(ChatConversation).filter(
            ChatConversation.user_id == user_id
        ).order_by(ChatConversation.updated_at.desc()).limit(limit).all()

    def get_conversation_messages(self, user_id: int, conversation_id: int) -> Optional[ChatConversation]:
        """获取对话详情及所有消息"""
        return self.db.query(ChatConversation).filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id
        ).first()

    def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        """删除对话"""
        conv = self.db.query(ChatConversation).filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id
        ).first()
        if not conv:
            return False
        self.db.delete(conv)
        self.db.commit()
        return True
