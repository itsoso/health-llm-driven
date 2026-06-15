"""用药管理 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.agents.safety_guardian import evaluate_safety
from app.database import get_db
from app.models.medication import Medication, MedicationLog, medication_timing_label
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.medication_service import medication_service
from app.twin.builder import build_twin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/medication", tags=["用药管理"])

_MEDICATION_SAFETY_CATEGORIES = {"pgx", "ddi", "dsi"}


class MedicationCreate(BaseModel):
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    times_per_day: int = 1
    reminder_times: Optional[List[str]] = None
    timing_relation: Optional[str] = None  # empty_stomach/before_meal_30/before_meal/with_meal/after_meal/bedtime/anytime
    meal_anchor: Optional[str] = None  # breakfast/lunch/dinner
    category: Optional[str] = None
    purpose: Optional[str] = None
    side_effects: Optional[str] = None
    interactions: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    times_per_day: Optional[int] = None
    reminder_times: Optional[List[str]] = None
    timing_relation: Optional[str] = None
    meal_anchor: Optional[str] = None
    category: Optional[str] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None


class MedicationLogCreate(BaseModel):
    medication_id: int
    taken_time: str
    status: str = "taken"
    skip_reason: Optional[str] = None
    actual_dosage: Optional[str] = None
    notes: Optional[str] = None


class MedicationLogUpdate(BaseModel):
    medication_id: Optional[int] = None
    taken_time: Optional[str] = None
    status: Optional[str] = None
    skip_reason: Optional[str] = None
    actual_dosage: Optional[str] = None
    notes: Optional[str] = None


@router.post("/medications")
async def add_medication(
    data: MedicationCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """添加药品"""
    logger.info(f"[MedAPI] 用户 {current_user.id} 添加药品: {data.name}")
    med = medication_service.add_medication(db, current_user.id, data.model_dump(exclude_none=True))

    # Memory KG: 药 → entity + 'self_user owns medication' 关系 (旁路)
    try:
        from app.services.memory_extractor import extract_kg_from_medication
        extract_kg_from_medication(db, current_user.id, med)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[MedAPI] KG extract 失败 (旁路): {e}")

    body = _serialize_medication(med)
    body["safety_alerts"] = _medication_safety_alerts(db, current_user.id)
    return body


@router.get("/medications/me")
async def list_my_medications(
    active_only: bool = True,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取我的药品列表"""
    meds = medication_service.list_medications(db, current_user.id, active_only)
    return [_serialize_medication(m) for m in meds]


@router.get("/medications/{medication_id}")
async def get_medication(
    medication_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取药品详情"""
    med = medication_service.get_medication(db, medication_id, current_user.id)
    if not med:
        raise HTTPException(status_code=404, detail="药品不存在")
    return _serialize_medication(med)


@router.put("/medications/{medication_id}")
async def update_medication(
    medication_id: int,
    data: MedicationUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新药品"""
    med = medication_service.update_medication(db, medication_id, current_user.id, data.model_dump(exclude_none=True))
    if not med:
        raise HTTPException(status_code=404, detail="药品不存在")
    body = _serialize_medication(med)
    body["safety_alerts"] = _medication_safety_alerts(db, current_user.id)
    return body


@router.delete("/medications/{medication_id}")
async def deactivate_medication(
    medication_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """停用药品"""
    success = medication_service.deactivate_medication(db, medication_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="药品不存在")
    return {"message": "药品已停用"}


@router.post("/medications/{medication_id}/restore")
async def restore_medication(
    medication_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """恢复已停用药品 (误点击回滚). 查 is_active=False 的也支持."""
    success = medication_service.reactivate_medication(db, medication_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="药品不存在或不属于当前用户")
    return {"message": "药品已恢复"}


@router.post("/logs")
async def log_medication(
    data: MedicationLogCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """记录服药"""
    logger.info(f"[MedAPI] 用户 {current_user.id} 记录服药: med={data.medication_id}")
    log = medication_service.log_medication(
        db=db,
        user_id=current_user.id,
        medication_id=data.medication_id,
        taken_time=data.taken_time,
        status=data.status,
        skip_reason=data.skip_reason,
        actual_dosage=data.actual_dosage,
        notes=data.notes,
    )
    return {
        "id": log.id,
        "medication_id": log.medication_id,
        "taken_date": str(log.taken_date),
        "taken_time": log.taken_time,
        "status": log.status,
    }


@router.delete("/logs/{log_id}")
async def delete_medication_log(
    log_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除一条服药日志（本人），用于撤销误点的快速打卡"""
    log = db.query(MedicationLog).filter(
        MedicationLog.id == log_id,
        MedicationLog.user_id == current_user.id,
    ).first()
    if not log:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(log)
    db.commit()
    logger.info(f"[MedAPI] 用户 {current_user.id} 删除服药日志 {log_id}")
    return {"message": "已删除", "id": log_id}


@router.put("/logs/{log_id}")
async def update_medication_log(
    log_id: int,
    data: MedicationLogUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新一条服药日志（本人），用于对话内修正误点/漏记"""
    payload = data.model_dump(exclude_unset=True)
    status_value = payload.get("status")
    if status_value is not None and status_value not in {"taken", "skipped", "delayed"}:
        raise HTTPException(status_code=400, detail="status 必须是 taken/skipped/delayed")

    log = db.query(MedicationLog).filter(
        MedicationLog.id == log_id,
        MedicationLog.user_id == current_user.id,
    ).first()
    if not log:
        raise HTTPException(status_code=404, detail="记录不存在")

    if "medication_id" in payload:
        med = db.query(Medication).filter(
            Medication.id == payload["medication_id"],
            Medication.user_id == current_user.id,
        ).first()
        if not med:
            raise HTTPException(status_code=404, detail="药品不存在")

    for key, value in payload.items():
        setattr(log, key, value)
    db.commit()
    db.refresh(log)
    logger.info(f"[MedAPI] 用户 {current_user.id} 更新服药日志 {log_id}")
    return _serialize_medication_log(log)


@router.get("/today/me")
async def get_today_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取今日服药状态"""
    return medication_service.get_today_status(db, current_user.id)


@router.get("/adherence/me")
async def get_adherence_stats(
    days: int = Query(default=7, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取服药依从性统计"""
    return medication_service.get_adherence_stats(db, current_user.id, days)


@router.get("/deprescribing-review/me")
async def get_deprescribing_review(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """多药梳理 / 减药候选(非建议停药;请与医生讨论是否可精简)。"""
    from app.models.medication import Medication
    from app.services.deprescribing_review import review_medications
    meds = db.query(Medication).filter(
        Medication.user_id == current_user.id, Medication.is_active == True  # noqa: E712
    ).all()
    payload = [{"name": m.name, "start_date": m.start_date, "end_date": m.end_date} for m in meds]
    return review_medications(payload)


class RegimenInstantiate(BaseModel):
    template_id: Optional[str] = None  # 选模板;与 phases 二选一
    phases: Optional[List[Dict[str, Any]]] = None  # 自定义/OCR 解析的多阶段
    name: Optional[str] = None
    start_on: Optional[str] = None  # YYYY-MM-DD,默认今天
    override_safety: bool = False  # 用户明确知情后强行录入(仅放行非 CRITICAL? CRITICAL 也需显式)


@router.get("/regimen-templates")
async def list_regimen_templates(
    hp_status: Optional[str] = None,   # positive/negative → 按 Hp 状态分流;None=全部
    current_user: User = Depends(get_current_user_required),
):
    """列出可选用药方案模板(录入脚手架,非用药建议)。

    传 hp_status 按幽门螺杆菌状态分流:Hp 阳性才给根除方案,Hp 阴性给 PPI 愈合(不含抗生素)。
    """
    from app.services import regimen_templates
    return {
        "templates": regimen_templates.templates_for_hp_status(hp_status),
        "disclaimer": regimen_templates.TEMPLATE_DISCLAIMER,
        "hp_status_filter": hp_status,
    }


@router.post("/regimens")
async def create_regimen(
    data: RegimenInstantiate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """实例化用药方案:解析阶段 → 引入即 DDI 预检 → 建疗程+当前阶段药品。

    有 CRITICAL 药物相互作用且未 override_safety → 422 阻断(不写库),返回触发的告警。
    """
    from datetime import date as _date
    from app.services import medication_regimen_service as mrs

    start = None
    if data.start_on:
        try:
            start = _date.fromisoformat(data.start_on)
        except ValueError:
            raise HTTPException(status_code=400, detail="start_on 格式应为 YYYY-MM-DD")

    try:
        result = mrs.instantiate_regimen(
            db, current_user.id,
            template_id=data.template_id,
            phases=data.phases,
            name=data.name,
            start_on=start,
            override_safety=data.override_safety,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result["blocked"]:
        # 用 422 + 结构化 body 让前端弹「检测到高危相互作用」确认页;
        # 用户知情后可带 override_safety=true 重试(强录,会留审计)
        raise HTTPException(status_code=422, detail={
            "reason": "high_risk_drug_interaction",
            "message": "检测到高危药物相互作用(需医生评估),已阻断录入。请咨询医生;确需录入可在确认后重试。",
            "safety_alerts": result["safety_alerts"],
            "disclaimer": result["disclaimer"],
            "can_override": True,
        })
    return result


@router.get("/regimens/me")
async def list_my_regimens(
    active_only: bool = True,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """列出我的用药方案/疗程。"""
    from app.services import medication_regimen_service as mrs
    return mrs.list_regimens(db, current_user.id, active_only)


def _serialize_medication(med) -> Dict[str, Any]:
    return {
        "id": med.id,
        "user_id": med.user_id,
        "name": med.name,
        "dosage": med.dosage,
        "frequency": med.frequency,
        "times_per_day": med.times_per_day,
        "reminder_times": med.reminder_times,
        "timing_relation": med.timing_relation,
        "meal_anchor": med.meal_anchor,
        "timing_label": medication_timing_label(med.timing_relation, med.meal_anchor),
        "category": med.category,
        "purpose": med.purpose,
        "side_effects": med.side_effects,
        "interactions": med.interactions,
        "start_date": str(med.start_date) if med.start_date else None,
        "end_date": str(med.end_date) if med.end_date else None,
        "is_active": med.is_active,
        "notes": med.notes,
        "created_at": str(med.created_at) if med.created_at else None,
    }


def _medication_safety_alerts(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """新增/更新药品后的即时用药安全预览:只返回 PGx/DDI/DSI。"""
    try:
        twin = build_twin(db, user_id, use_cache=False)
        report = evaluate_safety(twin)
    except Exception as e:  # noqa: BLE001
        logger.warning("[MedAPI] 用药安全预览失败: user_id=%s error=%s", user_id, e)
        return []

    alerts = [
        a for a in report.alerts
        if a.category in _MEDICATION_SAFETY_CATEGORIES
    ]
    alerts.sort(key=lambda a: (-int(a.severity), a.category, a.rule_id))
    return [a.model_dump_for_api() for a in alerts]


def _serialize_medication_log(log: MedicationLog) -> Dict[str, Any]:
    return {
        "id": log.id,
        "user_id": log.user_id,
        "medication_id": log.medication_id,
        "taken_date": str(log.taken_date) if log.taken_date else None,
        "taken_time": log.taken_time,
        "status": log.status,
        "skip_reason": log.skip_reason,
        "actual_dosage": log.actual_dosage,
        "notes": log.notes,
        "created_at": str(log.created_at) if log.created_at else None,
    }
