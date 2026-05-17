import pytest
from datetime import date

from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.services.agent_executor import AgentExecutor
from tests.test_system_knowledge_phase0 import _seed_phase0_knowledge


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
