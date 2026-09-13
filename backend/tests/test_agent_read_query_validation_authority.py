"""Parameter normalization must not erase a proposal before capability policy."""
import copy
import json
from unittest.mock import AsyncMock

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from tests.test_agent_longitudinal_read_regression import ANALYSIS_REQUESTS


@pytest.fixture(autouse=True)
def isolated(isolated_agent_protocol_transport):
    pass


@pytest.fixture
def executor(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    result = AgentExecutor(db)
    result._current_user_id = user.id
    result._current_turn_user_message = ANALYSIS_REQUESTS[0]
    result._turn_channel = 'typed'
    result._start_agent_kernel_turn(user_id=user.id, message=ANALYSIS_REQUESTS[0], channel='typed')
    return result


def proposal(shape, extra=None):
    query = {'dimension': 'sleep', 'days': 7}
    extra = extra or {}
    if shape == 'single':
        return 'health_query', {**query, **extra}
    if shape == 'single-plan':
        return 'health_query', {**query, 'plan': dict(extra)}
    if shape == 'batch-top':
        return 'health_query_batch', {'queries': [query], **extra}
    if shape == 'batch-plan':
        return 'health_query_batch', {'plan': {'queries': [query], **extra}}
    if shape == 'batch-query':
        return 'health_query_batch', {'queries': [{**query, **extra}]}
    return 'health_query_batch', {'plan': {'queries': [{**query, **extra}]}}


@pytest.mark.asyncio
@pytest.mark.parametrize('shape', ['single', 'single-plan', 'batch-top', 'batch-plan', 'batch-query', 'batch-plan-query'])
@pytest.mark.parametrize('owner_key', ['user_id', 'owner_id', 'tenant_id'])
async def test_actual_entry_preserves_owner_proposal_for_existing_policy(executor, monkeypatch, shape, owner_key):
    dispatch = AsyncMock(side_effect=AssertionError('Owner-bearing proposal must not dispatch'))
    monkeypatch.setattr(executor, '_dispatch_tool_request', dispatch)
    tool, args = proposal(shape, {owner_key: 999999})
    result = json.loads(await executor._execute_tool(tool, args, None))
    assert result['error_code'] == 'health_query_subject_not_current_user'
    assert result['dispatch_started'] is False
    dispatch.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('shape', ['single', 'single-plan', 'batch-top', 'batch-plan', 'batch-query', 'batch-plan-query'])
async def test_valid_single_and_batch_dispatch_only_canonical_frozen_args(executor, monkeypatch, shape):
    dispatch = AsyncMock(return_value='{"status":"success"}')
    monkeypatch.setattr(executor, '_dispatch_tool_request', dispatch)
    tool, args = proposal(shape)
    await executor._execute_tool(tool, args, None)
    dispatch.assert_awaited_once()
    actual = dispatch.call_args.args[0]
    query = resolve_owned_read_scope(executor._agent_kernel_snapshot).query('sleep')
    assert actual.arguments == (query if tool == 'health_query' else {'queries': [query]})


@pytest.mark.asyncio
@pytest.mark.parametrize('args', [
    {'type': 'sleep', 'time_range': '7 days', 'extra_proposal': 'not API data'},
    {'dimension': 'sleep', 'type': 'diet', 'days': 7, 'range': '30 days', 'extra_proposal': False},
])
async def test_existing_alias_precedence_and_adapter_projection_remain_canonical(executor, monkeypatch, args):
    dispatch = AsyncMock(return_value='{"status":"success"}')
    monkeypatch.setattr(executor, '_dispatch_tool_request', dispatch)
    await executor._execute_tool('health_query', copy.deepcopy(args), None)
    dispatch.assert_awaited_once()
    assert dispatch.call_args.args[0].arguments == resolve_owned_read_scope(
        executor._agent_kernel_snapshot).query('sleep')
