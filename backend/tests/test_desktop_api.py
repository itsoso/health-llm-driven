from datetime import date, timedelta


def test_desktop_bootstrap_requires_auth(client):
    resp = client.get("/api/v1/desktop/bootstrap")

    assert resp.status_code in {401, 403}


def test_desktop_bootstrap_returns_current_user_operating_context(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard
    from app.models.blood_pressure import BloodPressureRecord
    from app.models.daily_health import DietRecord, WaterIntake
    from app.models.genetic_data import GeneticProfile, GeneticVariant
    from app.models.memory_fact import MemoryFact
    from app.models.supplement import SupplementDefinition, SupplementRecord
    from app.models.system_knowledge import KBDocument, KBEdge
    from app.models.user import User
    from app.models.user_profile import UserProfile
    from app.models.weight import WeightRecord

    other = User(
        username="desktop_other",
        email="desktop_other@example.com",
        hashed_password="x",
        name="Other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    db.add(UserProfile(user_id=user.id, llm_model_id="claude-opus-4.7"))
    db.add(ActionCard(
        user_id=user.id,
        title="晚饭后散步",
        content="晚饭后走 20 分钟。",
        status="active",
        is_visible=True,
        priority=5,
    ))
    db.add(ActionCard(
        user_id=other.id,
        title="其他用户卡片",
        content="不应出现",
        status="active",
        is_visible=True,
        priority=99,
    ))
    db.add(MemoryFact(
        user_id=user.id,
        tier="semantic",
        subject="用户",
        predicate="prefers",
        object_value="晚上训练",
        confidence=0.8,
        tags=["desktop"],
    ))
    db.add(DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="breakfast",
        food_items="鸡蛋",
        calories=120,
    ))
    db.add(WaterIntake(
        user_id=user.id,
        record_date=date.today(),
        amount_ml=500,
        drink_type="water",
    ))
    db.add(DietRecord(
        user_id=user.id,
        record_date=date.today() - timedelta(days=6),
        meal_type="dinner",
        food_items="鸡胸肉",
        calories=430,
    ))
    db.add(WaterIntake(
        user_id=user.id,
        record_date=date.today() - timedelta(days=6),
        amount_ml=800,
        drink_type="water",
    ))
    db.add(DietRecord(
        user_id=user.id,
        record_date=date.today() - timedelta(days=29),
        meal_type="dinner",
        food_items="牛肉面",
        calories=650,
    ))
    db.add(WaterIntake(
        user_id=user.id,
        record_date=date.today() - timedelta(days=29),
        amount_ml=700,
        drink_type="water",
    ))
    db.add(WeightRecord(
        user_id=user.id,
        record_date=date(2026, 5, 2),
        weight=70.2,
        source="manual",
    ))
    db.add(BloodPressureRecord(
        user_id=user.id,
        record_date=date(2026, 5, 3),
        systolic=118,
        diastolic=76,
    ))
    profile = GeneticProfile(
        user_id=user.id,
        test_provider="wegene",
        test_date=date(2026, 5, 15),
        report_id="wg-20260515",
    )
    older_profile = GeneticProfile(
        user_id=user.id,
        test_provider="wegene",
        test_date=date(2026, 4, 10),
        report_id="wg-20260410",
    )
    other_profile = GeneticProfile(
        user_id=other.id,
        test_provider="wegene",
        test_date=date(2026, 5, 15),
        report_id="other",
    )
    db.add_all([profile, older_profile, other_profile])
    db.commit()
    db.refresh(profile)
    db.refresh(older_profile)
    db.refresh(other_profile)
    db.add_all([
        GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            rsid="rs1061235",
            category="drug_sensitivity",
            gene_name="HLA-A*31:01",
            variant_name="卡马西平皮肤不良反应",
            genotype="AA",
            result_label="positive",
            risk_level="high",
            evidence_level="screening",
            description="提示用药前需要医生确认的筛查信号。",
        ),
        GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            rsid="rs380390",
            category="disease_risk",
            gene_name="CFH",
            variant_name="年龄相关黄斑变性",
            genotype="CC",
            result_label="风险升高",
            risk_level="medium",
            evidence_level="B",
            description="用于风险分层，不构成诊断。",
        ),
        GeneticVariant(
            user_id=user.id,
            profile_id=older_profile.id,
            rsid="rs1801133",
            category="nutrition",
            gene_name="MTHFR",
            variant_name="叶酸代谢",
            genotype="TT",
            result_label="风险升高",
            risk_level="medium",
            evidence_level="B",
            description="用于同型半胱氨酸复查闭环。",
        ),
        GeneticVariant(
            user_id=other.id,
            profile_id=other_profile.id,
            rsid="rs999",
            category="disease_risk",
            gene_name="OTHER",
            genotype="AA",
            result_label="不应出现",
            risk_level="high",
        ),
    ])
    from app.models.genetic_data import GeneticImportJob
    db.add(GeneticImportJob(
        user_id=user.id,
        profile_id=profile.id,
        source_type="txt",
        provider="wegene",
        status="done",
        raw_record_count=18191,
        known_total=1200,
        matched_count=2,
        duplicate_count=3,
        unknown_count=11,
        unmapped_count=18176,
        missing_count=1198,
        coverage_summary={"panel": "desktop-test"},
    ))
    db.add_all([
        KBDocument(
            doc_id="claim:c_mthfr_c677t_hcy_folate_boundary",
            doc_type="claim",
            entity_type="gene",
            entity_id="MTHFR",
            title="MTHFR 叶酸边界",
            summary="Hcy 和叶酸/B12 用于复查闭环。",
            body="基因仅用于风险分层。",
            confidence=0.82,
            evidence_level="B",
            sources=["dedao:qiuzilong-genetics-07", "pubmed:123"],
            metadata_json={
                "origin": "down-dedao-llm-wiki",
                "review_status": "reviewed",
            },
            is_archived=False,
        ),
        KBDocument(
            doc_id="entity:gene:MTHFR",
            doc_type="entity",
            entity_type="gene",
            entity_id="MTHFR",
            title="MTHFR",
            sources=["dedao:qiuzilong-genetics-07"],
            metadata_json={
                "origin": "down-dedao-llm-wiki",
                "review_status": "reviewed",
            },
            is_archived=False,
        ),
        KBDocument(
            doc_id="article:dedao:folate",
            doc_type="article",
            title="叶酸代谢课程",
            sources=["dedao:qiuzilong-genetics-07"],
            metadata_json={
                "origin": "down-dedao-llm-wiki",
                "review_status": "reviewed",
            },
            is_archived=False,
        ),
        KBDocument(
            doc_id="claim:c_low_back_emergency_neurologic_red_flags",
            doc_type="claim",
            title="runtime-only low-back claim must stay hidden",
            summary="runtime-only low-back summary must stay hidden",
            sources=["nhs:back-pain-2026"],
            metadata_json={"review_status": "reviewed"},
            is_archived=False,
        ),
        KBDocument(
            doc_id="article:draft:must-not-serve",
            doc_type="article",
            title="unreviewed draft must stay hidden",
            summary="unreviewed draft must stay hidden",
            sources=["internal:draft"],
            metadata_json={
                "origin": "down-dedao-llm-wiki",
                "review_status": "draft",
            },
            is_archived=False,
        ),
    ])
    db.add(KBEdge(
        src_doc_id="entity:gene:MTHFR",
        dst_doc_id="claim:c_mthfr_c677t_hcy_folate_boundary",
        relation="has_claim",
        confidence=0.8,
        source_claim_id="claim:c_mthfr_c677t_hcy_folate_boundary",
    ))
    db.add(KBEdge(
        src_doc_id="entity:gene:MTHFR",
        dst_doc_id="claim:c_low_back_emergency_neurologic_red_flags",
        relation="must_not_leak",
        confidence=1.0,
        source_claim_id="claim:c_low_back_emergency_neurologic_red_flags",
    ))
    db.commit()
    supplement = SupplementDefinition(
        user_id=user.id,
        name="鱼油",
        dosage="1100mg",
        timing="morning",
        is_active=True,
    )
    db.add(supplement)
    db.commit()
    db.refresh(supplement)
    db.add(SupplementRecord(
        user_id=user.id,
        supplement_id=supplement.id,
        record_date=date.today(),
        taken=True,
    ))
    db.add(SupplementRecord(
        user_id=user.id,
        supplement_id=supplement.id,
        record_date=date.today() - timedelta(days=6),
        taken=True,
    ))
    db.commit()

    resp = client.get("/api/v1/desktop/bootstrap", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == user.id
    assert body["model_preference"]["llm_model_id"] == "claude-opus-4.7"
    assert body["daily_plan"]["plan_date"] == date.today().isoformat()
    assert "trajectory" in body
    assert [card["title"] for card in body["action_cards"]] == ["晚饭后散步"]
    assert body["recent_memory"][0]["object_value"] == "晚上训练"
    assert body["recent_records_summary"]["diet"]["today_count"] == 1
    assert body["recent_records_summary"]["diet"]["today_calories"] == 120
    assert body["recent_records_summary"]["diet"]["last_7_count"] == 2
    assert body["recent_records_summary"]["diet"]["last_7_calories"] == 550
    assert body["recent_records_summary"]["diet"]["last_7_avg_calories"] == 78.6
    assert body["recent_records_summary"]["diet"]["last_30_count"] == 3
    assert body["recent_records_summary"]["diet"]["last_30_calories"] == 1200
    assert len(body["recent_records_summary"]["diet"]["daily_7"]) == 7
    assert body["recent_records_summary"]["water"]["today_total_ml"] == 500
    assert body["recent_records_summary"]["water"]["last_7_total_ml"] == 1300
    assert body["recent_records_summary"]["water"]["last_7_avg_ml"] == 185.7
    assert body["recent_records_summary"]["water"]["last_30_total_ml"] == 2000
    assert len(body["recent_records_summary"]["water"]["daily_7"]) == 7
    assert body["recent_records_summary"]["supplements"]["active_count"] == 1
    assert body["recent_records_summary"]["supplements"]["last_7_count"] == 2
    assert body["recent_records_summary"]["supplements"]["last_7_avg_per_day"] == 0.3
    assert body["recent_records_summary"]["supplements"]["adherence_7_pct"] == 28.6
    assert body["recent_records_summary"]["supplements"]["top_items"] == [{"name": "鱼油", "count": 2}]
    assert body["recent_records_summary"]["latest_weight"]["value"] == 70.2
    assert body["recent_records_summary"]["latest_blood_pressure"]["value"] == "118/76"
    assert body["genomic_summary"]["record_count"] == 2
    assert body["genomic_summary"]["profile_count"] == 2
    assert body["genomic_summary"]["total_variant_count"] == 3
    assert body["genomic_summary"]["high_risk_count"] == 1
    assert body["genomic_summary"]["medium_risk_count"] == 1
    assert body["genomic_summary"]["provider"] == "wegene"
    assert body["genomic_summary"]["top_findings"][0]["gene_name"] == "HLA-A*31:01"
    assert body["genomic_summary"]["top_findings"][0]["genotype"] == "AA"
    assert body["genomic_summary"]["top_findings"][0]["clinical_status"] == "pharmacogenomic_screening"
    assert body["genomic_summary"]["top_categories"][0]["category"] == "disease_risk"
    assert body["genomic_summary"]["profile_summaries"][0]["profile_id"] == profile.id
    assert body["genomic_summary"]["profile_summaries"][0]["is_active"] is True
    assert body["genomic_summary"]["profile_summaries"][0]["record_count"] == 2
    assert body["genomic_summary"]["profile_summaries"][1]["profile_id"] == older_profile.id
    assert body["genomic_summary"]["latest_import"]["unmapped_count"] == 18176
    assert body["genomic_summary"]["latest_import"]["missing_count"] == 1198
    assert body["genomic_summary"]["latest_import"]["coverage_pct"] == 0.2
    assert body["knowledge_summary"]["document_count"] == 3
    assert body["knowledge_summary"]["claim_count"] == 1
    assert body["knowledge_summary"]["entity_count"] == 1
    assert body["knowledge_summary"]["article_count"] == 1
    assert body["knowledge_summary"]["edge_count"] == 1
    assert body["knowledge_summary"]["doc_type_counts"] == [
        {"level": "article", "count": 1},
        {"level": "claim", "count": 1},
        {"level": "entity", "count": 1},
    ]
    assert body["knowledge_summary"]["entity_type_counts"] == [{"level": "gene", "count": 2}]
    assert body["knowledge_summary"]["source_total_count"] == 2
    assert body["knowledge_summary"]["source_counts"][0] == {"source": "dedao:qiuzilong-genetics-07", "count": 3}
    assert body["knowledge_summary"]["local_source_summary"]["linked_document_count"] == 3
    assert body["knowledge_summary"]["local_source_summary"]["origin_counts"] == [
        {"origin": "down-dedao-llm-wiki", "count": 3}
    ]
    assert body["knowledge_summary"]["local_source_summary"]["bridge_manifest"]["pipeline"] == "down_dedao_llm_wiki_bridge_v1"
    assert body["knowledge_summary"]["recent_documents"][0]["doc_id"] == "article:dedao:folate"
    assert "runtime-only low-back" not in str(body["knowledge_summary"])
    assert "unreviewed draft" not in str(body["knowledge_summary"])
    recent_types = [record["type"] for record in body["recent_records_summary"]["recent_records"]]
    assert "blood_pressure" in recent_types
    assert "weight" in recent_types
    assert body["active_jobs"] == []


def test_desktop_bootstrap_handles_empty_user_without_500(client, auth_user_and_headers):
    user, headers = auth_user_and_headers

    resp = client.get("/api/v1/desktop/bootstrap", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == user.id
    assert body["action_cards"] == []
    assert body["recent_memory"] == []
    assert body["active_jobs"] == []
