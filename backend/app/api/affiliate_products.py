"""联盟产品 API — 管理员 CRUD + 用户产品匹配"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.affiliate_product import AffiliateProduct
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.affiliate_product import (
    AffiliateProductCreate,
    AffiliateProductUpdate,
    AffiliateProductResponse,
    ProductMatchResult,
)
from app.services.product_matching import find_products, get_user_gene_tags
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(user: User) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ── 公开端点（需登录） ──────────────────────────────────

@router.get("/match", response_model=list[ProductMatchResult])
async def match_products(
    supplement_name: str = Query(..., description="补剂名称"),
    category: str = Query("", description="补剂分类"),
    limit: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """根据补剂名称匹配可购买产品，结合用户基因加权"""
    gene_tags = get_user_gene_tags(db, user.id)
    results = find_products(db, supplement_name, category, gene_tags, limit)
    return results


# ── 管理员端点 ──────────────────────────────────────────

@router.get("", response_model=list[AffiliateProductResponse])
async def list_products(
    platform: Optional[str] = None,
    category: Optional[str] = None,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """列出产品（管理员）"""
    _require_admin(user)
    q = db.query(AffiliateProduct)
    if active_only:
        q = q.filter(AffiliateProduct.is_active == True)  # noqa: E712
    if platform:
        q = q.filter(AffiliateProduct.platform == platform)
    if category:
        q = q.filter(AffiliateProduct.category == category)
    return q.order_by(AffiliateProduct.sort_order, AffiliateProduct.id).offset(skip).limit(limit).all()


@router.post("", response_model=AffiliateProductResponse, status_code=201)
async def create_product(
    data: AffiliateProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """创建产品（管理员）"""
    _require_admin(user)
    product = AffiliateProduct(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=AffiliateProductResponse)
async def update_product(
    product_id: int,
    data: AffiliateProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """更新产品（管理员）"""
    _require_admin(user)
    product = db.query(AffiliateProduct).filter(AffiliateProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(product, k, v)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """软删除产品（管理员）"""
    _require_admin(user)
    product = db.query(AffiliateProduct).filter(AffiliateProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    product.is_active = False
    db.commit()
    return {"detail": "已下架"}
