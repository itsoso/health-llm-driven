"""Morning advice questions are answer goals, not implicit personal reads."""
import pytest

from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock, owned_data as owned_data,
)

QUESTIONS = [
    '今天应该如何制定锻炼计划',
    '今天该怎么安排运动计划？',
    '我今天应该如何制定锻炼计划',
]
INSPIRATION = ['给我一些启发', '请给我一点思路。']


@pytest.fixture(autouse=True)
def _isolate_transport(isolated_agent_protocol_transport):
    pass


@pytest.mark.parametrize('text', QUESTIONS)
def test_today_question_is_a_draft_without_read_authority(text):
    from app.services.agent_kernel.exercise_plan_scope import resolve_exercise_plan_scope
    from tests.test_sleep_oxygen_read_scope import decide
    scope = resolve_exercise_plan_scope(text)
    assert scope is not None
    assert scope.horizon == '今天' and scope.evidence_dimensions == ()
    assert decide({'dimension': 'workout'}, text).action == 'block'


@pytest.mark.parametrize('text', INSPIRATION)
def test_inspiration_has_only_current_input_answer_scope(text):
    from app.services.agent_kernel.current_input_advice_scope import is_current_input_advice
    from app.services.agent_input_tool_scope import scope_tools_for_current_input_advice
    assert is_current_input_advice(text)
    tools = [{'function': {'name': n}} for n in ['health_query', 'health_record', 'knowledge_search']]
    assert [t['function']['name'] for t in scope_tools_for_current_input_advice(tools, text)] == ['knowledge_search']
    from tests.test_sleep_oxygen_read_scope import decide
    assert decide({'dimension': 'sleep'}, text).action == 'block'


@pytest.mark.parametrize('text', [
    '妈妈今天应该如何制定锻炼计划',
    '“今天应该如何制定锻炼计划”',
    '假如今天应该如何制定锻炼计划',
    '今天应该如何制定锻炼计划，并查询我的病史',
    '今天应该如何制定锻炼计划，不要回答',
    '给我一些启发，查询昨天睡眠',
    '给我一些启发并删除记录',
    '“给我一些启发”',
    '不要给我一些启发',
])
def test_unknown_clause_is_not_erased_for_answer_recovery(text):
    from app.services.agent_kernel.exercise_plan_scope import resolve_exercise_plan_scope
    from app.services.agent_kernel.current_input_advice_scope import is_current_input_advice
    assert resolve_exercise_plan_scope(text) is None
    assert not is_current_input_advice(text)


@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('text', [QUESTIONS[0], INSPIRATION[0]])
async def test_real_pi_morning_answer_finishes_and_persists_without_reads(db, owned_data, monkeypatch, panel, text):
    monkeypatch.setattr('tests.test_agent_read_repair_round_budget.ANSWER',
                        '本轮未查询个人记录。可以先明确目标，再选择轻松活动；有不适时暂停。')
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    trace = batch_trace(db, monkeypatch, ['本轮未查询个人记录。可以先明确目标，再选择轻松活动；有不适时暂停。'])
    done, saved = await consume(db, trace, owned_data, panel=panel, query=text)
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['status'] == 'complete'
    assert not trace.dispatches
    assert '本轮数据查询未完成' not in saved.content
    assert all(t['function']['name'] == 'knowledge_search' for t in trace.calls[0][1])
