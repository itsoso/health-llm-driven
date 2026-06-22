"""P5(D2)复购下单 API —— 财务一等对象 `ReorderIntent`(SCAFFOLD,不真下单)。

见 docs/specs/active/2026-06-22-p5-reorder-ordering.md。所有端点 user_id 取自 token
(不信任客户端);IDOR 一律 404。

⚠️ 财务硬边界:`confirm` 走到「调快手电商 skill」时 skill 契约未就绪 → **501**,
意图停在安全态 user_confirmed,**绝不**下单。后端不处理支付凭据、不扣款。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services import reorder_intent_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reorder-intents", tags=["复购下单(P5/D2 财务一等对象)"])


class ProposeReorderBody(BaseModel):
    supplement_id: int
    quantity: int = Field(gt=0, description="下单数量,必须 > 0")
    brand: str | None = None
    spec: str | None = None
    auto_reorder_enabled: bool = False
    monthly_cap_cents: int | None = Field(default=None, ge=0)


@router.post("")
async def propose_reorder(
    body: ProposeReorderBody,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """提一个复购意图(proposed)。幂等:同 (user,supplement,proposed) 已有 → 返回既有。

    quantity ≤0 → 422(Pydantic);supplement 非本人 → 404(IDOR,且不建意图)。
    """
    try:
        return svc.propose_reorder_intent(
            db,
            current_user.id,
            supplement_id=body.supplement_id,
            quantity=body.quantity,
            brand=body.brand,
            spec=body.spec,
            auto_reorder_enabled=body.auto_reorder_enabled,
            monthly_cap_cents=body.monthly_cap_cents,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="补剂不存在或不属于当前用户")


@router.get("")
async def list_reorder(
    status: str | None = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """列出当前用户的复购意图(可选 ?status 过滤)。"""
    return {"items": svc.list_reorder_intents(db, current_user.id, status)}


@router.post("/{intent_id}/confirm")
async def confirm_reorder(
    intent_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """逐笔强确认 → 调快手电商 skill 下单。

    ⚠️ 本期 skill 契约未就绪 → **501**(意图停在 user_confirmed,不下单)。
    不存在 / 非本人 → 404。月额上限超限 → 409。下单业务失败 → 200 + status=order_failed。
    """
    try:
        return await svc.confirm_reorder_intent(db, current_user.id, intent_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="复购意图不存在")
    except svc.ReorderSkillNotReady as e:
        # 财务硬门:已记录确认,但本期不下单。501 = 接缝未实现(诚实,不假装成功)。
        raise HTTPException(status_code=501, detail=str(e))
    except svc.ReorderCapExceeded as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{intent_id}/cancel")
async def cancel_reorder(
    intent_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """取消复购意图(仅 proposed / user_confirmed → cancelled)。不存在 / 非本人 → 404。"""
    try:
        return svc.cancel_reorder_intent(db, current_user.id, intent_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="复购意图不存在")
