"""A future daily draft is not authority to inspect historical health records."""
import json
from uuid import uuid4

import pytest
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock, owned_data as owned_data,
)

REQUESTS = ['规划今天饮食运动和睡眠', '请帮我规划今天的饮食、运动和睡眠',
            '安排明天饮食和睡眠计划',
            '安排我明天的运动、饮食和补剂的摄入。',
            '今天如何运动 饮食和 睡眠',
            '今天应该怎么安排饮食、运动和睡眠？',
            '我今天该如何安排运动、饮食与睡眠？',
            '请问明天怎么规划饮食和睡眠',
            '今天饮食、运动和睡眠应该怎么安排？',
            '今天的运动和饮食如何安排',
            '本周如何制定运动和睡眠计划？', '今 天 如 何 运 动 饮 食 和 睡 眠']

@pytest.fixture(autouse=True)
def _transport(isolated_agent_protocol_transport):
    pass

@pytest.mark.parametrize('text', REQUESTS)
def test_daily_draft_has_answer_scope_without_personal_reads(text):
    from app.services.agent_kernel.current_input_advice_scope import is_current_input_advice, local_advice_response
    from tests.test_sleep_oxygen_read_scope import decide
    assert is_current_input_advice(text)
    kind, answer = local_advice_response(text)
    assert kind == 'daily_planning_advice'
    assert '本轮未查询个人记录、未保存计划' in answer
    assert decide({'dimension': 'sleep'}, text).action == 'block'


def test_daily_draft_instructions_preserve_missing_personal_basis():
    from app.services.agent_kernel.current_input_advice_scope import current_input_advice_instructions
    instructions = current_input_advice_instructions('今天如何运动 饮食和 睡眠')
    assert '先说明本轮未查询个人记录、未保存计划' in instructions
    assert '不默认减重或建议主食减半、制造热量缺口' in instructions
    assert '不能仅凭当前钟点断言适合入睡' in instructions


def test_supplement_daily_draft_is_local_and_never_invents_an_intake_plan():
    from app.services.agent_kernel.current_input_advice_scope import (
        current_input_advice_instructions,
        local_advice_response,
    )

    message = '安排我明天的运动、饮食和补剂的摄入。'
    kind, answer = local_advice_response(message)

    assert kind == 'daily_planning_advice'
    assert '**运动**' in answer and '**饮食**' in answer and '**补剂**' in answer
    assert '不能安排具体产品、剂量、频次或时间' in answer
    assert '未查询个人记录、未保存计划' in answer
    assert '不读取个人补剂记录' in current_input_advice_instructions(message)

@pytest.mark.parametrize('text', [
    '规划今天饮食运动和睡眠，并查询我的病史', '根据我昨天的睡眠规划今天饮食运动和睡眠',
    '给妈妈规划今天饮食运动和睡眠', '“规划今天饮食运动和睡眠”',
    '不要规划今天饮食运动和睡眠', '规划今天饮食运动和睡眠并保存',
    '规划今天用药和睡眠',
    '今天如何运动饮食和睡眠，并查询我的病史',
    '根据我昨天的睡眠，今天如何运动饮食和睡眠',
    '妈妈今天如何运动饮食和睡眠',
    '“今天如何运动 饮食和 睡眠”',
    '假如今天如何运动饮食和睡眠',
    '不要回答今天如何运动饮食和睡眠',
    '今天如何运动饮食和睡眠并保存计划',
    '今天如何运动饮食和睡眠，继续服药吗',
    '今天如何运动饮食和睡眠，只根据我的记录',
    '今天如何运动\n饮食和睡眠',
    '今天运动饮食睡眠怎么样',
    '今天如何服药和睡眠',
    '今天如何运动饮食和睡眠，查询昨天的睡眠',
    '安排我明天的运动、饮食和补剂的摄入，并查询我的补剂记录',
    '给妈妈安排明天的运动、饮食和补剂的摄入',
    '“安排我明天的运动、饮食和补剂的摄入”',
    '不要安排我明天的运动、饮食和补剂的摄入',
    '安排我明天的运动、饮食和补剂的摄入并保存计划',
    '安排我明天的运动、饮食和用药',
])
def test_unknown_owner_basis_or_write_does_not_become_general_advice(text):
    from app.services.agent_kernel.current_input_advice_scope import is_current_input_advice
    assert not is_current_input_advice(text)

@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('query', [REQUESTS[0], '今天如何运动 饮食和 睡眠'])
async def test_screenshot_turn_finishes_without_model_or_personal_reads(db, owned_data, monkeypatch, panel, query):
    from tests.test_agent_read_repair_round_budget import batch_trace
    answer = '本轮未查询个人记录。以下是通用安排草稿：规律进餐、按身体感受选择轻松活动，晚间预留休息时间；有不适时暂停。'
    monkeypatch.setattr('tests.test_agent_read_repair_round_budget.ANSWER', answer)
    trace = batch_trace(db, monkeypatch, [answer])
    done, saved = await consume_advice(db, trace, owned_data, panel=panel, query=query)
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['status'] == 'complete'
    assert not trace.dispatches
    assert not trace.calls
    assert '本轮数据查询未完成' not in saved.content
    assert done['model_call_count'] == 0
    assert '本轮未查询个人记录、未保存计划' in saved.content


@pytest.mark.parametrize('panel', [False, True])
async def test_question_after_failed_read_does_not_inherit_previous_goal(db, owned_data, monkeypatch, panel):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from tests.test_agent_read_repair_round_budget import batch_trace
    conversation = AgentConversation(user_id=owned_data.id, title='Synthetic failed read')
    db.add(conversation)
    db.flush()
    db.add_all([
        AgentMessage(conversation_id=conversation.id, role='user', content='查询我的昨天饮食和睡眠'),
        AgentMessage(conversation_id=conversation.id, role='assistant', content='本轮数据查询未完成。',
                     meta={'completion_status': 'error', 'turn_outcome': {'status': 'blocked',
                           'reason_code': 'health_query_dimension_conflict'}}),
    ])
    db.commit()
    answer = '本轮未查询个人记录。运动、饮食和睡眠仅提供有条件的通用安排，未保存计划。'
    monkeypatch.setattr('tests.test_agent_read_repair_round_budget.ANSWER', answer)
    trace = batch_trace(db, monkeypatch, [answer])
    done, saved = await consume_advice(db, trace, owned_data, panel=panel,
                               query='今天如何运动 饮食和 睡眠', conversation_id=conversation.id)
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['status'] == 'complete'
    assert not trace.dispatches
    assert not trace.calls
    assert '本轮未查询个人记录、未保存计划' in saved.content


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'sleep'}),
    ('health_query_batch', {'queries': [{'dimension': 'sleep'}, {'dimension': 'diet'}]}),
    ('health_record', {'record_type': 'sleep', 'data': {}}),
])
def test_question_never_grants_personal_tool_authority(tool, args):
    from tests.test_sleep_oxygen_read_scope import decide
    decision = decide(args, '今天如何运动 饮食和 睡眠', tool)
    assert decision.action == 'block'
    assert decision.reason == ('current_input_advice_tool_not_allowed' if tool == 'health_record'
                               else 'current_input_advice_read_not_needed')


def test_model_prose_cannot_replace_reviewed_daily_answer():
    from app.services.agent_kernel.current_input_advice_scope import guard_current_input_answer
    message = '今天如何运动 饮食和 睡眠'
    answer, verified = guard_current_input_answer(message, '根据个人记录，主食减半，22:30入睡。')
    assert not verified
    assert '已停止提供这部分结论' in answer
    assert '主食减半' not in answer


async def consume_advice(db, trace, user, *, panel=False, query, conversation_id=None):
    from app.models.agent_conversation import AgentMessage
    events = [event async for event in trace.executor.run_stream(
        user.id, query, channel='typed', client_turn_id=str(uuid4()),
        extra_context=json.dumps({'multi_model': panel}), conversation_id=conversation_id,
    )]
    done = next(event['data'] for event in reversed(events) if event.get('event') == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert done['route'] == 'current_input_local_advice'
    assert saved.meta['turn_outcome'] == done['turn_outcome']
    assert saved.meta['completion_status'] == done['completion_status']
    assert ''.join(event['data'].get('content', '') for event in events
                   if event.get('event') == 'token') == saved.content
    assert not done['write_receipts']
    return done, saved


@pytest.mark.parametrize('message', REQUESTS)
@pytest.mark.parametrize('panel', [False, True])
async def test_daily_question_has_reviewed_zero_model_answer(db, auth_user_and_headers, monkeypatch, message, panel):
    from tests.test_local_advice_response import forbid_heavy_work
    from app.services.agent_executor import AgentExecutor
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    forbid_heavy_work(executor, monkeypatch)
    turn_id = 'daily-question-replay'
    async def send():
        return [e async for e in executor.run_stream(user.id, message, client_turn_id=turn_id,
                    extra_context=json.dumps({'multi_model': panel}))]
    events = await send()
    done = next(e['data'] for e in reversed(events) if e.get('event') == 'done')
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert done['model_call_count'] == 0
    assert done['advice_kind'] == 'daily_planning_advice'
    answer = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert '本轮未查询个人记录、未保存计划' in answer
    assert '已有医嘱' in answer or '饮食要求' in answer
    assert not any(term in answer for term in ('主食减半', '热量缺口', '分钟', '22:', '23:'))
    assert not done['write_receipts'] and not done['turn_outcome']['dispatch_started']
    assert db.get(AgentMessage, done['message_id']).content == answer
    replay = await send()
    assert replay[-1]['data']['message_id'] == done['message_id']
    assert ''.join(e['data']['content'] for e in replay if e.get('event') == 'token') == answer
    assert db.query(AgentMessage).filter_by(conversation_id=done['conversation_id']).count() == 2
