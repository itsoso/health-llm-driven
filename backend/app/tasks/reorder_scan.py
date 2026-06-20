# -*- coding: utf-8 -*-
"""P3(D1)每日复购扫描 —— 补剂「快用完」→ 提议补货 write_intent + 稀缺门推送。

每天早晨(北京时)跑一次:对每个用户,按库存 + 依从估的剩余天数判 low,
生成 `reorder_nudge` write_intent(幂等,同补剂当天已提过不重复),再走 R15 稀缺门
(P1 级,补货是「可忽略」类)给一条汇总推送。

边界(safety):本任务**只检测 + 提醒**,绝不下单/购买/支付/调电商 skill —— 财务面是
PRD §3.D2(P5)。措辞 hedged、纯物流提醒,非医疗建议、非处方。

幂等:write_intent 生成器自带 (user, supplement, 当天) 去重;重跑当日扫描不会重复建提议。
fail-soft:单用户失败不影响整批,记日志(只记 user_id int,不落补剂名等内容)。
"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.supplement_inventory import SupplementInventory
from app.services import reorder_detection
from app.services import write_intent_service as svc
from app.utils.async_helpers import run_async

logger = logging.getLogger(__name__)

_AGENT_TYPE = "reorder_watch"  # 必须以 _watch 结尾才进 proactive 预算计数


@celery_app.task
def scan_reorder_nudges():
    """每日复购扫描:为有库存登记的用户生成补货提议 + 稀缺门推送一条汇总。"""
    from app.agents.audit import log_proactive_trigger
    from app.services.notification.push_service import PushService
    from app.services.proactive_coordinator import can_notify_proactively

    logger.info("[复购扫描] 开始每日补剂复购检测")
    proposed_total = notified = 0
    with SessionLocal() as db:
        # 只扫有库存行的用户(没登记库存的补剂 days_remaining=unknown,不会触发 low)
        user_ids = [
            uid for (uid,) in db.query(SupplementInventory.user_id).distinct().all()
        ]
        push_service = PushService(db)
        for user_id in user_ids:
            try:
                low_items = reorder_detection.low_items_for_user(db, user_id)
                if not low_items:
                    continue
                # 生成 write_intent 提议(幂等,内部 commit)
                created = svc.generate_reorder_nudges(db, user_id)
                proposed_total += created

                # 稀缺门(P1:补货可忽略)。每用户至多一条汇总推送,不逐补剂刷屏。
                do_notify = can_notify_proactively(db, user_id, tier="P1")
                if do_notify:
                    n = len(low_items)
                    if n == 1:
                        it = low_items[0]
                        title = "补剂快用完了"
                        content = f"{it['name']} 库存不多了,看看要不要补货。"
                    else:
                        title = "几种补剂快用完了"
                        content = f"有 {n} 种补剂库存不多了,看看要不要补货。"
                    run_async(push_service.send_notification(
                        user_id=user_id,
                        notification_type="reminder",
                        title=title,
                        content=content,
                        data={"kind": "reorder", "low_count": n},
                        severity="info",
                    ))
                    notified += 1
                log_proactive_trigger(
                    db, user_id, agent_type=_AGENT_TYPE,
                    metric="supplement_inventory", kind="reorder_low", delta=0.0,
                    notable=True, notified=do_notify, tier="P1",
                )
            except Exception as e:  # noqa: BLE001
                db.rollback()
                logger.warning(f"[复购扫描] user={user_id} 处理失败: {e}")
    logger.info(f"[复购扫描] 完成:提议 {proposed_total} 条,推送 {notified} 人")
    return {"proposed": proposed_total, "notified": notified}
