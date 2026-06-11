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
from app.services.biomarker_sync import sync_indicators_to_biomarkers
from app.services.intervention_cycle_service import get_active_cycle, refresh_cycle_targets
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


@router.post("/biomarker-sync", summary="把化验指标同步到归一生物标志层(并刷新干预周期目标)")
def biomarker_sync(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """打通 medical_indicators → biomarker_observations(根因修复:归一层此前为空)。
    顺带刷新 active 代谢周期的目标(此前因归一层空而无目标)。"""
    result = sync_indicators_to_biomarkers(db, current_user.id)
    cycle = get_active_cycle(db, current_user.id)
    refreshed = None
    if cycle is not None and cycle.cycle_type == "metabolic_90d":
        refresh_cycle_targets(db, cycle)
        refreshed = {"cycle_id": cycle.id, "target_count": len(cycle.target_metrics or [])}
    return {"sync": result, "cycle_refreshed": refreshed}
