"""联盟产品 API + 产品匹配 测试"""
import pytest
from tests.conftest import create_authenticated_user
from app.models.affiliate_product import AffiliateProduct


def _seed_products(db):
    """插入测试产品"""
    products = [
        AffiliateProduct(
            name="Thorne 5-MTHF 1mg", brand="Thorne", supplement_name="活性叶酸",
            category="basic", keywords=["叶酸", "5-MTHF", "甲基叶酸"],
            platform="iherb", affiliate_url="https://iherb.com/thorne-5mthf",
            price_display="$16.00", currency="USD",
            gene_tags=["MTHFR_TT", "MTHFR_CT"], gene_description="适合MTHFR变异用户",
        ),
        AffiliateProduct(
            name="Jarrow 甲基叶酸 400mcg", brand="Jarrow", supplement_name="活性叶酸",
            category="basic", keywords=["叶酸", "甲基叶酸"],
            platform="iherb", affiliate_url="https://iherb.com/jarrow-folate",
            price_display="$8.49", currency="USD",
            gene_tags=["MTHFR_TT"], gene_description="适合MTHFR TT变异",
        ),
        AffiliateProduct(
            name="Now Foods 维D3 5000IU", brand="Now Foods", supplement_name="维生素D3",
            category="basic", keywords=["维D", "维生素D", "VD3"],
            platform="iherb", affiliate_url="https://iherb.com/now-vd3",
            price_display="$11.99", currency="USD",
            gene_tags=["VDR_TT"], gene_description="适合VDR变异用户",
        ),
        AffiliateProduct(
            name="已下架产品", brand="Test", supplement_name="活性叶酸",
            category="basic", keywords=["叶酸"],
            platform="iherb", affiliate_url="https://iherb.com/disabled",
            is_active=False,
        ),
    ]
    db.add_all(products)
    db.commit()


# ── 产品匹配服务测试 ──────────────────────────────────

def test_match_exact_name(db):
    """精确名称匹配"""
    _seed_products(db)
    from app.services.product_matching import find_products
    results = find_products(db, "活性叶酸")
    assert len(results) >= 2
    assert all(r["name"] != "已下架产品" for r in results)


def test_match_excludes_inactive(db):
    """不返回已下架产品"""
    _seed_products(db)
    from app.services.product_matching import find_products
    results = find_products(db, "活性叶酸", limit=10)
    names = [r["name"] for r in results]
    assert "已下架产品" not in names


def test_match_with_gene_boost(db):
    """有基因数据时，匹配基因标签的产品排名更高"""
    _seed_products(db)
    from app.services.product_matching import find_products
    results = find_products(db, "活性叶酸", user_gene_tags=["MTHFR_TT"])
    assert len(results) >= 2
    # 所有结果都应该有 gene_match=True（因为两个叶酸产品都有 MTHFR_TT）
    assert results[0]["gene_match"] is True
    assert results[0]["gene_description"] is not None


def test_match_category_fallback(db):
    """类别匹配作为兜底"""
    _seed_products(db)
    from app.services.product_matching import find_products
    results = find_products(db, "不存在的补剂", category="basic")
    assert len(results) > 0  # 通过 category 兜底匹配


def test_match_empty_catalog(db):
    """空目录返回空列表"""
    from app.services.product_matching import find_products
    results = find_products(db, "活性叶酸")
    assert results == []


def test_match_limit(db):
    """限制返回数量"""
    _seed_products(db)
    from app.services.product_matching import find_products
    results = find_products(db, "活性叶酸", limit=1)
    assert len(results) == 1


def test_match_no_gene_tags(db):
    """无基因数据时，gene_match 应为 False"""
    _seed_products(db)
    from app.services.product_matching import find_products
    results = find_products(db, "活性叶酸", user_gene_tags=None)
    for r in results:
        assert r["gene_match"] is False


# ── API 端点测试 ──────────────────────────────────────

def test_match_api(client, db):
    """GET /affiliate-products/match 需要登录"""
    _seed_products(db)
    user, token = create_authenticated_user(db)
    resp = client.get(
        "/api/v1/affiliate-products/match?supplement_name=活性叶酸",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


def test_match_api_unauthorized(client, db):
    """未登录返回 401"""
    resp = client.get("/api/v1/affiliate-products/match?supplement_name=活性叶酸")
    assert resp.status_code == 401


def test_admin_create(client, db):
    """管理员可以创建产品"""
    user, token = create_authenticated_user(db)
    user.is_admin = True
    db.commit()

    resp = client.post(
        "/api/v1/affiliate-products",
        json={
            "name": "Test Product",
            "supplement_name": "测试补剂",
            "affiliate_url": "https://example.com/test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Product"
    assert data["id"] > 0


def test_non_admin_create_forbidden(client, db):
    """非管理员创建返回 403"""
    user, token = create_authenticated_user(db)
    resp = client.post(
        "/api/v1/affiliate-products",
        json={
            "name": "Test Product",
            "supplement_name": "测试补剂",
            "affiliate_url": "https://example.com/test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_update(client, db):
    """管理员可以更新产品"""
    _seed_products(db)
    user, token = create_authenticated_user(db)
    user.is_admin = True
    db.commit()

    product = db.query(AffiliateProduct).filter(AffiliateProduct.is_active == True).first()
    resp = client.put(
        f"/api/v1/affiliate-products/{product.id}",
        json={"price_display": "$99.99"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["price_display"] == "$99.99"


def test_admin_delete_soft(client, db):
    """删除是软删除（设 is_active=False）"""
    _seed_products(db)
    user, token = create_authenticated_user(db)
    user.is_admin = True
    db.commit()

    product = db.query(AffiliateProduct).filter(AffiliateProduct.is_active == True).first()
    resp = client.delete(
        f"/api/v1/affiliate-products/{product.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    db.refresh(product)
    assert product.is_active is False


def test_admin_list(client, db):
    """管理员可以列出产品"""
    _seed_products(db)
    user, token = create_authenticated_user(db)
    user.is_admin = True
    db.commit()

    resp = client.get(
        "/api/v1/affiliate-products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3  # 3 active products (inactive excluded by default)
