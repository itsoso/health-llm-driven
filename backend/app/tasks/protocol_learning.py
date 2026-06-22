# -*- coding: utf-8 -*-
"""P6 学习闭环周任务 —— 聚合每用户协议信号,把人体工学调参建议落审计(SUGGEST-ONLY)。

每周扫所有有活跃协议的用户,跑 `suggest_protocol_adjustments`(纯聚合 + 纯策略),
每条建议写一条 `log_proactive_trigger` 样式的审计行(agent_type="protocol_learning_watch")。

**绝不推送、绝不写协议本体、绝不调药量**:本任务只产「建议 + 审计」。建议在
/protocols/corrections 与首页议程里呈现,用户点 apply-adjustment 才生效(不劫持)。
节流(nudge_throttle)由 event_reminders 在扫描时按需读审计,不在此处主动推。

fail-open / 旁路:单用户失败不拖垮整批;审计写失败不影响主流程(log_proactive_trigger
自带兜底)。纯判定在 services/protocol_learning_loop.py(可全单测),本文件只取数 + 埋点。
"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)

_AGENT_TYPE = "protocol_learning_watch"


def _candidate_user_ids(db) -> list[int]:
    """有活跃 HealthProtocol 的用户(学习闭环只对有协议的人有意义)。"""
    from app.models.health_protocol import HealthProtocol

    ids: set[int] = set()
    for (uid,) in (
        db.query(HealthProtocol.user_id)
        .filter(HealthProtocol.status == "active")
        .distinct()
    ):
        if uid is not None:
            ids.add(uid)
    return sorted(ids)


@celery_app.task
def protocol_learning_watch():
    """每周聚合协议信号 → 把人体工学调参建议落审计(不推送、不改协议、不调药量)。"""
    from app.agents.audit import log_proactive_trigger
    from app.services.protocol_self_correction import suggest_protocol_adjustments

    logger.info("[学习闭环] 开始协议人体工学调参聚合")
    users = suggestions = 0
    with SessionLocal() as db:
        try:
            user_ids = _candidate_user_ids(db)
        except Exception as e:  # noqa: BLE001
            logger.error("[学习闭环] 候选用户枚举失败: %s", e)
            return {"users": 0, "suggestions": 0}

        for user_id in user_ids:
            try:
                deltas = suggest_protocol_adjustments(db, user_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("[学习闭环] user=%s 聚合失败: %s", user_id, e)
                continue
            if not deltas:
                continue
            users += 1
            for d in deltas:
                suggestions += 1
                # 旁路审计:notified=False(学习闭环只建议、不推送);tier 恒 P1(R15:
                # 绝不消耗 P0 预算)。metric=field 便于 eval 看板按调参字段聚合。
                log_proactive_trigger(
                    db, user_id,
                    agent_type=_AGENT_TYPE,
                    metric=d.get("field", "protocol"),
                    kind="suggest_adjustment",
                    delta=0.0,
                    notable=True,
                    notified=False,
                    tier="P1",
                )
    logger.info("[学习闭环] 完成:%s 用户,%s 条建议", users, suggestions)
    return {"users": users, "suggestions": suggestions}
