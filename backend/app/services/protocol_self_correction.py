"""协议自纠偏(R14):连续偏离 → 非羞辱式系统调整建议。

第一刀只看**协议事件流**里的显式 skip(带 skip_reason):近 7 天跳过 ≥2 次 → 产出一条
纠偏建议,按主导 skip_reason 给「系统/协议哪里不够好」的调整动作。措辞不怪用户(原则:
「系统哪里设计不够好」,不制造羞耻)。

体重均线上升、鼻炎评分持续高等**跨数据源**纠偏(PRD R14 后两例)需另接 weight/rhinitis
数据,留后续刀。
"""
from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.health_protocol import HealthProtocol, HealthProtocolEvent

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
