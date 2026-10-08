"""Returned scores carry numbers, not an attested grading scale."""
import pytest
from app.services.agent_composed_read_completion import (
    evaluate_composed_read_completion, enforce_composed_synthesis_boundaries,
)
from tests.test_agent_composed_read_completion import execution, scope

UNSUPPORTED = [
    '评分尚可。', '睡眠评分良好。', '评分80分，属于良好。',
    '睡眠评分：80分，尚可。', '评分为80，比较理想。', '**评分**尚可。',
    '评分并不差。', '并非不能判断评分良好。',
]
SUPPORTED = [
    '评分80分。', '睡眠评分：80。', '没有评分等级标准，不能判断评分是否良好。',
    '不能据此判断评分尚可。', '评分是否良好无法判断。',
    '评分为80，不能由此得出睡眠质量良好。',
    '两条记录的评分分别为80和82。', '评分字段格式正常。',
    '第二条记录的评分比第一条低。',
    '评分稳定。', '已记录的评分保持稳定。',
]

@pytest.mark.parametrize('text,blocked', [(s, True) for s in UNSUPPORTED] + [(s, False) for s in SUPPORTED])
def test_record_score_cannot_supply_its_own_grade(text, blocked):
    completion = evaluate_composed_read_completion(scope('diet', 'sleep'), [execution(),
        execution('sleep', rows=[{'record_date': '2026-09-12', 'total_sleep_duration': 420, 'sleep_score': 80}])])
    result = enforce_composed_synthesis_boundaries(text, completion)
    assert result.flagged is blocked
    if blocked:
        assert 'unsupported_current_health_inference' in result.violations
        assert text not in result.text
        assert '评分80' in result.text
    else:
        assert result.text == text

@pytest.mark.asyncio
async def test_actual_pi_score_grade_is_repaired_before_stream_and_save(db, four_domain_user, monkeypatch):
    from tests.test_agent_composed_synthesis_projection import run_projection
    from tests.test_agent_read_repair_round_budget import ANSWER
    _, calls, _, done, saved = await run_projection(db, four_domain_user, monkeypatch,
        answer='评分尚可。', correction_result={'content': ANSWER, 'finish_reason': 'stop'})
    assert len(calls) == 3
    assert done['turn_outcome']['status'] == 'complete'
    assert 'unsupported_current_health_inference' in calls[2]['messages'][0]['content']
    assert '评分尚可' not in saved.content

from tests.test_agent_read_repair_round_budget import four_domain_user as four_domain_user, clock as clock, owned_data as owned_data
