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
