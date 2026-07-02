"""Golden behavior tests for system-KB grounding.

These cases protect the product-level contract: KB evidence should ground
health advice, but should not leak unrelated Twin facts into simple recording
or unrelated analysis turns.
"""

from datetime import UTC, datetime

from app.models.system_knowledge import KBDocument, KBEdge
from app.services.agent_executor import _allow_twin_evidence_fallback
from app.services.system_knowledge_service import build_evidence_card_for_twin


def _seed_mthfr_claim(db):
    entity = KBDocument(
        doc_id="entity:gene:MTHFR",
        doc_type="entity",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR",
        summary="MTHFR 参与叶酸转化。",
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
        summary="C677T TT 用户可关注同型半胱氨酸、B12 与活性叶酸。",
        body="不用于诊断或治疗。",
        confidence=0.82,
        evidence_level="B",
        applies_when=["twin.genetics.MTHFR_C677T in ['CT', 'TT']"],
        recommends_lookup=["entity:supplement:5-MTHF", "entity:biomarker:Hcy"],
        sources=["dedao:qiuzilong-genetics-07", "pubmed:19033271"],
        last_confirmed=datetime(2026, 5, 16, tzinfo=UTC),
        decay_rate="normal",
        metadata_json={"review_status": "reviewed"},
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


def test_golden_record_intents_do_not_allow_twin_kb_fallback():
    blocked = [
        "记录晚餐：牛排150g、炸鸡50g",
        "删除午餐重复记录",
        "把今天体重录入 70.5kg",
    ]
    for message in blocked:
        assert _allow_twin_evidence_fallback(message) is False


def test_golden_relevant_advice_intents_allow_twin_kb_fallback():
    allowed = [
        "我最近应该怎么补叶酸？",
        "结合基因和体检给我一个补剂方案",
        "分析我的 MTHFR 风险",
    ]
    for message in allowed:
        assert _allow_twin_evidence_fallback(message) is True


def test_golden_twin_kb_filters_unrelated_record_analysis(db):
    _seed_mthfr_claim(db)
    card = build_evidence_card_for_twin(
        db,
        {"genetics": {"MTHFR_C677T": "TT"}},
        message="记录晚餐：牛排150g、炸鸡50g，帮我分析热量和蛋白是否合理",
    )

    assert card is None


def test_golden_twin_kb_keeps_relevant_folate_advice(db):
    _seed_mthfr_claim(db)
    card = build_evidence_card_for_twin(
        db,
        {"genetics": {"MTHFR_C677T": "TT"}},
        message="我最近应该怎么补叶酸？",
    )

    assert card is not None
    assert card["data"]["claims"][0]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"
    assert "叶酸" in card["data"]["retrieval"]["matched_message_terms"]


def _seed_chronic_claims(db, *, hba1c_copies: int = 1):
    """prod 实锤形状:HbA1c claim 标题含泛词"适合"、正文含"运动";BP claim 主题=血压。"""
    entity_bp = KBDocument(
        doc_id="entity:biomarker:BP",
        doc_type="entity",
        entity_type="biomarker",
        entity_id="BP",
        title="血压",
        summary="血压风险分层与家庭监测。",
        confidence=0.9,
        evidence_level="B",
        sources=["dedao:chronic-01"],
        last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
        decay_rate="slow",
        metadata_json={"review_status": "reviewed"},
    )
    entity_hba1c = KBDocument(
        doc_id="entity:biomarker:HbA1c",
        doc_type="entity",
        entity_type="biomarker",
        entity_id="HbA1c",
        title="HbA1c",
        summary="糖化血红蛋白反映 8-12 周血糖。",
        confidence=0.9,
        evidence_level="B",
        sources=["dedao:chronic-01"],
        last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
        decay_rate="slow",
        metadata_json={"review_status": "reviewed"},
    )
    claim_bp = KBDocument(
        doc_id="claim:c_bp_home_trend",
        doc_type="claim",
        entity_type="biomarker",
        entity_id="BP",
        title="血压建议优先基于家庭血压趋势",
        summary="单次偏高不应直接推导为诊断或用药建议。",
        body="不用于诊断或治疗。",
        confidence=0.8,
        evidence_level="B",
        applies_when=["twin.labs.systolic_bp >= 130"],
        sources=["dedao:chronic-01"],
        last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
        decay_rate="normal",
        metadata_json={"review_status": "reviewed"},
    )
    docs = [entity_bp, entity_hba1c, claim_bp]
    for idx in range(hba1c_copies):
        docs.append(
            KBDocument(
                doc_id=f"claim:c_dedao_{idx}_hba1c_feedback",
                doc_type="claim",
                entity_type="biomarker",
                entity_id="HbA1c",
                title="HbA1c 适合作为 8-12 周复查闭环",
                summary="生活方式调整(饮食与运动)后应以 HbA1c 复查验证效果。",
                body="运动与饮食干预的效果评估周期为 8-12 周。不用于诊断。",
                confidence=0.8,
                evidence_level="B",
                applies_when=["twin.labs.HbA1c >= 5.7"],
                sources=[f"dedao:chronic-{idx}"],
                last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
                decay_rate="normal",
                metadata_json={"review_status": "reviewed"},
            )
        )
    db.add_all(docs)
    db.flush()
    for doc in docs:
        if doc.doc_type != "claim":
            continue
        src = entity_bp if doc.entity_id == "BP" else entity_hba1c
        db.add(
            KBEdge(
                src_doc_id=src.doc_id,
                dst_doc_id=doc.doc_id,
                relation="has_claim",
                confidence=0.9,
                source_claim_id=doc.doc_id,
            )
        )
    db.commit()


_CHRONIC_TWIN = {"labs": {"systolic_bp": 135, "HbA1c": 5.9}}


def test_golden_generic_exercise_question_pulls_no_chronic_card(db):
    """prod 回归:"适合"中 HbA1c 标题、"运动"中正文 → 运动问题曾弹血压/HbA1c 卡。

    泛功能词已入 stop-list,正文命中不再作准入 → 无关慢病卡不出现。
    """
    _seed_chronic_claims(db, hba1c_copies=3)
    card = build_evidence_card_for_twin(db, _CHRONIC_TWIN, message="今天我适合怎样的运动？")
    assert card is None


def test_golden_bp_question_keeps_bp_claim_with_aligned_entity(db):
    _seed_chronic_claims(db, hba1c_copies=1)
    card = build_evidence_card_for_twin(db, _CHRONIC_TWIN, message="我的血压趋势有什么变化？")

    assert card is not None
    claims = card["data"]["claims"]
    assert claims[0]["doc_id"] == "claim:c_bp_home_trend"
    assert "血压" in card["data"]["retrieval"]["matched_message_terms"]
    # entity 必须与排序后首条 claim 同主题(曾错位:标题"血压"配 HbA1c claims)
    assert card["data"]["entity"].get("entity_id") == claims[0].get("entity_id")


def test_golden_duplicate_dedao_claims_collapse_to_one(db):
    """dedao 多批次导入产生同题 claim ×N → 卡内按标题去重,"3 条证据"不再是同一条×3。"""
    _seed_chronic_claims(db, hba1c_copies=3)
    card = build_evidence_card_for_twin(db, _CHRONIC_TWIN, message="HbA1c 复查节奏应该是多久？")

    assert card is not None
    titles = [c.get("title") for c in card["data"]["claims"]]
    assert len(titles) == len(set(titles))
    assert titles.count("HbA1c 适合作为 8-12 周复查闭环") == 1
