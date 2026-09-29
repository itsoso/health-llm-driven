"""Synthetic recovery advice must complete without reading personal records."""
import pytest

from tests.test_agent_read_plan_binding import decide, snapshot
from tests.test_query_reliability_outcomes import _run_scripted

QUERY = '我有慢性鼻炎(活动期)+过敏性鼻炎症状，今天该怎么休息和恢复？'
REPLY = '仅根据你当前描述，今天以休息为主；如果症状加重，请及时就医。'


@pytest.fixture(autouse=True)
def _isolate_transport(isolated_agent_protocol_transport):
    """Use real Pi transport, synthetic providers, and no external network."""


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'sleep'}),
    ('health_query_batch', {'queries': [{'dimension': 'sleep'}]}),
    ('health_manage', {'record_type': 'illness', 'operation': 'list'}),
    ('health_analysis', {'type': 'orchestrator', 'question': '今天如何休息？'}),
    ('analyze_recovery', {}),
])
@pytest.mark.parametrize("expose_tool", [False, True])
@pytest.mark.asyncio
async def test_optional_personal_read_cannot_abort_recovery_advice(
    db, auth_user_and_headers, monkeypatch, tool, args, expose_tool,
):
    if expose_tool:
        # Bypass schema filtering to prove the gateway independently rejects
        # model-forced calls and still allows the advice to complete.
        monkeypatch.setattr('app.services.agent_input_tool_scope.scope_tools_for_current_input_advice',
                            lambda tools, message: [{"type": "function", "function": {
                                "name": tool, "description": "Synthetic forced tool proposal",
                                "parameters": {"type": "object", "additionalProperties": True},
                            }}])
    user, _ = auth_user_and_headers
    executor, done, persisted, public, dispatched = await _run_scripted(
        db, user, monkeypatch, query=QUERY, first_tool=tool, first_args=args,
        dispatch=lambda request: {}, reply=REPLY, turn_id=f'advice-{tool}', required_context_text='本轮只依据用户当前输入',
    )
    assert not dispatched
    assert persisted.content == public == REPLY
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['status'] == 'complete'
    if expose_tool:
        assert 'current_input_advice_read_not_needed' in executor._agent_kernel_capability_block_reasons, 'Keep denial audit'
    assert not done['write_receipts']


@pytest.mark.asyncio
async def test_truncated_advice_cannot_recover_a_rejection(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    _, done, _, _, dispatched = await _run_scripted(
        db, user, monkeypatch, query=QUERY, first_tool='health_query',
        first_args={'dimension': 'sleep'}, dispatch=lambda request: {},
        reply='未完成的建议', turn_id='advice-truncated', answer_finish_reason='length',
    )
    assert not dispatched
    assert done['completion_status'] != 'complete'


@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
@pytest.mark.asyncio
async def test_advice_gateway_rejects_hidden_personal_tools_in_all_modes(mode):
    from dataclasses import replace
    from app.services.agent_kernel.tool_gateway import ToolGateway
    from app.services.agent_kernel.types import ToolExecutionRequest
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    gateway = ToolGateway(replace(snapshot(QUERY), policy_mode=mode))
    result = await gateway.execute(ToolExecutionRequest(tool_name='analyze_recovery', arguments={}), dispatch)
    assert result.decision.action == 'block'
    assert not calls


def test_advice_cannot_authorize_writes():
    assert decide(QUERY, 'health_record', {'record_type': 'weight', 'data': {'weight': 70}}).action == 'block'


def test_current_input_advice_does_not_preload_personal_health_context(db, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    calls = []
    monkeypatch.setattr('app.services.health_context_lite_service.build_lite_health_context',
                        lambda *a, **k: calls.append(True) or 'UNRELATED PERSONAL HISTORY')
    executor = AgentExecutor(db)
    executor._current_user_id = 41
    executor._current_turn_user_message = QUERY
    executor._start_agent_kernel_turn(user_id=41, message=QUERY, channel='typed')
    prompt = executor._build_system_prompt(41, 1, None, intent_query=QUERY)
    assert not calls
    assert 'UNRELATED PERSONAL HISTORY' not in prompt


@pytest.mark.asyncio
async def test_prior_actionable_context_not_in_current_input_reply(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ActionableReference
    user, _ = auth_user_and_headers
    marker = 'SYNTHETIC_PRIOR_MEAL_NOT_CURRENT_INPUT'
    monkeypatch.setattr('app.services.agent_conversation_service.AgentConversationService.build_actionable_references',
                        lambda *a, **k: (ActionableReference(kind='diet_daily_summary', source_message_id=99,
                            data={'record_date':'2026-01-01','meals':[{'meal_type':'breakfast','food_items':marker}]}),))
    seen = []
    async def provider(self, messages, tools):
        seen.extend(str(m.get('content','')) for m in messages)
        yield {'type':'content','text':'仅根据当前描述建议休息，不曾查询个人记录。'}
        yield {'type':'finish','finish_reason':'stop'}
    monkeypatch.setattr(AgentExecutor, '_call_llm_stream', provider)
    ex = AgentExecutor(db)
    events = [e async for e in ex.run_stream(user.id, '我有鼻炎症状，今天该怎么休息和恢复？', client_turn_id='review-old-context')]
    assert events[-1]['data']['completion_status'] == 'complete'
    assert not any(marker in m for m in seen), 'Previous personal meal data leaked into current-input-only provider messages'

def test_current_input_message_kb_miss_must_not_consult_twin(db, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    calls=[]
    monkeypatch.setattr('app.services.system_knowledge_service.build_evidence_card_for_message', lambda *a, **k: None)
    monkeypatch.setattr('app.twin.builder.build_twin', lambda *a, **k: calls.append('private_twin') or {})
    monkeypatch.setattr('app.services.system_knowledge_service.system_kb_twin_payload_from_health_twin', lambda *a, **k: {})
    monkeypatch.setattr('app.services.system_knowledge_service.build_evidence_card_for_twin', lambda *a, **k: {'type':'system_evidence','data':{'entity':{'title':'PRIOR_PRIVATE_ENTITY'},'claims':[{'title':'PRIOR_PERSONAL_CLAIM'}]}})
    ex=AgentExecutor(db)
    ex._start_agent_kernel_turn(user_id=41,message='我有鼻炎症状，今天该怎么休息和恢复？',channel='typed')
    prompt=ex._build_system_knowledge_prompt_context(41,'我有鼻炎症状，今天该怎么休息和恢复？')
    assert not calls, 'Current-input advice unexpectedly consults private Twin'
    assert 'PRIOR_PRIVATE_ENTITY' not in prompt


@pytest.mark.asyncio
async def test_current_input_reply_never_builds_twin_for_kb_or_citation(db, auth_user_and_headers, monkeypatch):
    calls = []
    def build_twin(*args, **kwargs):
        calls.append(True)
        return None
    monkeypatch.setattr('app.twin.builder.build_twin', build_twin)
    monkeypatch.setattr('app.services.system_knowledge_service.build_evidence_card_for_message', lambda *a, **k: None)
    user, _ = auth_user_and_headers
    await _run_scripted(db, user, monkeypatch, query=QUERY, first_tool='health_query',
        first_args={'dimension': 'sleep'}, dispatch=lambda request: {}, reply=REPLY, turn_id='no-background-twin')
    assert not calls, 'Advice cannot preload Twin via KB fallback or citation telemetry'


@pytest.mark.asyncio
async def test_current_input_advice_cannot_trigger_client_database_snapshot(db, auth_user_and_headers, monkeypatch):
    calls = []
    monkeypatch.setattr('app.services.agent_executor._extract_database_verification_instruction', lambda _: 'READ PRIOR DIET')
    monkeypatch.setattr('app.services.agent_executor._build_database_verification_snapshot', lambda *a, **k: calls.append(True) or 'OLD DIET')
    user, _ = auth_user_and_headers
    await _run_scripted(db, user, monkeypatch, query=QUERY, first_tool='health_query',
        first_args={'dimension': 'sleep'}, dispatch=lambda request: {}, reply=REPLY, turn_id='no-client-snapshot')
    assert not calls


@pytest.mark.asyncio
async def test_panel_current_input_advice_excludes_prior_cards_and_twin(db, auth_user_and_headers, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ActionableReference
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    marker = 'SYNTHETIC_OLD_MEAL'
    monkeypatch.setattr('app.services.agent_conversation_service.AgentConversationService.build_actionable_references',
        lambda *a, **k: (ActionableReference(kind='diet_daily_summary', source_message_id=99,
            data={'meals':[{'meal_type':'breakfast','food_items':marker}]}),))
    twin_calls = []
    monkeypatch.setattr('app.twin.builder.build_twin', lambda *a, **k: twin_calls.append(True))
    seen = []
    async def lead(messages, tools):
        seen.extend(str(m.get('content','')) for m in messages)
        assert {t['function']['name'] for t in tools} <= {'knowledge_search'}
        return {'content': REPLY, 'finish_reason': 'stop'}
    class Provider:
        async def chat(self, **kwargs):
            seen.extend(str(m.get('content','')) for m in kwargs['messages'])
            return {'content': REPLY, 'finish_reason': 'stop'}
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, '_call_llm', lead)
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_model_id', lambda *_: Provider())
    events = [e async for e in executor._run_multi_model_stream(user.id, QUERY, None, None, '{"multi_model":true}')]
    done = events[-1]['data']
    assert done['completion_status'] == 'complete'
    assert not twin_calls
    assert not any(marker in m for m in seen)
    assert db.get(AgentMessage, done['message_id']).meta['turn_outcome'] == done['turn_outcome']


@pytest.mark.asyncio
async def test_current_input_advice_ignores_opener_side_effects_and_opaque_context(db, auth_user_and_headers, monkeypatch):
    import json
    from app.services.agent_executor import AgentExecutor
    calls, seen = [], []
    marker = 'SYNTHETIC_UNRELATED_ENTRY_CONTEXT'
    monkeypatch.setattr('app.services.opener_quick_reply.apply_opener_quick_reply_context',
                        lambda *a, **k: calls.append(True) or marker)
    async def provider(self, messages, tools):
        seen.extend(str(m.get('content', '')) for m in messages)
        yield {'type': 'content', 'text': REPLY}
        yield {'type': 'finish', 'finish_reason': 'stop'}
    monkeypatch.setattr(AgentExecutor, '_call_llm_stream', provider)
    user, _ = auth_user_and_headers
    events = [e async for e in AgentExecutor(db).run_stream(user.id, QUERY,
        extra_context=json.dumps({'entry': 'conversation_opener_quick_reply', 'source': 'action_card_due',
                                  'action_card_id': 99, 'user_reply': '做到了', 'context': marker}))]
    assert events[-1]['data']['completion_status'] == 'complete'
    assert not calls
    assert not any(marker in value for value in seen)
