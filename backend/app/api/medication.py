"""用药管理 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, field_validator

from datetime import date

from app.database import get_db
from app.models.medication import Medication, MedicationLog, medication_timing_label
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.medication_safety import evaluate_medication_safety_alerts
from app.services.medication_service import medication_service
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/medication", tags=["用药管理"])


def _invalidate_twin(user_id: int) -> None:
    """Fail-soft twin-cache invalidation after a write (rank7: also drops pregen)."""
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001 — a Redis error must never fail the write
        pass


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
    taken_date: Optional[date] = None
    taken_time: str
    status: str = "taken"
    skip_reason: Optional[str] = None
    actual_dosage: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("taken_time")
    @classmethod
    def _normalize_taken_time(cls, v: str) -> str:
        # 边界归一化(单一真源在 service):完整 ISO/带秒 → "HH:MM";
        # 解析不了 → 422(fail-loud),绝不让 varchar 溢出变 500。
        from app.services.medication_service import normalize_taken_time
        normalized = normalize_taken_time(v)
        if normalized is None:
            raise ValueError("taken_time 不能为空")
        return normalized


class MedicationLogUpdate(BaseModel):
    medication_id: Optional[int] = None
    taken_time: Optional[str] = None
    status: Optional[str] = None
    skip_reason: Optional[str] = None
    actual_dosage: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("taken_time")
    @classmethod
    def _normalize_taken_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        from app.services.medication_service import normalize_taken_time
        return normalize_taken_time(v)


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

    _invalidate_twin(current_user.id)
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
    safety_alerts = _medication_safety_alerts(db, current_user.id)
    return [_serialize_medication(m, safety_alerts=safety_alerts) for m in meds]


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
    return _serialize_medication(med, safety_alerts=_medication_safety_alerts(db, current_user.id))


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
    _invalidate_twin(current_user.id)
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
    _invalidate_twin(current_user.id)
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
    _invalidate_twin(current_user.id)
    return {"message": "药品已恢复"}


def _resolve_dose_slot(med: Medication, taken_time: Optional[str]) -> Optional[str]:
    """多剂药 → 本次「已服」对应的时间线剂次槽("HH:MM");单剂 → None(与存量逐字节同)。

    脊柱把真多剂(reminder_times ≥2)展开成每槽一条 HealthEvent(complete_ref 带 slot);
    单剂/每日一次无 slot。为把这次打卡完成到**正确那一剂**,按 taken_time 归一化匹配
    reminder_times:命中 → 用该槽;不命中 → 回退最早的排程槽(reminder_times[0])。
    单剂药永远返回 None(不引入 slot 键,守存量单剂闭环零变化)。
    """
    times = [t for t in (med.reminder_times or []) if t]
    if len(times) < 2:
        return None  # 单剂/每日一次:不分槽

    def _min(hhmm: Optional[str]) -> Optional[int]:
        if not hhmm:
            return None
        try:
            h, m = (int(x) for x in str(hhmm).split(":")[:2])
            return h * 60 + m
        except (ValueError, AttributeError):
            return None

    want = _min(taken_time)
    if want is not None:
        for t in times:
            if _min(t) == want:
                return t  # 命中排程剂次槽
    return times[0]  # 不命中 → 完成最早排程剂次槽


def _writeback_agenda_completion(
    db: Session, user_id: int, med: Medication, data: "MedicationLogCreate",
) -> None:
    """把这次「已服/漏服」反向完成时间线上对应的 HealthEvent(反向完成链)。

    log_medication 已把依从事实(MedicationLog)落库;这里只翻议程 HealthEvent 的
    agenda_status 账本,让待办计数 / 复盘完成率 / 手表 due 项与打卡一致。

    环形终止:MedicationLog 本次已由 API 层写过,故走 skip_writeback=True —— 完成链只做
    原子 claim + 生命周期翻态,**不**再经 complete_item 二次写领域行(否则同一「已服」落两条)。
    object_type 按药的 category 走 timing_adapter._domain(与脊柱/day_schedule 同一映射:
    补剂类 category → 'supplement',其余 → 'medication')—— 同源映射保证本 ref 与脊柱物化的
    HealthEvent ref 一致,懒物化去重命中同一条。真多剂按 taken_time 定位对应剂次槽。

    失败语义(不假装成功):log 是已落库的依从事实,完成链失败绝不 500 也不回滚 log ——
    记 warning(fail-loud 可查,非 debug 静默),响应照常成功。展示层 done 态本就从
    get_today_status 派生会自愈,滞后的只是 agenda_status 账本。
    当天无对应时间线事件(未排程/未物化)→ complete_by_ref 懒物化后完成,不报错。
    """
    from app.services import timeline_agenda_service as tas
    from app.services.timing_adapter import _domain

    # 延迟点击旧通知时，服药事实属于提醒发生日。时间线完成接口只面向“今天”，
    # 因此旧日期仅写 MedicationLog，绝不能把今天同一药物的待办误标完成。
    if data.taken_date is not None and data.taken_date != get_user_today(db, user_id):
        return

    object_type = _domain(med)  # 'supplement' 或 'medication'(category 权威映射)
    agenda_status = "skipped" if data.status == "skipped" else "done"
    skip_reason = data.skip_reason if agenda_status == "skipped" else None
    slot = _resolve_dose_slot(med, data.taken_time)
    try:
        tas.complete_by_ref(
            db, user_id, object_type, med.id,
            status=agenda_status, skip_reason=skip_reason,
            slot=slot, skip_writeback=True,
        )
    except Exception as e:  # noqa: BLE001 — 依从事实已落库,完成链失败不拖垮打卡
        logger.warning(
            "[medication] agenda writeback failed user=%s med=%s status=%s slot=%s: %s",
            user_id, med.id, agenda_status, slot, e,
        )


@router.post("/logs")
async def log_medication(
    data: MedicationLogCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """记录服药"""
    logger.info(f"[MedAPI] 用户 {current_user.id} 记录服药: med={data.medication_id}")
    med = medication_service.get_medication(db, data.medication_id, current_user.id)
    if med is None:
        raise HTTPException(status_code=404, detail="药品不存在")
    log = medication_service.log_medication(
        db=db,
        user_id=current_user.id,
        medication_id=data.medication_id,
        taken_time=data.taken_time,
        status=data.status,
        skip_reason=data.skip_reason,
        actual_dosage=data.actual_dosage,
        notes=data.notes,
        taken_date=data.taken_date,
    )
    # 反向完成链:药物归属已在写日志前验证；完成链失败不拖垮已落库事实。
    _writeback_agenda_completion(db, current_user.id, med, data)
    _invalidate_twin(current_user.id)
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
    _invalidate_twin(current_user.id)
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
    _invalidate_twin(current_user.id)
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
    from app.utils.timezone import get_user_today
    meds = db.query(Medication).filter(
        Medication.user_id == current_user.id, Medication.is_active == True  # noqa: E712
    ).all()
    payload = [{"name": m.name, "start_date": m.start_date, "end_date": m.end_date} for m in meds]
    # 用药时长/过期判定按用户本地时区的日历日(缺省回退中国时区)
    return review_medications(payload, today=get_user_today(db, current_user.id))


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
    _invalidate_twin(current_user.id)
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


def _serialize_medication(med, safety_alerts: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    body = {
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
    if safety_alerts is not None:
        body["safety_alerts"] = safety_alerts
    return body


def _medication_safety_alerts(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """Compatibility wrapper for the shared deterministic medication precheck."""
    return evaluate_medication_safety_alerts(db, user_id)


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
