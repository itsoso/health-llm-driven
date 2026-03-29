"""基因数据 API 测试"""
import pytest
from datetime import date

from app.models.genetic_data import GeneticProfile, GeneticVariant


class TestCreateProfile:
    """POST /genetic/profiles"""

    def test_create_profile(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        res = client.post(
            "/api/v1/genetic/profiles",
            json={
                "test_provider": "华大基因",
                "test_date": "2025-06-01",
                "report_id": "BGI-20250601",
                "notes": "全基因组测序",
            },
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["test_provider"] == "华大基因"
        assert data["test_date"] == "2025-06-01"
        assert data["report_id"] == "BGI-20250601"
        assert data["id"] > 0


class TestListProfiles:
    """GET /genetic/profiles/me"""

    def test_returns_empty_list(self, client, db, auth_user_and_headers):
        _, headers = auth_user_and_headers
        res = client.get("/api/v1/genetic/profiles/me", headers=headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_list_profiles(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="微基因",
            test_date=date(2025, 3, 15),
            report_id="WGX-001",
        )
        db.add(profile)
        db.commit()

        res = client.get("/api/v1/genetic/profiles/me", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["test_provider"] == "微基因"


class TestGetProfileDetail:
    """GET /genetic/profiles/{id}"""

    def test_nonexistent_profile_returns_404(self, client, db, auth_user_and_headers):
        _, headers = auth_user_and_headers
        res = client.get("/api/v1/genetic/profiles/99999", headers=headers)
        assert res.status_code == 404

    def test_get_profile_detail(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="华大基因",
            test_date=date(2025, 6, 1),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        # 添加变异位点
        variant = GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            category="nutrition",
            gene_name="MTHFR",
            variant_name="C677T",
            genotype="CT",
            result_label="叶酸代谢能力降低",
            risk_level="medium",
        )
        db.add(variant)
        db.commit()

        res = client.get(f"/api/v1/genetic/profiles/{profile.id}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["test_provider"] == "华大基因"
        assert len(data["variants"]) == 1
        assert data["variants"][0]["gene_name"] == "MTHFR"


class TestDeleteProfile:
    """DELETE /genetic/profiles/{id} — cascade deletes variants"""

    def test_delete_profile_cascades(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="微基因",
            test_date=date(2025, 1, 1),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        # 添加变异位点
        variant = GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            category="exercise",
            gene_name="ACTN3",
            genotype="CC",
            risk_level="info",
        )
        db.add(variant)
        db.commit()

        # 删除 profile
        res = client.delete(f"/api/v1/genetic/profiles/{profile.id}", headers=headers)
        assert res.status_code == 200

        # 确认变异也被删除
        remaining = db.query(GeneticVariant).filter(GeneticVariant.profile_id == profile.id).all()
        assert len(remaining) == 0


class TestBatchCreateVariants:
    """POST /genetic/variants/batch"""

    def test_batch_create_variants(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="华大基因",
            test_date=date(2025, 6, 1),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        res = client.post(
            "/api/v1/genetic/variants/batch",
            json={
                "variants": [
                    {
                        "profile_id": profile.id,
                        "category": "nutrition",
                        "gene_name": "MTHFR",
                        "variant_name": "C677T",
                        "genotype": "CT",
                        "result_label": "叶酸代谢能力降低",
                        "risk_level": "medium",
                    },
                    {
                        "profile_id": profile.id,
                        "category": "exercise",
                        "gene_name": "ACTN3",
                        "genotype": "CC",
                        "result_label": "耐力型",
                        "risk_level": "info",
                    },
                ]
            },
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["created"] == 2
        assert len(data["ids"]) == 2

    def test_batch_create_invalid_profile(self, client, db, auth_user_and_headers):
        """引用不存在的 profile 应返回 404"""
        _, headers = auth_user_and_headers
        res = client.post(
            "/api/v1/genetic/variants/batch",
            json={
                "variants": [
                    {
                        "profile_id": 99999,
                        "category": "nutrition",
                        "gene_name": "MTHFR",
                    }
                ]
            },
            headers=headers,
        )
        assert res.status_code == 404


class TestUpdateVariant:
    """PUT /genetic/variants/{id}"""

    def test_update_variant(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="华大基因",
            test_date=date(2025, 6, 1),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        variant = GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            category="nutrition",
            gene_name="MTHFR",
            risk_level="info",
        )
        db.add(variant)
        db.commit()
        db.refresh(variant)

        res = client.put(
            f"/api/v1/genetic/variants/{variant.id}",
            json={"risk_level": "high", "description": "需要补充叶酸"},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["risk_level"] == "high"
        assert data["description"] == "需要补充叶酸"


class TestDeleteVariant:
    """DELETE /genetic/variants/{id}"""

    def test_delete_variant(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="华大基因",
            test_date=date(2025, 6, 1),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        variant = GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            category="sleep",
            gene_name="CLOCK",
            risk_level="low",
        )
        db.add(variant)
        db.commit()
        db.refresh(variant)

        res = client.delete(f"/api/v1/genetic/variants/{variant.id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["id"] == variant.id

        # 确认已删除
        assert db.query(GeneticVariant).filter(GeneticVariant.id == variant.id).first() is None


class TestListVariantsByCategory:
    """GET /genetic/variants/me?category=..."""

    def test_list_variants_by_category(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="华大基因",
            test_date=date(2025, 6, 1),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        for cat, gene in [("nutrition", "MTHFR"), ("exercise", "ACTN3"), ("nutrition", "FTO")]:
            db.add(GeneticVariant(
                user_id=user.id,
                profile_id=profile.id,
                category=cat,
                gene_name=gene,
                risk_level="info",
            ))
        db.commit()

        # 不过滤：应返回全部 3 条
        res = client.get("/api/v1/genetic/variants/me", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) == 3

        # 过滤 nutrition：应返回 2 条
        res = client.get("/api/v1/genetic/variants/me?category=nutrition", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        assert all(v["category"] == "nutrition" for v in data)


class TestSummary:
    """GET /genetic/summary/me"""

    def test_summary(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="华大基因",
            test_date=date(2025, 6, 1),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        db.add(GeneticVariant(
            user_id=user.id, profile_id=profile.id,
            category="nutrition", gene_name="MTHFR", risk_level="high",
        ))
        db.add(GeneticVariant(
            user_id=user.id, profile_id=profile.id,
            category="nutrition", gene_name="FTO", risk_level="low",
        ))
        db.add(GeneticVariant(
            user_id=user.id, profile_id=profile.id,
            category="exercise", gene_name="ACTN3", risk_level="info",
        ))
        db.commit()

        res = client.get("/api/v1/genetic/summary/me", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total_variants"] == 3
        assert "nutrition" in data["categories"]
        assert data["categories"]["nutrition"]["count"] == 2
        assert len(data["categories"]["nutrition"]["high_risk"]) == 1
        assert data["categories"]["nutrition"]["high_risk"][0]["gene_name"] == "MTHFR"


class TestOtherUserCannotAccess:
    """安全测试：用户不能访问他人数据"""

    def test_other_user_cannot_access(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers

        # 用另一个用户的 ID 创建 profile（模拟数据库中存在其他用户数据）
        other_profile = GeneticProfile(
            user_id=99999,  # 其他用户
            test_provider="其他",
            test_date=date(2025, 1, 1),
        )
        db.add(other_profile)
        db.commit()
        db.refresh(other_profile)

        # 当前用户尝试访问
        res = client.get(f"/api/v1/genetic/profiles/{other_profile.id}", headers=headers)
        assert res.status_code == 404

        # 当前用户尝试删除
        res = client.delete(f"/api/v1/genetic/profiles/{other_profile.id}", headers=headers)
        assert res.status_code == 404

        # profiles/me 不应返回其他用户数据
        res = client.get("/api/v1/genetic/profiles/me", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) == 0
