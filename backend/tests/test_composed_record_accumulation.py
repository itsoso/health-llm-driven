"""Closed record analysis must not turn into a new data collection assignment."""
import pytest
from app.services.agent_composed_read_completion import evaluate_composed_read_completion, project_composed_answer_quality
from app.services.agent_output_quality import enforce_agent_output_quality
from tests.test_agent_composed_read_completion import execution, scope
from tests.test_agent_read_repair_round_budget import four_domain_user as four_domain_user, owned_data as owned_data, clock as clock

@pytest.mark.parametrize('text,remove', [
    ('如需有效分析，建议先积累一段时间的连续记录。', True),
    ('建议积累更多记录后再分析。', True),
    ('请先积累一周记录。', True),
    ('你可以先积累连续记录。', True),
    ('已积累一段时间的连续记录。', False),
    ('不建议先积累连续记录。', False),
    ('无需积累更多记录。', False),
    ('医生建议积累连续记录属于既往背景，不能当作本轮医嘱。', False),
    ('建议先积累经验，而不是补录健康记录。', False),
])
def test_remove_new_accumulation_tasks_but_keep_facts_and_negations(text, remove):
    completion = evaluate_composed_read_completion(scope('diet','sleep'), [execution(),
        execution('sleep', rows=[{'record_date':'2026-09-12','total_sleep_duration':420,'sleep_score':80}])])
    assert completion.complete
    original = enforce_agent_output_quality(completion.trusted_fact_summary + '\n\n' + text)
    result = project_composed_answer_quality(original, completion)
    assert ('meta_query_invitation_removed' in result.flags) is remove
    assert (text in result.text) is not remove
    assert '评分80' in result.text and '时长7小时' in result.text

@pytest.mark.asyncio
@pytest.mark.parametrize('unsafe', [False, True])
async def test_actual_pi_removes_collection_request_without_hiding_medical_failure(db, four_domain_user, monkeypatch, unsafe):
    from tests.test_agent_composed_synthesis_projection import run_projection
    from tests.test_agent_read_repair_round_budget import ANSWER
    sentence = '如需有效分析，建议先积累一段时间的连续记录。'
    _, calls, _, done, saved = await run_projection(db, four_domain_user, monkeypatch,
        answer=('恢复良好。' if unsafe else ANSWER) + sentence)
    assert sentence not in saved.content
    assert (done['turn_outcome']['status'] == 'complete') is not unsafe
    if not unsafe:
        assert len(calls) == 2
        assert 'meta_query_invitation_removed' in saved.meta['output_quality_flags']
