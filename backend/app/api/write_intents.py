"""Write 层 v0 API —— 写意图账本(Agent 提议替你写,一键确认才执行)。

见 docs/design/health-os/architecture-lens.md「唯一真缺 = Write 层」。
v0:GET 列待确认(顺带跑「复查到点」生成器,打开即见提议)+ confirm/dismiss。
user_id 一律取自 token(不信任客户端)。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services import write_intent_service as svc
from app.services.medication_intake_batch import (
    ExpiredMedicationIntakePlan,
    MedicationIntakePlanNotPresented,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/write-intents", tags=["Write 层(写意图)"])


@router.get("")
async def list_write_intents(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """列出待确认写意图。先跑「复查到点」生成器(幂等),让用户一打开就看到该提的提议。"""
    try:
        svc.generate_followup_recall(db, current_user.id)
    except Exception as e:  # 生成器失败不该阻塞读列表(已有 pending 仍要能看)
        logger.warning(f"[write-intents] followup 生成失败(降级,仍返回现有): {e}")
        db.rollback()
    try:
        svc.generate_measurement_prompts(db, current_user.id)
    except Exception as e:  # 各生成器相互独立,一个挂不连累另一个 / 不阻塞读
        logger.warning(f"[write-intents] measurement 生成失败(降级,仍返回现有): {e}")
        db.rollback()
    try:
        svc.generate_recheck_due(db, current_user.id)
    except Exception as e:
        logger.warning(f"[write-intents] recheck-due 生成失败(降级,仍返回现有): {e}")
        db.rollback()
    try:
        svc.generate_adherence_nudge(db, current_user.id)
    except Exception as e:
        logger.warning(f"[write-intents] adherence 生成失败(降级,仍返回现有): {e}")
        db.rollback()
    try:
        svc.generate_reorder_nudges(db, current_user.id)
    except Exception as e:  # P3(D1)复购提醒生成失败 → 降级, 不阻塞读列表
        logger.warning(f"[write-intents] reorder 生成失败(降级,仍返回现有): {e}")
        db.rollback()
    try:
        svc.generate_doctor_booking_drafts(db, current_user.id)
    except Exception as e:  # P5 医生预约草稿生成失败 → 降级, 不阻塞读列表
        logger.warning(f"[write-intents] doctor-booking 生成失败(降级,仍返回现有): {e}")
        db.rollback()
    # Write 自治(首切片):所有提议生成后,对 allowlisted(仅 measurement_prompt)pending,
    # gate 全过(默认开 + 非 CRITICAL + 未超每日上限)则无需人确认自动执行;其余仍走人确认。
    try:
        from app.services import write_autonomy

        write_autonomy.auto_execute_pending(db, current_user.id)
    except Exception as e:  # 自治执行失败不阻塞列表(write_autonomy 内部已 fail-safe)
        logger.warning(f"[write-intents] 自治执行失败(降级,仍返回现有): {e}")
        db.rollback()
    return {"items": svc.list_pending(db, current_user.id)}


class ProposeExternalActionBody(BaseModel):
    kind: str = Field(
        description=(
            "外部动作类型: alarm_set / food_order / doctor_booking / "
            "environment_actuation"
        )
    )
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    payload: dict | None = None


@router.post("")
async def propose_write_intent(
    body: ProposeExternalActionBody,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """提一个外部动作写意图(propose;全 manual_confirm,确认才执行)。

    服务端 kind 白名单(alarm_set/food_order/doctor_booking/environment_actuation),
    未知 kind → 422。
    food_order 摘要先过 R4 守门(guidance_validator)再落库。幂等:同 (user,kind,target)
    已有 pending → 返回既有 id。**不在此下单/预约/支付** —— 仅记意图,确认是另一步。
    """
    try:
        wi = svc.propose_external_action(
            db,
            current_user.id,
            kind=body.kind,
            title=body.title,
            description=body.description,
            payload=body.payload,
        )
    except ValueError as e:  # 未知 kind → 422(服务端白名单门控)
        raise HTTPException(status_code=422, detail=str(e))
    if wi is None:  # 幂等:已有 pending → 返回既有
        existing = next(
            (
                it for it in svc.list_pending(db, current_user.id)
                if it["kind"] == body.kind
            ),
            None,
        )
        return {"intent": existing, "idempotent": True}
    return {"intent": svc._view(wi), "idempotent": False}


@router.post("/{intent_id}/confirm")
async def confirm_write_intent(
    intent_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """一键确认 → 执行(v0:建提醒)。不存在/非本人 → 404;执行失败 → 500(fail loud,状态退回 pending)。"""
    try:
        return svc.confirm(db, current_user.id, intent_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="写意图不存在")
    except ExpiredMedicationIntakePlan as exc:
        db.rollback()
        logger.warning(
            "[write-intents] confirm 已过期 "
            "user_id=%s intent_id=%s error_type=%s",
            current_user.id,
            intent_id,
            type(exc).__name__,
        )
        raise HTTPException(status_code=409, detail="确认计划已过期，请重新提交记录")
    except MedicationIntakePlanNotPresented as exc:
        db.rollback()
        logger.warning(
            "[write-intents] confirm 计划尚未展示 "
            "user_id=%s intent_id=%s error_type=%s",
            current_user.id,
            intent_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=409,
            detail="确认计划尚未完整展示，请等待当前回复完成后重试",
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error(
            "[write-intents] confirm 执行失败(fail loud) "
            "user_id=%s intent_id=%s error_type=%s",
            current_user.id,
            intent_id,
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="确认执行失败,请稍后重试")


@router.post("/{intent_id}/dismiss")
async def dismiss_write_intent(
    intent_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """忽略一个写意图(标记 dismissed,不执行)。不存在/非本人 → 404。"""
    try:
        return svc.dismiss(db, current_user.id, intent_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="写意图不存在")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error(
            "[write-intents] dismiss 执行失败(fail loud) "
            "user_id=%s intent_id=%s error_type=%s",
            current_user.id,
            intent_id,
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="取消执行失败,请稍后重试")
