from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument, KBEdge
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
