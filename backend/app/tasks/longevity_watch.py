# -*- coding: utf-8 -*-
"""抗衰主动 Agent —— 生物年龄跨快照监测任务(Phase2 W1)。

每周扫一遍有 ≥2 次生物年龄快照的用户:
  - 显著变化(≥ NOTABLE_YEARS)→ 推送(改善=正反馈 / 回升=温和提醒)+ 埋点
  - 非显著变化 → 只埋点,不打扰(打扰预算)

纯判定逻辑在 app/services/longevity_watch.py(可单测);本文件只做"取数 + 推送 + 埋点"。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.twin_snapshot import TwinSnapshot
from app.services.longevity_watch import LongevityChange, find_change_in_snapshots
from app.utils.async_helpers import run_async

logger = logging.getLogger(__name__)

# 每个用户最多看最近这么多条快照里找两次可比的生物年龄
_SCAN_LIMIT = 8


def evaluate_user(db, user_id: int) -> Optional[LongevityChange]:
    """取用户最近快照,算生物年龄变化(可测,无推送副作用)。"""
    rows = (
        db.query(TwinSnapshot)
        .filter(TwinSnapshot.user_id == user_id)
        .order_by(TwinSnapshot.created_at.desc())
        .limit(_SCAN_LIMIT)
        .all()
    )
    snapshots_newest_first = [r.twin_json for r in rows if r.twin_json]
    if len(snapshots_newest_first) < 2:
        return None
    return find_change_in_snapshots(snapshots_newest_first)


@celery_app.task
def longevity_watch():
    """每周扫描:主动播报生物年龄显著变化。"""
    from app.agents.audit import log_longevity_trigger
    from app.services.notification.push_service import PushService
    from app.services.proactive_coordinator import can_notify_proactively

    logger.info("[抗衰监测] 开始生物年龄跨快照扫描")
    triggered = notified = 0
    with SessionLocal() as db:
        user_ids = [
            uid for (uid,) in db.query(TwinSnapshot.user_id).distinct().all()
        ]
        push_service = PushService(db)
        for user_id in user_ids:
            try:
                change = evaluate_user(db, user_id)
                if change is None:
                    continue
                triggered += 1
                # 全局打扰预算 gate:显著 且 未超预算才推
                do_notify = change.notable and can_notify_proactively(db, user_id)
                if do_notify:
                    run_async(push_service.send_notification(
                        user_id=user_id,
                        notification_type="insight",
                        title=change.title,
                        content=change.message,
                        data={"kind": "longevity", "metric": change.metric,
                              "delta_years": change.delta_years},
                        severity="info",
                    ))
                    notified += 1
                # W6 eval:无论推没推都埋点(算 notable 率 / 推送率;notable-notified=被预算抑制)
                log_longevity_trigger(
                    db, user_id,
                    metric=change.metric, kind=change.kind,
                    delta_years=change.delta_years, notable=change.notable,
                    notified=do_notify,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[抗衰监测] user={user_id} 处理失败: {e}")
    logger.info(f"[抗衰监测] 完成:触发 {triggered} 人,推送 {notified} 人")
    return {"triggered": triggered, "notified": notified}
