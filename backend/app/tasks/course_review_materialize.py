# -*- coding: utf-8 -*-
"""每日物化「用药疗程结束 → 复查」日历(ReviewSchedule)。

盘点缺口:course-review→agenda 的投影(`agenda_service._project_course_reviews`)是
**只读**的 —— 它把已存在的 ReviewSchedule 行投影进议程。但 ReviewSchedule 行此前只能由
手动端点(`medication_course_service.ensure_review_schedules`)产生;没人调它,议程里那条
药程复查就永远是空的。

本任务补上自动物化:每天扫一遍「有在用药且 end_date 落在未来 ~45 天内」的用户,逐人调
`ensure_review_schedules`,把高把握复查项(如 PPI/P-CAB → 胃镜复查)物化成 ReviewSchedule,
供三端议程投影。`ensure_review_schedules` 在 (user_id, item_name, next_due_date) 上幂等,
每天重跑安全 —— 既不重复建,也能随疗程推进补建新进入窗口的复查。

边界(safety):只物化「提示性」复查日历项,不下诊断、不改药、不写依从。复查映射仅
高把握项,其余疗程不物化(留给对话层 `course_prompt_blob` 的通用复诊提示)。
fail-soft:单用户失败回滚 + 记日志(只记 user_id int,不落药名等内容),不拖垮整批。
"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.database import SessionLocal
from app.services import medication_course_service as course_svc

logger = logging.getLogger(__name__)

_WITHIN_DAYS = 45


@celery_app.task
def materialize_course_reviews():
    """每日物化即将结束疗程的复查日历(ReviewSchedule)。

    只迭代「有在用药且 end_date 在未来 ~45 天内」的用户(与 ensure_review_schedules
    同窗口),避免空扫全体用户。返回 {users, created, skipped} 汇总。
    """
    logger.info("[疗程复查物化] 开始每日扫描")
    created_total = skipped_total = users_scanned = 0
    with SessionLocal() as db:
        user_ids = course_svc.users_with_upcoming_completions(db, within_days=_WITHIN_DAYS)
        for user_id in user_ids:
            try:
                res = course_svc.ensure_review_schedules(
                    db, user_id, within_days=_WITHIN_DAYS
                )
                created_total += res["created"]
                skipped_total += res["skipped"]
                users_scanned += 1
            except Exception as e:  # noqa: BLE001 — 单用户失败不拖垮整批
                db.rollback()
                logger.warning("[疗程复查物化] user=%s 处理失败: %s", user_id, e)
    logger.info(
        "[疗程复查物化] 完成:扫描 %s 人,新建 %s 条,跳过 %s 条",
        users_scanned, created_total, skipped_total,
    )
    return {"users": users_scanned, "created": created_total, "skipped": skipped_total}
