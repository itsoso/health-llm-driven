"""Owned multi-query prompts keep safety/profile, not unverified daily summaries."""
import copy
import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.models.agent_conversation import AgentMessage
from app.models.daily_health import DietRecord
from app.models.user_profile import UserProfile
from app.services.agent_executor import AgentExecutor, _CLINICIAN_PROVENANCE_PROMPT_BLOCK
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from tests.test_agent_longitudinal_read_regression import ANALYSIS_REQUESTS
from tests.test_health_context_lite import _add_clinician_feedback


@pytest.fixture(autouse=True)
def isolated(isolated_agent_protocol_transport, monkeypatch):
    from app.services import health_context_lite_service as context
    from app.twin.schema import HealthTwin, TwinMeta
    context._context_cache.clear()
    context._context_cache_entry_generations.clear()
    monkeypatch.setattr('app.twin.builder.build_twin', lambda _db, user_id, **kw:
        HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now().astimezone())))
    yield
    context._context_cache.clear()
    context._context_cache_entry_generations.clear()


@pytest.fixture
def seeded(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    db.add(UserProfile(user_id=user.id, chronic_conditions=['PROFILE_CONDITION'],
        allergies=['PROFILE_ALLERGY'], current_medications=[{'name': 'PROFILE_MEDICATION'}]))
    db.add_all([DietRecord(user_id=user.id, record_date=date.today(), meal_type=meal,
        food_name='KNOWN_FOOD', food_items='KNOWN_ITEMS', calories=calories, protein=None)
        for meal, calories in [('breakfast', 300), ('breakfast', 300), ('dinner', 420)]])
    _add_clinician_feedback(db, user_id=user.id, generated_at=datetime.now(),
                            assessment='OWNED_CLINICIAN')
    db.commit()
    return user


def sentinels(monkeypatch):
    for module, name in [
        ('originator_recommendations', 'originator_recs_prompt_blob'),
        ('liver_health', 'liver_prompt_blob'), ('blood_routine', 'blood_routine_prompt_blob'),
        ('medication_course_service', 'course_prompt_blob'),
        ('intervention_cycle_service', 'intervention_proposal_prompt_blob'),
        ('effect_estimator', 'effect_estimate_prompt_blob'),
    ]:
        monkeypatch.setattr(f'app.services.{module}.{name}', lambda *a, **k: 'DYNAMIC_BLOB')
    monkeypatch.setattr('app.services.health_worldview.worldview_prompt_blob',
                        lambda **k: 'STATIC_TRIAGE' if k.get('include_triage') else 'NO_TRIAGE')
    monkeypatch.setattr('app.services.gene_rules_registry.get_registry', lambda:
                        SimpleNamespace(system_prompt_section=lambda **k: 'STATIC_GENE_WARNING'))


def assert_profile_prompt(prompt):
    for value in ('今日饮食:', '今日饮水:', 'DYNAMIC_BLOB', '蛋白质0g'):
        assert value not in prompt
    for value in ('PROFILE_CONDITION', 'PROFILE_ALLERGY', 'PROFILE_MEDICATION',
                  'OWNED_CLINICIAN', 'STATIC_GENE_WARNING', 'STATIC_TRIAGE',
                  '安全与边界 (R4', '不做诊断', '自我标识', '确认卡片必须由用户亲自点击'):
        assert value in prompt, value
    for rule in _CLINICIAN_PROVENANCE_PROMPT_BLOCK:
        assert rule in prompt


@pytest.mark.parametrize('domain_enabled', [False, True])
@pytest.mark.parametrize('panel', [False, True])
def test_owned_scope_selects_profile_budget_even_without_panel_intent(db, seeded, monkeypatch, domain_enabled, panel):
    sentinels(monkeypatch)
    monkeypatch.setattr('app.services.agent_executor.settings.domain_prompt_optimization', domain_enabled)
    executor = AgentExecutor(db)
    executor._start_agent_kernel_turn(user_id=seeded.id, message=ANALYSIS_REQUESTS[0], channel='typed')
    scope = resolve_owned_read_scope(executor._agent_kernel_snapshot)
    assert len(scope.queries) == 4
    prompt = executor._build_system_prompt(seeded.id, 1, None,
        intent_query=None if panel else ANALYSIS_REQUESTS[0])
    assert_profile_prompt(prompt)


@pytest.mark.parametrize('query', [
    None, '今天我吃的怎么样?', '不要查询我的日常睡眠和饮食记录，也别分析。',
    '查询我朋友近期睡眠和饮食记录，再分析。',
    '解释以下例句：“请查询我的日常睡眠和饮食记录，再给建议。”',
])
def test_no_owned_multiquery_keeps_existing_context(db, seeded, monkeypatch, query):
    sentinels(monkeypatch)
    executor = AgentExecutor(db)
    if query:
        executor._start_agent_kernel_turn(user_id=seeded.id, message=query, channel='typed')
    prompt = executor._build_system_prompt(seeded.id, 1, None, intent_query=query)
    assert '今日饮食:' in prompt


def test_prompt_builder_does_not_create_snapshot_or_reuse_other_owner_scope(db, seeded, monkeypatch):
    from app.services import health_context_lite_service as context
    sentinels(monkeypatch)
    executor = AgentExecutor(db)
    assert executor._agent_kernel_snapshot is None
    executor._build_system_prompt(seeded.id, 1, None, intent_query=ANALYSIS_REQUESTS[0])
    assert executor._agent_kernel_snapshot is None
    executor._start_agent_kernel_turn(user_id=seeded.id + 100, message=ANALYSIS_REQUESTS[0], channel='typed')
    seen = []
    original = context.build_lite_health_context
    def capture(*args, **kwargs):
        seen.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(context, 'build_lite_health_context', capture)
    executor._build_system_prompt(seeded.id, 1, None, intent_query=ANALYSIS_REQUESTS[0])
    assert seen and not seen[0].get('owned_read_profile')


def test_owned_budget_cache_and_clinician_overlay_are_owner_isolated(db, seeded, monkeypatch):
    from app.models.user import User
    from app.services import health_context_lite_service as context
    other = User(name='Other synthetic owner', email='other-context@example.test')
    db.add(other)
    db.flush()
    _add_clinician_feedback(db, user_id=other.id, generated_at=datetime.now(),
                            assessment='OTHER_CLINICIAN')
    db.commit()
    builds = []
    original = context._build_context
    def build(db, user_id, budget):
        builds.append((user_id, budget))
        return original(db, user_id, budget)
    monkeypatch.setattr(context, '_build_context', build)
    full = context.build_lite_health_context(db, seeded.id)
    owned = context.build_lite_health_context(db, seeded.id, owned_read_profile=True)
    minimal = context.build_lite_health_context(db, seeded.id, intent='什么是睡眠？')
    assert '今日饮食:' in full and '今日饮食:' not in owned
    assert 'OWNED_CLINICIAN' in owned and 'OTHER_CLINICIAN' not in owned
    assert 'OWNED_CLINICIAN' not in minimal
    assert len(builds) == 3 and len({budget for _, budget in builds}) == 3
    assert context.build_lite_health_context(db, seeded.id, owned_read_profile=True) == owned
    assert len(builds) == 3
    context.build_lite_health_context(db, other.id, owned_read_profile=True)
    context.invalidate_health_context(seeded.id)
    assert all(key[0] != seeded.id for key in context._context_cache)
    assert any(key[0] == other.id for key in context._context_cache)
    context.build_lite_health_context(db, seeded.id, owned_read_profile=True)
    assert len(builds) == 5


@pytest.mark.parametrize('kwargs', [{'static_rules_only': True}, {'health_evidence_runtime': True}])
def test_owned_scope_does_not_override_sealed_or_static_synthesis(db, seeded, monkeypatch, kwargs):
    sentinels(monkeypatch)
    executor = AgentExecutor(db)
    executor._start_agent_kernel_turn(user_id=seeded.id, message=ANALYSIS_REQUESTS[0], channel='typed')
    prompt = executor._build_system_prompt(seeded.id, 1, None, **kwargs)
    assert 'PROFILE_CONDITION' not in prompt and 'OWNED_CLINICIAN' not in prompt
    assert '安全与边界 (R4' in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize('panel', [False, True])
@pytest.mark.parametrize('outcome', ['complete', 'partial', 'generation_failure'])
async def test_real_pi_provider_projection_and_notices_once(db, seeded, monkeypatch, panel, outcome):
    sentinels(monkeypatch)
    executor = AgentExecutor(db)
    calls = []
    dimensions = ('diet', 'sleep', 'workout', 'supplements') if outcome == 'complete' else ('diet',)

    async def provider(messages, tools):
        calls.append(copy.deepcopy(messages))
        if len(calls) == 1:
            yield {'type': 'tool_calls', 'tool_calls': [
                {'id': f'owned-{d}', 'type': 'function', 'function': {
                    'name': 'health_query', 'arguments': json.dumps({'dimension': d, 'days': 7})}}
                for d in dimensions]}
            yield {'type': 'finish', 'finish_reason': 'tool_calls'}
        else:
            if outcome != 'generation_failure':
                yield {'type': 'content', 'text': '本次只依据已查询记录，未知字段不能视为零。'}
            yield {'type': 'finish', 'finish_reason': 'length' if outcome == 'generation_failure' else 'stop'}

    async def dispatch(request, token):
        d = request.arguments['dimension']
        rows = [{'record_date': request.arguments['end_date'], 'food_name': 'KNOWN_FOOD',
                 'food_items': 'KNOWN_ITEMS', 'meal_type': 'breakfast', 'calories': 300, 'protein': None}] if d == 'diet' else []
        return json.dumps({'dimension': d,
            'window': {k: request.arguments[k] for k in ('start_date', 'end_date', 'timezone')},
            'availability': 'available' if rows else 'no_data', 'records': rows,
            **({'source_scope': {'workout': 'owned_actual_workout_records',
                                'supplements': 'owned_actual_supplement_intake_logs'}[d]}
               if d in ('workout', 'supplements') else {})})

    class Provider:
        provider_name = 'synthetic'
        def __init__(self, model='qwen3.8-max-preview'):
            self.model = model
        async def chat_stream(self, **kwargs):
            async for event in provider(kwargs['messages'], kwargs.get('tools')):
                yield event
        async def chat(self, **kwargs):
            result = {'content': ''}
            async for event in provider(kwargs['messages'], kwargs.get('tools')):
                if event['type'] == 'content':
                    result['content'] += event['text']
                elif event['type'] == 'tool_calls':
                    result['tool_calls'] = event['tool_calls']
                elif event['type'] == 'finish':
                    result['finish_reason'] = event['finish_reason']
            return result
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_model_id',
                        lambda model_id, **kw: Provider(model_id))
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_user', lambda *a, **k: Provider())
    monkeypatch.setattr('app.services.llm.factory.get_llm_provider', lambda *a, **k: Provider())
    monkeypatch.setattr(executor, '_dispatch_tool_request', dispatch)
    monkeypatch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *a, **k: '')
    events = [e async for e in executor.run_stream(seeded.id, ANALYSIS_REQUESTS[0],
        extra_context=json.dumps({'multi_model': panel, 'model_id': 'qwen3.8-max-preview'}))]
    assert len(calls) >= 2
    for messages in calls[:2]:
        assert_profile_prompt(messages[0]['content'])
    tool_text = json.dumps([m for messages in calls for m in messages if m['role'] == 'tool'], ensure_ascii=False)
    assert 'KNOWN_FOOD' in tool_text and 'KNOWN_ITEMS' in tool_text
    assert '\\"protein\\": null' in tool_text
    done = events[-1]['data']
    saved = db.get(AgentMessage, done['message_id'])
    scope = resolve_owned_read_scope(executor._agent_kernel_snapshot)
    from app.services.agent_composed_read_completion import read_scope_notices
    for notice in read_scope_notices(scope):
        assert saved.content.count(notice) == 1
    assert saved.meta['turn_outcome'] == done['turn_outcome']
    assert ''.join(e['data'].get('content', '') for e in events if e.get('event') == 'token') == saved.content
    assert (done['turn_outcome']['status'] == 'complete') == (outcome == 'complete')
    assert not done.get('write_receipts')
