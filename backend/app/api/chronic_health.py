"""慢病趋势 API —— 消费已在库的历史数据给趋势/风险(非诊断)。

P0 第一块:肝脏趋势(肝酶 + FIB-4 + 脂肪肝风险提示)。后续接鼻炎趋势等。
分析逻辑在 service 层,对话(agent_executor 注入)也复用同一套 —— 三端共享。
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.biomarker_sync import sync_indicators_to_biomarkers
from app.services.causal_links import medication_intervention_effects
from app.services import connection_service
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


# ── P1.1 时滞因果:用药干预 → 指标变化(描述性,非因果)──
@router.get("/causal-links", summary="用药干预 → 目标指标前后变化(描述性关联,非因果)")
def causal_links(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return {
        "intervention_effects": medication_intervention_effects(db, current_user.id),
        "note": "观察到的关联,可能含饮食/运动等其他因素,非严格因果。",
    }


# ── P1.2 社会连接 check-in(L4)──
class ConnectionCheckinBody(BaseModel):
    ucla_score: Optional[int] = None         # UCLA-3 总分 3-9
    has_confidant: Optional[bool] = None
    in_stable_group: Optional[bool] = None
    notes: Optional[str] = None


@router.get("/connection", summary="社会连接自评状态(到期判断 + 解读,非诊断)")
def connection_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return connection_service.status(db, current_user.id)


@router.post("/connection", summary="提交一次社会连接自评(UCLA-3 + 连接结构)")
def submit_connection_checkin(
    body: ConnectionCheckinBody,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if body.ucla_score is not None and not (3 <= body.ucla_score <= 9):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="ucla_score 须为 3-9(UCLA-3 三题各 1-3 分)")
    c = connection_service.record_checkin(
        db, current_user.id,
        ucla_score=body.ucla_score, has_confidant=body.has_confidant,
        in_stable_group=body.in_stable_group, notes=body.notes,
    )
    return {"id": c.id, "checkin_date": c.checkin_date.isoformat(),
            "status": connection_service.status(db, current_user.id)}
