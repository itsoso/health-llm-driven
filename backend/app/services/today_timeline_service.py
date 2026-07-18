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
from app.services.caldav_sync import today_busy_blocks
from app.services.events_timeline_service import build_timeline
from app.services.today_spine_meds import (
    med_supplement_items,
    select_now_item,
    sort_key,
)
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


# 常驻承诺协议的周期(预定计划 = plan_driven)。event_triggered 是信号触发 = event_driven。
_PLAN_CADENCES = {"daily", "weekly", "monthly", "quarterly", "annual"}


def _derive_driver(item: Dict[str, Any]) -> str:
    """timeline item → 三驱标记(纯展示,不影响调度/完成/安全)。

    判据(设计 §契约1,按数据里实际可分的字段):
    - cadence=="event_triggered" → event_driven(餐后步行等信号触发的临时项)。
    - advisory 类(训练决策灯 / 数据质量 / 自纠偏 / 基线漂移,status=="info")→ event_driven
      (这些项由当下信号/事件点亮,非常驻承诺)。
    - 常驻承诺协议(用药/补剂/饮水/训练,cadence∈{daily,weekly,monthly,quarterly,annual})→ plan_driven。
    - 复查(checkup,health_problem 来源,预定到期)→ plan_driven。
    - 歧义(有常驻 source object 但 cadence 缺失)→ plan_driven(设计钦定:歧义偏 plan)。

    注:系统时刻卡(晨起/午间/下午/晚间/睡前)不从 agenda 派生,由
    _day_rhythm_items 显式标记为 time_driven。
    """
    cadence = item.get("cadence")
    if cadence == "event_triggered":
        return "event_driven"
    # advisory:由信号/事件点亮的只读建议项
    if item.get("type") in _ADVISORY_TYPES and item.get("status") == "info":
        return "event_driven"
    # 其余(常驻协议 / 复查 / 歧义)→ plan_driven
    return "plan_driven"


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

    out = {
        "id": f"agenda_{object_type}_{src.get('object_id')}_{itype}",
        "kind": kind,
        "driver": _derive_driver(item),
        "time_window": item.get("time_window") or "anytime",
        # scheduled_for:议程项若带 solver 求解的精确时点(如锻炼块 time=HH:MM)则透传;
        # 否则 None(无确定时点 → 时间窗排序兜底,排在带时点项之后)。
        "scheduled_for": item.get("time") or None,
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
    # P4 锻炼链指针(additive,仅链协议带;非链项不出现这些键 → 客户端行为零变化)。
    # 客户端据此把同一 chain_id 的步按 chain_step 串成一条链渲染/排序。
    if item.get("chain_id"):
        out["chain"] = {
            "chain_id": item.get("chain_id"),
            "chain_step": item.get("chain_step"),
            "chain_role": item.get("chain_role"),
            "prev_protocol_id": item.get("prev_protocol_id"),
            "next_protocol_id": item.get("next_protocol_id"),
        }
    return out


def _map_observation(ev) -> Dict[str, Any]:
    """TimelineEvent(过去/今日已发生)→ kind=observation 统一 item。"""
    return {
        "id": ev.id,
        "kind": "observation",
        "driver": "event_driven",  # 已发生的观测 = 事件
        "time_window": "anytime",
        "scheduled_for": None,
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
        from app.services.outcome_safety import is_efficacy_score_eligible_card

        rows = [card for card in rows if is_efficacy_score_eligible_card(card)]
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
            "driver": "plan_driven",  # 协议期内归因 = 计划驱动的结果
            "time_window": "anytime",
            "scheduled_for": None,
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


_DAY_RHYTHM_SLOTS: List[Dict[str, Any]] = [
    {
        "id": "rhythm_morning_start",
        "time_window": "morning",
        "scheduled_for": "08:00",
        "title": "晨起启动：补水并看今日重点",
        "subtitle": "先补水,再确认小巴排好的第一件事。",
        "icon": "sunny-outline",
        "color": "#1E8A8A",
        "priority": 18,
        "skip_action_kinds": {"hydration"},
    },
    {
        "id": "rhythm_morning_movement",
        "time_window": "morning",
        "scheduled_for": "08:10",
        "title": "晨间活动：10 分钟轻活动",
        "subtitle": "按今天状态选择散步、拉伸、八段锦或轻力量。",
        "icon": "walk-outline",
        "color": "#0A8F8F",
        "priority": 17,
        "skip_action_kinds": {"training", "activity"},
    },
    {
        "id": "rhythm_noon_meal",
        "time_window": "noon",
        "scheduled_for": "12:30",
        "title": "午餐窗口：拍照或一句话记餐",
        "subtitle": "记录一餐后,小巴才能把下一餐建议调准。",
        "icon": "restaurant-outline",
        "color": "#FF9500",
        "priority": 16,
        "skip_action_kinds": {"diet"},
    },
    {
        "id": "rhythm_afternoon_break",
        "time_window": "afternoon",
        "scheduled_for": "15:30",
        "title": "下午恢复：起身、喝水、放松眼睛",
        "subtitle": "工作间歇先做 2 分钟低成本恢复。",
        "icon": "leaf-outline",
        "color": "#34C759",
        "priority": 15,
        "skip_action_kinds": set(),
    },
    {
        "id": "rhythm_evening_close",
        "time_window": "evening",
        "scheduled_for": "19:30",
        "title": "晚间收口：补齐饮食和用药记录",
        "subtitle": "把漏记的晚餐、补剂或药物补上,方便夜间复盘。",
        "icon": "clipboard-outline",
        "color": "#AF52DE",
        "priority": 14,
        "skip_action_kinds": {"diet", "medication", "supplement"},
    },
    {
        "id": "rhythm_bedtime_wind_down",
        "time_window": "bedtime",
        "scheduled_for": "22:30",
        "title": "睡前收尾：降低刺激,准备入睡",
        "subtitle": "回看今天完成情况,把明早第一步留给小巴。",
        "icon": "moon-outline",
        "color": "#5AC8FA",
        "priority": 13,
        "skip_action_kinds": {"sleep", "recovery"},
    },
]


def _day_rhythm_items(existing_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """用户视角的低打扰日内时间骨架。

    它补的是「今天自然会经过哪些健康时刻」,不是新协议,所以:
    - driver=time_driven:按时间窗口出现。
    - kind=advisory:提示/引导,不写记录。
    - can_complete=False:不制造新的确认负担。

    若同一时间窗已有同域真实项(饮食/运动/睡眠/用药等),系统时刻卡让位,避免重复。
    """
    covered: set[tuple[str, str]] = set()
    for item in existing_items:
        action_kind = item.get("action_kind")
        window = item.get("time_window") or "anytime"
        if action_kind:
            covered.add((str(action_kind), str(window)))

    out: List[Dict[str, Any]] = []
    for slot in _DAY_RHYTHM_SLOTS:
        window = slot["time_window"]
        skip_action_kinds = slot.get("skip_action_kinds") or set()
        if any((kind, window) in covered for kind in skip_action_kinds):
            continue
        out.append({
            "id": slot["id"],
            "kind": "advisory",
            "driver": "time_driven",
            "time_window": window,
            "scheduled_for": slot["scheduled_for"],
            "title": slot["title"],
            "subtitle": slot["subtitle"],
            "icon": slot["icon"],
            "color": slot["color"],
            "status": "info",
            "priority": int(slot["priority"]),
            "can_complete": False,
            "complete_ref": None,
            "event_id": None,
            "action_kind": "day_rhythm",
            "deep_link": None,
            "severity": None,
            "proof": None,
        })
    return out


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


def _busy_window(start_hhmm: str) -> str:
    """忙碌块 start HH:MM → 时间窗(与 _current_window 同词表,供排序插对位置)。"""
    try:
        h = int(start_hhmm.split(":")[0])
    except (ValueError, IndexError, AttributeError):
        return "anytime"
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


def _busy_minutes(start_hhmm: str, end_hhmm: str) -> Optional[int]:
    """(HH:MM,HH:MM) → 时长分钟;解析失败 → None(标题降级为"忙碌")。"""
    try:
        sh, sm = (int(x) for x in start_hhmm.split(":"))
        eh, em = (int(x) for x in end_hhmm.split(":"))
        mins = (eh * 60 + em) - (sh * 60 + sm)
        return mins if mins > 0 else None
    except (ValueError, AttributeError):
        return None


def _work_items(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """今日工作块(CalDAV busy block)→ kind=work 时间线项。

    **隐私硬边界**:只用 ``today_busy_blocks`` 的粗粒度 (HH:MM,HH:MM) 接缝(已剥
    title/PII);work item **绝不含**日历标题/encrypted_title/location/uid。
    fail-soft:无凭据/无 block/查询抛错 → 不含 work item,不崩。
    """
    try:
        blocks = today_busy_blocks(db, user_id)
    except Exception as e:  # noqa: BLE001 — fail-soft:日历坏不崩,无 work item
        logger.warning("[today_timeline] busy blocks load failed user=%s: %s", user_id, e)
        return []

    items: List[Dict[str, Any]] = []
    icon, color = _style_for("checkup")  # 复用日历色系(calendar-outline / 蓝)
    for start, end in blocks:
        mins = _busy_minutes(start, end)
        title = f"工作 · {mins}min" if mins is not None else "忙碌"
        items.append({
            "id": f"work_{start}_{end}",
            "kind": "work",
            "driver": "plan_driven",  # 日历 = 预定承诺
            "time_window": _busy_window(start),
            "scheduled_for": start,   # busy block 起点(HH:MM)→ 时间线按时点插对位置
            "title": title,           # 仅时长/通用词,绝无日历标题
            "subtitle": None,
            "icon": icon,
            "color": color,
            "status": None,
            "priority": 40,           # 居协议(50)之下,不抢健康待办
            "can_complete": False,
            "complete_ref": None,
            "event_id": None,
            "action_kind": None,
            "deep_link": None,
            "severity": None,
            "proof": None,
        })
    return items


# 过期宽限窗(分钟):项的确定时点已比当前本地时刻早超过此值且未完成 → status='overdue'。
# 2h 与客户端 RevaTimelineStrip 的 OVERDUE_MINUTES 对齐,避免服务端/客户端判定漂移;
# 也避免「早上 8 点就把 7 点的项打成过期」——刚过一会儿仍算当前项。
_OVERDUE_GRACE_MIN = 120


def _actionable_unit_key(item: Dict[str, Any]):
    """actionable rollup 去重键:一个「待办单位」的稳定身份。

    BID/TID 药在展示层展开成每时段一行(complete_ref 带不同 slot),但它们是**同一个**
    待办单位(同一种药当天)。rollup 计数按 (object_type, object_id) 折叠(丢 slot),让
    一天多次的一种药算 1 个单位而非 N 个。无 complete_ref 的项各自独立(用 item id 兜底)。
    """
    ref = item.get("complete_ref")
    if ref and ref.get("object_type") is not None and ref.get("object_id") is not None:
        return (ref["object_type"], ref["object_id"])
    return item.get("id")


def _mark_overdue(items: List[Dict[str, Any]], now: datetime) -> None:
    """把过期未完成的确定时点项标为 status='overdue'(就地改,加层不减层)。

    判据(全部满足才标):
    - 可完成(can_complete=True)—— 已完成/已跳过/只读项不标。
    - 带确定时点(scheduled_for HH:MM)—— 无时点项无从判「过期」,不标。
    - 该时点已比当前本地时刻早超过 _OVERDUE_GRACE_MIN(2h 宽限)。

    只置状态,不动 can_complete(过期项仍可补记)、不删项、不隐藏 —— 下沉靠 sort_key 读 status。
    时区:now 已是用户本地时间(build_today_spine 传入),cur_min 用本地时分。
    """
    cur_min = now.hour * 60 + now.minute
    for it in items:
        if not it.get("can_complete"):
            continue
        sched = it.get("scheduled_for")
        if not sched:
            continue
        try:
            h, m = (int(x) for x in str(sched).split(":")[:2])
        except (ValueError, AttributeError):
            continue
        sched_min = h * 60 + m
        if cur_min - sched_min > _OVERDUE_GRACE_MIN:
            it["status"] = "overdue"


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

    # 1.1) 用药 + 补剂(medications 表)→ 带真实时点的行动项(统一脊柱核心缺口修复)。
    #      此前 meds 不进脊柱 → 首页回退 legacy 卡;现把 day_schedule(时点)× today_status
    #      (完成度)组合进来。去重:已被 agenda 协议项以同 complete_ref 覆盖的不重复并入
    #      (协议来源 object_type=health_protocol,与 medication/supplement 是不同 ref,
    #       天然不撞;此处用 complete_ref 集合统一防御未来交叉)。
    # F5b:去重键并入 slot —— 真多剂(BID)的两槽共享 (object_type, object_id) 但 slot 不同,
    # 是合法的两条独立脊柱行,不能被 ref 去重折成一条(否则又退回 under-count)。单剂无 slot
    # → 键与改前相同(byte-identical 防御行为)。
    def _cover_key(ref: Dict[str, Any]):
        return (ref["object_type"], ref["object_id"], ref.get("slot"))

    covered_refs = {
        _cover_key(it["complete_ref"])
        for it in items
        if it.get("complete_ref")
    }
    for med_item in med_supplement_items(db, user_id):
        ref = med_item.get("complete_ref")
        key = _cover_key(ref) if ref else None
        if key and key in covered_refs:
            continue  # 已由协议项覆盖 → 不双份
        if key:
            covered_refs.add(key)
        items.append(med_item)

    # NB:脊柱不调 build_daily_operating_plan —— 它请求内 transitively 调 build_twin
    # (自开 SessionLocal、绕过请求事务)且写 DailyOperatingPlan 行,破坏「只读投影」不变量;
    # 其测量提醒又是常驻通用项,并入只增噪。记录/测量提醒由首页各自入口承载,脊柱只投真实
    # 「今日承诺」(协议 + 用药/补剂 + 复查 + 工作块 + 已发生观测 + 归因)。

    # 1.5) 把可完成的行动项物化成 first-class HealthEvent(闭环修复点):
    #      为每个 can_complete 项写/复用一条议程 HealthEvent,把 event_id 回填到 item ——
    #      客户端用它调 POST /timeline/events/{id}/complete。物化失败只降级该项的
    #      可完成性(保留为只读项),不拖垮整条脊柱。med/supplement 也走同一物化(ensure_source
    #      _exists 支持 medication/supplement)→ 不 fork 完成路径。
    _attach_event_ids(db, user_id, items, now)

    # past.completed_count 口径:今日 agenda 里已完成/已自动观测的协议数。
    # 用 agenda 而非 build_timeline,因为 agenda 直接反映"今天该做且已闭环"的协议状态,
    # build_timeline 的事件不区分完成与否。
    completed_count = sum(
        1 for it in agenda_items if it.get("status") in ("completed", "auto_observed")
    )

    # 2) 结果归因项(best-effort 增强)
    items.extend(_outcome_items(db, user_id))

    # 2.5) 今日工作块(CalDAV busy block)→ kind=work 工作域项(无标题,fail-soft)。
    #      跨域护城河:把工作日程合进日脊柱;隐私只用粗粒度 busy 接缝。
    items.extend(_work_items(db, user_id))

    # 2.6) 用户视角完整时间动线:晨起/午间/下午/晚间/睡前的系统时刻卡。
    #      它们是低打扰 advisory,不物化 HealthEvent,也不要求用户确认;已有同窗口同域真实项时让位。
    items.extend(_day_rhythm_items(items))

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

    # 2.7) past-due 下沉标记:过了服药/复查时点(超 2h 宽限、按用户本地时间)且未完成的项
    #      → status='overdue'。让「现在该做的」浮顶、过期项下沉(排序里用 status 判,见 sort_key)。
    #      只加层不减层:overdue 不删项、不改可完成性,仅置状态 + 影响排序。在 sort 前置状态。
    _mark_overdue(items, now)

    # 排序:overdue 项下沉到当前待办之后;其余按真实时点(scheduled_for)升序在前,
    # 无时点项按时间窗兜底,同时段内按优先级降序(见 today_spine_meds.sort_key)。
    items.sort(key=sort_key)

    # now-marker:时间感知地挑「现在该做什么」单项 id(当下/下一项,非清晨第一项)。
    # 在排序与 _attach_event_ids(可能把已完成项熄灭)之后选,保证候选是当前真实待办。
    now_item_id = select_now_item(items, now)

    counts = {
        # actionable:按待办「单位」去重 —— 一种 BID/TID 药当天算 1 个单位(不是 N 个时段),
        # 否则一天吃 3 次的一种药会把待办数吹成 3 倍(alert fatigue)。子项仍按时段分别可打卡,
        # 只有 rollup 计数按 (object_type, object_id) 折叠(见 _actionable_unit_key)。
        "actionable": len({
            _actionable_unit_key(it) for it in items if it["can_complete"]
        }),
        "overdue": sum(1 for it in items if it.get("status") == "overdue"),
        "info": sum(1 for it in items if it["kind"] == "advisory"),
    }

    return {
        "date": str(today),
        "current_window": _current_window(now),
        # now:首页 hero 据此渲染「现在该做什么」(单项 id,指向 items 里的一行)。
        # null = 今天没有可完成的下一步(全完成/无待办)。
        "now": now_item_id,
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
        # scheduled_for:优先用项自带的真实时点(med/supplement 带 timing_solver 的 HH:MM)——
        # 让物化的 HealthEvent.scheduled_for 与完成时落的 taken_time 槽对齐(同槽去重)。
        # 无真实时点(协议项)→ 回退时间窗代表时刻(整点,与既有协议物化行为一致)。
        real_hhmm = it.get("scheduled_for")
        if real_hhmm:
            try:
                rh, rm = (int(x) for x in str(real_hhmm).split(":")[:2])
                scheduled_for = now.replace(hour=rh, minute=rm, second=0, microsecond=0)
            except (ValueError, AttributeError):
                hour = _WINDOW_HOUR.get(it.get("time_window"), 12)
                scheduled_for = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        else:
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
        it.setdefault("scheduled_for", None)
        it.pop("occurred_at", None)  # 脊柱 item 不含 occurred_at(past 已按当日聚合)
    return raw
