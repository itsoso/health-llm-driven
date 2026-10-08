"""A composed sync preserves its read goal; a device question grants no reads."""
import json

import pytest

from app.models.user import GarminCredential
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock, owned_data as owned_data,
    broker as broker, script_executor, run,
)
from tests.test_longitudinal_read_scope_policy import decide

DEVICE = '佳明戴在脚踝上，睡眠和血氧读数会受影响吗？'


def test_device_placement_explanation_rejects_personal_read_as_unnecessary():
    result = decide({'dimension': 'sleep'}, DEVICE)
    assert result.reason == 'current_input_advice_read_not_needed'


async def test_device_question_recovers_from_model_read_without_owner_or_date_notice(db, monkeypatch, owned_data):
    answer = '佩戴位置可能影响传感器接触和算法适用性；本轮未查询个人记录，不能据此判断你的具体读数。'
    trace = script_executor(db, monkeypatch, [('health_query', {'dimension': 'sleep'}), answer])
    done, saved = await run(db, trace, owned_data, DEVICE)
    assert not trace.dispatches
    assert done['turn_outcome']['status'] == 'complete'
    assert '只能查询' not in saved.content and '请明确' not in saved.content
    assert answer in saved.content


@pytest.mark.parametrize('status,verified', [('PENDING', False), ('FAILURE', False), ('SUCCESS', True)])
async def test_sync_submission_followed_by_model_stop_still_reads_bound_goal(db, monkeypatch, owned_data, broker, status, verified):
    db.add(GarminCredential(user_id=owned_data.id, garmin_email='synthetic@example.test',
        encrypted_password='synthetic', sync_enabled=True, credentials_valid=True, requires_mfa=False))
    db.commit()
    monkeypatch.setattr('app.services.agent_garmin_sync_status._read_task_meta', lambda job: {
        'task_id': job, 'status': status, 'result': {'status': 'success', 'success_count': 1,
        'error_count': 0, 'activities_count': 0}})
    trace = script_executor(db, monkeypatch, [
        ('health_record', {'record_type': 'garmin_sync', 'data': {}}),
        '同步请求已经提交。',
        '本轮已核对原日期已有的记录；同步结果单独展示。',
    ])
    done, saved = await run(db, trace, owned_data, '同步一下佳明，再分析昨晚睡眠。')
    assert len(broker.enqueued) == 1
    reads = [(request, raw) for request, raw in trace.results if request.tool_name == 'health_query_batch']
    assert len(reads) == 1
    assert reads[0][0].arguments['queries'] == [{'dimension': 'sleep',
        'start_date': '2026-09-13', 'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai'}]
    assert trace.executor._turn_sync_status_result['job_success_verified'] is verified
    if not verified:
        assert done['turn_outcome']['status'] != 'complete'
    assert '同步完成，所有数据已更新' not in saved.content


async def test_sync_only_never_injects_a_personal_health_read(db, monkeypatch, owned_data, broker):
    db.add(GarminCredential(user_id=owned_data.id, garmin_email='synthetic@example.test',
        encrypted_password='synthetic', sync_enabled=True, credentials_valid=True, requires_mfa=False))
    db.commit()
    trace = script_executor(db, monkeypatch, [
        ('health_record', {'record_type': 'garmin_sync', 'data': {}}), '同步请求已经提交。'])
    await run(db, trace, owned_data, '同步一下佳明')
    assert len(broker.enqueued) == 1
    assert [r.tool_name for r in trace.dispatches] == ['health_record']


@pytest.mark.parametrize('text', ['“' + DEVICE + '”', '假如' + DEVICE,
                                  DEVICE + '并查询我昨天的睡眠', DEVICE + '并删除记录'])
def test_placement_grammar_does_not_drop_other_commands_or_quoted_roles(text):
    from app.services.agent_kernel.current_input_advice_scope import is_wearable_placement_question
    assert not is_wearable_placement_question(text)


def test_placement_knowledge_question_never_selects_bedtime_answer():
    from app.services.agent_kernel.current_input_advice_scope import local_advice_response
    assert local_advice_response(DEVICE) is None
    assert decide({'query': '设备佩戴与测量原理'}, DEVICE, tool='knowledge_search').action == 'allow'
