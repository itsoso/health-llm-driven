"""统一健康议程投影(R1 第一刀)。

把分散来源投影成一条统一的 HealthAgendaItem 列表(item 引用 source object,不复制业务事实):
- HealthProtocol 今日待办(三域:饮水/用药/饮食 + 自定义)
- HealthProblem 到期/逾期复查(= 复查日历)

后续 slice 再并入:DailyOperatingPlan 行动、用药 regimen、今日训练决策灯。
只读投影,无副作用(完成/跳过仍走各自 source 的端点)。详见 docs/prd/reva-personal-health-os-prd.md §4 / R1。
"""
import logging
from datetime import date
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.services import health_protocol_service as proto_svc
from app.services import health_problem_service as prob_svc

logger = logging.getLogger(__name__)

# 时间窗排序(投影展示顺序)
_TW_ORDER = {"morning": 0, "noon": 1, "afternoon": 2, "evening": 3, "bedtime": 4, "anytime": 5}


def _agenda_item(**kw) -> Dict[str, Any]:
    return kw


def today(db: Session, user_id: int, followup_within_days: int = 14) -> Dict[str, Any]:
    """今日统一议程:协议待办 + 近 N 天到期复查。按优先级(高在前)+ 时间窗排序。"""
    items: List[Dict[str, Any]] = []

    # 1) 协议今日待办(三域)
    for p in proto_svc.today_status(db, user_id):
        if not p.get("is_due_today"):
            continue
        items.append(_agenda_item(
            type=p["domain"],
            title=p["name"],
            status=p["today_status"],            # pending/completed/skipped
            time_window=p.get("time_window") or "anytime",
            priority=50,
            can_default_complete=p.get("can_default_complete"),
            source={"object_type": "health_protocol", "object_id": p["protocol_id"]},
        ))

    # 2) 到期复查(HealthProblem follow_up)→ 复查日历项
    for f in prob_svc.due_followups(db, user_id, within_days=followup_within_days):
        items.append(_agenda_item(
            type="checkup",
            title=f"复查:{f['name']}",
            status="overdue" if f["overdue"] else "due",
            time_window="anytime",
            priority=95 if (f.get("risk_level") in ("P0", "P1")) else 75,
            detail=f.get("what_to_check"),
            responsible=f.get("responsible"),
            next_due=f.get("next_due"),
            source={"object_type": "health_problem", "object_id": f["problem_id"]},
        ))

    items.sort(key=lambda x: (-x["priority"], _TW_ORDER.get(x.get("time_window"), 9)))
    return {
        "agenda_date": str(date.today()),
        "count": len(items),
        "items": items,
    }
