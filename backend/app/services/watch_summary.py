"""Apple Watch 腕上摘要(W1 大脑)。

把 rolling-runtime 投影 runtime_range_view(days=1) 投影成 watch 优化的紧凑视图,并**加层不减层**
地补回 today() 里每一条今日到期协议(含事件触发非 daily 协议,见 build_watch_summary):
- status:今日状态灯(绿/黄/红/灰)+ readiness + 一句话 headline
- top_action:此刻最该做的一件可执行事(腕上一眼)
- quick_actions:打点入口目录(喝水/补剂/运动/记一餐/打卡)—— watch 渲染按钮,各指向已有端点
- push_items:该推到手腕的关键信息(分级 P0/P1,运动/补剂/睡眠/复查),小屏只留最多 3 条
- runtime:rolling-runtime 合同信封 + 当日协议项的 runtime_context 富化

只读投影,不写库、不绕过 Safety Guardian(critical 告警仍走告警通道);headline/push 措辞不诊断不开方。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent_audit_log import AgentAuditLog
from app.models.daily_health import GarminData
from app.models.health_protocol import HealthProtocolEvent
from app.models.smart_reminder import SmartReminder
from app.models.user import GarminCredential
from app.services import agenda_service, proactive_coordinator
from app.services.action_ranker import rank_agenda_actions
from app.services.reminder_delivery_status import reminder_delivery_status
from app.utils.timezone import get_user_now, get_user_today

logger = logging.getLogger(__name__)

# 打点入口目录(canonical):watch 据此渲染按钮,endpoint 指向已有写接口。
# value 由 watch 端补(喝水 ml / 运动 reps 等);diet_voice 走语音解析草稿流。
QUICK_ACTIONS: List[Dict[str, Any]] = [
    {"kind": "water", "label": "喝水", "endpoint": "/water/records/quick",
     "method": "POST", "param": "amount", "unit": "ml", "suggested": [250, 500]},
    {"kind": "supplement", "label": "补剂", "endpoint": "/supplements/records", "method": "POST"},
    {"kind": "exercise", "label": "运动", "endpoint": "/daily-health/exercise", "method": "POST",
     "hint": "俯卧撑/跑步等"},
    {"kind": "diet_voice", "label": "记一餐", "endpoint": "/diet/voice/parse", "method": "POST",
     "input": "voice"},
    {"kind": "checkin", "label": "打卡", "endpoint": "/checkin/records/quick", "method": "POST"},
]

_LIGHT_HEADLINE = {
    "green": "今日恢复良好,可按计划训练",
    "yellow": "今日恢复一般,适度为宜",
    "red": "今日建议以休息为主",
}
_PUSH_CAP = 3   # 手腕小屏:最多 3 条关键推送(对齐 R15 稀缺中断预算)
_WATCH_REMINDER_CAP = 3
_WATCH_BEHAVIOR_NUDGE_CAPS = {"exercise": 3, "training": 3, "activity": 3}
_WATCH_SKIP_DOWNRANK_REASONS = {"too_tired", "too_hard", "unwell"}


def _push_tier(item: Dict[str, Any]) -> Optional[str]:
    """该议程项是否值得推到手腕 + 分级(P0 必响应 / P1 可忽略)。其余不推。"""
    t = item.get("type")
    st = item.get("status")
    src = item.get("source") or {}
    if t == "checkup" and st == "overdue":
        return "P0"                      # 逾期复查
    if t == "training" and item.get("light") == "red":
        return "P1"                      # 今日建议休息
    if t == "correction":
        return "P1"                      # 协议自纠偏
    if t == "medication" and st == "pending":
        return "P1"                      # 用药待办
    if t == "exercise" and st == "pending":
        return "P1"                      # 餐后散步 / 微运动 nudge
    if t == "movement" and st == "pending":
        return "P1"                      # timing-solver 当日锻炼块(cut 6)
    if src.get("object_type") == "smart_reminder" and st == "pending":
        return "P1"                      # Agent 创建的可执行提醒,腕上可见但不声称已送达
    return None


def _action_id(item: Dict[str, Any]) -> Optional[str]:
    """由 item.source 合成 action_id(agenda-{ot}-{oid});无 source → None(不可一键完成)。"""
    src = item.get("source") or {}
    ot = src.get("object_type")
    oid = src.get("object_id")
    if ot is None or oid is None:
        return None
    return f"agenda-{ot}-{oid}"


def _action_view(item: Dict[str, Any]) -> Dict[str, Any]:
    view = {
        "action_id": _action_id(item),
        "title": item.get("title"),
        "kind": item.get("type"),
        "time_window": item.get("time_window"),
        "source": item.get("source"),
        "priority_tier": item.get("priority_tier"),
        "leverage_score": item.get("leverage_score"),
        "rationale_short": item.get("rationale_short"),
        "verification_window_days": item.get("verification_window_days"),
        "safety_status": item.get("safety_status"),
        "trajectory_context": item.get("trajectory_context"),
        "target_state_variable": item.get("target_state_variable"),
        "verification_signal": item.get("verification_signal"),
        "prescription": item.get("prescription"),  # cut A:movement 处方(None 则前端忽略)
    }
    if item.get("runtime_context"):
        view["runtime_context"] = item.get("runtime_context")
    if item.get("delivery_status"):
        view["delivery_status"] = item.get("delivery_status")
    return view


def _due_view(item: Dict[str, Any]) -> Dict[str, Any]:
    """只读到点项(腕上「待打点」列表):带 action_id 可一键完成。"""
    view = {
        "action_id": _action_id(item),
        "title": item.get("title"),
        "kind": item.get("type"),
        "time_window": item.get("time_window"),
        "source": item.get("source"),
    }
    if item.get("prescription"):
        view["prescription"] = item["prescription"]  # cut A:腕上渲染强度 chip
    if item.get("runtime_context"):
        view["runtime_context"] = item.get("runtime_context")
    if item.get("delivery_status"):
        view["delivery_status"] = item.get("delivery_status")
    return view


def _push_view(item: Dict[str, Any], tier: str) -> Dict[str, Any]:
    view = {
        "tier": tier,
        "title": item.get("title"),
        "detail": item.get("detail"),
        "kind": item.get("type"),
        "source": item.get("source"),
    }
    if item.get("delivery_status"):
        view["delivery_status"] = item.get("delivery_status")
    return view


def _runtime_contract(runtime_projection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mode": runtime_projection.get("mode"),
        "generated_by": runtime_projection.get("generated_by"),
        "horizon_days": runtime_projection.get("horizon_days"),
        "start": runtime_projection.get("start"),
        "end": runtime_projection.get("end"),
    }


def _runtime_projection_items(runtime_projection: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for day in runtime_projection.get("days") or []:
        if not isinstance(day, dict):
            continue
        for window in day.get("time_windows") or []:
            if not isinstance(window, dict):
                continue
            for item in window.get("items") or []:
                if isinstance(item, dict):
                    items.append(item)
    if not items and isinstance(runtime_projection.get("next_action"), dict):
        items.append(runtime_projection["next_action"])
    if not items and isinstance(runtime_projection.get("items"), list):
        items.extend([item for item in runtime_projection["items"] if isinstance(item, dict)])
    return items


def _is_exercise_behavior_nudge(item: Dict[str, Any]) -> bool:
    src = item.get("source") or {}
    if item.get("status") != "pending":
        return False
    # timing-solver 锻炼块(cut 6)同属运动行为 nudge:critical 安全信号活跃时不该催「去锻炼」。
    if src.get("object_type") == "day_schedule_workout":
        return True
    return (
        item.get("type") in ("exercise", "training", "activity")
        and src.get("object_type") == "health_protocol"
    )


def _is_required_execution_nudge(item: Dict[str, Any]) -> bool:
    if (item.get("source") or {}).get("object_type") == "smart_reminder":
        return item.get("status") == "pending"
    return item.get("status") == "pending" and item.get("type") == "medication"


def _reminder_local_time(reminder: SmartReminder, user_now: datetime) -> datetime:
    remind_at = reminder.remind_at
    if remind_at.tzinfo is None:
        # PostgreSQL preserves the timezone, while SQLite's DateTime
        # compatibility path returns the stored local wall-clock value as
        # naive.  SmartReminder inputs are normalized to the user's local
        # timezone, so attaching UTC here shifts same-day reminders across
        # midnight and removes them from the Watch summary.
        remind_at = remind_at.replace(tzinfo=user_now.tzinfo or timezone.utc)
    return remind_at.astimezone(user_now.tzinfo)


def _reminder_kind(reminder: SmartReminder) -> str:
    extra = reminder.extra_data or {}
    explicit = str(extra.get("watch_kind") or "").strip()
    if explicit:
        return explicit
    text = f"{reminder.title or ''} {reminder.message or ''}".lower()
    if any(term in text for term in ("喝水", "饮水", "补水", "water", "hydration")):
        return "hydration"
    return "reminder"


def _reminder_priority(reminder: SmartReminder) -> int:
    return {
        "urgent": 95,
        "high": 80,
        "normal": 55,
        "low": 35,
    }.get(str(reminder.priority or "normal"), 55)


def _agent_reminder_items(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """Project Agent-created SmartReminder rows into today's Watch task stream."""
    user_now = get_user_now(db, user_id)
    user_day_start = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
    visible_after = user_now - timedelta(hours=1)
    rows = (
        db.query(SmartReminder)
        .filter(
            SmartReminder.user_id == user_id,
            SmartReminder.status == "pending",
        )
        .order_by(SmartReminder.remind_at.asc())
        .limit(50)
        .all()
    )
    items: List[Dict[str, Any]] = []
    for reminder in rows:
        local_at = _reminder_local_time(reminder, user_now)
        if local_at.date() != user_now.date():
            continue
        if local_at < visible_after:
            continue
        items.append({
            "type": _reminder_kind(reminder),
            "title": reminder.title,
            "detail": reminder.message,
            "status": "pending",
            "priority": _reminder_priority(reminder),
            "time_window": local_at.strftime("%H:%M"),
            "source": {"object_type": "smart_reminder", "object_id": reminder.id},
            "runtime_context": {
                "current_state_summary": "小巴已创建的提醒,手表刷新今日摘要时可执行。",
                "replan_reason": "agent_scheduled_reminder",
                "safety_boundary": "这是提醒任务,不代表手表通知已实际送达。",
            },
            "delivery_status": reminder_delivery_status(
                db=db,
                user_id=user_id,
                reminder_id=reminder.id,
                since=user_day_start,
            ),
        })
        if len(items) >= _WATCH_REMINDER_CAP:
            break
    return items


def _watch_behavior_nudges_sent_today(db: Session, user_id: int, kind: str) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = db.query(AgentAuditLog.result_detail).filter(
        AgentAuditLog.user_id == user_id,
        AgentAuditLog.action == "proactive_trigger",
        AgentAuditLog.created_at >= cutoff,
    ).all()
    count = 0
    for row in rows:
        detail = row[0] or {}
        if not detail.get("notified"):
            continue
        if detail.get("kind") == kind or detail.get("domain") == kind:
            count += 1
    return count


def _watch_behavior_nudge_cap_reached(db: Session, user_id: int, kind: str) -> bool:
    cap = _WATCH_BEHAVIOR_NUDGE_CAPS.get(kind)
    if not cap:
        return False
    return _watch_behavior_nudges_sent_today(db, user_id, kind) >= cap


def _recent_behavior_skip_downranks(db: Session, user_id: int, item: Dict[str, Any]) -> bool:
    src = item.get("source") or {}
    if src.get("object_type") != "health_protocol":
        return False
    protocol_id = src.get("object_id")
    if protocol_id is None:
        return False
    since = get_user_today(db, user_id) - timedelta(days=7)
    return db.query(HealthProtocolEvent.id).filter(
        HealthProtocolEvent.user_id == user_id,
        HealthProtocolEvent.protocol_id == protocol_id,
        HealthProtocolEvent.status == "skipped",
        HealthProtocolEvent.event_date >= since,
        HealthProtocolEvent.skip_reason.in_(_WATCH_SKIP_DOWNRANK_REASONS),
    ).first() is not None


def _has_active_critical_safety(db: Session, user_id: int) -> bool:
    """是否有近期未确认 critical 安全信号。只查已落库证据,不在摘要路径跑 SafetyGuardian。"""
    today = get_user_today(db, user_id)
    try:
        from app.models.anomaly_alert import AnomalyAlert

        if db.query(AnomalyAlert.id).filter(
            AnomalyAlert.user_id == user_id,
            AnomalyAlert.severity == "critical",
            AnomalyAlert.detection_date >= today - timedelta(days=1),
            AnomalyAlert.acknowledged.is_(False),
            AnomalyAlert.is_suppressed.is_(False),
        ).first():
            return True
    except Exception:
        # 安全门查询失败时不静默给运动 nudge;后续 AgentAuditLog 还会再查一次。
        return True

    try:
        from app.agents.safety_guardian.schema import Severity
        from app.models.agent_audit_log import AgentAuditLog

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = db.query(AgentAuditLog.result_detail).filter(
            AgentAuditLog.user_id == user_id,
            AgentAuditLog.agent_type == "safety_guardian",
            AgentAuditLog.action == "evaluate",
            AgentAuditLog.created_at >= cutoff,
        ).order_by(AgentAuditLog.created_at.desc()).limit(20).all()
        for row in rows:
            detail = row[0] or {}
            try:
                if int(detail.get("top_severity") or 0) >= int(Severity.CRITICAL):
                    return True
            except (TypeError, ValueError):
                continue
    except Exception:
        # 已查过 AnomalyAlert;审计查询失败不应让普通摘要整体失败。
        return False
    return False


def _can_include_push(db: Session, user_id: int, item: Dict[str, Any], tier: str) -> bool:
    if tier == "P0":
        return True
    if _is_required_execution_nudge(item):
        return True
    if _is_exercise_behavior_nudge(item) and _has_active_critical_safety(db, user_id):
        return False
    if _is_exercise_behavior_nudge(item):
        if _recent_behavior_skip_downranks(db, user_id, item):
            return False
        if _watch_behavior_nudge_cap_reached(db, user_id, item.get("type") or ""):
            return False
    return proactive_coordinator.can_notify_proactively(db, user_id, tier=tier)


def _iso_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _wearable_freshness(db: Session, user_id: int) -> Dict[str, Any]:
    """腕上状态用的数据新鲜度。只暴露同步状态,不暴露凭据/错误原文。"""
    today = get_user_today(db, user_id)
    latest_date = (
        db.query(func.max(GarminData.record_date))
        .filter(GarminData.user_id == user_id)
        .scalar()
    )
    cred = (
        db.query(GarminCredential)
        .filter(GarminCredential.user_id == user_id)
        .first()
    )

    age_days = (today - latest_date).days if latest_date else None
    last_sync_at = _iso_datetime(cred.last_sync_at if cred else None)

    state = "missing"
    label = "待同步"

    if cred and (not cred.credentials_valid or (cred.error_count or 0) >= 3):
        state = "error"
        label = "同步异常"
    elif latest_date is None:
        state = "missing"
        label = "待同步"
    elif age_days is not None and age_days <= 0:
        state = "fresh"
        label = "今日已同步"
    elif age_days == 1:
        state = "stale"
        label = "数据偏旧 1 天"
    else:
        state = "stale"
        label = f"数据偏旧 {age_days} 天"

    return {
        "state": state,
        "label": label,
        "latest_date": latest_date.isoformat() if latest_date else None,
        "age_days": age_days,
        "last_sync_at": last_sync_at,
    }


def _merge_due_protocol_items(
    db: Session, user_id: int, items: List[Dict[str, Any]]
) -> None:
    """把 today() 里今日到期的协议/锻炼块补进投影 items(in-place,按 source 去重)。

    投影 runtime_range_view 的 max_items_per_day top-N 截断会把低 rank 的事件触发协议
    (餐后散步等)挤出,但腕上 due/push 必须看到每一条今日到期协议(加层不减层)。
    只补 pending 的 health_protocol / day_schedule_workout(= actionable 可回写域),不动
    checkup/training 等投影行为;已在投影里的同 source 项跳过 → daily 协议绝不双现。
    """
    seen = {
        (src.get("object_type"), src.get("object_id"))
        for src in ((it.get("source") or {}) for it in items)
        if (src.get("object_type"), src.get("object_id")) != (None, None)
    }
    try:
        agenda_today = agenda_service.today(db, user_id)
    except Exception as e:  # noqa: BLE001 — 补层失败不得拖垮整张腕上摘要(fail-loud 记日志)
        logger.warning("watch_summary: today() 协议补层失败,仅用投影 items: %s", e)
        return
    for it in agenda_today.get("items") or []:
        src = it.get("source") or {}
        if src.get("object_type") not in ("health_protocol", "day_schedule_workout"):
            continue
        if it.get("status") != "pending":
            continue
        key = (src.get("object_type"), src.get("object_id"))
        if key in seen:
            continue
        seen.add(key)
        items.append(it)


def build_watch_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """腕上摘要(只读投影 rolling runtime 今日行动合同)。

    items 以 runtime_range_view(days=1) 投影为基底(带 runtime_context 富化),再**加层不减层**
    地补回 today() 里每一条今日到期的协议/锻炼块 —— 投影的 max_items_per_day top-N 截断会把
    低 rank 的事件触发协议(餐后散步等)挤出,而腕上 due/push 必须看到每一条今日到期协议。
    按 source 去重,daily 协议不会双现。

    历史回归(a1535357 feat(runtime): add chat and watch surfaces):build_watch_summary 从
    today() 切到截断投影后,事件触发协议(rank 低)被 daily_plan_action(rank 高)挤出 top-3,
    手腕餐后散步 nudge 静默消失。见 tests/test_postmeal_walk_jitai.py。
    """
    runtime_projection = agenda_service.runtime_range_view(
        db,
        user_id,
        days=1,
        max_items_per_day=3,
    )
    items = _runtime_projection_items(runtime_projection)
    # 加层不减层:补回投影截断掉的今日到期协议/锻炼块(含事件触发非 daily 协议)。
    _merge_due_protocol_items(db, user_id, items)
    items.extend(_agent_reminder_items(db, user_id))

    training = next((i for i in items if i.get("type") == "training"), None)
    light = (training or {}).get("light") or "gray"
    readiness = (training or {}).get("readiness_score")

    actionable = [
        i for i in items
        if i.get("status") == "pending"
        and (i.get("source") or {}).get("object_type") in (
            "health_protocol",
            "day_schedule_workout",
            "smart_reminder",
        )
    ]
    ranked_actions = rank_agenda_actions(actionable)
    top_action = _action_view(ranked_actions[0]) if ranked_actions else None
    due_items = [_due_view(i) for i in ranked_actions]

    if training and training.get("light") in _LIGHT_HEADLINE:
        headline = _LIGHT_HEADLINE[training["light"]]
    elif actionable:
        headline = f"还有 {len(actionable)} 项待打点"
    else:
        headline = "今日暂无待办"

    push: List[Dict[str, Any]] = []
    for i in items:
        tier = _push_tier(i)
        if tier and _can_include_push(db, user_id, i, tier):
            push.append(_push_view(i, tier))
    push.sort(key=lambda x: 0 if x["tier"] == "P0" else 1)
    push = push[:_PUSH_CAP]

    return {
        "status": {
            "light": light,
            "readiness_score": readiness,
            "headline": headline,
            "freshness": _wearable_freshness(db, user_id),
        },
        "top_action": top_action,
        "due_items": due_items,
        "agenda": {"total": len(items), "pending": len(actionable)},
        "runtime": _runtime_contract(runtime_projection),
        # quick_actions 是目录入口(无具体 source)→ action_id=null,不可一键完成。
        "quick_actions": [{**qa, "action_id": None} for qa in QUICK_ACTIONS],
        "push_items": push,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
