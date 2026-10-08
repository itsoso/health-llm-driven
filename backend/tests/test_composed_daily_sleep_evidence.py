"""Daily sleep quantities need sleep evidence, not the workout veto."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
import pytest
from app.services.agent_composed_read_completion import evaluate_composed_read_completion, project_composed_answer_quality
from app.services.agent_output_quality import enforce_agent_output_quality
from tests.test_agent_composed_read_completion import execution, scope


def daily_completion(days=31):
    completion = evaluate_composed_read_completion(scope('diet','sleep'), [execution(),
        execution('sleep', rows=[{'record_date':'2026-09-12','total_sleep_duration':420,'sleep_score':80,'sources':{'total_sleep_duration':'garmin','sleep_score':'garmin'}}])])
    evidence = deepcopy(completion.verified_evidence)
    query = next(q for q in evidence['queries'] if q['query']['dimension']=='sleep')
    start = date(2026,8,14)
    query['query'].update(start_date=start.isoformat(), end_date=(start+timedelta(days=days-1)).isoformat())
    row = query['records'][0]
    query['records'] = [dict(deepcopy(row), record_index=i) for i in range(days)]
    for i,r in enumerate(query['records']): r['known_fields']['record_date']=(start+timedelta(days=i)).isoformat()
    query['record_count']=days
    return replace(completion, verified_evidence=evidence), query

@pytest.mark.parametrize('text', [
    '睡眠：31天均为Garmin来源，已返回的每日总睡眠420分钟、评分80分。',
    '睡眠记录每日总时长为7小时。',
    '已记录的每日睡眠总时长均为420分钟。',
])
def test_keep_verified_daily_sleep_quantities(text):
    completion, _ = daily_completion()
    original = enforce_agent_output_quality(text)
    result = project_composed_answer_quality(original, completion)
    assert result.text == original.text and result.flags == original.flags

@pytest.mark.parametrize('mutation,text', [
    ('missing_day','每日总睡眠420分钟。'),
    ('missing_duration','每日总睡眠420分钟。'),
    ('different_duration','每日总睡眠420分钟。'),
    ('duplicate_day','每日总睡眠420分钟。'),
    ('none','每日总睡眠480分钟。'),
    ('wrong_source','睡眠：31天均为Garmin来源，已返回的每日总睡眠420分钟、评分80分。'),
    ('none','睡眠：32天均为Garmin来源，已返回的每日总睡眠420分钟、评分80分。'),
    ('missing_score','睡眠记录每日总时长7小时、评分80分。'),
    ('none','睡眠记录每日深睡眠总时长7小时。'),
    ('none','睡眠记录每日REM睡眠总时长7小时。'),
    ('none','请按照已有记录每天维持睡眠总时长7小时。'),
    ('none','你可以参照记录每天睡眠总时长7小时。'),
    ('none','睡眠记录每日总时长7小时、评分90分。'),
    ('none','睡眠记录每日总时长7小时，是本人的完整睡眠。'),
    ('none','建议保持睡眠记录每日总时长7小时。'),
    ('none','每天总睡眠420分钟，是本人的完整睡眠。'),
    ('none','每日总睡眠8小时。'),
    ('none','每日总睡眠420分钟，其中深睡420分钟。'),
    ('none','每日睡眠包含一次420分钟的整夜睡眠。'),
    ('none','运动记录每天30分钟。'),
])
def test_keep_veto_for_unverified_daily_quantities(mutation,text):
    completion, query = daily_completion()
    if mutation=='missing_day': query['records'].pop()
    elif mutation=='missing_duration': query['records'][0]['known_fields'].pop('total_sleep_duration')
    elif mutation=='different_duration': query['records'][0]['known_fields']['total_sleep_duration']=480
    elif mutation=='wrong_source': query['records'][0]['known_fields']['sources']['total_sleep_duration']='apple_health'
    elif mutation=='missing_score': query['records'][0]['known_fields'].pop('sleep_score')
    elif mutation=='duplicate_day': query['records'].append(deepcopy(query['records'][0]))
    result=project_composed_answer_quality(enforce_agent_output_quality(text),completion)
    assert 'unsupported_daily_coverage_removed' in result.flags
    assert text not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize('variant', ['baseline','runtime_preplan'])
async def test_actual_pi_keeps_verified_daily_sleep_text(db, auth_user_and_headers, monkeypatch, variant):
    from app.config import settings
    from eval.full_task_prompt_benchmark import Scenario, ScriptedProvider, CallBudget, run_sample, seed_synthetic_records
    monkeypatch.setattr(settings, 'app_env', 'test')
    user, _ = auth_user_and_headers
    scenario=Scenario('sleep-evidence-replay',31,'available',allow_knowledge=True,dense_records=True)
    seed_synthetic_records(db,user.id,scenario)
    answer='睡眠：31天均为Garmin来源，已返回的每日总睡眠420分钟、评分80分。'
    class RecordedAnswer(ScriptedProvider):
        async def chat_stream(self, **kwargs):
            if kwargs.get('tools'):
                async for event in super().chat_stream(**kwargs): yield event
            else:
                yield {'type':'content','text':answer}
                yield {'type':'finish','finish_reason':'stop'}
    row=await run_sample(db,user.id,scenario,variant,'qwen3.8-flash',CallBudget(3),
        live=False,provider_factory=lambda: RecordedAnswer(scenario))
    assert row['status']=='passed_contracts',row
    assert answer in row['answer']
    assert '部分描述缺少记录依据' not in row['answer']
    assert len(row['calls'])==(2 if variant=='baseline' else 1)
