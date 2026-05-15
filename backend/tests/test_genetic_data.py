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


class TestProfileStatus:
    """GET /genetic/profiles/{id}/status — 异步 PDF 解析进度轮询端点"""

    def test_status_processing_when_no_variants(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id,
            test_provider="测试",
            test_date=date(2025, 1, 1),
            notes="PDF 自动提取",  # 未含"完成"或"失败"
        )
        db.add(profile); db.commit(); db.refresh(profile)
        res = client.get(f"/api/v1/genetic/profiles/{profile.id}/status", headers=headers)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "processing"
        assert data["variant_count"] == 0

    def test_status_done_when_variants_exist(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(user_id=user.id, test_provider="x", test_date=date(2025, 1, 1))
        db.add(profile); db.commit(); db.refresh(profile)
        db.add(GeneticVariant(
            user_id=user.id, profile_id=profile.id, category="metabolism",
            gene_name="MTHFR", variant_name="C677T", genotype="CC",
        ))
        db.commit()
        res = client.get(f"/api/v1/genetic/profiles/{profile.id}/status", headers=headers)
        assert res.status_code == 200
        assert res.json()["status"] == "done"
        assert res.json()["variant_count"] == 1

    def test_status_failed_when_notes_contain_failure(self, client, db, auth_user_and_headers):
        user, headers = auth_user_and_headers
        profile = GeneticProfile(
            user_id=user.id, test_provider="x", test_date=date(2025, 1, 1),
            notes="PDF 提取失败: timeout",
        )
        db.add(profile); db.commit(); db.refresh(profile)
        res = client.get(f"/api/v1/genetic/profiles/{profile.id}/status", headers=headers)
        assert res.status_code == 200
        assert res.json()["status"] == "failed"

    def test_status_404_for_other_user(self, client, db, auth_user_and_headers):
        from app.models.user import User
        from app.services.auth import auth_service
        import uuid
        # 创建另一个用户的 profile, 当前用户不应能查
        other = User(
            username=f"o_{uuid.uuid4().hex[:8]}",
            email=f"o_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="x",
            name="其他用户",
            is_active=True, is_approved=True,
        )
        db.add(other); db.commit(); db.refresh(other)
        other_profile = GeneticProfile(user_id=other.id, test_provider="x", test_date=date(2025, 1, 1))
        db.add(other_profile); db.commit(); db.refresh(other_profile)

        _, headers = auth_user_and_headers
        res = client.get(f"/api/v1/genetic/profiles/{other_profile.id}/status", headers=headers)
        assert res.status_code == 404


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


# ── 23andMe / WeGene 真实格式 sample ──
# 格式: rsid\tchromosome\tposition\tgenotype  (制表符分隔, # 开头注释)
# 覆盖 8 个 KNOWN_SNPS 类别: nutrition / exercise / drug_sensitivity / disease_risk / sleep
SAMPLE_23ANDME_TXT = """\
# This data file generated by 23andMe at: Tue Mar 11 12:00:00 2025
# Below is a text version of your data.  Fields are TAB-separated
# rsid\tchromosome\tposition\tgenotype
rs1801133\t1\t11856378\tAG
rs762551\t15\t75041917\tAC
rs4988235\t2\t136608646\tGG
rs671\t12\t112241766\tGA
rs1815739\t11\t66560624\tCT
rs4244285\t10\t96541616\tGG
rs429358\t19\t45411941\tCT
rs7903146\t10\t114758349\tCC
rs9939609\t16\t53820527\tAT
rs1801260\t4\t56301369\tAA
"""


class TestSampleIntegration:
    """Day 7 集成测试: 跑真实 23andMe 格式 TXT 全流程"""

    def test_upload_real_23andme_sample(self, client, db, auth_user_and_headers):
        """端到端: TXT → upload-txt → matched → status=done → list/me 可见"""
        user, headers = auth_user_and_headers

        # 1. 上传 (使用真实 23andme 多行 sample)
        res = client.post(
            "/api/v1/genetic/profiles/upload-txt",
            json={
                "test_provider": "23andMe",
                "test_date": "2025-03-11",
                "txt_content": SAMPLE_23ANDME_TXT,
                "notes": "integration test fixture",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        data = res.json()
        profile_id = data["id"]

        # 至少应解析出几条 (sample 写入 10 个 SNP, KNOWN_SNPS 全覆盖)
        assert data["matched_count"] >= 5, f"expected >=5 matches, got {data['matched_count']}: {data}"

        # 2. status 端点应已是 done (TXT 同步, variant 已写入)
        res = client.get(f"/api/v1/genetic/profiles/{profile_id}/status", headers=headers)
        assert res.status_code == 200
        sd = res.json()
        assert sd["status"] == "done"
        assert sd["variant_count"] == data["matched_count"]

        # 3. list/me 应返回该 profile
        res = client.get("/api/v1/genetic/profiles/me", headers=headers)
        assert res.status_code == 200
        profiles = res.json()
        assert any(p["id"] == profile_id for p in profiles)

        # 4. detail 端点应包含 variants
        res = client.get(f"/api/v1/genetic/profiles/{profile_id}", headers=headers)
        assert res.status_code == 200
        detail = res.json()
        assert len(detail["variants"]) == data["matched_count"]

        # 5. summary/me 应反映新数据
        res = client.get("/api/v1/genetic/summary/me", headers=headers)
        assert res.status_code == 200
        summ = res.json()
        assert summ["total_variants"] == data["matched_count"]

    def test_upload_handles_dirty_lines(self, client, db, auth_user_and_headers):
        """耐受空行 / 注释行 / 字段不足行 / -- 占位"""
        _, headers = auth_user_and_headers
        dirty = (
            "# header comment\n"
            "\n"
            "rs1801133\t1\t11856378\tAG\n"
            "rs_not_in_dict\t1\t111\tAA\n"
            "rs762551\t15\t75041917\t--\n"  # -- 应跳过
            "broken_line_without_tabs\n"
            "rs671\t12\t112241766\tGA\n"
        )
        res = client.post(
            "/api/v1/genetic/profiles/upload-txt",
            json={
                "test_provider": "WeGene",
                "test_date": "2025-04-01",
                "txt_content": dirty,
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        # 仅 rs1801133 + rs671 应命中, rs762551 因 -- 跳过
        assert res.json()["matched_count"] == 2

    def test_upload_txt_maps_complement_strand_genotypes(self, client, db, auth_user_and_headers):
        """WeGene 原始数据可能给出与规则字典互补的等位基因, 不应漏解析."""
        _, headers = auth_user_and_headers
        complement_sample = (
            "# rsid\tchromosome\tposition\tgenotype\n"
            "rs4880\t6\t160113872\tAA\n"      # SOD2: complement -> TT
            "rs1050450\t3\t49394747\tGG\n"    # GPX1: complement -> CC
            "rs1044396\t20\t61981120\tAA\n"   # CHRNA4: complement -> TT
            "rs25531\t17\t28562759\tTT\n"     # SLC6A4: complement -> AA
        )

        res = client.post(
            "/api/v1/genetic/profiles/upload-txt",
            json={
                "test_provider": "WeGene",
                "test_date": "2026-03-29",
                "txt_content": complement_sample,
            },
            headers=headers,
        )

        assert res.status_code == 200, res.text
        data = res.json()
        assert data["matched_count"] == 4
        by_gene = {v["gene"]: v for v in data["variants"]}
        assert by_gene["SOD2"]["genotype"] == "Ala/Ala"
        assert by_gene["GPX1"]["risk"] == "medium"
        assert by_gene["CHRNA4"]["risk"] == "medium"
        assert by_gene["SLC6A4"]["risk"] == "low"
