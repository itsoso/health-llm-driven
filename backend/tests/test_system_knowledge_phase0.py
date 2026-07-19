from datetime import UTC, datetime
import json

from sqlalchemy.dialects import postgresql

from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.models.notification import NotificationLog
from app.models.system_knowledge import KBAudit, KBDocument, KBEdge
from app.services.kbase_review_workspace import workspace_content_fingerprint
from app.services.system_knowledge_service import (
    _build_postgres_reindex_statement,
    apply_confidence_decay,
    attach_system_knowledge_evidence,
    build_evidence_card_for_message,
)
from app.orchestrator.schema import SpecialistFinding


def _write_artifact_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _artifact_counts(artifact_dir):
    names = ("pages", "entities", "claims", "protocols", "contraindications", "eval_cases", "relations")
    return {
        name: len([line for line in (artifact_dir / f"{name}.jsonl").read_text().splitlines() if line.strip()])
        for name in names
    }


def _write_dedao_review_workspace(artifact_dir):
    artifact_dir.mkdir()
    _write_artifact_jsonl(
        artifact_dir / "pages.jsonl",
        [
            {
                "doc_id": "page:release-abc",
                "doc_type": "article",
                "title": "睡眠与咖啡因",
                "summary": "结构化来源摘要",
                "metadata": {"review_status": "draft", "release_id": "release-abc"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "entities.jsonl",
        [
            {
                "doc_id": "entity:knowledge_source:sleep",
                "doc_type": "entity",
                "title": "睡眠与咖啡因",
                "metadata": {"review_status": "draft", "release_id": "release-abc"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "claims.jsonl",
        [
            {
                "doc_id": "claim:release-abc-claim-1",
                "doc_type": "claim",
                "title": "晚间咖啡因可能延长睡眠潜伏期",
                "summary": "晚间咖啡因可能延长睡眠潜伏期。",
                "body": "不应写入审计的 claim 正文",
                "evidence_level": "C",
                "confidence": 0.68,
                "sources": ["citation-1"],
                "metadata": {
                    "review_status": "draft",
                    "release_id": "release-abc",
                    "release_claim_id": "claim-1",
                    "usage_policy": "evidence_only",
                    "citation_ids": ["citation-1"],
                },
            }
        ],
    )
    for name in ("protocols", "contraindications", "eval_cases"):
        _write_artifact_jsonl(artifact_dir / f"{name}.jsonl", [])
    _write_artifact_jsonl(
        artifact_dir / "relations.jsonl",
        [
            {
                "src_doc_id": "entity:knowledge_source:sleep",
                "dst_doc_id": "claim:release-abc-claim-1",
                "relation": "has_claim",
                "metadata": {"review_status": "draft", "release_id": "release-abc"},
            }
        ],
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {"ingest": {"review_status": "draft"}, "counts": _artifact_counts(artifact_dir)},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "draft_manifest.json").write_text(
        json.dumps({"status": "draft", "requires_review": True, "serving_allowed": False}) + "\n",
        encoding="utf-8",
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
        metadata_json={"review_status": "reviewed"},
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
        metadata_json={"review_status": "reviewed", "domain": "nutrition"},
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


def test_get_entity_deduplicates_semantically_identical_claims(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    duplicate = KBDocument(
        doc_id="claim:c_mthfr_duplicate_from_other_course",
        doc_type="claim",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR C677T 与叶酸转化边界",
        summary="C677T CT/TT 用户可优先关注同型半胱氨酸、B12 与活性叶酸。",
        body="同一语义 claim 的低等级来源副本。",
        confidence=0.61,
        evidence_level="C",
        sources=["dedao:duplicate-course"],
        last_confirmed=datetime(2026, 5, 15, tzinfo=UTC),
        decay_rate="normal",
        metadata_json={"review_status": "reviewed"},
    )
    db.add(duplicate)
    db.flush()
    db.add(
        KBEdge(
            src_doc_id="entity:gene:MTHFR",
            dst_doc_id=duplicate.doc_id,
            relation="has_claim",
            confidence=0.7,
            source_claim_id=duplicate.doc_id,
        )
    )
    db.commit()

    response = client.get("/api/v1/knowledge/entity/gene/MTHFR", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    matching = [
        claim
        for claim in payload["linked_claims"]
        if claim["title"] == "MTHFR C677T 与叶酸转化边界"
    ]
    assert [claim["doc_id"] for claim in matching] == [
        "claim:c_mthfr_c677t_hcy_folate_boundary"
    ]


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


def test_lookup_for_twin_excludes_non_reviewed_claims(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_mthfr_draft_should_not_serve",
                doc_type="claim",
                entity_type="gene",
                entity_id="MTHFR",
                title="Draft MTHFR claim",
                summary="草稿 claim 即使命中条件也不能进入用户可见 lookup。",
                confidence=0.99,
                evidence_level="B",
                applies_when=[
                    "twin.genetics.MTHFR_C677T in ['CT', 'TT']",
                    "twin.labs.homocysteine_umol_l >= 15",
                ],
                metadata_json={"review_status": "draft", "domain": "nutrition"},
            ),
            KBDocument(
                doc_id="claim:c_mthfr_missing_review_should_not_serve",
                doc_type="claim",
                entity_type="gene",
                entity_id="MTHFR",
                title="Missing review MTHFR claim",
                summary="缺少 review_status 的 claim 必须 fail closed。",
                confidence=0.98,
                evidence_level="B",
                applies_when=[
                    "twin.genetics.MTHFR_C677T in ['CT', 'TT']",
                    "twin.labs.homocysteine_umol_l >= 15",
                ],
                metadata_json={"domain": "nutrition"},
            ),
        ]
    )
    db.commit()

    response = client.post(
        "/api/v1/knowledge/lookup_for_twin",
        headers=headers,
        json={
            "genetics": {"MTHFR_C677T": "TT"},
            "labs": {"homocysteine_umol_l": 18},
        },
    )

    assert response.status_code == 200
    claim_ids = [claim["doc_id"] for claim in response.json()["claims"]]
    assert claim_ids == ["claim:c_mthfr_c677t_hcy_folate_boundary"]


def test_get_claim_excludes_non_reviewed_claim(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    db.add(
        KBDocument(
            doc_id="claim:c_draft_claim_detail",
            doc_type="claim",
            title="Draft claim detail",
            summary="草稿详情不能直接打开。",
            confidence=0.8,
            evidence_level="C",
            metadata_json={"review_status": "draft"},
        )
    )
    db.commit()

    response = client.get("/api/v1/knowledge/claim/claim:c_draft_claim_detail", headers=headers)

    assert response.status_code == 404


def test_evidence_resolver_does_not_attach_non_reviewed_claim_refs(db):
    db.add(
        KBDocument(
            doc_id="claim:c_protein_draft_should_not_support",
            doc_type="claim",
            entity_type="intervention",
            entity_id="protein",
            title="Protein draft claim",
            summary="蛋白质建议草稿命中 Twin 后也不能成为 evidence_refs。",
            confidence=0.9,
            evidence_level="B",
            applies_when=["twin.goals.weight_loss.active == true"],
            sources=["system:test"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            metadata_json={"review_status": "draft", "domain": "nutrition"},
        )
    )
    db.commit()
    finding = SpecialistFinding(
        specialist_name="fuel_strategist",
        category="nutrition",
        summary="减重期蛋白质建议",
        findings=[{"title": "补足蛋白质", "action": "下一餐增加优质蛋白质"}],
    )

    attach_system_knowledge_evidence(
        db,
        {"goals": {"weight_loss": {"active": True}}},
        [finding],
    )

    assert finding.evidence_refs == []
    assert finding.raw["evidence_resolution"]["support_status"] == "model_inference"
    assert finding.raw["unsupported"] is True


def test_build_evidence_card_for_message_detects_mthfr_tt_question(db):
    _seed_phase0_knowledge(db)

    card = build_evidence_card_for_message(db, "我 MTHFR-TT 该注意什么？")

    assert card is not None
    assert card["type"] == "system_knowledge_evidence"
    assert card["data"]["entity"]["doc_id"] == "entity:gene:MTHFR"
    assert card["data"]["claims"][0]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"


def test_build_evidence_card_for_message_detects_9p21_aa_question(db):
    entity = KBDocument(
        doc_id="entity:gene:9p21",
        doc_type="entity",
        entity_type="gene",
        entity_id="9p21",
        title="9p21",
        summary="9p21 区域用于心血管风险沟通，必须结合血脂、血压、炎症和生活方式指标。",
        body="9p21 不是补剂处方锚点。",
        confidence=0.72,
        evidence_level="C",
        sources=["dedao:qiuzilong-genetics-20"],
        last_confirmed=datetime(2026, 5, 17, tzinfo=UTC),
        decay_rate="normal",
        metadata_json={"review_status": "reviewed"},
    )
    claim = KBDocument(
        doc_id="claim:c_9p21_cardiovascular_labs_lifestyle_boundary",
        doc_type="claim",
        entity_type="gene",
        entity_id="9p21",
        title="9p21 AA 解读必须锚定心血管临床指标",
        summary="9p21 AA 只能作为冠心病/动脉粥样硬化风险沟通线索；补剂建议必须先看 LDL-C、ApoB、血压、血糖、炎症、肝肾功能和运动恢复数据。",
        body="不应仅凭 9p21 AA 给出确定补剂方案。",
        confidence=0.68,
        evidence_level="C",
        applies_when=["twin.genetics.9p21 in ['AA', 'AG']", "twin.genetics.rs10757274 in ['AA', 'AG']"],
        recommends_lookup=["entity:gene:9p21", "entity:biomarker:LDL-C", "entity:biomarker:BP"],
        sources=["dedao:qiuzilong-genetics-20"],
        last_confirmed=datetime(2026, 5, 17, tzinfo=UTC),
        decay_rate="normal",
        metadata_json={"review_status": "reviewed"},
    )
    db.add_all([entity, claim])
    db.flush()
    db.add(KBEdge(src_doc_id=entity.doc_id, dst_doc_id=claim.doc_id, relation="has_claim", confidence=0.88))
    db.commit()

    card = build_evidence_card_for_message(db, "针对我的 9p21 基因 AA，补剂方面怎么做？")

    assert card is not None
    assert card["data"]["entity"]["doc_id"] == "entity:gene:9p21"
    assert card["data"]["claims"][0]["doc_id"] == "claim:c_9p21_cardiovascular_labs_lifestyle_boundary"


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


def test_get_claim_includes_evidence_and_source_details(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)

    response = client.get(
        "/api/v1/knowledge/claim/claim:c_mthfr_c677t_hcy_folate_boundary",
        headers=headers,
    )

    assert response.status_code == 200
    claim = response.json()["claim"]
    assert claim["evidence_level_detail"]["level"] == "B"
    assert claim["evidence_level_detail"]["label"] == "B级"
    assert "中等" in claim["evidence_level_detail"]["description"]

    source_labels = {source["label"] for source in claim["source_details"]}
    assert {"得到课程", "PubMed"} <= source_labels
    dedao_source = next(
        source for source in claim["source_details"] if source["source"] == "dedao:qiuzilong-genetics-07"
    )
    assert dedao_source["kind"] == "course"
    assert dedao_source["trust_tier"] == "expert_course"

    groups = {group["kind"]: group for group in claim["source_groups"]}
    assert groups["course"]["count"] == 1
    assert groups["research"]["count"] == 1


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
    assert {"lexical", "fts"} <= set(payload["retrieval_plan"]["channels"])
    assert payload["retrieval_plan"]["lexical_backend"] == "python_bm25_v1"
    assert payload["retrieval_plan"]["fts_backend"] == "sqlite_precomputed_text"
    assert payload["retrieval_plan"]["vector_backend"] == "sparse_term_cosine_v1"
    assert payload["retrieval_plan"]["rrf_backend"] == "python_rrf_v1"
    assert {"lexical", "fts"} <= set(payload["results"][0]["retrieval"]["channels"])
    assert payload["results"][0]["retrieval"]["lexical_score"] > 0


def test_search_knowledge_promotes_graph_neighbors_into_results(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    db.add(
        KBDocument(
            doc_id="claim:c_active_folate_dose_boundary",
            doc_type="claim",
            title="活性叶酸补充剂量边界",
            summary="从低剂量开始，并结合 B12 与同型半胱氨酸复查。",
            confidence=0.74,
            evidence_level="C",
            sources=["dedao:qiuzilong-genetics-07"],
            last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
            metadata_json={"review_status": "reviewed"},
        )
    )
    db.flush()
    db.add(
        KBEdge(
            src_doc_id="entity:gene:MTHFR",
            dst_doc_id="claim:c_active_folate_dose_boundary",
            relation="recommends",
            confidence=0.8,
            source_claim_id="claim:c_mthfr_c677t_hcy_folate_boundary",
        )
    )
    db.commit()

    response = client.get(
        "/api/v1/knowledge/search",
        headers=headers,
        params={"q": "MTHFR", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    graph_result = next(
        item
        for item in payload["results"]
        if item["document"]["doc_id"] == "claim:c_active_folate_dose_boundary"
    )
    assert "graph" in graph_result["retrieval"]["channels"]
    assert graph_result["retrieval"]["graph_distance"] == 1


def test_search_knowledge_excludes_non_reviewed_documents_and_graph_context(
    client, db, auth_user_and_headers
):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    db.add(
        KBDocument(
            doc_id="claim:c_unreviewed_graph_neighbor",
            doc_type="claim",
            title="Unreviewed Graph Neighbor",
            summary="MTHFR 草稿邻居不应出现在搜索结果或 graph_context。",
            confidence=0.95,
            evidence_level="B",
            metadata_json={"review_status": "draft"},
        )
    )
    db.flush()
    db.add(
        KBEdge(
            src_doc_id="entity:gene:MTHFR",
            dst_doc_id="claim:c_unreviewed_graph_neighbor",
            relation="has_claim",
            confidence=0.8,
            source_claim_id="claim:c_unreviewed_graph_neighbor",
        )
    )
    db.commit()

    response = client.get(
        "/api/v1/knowledge/search",
        headers=headers,
        params={"q": "MTHFR", "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    result_ids = {item["document"]["doc_id"] for item in payload["results"]}
    neighbor_ids = {item["doc_id"] for item in payload["graph_context"]["neighbors"]}
    edge_doc_ids = {
        edge_doc_id
        for edge in payload["graph_context"]["edges"]
        for edge_doc_id in (edge["src_doc_id"], edge["dst_doc_id"])
    }
    assert "claim:c_unreviewed_graph_neighbor" not in result_ids
    assert "claim:c_unreviewed_graph_neighbor" not in neighbor_ids
    assert "claim:c_unreviewed_graph_neighbor" not in edge_doc_ids


def test_search_knowledge_uses_semantic_alias_channel(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    db.add(
        KBDocument(
            doc_id="claim:c_unreviewed_graph_neighbor",
            doc_type="claim",
            title="Unreviewed Graph Neighbor",
            summary="MTHFR 草稿邻居不应出现在搜索结果或 graph_context。",
            confidence=0.95,
            evidence_level="B",
            metadata_json={"review_status": "draft"},
        )
    )
    db.flush()
    db.add(
        KBEdge(
            src_doc_id="entity:gene:MTHFR",
            dst_doc_id="claim:c_unreviewed_graph_neighbor",
            relation="has_claim",
            confidence=0.8,
            source_claim_id="claim:c_unreviewed_graph_neighbor",
        )
    )
    db.commit()

    response = client.get(
        "/api/v1/knowledge/search",
        headers=headers,
        params={"q": "MTHFR", "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    result_ids = {item["document"]["doc_id"] for item in payload["results"]}
    neighbor_ids = {item["doc_id"] for item in payload["graph_context"]["neighbors"]}
    edge_doc_ids = {
        edge_doc_id
        for edge in payload["graph_context"]["edges"]
        for edge_doc_id in (edge["src_doc_id"], edge["dst_doc_id"])
    }
    assert "claim:c_unreviewed_graph_neighbor" not in result_ids
    assert "claim:c_unreviewed_graph_neighbor" not in neighbor_ids
    assert "claim:c_unreviewed_graph_neighbor" not in edge_doc_ids


def test_search_knowledge_uses_sparse_vector_channel(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    from app.services.system_knowledge_service import reindex_knowledge_documents

    reindex_knowledge_documents(db, actor="test")

    response = client.get(
        "/api/v1/knowledge/search",
        headers=headers,
        params={"q": "homocysteine", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    claim_result = next(
        item
        for item in payload["results"]
        if item["document"]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"
    )
    assert "vector" in claim_result["retrieval"]["channels"]
    assert claim_result["retrieval"]["vector_score"] > 0
    assert payload["retrieval_plan"]["vector_backend"] == "sparse_term_cosine_v1"


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
                metadata_json={
                    "origin": "down-dedao-llm-wiki",
                    "review_status": "reviewed",
                    "external_sources": [
                        {"kind": "research", "source": "pubmed:123", "review_status": "reviewed"}
                    ],
                },
                sources=["dedao:foo", "pubmed:123"],
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
                            "specialist": "fuel_strategist",
                            "category": "nutrition",
                            "evidence_refs": ["claim:c_reviewed"],
                            "support_status": "supported",
                            "unsupported": False,
                        },
                        {
                            "summary": "unsupported flag",
                            "specialist": "fuel_strategist",
                            "category": "nutrition",
                            "evidence_refs": [],
                            "support_status": "model_inference",
                            "unsupported": True,
                        },
                        {
                            "summary": "missing refs",
                            "specialist": "movement_coach",
                            "category": "movement",
                            "data": {"unsupported": True, "support_status": "model_inference"},
                        },
                        {
                            "summary": "data gap",
                            "specialist": "longitudinal_analyst",
                            "category": "longitudinal",
                            "data": {
                                "support_status": "not_applicable",
                                "unsupported": False,
                                "evidence_refs": [],
                            },
                        },
                        {
                            "summary": "legacy kb refs",
                            "specialist": "rhinitis_specialist",
                            "category": "chronic",
                            "data": {
                                "system_kb_evidence_refs": ["claim:c_reviewed"],
                            },
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
            NotificationLog(
                user_id=user.id,
                notification_type="ai_advice",
                channel="ios_apns",
                title="supported push",
                content="with claim",
                data={
                    "support_status": "supported",
                    "unsupported": False,
                    "evidence_refs": ["claim:c_reviewed"],
                    "evidence_ref_count": 1,
                },
            ),
            NotificationLog(
                user_id=user.id,
                notification_type="ai_advice",
                channel="ios_apns",
                title="unsupported push",
                content="missing claim",
                data={
                    "support_status": "model_inference",
                    "unsupported": True,
                    "evidence_refs": [],
                    "evidence_ref_count": 0,
                },
            ),
            NotificationLog(
                user_id=user.id,
                notification_type="trend_report",
                channel="ios_apns",
                title="trend push",
                content="data summary",
                data={
                    "support_status": "data_summary",
                    "unsupported": False,
                    "evidence_refs": [],
                    "evidence_ref_count": 0,
                },
            ),
            NotificationLog(
                user_id=user.id,
                notification_type="reminder",
                channel="ios_apns",
                title="plain reminder",
                content="not kb governed",
                data={"reminder_type": "water"},
            ),
        ]
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/coverage_report", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"]["total"] == 2
    assert payload["documents"]["by_origin"]["down-dedao-llm-wiki"] == 1
    assert payload["documents"]["by_origin"]["unknown"] == 1
    assert payload["documents"]["by_review_status"]["reviewed"] == 1
    assert payload["documents"]["by_review_status"]["draft"] == 1
    assert payload["specialist_findings"]["total"] == 5
    assert payload["specialist_findings"]["applicable_total"] == 4
    assert payload["specialist_findings"]["not_applicable"] == 1
    assert payload["specialist_findings"]["with_evidence_refs"] == 2
    assert payload["specialist_findings"]["unsupported"] == 2
    assert payload["specialist_findings"]["evidence_ref_rate"] == 0.5
    assert payload["specialist_findings"]["raw_evidence_ref_rate"] == 0.4
    assert payload["specialist_findings"]["target_evidence_ref_rate"] == 0.85
    assert payload["specialist_findings"]["meets_target"] is False
    assert payload["specialist_findings"]["by_specialist"]["fuel_strategist"]["total"] == 2
    assert payload["specialist_findings"]["by_specialist"]["fuel_strategist"]["evidence_ref_rate"] == 0.5
    assert payload["specialist_findings"]["by_specialist"]["fuel_strategist"]["unsupported_rate"] == 0.5
    assert payload["specialist_findings"]["by_category"]["nutrition"]["total"] == 2
    assert payload["specialist_findings"]["by_category"]["movement"]["unsupported"] == 1
    assert payload["specialist_findings"]["by_category"]["longitudinal"]["unsupported"] == 0
    assert payload["specialist_findings"]["by_category"]["chronic"]["evidence_ref_rate"] == 1.0
    assert payload["specialist_findings"]["by_support_status"]["supported"] == 2
    assert payload["specialist_findings"]["by_support_status"]["model_inference"] == 2
    assert payload["specialist_findings"]["by_support_status"]["not_applicable"] == 1
    assert payload["external_evidence"]["claim_total"] == 2
    assert payload["external_evidence"]["claims_with_external_sources"] == 1
    assert payload["external_evidence"]["external_source_rate"] == 0.5
    assert payload["external_evidence"]["target_external_source_rate"] == 0.2
    assert payload["external_evidence"]["meets_target"] is True
    assert payload["external_evidence"]["by_kind"]["research"] == 1
    assert payload["notification_evidence"]["total"] == 3
    assert payload["notification_evidence"]["with_evidence_refs"] == 1
    assert payload["notification_evidence"]["unsupported"] == 1
    assert payload["notification_evidence"]["evidence_ref_rate"] == 0.3333
    assert payload["notification_evidence"]["unsupported_rate"] == 0.3333
    assert payload["notification_evidence"]["by_type"]["ai_advice"]["total"] == 2
    assert payload["notification_evidence"]["by_type"]["ai_advice"]["unsupported"] == 1
    assert payload["notification_evidence"]["by_type"]["ai_advice"]["evidence_ref_rate"] == 0.5
    assert payload["notification_evidence"]["by_type"]["ai_advice"]["unsupported_rate"] == 0.5
    assert payload["notification_evidence"]["by_support_status"]["supported"] == 1
    assert payload["notification_evidence"]["by_support_status"]["model_inference"] == 1
    assert payload["notification_evidence"]["by_support_status"]["data_summary"] == 1
    assert payload["feedback"]["disagree"] == 1


def test_admin_eval_report_runs_reviewed_eval_cases(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_admin_eval_weight_loss_boundary",
                doc_type="claim",
                entity_type="goal",
                entity_id="weight-loss",
                title="减重目标只做行为边界",
                summary="减重目标下只整理行为和趋势，不生成处方或极端饮食。",
                confidence=0.72,
                evidence_level="B",
                applies_when=["twin.goals.weight_loss.active == true"],
                sources=["guideline:test"],
                metadata_json={"review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="eval:admin_eval_weight_loss_boundary",
                doc_type="eval_case",
                entity_type="goal",
                entity_id="weight-loss",
                title="减重目标 eval",
                metadata_json={
                    "review_status": "reviewed",
                    "case_id": "eval:admin_eval_weight_loss_boundary",
                    "input": {"lookup_twin": {"goals": {"weight_loss": {"active": True}}}},
                    "expected": {
                        "required_claim_ids": ["claim:c_admin_eval_weight_loss_boundary"],
                    },
                },
            ),
        ]
    )
    db.commit()

    response = client.get(
        "/api/v1/admin/knowledge/eval_report?case_id=eval:admin_eval_weight_loss_boundary",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["passed"] == 1
    assert payload["failed"] == 0
    assert payload["cases"][0]["case_id"] == "eval:admin_eval_weight_loss_boundary"


def test_admin_operations_dashboard_summarizes_kb_health(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add_all(
        [
            KBDocument(
                doc_id="entity:condition:metabolic-health",
                doc_type="entity",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Metabolic health",
                metadata_json={"review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="claim:c_supported",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Supported",
                evidence_level="B",
                metadata_json={
                    "review_status": "reviewed",
                    "external_sources": [
                        {"kind": "guideline", "source": "guideline:test", "review_status": "reviewed"}
                    ],
                },
                sources=["dedao:test", "guideline:test"],
            ),
            KBDocument(
                doc_id="claim:c_missing_external",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Missing external",
                evidence_level="B",
                metadata_json={"review_status": "reviewed"},
                sources=["dedao:test"],
            ),
            KBEdge(
                src_doc_id="entity:condition:metabolic-health",
                dst_doc_id="claim:c_supported",
                relation="has_claim",
                confidence=0.9,
                source_claim_id="claim:c_supported",
            ),
            KBEdge(
                src_doc_id="entity:condition:metabolic-health",
                dst_doc_id="claim:c_missing_external",
                relation="has_claim",
                confidence=0.8,
                source_claim_id="claim:c_missing_external",
            ),
            KBAudit(
                doc_id=None,
                op="lifecycle_report",
                actor="celery:system-kb-lifecycle",
                diff={"lint": {"summary": {"orphan_claims": 0}}, "decay": {"processed": 1}},
            ),
            NotificationLog(
                user_id=user.id,
                notification_type="ai_advice",
                channel="ios_apns",
                title="unsupported push",
                content="missing claim",
                data={
                    "support_status": "model_inference",
                    "unsupported": True,
                    "evidence_refs": [],
                    "evidence_ref_count": 0,
                },
            ),
        ]
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/operations_dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "attention"
    assert payload["coverage"]["documents"]["total"] == 3
    assert payload["coverage"]["external_evidence"]["claims_with_external_sources"] == 1
    assert payload["coverage"]["external_evidence"]["meets_target"] is True
    assert payload["coverage"]["external_evidence"]["missing_external_source_claims"] == [
        {
            "doc_id": "claim:c_missing_external",
            "title": "Missing external",
            "entity_type": "condition",
            "entity_id": "metabolic-health",
        }
    ]
    assert payload["lint"]["summary"]["orphan_claims"] == 0
    assert payload["latest_lifecycle_report"]["op"] == "lifecycle_report"
    assert "specialist_evidence_below_target" in payload["action_items"]
    assert "notification_evidence_unsupported_high" in payload["action_items"]


def test_admin_operations_dashboard_flags_eval_failures(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add(
        KBAudit(
            doc_id=None,
            op="lifecycle_report",
            actor="celery:system-kb-lifecycle",
            diff={
                "lint": {"summary": {}},
                "decay": {"processed": 0},
                "eval": {"total": 2, "passed": 1, "failed": 1},
            },
        )
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/operations_dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "attention"
    assert "kb_eval_failures_present" in payload["action_items"]


def test_admin_operations_dashboard_surfaces_dedao_kbase_draft_sync(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add(
        KBAudit(
            doc_id=None,
            op="dedao_kbase_export_sync_draft",
            actor="celery:dedao_kbase_export_sync",
            diff={
                "status": "draft_written",
                "export_url": "https://kbase.executor.life/api/export",
                "artifact_dir": "/tmp/system_kb_v2_seed",
                "source": "dedao-kbase",
                "source_repo": "dedao-kbase",
                "source_commit": "abc123",
                "source_version": "2026-06-28",
                "diff": {"documents": {"added": 3}, "edges": {"added": 4}},
                "gate": {
                    "serving_allowed": False,
                    "blocking_reasons": ["draft_artifacts_pending_review"],
                },
            },
        )
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/operations_dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_dedao_kbase_export_sync"]["op"] == "dedao_kbase_export_sync_draft"
    assert payload["latest_dedao_kbase_export_sync"]["diff"]["source_commit"] == "abc123"
    assert payload["latest_dedao_kbase_export_sync"]["diff"]["gate"]["serving_allowed"] is False
    assert "dedao_kbase_draft_review_needed" in payload["action_items"]


def test_admin_operations_dashboard_flags_stale_source_freshness(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add(
        KBDocument(
            doc_id="claim:c_sleep_stale_guideline_source",
            doc_type="claim",
            entity_type="sleep",
            entity_id="caffeine",
            title="睡眠前咖啡因窗口",
            summary="睡眠前较晚摄入咖啡因可能影响入睡。",
            body="仅用于健康管理提示。",
            confidence=0.74,
            evidence_level="B",
            sources=["guideline:sleep-caffeine-window"],
            last_confirmed=datetime(2026, 5, 1, tzinfo=UTC),
            decay_rate="normal",
            metadata_json={
                "review_status": "reviewed",
                "domain": "sleep",
                "external_sources": [
                    {
                        "source": "guideline:sleep-caffeine-window",
                        "kind": "guideline",
                        "last_reviewed_at": "2024-01-01T00:00:00+00:00",
                    }
                ],
            },
        )
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/operations_dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert "kb_stale_sources_present" in payload["action_items"]
    freshness = payload["coverage"]["domain_coverage"]["sleep"]["source_freshness"]
    assert freshness["source_total"] == 1
    assert freshness["stale_sources"] == 1
    assert freshness["items"][0]["source"] == "guideline:sleep-caffeine-window"
    assert freshness["items"][0]["kind"] == "guideline"
    assert freshness["items"][0]["days_since_reviewed"] > 365


def test_admin_operations_dashboard_flags_pgvector_dense_coverage_gap(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_pgvector_indexed",
                doc_type="claim",
                entity_type="nutrition",
                entity_id="folate",
                title="Indexed claim",
                evidence_level="B",
                metadata_json={"review_status": "reviewed"},
            ),
            KBDocument(
                doc_id="claim:c_pgvector_missing",
                doc_type="claim",
                entity_type="nutrition",
                entity_id="b12",
                title="Missing dense vector",
                evidence_level="B",
                metadata_json={"review_status": "reviewed"},
            ),
            KBAudit(
                doc_id=None,
                op="lifecycle_report",
                actor="celery:system-kb-lifecycle",
                diff={"lint": {"summary": {}}, "eval": {"total": 1, "passed": 1, "failed": 0}},
            ),
            KBAudit(
                doc_id=None,
                op="system_kb_reindex_report",
                actor="celery:system-kb-reindex",
                diff={
                    "reindex": {"documents": 2, "dense_vectors": 1},
                    "pgvector": {
                        "enabled": True,
                        "postgres": True,
                        "table_exists": True,
                        "embedding_rows": 1,
                        "embedding_model": "text-embedding-v3",
                        "current_vector_backend": "sparse_term_cosine_v1",
                    },
                },
            ),
        ]
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/operations_dashboard", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "attention"
    assert payload["pgvector"]["latest_reindex_report"]["op"] == "system_kb_reindex_report"
    assert payload["pgvector"]["latest_reindex_report"]["diff"]["reindex"]["dense_vectors"] == 1
    assert "kb_pgvector_dense_coverage_low" in payload["action_items"]
    assert "kb_pgvector_backend_fallback" in payload["action_items"]


def test_admin_dedao_kbase_draft_review_bundle_reads_configured_artifacts(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "system_kb_v2_seed"
    artifact_dir.mkdir()
    monkeypatch.setattr(settings, "system_kb_artifact_dir", str(artifact_dir))
    _write_artifact_jsonl(
        artifact_dir / "pages.jsonl",
        [
            {
                "doc_id": "page:ak-kbase:sleep-caffeine",
                "title": "Sleep caffeine",
                "summary": "咖啡因与睡眠窗口的结构化摘要。",
                "metadata": {"review_status": "draft", "origin": "dedao-kbase-export"},
                "sources": ["dedao:sleep-course"],
            }
        ],
    )
    _write_artifact_jsonl(artifact_dir / "entities.jsonl", [])
    _write_artifact_jsonl(
        artifact_dir / "claims.jsonl",
        [
            {
                "doc_id": "claim:c_sleep_caffeine_window",
                "doc_type": "claim",
                "entity_type": "sleep",
                "entity_id": "caffeine",
                "title": "睡眠前咖啡因窗口",
                "summary": "下午晚些时候摄入咖啡因可能影响入睡。",
                "evidence_level": "B",
                "confidence": 0.72,
                "metadata": {"review_status": "draft", "origin": "dedao-kbase-export"},
                "sources": ["dedao:sleep-course", "guideline:test"],
            }
        ],
    )
    _write_artifact_jsonl(artifact_dir / "protocols.jsonl", [])
    _write_artifact_jsonl(artifact_dir / "contraindications.jsonl", [])
    _write_artifact_jsonl(artifact_dir / "eval_cases.jsonl", [])
    _write_artifact_jsonl(
        artifact_dir / "relations.jsonl",
        [
            {
                "src_doc_id": "page:ak-kbase:sleep-caffeine",
                "dst_doc_id": "claim:c_sleep_caffeine_window",
                "relation": "supports",
                "confidence": 0.8,
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "ingest": {"review_status": "draft"},
                "draft_gate": {"status": "draft", "requires_review": True, "serving_allowed": False},
                "counts": _artifact_counts(artifact_dir),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "draft_manifest.json").write_text(
        json.dumps({"status": "draft", "requires_review": True, "serving_allowed": False}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    response = client.get("/api/v1/admin/knowledge/dedao_kbase/draft_review", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_dir"] == str(artifact_dir)
    assert payload["gate"]["serving_allowed"] is False
    assert payload["gate"]["blocking_reasons"] == ["draft_artifacts_present", "manifest_not_reviewed"]
    assert payload["draft_manifest"]["status"] == "draft"
    assert payload["workspace_fingerprint"] == workspace_content_fingerprint(artifact_dir)
    assert payload["preview"]["counts"]["claims"] == 1
    assert payload["preview"]["claims"][0]["doc_id"] == "claim:c_sleep_caffeine_window"
    assert payload["preview"]["claims"][0]["review_status"] == "draft"
    assert "body" not in payload["preview"]["claims"][0]
    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_draft_review_bundle").count() == 1


def test_admin_dedao_kbase_draft_review_items_are_bounded_and_body_free(
    client,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "dedao-review"
    _write_dedao_review_workspace(artifact_dir)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(artifact_dir))

    response = client.get(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items?offset=0&limit=20",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["doc_id"] == "claim:release-abc-claim-1"
    assert payload["items"][0]["source_count"] == 1
    assert "body" not in payload["items"][0]


def test_admin_dedao_kbase_review_workspace_selector_reaches_agent_package_drafts(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    release_workspace = tmp_path / "dedao-review"
    agent_workspace = release_workspace / "agent-packages"
    _write_dedao_review_workspace(release_workspace)
    _write_dedao_review_workspace(agent_workspace)
    agent_claims = [
        {
            **row,
            "title": "Agent Package 隔离候选",
            "metadata": {
                **(row.get("metadata") or {}),
                "origin": "dedao-kbase-agent-package",
                "package_id": "health-book",
                "package_version": "1.0.0",
            },
        }
        for row in (
            json.loads(line)
            for line in (agent_workspace / "claims.jsonl").read_text().splitlines()
            if line.strip()
        )
    ]
    _write_artifact_jsonl(agent_workspace / "claims.jsonl", agent_claims)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(release_workspace))

    bundle = client.get(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review?workspace=agent_package",
        headers=headers,
    )
    assert bundle.status_code == 200
    assert bundle.json()["artifact_dir"] == str(agent_workspace)
    assert bundle.json()["preview"]["claims"][0]["title"] == "Agent Package 隔离候选"

    fingerprint = workspace_content_fingerprint(agent_workspace)
    adjudicated = client.patch(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1",
        headers=headers,
        json={
            "workspace": "agent_package",
            "workspace_fingerprint": fingerprint,
            "decision": "approve",
        },
    )
    assert adjudicated.status_code == 200
    release_claim = json.loads((release_workspace / "claims.jsonl").read_text().splitlines()[0])
    agent_claim = json.loads((agent_workspace / "claims.jsonl").read_text().splitlines()[0])
    assert release_claim["metadata"]["review_status"] == "draft"
    assert agent_claim["metadata"]["review_status"] == "reviewed"
    audit = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_claim_adjudicated").one()
    assert audit.diff["workspace"] == "agent_package"

    finalized = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/finalize",
        headers=headers,
        json={
            "workspace": "agent_package",
            "workspace_fingerprint": adjudicated.json()["workspace_fingerprint"],
        },
    )
    assert finalized.status_code == 200
    assert finalized.json()["artifact_dir"] == str(agent_workspace)
    assert finalized.json()["gate"]["serving_allowed"] is True

    preview = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/reviewed_artifacts/publish/preview",
        headers=headers,
        json={"workspace": "agent_package"},
    )
    assert preview.status_code == 200
    assert preview.json()["artifact_dir"] == str(agent_workspace)
    assert preview.json()["dry_run"] is True
    assert db.get(KBDocument, "claim:release-abc-claim-1") is None


def test_admin_dedao_kbase_claim_adjudication_records_metadata_only_audit(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "dedao-review"
    _write_dedao_review_workspace(artifact_dir)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(artifact_dir))

    response = client.patch(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1",
        headers=headers,
        json={
            "workspace_fingerprint": workspace_content_fingerprint(artifact_dir),
            "decision": "approve",
            "note": "外部证据核验后通过",
            "evidence_level": "B",
            "confidence": 0.84,
            "evidence": {
                "kind": "research",
                "source": "pubmed:12345",
                "title": "Caffeine and sleep",
                "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "approve"
    audit = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_claim_adjudicated").one()
    assert audit.doc_id == "claim:release-abc-claim-1"
    assert audit.diff["decision"] == "approve"
    assert audit.diff["release_id"] == "release-abc"
    assert audit.diff["release_claim_id"] == "claim-1"
    assert audit.diff["evidence"]["source"] == "pubmed:12345"
    assert "body" not in json.dumps(audit.diff, ensure_ascii=False)
    assert "不应写入审计" not in json.dumps(audit.diff, ensure_ascii=False)


def test_admin_dedao_kbase_claim_adjudication_returns_conflict_for_stale_fingerprint(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "dedao-review"
    _write_dedao_review_workspace(artifact_dir)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(artifact_dir))

    response = client.patch(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1",
        headers=headers,
        json={
            "workspace_fingerprint": "0" * 64,
            "decision": "needs_evidence",
            "note": "需要二源",
        },
    )

    assert response.status_code == 409
    assert "reload" in response.json()["detail"]
    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_claim_adjudicated").count() == 0


def test_admin_dedao_kbase_verification_packet_generate_read_and_audit_are_body_free(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "dedao-review"
    _write_dedao_review_workspace(artifact_dir)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(artifact_dir))
    fingerprint = workspace_content_fingerprint(artifact_dir)

    generated = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1/verification",
        headers=headers,
        json={"workspace_fingerprint": fingerprint},
    )

    assert generated.status_code == 200
    packet = generated.json()["packet"]
    assert packet["proposed_decision"] == "needs_evidence"
    assert generated.json()["workspace_fingerprint"] == fingerprint
    listed = client.get(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1/verification",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["packet_id"] == packet["packet_id"]
    assert listed.json()["items"][0]["stale"] is False

    audit = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_verification_generated").one()
    assert len(audit.op) <= 40
    assert audit.doc_id == "claim:release-abc-claim-1"
    assert audit.diff["packet_id"] == packet["packet_id"]
    assert "summary" not in json.dumps(audit.diff, ensure_ascii=False)
    assert "晚间咖啡因" not in json.dumps(audit.diff, ensure_ascii=False)


def test_admin_dedao_kbase_verification_packet_returns_conflict_for_stale_fingerprint(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "dedao-review"
    _write_dedao_review_workspace(artifact_dir)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(artifact_dir))

    response = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1/verification",
        headers=headers,
        json={"workspace_fingerprint": "0" * 64},
    )

    assert response.status_code == 409
    assert "reload" in response.json()["detail"]
    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_verification_generated").count() == 0


def test_admin_dedao_kbase_applies_only_ready_current_verification_packet(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "dedao-review"
    _write_dedao_review_workspace(artifact_dir)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(artifact_dir))
    fingerprint = workspace_content_fingerprint(artifact_dir)
    generated = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1/verification",
        headers=headers,
        json={"workspace_fingerprint": fingerprint},
    ).json()

    applied = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1/verification/apply",
        headers=headers,
        json={
            "workspace_fingerprint": fingerprint,
            "packet_id": generated["packet"]["packet_id"],
            "note": "采纳验证包建议",
        },
    )

    assert applied.status_code == 200
    assert applied.json()["decision"] == "needs_evidence"
    assert applied.json()["packet_id"] == generated["packet"]["packet_id"]
    audit = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_verification_applied").one()
    assert len(audit.op) <= 40
    assert audit.diff["decision"] == "needs_evidence"
    assert audit.diff["release_id"] == "release-abc"
    assert audit.diff["release_claim_id"] == "claim-1"
    assert "晚间咖啡因" not in json.dumps(audit.diff, ensure_ascii=False)

    stale_apply = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1/verification/apply",
        headers=headers,
        json={
            "workspace_fingerprint": applied.json()["workspace_fingerprint"],
            "packet_id": generated["packet"]["packet_id"],
        },
    )
    assert stale_apply.status_code == 409


def test_admin_dedao_kbase_finalize_requires_resolved_claims_then_allows_dry_run_preview(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "dedao-review"
    _write_dedao_review_workspace(artifact_dir)
    monkeypatch.setattr(settings, "dedao_kbase_review_artifact_dir", str(artifact_dir))
    fingerprint = workspace_content_fingerprint(artifact_dir)

    blocked = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/finalize",
        headers=headers,
        json={"workspace_fingerprint": fingerprint, "note": "finalize"},
    )
    assert blocked.status_code == 400
    assert "unresolved claim decisions" in blocked.json()["detail"]

    approved = client.patch(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/items/claim%3Arelease-abc-claim-1",
        headers=headers,
        json={"workspace_fingerprint": fingerprint, "decision": "approve"},
    )
    assert approved.status_code == 200
    finalized = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/finalize",
        headers=headers,
        json={"workspace_fingerprint": approved.json()["workspace_fingerprint"], "note": "finalize"},
    )
    assert finalized.status_code == 200
    assert finalized.json()["gate"]["serving_allowed"] is True

    preview = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/reviewed_artifacts/publish/preview",
        headers=headers,
        json={"note": "preview only"},
    )
    assert preview.status_code == 200
    assert preview.json()["dry_run"] is True
    assert preview.json()["import"]["documents"] == 3
    assert db.get(KBDocument, "claim:release-abc-claim-1") is None
    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_reviewed_artifacts_publish_preview").count() == 1


def test_admin_dedao_kbase_legacy_approve_rejects_unresolved_claims(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "system_kb_v2_seed"
    artifact_dir.mkdir()
    monkeypatch.setattr(settings, "system_kb_artifact_dir", str(artifact_dir))
    for name in ("pages", "entities", "protocols", "contraindications", "eval_cases"):
        _write_artifact_jsonl(artifact_dir / f"{name}.jsonl", [])
    _write_artifact_jsonl(
        artifact_dir / "claims.jsonl",
        [
            {
                "doc_id": "claim:c_sleep_caffeine_window",
                "doc_type": "claim",
                "entity_type": "sleep",
                "entity_id": "caffeine",
                "title": "睡眠前咖啡因窗口",
                "summary": "下午晚些时候摄入咖啡因可能影响入睡。",
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "relations.jsonl",
        [
            {
                "src_doc_id": "entity:sleep:caffeine",
                "dst_doc_id": "claim:c_sleep_caffeine_window",
                "relation": "has_claim",
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {"ingest": {"review_status": "draft"}, "counts": _artifact_counts(artifact_dir)},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "draft_manifest.json").write_text(
        json.dumps({"status": "draft", "requires_review": True, "serving_allowed": False}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/approve",
        headers=headers,
        json={
            "workspace_fingerprint": workspace_content_fingerprint(artifact_dir),
            "note": "结构化摘要已人工核对",
        },
    )

    assert response.status_code == 400
    assert "unresolved claim decisions" in response.json()["detail"]
    stored_claim = json.loads((artifact_dir / "claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert stored_claim["metadata"]["review_status"] == "draft"
    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_draft_review_approved").count() == 0


def test_admin_dedao_kbase_legacy_approve_rejects_direct_publish(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "system_kb_v2_seed"
    artifact_dir.mkdir()
    monkeypatch.setattr(settings, "system_kb_artifact_dir", str(artifact_dir))
    for name in ("pages", "protocols", "contraindications", "eval_cases"):
        _write_artifact_jsonl(artifact_dir / f"{name}.jsonl", [])
    _write_artifact_jsonl(
        artifact_dir / "entities.jsonl",
        [
            {
                "doc_id": "entity:sleep:caffeine",
                "doc_type": "entity",
                "entity_type": "sleep",
                "entity_id": "caffeine",
                "title": "咖啡因",
                "summary": "咖啡因是睡眠相关刺激物。",
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "claims.jsonl",
        [
            {
                "doc_id": "claim:c_sleep_caffeine_window",
                "doc_type": "claim",
                "entity_type": "sleep",
                "entity_id": "caffeine",
                "title": "睡眠前咖啡因窗口",
                "summary": "下午晚些时候摄入咖啡因可能影响入睡。",
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "relations.jsonl",
        [
            {
                "src_doc_id": "entity:sleep:caffeine",
                "dst_doc_id": "claim:c_sleep_caffeine_window",
                "relation": "has_claim",
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {"ingest": {"review_status": "draft"}, "counts": _artifact_counts(artifact_dir)},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "draft_manifest.json").write_text(
        json.dumps({"status": "draft", "requires_review": True, "serving_allowed": False}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/approve",
        headers=headers,
        json={
            "workspace_fingerprint": workspace_content_fingerprint(artifact_dir),
            "note": "审核后直接发布",
            "publish": True,
        },
    )

    assert response.status_code == 400
    assert "no longer supports publish" in response.json()["detail"]
    assert db.get(KBDocument, "claim:c_sleep_caffeine_window") is None
    assert db.query(KBEdge).filter(KBEdge.dst_doc_id == "claim:c_sleep_caffeine_window").count() == 0
    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_draft_review_approved").count() == 0


def test_admin_dedao_kbase_legacy_approve_rejects_inline_publish_preview(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "system_kb_v2_seed"
    artifact_dir.mkdir()
    monkeypatch.setattr(settings, "system_kb_artifact_dir", str(artifact_dir))
    for name in ("pages", "protocols", "contraindications", "eval_cases"):
        _write_artifact_jsonl(artifact_dir / f"{name}.jsonl", [])
    _write_artifact_jsonl(
        artifact_dir / "entities.jsonl",
        [
            {
                "doc_id": "entity:sleep:caffeine",
                "doc_type": "entity",
                "entity_type": "sleep",
                "entity_id": "caffeine",
                "title": "咖啡因",
                "summary": "咖啡因是睡眠相关刺激物。",
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "claims.jsonl",
        [
            {
                "doc_id": "claim:c_sleep_caffeine_window",
                "doc_type": "claim",
                "entity_type": "sleep",
                "entity_id": "caffeine",
                "title": "睡眠前咖啡因窗口",
                "summary": "下午晚些时候摄入咖啡因可能影响入睡。",
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "relations.jsonl",
        [
            {
                "src_doc_id": "entity:sleep:caffeine",
                "dst_doc_id": "claim:c_sleep_caffeine_window",
                "relation": "has_claim",
                "metadata": {"review_status": "draft"},
            }
        ],
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {"ingest": {"review_status": "draft"}, "counts": _artifact_counts(artifact_dir)},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "draft_manifest.json").write_text(
        json.dumps({"status": "draft", "requires_review": True, "serving_allowed": False}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/draft_review/approve",
        headers=headers,
        json={
            "workspace_fingerprint": workspace_content_fingerprint(artifact_dir),
            "note": "先预检发布影响",
            "dry_run_publish": True,
        },
    )

    assert response.status_code == 400
    assert "separate preview endpoint" in response.json()["detail"]
    assert db.get(KBDocument, "claim:c_sleep_caffeine_window") is None
    assert db.query(KBEdge).filter(KBEdge.dst_doc_id == "claim:c_sleep_caffeine_window").count() == 0
    assert db.query(KBAudit).filter(KBAudit.op == "system_kb_reindex_report").count() == 0
    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_draft_review_approved").count() == 0


def test_admin_dedao_kbase_reviewed_artifacts_publish_imports_without_reapproving(
    client,
    db,
    auth_user_and_headers,
    tmp_path,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    artifact_dir = tmp_path / "system_kb_v2_seed"
    artifact_dir.mkdir()
    monkeypatch.setattr(settings, "system_kb_artifact_dir", str(artifact_dir))
    for name in ("pages", "protocols", "contraindications", "eval_cases"):
        _write_artifact_jsonl(artifact_dir / f"{name}.jsonl", [])
    _write_artifact_jsonl(
        artifact_dir / "entities.jsonl",
        [
            {
                "doc_id": "entity:sleep:caffeine",
                "doc_type": "entity",
                "entity_type": "sleep",
                "entity_id": "caffeine",
                "title": "咖啡因",
                "summary": "咖啡因是睡眠相关刺激物。",
                "metadata": {"review_status": "reviewed"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "claims.jsonl",
        [
            {
                "doc_id": "claim:c_sleep_caffeine_window",
                "doc_type": "claim",
                "entity_type": "sleep",
                "entity_id": "caffeine",
                "title": "睡眠前咖啡因窗口",
                "summary": "下午晚些时候摄入咖啡因可能影响入睡。",
                "metadata": {"review_status": "reviewed"},
            }
        ],
    )
    _write_artifact_jsonl(
        artifact_dir / "relations.jsonl",
        [
            {
                "src_doc_id": "entity:sleep:caffeine",
                "dst_doc_id": "claim:c_sleep_caffeine_window",
                "relation": "has_claim",
                "metadata": {"review_status": "reviewed"},
            }
        ],
    )
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "ingest": {"review_status": "reviewed"},
                "review": {"review_status": "reviewed"},
                "counts": _artifact_counts(artifact_dir),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "draft_manifest.json").write_text(
        json.dumps({"status": "reviewed", "requires_review": False, "serving_allowed": True}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/v1/admin/knowledge/dedao_kbase/reviewed_artifacts/publish",
        headers=headers,
        json={"note": "dry-run 已确认，执行发布"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["import"]["documents"] == 2
    assert payload["import"]["edges"] == 1
    assert payload["reindex"]["reindex"]["documents"] == 2
    assert db.get(KBDocument, "claim:c_sleep_caffeine_window").metadata_json["review_status"] == "reviewed"
    assert db.query(KBEdge).filter(KBEdge.dst_doc_id == "claim:c_sleep_caffeine_window").count() == 1
    publish_audit = db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_reviewed_artifacts_published").one()
    assert publish_audit.diff["published"] is True
    assert publish_audit.diff["note"] == "dry-run 已确认，执行发布"
    assert db.query(KBAudit).filter(KBAudit.op == "dedao_kbase_draft_review_approved").count() == 0


def test_admin_review_queue_prioritizes_claims_needing_human_review(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_draft_no_external",
                doc_type="claim",
                entity_type="gene",
                entity_id="MTHFR",
                title="Draft no external",
                evidence_level="C",
                confidence=0.61,
                metadata_json={"review_status": "draft"},
                sources=["dedao:test"],
            ),
            KBDocument(
                doc_id="claim:c_needs_review_duplicate",
                doc_type="claim",
                entity_type="gene",
                entity_id="MTHFR",
                title="Needs review duplicate",
                evidence_level="B",
                confidence=0.72,
                metadata_json={
                    "review_status": "needs_review",
                    "candidate_duplicates": ["claim:c_old"],
                },
                sources=["dedao:test", "pubmed:123"],
            ),
            KBDocument(
                doc_id="claim:c_reviewed_missing_external",
                doc_type="claim",
                entity_type="condition",
                entity_id="metabolic-health",
                title="Reviewed missing external",
                evidence_level="B",
                confidence=0.8,
                metadata_json={"review_status": "reviewed"},
                sources=["dedao:test"],
            ),
            KBDocument(
                doc_id="claim:c_feedback",
                doc_type="claim",
                entity_type="supplement",
                entity_id="5-MTHF",
                title="Feedback claim",
                evidence_level="B",
                confidence=0.82,
                metadata_json={
                    "review_status": "reviewed",
                    "external_sources": [
                        {"kind": "research", "source": "pubmed:456", "review_status": "reviewed"}
                    ],
                },
                sources=["dedao:test", "pubmed:456"],
            ),
            KBDocument(
                doc_id="claim:c_clean",
                doc_type="claim",
                entity_type="condition",
                entity_id="sleep",
                title="Clean reviewed claim",
                evidence_level="A",
                confidence=0.9,
                metadata_json={
                    "review_status": "reviewed",
                    "external_sources": [
                        {"kind": "guideline", "source": "guideline:clean", "review_status": "reviewed"}
                    ],
                },
                sources=["guideline:clean"],
            ),
            KBAudit(
                doc_id="claim:c_feedback",
                op="feedback_disagree",
                actor=f"user:{user.id}",
                diff={"reason": "不适用"},
            ),
        ]
    )
    db.commit()

    response = client.get("/api/v1/admin/knowledge/review_queue?limit=10", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] == 4
    assert payload["summary"]["by_review_status"]["draft"] == 1
    assert payload["summary"]["by_review_status"]["needs_review"] == 1
    assert payload["summary"]["by_reason"]["draft"] == 1
    assert payload["summary"]["by_reason"]["needs_review"] == 1
    assert payload["summary"]["by_reason"]["missing_external_evidence"] == 2
    assert payload["summary"]["by_reason"]["candidate_duplicate"] == 1
    assert payload["summary"]["by_reason"]["user_feedback"] == 1
    by_id = {item["doc_id"]: item for item in payload["items"]}
    assert set(by_id) == {
        "claim:c_draft_no_external",
        "claim:c_needs_review_duplicate",
        "claim:c_reviewed_missing_external",
        "claim:c_feedback",
    }
    assert by_id["claim:c_draft_no_external"]["review_status"] == "draft"
    assert by_id["claim:c_draft_no_external"]["external_source_count"] == 0
    assert by_id["claim:c_needs_review_duplicate"]["candidate_duplicates"] == ["claim:c_old"]
    assert by_id["claim:c_feedback"]["feedback_disagree_count"] == 1
    assert db.query(KBAudit).filter(KBAudit.op == "review_queue").count() == 1


def test_admin_review_update_promotes_claim_and_records_external_evidence(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add_all(
        [
            KBDocument(
                doc_id="claim:c_review_target",
                doc_type="claim",
                entity_type="gene",
                entity_id="MTHFR",
                title="Needs reviewer action",
                evidence_level="C",
                confidence=0.61,
                metadata_json={
                    "review_status": "needs_review",
                    "candidate_duplicates": ["claim:c_old"],
                },
                sources=["dedao:test"],
            ),
            KBAudit(
                doc_id="claim:c_review_target",
                op="feedback_disagree",
                actor=f"user:{user.id}",
                diff={"reason": "需要二源"},
            ),
        ]
    )
    db.commit()

    response = client.patch(
        "/api/v1/admin/knowledge/claim/claim:c_review_target/review",
        headers=headers,
        json={
            "review_status": "reviewed",
            "evidence_level": "B",
            "confidence": 0.78,
            "clear_candidate_duplicates": True,
            "resolve_feedback": True,
            "note": "补充 PubMed 二源后通过",
            "external_source": {
                "kind": "research",
                "source": "pubmed:19033271",
                "title": "MTHFR and folate metabolism",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    claim = payload["claim"]
    assert claim["doc_id"] == "claim:c_review_target"
    assert claim["evidence_level"] == "B"
    assert claim["confidence"] == 0.78
    assert claim["metadata"]["review_status"] == "reviewed"
    assert claim["metadata"]["candidate_duplicates"] == []
    assert claim["metadata"]["feedback_resolution"]["resolved"] is True
    assert claim["metadata"]["external_sources"][0]["source"] == "pubmed:19033271"
    assert claim["metadata"]["external_sources"][0]["review_status"] == "reviewed"
    assert claim["sources"] == ["dedao:test", "pubmed:19033271"]

    audit_ops = [
        row.op
        for row in db.query(KBAudit)
        .filter(KBAudit.doc_id == "claim:c_review_target")
        .order_by(KBAudit.id.asc())
        .all()
    ]
    assert audit_ops == ["feedback_disagree", "review_update"]


def test_admin_review_update_archives_claim_from_serving_detail(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.add(
        KBDocument(
            doc_id="claim:c_archive_target",
            doc_type="claim",
            entity_type="condition",
            entity_id="metabolic-health",
            title="Archive target",
            evidence_level="C",
            confidence=0.5,
            metadata_json={"review_status": "needs_review"},
            sources=["dedao:test"],
        )
    )
    db.commit()

    response = client.patch(
        "/api/v1/admin/knowledge/claim/claim:c_archive_target/review",
        headers=headers,
        json={"review_status": "archived", "note": "重复且证据不足"},
    )

    assert response.status_code == 200
    assert response.json()["claim"]["is_archived"] is True
    stored = db.get(KBDocument, "claim:c_archive_target")
    assert stored is not None
    assert stored.is_archived is True
    assert (stored.metadata_json or {})["review_status"] == "archived"
    assert db.query(KBAudit).filter(KBAudit.op == "review_update").count() == 1

    detail = client.get("/api/v1/knowledge/claim/claim:c_archive_target", headers=headers)
    assert detail.status_code == 404


def test_admin_reindex_refreshes_search_text_and_content_hash(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    _seed_phase0_knowledge(db)

    response = client.post("/api/v1/admin/knowledge/reindex", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    # reindex 端点改为返回 report 结构(run_system_kb_reindex_report),文档数在 reindex 子对象里
    assert payload["reindex"]["documents"] == 2
    refreshed = db.get(KBDocument, "entity:gene:MTHFR")
    assert refreshed.tsv is not None
    assert "MTHFR" in refreshed.tsv
    assert refreshed.content_hash is not None


def test_postgres_reindex_statement_writes_tsvector_not_plain_text():
    statement = _build_postgres_reindex_statement(
        doc_id="entity:gene:MTHFR",
        searchable="MTHFR participates in folate metabolism",
        content_hash="abc123",
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "to_tsvector" in compiled
    assert "tsv=to_tsvector" in compiled
    assert "content_hash" in compiled


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
