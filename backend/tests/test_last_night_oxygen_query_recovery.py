"""Omitted model tools must not strand a server-bound last-night oxygen query."""
from datetime import datetime, time, timedelta
import json

import pytest

from tests.test_agent_read_repair_round_budget import (
    batch_trace, consume, four_domain_user, clock, owned_data, _isolate_twin_cache,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("has_samples", [False, True])
@pytest.mark.parametrize("query", ["昨晚血氧饱和度如何", "昨晚血氧如何", "分析昨晚的血氧数据。"])
async def test_last_night_oxygen_omitted_tool_is_proposed_via_owned_gateway(
    db, four_domain_user, clock, monkeypatch, panel, query, has_samples,
):
    day = clock[0].date()
    if has_samples:
        from app.models.daily_health import GarminData, SleepLevelInterval, SpO2Sample
        from zoneinfo import ZoneInfo

        start = datetime.combine(day - timedelta(days=1), time(23), ZoneInfo('Asia/Shanghai'))
        end = datetime.combine(day, time(7), ZoneInfo('Asia/Shanghai'))
        db.add(GarminData(user_id=four_domain_user.id, record_date=day, data_source='ringconn',
                          sleep_start_time=time(23), sleep_end_time=time(7), spo2_avg=40))
        db.add(SleepLevelInterval(user_id=four_domain_user.id, record_date=day, source='ringconn',
                                 activity_level='light', start_epoch_ms=int(start.timestamp()*1000),
                                 end_epoch_ms=int(end.timestamp()*1000)))
        for at, value, source in [(start+timedelta(minutes=30), 96, 'apple-watch'),
                                  (end-timedelta(minutes=30), 98, 'apple-watch'),
                                  (end+timedelta(hours=6), 51, 'apple-watch'),
                                  (end-timedelta(minutes=30), 52, 'garmin')]:
            db.add(SpO2Sample(user_id=four_domain_user.id, record_date=at.date(),
                             sample_time=at.time(), epoch_ms=int(at.timestamp()*1000),
                             spo2_value=value, source=source))
        db.commit()
    answer = "本轮依据实际读取结果回答；无法核验的夜间采样不作健康判断。"
    trace = batch_trace(db, monkeypatch, [answer, answer])
    dispatched = []
    results = []
    original = trace.executor._dispatch_tool_request

    async def dispatch(request, token):
        dispatched.append(request)
        result = await original(request, token)
        results.append(result)
        return result

    monkeypatch.setattr(trace.executor, "_dispatch_tool_request", dispatch)
    done, saved = await consume(db, trace, four_domain_user, panel=panel, query=query)
    reads = [r for r in dispatched if r.tool_name in {"health_query", "health_query_batch"}]
    assert len(reads) == 1, "the closed single-domain read was never executed"
    args = reads[0].arguments
    queries = args["queries"] if reads[0].tool_name == "health_query_batch" else [args]
    assert queries == [{"dimension": "spo2", "start_date": day.isoformat(), "end_date": day.isoformat(),
                        "timezone": "Asia/Shanghai", "period": "sleep_night"}]
    assert done["turn_outcome"]["status"] == "complete"
    assert not done["write_receipts"]
    assert "本轮查询未完成" not in saved.content
    if has_samples:
        content = results[0]
        payload = json.loads(content) if isinstance(content, str) else content
        item = payload['results'][0] if 'results' in payload else payload
        assert item['records'] == [{
            'record_date': day.isoformat(),
            'daily_metrics': {'spo2_avg': None, 'spo2_min': None, 'spo2_max': None},
            'daily_sources': {},
            'sample_summaries': [{'source': 'apple-watch', 'data_points': 2,
                                  'min_spo2': 96, 'max_spo2': 98, 'avg_spo2': 97.0}],
        }]
        assert '入睡至醒来时段筛选' in saved.content
    else:
        assert "缺少可定位的睡眠时段" in saved.content


@pytest.mark.asyncio
@pytest.mark.parametrize('panel', [False, True])
async def test_failed_oxygen_adapter_is_disclosed_without_model_replay(
    db, four_domain_user, monkeypatch, panel,
):
    attempts = []

    def fail(*args, **kwargs):
        attempts.append(1)
        raise RuntimeError('synthetic oxygen reader unavailable')

    monkeypatch.setattr('app.services.agent_query_window.read_calendar_health_query', fail)
    trace = batch_trace(db, monkeypatch, ['未读取个人数据，不能判断血氧情况。'] * 2)
    done, saved = await consume(db, trace, four_domain_user, panel=panel,
                                query='昨晚血氧饱和度如何')
    # Preserve the existing bounded transport retry, without proposing another
    # read after its failed ToolExecutionResult reaches the model.
    assert len(attempts) == 2
    assert len(trace.calls) == 2
    assert done['turn_outcome']['status'] != 'complete'
    assert '本轮查询未完成' in saved.content
    assert not done['write_receipts']


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['我朋友昨晚血氧饱和度如何', '不要查询昨晚血氧',
                                 '分析昨晚血氧，只看凌晨', '分析昨晚血氧并删除记录'])
async def test_single_domain_fallback_cannot_manufacture_scope(db, four_domain_user, monkeypatch, query):
    trace = batch_trace(db, monkeypatch, ['未读取个人数据。'])
    reads = []
    monkeypatch.setattr('app.services.agent_query_window.read_calendar_health_query',
                        lambda *a, **k: reads.append(1))
    await consume(db, trace, four_domain_user, query=query)
    assert not reads
