"""Synthetic provider, real Pi/gateway and owner/date-filtered database reads."""
import json
from datetime import timedelta

import pytest

from app.models.daily_health import DietRecord
from app.models.user import User
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock,
    owned_data as owned_data,
    run,
    script_executor,
)
from tests.test_diet_entry_read_scope import REQUEST

POST_CONFIRM_REQUEST = '帮我复盘这一天的饮食，给出下一餐的调整建议。'


def post_confirm_context(record_id):
    return json.dumps({
        'from': 'diet/post_confirm', 'verify_record_id': record_id,
        'database_verification': {
            'required': True, 'verify_record_id': record_id,
            'date': '2099-01-01', 'query_scope': 'daily_diet_records',
            'totals_source': 'database',
            'missing_record_instruction': 'UNTRUSTED_CONTROL_SENTINEL',
        },
        'record': {'food_items': 'UNTRUSTED_FOOD_SENTINEL'},
    })


@pytest.mark.asyncio
@pytest.mark.parametrize('batch', [False, True])
async def test_post_confirm_review_binds_owned_record_day(db, owned_data, clock, monkeypatch, batch):
    selected = db.query(DietRecord).filter_by(user_id=owned_data.id).one()
    db.add(DietRecord(user_id=owned_data.id, record_date=clock[0].date(),
                      meal_type='lunch', food_items='WRONG_DAY_SENTINEL'))
    other = db.query(User).filter(User.id != owned_data.id).first()
    db.add(DietRecord(user_id=other.id, record_date=selected.record_date,
                      meal_type='lunch', food_items='OTHER_OWNER_SENTINEL'))
    db.commit()
    query = {'dimension': 'diet'}
    trace = script_executor(db, monkeypatch, [
        ('health_query_batch', {'queries': [query]}) if batch else ('health_query', query),
        '建议：目前记录有限，下一餐可搭配蔬菜和蛋白质食物。',
    ])
    done, saved = await run(db, trace, owned_data, POST_CONFIRM_REQUEST,
                            extra_context=post_confirm_context(selected.id))
    payload = json.dumps([raw for _, raw in trace.results], ensure_ascii=False)
    assert '合成番茄' in payload
    assert 'WRONG_DAY_SENTINEL' not in payload and 'OTHER_OWNER_SENTINEL' not in payload
    assert 'UNTRUSTED_' not in json.dumps(trace.calls, ensure_ascii=False)
    assert trace.executor._turn_daily_read_plan.start_date == selected.record_date.isoformat()
    assert done['turn_outcome']['status'] == 'complete'
    assert not done['write_receipts']
    from app.models.agent_conversation import AgentMessage
    assert db.query(AgentMessage).filter_by(conversation_id=saved.conversation_id, role='user').one().content == POST_CONFIRM_REQUEST


@pytest.mark.asyncio
@pytest.mark.parametrize('selector', ['other_owner', 'missing', 'boolean', 'string', 'no_context'])
async def test_post_confirm_unavailable_record_never_calls_model_or_reads_day(db, owned_data, clock, monkeypatch, selector):
    other = db.query(User).filter(User.id != owned_data.id).first()
    row = DietRecord(user_id=other.id, record_date=clock[0].date(),
                     meal_type='lunch', food_items='PRIVATE_SENTINEL')
    db.add(row)
    db.commit()
    record_id = {'other_owner': row.id, 'missing': 999999, 'boolean': True,
                 'string': str(row.id), 'no_context': None}[selector]
    trace = script_executor(db, monkeypatch, [])
    events = [event async for event in trace.executor.run_stream(
        owned_data.id, POST_CONFIRM_REQUEST, channel='typed',
        extra_context=None if selector == 'no_context' else post_confirm_context(record_id),
    )]
    done = next(event['data'] for event in reversed(events) if event['event'] == 'done')
    assert not trace.calls and not trace.dispatches
    assert done['turn_outcome']['status'] == 'waiting_for_user'
    assert done['turn_outcome']['reason_code'] == 'diet_review_record_unavailable'
    assert 'PRIVATE_SENTINEL' not in json.dumps(events)


@pytest.mark.parametrize('prefix,suffix', [
    ('妈妈的', ''), ('如果可以，', ''), ('解释例句：“', '”'),
    ('', '只看上午。'), ('', '不要查询我的记录。'), ('', '只查昨天。'),
    ('', '删除昨天的记录。'), ('', '查询朋友的睡眠。'),
])
def test_post_confirm_binder_never_erases_user_edits(db, owned_data, prefix, suffix):
    from app.services.agent_executor import _resolve_post_confirm_diet_review
    selected = db.query(DietRecord).filter_by(user_id=owned_data.id).one()
    assert _resolve_post_confirm_diet_review(
        db, owned_data.id, prefix + POST_CONFIRM_REQUEST + suffix, post_confirm_context(selected.id),
    ) is None


@pytest.mark.parametrize('changes', [
    {'created_id': True}, {'verify_record_id': 999999}, {'created_id': '1'},
    {'from': 'diet/today'}, {'database_verification': []},
])
def test_post_confirm_binder_rejects_conflicting_or_malformed_selector(db, owned_data, changes):
    from app.services.agent_executor import _resolve_post_confirm_diet_review
    selected = db.query(DietRecord).filter_by(user_id=owned_data.id).one()
    context = {**json.loads(post_confirm_context(selected.id)), **changes}
    assert _resolve_post_confirm_diet_review(
        db, owned_data.id, POST_CONFIRM_REQUEST, json.dumps(context),
    ) is None


@pytest.mark.asyncio
async def test_edited_shortcut_uses_current_text_not_stale_selected_day(db, owned_data, clock, monkeypatch):
    selected = db.query(DietRecord).filter_by(user_id=owned_data.id).one()
    db.add(DietRecord(user_id=owned_data.id, record_date=clock[0].date(),
                      meal_type='lunch', food_items='CURRENT_REQUEST_DAY'))
    db.commit()
    trace = script_executor(db, monkeypatch, [
        ('health_query', {'dimension': 'diet'}),
        '建议：目前记录有限，下一餐可搭配蔬菜和蛋白质食物。',
    ])
    done, _ = await run(db, trace, owned_data, REQUEST, extra_context=post_confirm_context(selected.id))
    payload = json.dumps([raw for _, raw in trace.results], ensure_ascii=False)
    assert 'CURRENT_REQUEST_DAY' in payload and '合成番茄' not in payload
    assert 'UNTRUSTED_' not in json.dumps(trace.calls, ensure_ascii=False)
    assert done['turn_outcome']['status'] == 'complete'


@pytest.mark.asyncio
@pytest.mark.parametrize('correction,expected', [
    ('建议：仅凭现有记录无法判断全天饮食是否均衡。下一餐可结合自己的日常饮食安排搭配。', 'complete'),
    ('建议：全天只吃了200千卡，摄入不足。', 'partial'),
    (('health_record', {'record_type': 'diet', 'data': {'food_items': 'rice'}}), 'partial'),
])
async def test_post_confirm_advice_has_one_tool_free_correction(db, owned_data, monkeypatch, correction, expected):
    selected = db.query(DietRecord).filter_by(user_id=owned_data.id).one()
    trace = script_executor(db, monkeypatch, [
        ('health_query', {'dimension': 'diet'}),
        '建议：晚餐只有200千卡，全天热量严重不足。', correction,
    ])
    done, saved = await run(db, trace, owned_data, POST_CONFIRM_REQUEST,
                            extra_context=post_confirm_context(selected.id))
    assert len(trace.calls) == 3
    assert trace.calls[-1][1] == []
    assert len(trace.dispatches) == 1 and trace.dispatches[0].tool_name == 'health_query'
    assert done['turn_outcome']['status'] == expected
    assert not done['write_receipts']
    assert '全天热量严重不足' not in saved.content


@pytest.mark.asyncio
@pytest.mark.parametrize('batch', [False, True])
async def test_diet_entry_reads_owned_day_without_scope_refusal(db, owned_data, clock, monkeypatch, batch):
    today = clock[0].date()
    other = db.query(User).filter(User.id != owned_data.id).first()
    for owner, day, food in [
        (owned_data.id, today, 'ENTRY_OWNED_TODAY'),
        (owned_data.id, today + timedelta(days=1), 'ENTRY_FUTURE_FORBIDDEN'),
        (other.id, today, 'ENTRY_OTHER_FORBIDDEN'),
    ]:
        db.add(DietRecord(user_id=owner, record_date=day, meal_type='lunch',
                          food_items=food, food_name=food, calories=500, protein=20))
    db.commit()
    query = {'dimension': 'diet'}
    trace = script_executor(db, monkeypatch, [
        ('health_query_batch', {'queries': [query]}) if batch else ('health_query', query),
        '建议：仅凭这些记录还不能确定蛋白质是否充足。下一餐可考虑搭配蔬菜和蛋白质食物。',
    ])
    done, saved = await run(db, trace, owned_data, REQUEST)
    assert trace.dispatches
    assert all(r.tool_name in {'health_query', 'health_query_batch'} for r in trace.dispatches)
    payload = json.dumps([raw for _, raw in trace.results], ensure_ascii=False)
    assert 'ENTRY_OWNED_TODAY' in payload
    assert 'ENTRY_FUTURE_FORBIDDEN' not in payload and 'ENTRY_OTHER_FORBIDDEN' not in payload
    assert '合成番茄' not in payload  # Yesterday's own row is outside the scope.
    assert '范围限制尚不能完整解析' not in saved.content
    assert not done['write_receipts']
    assert done['turn_outcome']['status'] == 'complete', json.dumps(done['turn_outcome'], ensure_ascii=False)
