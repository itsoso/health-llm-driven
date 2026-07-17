"""Admin 观察期看板 API.

把 `scripts/observation_dashboard.py` 的 7 模块通过 HTTP 暴露,
让 admin 前端 tab 直接看, 不用 SSH 敲 CLI.

CLI 与本 API 共享 `app/services/observability_service.py`.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.database import get_db
from app.models.user import User
from app.services.celery_health import celery_health_snapshot
from app.services.garmin_sync_health import garmin_sync_health_snapshot
from app.services.sentry_status import sentry_status_snapshot
from app.services.release_readiness import release_readiness_snapshot
from app.services.observability_service import (
    actionable_suggestions,
    collect_dashboard,
    utc_now,
)
from app.utils.redis_cache import RedisCache

router = APIRouter()
logger = logging.getLogger(__name__)

# 单次聚合跑 6 个 SQL 聚合 + 可选 journalctl, 线上 5-10 秒. admin 反复刷不重算.
_CACHE_TTL_SECONDS = 180


@router.get("/release-readiness", summary="发布就绪检查 — 安全/监控/预算/人工闸门")
async def get_release_readiness(admin: User = Depends(get_admin_user)):
    """Return a secret-free release report; never conflates it with liveness."""
    return release_readiness_snapshot()


def _cache_key(days: int, user_id: Optional[int], include_journalctl: bool) -> str:
    uid = user_id if user_id else "all"
    return f"observability:dashboard:d={days}:u={uid}:j={int(include_journalctl)}"


@router.get("/safety-eval", summary="安全 eval — red-team 规则覆盖(确定性)")
async def get_safety_eval(
    admin: User = Depends(get_admin_user),
):
    """对抗性危险场景集 → 安全规则必须命中预期严重度。pass_rate<1 = 覆盖回归。"""
    from app.services.safety_eval import run_safety_eval

    return run_safety_eval()


@router.get("/funnel", summary="激活漏斗 — 注册→改善(去标识增长仪表)")
async def get_activation_funnel(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """注册 → 建档 → 接受 → 评分 → 改善(北极星)漏斗 + 转化率。"""
    from app.services.activation_funnel_service import activation_funnel

    return activation_funnel(db)


@router.get("/eval", summary="Agent eval 看板 — 主动/闭环/延迟/活动(去标识)")
async def get_agent_eval(
    days: int = Query(30, ge=1, le=180),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """RFC 方向九:agent_audit_log + ActionCard 去标识聚合,放量前的仪表盘。"""
    from app.services.agent_eval_service import agent_eval_dashboard

    return agent_eval_dashboard(db, days=days)


@router.get("/dashboard", summary="观察期看板 — 7 模块聚合")
async def get_observation_dashboard(
    days: int = Query(7, ge=1, le=90),
    user_id: Optional[int] = Query(None, description="限定单用户; 不传 = 全量"),
    include_journalctl: bool = Query(False, description="跑 journalctl 扫 tool_validator (仅生产机有效)"),
    refresh: bool = Query(False, description="强制跳过 Redis 缓存"),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """聚合 6-7 个观察期信号给 admin 前端展示.

    Redis 缓存 180s: admin 反复刷不重跑 SQL. 用 ?refresh=true 穿透.
    """
    key = _cache_key(days, user_id, include_journalctl)

    if not refresh:
        cached = RedisCache.get(key)
        if cached is not None:
            cached["cached"] = True
            return cached

    report = collect_dashboard(
        db, days=days, user_id=user_id, include_journalctl=include_journalctl,
    )
    payload = {
        "generated_at": utc_now().isoformat(),
        "window_days": days,
        "user_id": user_id,
        "report": report,
        "suggestions": actionable_suggestions(report),
        "celery_health": celery_health_snapshot(db),
        "garmin_sync_health": garmin_sync_health_snapshot(db),
        "sentry_status": sentry_status_snapshot(),
        "release_readiness": release_readiness_snapshot(),
        "cached": False,
    }
    try:
        RedisCache.set(key, payload, ttl=_CACHE_TTL_SECONDS)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[observability] cache set failed (bypass): {e}")
    return payload
