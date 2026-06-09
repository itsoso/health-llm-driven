"""日志脱敏工具。

AGENTS.md §5:敏感数据(邮箱/手机/医疗值)不得明文进日志。日志只应记 user_id
和事件类型;确需带标识时用脱敏形式。
"""
from __future__ import annotations

from typing import Optional


def mask_email(email: Optional[str]) -> str:
    """abc@x.com -> a***@x.com;非法/空 -> '<redacted>'。"""
    if not email or "@" not in email:
        return "<redacted>"
    local, _, domain = email.partition("@")
    head = local[:1] if local else ""
    return f"{head}***@{domain}"
