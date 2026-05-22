"""Regression tests for the genetics import/report/prediction safety layer."""

from datetime import date

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.services import genetic_report


def _profile(db, user_id, provider="WeGene"):
    profile = GeneticProfile(
        user_id=user_id,
        test_provider=provider,
        test_date=date(2026, 1, 1),
        notes="test",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _variant(db, profile, **kwargs):
    payload = {
        "user_id": profile.user_id,
        "profile_id": profile.id,
        "rsid": kwargs.pop("rsid", None),
        "category": kwargs.pop("category", "nutrition"),
        "gene_name": kwargs.pop("gene_name", "MTHFR"),
        "variant_name": kwargs.pop("variant_name", "A1298C"),
        "genotype": kwargs.pop("genotype", "CT"),
        "result_label": kwargs.pop("result_label", "other MTHFR variant"),
        "risk_level": kwargs.pop("risk_level", "medium"),
    }
    payload.update(kwargs)
    variant = GeneticVariant(**payload)
    db.add(variant)
    db.commit()
    return variant


def test_report_does_not_match_different_variant_from_same_gene(db, auth_user_and_headers):
    """MTHFR A1298C must not make rs1801133/C677T appear as a hit."""
    user, _ = auth_user_and_headers
    profile = _profile(db, user.id)
    _variant(db, profile, gene_name="MTHFR", variant_name="A1298C", rsid=None)

    report = genetic_report.build_report(db, user.id)

    c677t = next(item for item in report["items"] if item["rsid"] == "rs1801133")
    assert c677t["hit"] is False
    assert c677t["genotype"] is None


def test_upload_txt_creates_import_job_and_coverage_summary(client, auth_user_and_headers):
    user, headers = auth_user_and_headers
    txt = "\n".join([
        "# WeGene raw data",
        "rs1801133\t1\t11856378\tAG",
        "rs7903146\t10\t114758349\tCT",
        "rs1801133\t1\t11856378\tAG",
        "rs999999999\t1\t1\tAA",
    ])

    res = client.post(
        "/api/v1/genetic/profiles/upload-txt",
        headers=headers,
        json={
            "test_provider": "WeGene",
            "test_date": "2026-05-16",
            "txt_content": txt,
        },
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["matched_count"] == 2
    assert body["import_job"]["status"] == "done"
    assert body["import_job"]["duplicate_count"] == 1
    assert body["coverage"]["present"] == 2
    assert body["coverage"]["known_total"] >= 52
    assert "missing_by_rsids" in body["coverage"]


def test_profile_status_prefers_import_job_status(client, db, auth_user_and_headers):
    from app.models.genetic_data import GeneticImportJob

    user, headers = auth_user_and_headers
    profile = _profile(db, user.id)
    job = GeneticImportJob(
        user_id=user.id,
        profile_id=profile.id,
        source_type="pdf",
        provider="WeGene",
        status="queued",
        parser_version="genetic-import-v2",
    )
    db.add(job)
    db.commit()

    res = client.get(f"/api/v1/genetic/profiles/{profile.id}/status", headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "queued"
    assert body["import_job"]["id"] == job.id


def test_snp_detail_prompt_sets_drug_and_disease_boundaries():
    from app.services.genetic_registry import KNOWN_SNPS

    drug_prompt = genetic_report._build_snp_detail_prompt(
        KNOWN_SNPS["rs4244285"],
        {"hit": True, "genotype": "*1/*2", "result_label": "中间代谢", "risk_level": "medium"},
        {},
    )
    disease_prompt = genetic_report._build_snp_detail_prompt(
        KNOWN_SNPS["rs429358"],
        {"hit": True, "genotype": "ε3/ε4", "result_label": "风险轻度增高", "risk_level": "medium"},
        {},
    )

    assert "不得建议停药、换药或调整剂量" in drug_prompt
    assert "医生或药师确认" in drug_prompt
    assert "不是诊断" in disease_prompt
    assert "筛查级" in disease_prompt


def test_genetic_predictions_height_disease_and_education_guard(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = _profile(db, user.id)
    _variant(
        db,
        profile,
        rsid="rs9939609",
        category="disease_risk",
        gene_name="FTO",
        variant_name="肥胖倾向",
        genotype="AA",
        result_label="肥胖倾向增高",
        risk_level="high",
    )
    _variant(
        db,
        profile,
        rsid="rs7903146",
        category="disease_risk",
        gene_name="TCF7L2",
        variant_name="2型糖尿病",
        genotype="CT",
        result_label="糖尿病风险轻度增高",
        risk_level="medium",
    )

    res = client.get("/api/v1/genetic/predictions/me", headers=headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["height"]["status"] == "insufficient_model"
    assert body["height"]["marker_count"] == 0
    assert body["height"]["supported_marker_count"] >= 3
    assert "检测文件未覆盖" in body["height"]["coverage_note"]
    assert body["education"]["status"] == "unsupported"
    assert body["education"]["marker_count"] == 0
    assert body["education"]["supported_marker_count"] >= 3
    assert "检测文件未覆盖" in body["education"]["coverage_note"]
    assert "不会预测个人是否能上大学" in body["education"]["message"]
    assert body["disease_risk"]["status"] == "screening"
    assert body["disease_risk"]["top_risks"][0]["risk_level"] == "high"


def test_genetic_predictions_excludes_confirmation_only_monogenic_hits(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = _profile(db, user.id)
    _variant(
        db,
        profile,
        rsid="rs121908763",
        category="disease_risk",
        gene_name="CFTR",
        variant_name="CFTR 相关疾病筛查位点",
        genotype="GG",
        result_label="CFTR 风险等位纯合筛查阳性，需临床测序/汗氯确认",
        risk_level="high",
        evidence_level="requires_confirmation",
    )
    _variant(
        db,
        profile,
        rsid="rs380390",
        category="disease_risk",
        gene_name="AMD",
        variant_name="年龄相关黄斑变性 GWAS 位点",
        genotype="CC",
        result_label="年龄相关黄斑变性遗传关联信号显著升高",
        risk_level="high",
        evidence_level="screening",
    )

    res = client.get("/api/v1/genetic/predictions/me", headers=headers)

    assert res.status_code == 200, res.text
    genes = [item["gene"] for item in res.json()["disease_risk"]["top_risks"]]
    assert genes == ["AMD"]


def test_twin_genetic_collector_uses_active_profile_and_deduplicates(db, auth_user_and_headers):
    from app.twin._collectors import fetch_genetic_variants_categorized

    user, _headers = auth_user_and_headers
    old_profile = _profile(db, user.id, provider="old")
    active_profile = _profile(db, user.id, provider="new")
    _variant(
        db,
        old_profile,
        rsid="rs1801133",
        category="nutrition",
        gene_name="MTHFR",
        variant_name="C677T",
        genotype="CT",
        result_label="旧档案中度",
        risk_level="medium",
        variant_nature="risk",
    )
    _variant(
        db,
        active_profile,
        rsid="rs1801133",
        category="nutrition",
        gene_name="MTHFR",
        variant_name="C677T",
        genotype="TT",
        result_label="当前档案显著减弱",
        risk_level="high",
        variant_nature="risk",
    )
    _variant(
        db,
        active_profile,
        rsid="rs1801133",
        category="nutrition",
        gene_name="MTHFR",
        variant_name="C677T",
        genotype="TT",
        result_label="当前档案重复记录",
        risk_level="high",
        variant_nature="risk",
    )

    result = fetch_genetic_variants_categorized(db, user.id)

    assert result["total"] == 1
    assert result["risk"][0]["genotype"] == "TT"
    assert result["risk"][0]["result_label"] == "当前档案显著减弱"


def test_genetic_predictions_reports_exploratory_height_and_education_markers(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = _profile(db, user.id)
    _variant(
        db,
        profile,
        rsid="rs1042725",
        category="height_trait",
        gene_name="HMGA2",
        variant_name="成人身高相关位点",
        genotype="CC",
        result_label="身高增加相关等位基因 2/2",
        risk_level="info",
    )
    _variant(
        db,
        profile,
        rsid="rs143383",
        category="height_trait",
        gene_name="GDF5",
        variant_name="骨骼发育/身高相关位点",
        genotype="CT",
        result_label="身高增加相关等位基因 1/2",
        risk_level="info",
    )
    _variant(
        db,
        profile,
        rsid="rs9320913",
        category="education_trait",
        gene_name="LOC100129158",
        variant_name="教育年限相关位点",
        genotype="AA",
        result_label="教育年限相关等位基因 2/2",
        risk_level="info",
    )
    _variant(
        db,
        profile,
        rsid="rs11584700",
        category="education_trait",
        gene_name="LRRN2",
        variant_name="大学完成相关位点",
        genotype="AG",
        result_label="教育年限相关等位基因 1/2",
        risk_level="info",
    )
    _variant(
        db,
        profile,
        rsid="rs4851266",
        category="education_trait",
        gene_name="LOC150577",
        variant_name="教育年限相关位点",
        genotype="CC",
        result_label="教育年限相关等位基因 0/2",
        risk_level="info",
    )

    res = client.get("/api/v1/genetic/predictions/me", headers=headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["height"]["status"] == "exploratory_marker_score"
    assert body["height"]["marker_count"] == 2
    assert body["height"]["supported_marker_count"] >= 3
    assert body["height"]["missing_marker_count"] >= 1
    assert body["height"]["favorable_allele_count"] == 3
    assert body["education"]["status"] == "exploratory_association"
    assert body["education"]["marker_count"] == 3
    assert body["education"]["supported_marker_count"] >= 3
    assert body["education"]["missing_marker_count"] == 0
    assert body["education"]["favorable_allele_count"] == 3
    assert body["education"]["does_not_predict_college"] is True
    assert "不能判定" in body["education"]["message"]


def test_genetic_predictions_learning_recommendations_use_cognition_markers(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    profile = _profile(db, user.id)
    _variant(
        db,
        profile,
        rsid="rs6265",
        category="nutrition",
        gene_name="BDNF",
        variant_name="记忆/学习(Val66Met)",
        genotype="TT",
        result_label="记忆/学习能力偏弱",
        risk_level="medium",
    )
    _variant(
        db,
        profile,
        rsid="rs17070145",
        category="cognition",
        gene_name="KIBRA",
        variant_name="情景记忆力(WWC1)",
        genotype="TT",
        result_label="情景记忆力偏弱",
        risk_level="medium",
    )
    _variant(
        db,
        profile,
        rsid="rs1800544",
        category="cognition",
        gene_name="ADRA2A",
        variant_name="注意力/ADHD风险",
        genotype="GG",
        result_label="注意力缺陷风险增高",
        risk_level="medium",
    )

    res = client.get("/api/v1/genetic/predictions/me", headers=headers)

    assert res.status_code == 200, res.text
    learning = res.json()["learning"]
    assert learning["status"] == "actionable_markers"
    assert learning["marker_count"] == 3
    titles = [item["title"] for item in learning["recommendations"]]
    assert any("有氧运动" in title for title in titles)
    assert any("间隔复习" in title for title in titles)
    assert any("低干扰" in title for title in titles)
    assert learning["does_not_score_ability"] is True


def test_gene_config_uses_specific_gene_variants_without_overclaiming():
    from types import SimpleNamespace

    from app.twin.gene_config import build_gene_config
    from app.twin.schema import GeneticContext

    twin = SimpleNamespace(
        genetic=GeneticContext(
            has_profile=True,
            total_variants=2,
            nutrition_variants=[
                {
                    "rsid": "rs1801133",
                    "gene_name": "MTHFR",
                    "variant_name": "C677T",
                    "genotype": "TT",
                    "risk_level": "high",
                    "result_label": "叶酸代谢显著减弱",
                },
                {
                    "rsid": "rs1801394",
                    "gene_name": "MTRR",
                    "variant_name": "维B12代谢",
                    "genotype": "TT",
                    "risk_level": "medium",
                    "result_label": "B12代谢轻度减弱",
                },
            ],
        )
    )

    cfg = build_gene_config(twin)

    assert cfg.methylation == "severely_impaired"
    assert all("必须" not in line for line in cfg.summary_lines)
    assert cfg.insulin_sensitivity == "normal"
