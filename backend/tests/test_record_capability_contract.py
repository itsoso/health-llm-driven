from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=ZoneInfo('Asia/Taipei'))

@pytest.mark.parametrize('text', [
    '记录，我洗鼻一次，使用了一支10毫升的生理盐水',
    '今天（2026-10-31）洗鼻 1 次，使用生理盐水 10 ml',
    '帮我记下：我冲洗鼻腔一次，用了10ml生理盐水',
])
def test_contract_resolves_action_payload_and_schema(text):
    from app.services.record_capabilities import resolve_record_capability
    bound = resolve_record_capability(text, NOW)
    assert bound is not None
    assert bound.arguments() == {'record_type': 'nasal_wash', 'data': {
        'count': 1, 'volume_ml': 10.0, 'solution': '生理盐水', 'record_date': '2026-10-31'}}

@pytest.mark.parametrize('text', [
    '我爸洗鼻一次，使用生理盐水10ml', '不要记录，我洗鼻一次',
    '如果我洗鼻一次，使用生理盐水10ml，请记录',
    '请解释“记录，我洗鼻一次，使用生理盐水10ml”',
    '明天洗鼻一次，使用生理盐水10ml', '洗鼻一次可以吗',
    '记录我洗鼻一次，另外服药两片', '记录洗鼻一次，体重70kg',
    '今天（2026-10-30）洗鼻1次', '记录洗鼻一次，使用0ml生理盐水',
])
def test_unbound_or_compound_text_never_grants_capability(text):
    from app.services.record_capabilities import resolve_record_capability
    assert resolve_record_capability(text, NOW) is None


@pytest.mark.parametrize('channel', ['voice', 'siri', 'chat', 'unknown'])
def test_capability_does_not_bypass_channel_confirmation(channel):
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest
    from app.services.agent_kernel.context import build_turn_snapshot
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.types import TurnSnapshot
    from app.services.record_capabilities import resolve_record_capability
    message = '记录，我洗鼻一次，使用了一支10毫升的生理盐水'
    context = ExecutionContext(current_time=NOW, timezone='Asia/Taipei', user_id=1, channel=channel)
    envelope = AgentEnvelope(user_id=1, channel=channel, text=message)
    intent = build_intent_frame(envelope, context)
    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)
    snapshot = TurnSnapshot(envelope=envelope, context=context, intent=intent, goal=goal)
    bound = resolve_record_capability(message, NOW)
    decision = decide_tool_capability(snapshot, ToolExecutionRequest('health_record', bound.arguments()))
    assert decision.action == 'block'


@pytest.mark.parametrize('response', [
    {'id': '123', 'checkin_date': '2026-10-31'},
    {'record_id': 123, 'checkin_date': '2026-10-31'},
    {'id': 123, 'record_capability_proof': {'record_type': 'nasal_wash', 'payload_sha256': 'wrong'}},
])
def test_registered_capability_needs_value_proof_not_just_row_identity(response):
    from app.services.agent_executor import _write_receipt_from_tool_result
    from app.services.record_capabilities import resolve_record_capability
    bound = resolve_record_capability('我洗鼻一次', NOW)
    assert _write_receipt_from_tool_result('health_record', bound.arguments(), response) is None
