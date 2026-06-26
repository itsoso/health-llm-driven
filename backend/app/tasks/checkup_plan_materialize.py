# -*- coding: utf-8 -*-
"""每日物化「按年龄·性别的人群筛查」复查计划(R7)。

`checkup_planner.ensure_checkup_schedules` 把适用的人群筛查项(结直肠癌/血脂/血糖/胃镜/
女性宫颈乳腺/男性 PSA)幂等物化成 ReviewSchedule;由已上线的 agenda 投影 + 器官去重消费。
本任务每天扫一遍**有出生日期(可算年龄)**的用户,逐人调一次(幂等:已有同名未完成项即跳过)。

安全:只产出 advisory 人群筛查建议(带「以医生意见为准」),非处方/非诊断 —— 与 ② course-review
物化同一安全信封。fail-soft:单用户失败回滚 + 只记 user_id,不拖垮整批。
"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user_profile import UserProfile
from app.services import checkup_planner

logger = logging.getLogger(__name__)


@celery_app.task
def materialize_checkup_plans():
    """每日物化人群筛查复查项。返回 {users, created, skipped}。"""
    logger.info("[体检筛查规划] 开始每日扫描")
    created_total = skipped_total = users = 0
    with SessionLocal() as db:
        user_ids = [
            uid for (uid,) in db.query(UserProfile.user_id)
            .filter(UserProfile.birth_date.isnot(None))
            .all()
        ]
        for uid in user_ids:
            try:
                res = checkup_planner.ensure_checkup_schedules(db, uid)
                created_total += res.get("created", 0)
                skipped_total += res.get("skipped", 0)
                users += 1
            except Exception as e:  # noqa: BLE001 — 单用户失败不拖垮整批
                db.rollback()
                logger.warning("[体检筛查规划] user=%s 处理失败: %s", uid, e)
    logger.info(
        "[体检筛查规划] 完成:扫描 %s 人,新建 %s 条,跳过 %s 条",
        users, created_total, skipped_total,
    )
    return {"users": users, "created": created_total, "skipped": skipped_total}
