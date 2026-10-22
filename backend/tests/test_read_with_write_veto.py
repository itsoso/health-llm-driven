"""A write veto must not revoke an independently authorized personal read."""
import pytest

from app.services.agent_kernel import health_semantics as semantics
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_recent_workout_read_regression import snapshot


@pytest.mark.parametrize('veto', [
    '不要记录服药', '不要修改数据', '不用保存', '无需新增记录',
    '请勿更新记录', '别帮我打卡', '不需要录入数据',
])
def test_write_veto_preserves_read_act(veto):
    text = '查询今天的睡眠记录，' + veto + '。'
    result = semantics.resolve_health_read_act(text)
    assert result.status == 'active'
    assert result.active_clause == text.rstrip('。')
    assert not semantics.health_read_cancelled(text)


@pytest.mark.parametrize('text', [
    '查询今天的睡眠记录，不要修改数据，不要查了。',
    '查询今天的睡眠记录，不用保存，算了。',
    '查询今天的睡眠记录，请勿更新记录，也不要查询。',
    '不要记录查询', '不用保存查询结果，请停止查询。',
])
def test_actual_read_withdrawal_still_wins(text):
    assert semantics.resolve_health_read_act(text).status == 'cancelled'


@pytest.mark.parametrize('veto', ['不要记录服药', '不要修改数据', '不用保存'])
def test_gateway_keeps_read_bounded_and_write_veto(veto):
    turn = snapshot('查询今天的睡眠记录，' + veto + '。')
    query = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension': 'sleep'}))
    assert query.action == 'allow', query.reason
    assert query.normalized_args['dimension'] == 'sleep'
    assert query.normalized_args['start_date'] == query.normalized_args['end_date'] == '2026-10-10'
    for tool, args in [
        ('health_query', {'dimension': 'sleep', 'user_id': 999}),
        ('health_query', {'dimension': 'sleep', 'start_date': '2025-01-01'}),
        ('health_query', {'dimension': 'diet'}),
        ('health_record', {'record_type': 'medication', 'data': {'name': 'Synthetic', 'status': 'taken'}}),
        ('health_manage', {'operation': 'delete', 'record_type': 'sleep', 'id': 1}),
    ]:
        assert decide_tool_capability(turn, ToolExecutionRequest(tool, args)).action == 'block'


@pytest.mark.parametrize('text', [
    '查询妈妈今天的睡眠记录，不要修改数据。',
    '解释“查询今天的睡眠记录，不用保存”。',
    '如果用户说查询今天的睡眠记录，不要记录服药。',
    '不要修改数据。',
    '查询今天的睡眠记录，不要修改妈妈的数据。',
    '查询今天的睡眠记录，不要修改数据只查去年。',
    '查询今天的睡眠记录，不要修改数据，改查妈妈的记录。',
    '查询今天的睡眠记录，不要修改数据，取消。',
    '查询今天的睡眠记录，不要修改数据，只有最近一次。',
])
def test_write_veto_never_creates_missing_read_authority(text):
    assert decide_tool_capability(snapshot(text), ToolExecutionRequest(
        'health_query', {'dimension': 'sleep'})).action == 'block'


@pytest.mark.parametrize('text', [
    '同步佳明，不要修改数据。',
    '查询今天的睡眠记录，不用保存。',
])
def test_read_projection_never_grants_sync_side_effects(text):
    from app.services.agent_kernel.read_task_scope import has_owned_sync_instruction
    assert not has_owned_sync_instruction(text)
