"""iOS APNs 推送服务"""
import logging
import os
import json
import time
import jwt
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class IOSPushService:
    """
    iOS APNs 推送服务

    使用 Apple Push Notification service (APNs) 发送推送通知

    配置方式（二选一）：
    1. 证书方式（.p12 文件）- 传统方式
    2. 密钥方式（.p8 文件）- 推荐方式，JWT Token

    环境变量：
    - APNS_KEY_ID: APNs 密钥 ID
    - APNS_TEAM_ID: Apple 团队 ID
    - APNS_KEY_PATH: .p8 密钥文件路径
    - APNS_BUNDLE_ID: App Bundle ID
    - APNS_USE_SANDBOX: 是否使用沙盒环境 (true/false)
    """

    # APNs 服务器地址
    APNS_PRODUCTION = "https://api.push.apple.com"
    APNS_SANDBOX = "https://api.sandbox.push.apple.com"

    def __init__(self):
        from app.config import settings
        self.key_id = settings.apns_key_id or ""
        self.team_id = settings.apns_team_id or ""
        self.key_path = settings.apns_key_path or settings.apns_private_key_path or ""
        self.bundle_id = settings.apns_bundle_id or "life.executor.health"
        self.use_sandbox = bool(getattr(settings, "apns_use_sandbox", False))

        self._private_key: Optional[str] = None
        self._jwt_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    @property
    def is_configured(self) -> bool:
        """检查是否已配置 APNs"""
        return bool(self.key_id and self.team_id and self.key_path and os.path.exists(self.key_path))

    @property
    def base_url(self) -> str:
        """获取 APNs 服务器地址"""
        return self.APNS_SANDBOX if self.use_sandbox else self.APNS_PRODUCTION

    def _load_private_key(self) -> Optional[str]:
        """加载私钥"""
        if self._private_key:
            return self._private_key

        if not self.key_path or not os.path.exists(self.key_path):
            logger.warning(f"APNs 私钥文件不存在: {self.key_path}")
            return None

        try:
            with open(self.key_path, "r") as f:
                self._private_key = f.read()
            return self._private_key
        except Exception as e:
            logger.error(f"加载 APNs 私钥失败: {e}")
            return None

    def _generate_jwt_token(self) -> Optional[str]:
        """
        生成 JWT Token

        APNs JWT Token 有效期最长 1 小时
        """
        # 检查缓存
        if self._jwt_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                return self._jwt_token

        private_key = self._load_private_key()
        if not private_key:
            return None

        try:
            now = int(time.time())

            headers = {
                "alg": "ES256",
                "kid": self.key_id
            }

            payload = {
                "iss": self.team_id,
                "iat": now
            }

            self._jwt_token = jwt.encode(
                payload,
                private_key,
                algorithm="ES256",
                headers=headers
            )

            # Token 有效期设为 50 分钟（留 10 分钟余量）
            self._token_expires_at = datetime.now() + timedelta(minutes=50)

            logger.info("APNs JWT Token 生成成功")
            return self._jwt_token

        except Exception as e:
            logger.error(f"生成 APNs JWT Token 失败: {e}")
            return None

    async def send_push(
        self,
        device_token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        badge: Optional[int] = None,
        sound: str = "default",
        category: Optional[str] = None,
        priority: int = 10,
        expiration: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        发送 iOS 推送通知

        Args:
            device_token: 设备 Token
            title: 通知标题
            body: 通知正文
            data: 自定义数据
            badge: 角标数字
            sound: 提示音
            category: 通知类别
            priority: 优先级 (10=立即, 5=省电模式)
            expiration: 过期时间戳

        Returns:
            {"success": bool, "error": str, "apns_id": str}
        """
        if not self.is_configured:
            logger.warning(f"APNs 未配置，推送未发送: {title}")
            return {"success": False, "error": "APNs not configured", "simulated": True}

        if not device_token:
            return {"success": False, "error": "缺少 device_token"}

        jwt_token = self._generate_jwt_token()
        if not jwt_token:
            return {"success": False, "error": "生成 JWT Token 失败"}

        # 构建 APNs payload
        aps = {
            "alert": {
                "title": title,
                "body": body
            },
            "sound": sound
        }

        if badge is not None:
            aps["badge"] = badge

        if category:
            aps["category"] = category

        payload = {"aps": aps}

        if data:
            payload.update(data)

        # 发送请求
        url = f"{self.base_url}/3/device/{device_token}"

        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": self.bundle_id,
            "apns-priority": str(priority),
            "apns-push-type": "alert"
        }

        if expiration:
            headers["apns-expiration"] = str(expiration)

        try:
            async with httpx.AsyncClient(http2=True) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )

                if response.status_code == 200:
                    apns_id = response.headers.get("apns-id", "")
                    logger.info(f"APNs 推送成功: apns_id={apns_id}")
                    return {"success": True, "apns_id": apns_id}
                else:
                    try:
                        error_data = response.json()
                        error_reason = error_data.get("reason", "Unknown")
                    except:
                        error_reason = response.text or f"HTTP {response.status_code}"

                    logger.error(f"APNs 推送失败: {error_reason}")
                    return {"success": False, "error": error_reason}

        except Exception as e:
            logger.error(f"APNs 推送异常: {e}")
            return {"success": False, "error": str(e)}

    async def send_silent_push(
        self,
        device_token: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送静默推送（后台刷新数据）

        Args:
            device_token: 设备 Token
            data: 自定义数据

        Returns:
            {"success": bool, "error": str}
        """
        if not self.is_configured:
            logger.info("APNs 未配置，跳过静默推送")
            return {"success": True, "simulated": True}

        jwt_token = self._generate_jwt_token()
        if not jwt_token:
            return {"success": False, "error": "生成 JWT Token 失败"}

        payload = {
            "aps": {
                "content-available": 1
            }
        }
        payload.update(data)

        url = f"{self.base_url}/3/device/{device_token}"

        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": self.bundle_id,
            "apns-priority": "5",  # 低优先级
            "apns-push-type": "background"
        }

        try:
            async with httpx.AsyncClient(http2=True) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )

                if response.status_code == 200:
                    return {"success": True}
                else:
                    return {"success": False, "error": response.text}

        except Exception as e:
            return {"success": False, "error": str(e)}


# ============ APNs 配置指南 ============

APNS_SETUP_GUIDE = """
# iOS APNs 推送配置指南

## 1. 创建 APNs Key（推荐方式）

1. 登录 Apple Developer Portal
2. 进入 Certificates, Identifiers & Profiles
3. 选择 Keys -> Create a Key
4. 勾选 Apple Push Notifications service (APNs)
5. 下载 .p8 文件（只能下载一次！）
6. 记录 Key ID

## 2. 配置环境变量

```bash
# .env 文件
APNS_KEY_ID=XXXXXXXXXX           # Key ID
APNS_TEAM_ID=XXXXXXXXXX          # Team ID
APNS_KEY_PATH=/path/to/AuthKey.p8
APNS_BUNDLE_ID=life.executor.health
APNS_USE_SANDBOX=true            # 开发环境用 true，生产环境用 false
```

## 3. iOS App 端配置

在 AppDelegate.swift 中注册推送：

```swift
import UIKit
import UserNotifications

@main
class AppDelegate: UIResponder, UIApplicationDelegate {

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        registerForPushNotifications()
        return true
    }

    func registerForPushNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        // 发送到服务器保存
        print("Device Token: \\(token)")
    }
}
```

## 4. Capacitor 集成（如使用 Capacitor）

```bash
npm install @capacitor/push-notifications
npx cap sync
```

```typescript
import { PushNotifications } from '@capacitor/push-notifications';

// 注册推送
await PushNotifications.requestPermissions();
await PushNotifications.register();

// 获取 token
PushNotifications.addListener('registration', (token) => {
  console.log('Push token:', token.value);
  // 发送到服务器
});
```
"""
