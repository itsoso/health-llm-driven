"""微信小程序订阅消息推送服务"""
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import os
import json

logger = logging.getLogger(__name__)


class WeChatPushService:
    """
    微信小程序订阅消息推送服务
    
    使用说明：
    1. 在微信公众平台配置订阅消息模板
    2. 用户在小程序中订阅消息
    3. 通过此服务发送订阅消息
    
    环境变量：
    - WECHAT_MINI_APP_ID: 小程序 AppID
    - WECHAT_MINI_APP_SECRET: 小程序 AppSecret
    """
    
    # 微信 API 地址
    ACCESS_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    SUBSCRIBE_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"
    
    def __init__(self):
        self.app_id = os.getenv("WECHAT_MINI_APP_ID", "")
        self.app_secret = os.getenv("WECHAT_MINI_APP_SECRET", "")
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
                    logger.error(f"获取微信 access_token 失败: {data}")
                    return None
                    
        except Exception as e:
            logger.error(f"获取微信 access_token 异常: {e}")
            return None
    
    async def send_subscription_message(
        self,
        openid: str,
        template_id: str,
        title: str,
        content: str,
        data: Optional[Dict[str, Any]] = None,
        page: Optional[str] = None,
        miniprogram_state: str = "formal"
    ) -> Dict[str, Any]:
        """
        发送订阅消息
        
        Args:
            openid: 用户 OpenID
            template_id: 订阅消息模板 ID
            title: 标题（会映射到模板的某个字段）
            content: 内容
            data: 模板数据（格式根据模板定义）
            page: 点击跳转页面
            miniprogram_state: developer/trial/formal
            
        Returns:
            {"success": bool, "error": str}
        """
        if not self.is_configured:
            return {"success": False, "error": "微信小程序未配置"}
        
        if not openid or not template_id:
            return {"success": False, "error": "缺少 openid 或 template_id"}
        
        access_token = await self.get_access_token()
        if not access_token:
            return {"success": False, "error": "获取 access_token 失败"}
        
        # 构建模板数据
        # 注意：实际的模板数据格式需要根据你在微信后台配置的模板来调整
        template_data = data if data else self._build_default_template_data(title, content)
        
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
                    logger.info(f"微信订阅消息发送成功: openid={openid[:10]}...")
                    return {"success": True}
                else:
                    error_msg = f"errcode={result.get('errcode')}, errmsg={result.get('errmsg')}"
                    logger.error(f"微信订阅消息发送失败: {error_msg}")
                    return {"success": False, "error": error_msg}
                    
        except Exception as e:
            logger.error(f"微信订阅消息发送异常: {e}")
            return {"success": False, "error": str(e)}
    
    def _build_default_template_data(self, title: str, content: str) -> Dict[str, Any]:
        """
        构建默认的模板数据
        
        实际使用时需要根据模板字段名称调整
        
        常见的健康提醒模板字段：
        - thing1: 提醒内容
        - time2: 提醒时间
        - thing3: 备注
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return {
            "thing1": {"value": title[:20]},  # 微信限制20字符
            "time2": {"value": now},
            "thing3": {"value": content[:20] if content else "点击查看详情"}
        }


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
