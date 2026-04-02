"""补剂产品匹配服务 — 根据推荐名称 + 用户基因匹配联盟产品"""
from sqlalchemy.orm import Session
from app.models.affiliate_product import AffiliateProduct


def find_products(
    db: Session,
    supplement_name: str,
    category: str = "",
    user_gene_tags: list[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    """
    匹配产品并按相关性评分排序。

    评分策略:
      supplement_name 精确匹配 +10
      keywords 包含推荐名 +5
      category 匹配 +3
      gene_tags 与用户基因重叠 +8 (每个重叠 tag)
    """
    products = (
        db.query(AffiliateProduct)
        .filter(AffiliateProduct.is_active == True)  # noqa: E712
        .all()
    )

    name_lower = supplement_name.lower().strip()
    user_tags = set(t.upper() for t in (user_gene_tags or []))
    scored = []

    for p in products:
        score = 0

        # 精确名称匹配
        if p.supplement_name and p.supplement_name.lower().strip() == name_lower:
            score += 10

        # 关键词包含
        kws = p.keywords if isinstance(p.keywords, list) else []
        for kw in kws:
            if isinstance(kw, str) and kw.lower() in name_lower:
                score += 5
                break

        # 类别匹配
        if category and p.category and p.category.lower() == category.lower():
            score += 3

        # 基因标签重叠
        gene_tags = p.gene_tags if isinstance(p.gene_tags, list) else []
        product_tags = set(t.upper() for t in gene_tags if isinstance(t, str))
        overlap = user_tags & product_tags
        gene_match = len(overlap) > 0
        if gene_match:
            score += 8 * len(overlap)

        if score <= 0:
            continue

        scored.append({
            "id": p.id,
            "name": p.name,
            "brand": p.brand,
            "image_url": p.image_url,
            "platform": p.platform,
            "affiliate_url": p.affiliate_url,
            "price_display": p.price_display,
            "currency": p.currency or "CNY",
            "gene_match": gene_match,
            "gene_description": p.gene_description if gene_match else None,
            "match_score": score,
        })

    scored.sort(key=lambda x: (-x["match_score"], x.get("name", "")))
    return scored[:limit]


def get_user_gene_tags(db: Session, user_id: int) -> list[str]:
    """获取用户基因标签列表 (格式: GENE_GENOTYPE, 如 MTHFR_TT)"""
    try:
        from app.models.genetic_data import GeneticVariant
        variants = db.query(GeneticVariant).filter(
            GeneticVariant.user_id == user_id
        ).all()
        return [f"{v.gene_name}_{v.genotype}" for v in variants if v.gene_name and v.genotype]
    except Exception:
        return []
