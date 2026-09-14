"""Quoted operands never become owned sync authority after erasure."""
from dataclasses import replace
from datetime import datetime

import pytest

from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import has_owned_sync_instruction, resolve_sync_status_query
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot


def snapshot(text, mode='enforce'):
    envelope = AgentEnvelope(user_id=41, channel='typed', text=text)
    context = ExecutionContext(user_id=41, channel='typed', timezone='Asia/Shanghai',
                               current_time=datetime.fromisoformat('2026-09-13T09:00:00+08:00'))
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context), policy_mode=mode)


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['同步“张三”的佳明数据', '同步我“昨天”的佳明数据'])
@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
async def test_quoted_sync_operand_never_dispatches_or_receives_owned_evidence(text, mode):
    turn = snapshot(text, mode)
    dispatched = []
    async def dispatch(request):
        dispatched.append(request)
        return '{"job_id":"must-not-enqueue"}'
    result = await ToolGateway(turn).execute(
        ToolExecutionRequest('health_record', {'record_type': 'garmin_sync', 'data': {}}), dispatch,
    )
    assert not dispatched
    assert not has_owned_sync_instruction(text)
    assert 'semantic:owned_garmin_sync' not in turn.intent.evidence
    assert result.decision.action == 'block'
    assert result.decision.reason == 'garmin_sync_scope_unresolved'


@pytest.mark.asyncio
@pytest.mark.parametrize('text', [
    '同步`张三的`佳明数据',
    '同步~~张三的~~佳明数据',
    '同步我`昨天`的佳明数据',
    '“例子”仅限张三。仅限张三。同步我的佳明数据',
    '“例子”仅限张三。同步我的佳明数据',
    '`例子`仅限张三。同步我的佳明数据',
    '~~例子~~仅限张三。同步我的佳明数据',
    '“例子”仅限昨天。同步我的佳明数据',
    '“例子”先等我确认。同步我的佳明数据',
    '“例子”不要执行。同步我的佳明数据',
])
@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
async def test_markdown_material_cannot_erase_sync_owner_or_scope(text, mode):
    turn = snapshot(text, mode)
    dispatched = []

    async def dispatch(request):
        dispatched.append(request)
        return '{"job_id":"must-not-enqueue"}'

    result = await ToolGateway(turn).execute(
        ToolExecutionRequest('health_record', {'record_type': 'garmin_sync', 'data': {}}),
        dispatch,
    )

    assert not dispatched
    assert not has_owned_sync_instruction(text)
    assert 'semantic:owned_garmin_sync' not in turn.intent.evidence
    assert result.decision.action == 'block'
    assert result.decision.reason == 'garmin_sync_scope_unresolved'


@pytest.mark.asyncio
@pytest.mark.parametrize('text', [
    '“这只是例子”已结束。同步我的佳明数据',
    '`这只是例子`已结束；同步我的佳明数据',
    '~~这只是例子~~已结束；同步我的佳明数据',
    '同步我的佳明数据；`独立例子`已结束',
    '同步我的佳明数据；~~独立例子~~已结束',
])
@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
async def test_independent_material_does_not_block_owned_sync(text, mode):
    turn = snapshot(text, mode)
    dispatched = []

    async def dispatch(request):
        dispatched.append(request)
        return '{"job_id":"synthetic-authorized-sync"}'

    result = await ToolGateway(turn).execute(
        ToolExecutionRequest('health_record', {'record_type': 'garmin_sync', 'data': {}}),
        dispatch,
    )

    assert len(dispatched) == 1
    assert has_owned_sync_instruction(text)
    assert 'semantic:owned_garmin_sync' in turn.intent.evidence
    assert result.decision.action == 'allow'


@pytest.mark.parametrize('text', [
    '同步我「昨天」的佳明数据', '同步我\'昨天\'的佳明数据',
    '同步我`昨天`的佳明数据', '同步我“昨天的佳明数据',
    '“同步我的佳明数据”', '医生说“同步我的佳明数据”',
    '不要同步我的佳明数据', '同步我昨天的佳明数据',
])
def test_non_authorizing_sync_preserves_existing_scope_restrictions(text):
    assert not has_owned_sync_instruction(text)


@pytest.mark.parametrize('text', [
    '同步我的佳明数据', '刷新我的佳明数据',
    '麻烦把我的佳明数据刷新一下，然后看看昨晚睡得怎么样。',
])
def test_explicit_owned_current_sync_still_resolves(text):
    assert has_owned_sync_instruction(text)


def test_readonly_snapshot_cannot_gain_sync_authority():
    turn = snapshot('同步我的佳明数据')
    readonly = replace(turn, intent=replace(turn.intent, operation='list', is_write=False))
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    decision = decide_tool_capability(readonly, ToolExecutionRequest(
        'health_record', {'record_type': 'garmin_sync', 'data': {}},
    ))
    assert decision.action == 'block'


@pytest.mark.parametrize('text', ['“张三”的佳明数据同步完成了吗', '我的“昨天”佳明数据同步完成了吗'])
def test_quoted_sync_status_scope_cannot_become_current_owned_status(text):
    assert resolve_sync_status_query(snapshot(text)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "shadow"])
@pytest.mark.parametrize("text,expected", [
    ("同步我的佳明数据，算了", False),
    ("同步我的佳明数据还是算了", False),
    ("同步我的佳明数据，先放一放", False),
    ("刷新我的佳明数据，我改主意了", False),
    ("拉取我的佳明数据，当我没说", False),
    ("同步我的佳明数据，算了，再查询我昨天的睡眠", False),
    ("同步我的佳明数据，算了。再同步我的佳明数据", True),
    ("算了。同步我的佳明数据", True),
    ("医生说“算了”。同步我的佳明数据", True),
    ("同步我的佳明数据。医生说“算了”", True),
    ("“同步我的佳明数据，算了”", False),
    ("同步我的佳明数据。查询昨天睡眠还是算了", True),
])
async def test_sync_withdrawal_binds_action_order_without_reviving_cancelled_sync(text, expected, mode):
    turn = snapshot(text, mode)
    dispatched = []

    async def dispatch(request):
        dispatched.append(request)
        return '{"job_id":"synthetic-authorized-sync"}'

    result = await ToolGateway(turn).execute(
        ToolExecutionRequest("health_record", {"record_type": "garmin_sync", "data": {}}), dispatch,
    )
    assert bool(dispatched) is expected
    assert has_owned_sync_instruction(text) is expected
    assert ("semantic:owned_garmin_sync" in turn.intent.evidence) is expected
    if not expected:
        assert result.decision.action == "block"
        assert result.decision.reason == "garmin_sync_scope_unresolved"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "shadow"])
@pytest.mark.parametrize("text,expected", [
    ("同步我的佳明数据，仅限昨天", False),
    ("同步我的佳明数据，仅限早餐后", False),
    ("同步我的佳明数据，先等我确认", False),
    ("同步我的佳明数据，然后查询昨天睡眠", True),
    ("同步我的佳明数据早餐后", False),
    ("同步我的佳明数据，仅在我批准以后", False),
    ("同步我的佳明数据，有空再执行", False),
    ("同步我的佳明数据。查询昨天的睡眠。仅限早餐后", False),
    ("同步我的佳明数据。查询昨天的睡眠。给我建议", True),
    ("先分析昨天的睡眠，再同步佳明数据", True),
])
async def test_sync_authority_requires_every_clause_to_be_consumed(text, expected, mode):
    turn = snapshot(text, mode)
    dispatched = []

    async def dispatch(request):
        dispatched.append(request)
        return '{"job_id":"synthetic-authorized-sync"}'

    result = await ToolGateway(turn).execute(
        ToolExecutionRequest("health_record", {"record_type": "garmin_sync", "data": {}}), dispatch,
    )
    assert bool(dispatched) is expected
    assert has_owned_sync_instruction(text) is expected
    if not expected:
        assert result.decision.action == "block"
        assert result.decision.reason == "garmin_sync_scope_unresolved"
