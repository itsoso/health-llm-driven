"""
Sentry status snapshot — admin 观察期看板的 Sentry 启用指示.

WHY: backend 的 Sentry 集成代码 (main.py:36-57) 已就位, 但**只在 settings.sentry_dsn
非空时启用**. 接 DSN 是用户的手动操作 (注册 sentry.io + 拿 DSN + 写 .env-online).
让 admin 看板直接显示当前状态, 接好后立刻能看到生效, 不用 grep journalctl.

返回 dict (而非 enum/类), 与其它 *_snapshot 服务一致.
"""
from __future__ import annotations

from typing import Optional


def sentry_status_snapshot() -> dict:
    """Return current Sentry config + enabled state. No DB I/O — just config inspection.

    Fields:
      enabled: bool — settings.sentry_dsn 是否配置
      environment: str — production / development / unset
      traces_sample_rate: float
      hint: str — 若未启用, 给出简短下一步指引
    """
    try:
        from app.config import settings
        dsn: Optional[str] = (settings.sentry_dsn or "").strip() or None
        env_name = (settings.sentry_environment or "unset").strip() or "unset"
        rate = float(settings.sentry_traces_sample_rate or 0.0)
    except Exception:  # noqa: BLE001
        # config 读取失败本身就是大问题, 但本 probe 不该崩 admin 看板
        return {
            "enabled": False,
            "environment": "unknown",
            "traces_sample_rate": 0.0,
            "hint": "config inspection failed",
        }

    if not dsn:
        return {
            "enabled": False,
            "environment": env_name,
            "traces_sample_rate": rate,
            "hint": "未启用. 设 SENTRY_DSN env var 后重启 backend 生效. 详见 docs/plans/2026-05-02-sentry-setup.md",
        }

    # DSN 已配置 — 不回传 DSN 本身 (它是 secret-ish, 即便可公开也不必暴露给前端)
    return {
        "enabled": True,
        "environment": env_name,
        "traces_sample_rate": rate,
        "hint": "已启用",
    }
