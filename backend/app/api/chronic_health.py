"""慢病趋势 API —— 消费已在库的历史数据给趋势/风险(非诊断)。

P0 第一块:肝脏趋势(肝酶 + FIB-4 + 脂肪肝风险提示)。后续接鼻炎趋势等。
分析逻辑在 service 层,对话(agent_executor 注入)也复用同一套 —— 三端共享。
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.liver_health import assess_liver

router = APIRouter()


def _age(bd: Optional[date]) -> Optional[float]:
    if not bd:
        return None
    t = date.today()
    return float(t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day)))


@router.get("/liver", summary="肝脏趋势评估(肝酶趋势 + FIB-4 + 脂肪肝风险,非诊断)")
def liver_assessment(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """基于历史肝酶给趋势 + 风险提示。缺血小板时 FIB-4 返回 null 并提示补血常规。"""
    return assess_liver(db, current_user.id, age=_age(current_user.birth_date))
