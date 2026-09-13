"""Owned sync aliases refine only the sync operation, never other write grants."""
from dataclasses import replace

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import has_owned_sync_instruction
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot


def snapshot(text):
    env = AgentEnvelope(user_id=41, channel='typed', text=text)
    context = ExecutionContext.for_test(user_id=41, channel='typed')
    return TurnSnapshot(env, context, build_intent_frame(env, context))


def decision(turn, record_type='garmin_sync', data=None):
    return decide_tool_capability(turn, ToolExecutionRequest('health_record', {
        'record_type': record_type, 'data': {} if data is None else data,
    }))


@pytest.mark.parametrize('text', [
    '麻烦把我的佳明数据刷新一下，然后看看昨晚睡得怎么样。',
    '拉取一下我的 Garmin 数据，然后分析2026-07-11的睡眠。',
    '刷新我的佳明数据', '把我的Garmin数据拉取一下',
    '同步一下佳明，再分析昨晚睡眠。',
    '先分析昨天的睡眠，再同步佳明数据。',
])
def test_expanded_sync_refines_frame_and_retains_separate_read_date(text):
    turn = snapshot(text)
    assert turn.intent.operation == 'sync'
    assert decision(turn).action == 'allow'
    assert decision(turn, 'weight', {'weight': 70}).action == 'block'
    read_only = replace(turn, intent=replace(turn.intent, primary='query', operation='query', is_write=False))
    assert decision(read_only).action == 'block'


@pytest.mark.parametrize('text', [
    '获取佳明昨天的数据，同步一下。',
    '获取佳明最近7天的数据，同步一下。',
    '获取佳明2026-07-11的数据，同步一下。',
    '获取佳明上周的数据，同步一下。',
    '获取佳明近三天的数据，同步一下。',
    '获取佳明的数据，同步一下昨天的数据。',
])
def test_device_or_sync_target_date_cannot_be_discarded_into_default_sync(text):
    assert not has_owned_sync_instruction(text)
    assert decision(snapshot(text)).action == 'block'


@pytest.mark.parametrize('text', [
    '不要刷新佳明数据', '如果需要，拉取佳明数据', '“刷新我的佳明数据”',
    '朋友说：拉取我的佳明数据', '刷新王小明的佳明数据',
    '佳明的数据同步完了吗？', '获取佳明数据', '明天刷新我的佳明数据',
])
def test_non_authorizing_aliases_do_not_gain_sync_frame_authority(text):
    assert not has_owned_sync_instruction(text)
    assert decision(snapshot(text)).action == 'block'


@pytest.mark.asyncio
async def test_repeated_owned_sync_commands_have_one_enqueued_effect(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport,
):
    from types import SimpleNamespace
    from uuid import uuid4
    from datetime import datetime
    import app.tasks.garmin_sync as task
    from app.models.user import GarminCredential
    from app.twin.schema import HealthTwin, TwinMeta
    from tests.test_agent_coherence_pi_trajectories import script_executor, run

    monkeypatch.setattr('app.twin.builder.build_twin', lambda _db, user_id, **kwargs: HealthTwin(
        meta=TwinMeta(user_id=user_id, generated_at=datetime.now().astimezone())))
    user, _ = auth_user_and_headers
    db.add(GarminCredential(user_id=user.id, garmin_email='synthetic@example.test',
                           encrypted_password='synthetic', sync_enabled=True,
                           credentials_valid=True, requires_mfa=False))
    db.commit()
    enqueued = []
    def enqueue(*args, **kwargs):
        enqueued.append((args, kwargs))
        return SimpleNamespace(id=str(uuid4()))
    monkeypatch.setattr(task.sync_user_garmin_data, 'delay', enqueue)
    trace = script_executor(db, monkeypatch, [
        ('health_record', {'record_type': 'garmin_sync', 'data': {}}),
        ('health_record', {'record_type': 'garmin_sync', 'data': {}}),
        '同步任务已提交，尚未核实完成。',
    ])
    _, saved = await run(db, trace, user, '获取佳明的数据，同步一下，同步一下，同步一下。')
    assert len(enqueued) == 1
    assert saved.meta['garmin_sync_job']['job_id']
