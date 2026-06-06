# -*- coding: utf-8 -*-
"""主动化推广 —— 代谢/心血管指标轨迹监测任务(把 longevity_watch 模式泛化)。

每周扫有 ≥2 次快照的用户,对 WATCH_METRICS(体重/血糖/HbA1c/LDL/收缩压)做跨快照
变化检测;每用户至多推一条(打扰预算),埋点全部 notable 变化(eval 看板聚合)。

纯判定逻辑在 services/trajectory_watch.py(可测);本文件只取数 + 推送 + 埋点。
"""
from __future__ import annotations

import logging
from typing import List

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.twin_snapshot import TwinSnapshot
from app.services.trajectory_watch import MetricChange, scan_trajectories
from app.utils.async_helpers import run_async

logger = logging.getLogger(__name__)

_SCAN_LIMIT = 8
_AGENT_TYPE = "trajectory_watch"


def evaluate_user_trajectories(db, user_id: int) -> List[MetricChange]:
    """取用户最近快照,返回 notable 的指标轨迹变化(可测,无副作用)。"""
    rows = (
        db.query(TwinSnapshot)
        .filter(TwinSnapshot.user_id == user_id)
        .order_by(TwinSnapshot.created_at.desc())
        .limit(_SCAN_LIMIT)
        .all()
    )
    snaps = [r.twin_json for r in rows if r.twin_json]
    if len(snaps) < 2:
        return []
    return scan_trajectories(snaps)


@celery_app.task
def trajectory_watch():
    """每周扫描:代谢/心血管指标主动播报(每人至多一条,埋点全部)。"""
    from app.agents.audit import log_proactive_trigger
    from app.services.notification.push_service import PushService

    logger.info("[轨迹监测] 开始代谢/心血管跨快照扫描")
    triggered = notified = 0
    with SessionLocal() as db:
        user_ids = [uid for (uid,) in db.query(TwinSnapshot.user_id).distinct().all()]
        push_service = PushService(db)
        for user_id in user_ids:
            try:
                changes = evaluate_user_trajectories(db, user_id)
                if not changes:
                    continue
                triggered += len(changes)
                # 打扰预算:每人只推变化最大的一条
                top = max(changes, key=lambda c: abs(c.delta_pct))
                run_async(push_service.send_notification(
                    user_id=user_id,
                    notification_type="insight",
                    title=top.title,
                    content=top.message,
                    data={"kind": "trajectory", "metric": top.metric},
                    severity="info",
                ))
                notified += 1
                # 埋点:全部 notable 变化(eval 看板看命中/推送率)
                for c in changes:
                    log_proactive_trigger(
                        db, user_id, agent_type=_AGENT_TYPE, metric=c.metric,
                        kind=c.kind, delta=c.delta_pct, notable=True,
                        notified=(c.metric == top.metric),
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[轨迹监测] user={user_id} 处理失败: {e}")
    logger.info(f"[轨迹监测] 完成:notable {triggered} 项,推送 {notified} 人")
    return {"triggered": triggered, "notified": notified}
