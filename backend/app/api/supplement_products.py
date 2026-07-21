"""补剂产品库 API — 公共知识库，管理员维护"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models import User, SupplementProduct
from app.models.genetic_data import GeneticVariant
from app.schemas.supplement import (
    SupplementProductCreate, SupplementProductUpdate,
    SupplementProductResponse, SupplementProductListResponse,
)

router = APIRouter(prefix="/supplements/products", tags=["supplement-products"])


def _require_admin(user: User):
    if not getattr(user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="仅管理员可操作产品库")


# ── 公共查询（所有登录用户） ──

@router.get("", response_model=SupplementProductListResponse)
def list_products(
    search: Optional[str] = Query(None, description="搜索名称或品牌"),
    category: Optional[str] = Query(None, description="分类筛选"),
    brand: Optional[str] = Query(None),
    tag: Optional[str] = Query(None, description="健康标签筛选"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """浏览产品库"""
    q = db.query(SupplementProduct).filter(SupplementProduct.is_active == True)
    if search:
        q = q.filter(
            (SupplementProduct.name.ilike(f"%{search}%")) |
            (SupplementProduct.brand.ilike(f"%{search}%"))
        )
    if category:
        q = q.filter(SupplementProduct.category == category)
    if brand:
        q = q.filter(SupplementProduct.brand.ilike(f"%{brand}%"))
    # tag filtering on JSONB array
    if tag:
        q = q.filter(SupplementProduct.health_tags.contains([tag]))

    total = q.count()
    items = q.order_by(SupplementProduct.brand, SupplementProduct.name).offset(offset).limit(limit).all()
    return SupplementProductListResponse(items=items, total=total)


@router.get("/{product_id}", response_model=SupplementProductResponse)
def get_product(
    product_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """产品详情"""
    product = db.query(SupplementProduct).filter(SupplementProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    return product


@router.get("/compare/list")
def compare_products(
    ids: str = Query(..., description="产品ID列表，逗号分隔，如 1,2,3"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """产品对比 — 并排展示成分表"""
    id_list = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    if len(id_list) < 2 or len(id_list) > 5:
        raise HTTPException(status_code=400, detail="对比产品数量需在2-5之间")

    products = db.query(SupplementProduct).filter(SupplementProduct.id.in_(id_list)).all()
    if len(products) < 2:
        raise HTTPException(status_code=404, detail="未找到足够产品")

    # 构建成分对照表
    all_ingredients = set()
    for p in products:
        for ing in (p.ingredients or []):
            all_ingredients.add(ing.get("name", ""))

    comparison = []
    for name in sorted(all_ingredients):
        row = {"ingredient": name}
        for p in products:
            matched = next((i for i in (p.ingredients or []) if i.get("name") == name), None)
            row[f"product_{p.id}"] = {
                "amount": matched.get("amount", "-") if matched else "-",
                "form": matched.get("form", "") if matched else "",
            }
        comparison.append(row)

    return {
        "products": [SupplementProductResponse.model_validate(p) for p in products],
        "comparison": comparison,
    }


@router.get("/recommended/for-me")
def recommended_for_user(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """基于用户基因数据推荐产品"""
    # 获取用户基因变异
    variants = db.query(GeneticVariant).filter(
        GeneticVariant.user_id == current_user.id
    ).all()
    user_genes = {f"{v.gene_name}_{v.genotype}" for v in variants}
    gene_names = {v.gene_name for v in variants}

    products = db.query(SupplementProduct).filter(
        SupplementProduct.is_active == True
    ).all()

    scored = []
    for p in products:
        score = 0
        reasons = []
        for rel in (p.gene_relevance or []):
            gene = rel.get("gene", "")
            if gene in gene_names:
                score += 10
                reasons.append(rel.get("relevance", f"与{gene}基因相关"))
        if score > 0:
            scored.append({
                "product": SupplementProductResponse.model_validate(p),
                "relevance_score": score,
                "reasons": reasons,
            })

    scored.sort(key=lambda x: -x["relevance_score"])
    return {"recommendations": scored}


# ── 管理员操作 ──

@router.post("", response_model=SupplementProductResponse)
def create_product(
    data: SupplementProductCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建产品（管理员）"""
    _require_admin(current_user)
    product = SupplementProduct(
        **data.model_dump(),
        created_by=current_user.id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=SupplementProductResponse)
def update_product(
    product_id: int,
    data: SupplementProductUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新产品（管理员）"""
    _require_admin(current_user)
    product = db.query(SupplementProduct).filter(SupplementProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(product, key, val)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除产品（管理员，软删除）"""
    _require_admin(current_user)
    product = db.query(SupplementProduct).filter(SupplementProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    product.is_active = False
    db.commit()
    return {"message": "产品已删除"}
