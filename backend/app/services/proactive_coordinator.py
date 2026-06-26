# -*- coding: utf-8 -*-
"""主动触达协调 —— 跨 watcher 三级打扰预算(R15)。

提醒是稀缺中断预算。分三级:
- **P0 必响应**(处方药/复查当天/异常血压):周上限 ``proactive_p0_weekly_budget``(默认 3);
  穿透静默时段(同 critical 既有策略)。
- **P1 可忽略**(运动开始/睡前降光/补水不足):不要求确认;**静默时段不推**;只受全局周上限约束。
- **P2 纯日志**(步数/体重同步):**永不推送**,周复盘看。

全局:跨所有 tier 周上限 ``proactive_global_weekly_budget``(默认 15)。
预算来源 = agent_audit_log 的 proactive_trigger 埋点(result_detail.tier;旧埋点无 tier 记为 P1)。
fail-open(健康告警宁可多推不可漏),但 P2 永不推、异常可观测。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.services.caldav_sync import today_busy_blocks
from app.utils.timezone import get_china_now, get_user_now

logger = logging.getLogger(__name__)


def proactive_notifications_sent(
    db: Session, user_id: int, days: int = 7, tier: Optional[str] = None,
) -> int:
    """近 days 天已收到的主动推送数(跨所有 *_watch)。tier 给定则只计该级(旧埋点无 tier 记为 P1)。"""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.user_id == user_id,
            AgentAuditLog.action == "proactive_trigger",
            AgentAuditLog.created_at >= cutoff,
        )
        .all()
    )
    n = 0
    for r in rows:
        if not (r.agent_type or "").endswith("_watch"):
            continue
        detail = r.result_detail or {}
        if not detail.get("notified"):
            continue
        if tier is not None and (detail.get("tier") or "P1") != tier:
            continue
        n += 1
    return n


def _parse_hhmm(s: str, default: time) -> time:
    try:
        hh, mm = s.split(":")
        return time(int(hh), int(mm))
    except Exception:  # noqa: BLE001
        return default


def _in_quiet_hours(db: Session, user_id: int) -> bool:
    """当前(本地时刻)是否在用户免打扰时段(默认 22:00–08:30,跨午夜)。失败 → False(不静默)。"""
    try:
        from app.models.notification import UserNotificationSetting
        s = (
            db.query(UserNotificationSetting)
            .filter(UserNotificationSetting.user_id == user_id)
            .first()
        )
        start = _parse_hhmm(getattr(s, "quiet_hours_start", None) or "22:00", time(22, 0))
        end = _parse_hhmm(getattr(s, "quiet_hours_end", None) or "08:30", time(8, 30))
        now = get_user_now(db, user_id).time()
        if start <= end:
            return start <= now < end
        return now >= start or now < end  # 跨午夜
    except Exception as e:  # noqa: BLE001
        logger.warning("[proactive] quiet-hours check failed user=%s: %s", user_id, e)
        return False


def _in_busy_window(db: Session, user_id: int) -> bool:
    """当前(北京时刻)是否落在今日某个日历忙碌块内 → 日程感知静默 P1/P2。

    只用 ``today_busy_blocks`` 的粗粒度 (HH:MM,HH:MM) 接缝(已剥 title/PII),绝不读日历标题。
    忙碌块是北京时刻,故用 get_china_now 比较(与块同时区)。
    fail-soft:无凭据/同步失败/查询抛错 → False(当「不忙」正常推,别因日历坏把所有 nudge 静默)。
    """
    try:
        now_hhmm = get_china_now().strftime("%H:%M")
        for start, end in today_busy_blocks(db, user_id):
            if start <= end:
                # 同日窗 [start, end):常规会议块。
                if start <= now_hhmm < end:
                    return True
            else:
                # 跨午夜窗(end < start,如 23:00–00:30 会议 / 22:00–07:00 睡眠 DND):
                # now 落在 [start, 24:00) 或 [00:00, end) 都算忙。旧的单条 `start<=now<end`
                # 对 end<start 恒 False → 跨午夜块永不静默(该忙时仍推 P1)= 真 bug,且让
                # 23:30–00:29 北京时刻构造跨午夜窗的 busy-window 测试必红(CI 实锤)。
                if now_hhmm >= start or now_hhmm < end:
                    return True
        return False
    except Exception as e:  # noqa: BLE001 — fail-soft:日历坏不静默,不崩
        logger.warning("[proactive] busy-window check failed user=%s: %s", user_id, e)
        return False


def can_notify_proactively(db: Session, user_id: int, tier: str = "P1") -> bool:
    """三级打扰预算 gate(R15)。tier 默认 P1(兼容既有 watcher)。

    P2 永不推;全局周上限封顶;P0 受 P0 周上限且穿透静默;P1 静默时段不推。
    """
    if tier == "P2":
        return False  # 纯日志,永不主动推
    try:
        global_budget = getattr(settings, "proactive_global_weekly_budget", 15)
        if global_budget > 0 and proactive_notifications_sent(db, user_id) >= global_budget:
            return False  # 全局周上限封顶(含 P0)

        if tier == "P0":
            p0_budget = getattr(settings, "proactive_p0_weekly_budget", 3)
            if p0_budget <= 0:
                return True
            return proactive_notifications_sent(db, user_id, tier="P0") < p0_budget

        # P1:静默时段不推;日程感知——忙碌窗内静默(P0 已在上方穿透,不受影响);
        # 白天非忙时受全局上限(上面已查)。
        if _in_quiet_hours(db, user_id):
            return False
        if _in_busy_window(db, user_id):
            return False
        return True
    except Exception as e:  # noqa: BLE001
        # 刻意 fail-open(健康告警宁可多推不可漏),但失败必须可观测。P2 已在上面拦掉。
        logger.warning(
            "[proactive] budget check failed for user=%s tier=%s, failing open: %s",
            user_id, tier, e,
        )
        return True
