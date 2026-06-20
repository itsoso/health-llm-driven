"""Write 层 v0 API —— 写意图账本(Agent 提议替你写,一键确认才执行)。

见 docs/design/health-os/architecture-lens.md「唯一真缺 = Write 层」。
v0:GET 列待确认(顺带跑「复查到点」生成器,打开即见提议)+ confirm/dismiss。
user_id 一律取自 token(不信任客户端)。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services import write_intent_service as svc

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
    return {"items": svc.list_pending(db, current_user.id)}


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
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error(f"[write-intents] confirm 执行失败(fail loud): {e}", exc_info=True)
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
