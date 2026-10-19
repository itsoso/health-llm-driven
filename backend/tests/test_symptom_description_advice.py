"""Synthetic symptom follow-ups are answer goals, not personal record queries."""
import pytest

from app.services.agent_kernel.current_input_advice_scope import (
    current_input_advice_instructions, is_current_input_advice, local_advice_response,
)
from tests.test_agent_read_plan_binding import decide

DESCRIPTION = '有嗳气的感觉，大便正常，吃饭两个小时后开始疼'


@pytest.mark.parametrize('message', [
    DESCRIPTION, '我有反酸，饭后1小时胃疼，怎么办？',
    '大便正常 餐后半小时开始腹痛 有打嗝的感觉',
    '我胃疼，怎么办？', '腹痛，恶心，怎么回事？', '肚子疼，大便黑色，需要就医吗？',
    '有嗳气的感觉，吃完饭四个小时后开始痛。',
])
def test_symptom_follow_up_is_current_input_advice(message):
    assert is_current_input_advice(message)
    assert local_advice_response(message)[0] == 'gastrointestinal_symptom_advice'
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


@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
async def test_gateway_independently_rejects_forced_personal_read(mode):
    from dataclasses import replace
    from tests.test_agent_read_plan_binding import snapshot
    from app.services.agent_kernel.tool_gateway import ToolGateway
    from app.services.agent_kernel.types import ToolExecutionRequest
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    gateway = ToolGateway(replace(snapshot(DESCRIPTION), policy_mode=mode))
    result = await gateway.execute(ToolExecutionRequest(
        tool_name='health_query', arguments={'dimension': 'diet'}), dispatch)
    assert result.decision.reason == 'current_input_advice_read_not_needed'
    assert result.decision.action == 'block'
    assert not calls


def test_symptom_turn_buffers_unreviewed_medical_output():
    from app.services.guidance_validator import requires_medical_evidence_boundary
    assert requires_medical_evidence_boundary(DESCRIPTION)


@pytest.mark.parametrize('draft', [
    '你这就是胃溃疡。', '考虑已经确诊为胃炎。',
    '大便正常说明没有危险，不需要就医。', '可以排除消化道出血，放心在家休息。',
    'The pain is definitely an ulcer; you do not need medical care.',
])
def test_unreviewed_diagnosis_or_reassurance_cannot_be_released(draft):
    from app.services.agent_kernel.current_input_advice_scope import guard_current_input_answer
    answer, verified = guard_current_input_answer(DESCRIPTION, draft)
    assert not verified
    assert draft not in answer


@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('emergency', [False, True])
async def test_symptom_answer_never_invokes_model_or_health_context(
    db, auth_user_and_headers, monkeypatch, panel, emergency,
):
    import json
    from app.config import settings
    from app.services.agent_executor import AgentExecutor
    from tests.test_local_advice_response import forbid_heavy_work
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    forbid_heavy_work(executor, monkeypatch)
    monkeypatch.setattr(settings, 'health_evidence_runtime_enabled', True)
    message = '肚子疼，大便黑色，需要就医吗？' if emergency else DESCRIPTION
    events = [e async for e in executor.run_stream(user.id, message,
              extra_context=json.dumps({'multi_model': panel}))]
    done = events[-1]['data']
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert done['model_call_count'] == 0
    assert done['advice_kind'] == 'gastrointestinal_symptom_advice'
    answer = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert '未查询个人记录' in answer
    assert ('立即' in answer and '急救' in answer) if emergency else '疼痛部位' in answer
    assert not done['write_receipts']


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
    from tests.test_local_advice_response import forbid_heavy_work
    forbid_heavy_work(executor, monkeypatch)
    async def send():
        return [e async for e in executor.run_stream(
            user.id, DESCRIPTION, conversation_id=conversation.id,
            client_turn_id='symptom-follow-up', extra_context=json.dumps({'multi_model': panel}))]
    events = await send()
    done = events[-1]['data']
    public = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert public == db.get(AgentMessage, done['message_id']).content == local_advice_response(DESCRIPTION)[1]
    assert not done['write_receipts']
    replay = await send()
    assert replay[-1]['data']['message_id'] == done['message_id']
    assert done['model_call_count'] == 0
    assert ''.join(e['data']['content'] for e in replay if e.get('event') == 'token') == public
    assert db.query(AgentMessage).filter_by(conversation_id=conversation.id).count() == 4


@pytest.mark.parametrize('message', [DESCRIPTION, '腹痛，黑便，怎么办？'])
async def test_local_symptom_answer_preserves_owner_isolation(db, auth_user_and_headers, monkeypatch, message):
    from tests.test_local_advice_response import test_local_advice_cannot_use_another_users_conversation
    await test_local_advice_cannot_use_another_users_conversation(db, auth_user_and_headers, monkeypatch, message)


@pytest.mark.parametrize('message', [DESCRIPTION, '腹痛，黑便，怎么办？'])
async def test_local_symptom_answer_fails_loud_on_persistence_error(db, auth_user_and_headers, monkeypatch, message):
    from tests.test_local_advice_response import test_failed_persistence_cannot_emit_success_or_answer
    await test_failed_persistence_cannot_emit_success_or_answer(db, auth_user_and_headers, monkeypatch, message)
