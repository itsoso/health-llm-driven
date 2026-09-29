"""Synthetic recovery advice must complete without reading personal records."""
import pytest

from tests.test_agent_read_plan_binding import decide, snapshot
from tests.test_query_reliability_outcomes import _run_scripted

QUERY = '我有慢性鼻炎(活动期)+过敏性鼻炎症状，今天该怎么休息和恢复？'
REPLY = '仅根据你当前描述，今天以休息为主；如果症状加重，请及时就医。'


@pytest.fixture(autouse=True)
def _isolate_transport(isolated_agent_protocol_transport):
    """Use real Pi transport, synthetic providers, and no external network."""


@pytest.mark.parametrize('tool,args', [
    ('health_query', {'dimension': 'sleep'}),
    ('health_query_batch', {'queries': [{'dimension': 'sleep'}]}),
    ('health_manage', {'record_type': 'illness', 'operation': 'list'}),
    ('health_analysis', {'type': 'orchestrator', 'question': '今天如何休息？'}),
    ('analyze_recovery', {}),
])
@pytest.mark.parametrize("expose_tool", [False, True])
@pytest.mark.asyncio
async def test_optional_personal_read_cannot_abort_recovery_advice(
    db, auth_user_and_headers, monkeypatch, tool, args, expose_tool,
):
    if expose_tool:
        # Bypass schema filtering to prove the gateway independently rejects
        # model-forced calls and still allows the advice to complete.
        monkeypatch.setattr('app.services.agent_input_tool_scope.scope_tools_for_current_input_advice',
                            lambda tools, message: [{"type": "function", "function": {
                                "name": tool, "description": "Synthetic forced tool proposal",
                                "parameters": {"type": "object", "additionalProperties": True},
                            }}])
    user, _ = auth_user_and_headers
    executor, done, persisted, public, dispatched = await _run_scripted(
        db, user, monkeypatch, query=QUERY, first_tool=tool, first_args=args,
        dispatch=lambda request: {}, reply=REPLY, turn_id=f'advice-{tool}', required_context_text='本轮只依据用户当前输入',
    )
    assert not dispatched
    assert persisted.content == public == REPLY
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['status'] == 'complete'
    if expose_tool:
        assert 'current_input_advice_read_not_needed' in executor._agent_kernel_capability_block_reasons, 'Keep denial audit'
    assert not done['write_receipts']


@pytest.mark.asyncio
async def test_truncated_advice_cannot_recover_a_rejection(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    _, done, _, _, dispatched = await _run_scripted(
        db, user, monkeypatch, query=QUERY, first_tool='health_query',
        first_args={'dimension': 'sleep'}, dispatch=lambda request: {},
        reply='未完成的建议', turn_id='advice-truncated', answer_finish_reason='length',
    )
    assert not dispatched
    assert done['completion_status'] != 'complete'


@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
@pytest.mark.asyncio
async def test_advice_gateway_rejects_hidden_personal_tools_in_all_modes(mode):
    from dataclasses import replace
    from app.services.agent_kernel.tool_gateway import ToolGateway
    from app.services.agent_kernel.types import ToolExecutionRequest
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    gateway = ToolGateway(replace(snapshot(QUERY), policy_mode=mode))
    result = await gateway.execute(ToolExecutionRequest(tool_name='analyze_recovery', arguments={}), dispatch)
    assert result.decision.action == 'block'
    assert not calls


def test_advice_cannot_authorize_writes():
    assert decide(QUERY, 'health_record', {'record_type': 'weight', 'data': {'weight': 70}}).action == 'block'


def test_current_input_advice_does_not_preload_personal_health_context(db, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    calls = []
    monkeypatch.setattr('app.services.health_context_lite_service.build_lite_health_context',
                        lambda *a, **k: calls.append(True) or 'UNRELATED PERSONAL HISTORY')
    executor = AgentExecutor(db)
    executor._current_user_id = 41
    executor._current_turn_user_message = QUERY
    executor._start_agent_kernel_turn(user_id=41, message=QUERY, channel='typed')
    prompt = executor._build_system_prompt(41, 1, None, intent_query=QUERY)
    assert not calls
    assert 'UNRELATED PERSONAL HISTORY' not in prompt
