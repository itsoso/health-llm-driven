"""共享: X-Reva-Client-Caps 头解析。

GenUI 能力协商: 客户端在 `X-Reva-Client-Caps` 头声明 `genui-v1` 才返回 reva-ui block。
orchestrator 与 agent 两个端点共用同一解析逻辑 (别各写一份, 否则归一化口径漂移)。
"""

from __future__ import annotations


def parse_client_caps(raw: str | None) -> list[str]:
    """解析 X-Reva-Client-Caps 头 (逗号分隔, 大小写归一化)。"""
    if not raw:
        return []
    return [c.strip().lower() for c in raw.split(",") if c.strip()]
