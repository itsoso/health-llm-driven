"""智能助理专用 OpenClaw 绑定服务"""
import base64
import hashlib
import json
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import settings
from app.models.assistant_openclaw import AssistantOpenClawBinding
from app.services.assistant_openclaw_gateway_client import (
    AssistantOpenClawGatewayAuthError,
    AssistantOpenClawGatewayClient,
    AssistantOpenClawGatewayError,
)


class AssistantOpenClawBindingService:
    """管理用户的智能助理专用 OpenClaw 绑定配置"""

    VALID_STATUSES = {"unconfigured", "active", "invalid", "disabled"}

    def __init__(self, db: Session):
        self.db = db
        encryption_key = (
            getattr(settings, "device_encryption_key", None)
            or getattr(settings, "garmin_encryption_key", None)
        )
        if not encryption_key:
            secret = settings.secret_key or "assistant-openclaw-fallback-secret"
            encryption_key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        self._fernet = Fernet(encryption_key)

    @property
    def allowed_hosts(self) -> set[str]:
        return {
            host.strip().lower()
            for host in settings.assistant_openclaw_allowed_hosts.split(",")
            if host.strip()
        }

    def get_binding(self, user_id: int) -> Optional[AssistantOpenClawBinding]:
        return (
            self.db.query(AssistantOpenClawBinding)
            .filter(AssistantOpenClawBinding.user_id == user_id)
            .first()
        )

    def get_binding_response(self, user_id: int) -> dict:
        binding = self.get_binding(user_id)
        if not binding:
            return {
                "configured": False,
                "enabled": False,
                "display_name": "我的 OpenClaw",
                "gateway_url": None,
                "gateway_token_last4": None,
                "status": "unconfigured",
                "last_tested_at": None,
                "last_error": None,
            }

        return {
            "configured": True,
            "enabled": binding.enabled,
            "display_name": binding.display_name,
            "gateway_url": binding.gateway_url,
            "gateway_token_last4": binding.gateway_token_last4,
            "status": binding.status,
            "last_tested_at": binding.last_tested_at.isoformat() if binding.last_tested_at else None,
            "last_error": binding.last_error,
        }

    def validate_gateway_url(self, gateway_url: str) -> str:
        parsed = urlparse(gateway_url.strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("OpenClaw 地址只支持 http 或 https")
        if not parsed.hostname:
            raise ValueError("OpenClaw 地址缺少主机名")
        if parsed.username or parsed.password:
            raise ValueError("OpenClaw 地址不允许包含用户名或密码")
        host = parsed.hostname.lower()
        if host not in self.allowed_hosts:
            raise ValueError("该 OpenClaw 地址不在允许范围内")
        if parsed.path and parsed.path not in {"", "/"}:
            raise ValueError("OpenClaw 地址请填写到网关根地址，不要包含额外路径")
        if parsed.query or parsed.fragment:
            raise ValueError("OpenClaw 地址不允许包含查询参数或片段")
        return f"{parsed.scheme}://{parsed.netloc}"

    def encrypt_token(self, token: str) -> str:
        return self._fernet.encrypt(token.encode()).decode()

    def decrypt_token(self, encrypted_token: str) -> str:
        return self._fernet.decrypt(encrypted_token.encode()).decode()

    def upsert_binding(
        self,
        user_id: int,
        display_name: str,
        gateway_url: str,
        enabled: bool,
        gateway_token: str | None = None,
    ) -> AssistantOpenClawBinding:
        normalized_url = self.validate_gateway_url(gateway_url)
        binding = self.get_binding(user_id)
        display_name = (display_name or "我的 OpenClaw").strip()[:100] or "我的 OpenClaw"

        if not binding:
            if not gateway_token:
                raise ValueError("首次绑定必须提供 OpenClaw Token")
            binding = AssistantOpenClawBinding(
                user_id=user_id,
                display_name=display_name,
                gateway_url=normalized_url,
                gateway_token_encrypted=self.encrypt_token(gateway_token.strip()),
                gateway_token_last4=gateway_token.strip()[-4:],
                enabled=enabled,
                status="unconfigured" if enabled else "disabled",
                last_error=None,
                last_tested_at=None,
            )
            self.db.add(binding)
        else:
            url_changed = binding.gateway_url != normalized_url
            token_changed = False
            binding.display_name = display_name
            binding.gateway_url = normalized_url
            binding.enabled = enabled
            if gateway_token:
                clean_token = gateway_token.strip()
                binding.gateway_token_encrypted = self.encrypt_token(clean_token)
                binding.gateway_token_last4 = clean_token[-4:]
                token_changed = True

            if not enabled:
                binding.status = "disabled"
                binding.last_error = None
            elif url_changed or token_changed or binding.status == "disabled":
                binding.status = "unconfigured"
                binding.last_error = None
                binding.last_tested_at = None

        self.db.commit()
        self.db.refresh(binding)
        return binding

    def delete_binding(self, user_id: int) -> bool:
        binding = self.get_binding(user_id)
        if not binding:
            return False
        self.db.delete(binding)
        self.db.commit()
        return True

    async def test_binding(
        self,
        user_id: int,
        gateway_url: str | None = None,
        gateway_token: str | None = None,
        persist_result: bool = False,
    ) -> dict:
        binding = self.get_binding(user_id)
        if gateway_url:
            normalized_url = self.validate_gateway_url(gateway_url)
        elif binding:
            normalized_url = binding.gateway_url
        else:
            raise ValueError("当前账号尚未绑定 OpenClaw")

        if gateway_token:
            clean_token = gateway_token.strip()
        elif binding:
            clean_token = self.decrypt_token(binding.gateway_token_encrypted)
        else:
            raise ValueError("当前账号尚未配置 OpenClaw Token")

        result = await self._probe_gateway(normalized_url, clean_token)

        if persist_result and binding and not gateway_url and not gateway_token:
            binding.last_tested_at = datetime.utcnow()
            binding.last_error = None if result["status"] == "active" else result["message"]
            if binding.enabled:
                binding.status = result["status"]
            self.db.commit()
            self.db.refresh(binding)

        return result

    def get_active_connection(self, user_id: int) -> tuple[str, str]:
        binding = self.get_binding(user_id)
        if not binding:
            raise ValueError("当前账号尚未绑定 OpenClaw，请先前往设置页完成绑定")
        if not binding.enabled:
            raise ValueError("当前账号的 OpenClaw 已停用，请前往设置页启用")
        if binding.status != "active":
            raise ValueError("当前账号的 OpenClaw 尚未通过连接测试，请前往设置页测试连接")
        return binding.gateway_url, self.decrypt_token(binding.gateway_token_encrypted)

    async def _probe_gateway(self, gateway_url: str, gateway_token: str) -> dict:
        start = time.perf_counter()
        client = AssistantOpenClawGatewayClient(gateway_url, gateway_token)

        try:
            status_code, payload = await client.check_health()
            if status_code != 200:
                return {
                    "reachable": True,
                    "authenticated": False,
                    "status": "invalid",
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                    "message": f"OpenClaw 返回异常状态: {status_code}",
                }

            async with client:
                pass

            latency_ms = int((time.perf_counter() - start) * 1000)
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                return {
                    "reachable": True,
                    "authenticated": True,
                    "status": "active",
                    "latency_ms": latency_ms,
                    "message": "连接成功",
                }

            return {
                "reachable": True,
                "authenticated": True,
                "status": "active",
                "latency_ms": latency_ms,
                "message": "连接成功",
            }
        except AssistantOpenClawGatewayAuthError:
            return {
                "reachable": True,
                "authenticated": False,
                "status": "invalid",
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "message": "Gateway 鉴权失败，请检查 OpenClaw Token",
            }
        except AssistantOpenClawGatewayError as exc:
            return {
                "reachable": True,
                "authenticated": False,
                "status": "invalid",
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "message": f"Gateway 调用失败: {exc}",
            }
        except httpx.ConnectTimeout:
            return {
                "reachable": False,
                "authenticated": False,
                "status": "invalid",
                "latency_ms": None,
                "message": "连接 OpenClaw 超时，请检查实例是否在线",
            }
        except httpx.ConnectError:
            return {
                "reachable": False,
                "authenticated": False,
                "status": "invalid",
                "latency_ms": None,
                "message": "无法连接到 OpenClaw，请检查地址和网络",
            }
        except httpx.ReadTimeout:
            return {
                "reachable": True,
                "authenticated": False,
                "status": "invalid",
                "latency_ms": None,
                "message": "OpenClaw 响应超时，请稍后重试",
            }
        except Exception as exc:
            return {
                "reachable": False,
                "authenticated": False,
                "status": "invalid",
                "latency_ms": None,
                "message": f"连接测试失败: {type(exc).__name__}",
            }
