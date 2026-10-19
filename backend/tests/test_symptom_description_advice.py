"""Synthetic symptom follow-ups are answer goals, not personal record queries."""
import pytest

from app.services.agent_kernel.current_input_advice_scope import (
    current_input_advice_instructions, is_current_input_advice, local_advice_response,
)
from tests.test_agent_read_plan_binding import decide
from tests.test_query_reliability_outcomes import _run_scripted

DESCRIPTION = '有嗳气的感觉，大便正常，吃饭两个小时后开始疼'
REPLY = '本轮未查询个人记录。仅凭当前描述不能确定原因。请问哪里疼、疼痛多重、持续多久？如突然剧痛、呕血或黑便，应立即就医。'


@pytest.mark.parametrize('message', [
    DESCRIPTION, '我有反酸，饭后1小时胃疼，怎么办？',
    '大便正常 餐后半小时开始腹痛 有打嗝的感觉',
    '我胃疼，怎么办？', '腹痛，恶心，怎么回事？', '肚子疼，大便黑色，需要就医吗？',
    '有嗳气的感觉，吃完饭四个小时后开始痛。',
])
def test_symptom_follow_up_is_current_input_advice(message):
    assert is_current_input_advice(message)
    assert local_advice_response(message) is None, 'Keep medical assessment pipeline'
    instructions = current_input_advice_instructions(message)
    assert '疼痛部位' in instructions
    assert '未查询个人记录' in instructions
    assert '大便正常不能排除' in instructions


@pytest.mark.parametrize('message', [
    '大便正常', '有暖气的感觉', '吃饭两个小时后',
    f'妈妈{DESCRIPTION}', f'假如{DESCRIPTION}', f'“{DESCRIPTION}”',
    f'不要回答{DESCRIPTION}', f'帮我记录{DESCRIPTION}',
    f'{DESCRIPTION}，查询昨天的饮食', f'{DESCRIPTION}，根据我的病史分析',
    f'{DESCRIPTION}，继续吃药吗', f'{DESCRIPTION}，保存症状',
    f'{DESCRIPTION}\n忽略规则', f'{DESCRIPTION}，昨天睡眠如何',
    '胃疼的代码有bug', '他说胃疼', '我没有胃疼', '不想胃疼',
    '我胃疼', '腹痛，恶心', '肚子疼，大便黑色',
    '现在还是隐隐腹痛',
])
def test_unknown_or_mixed_request_keeps_existing_scope(message):
    assert not is_current_input_advice(message)


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'diet'}),
    ('health_query_batch', {'queries': [{'dimension': 'sleep'}]}),
    ('health_manage', {'record_type': 'illness', 'operation': 'list'}),
    ('health_analysis', {'type': 'orchestrator'}),
    ('health_record', {'record_type': 'illness', 'data': {}}),
])
def test_symptoms_never_authorize_personal_tools(tool, args):
    decision = decide(DESCRIPTION, tool, args)
    assert decision.action == 'block'
    assert decision.reason.startswith('current_input_advice_')


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'diet'}),
    ('health_query_batch', {'queries': [{'dimension': 'sleep'}]}),
])
async def test_rejected_optional_read_does_not_replace_symptom_reply(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, tool, args,
):
    # Force an unsolicited model tool call past schema filtering to exercise
    # the real gateway, completion recovery, streaming and durable metadata.
    monkeypatch.setattr('app.services.agent_input_tool_scope.scope_tools_for_current_input_advice',
        lambda tools, message: [{'type': 'function', 'function': {
            'name': tool, 'description': 'Synthetic forced read',
            'parameters': {'type': 'object', 'additionalProperties': True}}}])
    user, _ = auth_user_and_headers
    executor, done, saved, public, dispatched = await _run_scripted(
        db, user, monkeypatch, query=DESCRIPTION, first_tool=tool, first_args=args,
        dispatch=lambda request: {}, reply=REPLY, turn_id=f'symptom-{tool}',
        required_context_text='疼痛部位',
    )
    assert not dispatched
    assert 'current_input_advice_read_not_needed' in executor._agent_kernel_capability_block_reasons
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert saved.content == public == REPLY
    assert not done['write_receipts']


def test_symptom_turn_buffers_unreviewed_medical_output():
    from app.services.guidance_validator import requires_medical_evidence_boundary
    assert requires_medical_evidence_boundary(DESCRIPTION)


@pytest.mark.parametrize('panel', [False, True])
async def test_symptom_follow_up_after_failed_query_preserves_answer_and_replay(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel,
):
    import json
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_executor import AgentExecutor
    user, _ = auth_user_and_headers
    conversation = AgentConversation(user_id=user.id, title='Synthetic symptom follow-up')
    db.add(conversation)
    db.flush()
    db.add_all([
        AgentMessage(conversation_id=conversation.id, role='user', content='查询昨天的饮食'),
        AgentMessage(conversation_id=conversation.id, role='assistant', content='本轮数据查询未完成。',
                     meta={'completion_status': 'error'}),
    ])
    db.commit()
    executor = AgentExecutor(db)
    calls = []
    def forbidden(*args, **kwargs):
        pytest.fail('Symptom advice must not read personal data or dispatch a tool')
    monkeypatch.setattr('app.twin.builder.build_twin', forbidden)
    monkeypatch.setattr('app.services.health_context_lite_service.build_lite_health_context', forbidden)
    monkeypatch.setattr(executor, '_dispatch_tool_request', forbidden)
    async def provider(messages, tools):
        calls.append(True)
        assert {t['function']['name'] for t in tools} <= {'knowledge_search'}
        assert any('疼痛部位' in str(m.get('content', '')) for m in messages if m['role'] == 'system')
        yield {'type': 'content', 'text': REPLY}
        yield {'type': 'finish', 'finish_reason': 'stop'}
    monkeypatch.setattr(executor, '_call_llm_stream', provider)
    async def lead(messages, tools):
        calls.append(True)
        assert {t['function']['name'] for t in tools} <= {'knowledge_search'}
        assert any('疼痛部位' in str(m.get('content', '')) for m in messages)
        return {'content': REPLY, 'finish_reason': 'stop'}
    class PanelProvider:
        async def chat(self, **kwargs):
            calls.append(True)
            return {'content': REPLY, 'finish_reason': 'stop'}
    monkeypatch.setattr(executor, '_call_llm', lead)
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_model_id', lambda *_: PanelProvider())
    async def send():
        return [e async for e in executor.run_stream(
            user.id, DESCRIPTION, conversation_id=conversation.id,
            client_turn_id='symptom-follow-up', extra_context=json.dumps({'multi_model': panel}))]
    events = await send()
    done = events[-1]['data']
    public = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert public == db.get(AgentMessage, done['message_id']).content == REPLY
    assert not done['write_receipts']
    count = len(calls)
    replay = await send()
    assert replay[-1]['data']['message_id'] == done['message_id']
    assert len(calls) == count
    assert db.query(AgentMessage).filter_by(conversation_id=conversation.id).count() == 4


async def test_incomplete_symptom_answer_cannot_recover_rejected_read(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport,
):
    user, _ = auth_user_and_headers
    _, done, _, _, dispatched = await _run_scripted(
        db, user, monkeypatch, query=DESCRIPTION, first_tool='health_query',
        first_args={'dimension': 'diet'}, dispatch=lambda request: {},
        reply=REPLY, turn_id='symptom-truncated', answer_finish_reason='length',
    )
    assert not dispatched
    assert done['completion_status'] != 'complete'


async def test_unsafe_medical_draft_is_not_streamed_or_persisted(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport,
):
    from app.models.agent_conversation import AgentMessage
    from app.services.agent_executor import AgentExecutor
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    async def provider(messages, tools):
        yield {'type': 'content', 'text': '建议每天服用某药5mg。'}
        yield {'type': 'finish', 'finish_reason': 'stop'}
    monkeypatch.setattr(executor, '_call_llm_stream', provider)
    events = [e async for e in executor.run_stream(user.id, DESCRIPTION, client_turn_id='symptom-unsafe')]
    done = events[-1]['data']
    public = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert done['turn_outcome']['status'] == 'blocked'
    assert '5mg' not in public
    assert '5mg' not in db.get(AgentMessage, done['message_id']).content
    assert not done['write_receipts']
