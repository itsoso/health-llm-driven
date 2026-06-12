"""社会连接 check-in 服务 —— 主观问询的存取 + 到期判断 + 解读(非诊断)。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.connection_checkin import ConnectionCheckin

_QUARTER_DAYS = 90


def latest_checkin(db: Session, user_id: int) -> Optional[ConnectionCheckin]:
    return (
        db.query(ConnectionCheckin)
        .filter(ConnectionCheckin.user_id == user_id)
        .order_by(ConnectionCheckin.checkin_date.desc())
        .first()
    )


def record_checkin(
    db: Session, user_id: int, *,
    ucla_score: Optional[int] = None,
    has_confidant: Optional[bool] = None,
    in_stable_group: Optional[bool] = None,
    notes: Optional[str] = None,
) -> ConnectionCheckin:
    c = ConnectionCheckin(
        user_id=user_id, checkin_date=date.today(),
        ucla_score=ucla_score, has_confidant=has_confidant,
        in_stable_group=in_stable_group, notes=notes,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def status(db: Session, user_id: int) -> dict[str, Any]:
    """到期判断 + 孤独解读(非诊断)。"""
    last = latest_checkin(db, user_id)
    today = date.today()
    if last is None:
        return {"has_checkin": False, "due": True, "days_since": None,
                "interpretation": "还没做过社会连接自评。关系质量是长期健康最强的单一预测因子,建议花 1 分钟做一次。"}
    days_since = (today - last.checkin_date).days
    due = days_since >= _QUARTER_DAYS
    interp = _interpret(last)
    return {
        "has_checkin": True, "due": due, "days_since": days_since,
        "last_date": last.checkin_date.isoformat(),
        "ucla_score": last.ucla_score,
        "has_confidant": last.has_confidant, "in_stable_group": last.in_stable_group,
        "interpretation": interp,
    }


def _interpret(c: ConnectionCheckin) -> str:
    parts = []
    if c.ucla_score is not None:
        if c.ucla_score >= 6:
            parts.append("UCLA-3 孤独评分偏高,提示当前社会连接可能不足——这对长期健康的影响不亚于血脂血糖。")
        else:
            parts.append("孤独评分在健康范围。")
    if c.has_confidant is False:
        parts.append("缺少可吐露脆弱的人是值得关注的信号,主动维系一段深度关系的健康收益很高。")
    if c.in_stable_group is False:
        parts.append("没有稳定群体归属时,可考虑加入一个长期、低门槛的群体活动。")
    return " ".join(parts) or "社会连接结构良好,继续保持。"
