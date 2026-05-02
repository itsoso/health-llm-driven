"""Garmin 同步健康探针 — admin 观察期看板的第 9 block.

Garmin 是整个系统的数据 root, 同步挂 = analysis 全废. 当前发现路径仅靠
用户自己重试; 本 probe 让产品 owner 一眼看到.

不直接调 Garmin API (ops 看板不该依赖外部), 纯读 DB 副作用
(GarminCredential.last_sync_at + GarminData record_date), 和 Task 8
Celery Health 同路线 (outage-proof).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session


def garmin_sync_health_snapshot(db: Session) -> dict:
    from app.models.user import GarminCredential
    from app.models.daily_health import GarminData

    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    # 1. 最近一次成功同步 (last_sync_at 最大值)
    last_sync_at = db.query(func.max(GarminCredential.last_sync_at)).scalar()
    # SQLite (test fixture) 会剥掉 tz info; 线上 PG 保留. 统一归一化为 UTC-aware.
    if last_sync_at is not None and last_sync_at.tzinfo is None:
        last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)

    # 2. sync_enabled × credentials_valid 用户数
    active_users = db.query(func.count(GarminCredential.id)).filter(
        GarminCredential.sync_enabled == True,  # noqa: E712
        GarminCredential.credentials_valid == True,  # noqa: E712
    ).scalar() or 0

    # 3. sync_enabled 但 credentials_valid=False (需要重新登录)
    invalid_cred_users = db.query(func.count(GarminCredential.id)).filter(
        GarminCredential.sync_enabled == True,  # noqa: E712
        GarminCredential.credentials_valid == False,  # noqa: E712
    ).scalar() or 0

    # 4. 最近 24h 有 GarminData 写入的 user_id 唯一数
    distinct_users_24h = db.query(
        func.count(func.distinct(GarminData.user_id))
    ).filter(
        GarminData.record_date >= since_24h.date(),
    ).scalar() or 0

    # 5. sync_enabled 但 7 天内零 GarminData (warning 级)
    users_with_recent_data_subq = db.query(
        GarminData.user_id
    ).filter(
        GarminData.record_date >= since_7d.date(),
    ).distinct().subquery()

    stale_users = db.query(func.count(GarminCredential.id)).filter(
        GarminCredential.sync_enabled == True,  # noqa: E712
        GarminCredential.credentials_valid == True,  # noqa: E712
        ~GarminCredential.user_id.in_(
            db.query(users_with_recent_data_subq.c.user_id)
        ),
    ).scalar() or 0

    last_sync_age_hours = (
        (now - last_sync_at).total_seconds() / 3600 if last_sync_at else None
    )

    # Status 分类:
    # - no_data: 没有任何 active (sync_enabled & credentials_valid) 用户
    # - stale: last_sync > 24h 前, 或 24h 内零用户产生数据
    # - ok: last_sync <= 24h AND 24h 产生数据用户数 >= active_users * 0.5
    # - observing: 其他 (有 active, 有 sync, 但 24h 数据覆盖率 < 50%)
    if active_users == 0:
        status = "no_data"
    elif last_sync_at is None or (
        last_sync_age_hours is not None and last_sync_age_hours > 24
    ):
        status = "stale"
    elif distinct_users_24h == 0:
        status = "stale"
    elif distinct_users_24h >= max(1, active_users * 0.5):
        status = "ok"
    else:
        status = "observing"

    return {
        "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
        "last_sync_age_hours": (
            round(last_sync_age_hours, 1) if last_sync_age_hours is not None else None
        ),
        "active_users": int(active_users),
        "invalid_cred_users": int(invalid_cred_users),
        "distinct_users_24h": int(distinct_users_24h),
        "stale_users_7d": int(stale_users),
        "status": status,
        "note": (
            "Garmin 是数据 root: last_sync_at 是所有 GarminCredential 的 max; "
            "distinct_users_24h 是真的产生了 GarminData 的用户数. "
            "stale_users_7d = sync_enabled & credentials_valid 但 7 天零数据 "
            "(需看是否 Garmin 账号问题)."
        ),
    }
