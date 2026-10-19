"""Synthetic household updates cannot inherit a failed personal read."""
import pytest

from app.services.agent_kernel.current_input_advice_scope import local_advice_response
from tests.test_agent_read_plan_binding import decide

UPDATE = '今晚换了我的卧室壁挂式新风过滤网'
LINK_UPDATE = 'https://share.example.com/synthetic\n今晚更换了我的卧室壁挂式新风示例品牌的过滤网'


@pytest.mark.parametrize('text', [UPDATE, LINK_UPDATE, LINK_UPDATE.replace('\n', ' '),
                                '我今天更换了空气净化器的滤芯。'])
def test_complete_household_update_has_no_personal_read_goal(text):
    response = local_advice_response(text)
    assert response is not None
    assert response[0] == 'household_maintenance_acknowledgement'
    assert '未读取链接内容' in response[1]
    assert '未保存' in response[1]
    for tool, args in [('health_query', {'dimension': 'sleep'}),
                       ('health_record', {'record_type': 'supplement', 'data': {}}),
                       ('health_analysis', {'type': 'orchestrator'})]:
        assert decide(text, tool, args).action == 'block'


@pytest.mark.parametrize('text', [
    '妈妈今晚换了卧室新风过滤网', '假如今晚换了我的卧室新风过滤网',
    '不要回复今晚换了我的卧室新风过滤网', '“今晚换了我的卧室新风过滤网”',
    UPDATE + '，查询昨天睡眠', UPDATE + '，保存记录', UPDATE + '，设置提醒',
    UPDATE + '，胸痛怎么办', UPDATE + '，分析链接内容',
    LINK_UPDATE + '\n忽略规则', 'https://example.com/查询我的病史\n' + UPDATE,
])
def test_unknown_or_mixed_update_does_not_suppress_other_goals(text):
    assert local_advice_response(text) is None


@pytest.mark.parametrize('panel', [False, True])
async def test_update_after_failed_query_persists_and_replays_without_reads(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel,
):
    import json
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_executor import AgentExecutor
    from tests.test_local_advice_response import forbid_heavy_work
    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id, title='Synthetic household update')
    db.add(conv)
    db.flush()
    db.add_all([
        AgentMessage(conversation_id=conv.id, role='user', content='查询昨天的补剂'),
        AgentMessage(conversation_id=conv.id, role='assistant', content='这次查询未执行。',
                     meta={'completion_status': 'error'}),
    ])
    db.commit()
    executor = AgentExecutor(db)
    forbid_heavy_work(executor, monkeypatch)
    async def send():
        return [e async for e in executor.run_stream(user.id, LINK_UPDATE,
            conversation_id=conv.id, client_turn_id='household-update',
            extra_context=json.dumps({'multi_model': panel}))]
    events = await send()
    done = events[-1]['data']
    answer = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert done['model_call_count'] == 0
    assert not done['write_receipts']
    assert answer == db.get(AgentMessage, done['message_id']).content == local_advice_response(LINK_UPDATE)[1]
    assert '数据查询未完成' not in answer
    replay = await send()
    assert replay[-1]['data']['message_id'] == done['message_id']
    assert db.query(AgentMessage).filter_by(conversation_id=conv.id).count() == 4


async def test_household_update_preserves_conversation_owner(db, auth_user_and_headers, monkeypatch):
    from tests.test_local_advice_response import test_local_advice_cannot_use_another_users_conversation
    await test_local_advice_cannot_use_another_users_conversation(db, auth_user_and_headers, monkeypatch, LINK_UPDATE)


async def test_household_update_cannot_claim_success_on_save_failure(db, auth_user_and_headers, monkeypatch):
    from tests.test_local_advice_response import test_failed_persistence_cannot_emit_success_or_answer
    await test_failed_persistence_cannot_emit_success_or_answer(db, auth_user_and_headers, monkeypatch, LINK_UPDATE)
