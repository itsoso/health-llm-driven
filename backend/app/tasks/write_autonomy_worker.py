# -*- coding: utf-8 -*-
"""Write 自治层后台 worker —— 把「无人确认自动执行」从 GET-lazy 路径解耦到后台周期任务。

背景:首切片把 `auto_execute_pending` 挂在 `GET /write-intents` 的懒路径上(用户打开列表时
顺带跑)。这有两个弱点:(a) 用户不打开列表 → 永远不自动执行;(b) 安全门里的 `build_twin`
自开 SessionLocal,在 HTTP 请求事务内跑是已知地雷(请求事务看不到/会与 build_twin 的独立
连接打架)。后台任务**无 HTTP 请求事务**,build_twin 在这里跑是安全的。

本任务**只换"在哪跑",不换"跑什么"**:逐用户调既有 `write_autonomy.auto_execute_pending`,
allowlist(仅 measurement_prompt)/ 每日上限(原子槽)/ 安全门(failed_rule_count + CRITICAL)/
产物 priority=low —— 全部不变。bg 与 GET 同时跑也不会双写/超额:每条执行前在
`autonomy_daily_counters` 单行做原子 `UPDATE count+1 WHERE count<CAP` 预留(行锁串行化),
且 confirm 是 `(id,user,status=pending)` 原子认领 —— 两路抢同一条只有一路赢得认领,另一路幂等。

范围:只扫**有 eligible pending 的用户**(runtime allowlist ∩ ¬NEVER 的 kind),不打扰其余用户。
fail-soft:单用户失败 rollback + 记日志(只记 user_id int,无内容),不连累整批。
"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.write_intent import WriteIntent
from app.services import write_autonomy

logger = logging.getLogger(__name__)


@celery_app.task
def run_write_autonomy_sweep():
    """周期扫描:对每个有 eligible pending 写意图的用户跑一次自治执行(后台事务,无 HTTP 请求)。

    返回 {users_scanned, total_auto_executed}。allowlist/cap/safety-gate/priority 全沿用
    write_autonomy.auto_execute_pending —— 本任务不改任何自治语义,只提供后台驱动。
    """
    # eligible kinds = 静态 allowlist ∩ ¬NEVER(B v1 = {measurement_prompt})。
    # 注:runtime_autonomy_allowlist 需 (db, user_id),此处先用静态集圈定候选用户,
    # 每用户的最终准入(含 per-user graduated kinds + 两道硬门)仍由 auto_execute_pending 复核。
    eligible_kinds = tuple(
        k for k in write_autonomy.AUTONOMY_ALLOWLIST
        if k not in write_autonomy.NEVER_AUTONOMY_KINDS
    )
    if not eligible_kinds:
        logger.info("[自治扫描] eligible kinds 为空 → 跳过")
        return {"users_scanned": 0, "total_auto_executed": 0}

    if not write_autonomy.autonomy_enabled():
        logger.info("[自治扫描] 自治全局关闭 → 跳过")
        return {"users_scanned": 0, "total_auto_executed": 0}

    users_scanned = 0
    total_auto_executed = 0
    with SessionLocal() as db:
        user_ids = [
            uid
            for (uid,) in db.query(WriteIntent.user_id)
            .filter(
                WriteIntent.status == "pending",
                WriteIntent.kind.in_(eligible_kinds),
            )
            .distinct()
            .all()
        ]
        for user_id in user_ids:
            users_scanned += 1
            try:
                res = write_autonomy.auto_execute_pending(db, user_id)
                total_auto_executed += int(res.get("auto_executed", 0) or 0)
            except Exception as e:  # noqa: BLE001 — 单用户失败不拖累整批;自治内部已 fail-safe
                logger.warning("[自治扫描] user=%s 自治执行失败(跳过): %s", user_id, e)
                try:
                    db.rollback()
                except Exception:
                    pass
    logger.info(
        "[自治扫描] 完成:扫描 %s 人,自动执行 %s 条", users_scanned, total_auto_executed
    )
    return {"users_scanned": users_scanned, "total_auto_executed": total_auto_executed}
