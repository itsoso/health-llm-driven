"""Synthetic everyday questions must not become required personal reads."""
import pytest

from app.services.agent_input_tool_scope import scope_tools_for_current_input_advice
from tests.test_agent_read_plan_binding import decide
from tests.test_query_reliability_outcomes import _run_scripted


BEDTIME = '给我一些健康的建议，现在是不是可以睡觉了？'
ACTION = '请解释今天这条行动：“复查:鼻炎(活动期)”。告诉我为什么现在做、怎么做，以及什么情况下不适合做。'


@pytest.fixture(autouse=True)
def _isolate_transport(isolated_agent_protocol_transport):
    """Synthetic provider and database; no real user records or network."""


@pytest.mark.parametrize('message', [BEDTIME, '现在可以睡觉了吗？', ACTION,
    '解释睡眠的一般性建议',
    ACTION.replace('鼻炎(活动期)', '胃炎(Hp阴性,胃体前壁)'),
])
def test_whole_advice_hides_personal_tools(message):
    tools = [{'function': {'name': name}} for name in ['health_query', 'health_manage', 'knowledge_search']]
    assert [t['function']['name'] for t in scope_tools_for_current_input_advice(tools, message)] == ['knowledge_search']


@pytest.mark.parametrize('message', [BEDTIME, ACTION])
@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'sleep'}),
    ('health_manage', {'record_type': 'illness', 'operation': 'list'}),
    ('analyze_recovery', {}),
])
def test_advice_rejects_optional_personal_reads_with_nonterminal_reason(message, tool, args):
    result = decide(message, tool, args)
    assert result.action == 'block'
    assert result.reason == 'current_input_advice_read_not_needed'


@pytest.mark.parametrize('message', [
    BEDTIME + '查询昨天的睡眠',
    '查询最近一周的睡眠，给我健康建议，现在可以睡觉了吗？',
    '妈妈现在可以睡觉了吗？', '现在吃安眠药就可以睡觉了吗？',
    '不要回答现在可以睡觉了吗？', '“现在可以睡觉了吗？”',
    ACTION + '并删除记录',
    ACTION.replace('鼻炎(活动期)', '鼻炎(查询妈妈的记录)'),
    ACTION.replace('鼻炎(活动期)', '鼻炎(增加药物剂量)'),
    '假如' + ACTION,
    '我胸痛，现在可以睡觉了吗？',
    '我呕血了，现在可以睡觉了吗？',
])
def test_whole_request_proof_does_not_erase_other_intents(message):
    tools = [{'function': {'name': 'health_query'}}]
    assert scope_tools_for_current_input_advice(tools, message) == tools


@pytest.mark.asyncio
@pytest.mark.parametrize('message', [BEDTIME, ACTION])
async def test_bypassed_local_route_cannot_promote_free_model_prose(db, auth_user_and_headers, monkeypatch, message):
    from app.services.agent_executor import AgentExecutor
    monkeypatch.setattr(AgentExecutor, 'run_stream', AgentExecutor._run_stream_impl)
    monkeypatch.setattr('app.services.agent_input_tool_scope.scope_tools_for_current_input_advice',
                        lambda tools, text: [{'type': 'function', 'function': {
                            'name': 'health_query', 'description': 'Synthetic forced read',
                            'parameters': {'type': 'object', 'additionalProperties': True}}}])
    reply = '本轮未查询个人记录，仅解释你提供的内容；无法确认个人检查安排或当前身体状态，请补充必要信息。'
    user, _ = auth_user_and_headers
    executor, done, persisted, public, dispatched = await _run_scripted(
        db, user, monkeypatch, query=message, first_tool='health_query',
        first_args={'dimension': 'sleep'}, dispatch=lambda request: {}, reply=reply,
        turn_id='conversation-advice', required_context_text='本轮只依据用户当前输入')
    assert not dispatched
    assert done['completion_status'] != 'complete'
    assert done['turn_outcome']['status'] != 'complete'
    assert persisted.content == public
    assert reply not in public
    assert 'current_input_advice_read_not_needed' in executor._agent_kernel_capability_block_reasons
    assert not done['write_receipts']


@pytest.mark.parametrize('message', [BEDTIME, ACTION])
def test_advice_has_no_private_preload_or_write_authority(db, monkeypatch, message):
    from app.services.agent_executor import AgentExecutor
    calls = []
    monkeypatch.setattr('app.services.health_context_lite_service.build_lite_health_context',
                        lambda *a, **k: calls.append('lite') or 'PRIVATE')
    monkeypatch.setattr('app.twin.builder.build_twin', lambda *a, **k: calls.append('twin'))
    executor = AgentExecutor(db)
    executor._start_agent_kernel_turn(user_id=41, message=message, channel='typed')
    executor._build_system_prompt(41, 1, None, intent_query=message)
    assert not calls
    assert decide(message, 'health_record', {'record_type': 'weight', 'data': {'weight': 70}}).action == 'block'


@pytest.mark.asyncio
@pytest.mark.parametrize('message', [BEDTIME, ACTION])
@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
async def test_advice_gateway_never_dispatches_private_read(message, mode):
    from dataclasses import replace
    from tests.test_agent_read_plan_binding import snapshot
    from app.services.agent_kernel.tool_gateway import ToolGateway
    from app.services.agent_kernel.types import ToolExecutionRequest
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    result = await ToolGateway(replace(snapshot(message), policy_mode=mode)).execute(
        ToolExecutionRequest(tool_name='analyze_recovery', arguments={}), dispatch)
    assert result.decision.action == 'block'
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('message', [BEDTIME, ACTION])
async def test_incomplete_answer_is_not_recovered(db, auth_user_and_headers, monkeypatch, message):
    from app.services.agent_executor import AgentExecutor
    monkeypatch.setattr(AgentExecutor, 'run_stream', AgentExecutor._run_stream_impl)
    user, _ = auth_user_and_headers
    _, done, _, _, calls = await _run_scripted(db, user, monkeypatch,
        query=message, first_tool='health_query', first_args={'dimension': 'sleep'},
        dispatch=lambda request: {}, reply='尚未完成', turn_id='advice-length', answer_finish_reason='length')
    assert not calls
    assert done['completion_status'] != 'complete'


@pytest.mark.asyncio
@pytest.mark.parametrize('message', [BEDTIME, ACTION])
@pytest.mark.parametrize('fabricate', [False, True])
async def test_panel_uses_same_answer_only_boundary(db, auth_user_and_headers, monkeypatch, message, fabricate):
    from app.models.agent_conversation import AgentMessage
    from app.services.agent_executor import AgentExecutor
    calls = []
    monkeypatch.setattr('app.twin.builder.build_twin', lambda *a, **k: calls.append('twin'))
    reply = '本轮未查询个人记录，仅基于当前输入提供通用解释；无法确认个人安排。'
    if fabricate:
        reply = '本轮未查询个人记录。你的睡眠记录显示你需要补觉。'
    async def lead(messages, tools):
        assert {t['function']['name'] for t in tools} <= {'knowledge_search'}
        assert any('不要假设用户描述了病症' in str(m.get('content', '')) for m in messages)
        return {'content': reply, 'finish_reason': 'stop'}
    class Provider:
        async def chat(self, **kwargs):
            return {'content': reply, 'finish_reason': 'stop'}
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, '_call_llm', lead)
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_model_id', lambda *_: Provider())
    user, _ = auth_user_and_headers
    events = [e async for e in executor._run_multi_model_stream(user.id, message, None, None, '{"multi_model":true}')]
    done = events[-1]['data']
    assert done['completion_status'] != 'complete'
    assert done['turn_outcome']['status'] != 'complete'
    assert not calls
    persisted = db.get(AgentMessage, done['message_id'])
    assert persisted.meta['turn_outcome'] == done['turn_outcome']
    assert reply not in persisted.content
    assert '无法核实' in persisted.content


@pytest.mark.parametrize('message,reply', [
    (BEDTIME, '我查过你的睡眠记录：你昨晚只睡了4小时，所以现在可以睡。'),
    (BEDTIME, '本轮未查询个人记录。你的睡眠记录显示你需要补觉。'),
    (ACTION, '你今天的复查是医生根据你的个人病史安排的，现在应当去做。'),
    (ACTION, '本轮未查询个人记录。医生已经安排你今天复查。'),
])
@pytest.mark.asyncio
async def test_invented_private_evidence_cannot_be_streamed_or_complete(db, auth_user_and_headers, monkeypatch, message, reply):
    from app.services.agent_executor import AgentExecutor
    monkeypatch.setattr(AgentExecutor, 'run_stream', AgentExecutor._run_stream_impl)
    user, _ = auth_user_and_headers
    _, done, persisted, public, calls = await _run_scripted(db, user, monkeypatch,
        query=message, first_tool='health_query', first_args={'dimension': 'sleep'},
        dispatch=lambda request: {}, reply=reply, turn_id='advice-invented-facts')
    assert not calls
    assert done['turn_outcome']['status'] != 'complete'
    assert persisted.content == public
    assert reply not in public
    assert '无法核实' in public or '未核验' in public or '已核验' in public


@pytest.mark.parametrize('reply', [
    '本轮未查询个人记录。查看了你的病史，所以今晚安全。',
    '本轮未查询个人记录。I have checked your sleep records.',
    '本轮未查询个人记录。我并非没有查过你的记录。',
    '本轮未查询个人记录。医生根据你的病史安排今天复查。',
    '本轮未查询个人记录。从你的睡眠记录来看，你昨晚只睡四小时，所以现在应当睡觉。',
    '本轮未查询个人记录。你的医生让你今天去复查。',
    '本轮未查询个人记录。医生说你今天要复查。',
    '本轮未查询个人记录。查到了昨晚睡眠只有4小时，所以现在可以睡。',
    '本轮未查询个人记录。睡眠记录表明昨晚只睡4小时。',
    '本轮未查询个人记录。经核验，你昨晚睡够了，可以放心睡。',
    '本轮未查询个人记录。I checked the sleep data; you only got four hours.',
])
def test_disclaimer_never_launders_unsupported_claims(reply):
    from app.services.agent_kernel.current_input_advice_scope import guard_current_input_answer
    for message in (BEDTIME, ACTION):
        assert not guard_current_input_answer(message, reply)[1]


def test_only_exact_goal_bound_canonical_answer_is_supported():
    from app.services.agent_kernel.current_input_advice_scope import guard_current_input_answer, local_advice_response
    bedtime = local_advice_response(BEDTIME)[1]
    action = local_advice_response(ACTION)[1]
    assert guard_current_input_answer(BEDTIME, bedtime) == (bedtime, True)
    assert guard_current_input_answer(ACTION, action) == (action, True)
    assert not guard_current_input_answer(BEDTIME, action)[1]
    assert not guard_current_input_answer(ACTION, bedtime)[1]
    assert not guard_current_input_answer(BEDTIME, bedtime + '你肯定安全。')[1]
