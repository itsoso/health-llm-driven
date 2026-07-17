"""R4 · 主动触达统一 Gatekeeper(观测模式先行,ships-OFF)。

现状(2026-07-17 架构映射结论):主动触达任务经 PushService.send_notification 收口,
并由本模块提供可观测/可切换的每日触达预算；quiet-hours + 晨间地板 + dedup + 类型开关仍是基础抑制器。
本模块加**一层统一预算决策**:每类主动内容(洞察/总结/建议…)设每日上限,超限则
(enforce)丢弃 /(observe)只记决策日志。

设计纪律(路线图 R4 + 本仓库铁律):
- **观测先行**:`mode="observe"` 只算+记 would_drop 决策,**绝不实际拦**(投递逐字节不变);
  founder 看两周日志再翻 `mode="enforce"`。默认 `mode="off"` = 完全零行为(连日志/查询都不跑)。
- **CRITICAL/安全永远 bypass**(加层不减层硬红线,进对抗测试):severity≥critical **或** 类别==safety
  → 恒 `suppress=False`,即便 enforce 模式。双重判定(severity + 类别)防单点漏。
- **fail-open**:任何异常 → 允许发送 + 告警日志,绝不因预算逻辑吞掉一条通知
  (通知子系统既有策略是"宁可过推不可漏",与 write-autonomy 的 fail-closed 相反)。
- **数 SENT 真投递**(非调用次数):按当日(北京日历日)NotificationLog.status==sent 的行计数,
  故 dedup/quiet-hours-delay/禁用 的未投递尝试不消耗预算(镜像 agent_loop"发后才计"语义,
  但用 DB 派生计数避开 Redis 计数漂移 + 自增时序坑)。

open-loop 已经通过 PushService 收口；新增主动通知类型必须先显式分类，否则按
`other` fail-safe 放行，不能在未知类型上意外启用预算拦截。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from app.config import settings
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)

# 通知严重度序(与 push_service._SEVERITY_ORDER 同源语义;此处独立一份避免循环 import)。
_SEVERITY_ORDER: Dict[str, int] = {
    "info": 0, "low": 1, "warning": 2, "medium": 2, "high": 3, "critical": 4,
}


def _severity_rank(severity: Optional[str]) -> int:
    # .strip() 与 _category_of 对齐(安全评审 F1):severity="critical " 带空白也须判为 critical,
    # 否则"实现硬红线的这一行"反而比两 def 之下的 _category_of 更弱。非 str 交由上层 try fail-open。
    return _SEVERITY_ORDER.get((severity or "info").strip().lower(), 0)


def _normalize_mode(mode) -> str:
    """模式归一化(F1 同款):大小写/空白容错。非法值 → 'off'(inert,绝不误入 enforce)。"""
    if not isinstance(mode, str):
        return "off"
    m = mode.strip().lower()
    return m if m in {"off", "observe", "enforce"} else "off"


# notification_type(自由字符串,无中央 enum)→ 预算类别。未映射 → "other"。
# safety 类别恒不限额(与 severity≥critical 双保险)。reminder 是用户排程的(用药/计划提醒),
# 不该被"打扰预算"限——预算只治**非请求式**主动推送(洞察/趋势/总结/建议)。
_CATEGORY_BY_TYPE: Dict[str, str] = {
    # —— safety:永不限额 ——
    "health_alert": "safety",
    "garmin_sync_failed": "safety",
    # —— reminder:用户排程,不限额 ——
    "reminder": "reminder",
    "plan_reminder": "reminder",
    "episode_action_reminder": "reminder",
    # —— insight:非请求式,限额(路线图示例"洞察类 ≤2/天")——
    "daily_insights": "insight",
    "insight": "insight",
    "trend_report": "insight",
    "prediction_verified": "insight",
    "workout_analysis": "insight",
    "open_loop": "insight",
    # —— summary ——
    "morning_briefing": "summary",
    "doctor_weekly_summary": "summary",
    # —— advice ——
    "ai_advice": "advice",
}

# 每类每日上限(北京日历日)。None = 不限额(永不 suppress)。
# **fail-safe 白名单口径(opt-in budgeting)**:只有显式列为"非请求式推广内容"的三类
# (insight/summary/advice)有有限预算;其余一切(safety/reminder/**other=未映射类型**)恒不限额。
# 这样将来新增一个我没映射的 notification_type(可能是安全相关)默认落 "other" → 永不被 enforce
# 丢弃(under-alarm 兜底);等显式分类后再纳入预算。初版预算为占位值,观测两周后按日志调参。
_DAILY_BUDGET: Dict[str, Optional[int]] = {
    "safety": None,
    "reminder": None,
    "insight": 2,
    "summary": 2,
    "advice": 2,
    "other": None,  # 未映射类型 fail-safe 不限额(可能是新安全类型),显式分类后再进预算
}

# 类别 → 该类别下的 notification_type 集合(反查,供 DB 计数)。
_TYPES_BY_CATEGORY: Dict[str, list] = {}
for _t, _c in _CATEGORY_BY_TYPE.items():
    _TYPES_BY_CATEGORY.setdefault(_c, []).append(_t)


def _category_of(notification_type: Optional[str]) -> str:
    return _CATEGORY_BY_TYPE.get((notification_type or "").strip(), "other")


def _budget_of(category: str) -> Optional[int]:
    return _DAILY_BUDGET.get(category, _DAILY_BUDGET["other"])


@dataclass(frozen=True)
class GateOutcome:
    """网关裁决。suppress=True 仅在 enforce 模式 + 非 critical + 超预算时;observe/off 恒 False。"""
    suppress: bool
    decision: str          # allow | would_drop | drop | off
    reason: str            # critical_bypass | within_budget | over_budget | disabled | error
    category: str
    count_today: int = 0
    budget: Optional[int] = None


def _count_sent_today(db, user_id: int, category: str) -> int:
    """当日(北京日历日)该用户该类别已 SENT 的 NotificationLog 行数。异常 → -1(调用方 fail-open)。"""
    try:
        from app.models.notification import NotificationLog, NotificationStatus

        types = _TYPES_BY_CATEGORY.get(category)
        if not types:
            return 0
        now = get_china_now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            db.query(NotificationLog)
            .filter(
                NotificationLog.user_id == user_id,
                NotificationLog.notification_type.in_(types),
                NotificationLog.status == NotificationStatus.SENT.value,
                NotificationLog.sent_at >= day_start,
            )
            .count()
        )
    except Exception as e:  # noqa: BLE001 — 计数失败 → fail-open
        logger.warning("[notif_gate] 计数失败(fail-open 放行): %s", e)
        return -1


def gate_proactive_notification(
    db,
    user_id: int,
    notification_type: str,
    severity: str = "info",
) -> GateOutcome:
    """主动触达统一预算网关。off→零行为;observe→算+记不拦;enforce→超预算非 critical 才 suppress。

    CRITICAL(severity≥critical)或 safety 类别 **永远 suppress=False**(硬红线,双重判定)。
    全程 fail-open:任何异常 → suppress=False + 告警。
    """
    # off 归一化 + 零行为最先返回:此前**任何**计算(含 _category_of)都不跑,
    # 保证 "off = 绝不影响投递",即便 notification_type 是非 str 脏值(安全评审 F3)。
    mode = _normalize_mode(getattr(settings, "notification_gatekeeper_mode", "off"))
    if mode == "off":
        return GateOutcome(False, "off", "disabled", "")

    try:
        category = _category_of(notification_type)
        is_critical = _severity_rank(severity) >= _severity_rank("critical")
        # —— 硬红线:critical 或 safety 类别永不限额 ——
        if is_critical or category == "safety":
            logger.info(
                "[notif_gate] %s allow user=%s type=%s cat=%s reason=critical_bypass",
                mode, user_id, notification_type, category,
            )
            return GateOutcome(False, "allow", "critical_bypass", category)

        budget = _budget_of(category)
        if budget is None:
            return GateOutcome(False, "allow", "unbudgeted", category, budget=None)

        count = _count_sent_today(db, user_id, category)
        if count < 0:  # 计数异常 → fail-open
            return GateOutcome(False, "allow", "error", category)

        over = count >= budget
        decision = "would_drop" if over else "allow"
        reason = "over_budget" if over else "within_budget"
        # enforce 模式且超预算才真拦;observe 恒 False(逐字节不变的投递)。
        suppress = over and mode == "enforce"
        if over:
            decision = "drop" if suppress else "would_drop"
        logger.info(
            "[notif_gate] %s %s user=%s type=%s cat=%s count=%s/%s reason=%s",
            mode, decision, user_id, notification_type, category, count, budget, reason,
        )
        return GateOutcome(suppress, decision, reason, category, count_today=count, budget=budget)
    except Exception as e:  # noqa: BLE001 — 预算逻辑绝不吞通知
        # category 可能在 _category_of 抛之前尚未赋值 → 用 "" 兜底,绝不让 except 自己 NameError。
        logger.warning("[notif_gate] 网关异常(fail-open 放行): %s", e)
        return GateOutcome(False, "allow", "error", "")
