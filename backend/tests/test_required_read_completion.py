"""Historical read requests must not become successful ungrounded answers."""
import pytest

from app.services.agent_executor import AgentExecutor
from tests.test_agent_read_plan_binding import decide
from tests.test_query_reliability_outcomes import _run_scripted


@pytest.fixture(autouse=True)
def _isolate_transport(isolated_agent_protocol_transport):
    """Use real Pi transport with synthetic provider and data only."""


@pytest.mark.parametrize('message,day', [
    ('昨日我过得怎么样', '2026-07-16'),
    ('我昨天过得怎样？', '2026-07-16'),
    ('前天我过得如何', '2026-07-15'),
])
@pytest.mark.parametrize('dimension', ['diet', 'sleep'])
def test_retrospective_summary_keeps_exact_requested_day(message, day, dimension):
    result = decide(message, 'health_query', {'dimension': dimension, 'days': 7})
    assert result.action == 'allow', result.reason
    assert result.normalized_args == {
        'dimension': dimension, 'start_date': day, 'end_date': day,
        'timezone': 'Asia/Shanghai',
    }


@pytest.mark.parametrize('message', [
    '重新查询昨天数据', '查询我最近的状态', '最近血氧饱和度情况如何',
])
def test_unresolved_requested_read_is_not_optional(db, message):
    executor = AgentExecutor(db)
    executor._current_user_id = 41
    executor._current_turn_user_message = message
    executor._start_agent_kernel_turn(user_id=41, message=message, channel='typed')
    executor._agent_kernel_capability_block_reasons = ['health_query_semantics_unresolved']
    executor._recover_irrelevant_read_blocks_after_completed_answer(
        completion_status='complete', final_text='本轮未查到，改用背景中的周均值回答。',
    )
    assert executor._agent_kernel_recovered_capability_block_reasons == []


@pytest.mark.asyncio
async def test_unresolved_history_question_cannot_report_complete(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    _, done, persisted, public, dispatched = await _run_scripted(
        db, user, monkeypatch, query='重新查询昨天数据',
        first_tool='health_query', first_args={'dimension': 'sleep', 'days': 7},
        dispatch=lambda request: {'records': [], 'count': 0},
        reply='昨日没有取到，改用近七天的均值回答。',
        turn_id='unresolved-required-read',
    )
    assert not dispatched
    assert done['turn_outcome']['status'] != 'complete'
    assert done['completion_status'] == 'error'
    assert persisted.meta['turn_outcome']['status'] != 'complete'
    assert '改用近七天的均值回答' not in public
    assert '查询' in public


@pytest.mark.parametrize('message', [
    '解释高原旅行的通用准备原则。查询昨天的数据',
    '解释我的睡眠的一般性建议', '“解释高原旅行的通用准备原则”',
    '不要解释高原旅行的通用准备原则', '假如解释高原旅行的通用准备原则',
    '解释高原旅行的通用准备原则并删除记录',
])
def test_general_advice_proof_never_erases_residue(message):
    from app.services.agent_policy_retry import is_general_advice_only_request
    assert not is_general_advice_only_request(message)


@pytest.mark.parametrize('message', [
    '妈妈昨日过得怎么样', '昨日妈妈过得怎么样', '明天我过得怎么样',
    '假如昨日我过得怎么样', '不要查询昨日我过得怎么样',
    '昨日我过得怎么样，然后删除饮食', '“昨日我过得怎么样”',
    '昨日和今天我过得怎么样',
])
def test_summary_extension_preserves_authority_boundaries(message):
    assert decide(message, 'health_query', {'dimension': 'diet'}).action == 'block'


@pytest.mark.asyncio
@pytest.mark.parametrize('dimension', ['diet', 'sleep'])
async def test_yesterday_summary_reads_only_owned_target_day_postgres(db, auth_user_and_headers, dimension):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('requires isolated PostgreSQL')
    import json
    from dataclasses import replace
    from datetime import date
    from app.models.daily_health import DietRecord, GarminData
    from app.models.user import User
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    from app.services.agent_kernel.types import ToolExecutionRequest
    from tests.test_agent_read_plan_binding import snapshot

    owner, _ = auth_user_and_headers
    other = User(username='summary-other', name='Synthetic other', hashed_password='fixture')
    db.add(other)
    db.flush()
    for uid, day in [(owner.id, 16), (owner.id, 17), (other.id, 16)]:
        db.add(DietRecord(user_id=uid, record_date=date(2026, 7, day),
                          meal_type='午餐', food_name='Synthetic fixture'))
        db.add(GarminData(user_id=uid, record_date=date(2026, 7, day),
                         data_source='garmin', total_sleep_duration=400))
    db.commit()
    snap = snapshot('昨日我过得怎么样')
    snap = replace(snap, envelope=replace(snap.envelope, user_id=owner.id),
                   context=replace(snap.context, user_id=owner.id))
    decision = decide_tool_capability(snap, ToolExecutionRequest(
        tool_name='health_query', arguments={'dimension': dimension, 'days': 7}))
    assert decision.action == 'allow'
    executor = AgentExecutor(db)
    executor._current_user_id = owner.id
    executor._current_turn_user_message = snap.envelope.text
    executor._agent_kernel_snapshot = snap
    raw = await executor._exec_health_query('http://unused', {}, decision.normalized_args)
    result = json.loads(raw)
    assert result['window'] == {'start_date': '2026-07-16', 'end_date': '2026-07-16', 'timezone': 'Asia/Shanghai'}
    assert len(result['records']) == 1
    assert result['records'][0]['record_date'] == '2026-07-16'
    assert db.query(DietRecord).count() == db.query(GarminData).count() == 3
