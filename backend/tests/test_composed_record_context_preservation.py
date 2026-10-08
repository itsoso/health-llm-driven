"""Do not hide quoted facts to make an unsafe collection-request probe pass."""
import pytest
from app.services.agent_composed_read_completion import evaluate_composed_read_completion, project_composed_answer_quality
from app.services.agent_output_quality import enforce_agent_output_quality
from tests.test_agent_composed_read_completion import execution, scope
from tests.test_agent_read_repair_round_budget import four_domain_user as four_domain_user, owned_data as owned_data, clock as clock

QUOTED = '医生此前的原话是：\n建议先积累连续记录。\n以上只是既往背景。'

@pytest.mark.parametrize('text', [
    QUOTED,
    '以下不是给你的建议：\n请先积累一周记录。',
    '医生此前说，建议先积累连续记录，这只是既往背景。',
    '并不是说，建议先积累连续记录。',
    '已返回两条记录，建议先积累连续记录。',
    '建议先积累连续记录，但目前已返回两条记录。',
    '已积累一段时间的连续记录。',
    '不建议先积累连续记录。',
    '无需积累更多记录。',
    '医生建议积累连续记录属于既往背景，不能当作本轮医嘱。',
    '建议先积累经验，而不是补录健康记录。',
])
def test_preserve_quoted_negated_and_factual_record_context(text):
    completion = evaluate_composed_read_completion(scope('diet','sleep'), [execution(),
        execution('sleep', rows=[{'record_date':'2026-09-12','total_sleep_duration':420,'sleep_score':80}])])
    original = enforce_agent_output_quality(completion.trusted_fact_summary + '\n\n' + text)
    result = project_composed_answer_quality(original, completion)
    assert 'meta_query_invitation_removed' not in result.flags
    assert text in result.text
    assert '评分80' in result.text and '时长7小时' in result.text

@pytest.mark.asyncio
async def test_actual_pi_preserves_multiline_record_background(db, four_domain_user, monkeypatch):
    from tests.test_agent_composed_synthesis_projection import run_projection
    from tests.test_agent_read_repair_round_budget import ANSWER
    _, calls, _, done, saved = await run_projection(db, four_domain_user, monkeypatch, answer=ANSWER+'\n'+QUOTED)
    assert done['turn_outcome']['status'] == 'complete'
    assert len(calls) == 2 and QUOTED in saved.content
    assert 'meta_query_invitation_removed' not in saved.meta.get('output_quality_flags', [])
