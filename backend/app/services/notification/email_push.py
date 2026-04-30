"""Email 推送服务 — 阿里云 DirectMail / 通用 SMTP.

Doctor Weekly 的优先级通道: Email (给医生) > Telegram (给产品 owner 自己) >
APNs (兜底提示).

阿里云 DirectMail SMTP 配置 (控制台开通后生成):
  SMTP_HOST=smtpdm.aliyun.com
  SMTP_PORT=465                       # SSL (或 80/25 明文)
  SMTP_USER=noreply@executor.life     # 阿里云 DirectMail 里创建的发信地址
  SMTP_PASSWORD=***                    # 阿里云生成的 SMTP 密码 (不是阿里云登录密码)
  SMTP_FROM=HealthPilot <noreply@executor.life>  # 显示的发件人 (可省, 默认 SMTP_USER)
  SMTP_USE_SSL=true                   # 465 用 SSL, 80/25 用明文

配置 DNS 让邮件进对方收件箱不进垃圾箱 (必做):
  - SPF: TXT `v=spf1 include:spf1.dm.aliyun.com -all`
  - DKIM: 阿里云控制台生成后加 DNS
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class EmailPushService:
    """基于 SMTP 的邮件推送. 默认用阿里云 DirectMail 但兼容任何 SMTP 服务."""

    def __init__(self):
        self.host = getattr(settings, "smtp_host", None) or ""
        self.port = int(getattr(settings, "smtp_port", 465) or 465)
        self.user = getattr(settings, "smtp_user", None) or ""
        self.password = getattr(settings, "smtp_password", None) or ""
        self.from_addr = getattr(settings, "smtp_from", None) or self.user
        self.use_ssl = bool(getattr(settings, "smtp_use_ssl", True))
        self.timeout = int(getattr(settings, "smtp_timeout", 15))

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password)

    def send(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        from_name: str = "HealthPilot",
    ) -> dict:
        """发送一封邮件. 返回 {success: bool, error?: str}.

        body_html 可选. 传了则用 multipart/alternative, 收件人客户端
        优先显示 HTML, 不支持的看 text.
        """
        if not self.configured:
            return {"success": False, "error": "smtp_not_configured"}
        if not to or "@" not in to:
            return {"success": False, "error": "invalid_to_address"}

        msg = EmailMessage()
        msg["Subject"] = subject[:200]
        # From 必须是已 verify 的发信地址 (阿里云 DirectMail 校验严格)
        msg["From"] = formataddr((from_name, self.from_addr.split("<")[-1].strip("<> ")))
        msg["To"] = to
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        try:
            if self.use_ssl or self.port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout,
                                       context=context) as smtp:
                    smtp.login(self.user, self.password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                    smtp.ehlo()
                    # STARTTLS 升级 (端口 80/25 阿里云也支持)
                    try:
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.ehlo()
                    except smtplib.SMTPException:
                        pass  # 降级明文
                    smtp.login(self.user, self.password)
                    smtp.send_message(msg)
            logger.info(f"[email] 发送成功 to={to} subject={subject[:40]}")
            return {"success": True}
        except smtplib.SMTPAuthenticationError as e:
            logger.warning(f"[email] 认证失败: {e}")
            return {"success": False, "error": f"auth_failed: {str(e)[:120]}"}
        except smtplib.SMTPException as e:
            logger.warning(f"[email] SMTP 异常: {e}")
            return {"success": False, "error": f"smtp_error: {str(e)[:120]}"}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[email] 发送失败: {e}")
            return {"success": False, "error": f"exception: {str(e)[:120]}"}


def markdown_to_simple_html(md: str) -> str:
    """极简 markdown → HTML (仅处理粗体/斜体/换行/列表, 不引入依赖)."""
    import re
    html = md
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.M)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.M)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.M)
    html = html.replace("\n", "<br>")
    return (
        f"<!DOCTYPE html><html><body style='font-family: sans-serif; "
        f"max-width:720px; margin:16px auto; padding:16px; line-height:1.6;'>"
        f"{html}</body></html>"
    )
