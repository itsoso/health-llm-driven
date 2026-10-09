"""Planning horizon is not a read window or a health-record owner."""
from dataclasses import replace

import pytest

from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_sleep_oxygen_read_scope import snapshot, decide
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock, owned_data as owned_data,
)

TODAY_RECOMMENDATION = '今天是否适合运动？给我推荐适合我的运动的方式以及运动的强度，最终生成一个HTML页面。'

CONTEXT_PLAN = '基于我的身体状况，体检报告，以及历史记录的病症，帮我制定10天的锻炼恢复计划。'
PLANS = ['帮我制定未来十天的锻炼计划', '制定未来十天的锻炼计划',
         '请为我设计未来14天的运动计划', '帮我起草下周的训练计划']


@pytest.mark.parametrize('text', [CONTEXT_PLAN, *PLANS])
def test_plan_modifiers_are_not_foreign_owners(text):
    assert not health_read_has_nonself_subject(text)


@pytest.mark.parametrize('text', PLANS)
def test_draft_does_not_authorize_history_but_wrong_read_can_recover(text):
    from app.services.agent_policy_retry import is_repairable_read_reason
    result = decide({'dimension': 'workout'}, text)
    assert result.action == 'block'
    assert is_repairable_read_reason(result.reason)


@pytest.mark.parametrize('dimension', ['medical_exam', 'illness'])
def test_expressed_basis_authorizes_only_that_context(dimension):
    result = decide({'dimension': dimension}, CONTEXT_PLAN)
    assert result.action == 'allow', result.reason
    assert result.normalized_args == {'dimension': dimension}


@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
@pytest.mark.parametrize('args', [
    {'dimension': 'illness', 'user_id': 42},
    {'dimension': 'illness', 'days': 10},
    {'dimension': 'illness', 'keyword': 'other'},
    {'dimension': 'medical_exam', 'start_date': '2031-04-05'},
    {'dimension': 'genetic'}, {'dimension': 'workout'},
])
async def test_plan_cannot_expand_context_or_use_future_horizon(mode, args):
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    result = await ToolGateway(replace(snapshot(CONTEXT_PLAN), policy_mode=mode)).execute(
        ToolExecutionRequest('health_query', args), dispatch)
    assert result.decision.action == 'block'
    assert not calls


@pytest.mark.parametrize('text', [
    CONTEXT_PLAN.replace('我的身体', '张三的身体'),
    CONTEXT_PLAN.replace('体检报告', '朋友的体检报告'),
    CONTEXT_PLAN.replace('历史记录', '张三的历史记录'),
    CONTEXT_PLAN + '只看检查之后。', CONTEXT_PLAN + '不要读取记录。',
    '假如' + CONTEXT_PLAN, '“' + CONTEXT_PLAN + '”',
    '分析例句：' + CONTEXT_PLAN, CONTEXT_PLAN + '并删除病史。',
])
def test_unknown_owner_filter_or_speech_act_cannot_grant_plan_basis(text):
    assert decide({'dimension': 'illness'}, text).action == 'block'


@pytest.mark.parametrize('tool', ['health_record', 'manage_plan', 'health_analysis'])
def test_plan_basis_grants_no_write_or_unbounded_analysis(tool):
    assert decide({}, CONTEXT_PLAN, tool).action == 'block'


def test_tool_exposure_uses_same_plan_contract():
    from app.services.agent_input_tool_scope import scope_tools_for_exercise_plan
    tools = [{'function': {'name': n}} for n in ['health_query', 'health_query_batch',
             'health_manage', 'health_analysis', 'manage_plan', 'knowledge_search']]
    assert [t['function']['name'] for t in scope_tools_for_exercise_plan(tools, PLANS[0])] == ['knowledge_search']
    assert [t['function']['name'] for t in scope_tools_for_exercise_plan(tools, CONTEXT_PLAN)] == ['health_query', 'health_query_batch', 'knowledge_search']


def test_plan_requires_matching_authenticated_owner():
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    turn = snapshot(CONTEXT_PLAN)
    for owner in (42, None, True):
        result = decide_tool_capability(replace(turn, context=replace(turn.context, user_id=owner)),
                                       ToolExecutionRequest('health_query', {'dimension': 'illness'}))
        assert result.action == 'block'


@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('text', [*PLANS[:2], TODAY_RECOMMENDATION])
async def test_real_pi_draft_finishes_without_personal_reads(db, owned_data, monkeypatch, panel, text):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume, ANSWER
    trace = batch_trace(db, monkeypatch, [ANSWER])
    done, saved = await consume(db, trace, owned_data, panel=panel, query=text)
    assert not trace.dispatches
    assert trace.executor._current_turn_user_message == text
    if 'HTML' in text:
        assert any(m.get('role') == 'user' and 'HTML' in str(m.get('content', '')) for m in trace.calls[0][0])
    assert done['turn_outcome']['status'] == 'complete', (done['turn_outcome'], trace.executor._turn_composed_read_executions)
    assert '只能查询' not in saved.content
    assert all(t['function']['name'] == 'knowledge_search' for t in trace.calls[0][1])
    # Fixtures replace the heavy system prompt. Check production prompt hook.
    assert '不是历史查询窗口' in trace.executor._exercise_plan_prompt_parts(trace.executor._agent_kernel_snapshot)[0]


@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('model_skips_read', [False, True])
async def test_real_pi_context_read_keeps_old_owned_illness_and_excludes_others(
    db, owned_data, monkeypatch, panel, model_skips_read,
):
    from datetime import date
    from app.models.illness import IllnessEpisode
    from app.models.user import User
    from tests.test_agent_read_repair_round_budget import batch_trace, consume, ANSWER
    other = db.query(User).filter(User.id != owned_data.id).first()
    db.add_all([
        IllnessEpisode(user_id=owned_data.id, name='Synthetic-old-owned', start_date=date(2025, 1, 1)),
        IllnessEpisode(user_id=other.id, name='Synthetic-foreign', start_date=date(2025, 1, 1)),
        IllnessEpisode(user_id=owned_data.id, name='Synthetic-future', start_date=date(2035, 1, 1)),
    ])
    db.commit()
    queries = [{'dimension': d} for d in ('medical_exam', 'illness')]
    first = '准备根据依据生成计划。' if model_skips_read else [('health_query_batch', {'queries': queries})]
    trace = batch_trace(db, monkeypatch, [first, ANSWER])
    done, saved = await consume(db, trace, owned_data, panel=panel, query=CONTEXT_PLAN)
    assert len(trace.dispatches) == 1
    assert trace.dispatches[0].arguments == {'queries': queries}
    content = trace.results[0][1]
    assert 'Synthetic-old-owned' in content
    assert 'Synthetic-foreign' not in content
    assert 'Synthetic-future' not in content
    assert done['turn_outcome']['status'] == 'complete', (done['turn_outcome'], trace.executor._turn_composed_read_executions)
    assert '只能查询' not in saved.content


@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('first', [
    ('health_query', {'dimension': 'medical_exam'}),
    ('knowledge_search', {'query': '一般运动注意事项'}),
])
async def test_partial_or_knowledge_first_cannot_skip_required_evidence(db, owned_data, monkeypatch, panel, first):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume, ANSWER
    trace = batch_trace(db, monkeypatch, [[first], '准备根据依据生成计划。', ANSWER])
    # Knowledge service is an external boundary, not evidence for user history.
    original = trace.executor._dispatch_tool_request
    async def dispatch(request, token):
        if request.tool_name == 'knowledge_search':
            return '通用知识，不包含个人资料。'
        return await original(request, token)
    monkeypatch.setattr(trace.executor, '_dispatch_tool_request', dispatch)
    done, _ = await consume(db, trace, owned_data, panel=panel, query=CONTEXT_PLAN)
    assert done['turn_outcome']['status'] == 'complete'
    goals = {g['goal_id']: g['status'] for g in done['turn_outcome']['goals']}
    assert goals == {'plan_basis_medical_exam': 'verified', 'plan_basis_illness': 'verified'}
    queries = trace.dispatches[-1].arguments['queries']
    assert {'dimension': 'illness'} in queries
    assert len(queries) == (1 if first[0] == 'health_query' else 2)


@pytest.mark.parametrize('panel', [False, True])
async def test_failed_plan_basis_never_becomes_successful_personal_plan(db, owned_data, monkeypatch, panel):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume, ANSWER
    from app.services import health_read
    original = health_read.canonical_read
    def read(db, user_id, dimension, **kwargs):
        if dimension == 'illness':
            return 'Error: synthetic unavailable'
        return original(db, user_id, dimension, **kwargs)
    monkeypatch.setattr(health_read, 'canonical_read', read)
    trace = batch_trace(db, monkeypatch, [[('health_query_batch', {'queries': [
        {'dimension': 'medical_exam'}, {'dimension': 'illness'}]})], ANSWER])
    done, saved = await consume(db, trace, owned_data, panel=panel, query=CONTEXT_PLAN)
    assert done['turn_outcome']['status'] != 'complete'
    assert '尚未查询完成' in saved.content
    assert len(trace.calls) == 2  # no unbounded retry


@pytest.mark.parametrize('text', [TODAY_RECOMMENDATION,
    TODAY_RECOMMENDATION.replace('，最终生成一个HTML页面。', '。'),
    '今天我是否适合运动？请给我推荐适合我的运动方式以及运动强度，最后生成一个HTML页面。',
])
def test_today_recommendation_is_only_a_draft_not_personal_read_authority(text):
    from app.services.agent_kernel.exercise_plan_scope import resolve_exercise_plan_scope
    scope = resolve_exercise_plan_scope(text)
    assert scope is not None
    assert scope.horizon == '今天'
    assert scope.evidence_dimensions == ()
    assert scope.queries() == []
    assert not health_read_has_nonself_subject(text)
    for dimension in ['activity', 'sleep', 'workout', 'medical_exam', 'illness']:
        decision = decide({'dimension': dimension}, text)
        assert decision.action == 'block'
        assert decision.reason != 'health_query_subject_not_current_user'


@pytest.mark.parametrize('text', [
    TODAY_RECOMMENDATION.replace('我的运动', '张三的运动'),
    '“' + TODAY_RECOMMENDATION + '”',
    '分析例句：' + TODAY_RECOMMENDATION,
    '假如' + TODAY_RECOMMENDATION,
    TODAY_RECOMMENDATION + '不要读取记录。',
    TODAY_RECOMMENDATION + '并删除病史。',
    TODAY_RECOMMENDATION + '附加未知条件。',
    TODAY_RECOMMENDATION.replace('最终生成一个HTML页面', '最终读取所有病史并生成一个HTML页面'),
    TODAY_RECOMMENDATION.replace('今天是否', '不要判断今天是否'),
    TODAY_RECOMMENDATION.replace('今天是否', '根据刚才那份报告，今天是否'),
])
def test_today_recommendation_rejects_unconsumed_authority_or_output_tail(text):
    from app.services.agent_kernel.exercise_plan_scope import resolve_exercise_plan_scope
    assert resolve_exercise_plan_scope(text) is None


@pytest.mark.parametrize('panel', [False, True])
async def test_today_draft_recovers_from_model_proposed_unrequested_personal_read(db, owned_data, monkeypatch, panel):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume, ANSWER
    trace = batch_trace(db, monkeypatch, [[('health_query', {'dimension': 'workout'})], ANSWER])
    done, saved = await consume(db, trace, owned_data, panel=panel, query=TODAY_RECOMMENDATION)
    assert not trace.dispatches
    assert done['turn_outcome']['status'] == 'complete'
    assert len(trace.calls) == 2
    assert '只能查询' not in saved.content


@pytest.mark.parametrize('base', [*PLANS, CONTEXT_PLAN])
def test_html_format_suffix_preserves_the_existing_draft_authority(base):
    from app.services.agent_kernel.exercise_plan_scope import resolve_exercise_plan_scope
    assert resolve_exercise_plan_scope(base.rstrip('。') + '，最终生成一个HTML页面。') == resolve_exercise_plan_scope(base)
