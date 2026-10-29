"""Personal dietary advice must read its declared evidence before synthesis."""
from dataclasses import replace
import json
import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_recent_workout_read_regression import snapshot

REQUEST = '建议我应该吃点啥，基于我的health系统中我个人的信息，包括基因、年龄、体重、季节等 给我健康饮食的分析和推荐'
VARIANTS = [REQUEST,
    '基于我的基因、年龄和体重，给我健康饮食建议。',
    '请结合我个人的年龄、体重、基因，推荐我吃什么。',
    '根据我的健康系统里本人的资料，包括年龄、体重、基因和季节，给我饮食分析和建议。',
]

@pytest.mark.parametrize('text', VARIANTS)
def test_explicit_personal_diet_basis_is_readable(text):
    assert not health_read_has_nonself_subject(text)
    for dimension in ('genetic', 'age', 'weight'):
        decision = decide_tool_capability(snapshot(text), ToolExecutionRequest('health_query', {'dimension': dimension}))
        assert decision.action == 'allow', decision.reason
        assert decision.normalized_args == {'dimension': dimension}

@pytest.mark.parametrize('text', [
    REQUEST.replace('我个人的信息', '朋友的信息'),
    REQUEST.replace('基因、年龄', '妈妈的基因、年龄'),
    '假如' + REQUEST, '“' + REQUEST + '”', '分析例句：' + REQUEST,
    REQUEST + '，不要查询个人数据', REQUEST + '，仅查2020年',
    REQUEST + '，删除记录', REQUEST + '，再查询妈妈的体重',
])
def test_unconsumed_material_never_grants_diet_evidence(text):
    for dimension in ('genetic', 'age', 'weight'):
        assert decide_tool_capability(snapshot(text), ToolExecutionRequest('health_query', {'dimension': dimension})).action == 'block'

@pytest.mark.parametrize('args', [
    {'dimension': 'weight', 'user_id': 42}, {'dimension': 'genetic', 'profile_id': 2},
    {'dimension': 'weight', 'days': 365}, {'dimension': 'medical_exam'},
    {'dimension': 'sleep'}, {'dimension': 'age', 'tenant_id': 2},
])
@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
async def test_diet_scope_rejects_model_expansion(args, mode):
    from app.services.agent_kernel.tool_gateway import ToolGateway
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    result = await ToolGateway(replace(snapshot(REQUEST), policy_mode=mode)).execute(ToolExecutionRequest('health_query', args), dispatch)
    assert result.decision.action == 'block'
    assert not calls

@pytest.mark.parametrize('owner', [None, True, -1, 42])
def test_diet_requires_authenticated_owner(owner):
    turn = snapshot(REQUEST)
    turn = replace(turn, context=replace(turn.context, user_id=owner))
    assert decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension': 'weight'})).action == 'block'

@pytest.mark.parametrize('tool', ['health_analysis', 'health_manage', 'health_record', 'manage_plan'])
def test_advice_grants_no_unbounded_tool(tool):
    assert decide_tool_capability(snapshot(REQUEST), ToolExecutionRequest(tool, {})).action == 'block'

@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('skip_reads', [False, True])
async def test_real_turn_reads_declared_basis_before_answer(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel, skip_reads):
    from datetime import date
    from app.models.weight import WeightRecord
    from tests.conftest import create_authenticated_user
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    user.birth_date = date(1990, 1, 1)
    other.birth_date = date(1970, 1, 1)
    db.add_all([WeightRecord(user_id=user.id, record_date=date(2026, 10, 20), weight=70),
                WeightRecord(user_id=other.id, record_date=date(2026, 10, 20), weight=150)])
    db.commit()
    queries = [{'dimension': d} for d in ('genetic', 'age', 'weight')]
    first = '已经充分了解你的资料。' if skip_reads else [('health_query_batch', {'queries': queries})]
    answer = '年龄36岁，体重记录70千克；基因资料不足。信息有限，先给有条件的通用搭配建议：蔬菜、全谷物和适量蛋白质。'
    monkeypatch.setattr('tests.test_agent_read_repair_round_budget.ANSWER', answer)
    trace = batch_trace(db, monkeypatch, [first, answer, answer])
    # Use the same fixture DB at the in-process transport boundary.
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, saved = await consume(db, trace, user, panel=panel, query=REQUEST)
    assert done['turn_outcome']['status'] == 'complete', done['turn_outcome']
    assert len(trace.dispatches) == 1
    assert trace.dispatches[0].arguments == {'queries': queries}
    result = trace.results[0][1]
    assert '150' not in result
    assert '70' in result
    assert 'age_years' in result
    import json
    age_payload = json.loads(next(row['data'] for row in json.loads(result)['results'] if row['dimension'] == 'age'))
    assert set(age_payload) == {'age_years', 'as_of', 'source'}
    assert age_payload['age_years'] == 36
    assert 'email' not in result
    assert '只能查询当前登录用户' not in saved.content
    assert '已经充分了解' not in saved.content
    assert len(done['turn_outcome']['goals']) == 4
    assert not done['write_receipts']

@pytest.mark.parametrize('panel', [False, True])
async def test_diet_enters_evidence_only_synthesis_immediately_after_reads(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    answer = '年龄、体重和基因资料有限。在无相应禁忌时，可选择蔬菜配全谷物和鱼肉。'
    trace = batch_trace(db, monkeypatch, [[('health_query_batch', {'queries': [
        {'dimension': d} for d in ('genetic', 'age', 'weight')]})], answer, answer])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, saved = await consume(db, trace, user, panel=panel, query=REQUEST)
    messages, tools = trace.calls[1]
    assert tools == []
    assert len(messages) == 2
    evidence = json.loads(messages[1]['content'])
    assert evidence['request'] == REQUEST
    assert set(evidence) == {'request', 'current_time', 'timezone', 'read_results'}
    assert evidence['read_results']
    assert len(trace.dispatches) == 1
    assert done['turn_outcome']['status'] == 'complete'
    assert '可选择蔬菜' in saved.content


async def test_age_reader_projects_only_owned_age_and_missing_is_explicit(db, auth_user_and_headers):
    from datetime import date
    from app.services.personal_diet_read import read_age
    from tests.conftest import create_authenticated_user
    user, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    user.birth_date = date(1990, 10, 30)
    other.birth_date = date(1970, 1, 1)
    db.commit()
    assert read_age(db, user.id, date(2026, 10, 29)) == {'age_years': 35, 'as_of': '2026-10-29', 'source': 'account_birth_date'}
    user.birth_date = None
    db.commit()
    assert read_age(db, user.id, date(2026, 10, 29))['age_years'] is None
    with pytest.raises(ValueError):
        read_age(db, None, date(2026, 10, 29))

@pytest.mark.parametrize('panel', [False, True])
async def test_failed_diet_basis_is_not_reported_as_completed(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    from app.services import agent_read_tools
    user, _ = auth_user_and_headers
    monkeypatch.setattr(agent_read_tools, 'read_genetic_variants', lambda *a, **k: 'Error: synthetic unavailable')
    trace = batch_trace(db, monkeypatch, [[('health_query_batch', {'queries': [
        {'dimension': d} for d in ('genetic', 'age', 'weight')]})], '根据你的基因建议特殊饮食。'])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, saved = await consume(db, trace, user, panel=panel, query=REQUEST)
    assert done['turn_outcome']['status'] != 'complete'
    assert '尚未查询完成' in saved.content
    assert '根据你的基因建议特殊饮食' not in saved.content
    assert len(trace.calls) == 2

@pytest.mark.parametrize('text,expected', [
    ('基于我的年龄，给我饮食建议', ('age',)),
    ('基于我的体重，给我饮食建议', ('weight',)),
    ('基于我的基因和年龄，给我饮食建议', ('genetic', 'age')),
])
def test_diet_reads_only_named_basis(text, expected):
    from app.services.agent_kernel.personal_diet_scope import resolve_personal_diet_scope
    assert resolve_personal_diet_scope(text).evidence_dimensions == expected
    for dimension in set(('age', 'genetic', 'weight')) - set(expected):
        assert decide_tool_capability(snapshot(text), ToolExecutionRequest('health_query', {'dimension': dimension})).action == 'block'

@pytest.mark.parametrize('panel', [False, True])
async def test_data_only_answer_gets_one_synthesis_retry_then_remains_partial(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    trace = batch_trace(db, monkeypatch, ['已查询资料。', '已查询资料。', '已查询资料。'])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, saved = await consume(db, trace, user, panel=panel, query=REQUEST)
    assert done['turn_outcome']['status'] != 'complete'
    assert any(g['goal_id'] == 'personal_diet_answer' and g['status'] == 'failed' for g in done['turn_outcome']['goals'])
    assert len(trace.dispatches) == 1  # synthesis repair cannot read more
    assert len(trace.calls) == 3  # one bounded answer repair

@pytest.mark.parametrize('panel', [False, True])
async def test_synthesis_retry_can_finish_without_more_reads(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    answer = '年龄、体重和基因信息不足，不能据此给个体化判断。在没有相应饮食禁忌时，可选择蔬菜配全谷物和适量蛋白质。'
    trace = batch_trace(db, monkeypatch, ['已查询资料。', '已查询资料。', answer])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, saved = await consume(db, trace, user, panel=panel, query=REQUEST)
    assert done['turn_outcome']['status'] == 'complete', done['turn_outcome']
    assert '可选择蔬菜' in saved.content
    assert len(trace.dispatches) == 1
    assert len(trace.calls) == 3
    assert not trace.calls[-1][1]  # no tools in synthesis repair


@pytest.mark.parametrize('panel', [False, True])
async def test_complete_diet_draft_is_resynthesized_from_current_reads_only(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    contaminated = '年龄、体重和基因已查询。旧上下文标记：你今天已摄入780千卡，建议蔬菜少盐，每天总钠5g。'
    answer = '年龄、体重和基因资料有限。在无相应禁忌时，可选择蔬菜配全谷物和鱼肉；少用高盐酱料。'
    trace = batch_trace(db, monkeypatch, ['先查资料。', contaminated, answer])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, saved = await consume(db, trace, user, panel=panel, query=REQUEST)
    assert done['turn_outcome']['status'] == 'complete'
    assert '旧上下文标记' not in saved.content
    assert '总钠5g' not in saved.content
    assert len(trace.calls) == 3 and len(trace.dispatches) == 1
    assert not trace.calls[-1][1]
    assert '旧上下文标记' not in json.dumps(trace.calls[-1][0], ensure_ascii=False)


@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('bad_reply', [
    {'finish_reason': 'length', 'content': '年龄、体重和基因不足，建议蔬菜。'},
    {'finish_reason': 'stop', 'content': None},
    {'finish_reason': 'stop', 'content': '年龄、体重和基因不足，建议蔬菜。', 'tool_calls': [{'id': 'unexpected'}]},
    {'finish_reason': 'stop', 'content': '年龄、体重和基因不足，建议蔬菜，每天总钠少于5g。'},
    {'finish_reason': 'stop', 'content': '年龄、体重和基因不足，建议蔬菜，少油少盐（<5g/天总钠）。'},
    {'finish_reason': 'stop', 'content': '年龄、体重和基因不足，建议蔬菜，每天总钠少于 **5g**。'},
    {'finish_reason': 'stop', 'content': '年龄、体重和基因不足，建议蔬菜，钠：**5g/天**。'},
])
async def test_failed_evidence_synthesis_never_publishes_complete_untrusted_draft(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel, bad_reply):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    draft = '年龄、体重和基因已查询。旧上下文标记：建议蔬菜。'
    trace = batch_trace(db, monkeypatch, ['先查。', draft, bad_reply])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, saved = await consume(db, trace, user, panel=panel, query=REQUEST)
    assert done['turn_outcome']['status'] != 'complete'
    assert '旧上下文标记' not in saved.content
    assert '饮食分析和建议尚未完成' in saved.content
    assert len(trace.dispatches) == 1 and len(trace.calls) == 3


async def test_interrupted_diet_draft_never_escapes_evidence_boundary(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    draft = '年龄、体重和基因已查询。旧上下文标记：建议蔬菜。'
    trace = batch_trace(db, monkeypatch, ['先查。', {'finish_reason': 'length', 'content': draft}])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, saved = await consume(db, trace, user, query=REQUEST)
    assert done['turn_outcome']['status'] != 'complete'
    assert '旧上下文标记' not in saved.content

@pytest.mark.parametrize('reply', ['已查询基因年龄体重。', '年龄未知，体重未知，基因未知。尚未提供蔬菜建议。', '年龄体重基因。', '基因、年龄、体重已查询。需要我给你蔬菜搭配建议吗？', '基因、年龄、体重已查询。接下来我会给你关于蔬菜的建议。'])
def test_answer_goal_rejects_data_only_or_negated_advice(reply):
    from app.services.agent_kernel.personal_diet_scope import resolve_personal_diet_scope, personal_diet_answer_complete
    assert not personal_diet_answer_complete(resolve_personal_diet_scope(REQUEST), reply)


@pytest.mark.parametrize('advice', ['建议少盐清蒸鱼150克，搭配蔬菜。', '建议蔬菜200g，少放盐。', '建议少盐清蒸鱼**150克**，搭配蔬菜。'])
def test_food_portions_do_not_trigger_sodium_quantity_boundary(advice):
    from app.services.agent_kernel.personal_diet_scope import resolve_personal_diet_scope, personal_diet_answer_complete
    assert personal_diet_answer_complete(resolve_personal_diet_scope(REQUEST), '年龄、体重和基因信息有限。' + advice)

async def test_diet_genetic_read_keeps_user_and_active_profile_boundaries(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport):
    from datetime import date
    from app.models.genetic_data import GeneticProfile, GeneticVariant
    from tests.conftest import create_authenticated_user
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    monkeypatch.setattr('app.services.genetic_report._get_known_snps', lambda: {'rsSynthetic': {'gene': 'SyntheticOwned', 'variant': 'Synthetic'}})
    active = GeneticProfile(user_id=user.id, test_provider='synthetic', test_date=date(2026, 10, 1))
    old = GeneticProfile(user_id=user.id, test_provider='synthetic', test_date=date(2020, 1, 1))
    foreign = GeneticProfile(user_id=other.id, test_provider='synthetic', test_date=date(2026, 10, 2))
    db.add_all([active, old, foreign]); db.flush()
    db.add_all([GeneticVariant(user_id=uid, profile_id=pid, gene_name=name, category='nutrition')
                for uid, pid, name in [(user.id, active.id, 'SyntheticOwned'),
                                      (user.id, old.id, 'SyntheticOld'),
                                      (other.id, foreign.id, 'SyntheticForeign'),
                                      (other.id, active.id, 'SyntheticMismatched')]])
    db.commit()
    answer = '基因结果仅为检测记录，不能判断饮食禁忌。一般可选择蔬菜与全谷物搭配。'
    trace = batch_trace(db, monkeypatch, ['先读取。', answer, answer])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    done, _ = await consume(db, trace, user, query='基于我的基因，给我饮食建议')
    assert done['turn_outcome']['status'] == 'complete'
    result = trace.results[0][1]
    assert 'SyntheticOwned' in result
    assert all(name not in result for name in ('SyntheticOld', 'SyntheticForeign', 'SyntheticMismatched'))

async def test_diet_final_synthesis_uses_cancellable_stream(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    answer = '年龄、体重和基因资料有限。在无相应禁忌时，可选择蔬菜配全谷物和鱼肉。'
    trace = batch_trace(db, monkeypatch, ['先查资料。', answer, answer])
    async def in_process(reader, *args, **kwargs):
        return reader(db, *args, **kwargs)
    async def non_cancellable(*args, **kwargs):
        raise RuntimeError('non-streaming provider cannot cancel its worker thread')
    monkeypatch.setattr(trace.executor, '_read_in_process', in_process)
    monkeypatch.setattr(trace.executor, '_call_llm', non_cancellable)
    done, saved = await consume(db, trace, user, query=REQUEST)
    assert done['turn_outcome']['status'] == 'complete'
    assert '可选择蔬菜' in saved.content
    assert len(trace.calls) == 3 and not trace.calls[-1][1]

@pytest.mark.parametrize('model,verified,tools,expected', [
    ('qwen3.8-max', True, False, 1024),
    ('qwen3.8-max-preview', True, False, 1024),
    ('qwen3.8-max', False, False, None),
    ('qwen3.8-max', True, True, None),
    ('qwen3.8-flash', True, False, None),
])
def test_diet_thinking_budget_only_for_verified_projection_and_supported_model(db, monkeypatch, model, verified, tools, expected):
    from app.services.agent_executor import AgentExecutor
    ex = AgentExecutor(db)
    ex._last_effective_model_id = model
    messages = [{'role': 'system', 'content': 'synthetic evidence projection'}]
    monkeypatch.setattr(ex, '_personal_diet_synthesis_messages', lambda: messages if verified else None)
    kwargs = {'tools': [{'type': 'function'}]} if tools else {}
    ex._maybe_apply_personal_diet_thinking_budget(kwargs, messages)
    assert kwargs.get('thinking_budget') == expected
    assert 'enable_thinking' not in kwargs
