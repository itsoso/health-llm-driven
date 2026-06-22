"""统一今日时间线投影(Reva Personal Health OS · 首页新脊柱)。

**只读投影,无写、无副作用**。把已存在的两个服务组合成一条统一时间线:
- 未来/现在该做的: `agenda_service.today()` → action / checkup / advisory item
- 今日已发生的观测: `events_timeline_service.build_timeline(days=1)` → observation item(归入 past)
- 结果归因(产品放大器,best-effort): 最近 7 天已评级 improved 的 ActionCard → outcome item

不复制业务事实、不重造服务,只组合 + 投影。完成动作仍走 `/agenda/complete`(复用,
不新建完成接口)。详见 docs/prd/reva-personal-health-os-prd.md。

主路径(agenda + past)失败应让调用方感知;归因增强项失败只记 warning,绝不拖垮时间线。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services import agenda_service
from app.services.agenda_service import _TW_ORDER  # 复用议程时间窗排序
from app.services.events_timeline_service import build_timeline
from app.utils.timezone import get_user_timezone

logger = logging.getLogger(__name__)

# agenda item.type(域) → (Ionicons 名, 颜色). 颜色沿用 events_timeline_service 的色系风格。
_DOMAIN_STYLE: Dict[str, tuple[str, str]] = {
    "hydration": ("water-outline", "#0A84FF"),
    "diet": ("restaurant-outline", "#FF9500"),
    "medication": ("medkit-outline", "#AF52DE"),
    "supplement": ("nutrition-outline", "#34C759"),
    "training": ("barbell-outline", "#0A8F8F"),
    "measurement": ("pulse-outline", "#FF2D55"),
    "activity": ("walk-outline", "#0A8F8F"),
    "mood": ("happy-outline", "#FFD60A"),
    "checkup": ("calendar-outline", "#5AC8FA"),
    "data_quality": ("git-compare-outline", "#8E8E93"),
    "correction": ("sync-outline", "#FF9500"),
    "baseline_deviation": ("pulse-outline", "#8E8E93"),
}
_DEFAULT_STYLE = ("ellipse-outline", "#8E8E93")

# agenda item.type → 统一 kind
_ADVISORY_TYPES = {"training", "data_quality", "correction", "baseline_deviation"}


def _style_for(domain: str) -> tuple[str, str]:
    return _DOMAIN_STYLE.get(domain, _DEFAULT_STYLE)


def _current_window(now: datetime) -> str:
    """按用户本地当前时间推时间窗(与 agenda 的 _TW_ORDER 同词表)。"""
    h = now.hour
    if h < 11:
        return "morning"
    if h < 14:
        return "noon"
    if h < 17:
        return "afternoon"
    if h < 20:
        return "evening"
    if h < 23:
        return "bedtime"
    return "anytime"


def _kind_for(item: Dict[str, Any]) -> str:
    """agenda item → 统一 kind。"""
    itype = item.get("type")
    if itype == "checkup":
        return "checkup"
    if itype in _ADVISORY_TYPES and item.get("status") == "info":
        return "advisory"
    return "action"


def _map_agenda_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """把一个 agenda item 映射成统一时间线 item(未来/现在项)。"""
    itype = item.get("type") or "anytime"
    kind = _kind_for(item)
    icon, color = _style_for(itype)
    src = item.get("source") or {}
    object_type = src.get("object_type")
    status = item.get("status")

    can_complete = status == "pending" and object_type in (
        "health_protocol", "medication", "supplement",
    )
    complete_ref = (
        {"object_type": object_type, "object_id": src.get("object_id")}
        if (object_type is not None and src.get("object_id") is not None)
        else None
    )

    # subtitle 优先 detail(议程项的人话说明),否则用 time_window/状态兜底
    subtitle = item.get("detail")

    return {
        "id": f"agenda_{object_type}_{src.get('object_id')}_{itype}",
        "kind": kind,
        "time_window": item.get("time_window") or "anytime",
        "title": item.get("title") or "",
        "subtitle": subtitle,
        "icon": icon,
        "color": color,
        "status": status,
        "priority": int(item.get("priority") or 0),
        "can_complete": can_complete,
        "complete_ref": complete_ref,
        # 物化后的 first-class HealthEvent id —— 客户端用它调闭环完成端点。
        # 只在 can_complete 的行动项上物化(见 build_today_spine);其余为 None。
        "event_id": None,
        "action_kind": itype,
        "deep_link": None,
        "severity": None,
        "proof": None,
    }


def _map_observation(ev) -> Dict[str, Any]:
    """TimelineEvent(过去/今日已发生)→ kind=observation 统一 item。"""
    return {
        "id": ev.id,
        "kind": "observation",
        "time_window": "anytime",
        "title": ev.title,
        "subtitle": ev.subtitle,
        "icon": ev.icon,
        "color": ev.color,
        "status": None,
        "priority": 0,
        "can_complete": False,
        "complete_ref": None,
        "event_id": None,
        "action_kind": None,
        "deep_link": ev.deep_link,
        "severity": ev.severity,
        "proof": None,
    }


def _outcome_items(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """最近 7 天已评级且 outcome=='improved' 的 ActionCard → kind=outcome item。

    best-effort 产品放大器:任何异常吞掉只记 warning,归因项失败绝不拖垮时间线。
    """
    try:
        from sqlalchemy import or_

        from app.models.action_card import ActionCard

        # S3-B: 窗口收窄到最近 48h,贴「今日」,不把一周前评级的卡顶在最显眼处
        since = datetime.now(timezone.utc) - timedelta(hours=48)
        rows = (
            db.query(ActionCard)
            .filter(
                ActionCard.user_id == user_id,
                ActionCard.graded_at.isnot(None),
                ActionCard.graded_at >= since,
                ActionCard.outcome == "improved",
            )
            # S2: 高风险卡的好转先排除,不进绿色 trophy「庆祝」通道
            .filter(or_(ActionCard.severity.is_(None), ActionCard.severity.notin_(["critical", "high"])))
            .filter(or_(ActionCard.evidence_level.is_(None), ActionCard.evidence_level != "medical_grade"))
            .order_by(ActionCard.graded_at.desc())
            .limit(5)
            .all()
        )
    except Exception as e:  # noqa: BLE001 — 增强项,失败降级
        logger.warning("[today_timeline] outcome attribution load failed for user=%s: %s", user_id, e)
        return []

    items: List[Dict[str, Any]] = []
    for c in rows:
        try:
            proof = _build_proof(c)
        except Exception as e:  # noqa: BLE001 — 单卡 proof 折算失败不影响其它卡
            logger.warning("[today_timeline] outcome proof build failed for card=%s: %s", getattr(c, "id", "?"), e)
            continue
        metric_label = proof["label"] if proof else (c.metric_key or "指标")
        icon, color = _style_for("measurement")
        items.append({
            "id": f"outcome_{c.id}",
            "kind": "outcome",
            "time_window": "anytime",
            "title": f"协议期内{metric_label}向好",
            "subtitle": c.title,
            "icon": "trophy-outline",
            "color": "#34C759",
            "status": "graded",
            "priority": 60,  # 归因项介于协议(50)与建议项之间,首页可见但不抢复查
            "can_complete": False,
            "complete_ref": None,
            "event_id": None,
            "action_kind": None,
            "deep_link": None,
            "severity": None,
            "proof": proof,
        })
    return items


# metric_key → 人话标签(与 events_timeline_service._METRIC_LABELS 风格一致,去单位)
_METRIC_LABEL: Dict[str, str] = {
    "sleep_score": "睡眠评分",
    "hrv": "HRV",
    "rhr": "静息心率",
    "resting_heart_rate": "静息心率",
    "weight": "体重",
    "bp": "血压",
    "spo2_odi": "血氧 ODI",
    "spo2": "血氧",
}


def _build_proof(c) -> Optional[Dict[str, Any]]:
    """ActionCard 的 baseline→actual 折成 proof。值缺失/非数值 → None(不假装)。"""
    metric = c.metric_key
    if not metric:
        return None
    label = _METRIC_LABEL.get(metric, metric)
    baseline_raw = c.baseline_value
    actual_raw = c.actual_value
    if baseline_raw is None or actual_raw is None:
        return None

    direction: Optional[str] = None
    delta = f"{baseline_raw} → {actual_raw}"
    try:
        b = float(str(baseline_raw).strip())
        a = float(str(actual_raw).strip())
        diff = a - b
        if diff != 0:
            direction = "up" if diff > 0 else "down"
        delta = f"{baseline_raw} → {actual_raw}"
    except (ValueError, TypeError):
        # 非数值指标(如血压 "120/80"),保留文字 delta,不强行算方向
        direction = None

    return {"metric": metric, "label": label, "delta": delta, "direction": direction, "association_only": True}


def build_today_spine(db: Session, user_id: int) -> Dict[str, Any]:
    """组合今日统一时间线(只读投影)。

    主路径(agenda + past)失败让调用方感知;归因增强项失败降级。
    """
    tz = get_user_timezone(db, user_id)
    now = datetime.now(tz)
    today = now.date()

    # 1) 未来/现在项:agenda → action / checkup / advisory
    agenda = agenda_service.today(db, user_id)
    agenda_items = agenda.get("items", [])
    items: List[Dict[str, Any]] = [_map_agenda_item(it) for it in agenda_items]

    # 1.5) 把可完成的行动项物化成 first-class HealthEvent(闭环修复点):
    #      为每个 can_complete 项写/复用一条议程 HealthEvent,把 event_id 回填到 item ——
    #      客户端用它调 POST /timeline/events/{id}/complete。物化失败只降级该项的
    #      可完成性(保留为只读项),不拖垮整条脊柱。
    _attach_event_ids(db, user_id, items, now)

    # past.completed_count 口径:今日 agenda 里已完成/已自动观测的协议数。
    # 用 agenda 而非 build_timeline,因为 agenda 直接反映"今天该做且已闭环"的协议状态,
    # build_timeline 的事件不区分完成与否。
    completed_count = sum(
        1 for it in agenda_items if it.get("status") in ("completed", "auto_observed")
    )

    # 2) 结果归因项(best-effort 增强)
    items.extend(_outcome_items(db, user_id))

    # 3) 过去项(今日已发生)→ past.events(observation)
    past_events: List[Dict[str, Any]] = []
    try:
        timeline = build_timeline(db, user_id, days=1, limit=20)
        for ev in timeline:
            occ = ev.occurred_at
            occ_local = occ.astimezone(tz) if occ.tzinfo else occ.replace(tzinfo=tz)
            if occ_local.date() == today:
                past_events.append(_map_observation(ev))
    except Exception:
        # past 是主路径的一部分(今日已发生),失败要让调用方感知 —— 不静默吞。
        logger.exception("[today_timeline] build_timeline failed for user=%s", user_id)
        raise

    # 3.5) 全天产出回溯(简报 7:30 + 异常 23:00)→ past.events(insight)。
    #      过同一道 critical/medical-grade 闸 + 标 association_only(见 timeline_past_service)。
    #      回溯增强项,失败降级不拖垮 past。
    past_events.extend(_past_projection_items(db, user_id, today))

    # 排序:(-priority, 时间窗顺序),复用 agenda 的 _TW_ORDER
    items.sort(key=lambda x: (-x["priority"], _TW_ORDER.get(x.get("time_window"), 9)))

    counts = {
        "actionable": sum(1 for it in items if it["can_complete"]),
        "overdue": sum(1 for it in items if it.get("status") == "overdue"),
        "info": sum(1 for it in items if it["kind"] == "advisory"),
    }

    return {
        "date": str(today),
        "current_window": _current_window(now),
        "items": items,
        "past": {"completed_count": completed_count, "events": past_events},
        "counts": counts,
    }


# 时间窗 → 当日代表性时刻(物化 HealthEvent.scheduled_for 用;非精确,仅供排序/过期)。
_WINDOW_HOUR = {
    "morning": 9, "noon": 12, "afternoon": 15,
    "evening": 19, "bedtime": 22, "anytime": 12,
}


def _attach_event_ids(
    db: Session, user_id: int, items: List[Dict[str, Any]], now: datetime,
) -> None:
    """为 can_complete 的行动项物化 first-class HealthEvent,回填 event_id。

    物化幂等(timeline_agenda_service 内部同日去重)。若该议程 HealthEvent 已被完成
    (agenda_status in done/skipped),把脊柱项的状态翻成对应终态 + can_complete=False
    —— 这正是闭环:完成写一处统一事实,脊柱下次读到就熄灭。
    单项物化失败只降级该项(can_complete=False),不抛(不拖垮整条脊柱)。
    """
    from app.services import timeline_agenda_service as tas

    for it in items:
        if not it.get("can_complete"):
            continue
        ref = it.get("complete_ref")
        if not ref or ref.get("object_type") is None or ref.get("object_id") is None:
            continue
        hour = _WINDOW_HOUR.get(it.get("time_window"), 12)
        scheduled_for = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        try:
            ev = tas.materialize_agenda_event(
                db, user_id,
                action_kind=it.get("action_kind") or "action",
                title=it.get("title") or "",
                complete_ref=dict(ref),
                scheduled_for=scheduled_for,
            )
        except Exception as e:  # noqa: BLE001 — 物化失败只降级该项,不拖垮脊柱
            logger.warning(
                "[today_timeline] materialize agenda event failed user=%s ref=%s: %s",
                user_id, ref, e,
            )
            it["can_complete"] = False
            continue
        it["event_id"] = ev.id
        # 已闭环 → 脊柱项熄灭(翻终态,不可再完成)。
        if ev.agenda_status in ("done", "skipped"):
            it["status"] = "completed" if ev.agenda_status == "done" else "skipped"
            it["can_complete"] = False


def _past_projection_items(
    db: Session, user_id: int, on_date,
) -> List[Dict[str, Any]]:
    """全天产出(简报 + 异常)→ past insight 项,补齐脊柱项的统一字段。"""
    from app.services import timeline_past_service as tps

    raw: List[Dict[str, Any]] = []
    try:
        raw.extend(tps.briefing_past_items(db, user_id, on_date))
        raw.extend(tps.anomaly_past_items(db, user_id, on_date))
    except Exception as e:  # noqa: BLE001 — 回溯增强项,失败降级不拖垮 past
        logger.warning("[today_timeline] past projection failed user=%s: %s", user_id, e)
        return []

    for it in raw:
        it.setdefault("event_id", None)
        it.setdefault("action_kind", None)
        it.pop("occurred_at", None)  # 脊柱 item 不含 occurred_at(past 已按当日聚合)
    return raw
