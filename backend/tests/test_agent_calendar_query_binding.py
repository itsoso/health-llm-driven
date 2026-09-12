"""Synthetic request-to-tool date binding; model arguments cannot widen scope."""
import json
from unittest.mock import AsyncMock
import pytest
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.capability_policy import decide_tool_capability


def decision(message, args):
    envelope = AgentEnvelope(user_id=41, channel='chat', text=message)
    context = ExecutionContext.for_test(user_id=41, channel='chat')
    snapshot = TurnSnapshot(envelope=envelope, context=context,
                            intent=build_intent_frame(envelope, context))
    return decide_tool_capability(snapshot, ToolExecutionRequest(
        tool_name='health_query', arguments=args, source='structured_or_recovered'))


@pytest.mark.parametrize('message,dimension,target', [
    ('查询昨天的饮食记录', 'diet', '2026-07-16'),
    ('昨晚睡眠怎么样', 'sleep', '2026-07-17'),
])
def test_calendar_query_is_bound_to_requested_day(message, dimension, target):
    result = decision(message, {'dimension': dimension, 'days': 30})
    assert result.action == 'allow', result.reason
    assert result.normalized_args == {'dimension': dimension, 'start_date': target,
                                      'end_date': target, 'timezone': 'Asia/Shanghai'}


def test_model_calendar_scope_is_not_authorization():
    result = decision('看看最近的饮食', {'dimension': 'diet', 'start_date': '2020-01-01',
                                         'end_date': '2020-01-31'})
    assert result.action == 'block'


@pytest.mark.parametrize('message,dimension', [
    ('不要查询昨天的饮食', 'diet'), ('查询我朋友昨天的饮食', 'diet'),
    ('查询昨天的睡眠', 'diet'), ('查询昨天和今天的饮食', 'diet'),
])
def test_calendar_projection_does_not_bypass_scope_guards(message, dimension):
    assert decision(message, {'dimension': dimension}).action == 'block'


@pytest.mark.asyncio
async def test_ambiguous_supplement_dosage_never_reaches_definition_api(db):
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)
    executor._current_user_id = 41
    executor._current_turn_user_message = '记录补剂：一粒两粒鱼油'
    executor._api_get_json = AsyncMock(return_value=([], None))
    result = await executor._exec_health_record('http://unused', {}, {
        'record_type': 'supplement', 'data': {'supplement_name': '鱼油', 'dosage': '2粒'},
    })
    assert json.loads(result)['error_code'] == 'supplement_dosage_requires_clarification'
    executor._api_get_json.assert_not_called()


@pytest.mark.parametrize('message', ['昨晚睡得怎样，是否适合锻炼', '昨天饮食怎么样',
                                      '2026-07-15睡眠如何', '本周一的睡眠怎么样'])
def test_calendar_question_is_a_read_without_command_verb(message):
    dimension = 'diet' if '饮食' in message else 'sleep'
    result = decision(message, {'dimension': dimension})
    assert result.action == 'allow', result.reason
    assert result.normalized_args['start_date'] == result.normalized_args['end_date']


@pytest.mark.parametrize('message,target', [
    ('今天我吃了啥', '2026-07-17'),
    ('我今天吃了什么？', '2026-07-17'),
    ('今天都吃了些什么', '2026-07-17'),
    ('昨天我吃过哪些东西？', '2026-07-16'),
    ('前天吃了什么', '2026-07-15'),
])
def test_colloquial_diet_recall_binds_exact_business_day(message, target):
    result = decision(message, {'dimension': 'diet', 'days': 30})
    assert result.action == 'allow', result.reason
    assert result.normalized_args == {
        'dimension': 'diet', 'start_date': target, 'end_date': target,
        'timezone': 'Asia/Shanghai',
    }


@pytest.mark.parametrize('message', [
    '今天妈妈吃了啥', '假如我问今天我吃了啥', '今天我应该吃什么',
    '今天我吃了米饭', '今天我吃了什么药', '今天我吃了什么补剂',
    '不要查询今天我吃了啥', '昨天和今天我吃了啥',
])
def test_colloquial_diet_recall_does_not_grant_other_speech_acts(message):
    assert decision(message, {'dimension': 'diet'}).action == 'block'


@pytest.mark.parametrize('message', ['昨晚妈妈的睡眠怎么样', '昨晚张三睡眠怎么样',
                                      '本周一张三的睡眠如何', '2026-07-15妈妈的睡眠如何',
                                      '我在想昨晚睡眠怎么样', '假如查询昨天饮食会怎样',
                                      '查询昨晚睡眠和饮食', '我昨晚睡了八小时'])
def test_calendar_subject_and_speech_act_remain_bound(message):
    assert decision(message, {'dimension': 'sleep'}).action == 'block'


def test_model_supplied_window_cannot_override_user_date():
    result = decision('查询昨天的饮食记录', {'dimension': 'diet', 'start_date': '2020-01-01',
                                             'end_date': '2020-01-31'})
    assert result.action == 'block'
    assert result.reason == 'health_query_calendar_window_conflict'


@pytest.mark.parametrize('dimension', ['sleep', 'diet'])
def test_mixed_domain_calendar_query_cannot_inherit_one_intent_domain(dimension):
    assert decision('查询昨晚睡眠和饮食', {'dimension': dimension}).action == 'block'
