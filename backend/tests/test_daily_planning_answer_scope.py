"""A future daily draft is not authority to inspect historical health records."""
import pytest
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock, owned_data as owned_data,
)

REQUESTS = ['规划今天饮食运动和睡眠', '请帮我规划今天的饮食、运动和睡眠',
            '安排明天饮食和睡眠计划']

@pytest.fixture(autouse=True)
def _transport(isolated_agent_protocol_transport):
    pass

@pytest.mark.parametrize('text', REQUESTS)
def test_daily_draft_has_answer_scope_without_personal_reads(text):
    from app.services.agent_kernel.current_input_advice_scope import is_current_input_advice, local_advice_response
    from tests.test_sleep_oxygen_read_scope import decide
    assert is_current_input_advice(text)
    assert local_advice_response(text) is None  # not a bedtime-only canned reply
    assert decide({'dimension': 'sleep'}, text).action == 'block'

@pytest.mark.parametrize('text', [
    '规划今天饮食运动和睡眠，并查询我的病史', '根据我昨天的睡眠规划今天饮食运动和睡眠',
    '给妈妈规划今天饮食运动和睡眠', '“规划今天饮食运动和睡眠”',
    '不要规划今天饮食运动和睡眠', '规划今天饮食运动和睡眠并保存',
    '规划今天用药和睡眠',
])
def test_unknown_owner_basis_or_write_does_not_become_general_advice(text):
    from app.services.agent_kernel.current_input_advice_scope import is_current_input_advice
    assert not is_current_input_advice(text)

@pytest.mark.parametrize('panel', [False, True])
async def test_screenshot_turn_finishes_in_one_answer_round_without_reads(db, owned_data, monkeypatch, panel):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    answer = '本轮未查询个人记录。以下是通用安排草稿：规律进餐、按身体感受选择轻松活动，晚间预留休息时间；有不适时暂停。'
    monkeypatch.setattr('tests.test_agent_read_repair_round_budget.ANSWER', answer)
    trace = batch_trace(db, monkeypatch, [answer])
    done, saved = await consume(db, trace, owned_data, panel=panel, query=REQUESTS[0])
    assert done['completion_status'] == 'complete'
    assert done['turn_outcome']['status'] == 'complete'
    assert not trace.dispatches
    assert len(trace.calls) == 1
    assert '本轮数据查询未完成' not in saved.content
    assert all(t['function']['name'] == 'knowledge_search' for t in trace.calls[0][1])
