import pytest
from datetime import UTC, date, datetime

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.models.system_knowledge import KBDocument, KBEdge
from app.services.agent_executor import AgentExecutor
from tests.test_system_knowledge_phase0 import _seed_phase0_knowledge


def _seed_9p21_knowledge(db):
    entity = KBDocument(
        doc_id="entity:gene:9p21",
        doc_type="entity",
        entity_type="gene",
        entity_id="9p21",
        title="9p21 心血管风险位点",
        summary="9p21 只适合作为冠心病风险沟通线索，必须锚定临床和生活方式数据。",
        confidence=0.72,
        evidence_level="C",
        sources=["dedao:qiuzilong-genetics-20"],
        last_confirmed=datetime(2026, 5, 17, tzinfo=UTC),
        decay_rate="normal",
    )
    claim = KBDocument(
        doc_id="claim:c_9p21_cardiovascular_labs_lifestyle_boundary",
        doc_type="claim",
        entity_type="gene",
        entity_id="9p21",
        title="9p21 心血管风险解读必须锚定临床和生活方式指标",
        summary="9p21 AA/AG 解读必须锚定血脂、血压、血糖、炎症、肝肾功能和恢复状态；不能只凭基因给出确定补剂方案。",
        body="9p21/rs10757274 AA 或 AG 只能作为冠心病、动脉粥样硬化风险沟通线索。",
        confidence=0.68,
        evidence_level="C",
        applies_when=[
            "twin.genetics.9p21 in ['AA', 'AG']",
            "twin.genetics.rs10757274 in ['AA', 'AG']",
        ],
        recommends_lookup=["entity:gene:9p21", "entity:biomarker:LDL-C", "entity:biomarker:BP"],
        sources=["dedao:qiuzilong-genetics-20"],
        last_confirmed=datetime(2026, 5, 17, tzinfo=UTC),
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


@pytest.mark.asyncio
async def test_agent_stream_injects_system_knowledge_into_model_prompt(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    executor = AgentExecutor(db)
    captured_messages = []

    async def fake_call_llm(messages, tools):
        captured_messages.extend(messages)
        return "已结合系统知识库回答。"

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="我 MTHFR-TT 该注意什么？",
            user_auth_token=None,
        )
    ]

    assert events[-1]["event"] == "done"
    system_prompt = captured_messages[0]["content"]
    assert "## 系统知识库相关条目" in system_prompt
    assert "claim:c_mthfr_c677t_hcy_folate_boundary" in system_prompt
    assert "具体饮食/补剂/运动建议" in system_prompt
    assert "claim_id" in system_prompt
    assert "不替代医生诊断" in system_prompt
    assert "系统知识库" in events[-1]["data"]["sources_used"]


@pytest.mark.asyncio
async def test_agent_stream_injects_system_knowledge_from_user_twin(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    profile = GeneticProfile(
        user_id=user.id,
        test_provider="wegene",
        test_date=date(2026, 5, 1),
    )
    db.add(profile)
    db.flush()
    db.add(
        GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            rsid="rs1801133",
            category="nutrition",
            gene_name="MTHFR",
            variant_name="C677T",
            genotype="TT",
            result_label="叶酸代谢显著减弱",
            risk_level="high",
            variant_nature="risk",
        )
    )
    db.commit()

    executor = AgentExecutor(db)
    captured_messages = []

    async def fake_call_llm(messages, tools):
        captured_messages.extend(messages)
        return "已结合用户 Twin 和系统知识库回答。"

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="我最近应该怎么补叶酸？",
            user_auth_token=None,
        )
    ]

    assert events[-1]["event"] == "done"
    system_prompt = captured_messages[0]["content"]
    assert "## 系统知识库相关条目" in system_prompt
    assert "claim:c_mthfr_c677t_hcy_folate_boundary" in system_prompt
    assert "系统知识库" in events[-1]["data"]["sources_used"]
    cards = events[-1]["data"]["cards"]
    assert cards
    assert cards[0]["type"] == "system_knowledge_evidence"
    assert cards[0]["data"]["claims"][0]["doc_id"] == "claim:c_mthfr_c677t_hcy_folate_boundary"


@pytest.mark.asyncio
async def test_agent_stream_does_not_attach_twin_kb_card_for_pure_record_intent(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    profile = GeneticProfile(
        user_id=user.id,
        test_provider="wegene",
        test_date=date(2026, 5, 1),
    )
    db.add(profile)
    db.flush()
    db.add(
        GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            rsid="rs1801133",
            category="nutrition",
            gene_name="MTHFR",
            variant_name="C677T",
            genotype="TT",
            result_label="叶酸代谢显著减弱",
            risk_level="high",
            variant_nature="risk",
        )
    )
    db.commit()

    executor = AgentExecutor(db)
    captured_messages = []

    async def fake_call_llm(messages, tools):
        captured_messages.extend(messages)
        return "已记录晚餐。"

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录晚餐：牛排150g、炸鸡50g、炸红薯50g",
            user_auth_token=None,
        )
    ]

    assert events[-1]["event"] == "done"
    assert "## 系统知识库相关条目" not in captured_messages[0]["content"]
    assert "系统知识库" not in events[-1]["data"]["sources_used"]
    assert events[-1]["data"]["cards"] == []


@pytest.mark.asyncio
async def test_agent_stream_does_not_attach_unrelated_twin_kb_card_for_diet_record_analysis(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    _seed_phase0_knowledge(db)
    profile = GeneticProfile(
        user_id=user.id,
        test_provider="wegene",
        test_date=date(2026, 5, 1),
    )
    db.add(profile)
    db.flush()
    db.add(
        GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            rsid="rs1801133",
            category="nutrition",
            gene_name="MTHFR",
            variant_name="C677T",
            genotype="TT",
            result_label="叶酸代谢显著减弱",
            risk_level="high",
            variant_nature="risk",
        )
    )
    db.commit()

    executor = AgentExecutor(db)
    captured_messages = []

    async def fake_call_llm(messages, tools):
        captured_messages.extend(messages)
        return "已记录晚餐，并分析了热量和蛋白。"

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录晚餐：牛排150g、炸鸡50g、炸红薯50g，帮我分析热量和蛋白是否合理",
            user_auth_token=None,
        )
    ]

    assert events[-1]["event"] == "done"
    assert "claim:c_mthfr_c677t_hcy_folate_boundary" not in captured_messages[0]["content"]
    assert "系统知识库" not in events[-1]["data"]["sources_used"]
    assert events[-1]["data"]["cards"] == []


@pytest.mark.asyncio
async def test_agent_stream_9p21_supplement_question_injects_boundary_claim(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    _seed_9p21_knowledge(db)
    executor = AgentExecutor(db)
    captured_messages = []

    async def fake_call_llm(messages, tools):
        captured_messages.extend(messages)
        return "已基于 claim:c_9p21_cardiovascular_labs_lifestyle_boundary 保留边界。"

    executor._call_llm = fake_call_llm

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="针对我的 9p21 基因 (AA)，补剂怎么做？",
            user_auth_token=None,
        )
    ]

    system_prompt = captured_messages[0]["content"]
    assert "claim:c_9p21_cardiovascular_labs_lifestyle_boundary" in system_prompt
    assert "不能只凭基因给出确定补剂方案" in system_prompt
    assert "claim_id" in system_prompt
    cards = events[-1]["data"]["cards"]
    assert cards[0]["data"]["claims"][0]["doc_id"] == "claim:c_9p21_cardiovascular_labs_lifestyle_boundary"
