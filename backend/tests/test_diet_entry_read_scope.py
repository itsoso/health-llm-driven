"""The diet screen's advice prompt authorizes one owned day, never future reads."""
from datetime import datetime

import pytest

from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan
from tests.test_longitudinal_read_scope_policy import decide, snapshot

REQUEST = '今天饮食结构怎么样? 蛋白质够吗? 帮我给出下一餐调整建议。'


@pytest.mark.parametrize('day,expected', [('今天', '2026-09-13'), ('昨天', '2026-09-12'), ('2026-09-10', '2026-09-10')])
@pytest.mark.parametrize('punctuation', ['?', '？'])
def test_diet_entry_binds_exact_read_day(day, expected, punctuation):
    text = REQUEST.replace('今天', day).replace('?', punctuation)
    turn = snapshot(text)
    plan = resolve_daily_read_plan(text, turn.context.current_time)
    assert plan is not None and plan.asks_advice
    assert plan.dimensions == ('diet',)
    assert plan.start_date == plan.end_date == expected
    decision = decide({'dimension': 'diet'}, text=text)
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == plan.queries()[0]
    batch = decide({'queries': [{'dimension': 'diet'}]}, text=text, tool='health_query_batch')
    assert batch.action == 'allow', batch.reason
    assert batch.normalized_args == {'queries': list(plan.queries())}


def test_diet_entry_uses_account_local_day():
    plan = resolve_daily_read_plan(REQUEST, datetime.fromisoformat('2026-09-13T01:00:00+00:00'),
                                  timezone_name='America/Los_Angeles')
    assert plan is not None
    assert plan.start_date == plan.end_date == '2026-09-12'


@pytest.mark.parametrize('text', [
    '妈妈的' + REQUEST, '如果可以，' + REQUEST, '解释例句：“' + REQUEST + '”',
    REQUEST + '只看上午。', REQUEST + '不要查询我的记录。',
    REQUEST + '只查昨天。', REQUEST.replace('今天', '明天'),
    REQUEST + '删除昨天的记录。', REQUEST + '查询朋友的睡眠。',
])
def test_diet_entry_does_not_discard_scope_restrictions(text):
    assert decide({'dimension': 'diet'}, text=text).action == 'block'


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'sleep'}),
    ('health_query', {'dimension': 'diet', 'user_id': 42}),
    ('health_query', {'dimension': 'diet', 'start_date': '2026-09-12'}),
    ('health_record', {'record_type': 'diet', 'data': {'food_items': 'rice'}}),
])
def test_diet_entry_cannot_expand_read_or_write(tool, args):
    assert decide(args, text=REQUEST, tool=tool).action == 'block'


@pytest.mark.parametrize('args', [
    {'queries': [{'dimension': 'diet', 'owner_id': 42}]},
    {'queries': [{'dimension': 'diet', 'timezone': 'UTC'}]},
    {'queries': [{'dimension': 'diet', 'end_date': '2026-09-14'}]},
    {'queries': [{'dimension': 'diet'}, {'dimension': 'sleep'}]},
    {'queries': [{'dimension': 'diet'}, {'dimension': 'diet'}]},
    {'queries': []}, {'queries': [None]},
    {'plan': {'queries': [{'dimension': 'diet'}], 'owner_id': 42}},
    {'queries': [{'dimension': 'diet'}], 'compare': True},
])
def test_diet_entry_batch_rejects_expanded_or_malformed_plan(args):
    assert decide(args, text=REQUEST, tool='health_query_batch').action == 'block'
