# -*- coding: utf-8 -*-
"""周期 TwinSnapshot 任务。

长期规划里的主动漂移检测(trajectory_watch/longevity_watch)依赖 >=2 个
TwinSnapshot。过去只有 intervention cycle 会写快照,未进入 cycle 的用户会结构性
饿死。本任务每天为活跃用户落一份 periodic 快照,形成最低限度的时间序列。

边界:
- 只扫活跃且已审核的真实用户,以及家庭代管 shadow user。
- 近期已有任意目的快照时跳过,避免日内重复落库。
- periodic 快照关闭 content-hash 去重:这里需要时间锚点,否则内容不变会一直复用旧行。
- 单用户失败回滚并继续,不让一个坏数据源拖垮全批。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.twin_snapshot import TwinSnapshot
from app.models.user import User
from app.twin.builder import build_twin
from app.twin.snapshots import snapshot_twin

logger = logging.getLogger(__name__)

_DEFAULT_STALE_AFTER_HOURS = 20
_PURPOSE = "periodic"


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _eligible_user_ids(db: Session, *, limit: Optional[int] = None) -> list[int]:
    query = (
        db.query(User.id)
        .filter(User.is_active.is_(True))
        .filter(or_(User.is_approved.is_(True), User.is_managed.is_(True)))
        .order_by(User.id.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    return [int(uid) for (uid,) in query.all()]


def _latest_snapshot(db: Session, user_id: int) -> Optional[TwinSnapshot]:
    return (
        db.query(TwinSnapshot)
        .filter(TwinSnapshot.user_id == user_id)
        .order_by(TwinSnapshot.created_at.desc(), TwinSnapshot.id.desc())
        .first()
    )


def _has_recent_snapshot(
    db: Session,
    user_id: int,
    *,
    now: datetime,
    stale_after_hours: int,
) -> bool:
    latest = _latest_snapshot(db, user_id)
    if latest is None or latest.created_at is None:
        return False
    cutoff = _naive_utc(now) - timedelta(hours=stale_after_hours)
    return _naive_utc(latest.created_at) >= cutoff


def run_periodic_twin_snapshot_once(
    db: Session,
    *,
    now: Optional[datetime] = None,
    stale_after_hours: int = _DEFAULT_STALE_AFTER_HOURS,
    limit: Optional[int] = None,
    build_fn: Callable[..., Any] = build_twin,
) -> dict[str, int]:
    """为需要周期快照的用户补一轮 TwinSnapshot。

    返回汇总计数,方便 Celery 日志、运维面板和单测校验。
    """
    run_at = now or datetime.now(UTC)
    result = {"eligible": 0, "created": 0, "skipped_recent": 0, "failed": 0}

    for user_id in _eligible_user_ids(db, limit=limit):
        result["eligible"] += 1
        if _has_recent_snapshot(
            db,
            user_id,
            now=run_at,
            stale_after_hours=stale_after_hours,
        ):
            result["skipped_recent"] += 1
            continue

        try:
            twin = build_fn(db, user_id, use_cache=False)
            snapshot_twin(db, user_id, twin, purpose=_PURPOSE, dedupe=False)
            result["created"] += 1
        except Exception as e:  # noqa: BLE001 - 单用户失败不拖垮整批
            db.rollback()
            result["failed"] += 1
            logger.warning("[周期 Twin 快照] user=%s 处理失败: %s", user_id, e)

    return result


@celery_app.task
def periodic_twin_snapshot():
    """每日生成周期 Twin 快照,供主动漂移检测消费。"""
    logger.info("[周期 Twin 快照] 开始每日扫描")
    with SessionLocal() as db:
        result = run_periodic_twin_snapshot_once(db)
    logger.info(
        "[周期 Twin 快照] 完成: eligible=%s created=%s skipped_recent=%s failed=%s",
        result["eligible"],
        result["created"],
        result["skipped_recent"],
        result["failed"],
    )
    return result
