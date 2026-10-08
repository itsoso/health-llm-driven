"""Public completion must not rebuild private Twin context after answering."""
from datetime import datetime, timezone

import pytest

from app.services import agent_executor as ae
from app.twin.schema import HealthTwin, TwinMeta


@pytest.mark.asyncio
@pytest.mark.parametrize('message', [
    '杭州明天天气温度怎么样？空气质量。',
    '请介绍一下你自己',
])
async def test_public_completion_never_builds_personal_twin(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, message,
):
    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    builds, environment_reads = [], []
    reference_now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(executor, '_agent_kernel_reference_now', lambda: reference_now)
    monkeypatch.setattr(ae.settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(ae.settings, 'citation_anchor_shadow', True)

    def twin_sentinel(*args, **kwargs):
        builds.append(kwargs.get('use_cache'))
        return HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=datetime.now(timezone.utc)))

    monkeypatch.setattr('app.twin.builder.build_twin', twin_sentinel)

    async def environment(check_type, *, city, days):
        environment_reads.append(check_type)
        if check_type == 'forecast':
            return {'available': True, 'forecasts': [{'date': '2026-10-09', 'weather': '多云', 'temp_min': 18, 'temp_max': 24}]}
        assert check_type == 'air_quality'
        return {'available': True, 'aqi': 52, 'aqi_description': '良'}

    async def provider(messages, tools):
        yield {'type': 'content', 'text': '杭州明天18至24度。来源报告AQI52，良；观测时间未知。' if '杭州' in message else '我是小巴，可以协助整理健康记录。'}
        yield {'type': 'finish', 'finish_reason': 'stop'}

    monkeypatch.setattr(executor, '_read_environment_in_process', environment)
    monkeypatch.setattr(executor, '_call_llm_stream', provider)
    events = [e async for e in executor.run_stream(user.id, message, client_turn_id='public-completion-isolation')]
    done = events[-1]['data']
    assert done['completion_status'] == 'complete'
    assert builds == []
    assert not done.get('citation_anchor')
    assert not done.get('evidence_cards')
    assert environment_reads == (['forecast', 'air_quality'] if '杭州' in message else [])


def test_personal_evidence_and_citation_keep_their_twin_sources(db, monkeypatch):
    executor = ae.AgentExecutor(db)
    executor._public_task = None
    builds = []
    twin = HealthTwin(meta=TwinMeta(user_id=7, generated_at=datetime.now(timezone.utc)))
    def build(*args, **kwargs):
        builds.append(kwargs.get('use_cache'))
        return twin
    monkeypatch.setattr('app.twin.builder.build_twin', build)
    monkeypatch.setattr(ae.settings, 'citation_anchor_shadow', True)
    monkeypatch.setattr('app.services.system_knowledge_service.build_evidence_card_for_message', lambda *a, **k: None)
    evidence = {'type': 'system_knowledge_evidence', 'data': {'synthetic': True}}
    monkeypatch.setattr('app.services.system_knowledge_service.build_evidence_card_for_twin', lambda *a, **k: evidence)
    assert executor._build_system_knowledge_evidence_card(7, '我最近应该怎么补叶酸') is evidence
    assert ae._citation_anchor_shadow_meta(db, 7, '这次没有可用的个人数值。') is not None
    assert builds == [False, True]
