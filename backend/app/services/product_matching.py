"""补剂产品匹配服务 — 根据推荐名称 + 用户基因匹配联盟产品 & 产品知识库"""
import logging
from sqlalchemy.orm import Session
from app.models.affiliate_product import AffiliateProduct
from app.models.supplement import SupplementProduct

logger = logging.getLogger(__name__)


def find_products(
    db: Session,
    supplement_name: str,
    category: str = "",
    user_gene_tags: list[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    """
    匹配产品并按相关性评分排序。

    先搜索联盟产品，再搜索产品知识库，合并去重后返回。

    评分策略:
      supplement_name 精确匹配 +10
      keywords/health_tags 包含推荐名 +5
      category 匹配 +3
      gene_tags 与用户基因重叠 +8 (每个重叠 tag)
    """
    name_lower = supplement_name.lower().strip()
    user_tags = set(t.upper() for t in (user_gene_tags or []))
    scored = []

    # --- 1. 搜索联盟产品 ---
    try:
        affiliate_products = (
            db.query(AffiliateProduct)
            .filter(AffiliateProduct.is_active == True)  # noqa: E712
            .all()
        )
        for p in affiliate_products:
            score = 0
            if p.supplement_name and p.supplement_name.lower().strip() == name_lower:
                score += 10
            kws = p.keywords if isinstance(p.keywords, list) else []
            for kw in kws:
                if isinstance(kw, str) and kw.lower() in name_lower:
                    score += 5
                    break
            if category and p.category and p.category.lower() == category.lower():
                score += 3
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
                "source": "affiliate",
            })
    except Exception as e:
        logger.warning(f"[产品匹配] 联盟产品搜索失败: {e}")

    # --- 2. 搜索产品知识库 ---
    try:
        kb_products = (
            db.query(SupplementProduct)
            .filter(SupplementProduct.is_active == True)  # noqa: E712
            .all()
        )
        for p in kb_products:
            score = 0
            # 名称匹配（产品名或成分名）
            p_name = (p.name or "").lower()
            p_brand = (p.brand or "").lower()
            if name_lower in p_name or p_name in name_lower:
                score += 10
            # 健康标签匹配
            tags = p.health_tags if isinstance(p.health_tags, list) else []
            for tag in tags:
                if isinstance(tag, str) and (tag.lower() in name_lower or name_lower in tag.lower()):
                    score += 5
                    break
            # 成分名匹配
            for ing in (p.ingredients or []):
                ing_name = (ing.get("name", "") or "").lower()
                if name_lower in ing_name or ing_name in name_lower:
                    score += 8
                    break
            # 分类匹配
            if category and p.category and p.category.lower() == category.lower():
                score += 3
            # 基因关联匹配
            gene_match = False
            gene_desc = None
            for rel in (p.gene_relevance or []):
                gene = (rel.get("gene", "") or "").upper()
                genotype = (rel.get("genotype", "") or "").upper()
                for ut in user_tags:
                    if gene and gene in ut:
                        score += 8
                        gene_match = True
                        gene_desc = rel.get("relevance", "")
                        break
                if gene_match:
                    break
            if score <= 0:
                continue
            # 格式化价格
            price_display = None
            if p.price_cny:
                price_display = f"¥{float(p.price_cny):.0f}"
                if p.price_per_serving:
                    price_display += f" (¥{float(p.price_per_serving):.2f}/份)"
            scored.append({
                "id": p.id,
                "name": p.name,
                "brand": p.brand,
                "image_url": p.image_url,
                "platform": p.platform or "iherb",
                "affiliate_url": p.purchase_url or "",
                "price_display": price_display,
                "currency": "CNY",
                "gene_match": gene_match,
                "gene_description": gene_desc,
                "match_score": score,
                "source": "knowledge_base",
            })
    except Exception as e:
        logger.warning(f"[产品匹配] 产品知识库搜索失败: {e}")

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
