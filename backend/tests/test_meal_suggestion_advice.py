"""Ordinary meal suggestions are answer goals, not personal-record queries."""
import json

import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.current_input_advice_scope import (
    is_current_input_advice, local_advice_response,
)
from tests.test_local_advice_response import forbid_heavy_work


REQUESTS = [
    '今晚吃点啥比较好', '今晚吃什么好？', '今天晚上吃什么比较好？',
    '晚饭吃啥', '晚餐吃点什么好呢？', '今天中午吃什么好',
    '明天早餐吃什么比较好？', '午餐吃啥好？', '请问我晚饭应该吃什么？',
    '今 晚 吃 点 啥 比 较 好',
]
STRICT = [
    '根据我昨天的饮食，今晚吃点啥比较好', '今晚吃点啥比较好，查一下我的饮食',
    '今晚吃点啥比较好并保存计划', '我胃痛，今晚吃点啥比较好',
    '我对鸡蛋过敏，今晚吃什么好', '给妈妈推荐晚饭吃什么',
    '不要回答今晚吃点啥比较好', '“今晚吃点啥比较好”',
    '如果我问今晚吃点啥比较好', '今晚吃点啥比较好\n并记录',
    '今晚吃点啥比较好\t', '今晚吃什么药好', '今晚吃什么补剂好',
    '晚饭吃了什么', '查询我今晚吃了什么', '今晚吃点啥比较好，减重用',
    '今晚吃点啥比较好，按之前说的禁忌', '刚才那个能吃吗',
]


@pytest.mark.parametrize('text', REQUESTS)
def test_complete_meal_question_is_an_answer_without_read_authority(text):
    from tests.test_sleep_oxygen_read_scope import decide
    assert is_current_input_advice(text)
    kind, answer = local_advice_response(text)
    assert kind == 'meal_suggestion_advice'
    assert '本轮未查询个人记录' in answer
    assert '过敏' in answer and '饮食要求' in answer
    for tool, args in [('health_query', {'dimension': 'diet'}),
                       ('health_query_batch', {'queries': [{'dimension': 'diet'}]}),
                       ('health_record', {'record_type': 'diet', 'data': {}})]:
        assert decide(args, text, tool).action == 'block'


@pytest.mark.parametrize('text', STRICT)
def test_other_goals_and_limits_are_not_erased(text):
    assert local_advice_response(text) is None


def test_free_model_prose_cannot_claim_personalized_meal_evidence():
    from app.services.agent_kernel.current_input_advice_scope import guard_current_input_answer
    answer, verified = guard_current_input_answer(REQUESTS[0], '根据你的病史，今晚只吃半碗饭。')
    assert not verified
    assert '根据你的病史' not in answer and '半碗饭' not in answer


@pytest.mark.parametrize('attachment', ['image', 'file'])
async def test_attachments_keep_their_existing_pipeline(db, auth_user_and_headers, monkeypatch, attachment):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs)
        yield {'event': 'done', 'data': {'completion_status': 'error'}}
    monkeypatch.setattr(executor, '_run_stream_impl', ordinary)
    kwargs = ({'images': [{'base64': 'c3ludGhldGlj', 'mime_type': 'image/jpeg'}]}
              if attachment == 'image' else {'file_base64': 'c3ludGhldGlj', 'file_name': 'synthetic.txt'})
    events = [e async for e in executor.run_stream(user.id, REQUESTS[0], **kwargs)]
    assert calls
    assert events[-1]['data'].get('route') != 'current_input_local_advice'


@pytest.mark.parametrize('history', ['weather', 'blocked_read'])
@pytest.mark.parametrize('panel', [False, True])
async def test_screenshot_entry_persists_a_useful_answer_without_model_or_reads(
    db, auth_user_and_headers, monkeypatch, history, panel,
):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='Synthetic meal suggestion')
    svc.save_message(conv.id, 'user', '合成城市天气' if history == 'weather' else '查询昨天的饮食')
    svc.save_message(conv.id, 'assistant', '合成天气回复' if history == 'weather' else '本轮数据查询未完成。',
                     meta={'completion_status': 'complete' if history == 'weather' else 'error'})
    executor = AgentExecutor(db)
    forbid_heavy_work(executor, monkeypatch)
    async def send():
        return [e async for e in executor.run_stream(
            user.id, REQUESTS[0], conversation_id=conv.id, client_turn_id='meal-advice',
            extra_context=json.dumps({'multi_model': panel}),
        )]
    events = await send()
    done = events[-1]['data']
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert done['advice_kind'] == 'meal_suggestion_advice'
    assert done['model_call_count'] == 0
    assert not done['write_receipts'] and not done['turn_outcome']['dispatch_started']
    answer = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert '米饭' in answer and '面' in answer and '蔬菜' in answer
    assert '本轮数据查询未完成' not in answer
    saved = db.get(AgentMessage, done['message_id'])
    assert saved.content == answer and saved.meta['turn_outcome'] == done['turn_outcome']
    replay = await send()
    assert replay[-1]['data']['message_id'] == done['message_id']
    assert ''.join(e['data']['content'] for e in replay if e.get('event') == 'token') == answer
    assert db.query(AgentMessage).filter_by(conversation_id=conv.id).count() == 4


@pytest.mark.parametrize('text', STRICT[:8])
async def test_strict_requests_reach_full_pipeline(db, auth_user_and_headers, monkeypatch, text):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs['message'])
        yield {'event': 'done', 'data': {'completion_status': 'error'}}
    monkeypatch.setattr(executor, '_run_stream_impl', ordinary)
    _ = [e async for e in executor.run_stream(user.id, text)]
    assert calls == [text]
