"""协议自纠偏(R14):连续偏离 → 非羞辱式系统调整建议。

第一刀只看**协议事件流**里的显式 skip(带 skip_reason):近 7 天跳过 ≥2 次 → 产出一条
纠偏建议,按主导 skip_reason 给「系统/协议哪里不够好」的调整动作。措辞不怪用户(原则:
「系统哪里设计不够好」,不制造羞耻)。

体重均线上升、鼻炎评分持续高等**跨数据源**纠偏(PRD R14 后两例)需另接 weight/rhinitis
数据,留后续刀。
"""
from collections import Counter
import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.health_protocol import HealthProtocol, HealthProtocolEvent

logger = logging.getLogger(__name__)

# skip_reason → 系统视角的调整动作(主语是协议/系统,不是用户的意志力)
_REASON_FIX = {
    "no_time": "时机太挤——把它挪到你更空的时间窗",
    "forgot": "容易忘——加个提醒,或挂到固定锚点(如刷牙后)",
    "no_supply": "耗材不在手边——固定放到显眼位置,顺手补货",
    "too_tired": "可能定太重——先把单次量减半,保住习惯",
    "wrong_place": "地点不对——换成你常在的地方也能做的形式",
    "too_hard": "目标偏高——这周先降难度,达成比完美重要",
    "unwell": "身体不适期——先暂停,别自责,恢复后再续",
    "social": "社交常打断——挪到独处时段",
}
_DEFAULT_FIX = "这条协议最近总没完成——也许它本身需要调整,而不是你不够努力"

_WINDOW_DAYS = 7
_SKIP_THRESHOLD = 2  # 近 7 天跳过 ≥2 次即触发


def detect_self_corrections(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """近 _WINDOW_DAYS 天跳过 ≥_SKIP_THRESHOLD 次的活跃协议 → 纠偏建议列表。"""
    since = date.today() - timedelta(days=_WINDOW_DAYS - 1)
    out: List[Dict[str, Any]] = []
    protos = db.query(HealthProtocol).filter(
        HealthProtocol.user_id == user_id,
        HealthProtocol.status == "active",
    ).all()
    for p in protos:
        skips = db.query(HealthProtocolEvent).filter(
            HealthProtocolEvent.protocol_id == p.id,
            HealthProtocolEvent.user_id == user_id,
            HealthProtocolEvent.status == "skipped",
            HealthProtocolEvent.event_date >= since,
        ).all()
        if len(skips) < _SKIP_THRESHOLD:
            continue
        reasons = [s.skip_reason for s in skips if s.skip_reason]
        dominant = Counter(reasons).most_common(1)[0][0] if reasons else None
        fix = _REASON_FIX.get(dominant, _DEFAULT_FIX)
        out.append({
            "protocol_id": p.id,
            "domain": p.domain,
            "name": p.name,
            "skip_count": len(skips),
            "window_days": _WINDOW_DAYS,
            "dominant_reason": dominant,
            "suggestion": fix,
            "message": f"近 {_WINDOW_DAYS} 天「{p.name}」跳过了 {len(skips)} 次。不是你的错——{fix}。",
        })
    return out


# ── P6 学习闭环:聚合 14 天信号 → 人体工学调参建议(SUGGEST-ONLY)──────────
# R4 硬门:用药/补剂域只允许调时间/冷却/曝光面/节奏,**绝不**触碰量/剂量。
# 这些域键一旦出现在 field_delta 里即视为违规(配对守门测试 + run_loop 后置断言)。
_DOSE_DOMAINS = ("medication", "supplement")
# 绝不允许成为 field_delta.field 的「量/剂量」键(R4):
_DOSE_FORBIDDEN_FIELDS = frozenset(
    {"implied_quantity", "dosage", "actual_dosage", "drug", "dose"}
)
_LEARN_WINDOW_DAYS = 14


def _protocol_priority_tier(domain: str) -> str:
    """协议域 → 通知预算 tier(对齐 event_reminders._KIND_TIER)。

    用药 = P0(处方/关键提醒,学习闭环绝不收紧);其余 = P1(可省轻推)。
    """
    return "P0" if domain == "medication" else "P1"


def _expired_count(db: Session, user_id: int, protocol_id: int, since: date) -> int:
    """该协议近窗内议程 HealthEvent 被判 expired 的次数(逾期未完成信号)。失败 → 0。"""
    try:
        from datetime import datetime as _dt
        from app.models.health_event import HealthEvent
        day_start = _dt.combine(since, _dt.min.time())
        rows = db.query(HealthEvent.complete_ref).filter(
            HealthEvent.user_id == user_id,
            HealthEvent.event_type == "agenda_action",
            HealthEvent.agenda_status == "expired",
            HealthEvent.scheduled_for >= day_start,
        ).all()
        n = 0
        for (ref,) in rows:
            ref = ref or {}
            if (ref.get("object_type") == "health_protocol"
                    and ref.get("object_id") == protocol_id):
                n += 1
        return n
    except Exception as e:  # noqa: BLE001
        logger.warning("learning-loop expired 计数失败 proto=%s: %s", protocol_id, e)
        return 0


def _proactive_conversion(db: Session, user_id: int) -> tuple[int, float | None]:
    """用户级主动触达 → 后续完成的粗代理(诚实:遥测 metric=kind 不带 protocol_id)。

    返回 (近窗 protocol 类轻推事件数, 触达后有完成的占比%)。门槛由 loop 层把控
    (≥3 事件 / ≥10%,对齐 lag_association)。任何失败 → (0, None),不臆测。
    """
    try:
        from datetime import UTC, datetime as _dt, timedelta as _td
        from app.models.agent_audit_log import AgentAuditLog
        cutoff = _dt.now(UTC) - _td(days=_LEARN_WINDOW_DAYS)
        rows = db.query(AgentAuditLog).filter(
            AgentAuditLog.user_id == user_id,
            AgentAuditLog.action == "proactive_trigger",
            AgentAuditLog.created_at >= cutoff,
        ).all()
        events = 0
        for r in rows:
            detail = r.result_detail or {}
            if detail.get("metric") == "protocol" or detail.get("kind") == "pre_event":
                events += 1
        if events == 0:
            return (0, None)
        # 完成基准:近窗内协议完成事件数 / 触达事件数(粗代理,跨协议聚合)。
        completed = db.query(HealthProtocolEvent.id).filter(
            HealthProtocolEvent.user_id == user_id,
            HealthProtocolEvent.status.in_(("completed", "auto_observed")),
            HealthProtocolEvent.event_date >= (date.today() - timedelta(days=_LEARN_WINDOW_DAYS - 1)),
        ).count()
        pct = round(min(completed / events, 1.0) * 100.0, 1)
        return (events, pct)
    except Exception as e:  # noqa: BLE001
        logger.warning("learning-loop proactive 转化计算失败 user=%s: %s", user_id, e)
        return (0, None)


def suggest_protocol_adjustments(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """P6 学习闭环入口:聚合每条活跃协议 14 天信号 → 人体工学调参建议(SUGGEST-ONLY)。

    **不写库、不调药量**:返回的 field_delta 一律是建议(applied=False),用户点一下
    (/protocols/{id}/apply-adjustment)才生效。R4 硬门:用药/补剂域只调时间/冷却/
    曝光面/节奏,绝不触碰量/剂量(下方断言 + 守门测试兜底)。

    每聚合**仅看本 user_id** 的事件(L3 隔离:绝不跨用户合并跳过先验)。
    """
    from app.services.protocol_learning_loop import (
        ProtocolCounters, run_loop, ALLOWED_FIELDS,
    )

    since = date.today() - timedelta(days=_LEARN_WINDOW_DAYS - 1)
    protos = db.query(HealthProtocol).filter(
        HealthProtocol.user_id == user_id,
        HealthProtocol.status == "active",
    ).all()

    proactive_events, proactive_pct = _proactive_conversion(db, user_id)

    counters: List[ProtocolCounters] = []
    for p in protos:
        evs = db.query(HealthProtocolEvent).filter(
            HealthProtocolEvent.protocol_id == p.id,
            HealthProtocolEvent.user_id == user_id,
            HealthProtocolEvent.event_date >= since,
        ).all()
        completed = sum(1 for e in evs if e.status in ("completed", "auto_observed"))
        skipped = sum(1 for e in evs if e.status == "skipped")
        snoozed = sum(1 for e in evs if e.status == "snoozed")
        reasons = [e.skip_reason for e in evs if e.status == "skipped" and e.skip_reason]
        dominant = Counter(reasons).most_common(1)[0][0] if reasons else None
        counters.append(ProtocolCounters(
            protocol_id=p.id,
            domain=p.domain,
            name=p.name,
            priority_tier=_protocol_priority_tier(p.domain),
            time_window=p.time_window or "anytime",
            cadence=p.cadence or "daily",
            completed=completed,
            skipped=skipped,
            snoozed=snoozed,
            expired=_expired_count(db, user_id, p.id, since),
            dominant_skip_reason=dominant,
            proactive_events=proactive_events,
            proactive_followed_pct=proactive_pct,
        ))

    result = run_loop(counters)
    out = result.deltas_as_dicts()
    # R4 最后一道闸:任何 field 落在量/剂量键集合即视为违规,整批拒绝(fail loud)。
    for d in out:
        fld = d.get("field")
        if fld in _DOSE_FORBIDDEN_FIELDS or fld not in ALLOWED_FIELDS:
            raise ValueError(f"R4 违规:学习闭环产出了量/剂量字段 {fld!r}")
    return out


def protocol_nudge_throttle(db: Session, user_id: int, protocol_id: int) -> int:
    """单协议的每周轻推上限(R15:只能 SPEND FEWER,永不低于 floor,绝不收紧 P0)。

    供 event_reminders 在每分钟扫描时**廉价**调用:只取该协议 14 天的跳过/逾期计数,
    走纯策略 nudge_throttle。P0(用药域)恒返回默认(关键提醒不被收紧)。
    任何失败 → 返回默认(fail-open:不因学习闭环坏掉而漏推)。
    """
    from app.services.protocol_learning_loop import (
        ProtocolCounters, nudge_throttle, NUDGE_DEFAULT_PER_WEEK,
    )
    try:
        p = db.query(HealthProtocol).filter(
            HealthProtocol.id == protocol_id,
            HealthProtocol.user_id == user_id,
            HealthProtocol.status == "active",
        ).first()
        if p is None:
            return NUDGE_DEFAULT_PER_WEEK
        since = date.today() - timedelta(days=_LEARN_WINDOW_DAYS - 1)
        evs = db.query(HealthProtocolEvent).filter(
            HealthProtocolEvent.protocol_id == protocol_id,
            HealthProtocolEvent.user_id == user_id,
            HealthProtocolEvent.event_date >= since,
        ).all()
        skipped = sum(1 for e in evs if e.status == "skipped")
        c = ProtocolCounters(
            protocol_id=protocol_id,
            domain=p.domain,
            name=p.name,
            priority_tier=_protocol_priority_tier(p.domain),
            skipped=skipped,
            expired=_expired_count(db, user_id, protocol_id, since),
        )
        return nudge_throttle(c)
    except Exception as e:  # noqa: BLE001
        logger.warning("learning-loop throttle 计算失败 proto=%s: %s", protocol_id, e)
        from app.services.protocol_learning_loop import NUDGE_DEFAULT_PER_WEEK
        return NUDGE_DEFAULT_PER_WEEK


# ── 跨数据源纠偏(R14 续):结果趋势驱动,非协议跳过 ──────────────────
_TREND_WINDOW_DAYS = 14
_WEIGHT_MIN_POINTS = 6          # 体重需更多点(日波动 1–2kg,4 点易假阳)
_WEIGHT_MIN_SPAN_DAYS = 10
_WEIGHT_MIN_ABS_KG = 1.0        # 首/尾各 3 日均值之差 ≥1.0kg 才算真趋势
_WEIGHT_LOW_BMI = 20.0          # BMI<20 或登记进食障碍 → 不给减重方向(安全门控)
_ED_KEYWORDS = ("进食障碍", "厌食", "暴食", "神经性", "低体重", "消瘦", "恶病质")
_SNEEZE_MIN_POINTS = 4


def _has_ed_or_lowweight_problem(db: Session, user_id: int) -> bool:
    try:
        from app.services import health_problem_service as prob_svc
        for p in prob_svc.list_problems(db, user_id, active_only=True):
            if any(k in (p.name or "") for k in _ED_KEYWORDS):
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs)


def detect_outcome_corrections(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """结果指标连续恶化 → 纠偏建议(体重上升、鼻炎症状上升)。

    诚实边界:只做「随访/建议」,不开方、不调药量、不给减重处方。一切方案以医生/营养师为准。
    数据不足不臆测;低体重/进食障碍用户不给体重相关建议(安全门控)。各项失败独立降级。
    """
    from datetime import timedelta

    out: List[Dict[str, Any]] = []
    since = date.today() - timedelta(days=_TREND_WINDOW_DAYS - 1)

    # 1) 体重上升趋势 → 仅观察 + 建议找专业聊(不给「降热量」方向 = 不隐性开方)
    try:
        from app.models.basic_health import BasicHealthData
        rows = db.query(
            BasicHealthData.record_date, BasicHealthData.weight,
            BasicHealthData.height, BasicHealthData.bmi,
        ).filter(
            BasicHealthData.user_id == user_id,
            BasicHealthData.record_date >= since,
            BasicHealthData.weight.isnot(None),
        ).order_by(BasicHealthData.record_date).all()

        pts = [(r.record_date, float(r.weight)) for r in rows]
        # 安全门控:低 BMI / 进食障碍 → 不产出任何体重减重相关建议
        latest_bmi = next((r.bmi for r in reversed(rows) if r.bmi), None)
        if latest_bmi is None:
            h = next((r.height for r in reversed(rows) if r.height), None)
            if h and pts:
                latest_bmi = pts[-1][1] / ((h / 100) ** 2)
        # 健康建议从严:BMI 未知(没录身高)时无法确认不是偏瘦 → 保守不产出
        #(用户补录身高后自然恢复);低 BMI / 进食障碍登记同样门控。
        gated = (latest_bmi is None or latest_bmi < _WEIGHT_LOW_BMI) \
            or _has_ed_or_lowweight_problem(db, user_id)

        if not gated and len(pts) >= _WEIGHT_MIN_POINTS:
            span = (pts[-1][0] - pts[0][0]).days
            first3, last3 = _mean([v for _, v in pts[:3]]), _mean([v for _, v in pts[-3:]])
            change = round(last3 - first3, 1)
            if span >= _WEIGHT_MIN_SPAN_DAYS and change >= _WEIGHT_MIN_ABS_KG:
                out.append({
                    "kind": "weight_uptrend",
                    "name": "体重上升趋势",
                    "metric": "weight",
                    "abs_change": change,
                    "window_days": _TREND_WINDOW_DAYS,
                    "suggestion": "如有体重管理目标,方案请与医生/营养师商量",
                    "message": (
                        f"近 {span} 天体重均线上升约 {change:.1f}kg(首/尾 3 日均值 "
                        f"{first3:.1f}→{last3:.1f})。要不要和医生或营养师聊聊?"
                    ),
                })
    except Exception as e:  # noqa: BLE001
        logger.warning("outcome correction weight 失败: %s", e)

    # 2) 鼻炎(打喷嚏)上升 + 当前仍偏高 → 只建议「就诊复评」,用药调整属医生(不放进用户动作)
    try:
        from app.services.chronic_trends import compute_trend
        from app.models.health_checkin import HealthCheckin
        rows = db.query(HealthCheckin.checkin_date, HealthCheckin.sneeze_count).filter(
            HealthCheckin.user_id == user_id,
            HealthCheckin.checkin_date >= since,
            HealthCheckin.sneeze_count.isnot(None),
        ).all()
        pts = [(r.checkin_date, float(r.sneeze_count)) for r in rows]
        if len(pts) >= _SNEEZE_MIN_POINTS:
            t = compute_trend(pts)
            if (t and t.verdict(higher_is_worse=True, flat_pct=20) == "worsening"
                    and t.last_value >= 3):
                out.append({
                    "kind": "rhinitis_uptrend",
                    "name": "鼻炎症状上升趋势",
                    "metric": "sneeze_count",
                    "window_days": _TREND_WINDOW_DAYS,
                    "suggestion": "建议就诊复评 / 留意环境过敏原(方案由医生决定)",
                    "message": (
                        f"近 {t.span_days} 天打喷嚏增多且仍偏高("
                        f"{t.first_value:.0f}→{t.last_value:.0f}/天)。建议就诊复评;"
                        "可留意环境过敏原。"
                    ),
                })
    except Exception as e:  # noqa: BLE001
        logger.warning("outcome correction rhinitis 失败: %s", e)

    return out
