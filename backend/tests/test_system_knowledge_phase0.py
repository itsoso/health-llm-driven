from datetime import UTC, datetime

from app.models.agent_audit_log import AgentAuditLog
from app.models.system_knowledge import KBAudit, KBDocument, KBEdge
from app.services.system_knowledge_service import (
    apply_confidence_decay,
    build_evidence_card_for_message,
)


def _seed_phase0_knowledge(db):
    entity = KBDocument(
        doc_id="entity:gene:MTHFR",
        doc_type="entity",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR",
        summary="MTHFR 参与一碳代谢和叶酸转化。",
        body="MTHFR C677T 会影响叶酸向 5-MTHF 的转化效率。",
        confidence=0.88,
        evidence_level="B",
        sources=["dedao:qiuzilong-genetics-07"],
        last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        decay_rate="slow",
    )
    claim = KBDocument(
        doc_id="claim:c_mthfr_c677t_hcy_folate_boundary",
        doc_type="claim",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR C677T 与叶酸转化边界",
        summary="C677T CT/TT 用户可优先关注同型半胱氨酸、B12 与活性叶酸。",
        body="该 claim 只支持健康管理提示，不用于诊断或治疗。",
        confidence=0.82,
        evidence_level="B",
        applies_when=[
            "twin.genetics.MTHFR_C677T in ['CT', 'TT']",
            "twin.labs.homocysteine_umol_l >= 15",
        ],
        recommends_lookup=["entity:supplement:5-MTHF", "entity:biomarker:Hcy"],
        sources=["dedao:qiuzilong-genetics-07", "pubmed:19033271"],
        last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        decay_rate="normal",
    )
    db.add_all([entity, claim])
    db.flush()
    db.add(
        KBEdge(
            src_doc_id=entity.doc_id,
            dst_doc_id=claim.doc_id,
            relation="has_claim",
            confidence=0.9,
            source_claim_id=claim.doc_id,
        )
    )
    db.commit()


def test_get_entity_returns_entity_page_and_linked_claims(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)

    response = client.get("/api/v1/knowledge/entity/gene/MTHFR", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity"]["doc_id"] == "entity:gene:MTHFR"
    assert payload["entity"]["entity_id"] == "MTHFR"
    assert payload["linked_claims"][0]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"
    assert payload["linked_claims"][0]["evidence_level"] == "B"
    assert payload["linked_claims"][0]["sources"] == [
        "dedao:qiuzilong-genetics-07",
        "pubmed:19033271",
    ]
    assert payload["claim_boundary"] == "仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。"


def test_lookup_for_twin_returns_structured_matches(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)

    response = client.post(
        "/api/v1/knowledge/lookup_for_twin",
        headers=headers,
        json={
            "genetics": {"MTHFR_C677T": "TT"},
            "labs": {"homocysteine_umol_l": 18},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [entity["doc_id"] for entity in payload["entities"]] == ["entity:gene:MTHFR"]
    assert [claim["doc_id"] for claim in payload["claims"]] == [
        "claim:c_mthfr_c677t_hcy_folate_boundary"
    ]
    assert payload["claims"][0]["matched_conditions"] == [
        "twin.genetics.MTHFR_C677T in ['CT', 'TT']",
        "twin.labs.homocysteine_umol_l >= 15",
    ]


def test_lookup_for_twin_excludes_archived_or_non_matching_claims(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    db.add(
        KBDocument(
            doc_id="claim:c_mthfr_archived",
            doc_type="claim",
            entity_type="gene",
            entity_id="MTHFR",
            title="Archived claim",
            confidence=0.9,
            evidence_level="B",
            applies_when=["twin.genetics.MTHFR_C677T == 'TT'"],
            is_archived=True,
        )
    )
    db.commit()

    response = client.post(
        "/api/v1/knowledge/lookup_for_twin",
        headers=headers,
        json={
            "genetics": {"MTHFR_C677T": "CC"},
            "labs": {"homocysteine_umol_l": 8},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["claims"] == []


def test_build_evidence_card_for_message_detects_mthfr_tt_question(db):
    _seed_phase0_knowledge(db)

    card = build_evidence_card_for_message(db, "我 MTHFR-TT 该注意什么？")

    assert card is not None
    assert card["type"] == "system_knowledge_evidence"
    assert card["data"]["entity"]["doc_id"] == "entity:gene:MTHFR"
    assert card["data"]["claims"][0]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"


def test_get_claim_returns_claim_detail_with_neighbors(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)

    response = client.get(
        "/api/v1/knowledge/claim/claim:c_mthfr_c677t_hcy_folate_boundary",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["claim"]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"
    assert payload["claim"]["entity_id"] == "MTHFR"
    assert payload["neighbors"][0]["doc_id"] == "entity:gene:MTHFR"
    assert payload["claim_boundary"] == "仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。"


def test_claim_feedback_disagree_writes_audit_log(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)

    response = client.post(
        "/api/v1/knowledge/claim/claim:c_mthfr_c677t_hcy_folate_boundary/feedback",
        headers=headers,
        json={"feedback": "disagree", "reason": "这条建议和医生意见不一致"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True

    from app.models.system_knowledge import KBAudit

    audit = db.query(KBAudit).filter(KBAudit.op == "feedback_disagree").one()
    assert audit.doc_id == "claim:c_mthfr_c677t_hcy_folate_boundary"
    assert audit.actor == f"user:{user.id}"
    assert audit.diff["reason"] == "这条建议和医生意见不一致"


def test_search_knowledge_returns_lexical_and_graph_context(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)

    response = client.get(
        "/api/v1/knowledge/search",
        headers=headers,
        params={"q": "叶酸 MTHFR", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    result_ids = [item["document"]["doc_id"] for item in payload["results"]]
    assert "entity:gene:MTHFR" in result_ids
    assert "claim:c_mthfr_c677t_hcy_folate_boundary" in result_ids
    assert payload["graph_context"]["edges"][0]["relation"] == "has_claim"


def test_admin_lint_report_flags_orphans_and_invalid_conditions(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    _seed_phase0_knowledge(db)
    db.add(
        KBDocument(
            doc_id="claim:c_invalid_condition",
            doc_type="claim",
            entity_type="gene",
            entity_id="MTHFR",
            title="Invalid condition",
            confidence=0.4,
            evidence_level="C",
            applies_when=["twin.genetics.MTHFR_C677T ~= 'TT'"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        )
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/lint_report", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["orphan_claims"] == 1
    assert payload["summary"]["invalid_conditions"] == 1
    assert payload["issues"]["invalid_conditions"][0]["doc_id"] == "claim:c_invalid_condition"


def test_admin_lint_report_flags_contradictions_and_invalid_review_status(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_fiber_supports_tg",
                doc_type="claim",
                entity_type="nutrient",
                entity_id="fiber",
                title="膳食纤维支持甘油三酯管理",
                summary="增加膳食纤维有助于代谢健康管理。",
                confidence=0.72,
                evidence_level="B",
                applies_when=["twin.labs.triglycerides_mmol_l >= 1.7"],
                sources=["dedao:nutrition"],
                last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
                metadata_json={
                    "claim_key": "fiber_tg_management",
                    "stance": "supports",
                    "review_status": "reviewed",
                },
            ),
            KBDocument(
                doc_id="claim:c_fiber_opposes_tg",
                doc_type="claim",
                entity_type="nutrient",
                entity_id="fiber",
                title="膳食纤维不应用于甘油三酯管理",
                summary="膳食纤维不适合用于甘油三酯管理。",
                confidence=0.61,
                evidence_level="C",
                applies_when=["twin.labs.triglycerides_mmol_l >= 1.7"],
                sources=["dedao:nutrition-old"],
                last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
                metadata_json={
                    "claim_key": "fiber_tg_management",
                    "stance": "opposes",
                    "review_status": "reviewed",
                },
            ),
            KBDocument(
                doc_id="claim:c_bad_review_status",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Bad review status",
                confidence=0.5,
                evidence_level="C",
                applies_when=["twin.goals.weight_loss.active == true"],
                metadata_json={"review_status": "maybe"},
            ),
        ]
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/lint_report", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["contradictions"] == 1
    assert payload["issues"]["contradictions"][0]["claim_key"] == "fiber_tg_management"
    assert set(payload["issues"]["contradictions"][0]["doc_ids"]) == {
        "claim:c_fiber_supports_tg",
        "claim:c_fiber_opposes_tg",
    }
    assert payload["summary"]["invalid_review_status"] == 1
    assert payload["issues"]["invalid_review_status"][0]["doc_id"] == "claim:c_bad_review_status"


def test_admin_coverage_report_counts_evidence_refs_unsupported_and_feedback(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_reviewed",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Reviewed claim",
                confidence=0.7,
                evidence_level="B",
                metadata_json={"review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="claim:c_draft",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Draft claim",
                confidence=0.5,
                evidence_level="C",
                metadata_json={"review_status": "draft"},
            ),
            AgentAuditLog(
                user_id=user.id,
                agent_type="specialist_batch",
                action="run",
                findings_count=3,
                result_detail={
                    "findings": [
                        {
                            "summary": "supported",
                            "evidence_refs": ["claim:c_reviewed"],
                            "unsupported": False,
                        },
                        {
                            "summary": "unsupported flag",
                            "evidence_refs": [],
                            "unsupported": True,
                        },
                        {
                            "summary": "missing refs",
                            "data": {"unsupported": True},
                        },
                    ]
                },
            ),
            KBAudit(
                doc_id="claim:c_reviewed",
                op="feedback_disagree",
                actor=f"user:{user.id}",
                diff={"reason": "不适用"},
            ),
        ]
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/coverage_report", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"]["total"] == 2
    assert payload["documents"]["by_review_status"]["reviewed"] == 1
    assert payload["documents"]["by_review_status"]["draft"] == 1
    assert payload["specialist_findings"]["total"] == 3
    assert payload["specialist_findings"]["with_evidence_refs"] == 1
    assert payload["specialist_findings"]["unsupported"] == 2
    assert payload["specialist_findings"]["evidence_ref_rate"] == 0.3333
    assert payload["specialist_findings"]["target_evidence_ref_rate"] == 0.85
    assert payload["specialist_findings"]["meets_target"] is False
    assert payload["feedback"]["disagree"] == 1


def test_admin_reindex_refreshes_search_text_and_content_hash(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    _seed_phase0_knowledge(db)

    response = client.post("/api/v1/admin/knowledge/reindex", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"] == 2
    refreshed = db.get(KBDocument, "entity:gene:MTHFR")
    assert refreshed.tsv is not None
    assert "MTHFR" in refreshed.tsv
    assert refreshed.content_hash is not None


def test_apply_confidence_decay_reduces_stale_fast_claims(db):
    stale_time = datetime(2026, 1, 1, tzinfo=UTC)
    db.add(
        KBDocument(
            doc_id="claim:c_fast_stale",
            doc_type="claim",
            title="Fast stale claim",
            confidence=0.8,
            evidence_level="C",
            last_confirmed=stale_time,
            decay_rate="fast",
        )
    )
    db.commit()

    result = apply_confidence_decay(
        db,
        now=datetime(2026, 5, 16, tzinfo=UTC),
        actor="test",
    )

    assert result["updated"] == 1
    refreshed = db.get(KBDocument, "claim:c_fast_stale")
    assert refreshed.confidence == 0.72
    assert db.query(KBDocument).filter(KBDocument.doc_id == "claim:c_fast_stale").count() == 1
