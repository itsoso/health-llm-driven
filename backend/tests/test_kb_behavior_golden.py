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
