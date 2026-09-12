"""Production failure variants, with real executor classification and Pi transport."""
import json
import pytest

from app.services.agent_executor import (
    AgentExecutor, _is_fast_eligible_turn, _parse_explicit_diet_correction,
)


@pytest.fixture(autouse=True)
def _isolate_twin_cache(isolated_agent_protocol_transport):
    """No live provider/cache I/O in executor tests."""


@pytest.mark.asyncio
@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('query,tool,args,expected', [
    ('今日我吃了啥', 'health_manage', {'record_type': 'diet', 'operation': 'list'}, ('diet',)),
    ('今天晚上我吃了什么？给我一些建议。', 'health_query', {'dimension': 'diet'}, ('diet',)),
    ('给我今天总结 给我建议', 'health_analysis', {'analysis_type': 'orchestrator'}, ('diet', 'sleep')),
])
async def test_daily_read_runs_through_pi_with_verified_scope(db, auth_user_and_headers, monkeypatch, query, tool, args, expected, panel):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    dispatched = []
    rounds = []

    async def provider(messages, tools):
        rounds.append(messages)
        if len(rounds) == 1:
            yield {'type': 'tool_calls', 'tool_calls': [{'id': 'read-1', 'type': 'function',
                'function': {'name': tool, 'arguments': json.dumps(args)}}]}
            yield {'type': 'finish', 'finish_reason': 'tool_calls'}
        else:
            yield {'type': 'content', 'text': '已查询，本次没有可用记录。'}
            yield {'type': 'finish', 'finish_reason': 'stop'}

    async def dispatch(request, token):
        dispatched.append(request)
        return json.dumps({'records': [], 'count': 0, 'availability': 'no_data'})

    monkeypatch.setattr(executor, '_build_system_prompt', lambda *a, **k: 'Use tools.')
    monkeypatch.setattr(executor, '_call_llm_stream', provider)
    monkeypatch.setattr(executor, '_dispatch_tool_request', dispatch)
    events = [e async for e in executor.run_stream(user.id, query, client_turn_id='daily-scope', extra_context=json.dumps({'multi_model': panel}))]
    done = events[-1]['data']
    assert len(dispatched) == len(expected)
    assert {r.arguments.get('dimension') or r.arguments.get('record_type') for r in dispatched} == set(expected)
    for request in dispatched:
        assert request.arguments.get('date') or request.arguments['start_date'] == request.arguments['end_date']
    if '晚上' in query:
        assert dispatched[0].arguments['meal_type'] == 'dinner'
    assert done['turn_outcome']['status'] == 'complete'
    assert {g['goal_id'] for g in done['turn_outcome']['goals']} == set(expected)


@pytest.mark.parametrize('message', [
    '晚餐我吃了1/2，请修改记录',
    '今天晚餐我吃了二分之一，修改记录',
    '我吃了1/2，重新修改晚餐的热量和分量。',
])
def test_explicit_whole_meal_fraction_survives_clause_order(message):
    correction = _parse_explicit_diet_correction(message)
    assert correction is not None
    assert correction['meal_type'] == 'dinner'
    assert correction['consumed_fraction'] == 0.5


@pytest.mark.parametrize('message', [
    '晚餐我吃了1/2的蛋糕，请修改记录',
    '晚餐我可能吃了1/2，请修改记录',
    '晚餐我吃了1/2又吃了1/3，请修改记录',
    '晚餐妈妈吃了1/2，请修改记录',
    '晚餐我吃了1/2，不要修改记录',
    '晚餐我吃了1/0，请修改记录',
])
def test_ambiguous_or_nonself_portion_does_not_authorize_update(message):
    assert _parse_explicit_diet_correction(message) is None


def test_supplement_recommendation_is_not_fast_simple_read():
    assert not _is_fast_eligible_turn('应该吃什么样的补剂？', has_images=False, has_file=False)


def test_high_risk_tool_round_cannot_downgrade(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._staged_answer_task_tier = 'high_stakes'
    monkeypatch.setattr('app.services.agent_executor.settings.task_tiered_routing', True)
    assert executor._maybe_fast_route_tool_round(None) is None


@pytest.mark.asyncio
async def test_valid_but_ambiguous_portion_gets_scope_clarification(monkeypatch):
    from app.services.agent_executor import _SimpleRecordTerminal
    executor = AgentExecutor(None)
    executor._current_turn_user_message = '晚餐我吃了1/2的蛋糕，请修改记录'
    calls = [{'id': 'portion', 'function': {'name': 'health_manage', 'arguments': json.dumps({
        'record_type': 'diet', 'operation': 'update', 'record_id': 1, 'data': {},
    })}}]
    with pytest.raises(_SimpleRecordTerminal) as error:
        await executor._normalize_explicit_diet_update_tool_calls(calls, None)
    assert '整餐' in str(error.value)
    assert '请用 1/2' not in str(error.value)


@pytest.mark.parametrize('mode', ['off', 'shadow', 'on'])
def test_high_risk_quality_floor_is_independent_of_staged_experiment(db, monkeypatch, mode):
    executor = AgentExecutor(db)
    executor._request_model_id = 'qwen3.6-flash'
    executor._current_user_id = 41
    monkeypatch.setattr('app.services.agent_executor.settings.staged_response_mode', mode)
    monkeypatch.setattr('app.services.llm.task_routing.pick_model_id_by_tier', lambda *a, **k: 'qwen3.8-max-preview')
    executor._configure_staged_answer_routing('应该吃什么样的补剂？', has_attachments=False)
    assert executor._request_model_id == 'qwen3.8-max-preview'
    assert not executor._fast_route_simple_turn


def test_high_stakes_provider_failure_cannot_use_fast_user_preference(db, monkeypatch):
    from types import SimpleNamespace
    executor = AgentExecutor(db)
    executor._current_user_id = 41
    executor._request_model_id = 'qwen3.6-flash'
    monkeypatch.setattr('app.services.agent_executor.settings.staged_response_mode', 'off')
    monkeypatch.setattr('app.services.llm.task_routing.pick_model_id_by_tier', lambda *a, **k: 'qwen3.8-max-preview')
    executor._configure_staged_answer_routing('应该吃什么样的补剂？', has_attachments=False)
    assert executor._request_model_id == 'qwen3.8-max-preview'
    assert executor._staged_answer_task_tier == 'high_stakes'
    def broken_quality(*a, **k):
        raise RuntimeError('Synthetic quality provider unavailable')
    fallback = SimpleNamespace(model='qwen3.6-flash', provider_name='synthetic')
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_model_id', broken_quality)
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_user', lambda *a, **k: fallback)
    monkeypatch.setattr(executor, '_user_effective_model_id', lambda: 'qwen3.6-flash')
    try:
        provider, _ = executor._resolve_chat_provider([])
    except RuntimeError:
        return
    print('REVIEW_HIGH_STAKES_FALLBACK', executor._staged_answer_task_tier, provider.model)
    assert provider.model != 'qwen3.6-flash', 'Quality provider failure must not downgrade high stakes answer'


@pytest.mark.parametrize("entry", ["assert", "stable"])
def test_high_stakes_alternate_routes_cannot_use_fast(db, entry):
    executor = AgentExecutor(db)
    executor._staged_answer_task_tier = "high_stakes"
    with pytest.raises(RuntimeError):
        if entry == "assert":
            executor._assert_recovery_quality_model("qwen3.6-flash")
        else:
            executor._stable_fallback_provider(False)


def test_meal_result_at_limit_never_proves_complete():
    from datetime import datetime
    from types import SimpleNamespace
    from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan
    from app.services.agent_daily_read_execution import daily_result_goal
    plan = resolve_daily_read_plan("今天晚上我吃了什么", datetime(2026, 9, 12))
    args = plan.diet_list_args()
    assert args["limit"] == 100
    decision = SimpleNamespace(action="allow", normalized_tool_name="health_manage", normalized_args=args)
    goal = daily_result_goal(plan, decision, [{"record_date": plan.start_date, "meal_type": "dinner"}] * 100)
    assert goal["status"] == "failed"
    assert goal["reason_code"] == "query_result_truncated"


@pytest.mark.parametrize("mode", ["off", "shadow", "on"])
def test_high_stakes_never_trims_thinking(db, monkeypatch, mode):
    executor = AgentExecutor(db)
    executor._staged_response_mode = mode
    executor._staged_answer_task_tier = "high_stakes"
    executor._last_effective_model_id = "qwen3.8-max-preview"
    executor._turn_synthesis_skip_thinking = True
    monkeypatch.setattr("app.services.agent_executor.settings.synthesis_thinking_budget", 100)
    kwargs = {}
    executor._maybe_apply_synthesis_thinking_budget(kwargs)
    assert kwargs == {}
