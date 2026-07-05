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


# ── prod 实锤 (msg 5552):机器序列化的"基因发现"块 (CFTR, reviewed KB 无此 claim)
#    却弹出"血压"证据卡。根因 2 处:①样板/脚手架词 (必须/用药/边界/gene_name/…) 把
#    无关慢病 claim 钓进卡 ②卡 entity 恒取 entities[0]=用户首个 lab (血压),与 claims
#    主题不符。以下三组测试钉死修复不回潮。

def _seed_fiber_intervention_claim(db):
    """膳食纤维 intervention claim —— 主题词"纤维"会与"囊性纤维化"的碎片"纤维"同形。"""
    entity = KBDocument(
        doc_id="entity:intervention:fiber-intake",
        doc_type="entity",
        entity_type="intervention",
        entity_id="fiber-intake",
        title="膳食纤维摄入",
        summary="膳食纤维支持血糖与血脂管理。",
        confidence=0.85,
        evidence_level="B",
        sources=["dedao:nutrition-01"],
        last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
        decay_rate="slow",
        metadata_json={"review_status": "reviewed"},
    )
    claim = KBDocument(
        doc_id="claim:c_fiber_glycemic_lipid_support",
        doc_type="claim",
        entity_type="intervention",
        entity_id="fiber-intake",
        title="膳食纤维摄入:膳食纤维支持血糖和血脂管理",
        summary="逐步增加膳食纤维有助于血糖和血脂管理。",
        body="不用于诊断或治疗。",
        confidence=0.8,
        evidence_level="B",
        applies_when=["twin.labs.HbA1c >= 5.7"],
        sources=["dedao:nutrition-01"],
        last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
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


# founder 真实触发文案的最小化复刻:纯样板指令 + 结构化基因发现块 (英文脚手架)。
_CFTR_GENOMIC_FINDING_MESSAGE = (
    "请基于我的真实基因上下文，分析这个基因发现，并给出可执行建议。"
    "注意：不要把基因风险当成诊断，不要直接给用药决定；请列出不确定性边界、"
    "需要结合的化验/症状/生活方式数据，以及未来 30 天可执行动作。"
    "基因发现：- 标题：CFTR · CFTR 相关疾病筛查位点 - 分类：disease_risk "
    "- rsid：rs121908763 - 基因型：GG - 结果：CFTR 风险等位纯合筛查阳性，"
    "需临床测序/汗氯确认 - 风险等级：high requires_confirmation "
    "变异与囊性纤维化、支气管扩张有关。结果必须复核。"
    "genomic_finding category=disease_risk clinical_status evidence_level gene_name id"
)


def test_golden_genomic_finding_boilerplate_pulls_no_chronic_card(db):
    """CFTR 基因发现块 (KB 无 CFTR claim) 绝不因样板/脚手架词弹出无关慢病卡。"""
    _seed_chronic_claims(db, hba1c_copies=1)
    _seed_fiber_intervention_claim(db)
    card = build_evidence_card_for_twin(
        db, _CHRONIC_TWIN, message=_CFTR_GENOMIC_FINDING_MESSAGE
    )
    assert card is None


def test_golden_card_entity_always_matches_top_claim_subject(db):
    """卡 entity 必须是首条 claim 的自身主题实体,绝不错位到 entities[0]。

    尿酸问句下,即使 BP 生标实体排在实体池首位,卡标题也必须是尿酸主题,不是血压。
    """
    _seed_chronic_claims(db, hba1c_copies=1)
    # 追加一条尿酸 claim + 实体,条件命中同一 twin。
    uric_entity = KBDocument(
        doc_id="entity:condition:hyperuricemia-risk",
        doc_type="entity",
        entity_type="condition",
        entity_id="hyperuricemia-risk",
        title="尿酸风险",
        summary="尿酸偏高的生活方式管理。",
        confidence=0.85,
        evidence_level="B",
        sources=["dedao:chronic-uric"],
        last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
        decay_rate="slow",
        metadata_json={"review_status": "reviewed"},
    )
    uric_claim = KBDocument(
        doc_id="claim:c_uric_lifestyle",
        doc_type="claim",
        entity_type="condition",
        entity_id="hyperuricemia-risk",
        title="尿酸风险:尿酸偏高需结合酒精、含糖饮料、体重",
        summary="尿酸偏高优先看生活方式而非直接用药。",
        body="不用于诊断或治疗。",
        confidence=0.82,
        evidence_level="B",
        applies_when=["twin.labs.HbA1c >= 5.7"],
        sources=["dedao:chronic-uric"],
        last_confirmed=datetime(2026, 6, 1, tzinfo=UTC),
        decay_rate="normal",
        metadata_json={"review_status": "reviewed"},
    )
    db.add_all([uric_entity, uric_claim])
    db.flush()
    db.add(
        KBEdge(
            src_doc_id=uric_entity.doc_id,
            dst_doc_id=uric_claim.doc_id,
            relation="has_claim",
            confidence=0.9,
            source_claim_id=uric_claim.doc_id,
        )
    )
    db.commit()

    card = build_evidence_card_for_twin(db, _CHRONIC_TWIN, message="分析我的尿酸偏高")
    assert card is not None
    claims = card["data"]["claims"]
    assert claims[0]["entity_id"] == "hyperuricemia-risk"
    # 卡标题实体 = 首条 claim 的主题实体 (尿酸风险),不是 entities 池首位的血压。
    assert card["data"]["entity"].get("entity_id") == claims[0].get("entity_id")
    assert card["data"]["entity"].get("title") == "尿酸风险"


def test_golden_fiber_fragment_vs_real_fiber_question(db):
    """区分"囊性纤维化"里的碎片"纤维"(不弹膳食纤维卡)与真问膳食纤维(要弹卡)。"""
    _seed_chronic_claims(db, hba1c_copies=1)
    _seed_fiber_intervention_claim(db)

    # 碎片:纤维化 共现 → "纤维" 被判子串碎片丢弃 → 不误弹膳食纤维卡。
    frag = build_evidence_card_for_twin(db, _CHRONIC_TWIN, message="囊性纤维化是什么？")
    assert frag is None

    # 真问膳食纤维:主题即纤维 → 卡正常出。
    real = build_evidence_card_for_twin(db, _CHRONIC_TWIN, message="我需要多补充膳食纤维吗？")
    assert real is not None
    assert real["data"]["entity"].get("entity_id") == "fiber-intake"
