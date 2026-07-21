"""微信小程序订阅消息推送服务"""
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import os
import json

logger = logging.getLogger(__name__)


# ============ 订阅消息模板配置 ============
# 在微信公众平台申请模板后，将模板ID配置到环境变量或此处

# 模板类型到环境变量名的映射
TEMPLATE_ENV_MAPPING = {
    "reminder": "WECHAT_TEMPLATE_REMINDER",           # 健康提醒
    "morning_briefing": "WECHAT_TEMPLATE_BRIEFING",   # 早间简报
    "health_alert": "WECHAT_TEMPLATE_ALERT",          # 健康预警
    "goal_progress": "WECHAT_TEMPLATE_GOAL",          # 目标进度
    "weekly_report": "WECHAT_TEMPLATE_WEEKLY",        # 周报
}

# 模板数据字段配置（根据实际申请的模板调整）
# 微信订阅消息模板字段通常为 thing1, thing2, time3 等格式
TEMPLATE_FIELD_MAPPING = {
    "reminder": {
        "title_field": "thing1",      # 提醒标题
        "content_field": "thing2",    # 提醒内容
        "time_field": "time3",        # 提醒时间
    },
    "morning_briefing": {
        "title_field": "thing1",      # 报告名称
        "content_field": "thing2",    # 报告内容
        "time_field": "time3",        # 报告时间
    },
    "health_alert": {
        "title_field": "thing1",      # 预警类型
        "content_field": "thing2",    # 预警内容
        "time_field": "time3",        # 预警时间
    },
    "goal_progress": {
        "title_field": "thing1",      # 目标名称
        "content_field": "thing2",    # 当前进度
        "time_field": "time3",        # 更新时间
    },
    "weekly_report": {
        "title_field": "thing1",      # 报告名称
        "content_field": "thing2",    # 主要指标
        "time_field": "time3",        # 报告周期
    },
}


def get_template_id(notification_type: str) -> Optional[str]:
    """
    获取模板ID

    优先级：
    1. 环境变量配置
    2. 用户订阅时保存的模板ID（需要从数据库获取）
    """
    env_key = TEMPLATE_ENV_MAPPING.get(notification_type)
    if env_key:
        template_id = os.getenv(env_key, "")
        if template_id:
            return template_id
    return None


class WeChatPushService:
    """
    微信小程序订阅消息推送服务

    使用说明：
    1. 在微信公众平台配置订阅消息模板
    2. 用户在小程序中订阅消息
    3. 通过此服务发送订阅消息

    环境变量：
    - WECHAT_MINI_APP_ID / WECHAT_APPID: 小程序 AppID
    - WECHAT_MINI_APP_SECRET / WECHAT_SECRET: 小程序 AppSecret
    - WECHAT_TEMPLATE_REMINDER: 健康提醒模板ID
    - WECHAT_TEMPLATE_BRIEFING: 早间简报模板ID
    - WECHAT_TEMPLATE_ALERT: 健康预警模板ID
    - WECHAT_TEMPLATE_GOAL: 目标进度模板ID
    - WECHAT_TEMPLATE_WEEKLY: 周报模板ID
    """

    # 微信 API 地址
    ACCESS_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    SUBSCRIBE_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"

    def __init__(self):
        # 支持多种环境变量名
        self.app_id = os.getenv("WECHAT_MINI_APP_ID") or os.getenv("WECHAT_APPID", "")
        self.app_secret = os.getenv("WECHAT_MINI_APP_SECRET") or os.getenv("WECHAT_SECRET", "")
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    @property
    def is_configured(self) -> bool:
        """检查是否已配置微信"""
        return bool(self.app_id and self.app_secret)

    async def get_access_token(self) -> Optional[str]:
        """
        获取 access_token（带缓存）

        微信 access_token 有效期为 2 小时
        """
        if not self.is_configured:
            logger.warning("微信小程序未配置，无法获取 access_token")
            return None

        # 检查缓存
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                return self._access_token

        # 请求新 token
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.ACCESS_TOKEN_URL,
                    params={
                        "grant_type": "client_credential",
                        "appid": self.app_id,
                        "secret": self.app_secret
                    },
                    timeout=10
                )

                data = response.json()

                if "access_token" in data:
                    self._access_token = data["access_token"]
                    # 提前 5 分钟过期
                    expires_in = data.get("expires_in", 7200) - 300
                    self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                    logger.info("微信 access_token 获取成功")
                    return self._access_token
                else:
                    logger.error(
                        "获取微信 access_token 失败: errcode=%s errmsg=%s",
                        data.get("errcode"),
                        data.get("errmsg", "未知错误"),
                    )
                    return None

        except Exception as e:
            logger.error("获取微信 access_token 异常 error_type=%s", type(e).__name__)
            return None

    async def send_subscription_message(
        self,
        openid: str,
        template_id: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]] = None,
        page: Optional[str] = None,
        miniprogram_state: str = "formal",
        notification_type: str = "reminder"
    ) -> Dict[str, Any]:
        """
        发送订阅消息

        Args:
            openid: 用户 OpenID
            template_id: 订阅消息模板 ID
            title: 标题（会映射到模板的某个字段）
            content: 内容
            data: 模板数据（格式根据模板定义），如果为None则自动构建
            page: 点击跳转页面
            miniprogram_state: developer/trial/formal
            notification_type: 通知类型，用于构建模板数据

        Returns:
            {"success": bool, "error": str}
        """
        if not self.is_configured:
            logger.warning("微信小程序未配置 AppID/Secret，无法发送订阅消息")
            return {"success": False, "error": "微信小程序未配置"}

        if not openid:
            return {"success": False, "error": "缺少用户 openid"}

        # 如果没有传入 template_id，尝试从环境变量获取
        if not template_id:
            template_id = get_template_id(notification_type)
            if not template_id:
                logger.warning(f"未配置 {notification_type} 类型的模板ID")
                return {"success": False, "error": f"未配置 {notification_type} 模板ID"}

        access_token = await self.get_access_token()
        if not access_token:
            return {"success": False, "error": "获取 access_token 失败"}

        # 构建模板数据
        if data:
            template_data = data
        else:
            template_data = self._build_default_template_data(title, content, notification_type)

        payload = {
            "touser": openid,
            "template_id": template_id,
            "data": template_data,
            "miniprogram_state": miniprogram_state
        }

        if page:
            payload["page"] = page

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.SUBSCRIBE_SEND_URL}?access_token={access_token}",
                    json=payload,
                    timeout=10
                )

                result = response.json()

                if result.get("errcode") == 0:
                    logger.info(f"微信订阅消息发送成功: openid={openid[:10]}..., type={notification_type}")
                    return {"success": True}
                else:
                    error_code = result.get("errcode")
                    error_msg = result.get("errmsg", "未知错误")

                    # 特殊错误码处理
                    if error_code == 43101:
                        # 用户拒绝接受消息
                        logger.warning(f"用户拒绝接收订阅消息: openid={openid[:10]}...")
                        return {"success": False, "error": "用户未订阅此类消息"}
                    elif error_code == 47003:
                        # 模板参数不正确
                        logger.error(
                            "微信模板参数错误: errcode=%s errmsg=%s notification_type=%s",
                            error_code,
                            error_msg,
                            notification_type,
                        )
                        return {"success": False, "error": "模板参数格式错误"}
                    else:
                        logger.error(f"微信订阅消息发送失败: errcode={error_code}, errmsg={error_msg}")
                        return {"success": False, "error": f"发送失败({error_code})"}

        except Exception as e:
            logger.error(f"微信订阅消息发送异常: {e}")
            return {"success": False, "error": str(e)}

    async def send_health_reminder(
        self,
        openid: str,
        template_id: str,
        reminder_title: str,
        reminder_content: str,
        page: str = "pages/index/index"
    ) -> Dict[str, Any]:
        """
        发送健康提醒消息

        便捷方法，用于发送洗鼻、喝水、运动等提醒
        """
        return await self.send_subscription_message(
            openid=openid,
            template_id=template_id,
            title=reminder_title,
            content=reminder_content,
            page=page,
            notification_type="reminder"
        )

    async def send_morning_briefing(
        self,
        openid: str,
        template_id: str,
        greeting: str,
        summary: str,
        page: str = "pages/index/index"
    ) -> Dict[str, Any]:
        """
        发送早间简报消息
        """
        return await self.send_subscription_message(
            openid=openid,
            template_id=template_id,
            title=greeting,
            content=summary,
            page=page,
            notification_type="morning_briefing"
        )

    async def send_health_alert(
        self,
        openid: str,
        template_id: str,
        alert_title: str,
        alert_content: str,
        page: str = "pages/index/index"
    ) -> Dict[str, Any]:
        """
        发送健康预警消息
        """
        return await self.send_subscription_message(
            openid=openid,
            template_id=template_id,
            title=alert_title,
            content=alert_content,
            page=page,
            notification_type="health_alert"
        )

    def _build_default_template_data(
        self,
        title: str,
        content: str,
        notification_type: str = "reminder"
    ) -> Dict[str, Any]:
        """
        构建模板数据

        根据不同的通知类型使用不同的字段映射

        微信订阅消息限制：
        - thing 类型：20个字符
        - time 类型：需要符合时间格式
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 获取字段映射
        field_mapping = TEMPLATE_FIELD_MAPPING.get(notification_type, {
            "title_field": "thing1",
            "content_field": "thing2",
            "time_field": "time3",
        })

        # 截断文本以符合微信限制
        title_truncated = title[:20] if title else "健康提醒"
        content_truncated = content[:20] if content else "点击查看详情"

        return {
            field_mapping["title_field"]: {"value": title_truncated},
            field_mapping["content_field"]: {"value": content_truncated},
            field_mapping["time_field"]: {"value": now},
        }

    def build_template_data_for_type(
        self,
        notification_type: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        根据通知类型构建模板数据

        Args:
            notification_type: 通知类型
            **kwargs: 模板字段值

        Returns:
            格式化的模板数据
        """
        field_mapping = TEMPLATE_FIELD_MAPPING.get(notification_type, {})
        data = {}

        for field_name, template_field in field_mapping.items():
            # 从 kwargs 中获取值，如 title_field -> title
            key = field_name.replace("_field", "")
            value = kwargs.get(key, "")

            if value:
                # 截断以符合微信限制
                if "thing" in template_field:
                    value = str(value)[:20]
                data[template_field] = {"value": value}

        return data


# ============ 微信订阅消息模板配置 ============

# 以下是推荐的订阅消息模板类型和对应的模板选择建议
# 实际模板ID需要在微信公众平台申请

WECHAT_TEMPLATE_SUGGESTIONS = {
    "morning_briefing": {
        "title": "每日健康报告提醒",
        "category": "IT科技 - 健康管理",
        "keywords": ["报告名称", "报告时间", "报告内容", "备注"]
    },
    "reminder": {
        "title": "健康提醒通知",
        "category": "IT科技 - 健康管理",
        "keywords": ["提醒内容", "提醒时间", "备注"]
    },
    "health_alert": {
        "title": "健康预警通知",
        "category": "IT科技 - 健康管理",
        "keywords": ["预警类型", "预警内容", "建议措施", "预警时间"]
    },
    "goal_progress": {
        "title": "目标进度提醒",
        "category": "IT科技 - 健康管理",
        "keywords": ["目标名称", "当前进度", "剩余天数", "备注"]
    },
    "weekly_report": {
        "title": "周报通知",
        "category": "IT科技 - 健康管理",
        "keywords": ["报告名称", "报告周期", "主要指标", "备注"]
    }
}
