"""D1 补剂库存 + 复购检测 API(P3:检测 + 提醒,**不下单**)。

挂在 /api/v1/supplements 下(与既有补剂路由同前缀,但单独成文件防 supplements.py 继续膨胀)。

端点:
- GET  /supplements/inventory                       → 每个活跃补剂的库存 + days_remaining + status
- POST /supplements/inventory/{supplement_id}/restock → 补货(累加 units_added,记 last_restock_date)
- PUT  /supplements/inventory/{supplement_id}        → 手动修正剩余量

边界(safety):这些端点只读写物流事实(剩余量/品牌/规格/补货日),无价格/支付/订单/购买动作。
财务面下单是 PRD §3.D2(P5),不在此实现。units_added 必填且 > 0(无静默默认,踩过端点默认掩
盖弱模型漏参的坑)。IDOR:supplement_id 必须属于调用方,否则 404。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.supplement import SupplementDefinition
from app.models.supplement_inventory import SupplementInventory
from app.models.user import User
from app.services import reorder_detection

router = APIRouter()


class InventoryItem(BaseModel):
    supplement_id: int
    name: str
    brand: str
    spec: str
    units_remaining: Optional[int]
    daily_consumption: Optional[float]
    days_remaining: Optional[float]
    status: str  # "ok" | "low" | "unknown"


class InventoryListResponse(BaseModel):
    items: List[InventoryItem]


class RestockRequest(BaseModel):
    # 必填且 > 0:不给静默默认(端点默认会掩盖弱模型漏传参 → 记错值)。
    units_added: int = Field(..., gt=0, description="本次补货新增单位数(必填, 必须 > 0)")
    brand: Optional[str] = None
    spec: Optional[str] = None
    package_units: Optional[int] = Field(default=None, gt=0)


class ManualSetRequest(BaseModel):
    units_remaining: int = Field(..., ge=0, description="手动修正后的剩余单位数(>= 0)")


def _owned_supplement(db: Session, user_id: int, supplement_id: int) -> SupplementDefinition:
    supp = (
        db.query(SupplementDefinition)
        .filter(
            SupplementDefinition.id == supplement_id,
            SupplementDefinition.user_id == user_id,
        )
        .first()
    )
    if supp is None:  # IDOR / 不存在统一 404(不泄露他人补剂存在性)
        raise HTTPException(status_code=404, detail="补剂不存在")
    return supp


def _item_for(db: Session, user_id: int, supplement_id: int) -> Dict[str, Any]:
    """单条 InventoryItem(restock/set 后返回更新态)。复用 detect_for_user 保证口径一致。"""
    for it in reorder_detection.detect_for_user(db, user_id):
        if it["supplement_id"] == supplement_id:
            return it
    # 理论不可达(已 _owned_supplement 校验):活跃补剂必在列表里。fail loud。
    raise HTTPException(status_code=404, detail="补剂不存在")


@router.get("/inventory", response_model=InventoryListResponse)
def get_inventory(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """当前用户每个活跃补剂的库存 + 估计日消耗 + 剩余天数 + 复购状态。

    缺库存的补剂 units_remaining=None, status=unknown。days_remaining 可能是小数。
    """
    items = reorder_detection.detect_for_user(db, current_user.id)
    return {"items": items}


@router.post("/inventory/{supplement_id}/restock", response_model=InventoryItem)
def restock_inventory(
    supplement_id: int,
    req: RestockRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """补货:累加 units_added 到 units_remaining(无库存行则建),记今天为 last_restock_date。

    brand/spec/package_units 给定则更新。units_added 必填 > 0(Pydantic 校验,缺/<=0 → 422)。
    并发建行撞唯一约束 → 回滚重读再累加(不静默丢补货)。
    """
    _owned_supplement(db, current_user.id, supplement_id)

    inv = (
        db.query(SupplementInventory)
        .filter(SupplementInventory.supplement_id == supplement_id)
        .first()
    )
    if inv is None:
        inv = SupplementInventory(
            user_id=current_user.id,
            supplement_id=supplement_id,
            units_remaining=req.units_added,
            package_units=req.package_units,
            brand=req.brand,
            spec=req.spec,
            last_restock_date=date.today(),
        )
        db.add(inv)
        try:
            db.commit()
        except IntegrityError:
            # 并发另一请求先建了该补剂库存行(uq_supp_inventory_supplement)→ 回滚, 重读累加
            db.rollback()
            inv = (
                db.query(SupplementInventory)
                .filter(SupplementInventory.supplement_id == supplement_id)
                .first()
            )
            if inv is None:  # 撞约束却查不到 → 反常, fail loud
                raise
            inv.units_remaining = (inv.units_remaining or 0) + req.units_added
            if req.package_units is not None:
                inv.package_units = req.package_units
            if req.brand is not None:
                inv.brand = req.brand
            if req.spec is not None:
                inv.spec = req.spec
            inv.last_restock_date = date.today()
            db.commit()
    else:
        inv.units_remaining = (inv.units_remaining or 0) + req.units_added
        if req.package_units is not None:
            inv.package_units = req.package_units
        if req.brand is not None:
            inv.brand = req.brand
        if req.spec is not None:
            inv.spec = req.spec
        inv.last_restock_date = date.today()
        db.commit()

    return _item_for(db, current_user.id, supplement_id)


@router.put("/inventory/{supplement_id}", response_model=InventoryItem)
def set_inventory(
    supplement_id: int,
    req: ManualSetRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """手动修正剩余量(覆盖 units_remaining)。无库存行则建一行。"""
    _owned_supplement(db, current_user.id, supplement_id)

    inv = (
        db.query(SupplementInventory)
        .filter(SupplementInventory.supplement_id == supplement_id)
        .first()
    )
    if inv is None:
        inv = SupplementInventory(
            user_id=current_user.id,
            supplement_id=supplement_id,
            units_remaining=req.units_remaining,
        )
        db.add(inv)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            inv = (
                db.query(SupplementInventory)
                .filter(SupplementInventory.supplement_id == supplement_id)
                .first()
            )
            if inv is None:
                raise
            inv.units_remaining = req.units_remaining
            db.commit()
    else:
        inv.units_remaining = req.units_remaining
        db.commit()

    return _item_for(db, current_user.id, supplement_id)
