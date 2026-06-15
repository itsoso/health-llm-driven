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
