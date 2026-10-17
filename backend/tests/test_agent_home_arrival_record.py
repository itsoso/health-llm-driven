"""Explicit home arrivals bind only this turn's facts to an owned event."""
import pytest

from app.services.agent_executor import _record_intent_needs_detail_message
from app.services.utterance_intent_classifier import classify_agent_utterance
from app.services.write_intent_scope import current_turn_trip_payload
from tests.test_agent_trip_record import execute_trip


@pytest.mark.parametrize('message,title', [
    ('到家了。记录下来。', '到家了'),
    ('我到家了，帮我记一下。', '我到家了'),
    ('记录一下，我刚到家了。', '我刚到家了'),
    ('请帮我记录：我已经回到家了。', '我已经回到家了'),
])
@pytest.mark.asyncio
async def test_explicit_home_arrival_binds_current_fact(db, monkeypatch, message, title):
    assert classify_agent_utterance(message).is_write
    expected = {'title': title, 'notes': title}
    assert current_turn_trip_payload(message) == expected
    calls, _ = await execute_trip(db, monkeypatch, message)
    assert len(calls) == 1
    assert calls[0][2] == expected


@pytest.mark.parametrize('message', [
    '到家了', '朋友到家了。记录下来。', '如果到家了。记录下来。',
    '明天到家了。记录下来。', '还没到家了。记录下来。',
    '到家了。不要记录下来。', '到家了。记录下来。先别保存。',
    '“到家了。记录下来。”', '到家了。记录下来？',
    '到家了。记录下来。这是示例。', '朋友说：到家了。记录下来。',
    '到家了。记录下来。胸痛。', '到家了。记录下来。查询睡眠。',
    '到家了。记录下来。22:00提醒我。', '到家了。记录下来。这是小明的记录。',
    '到家了。记录下来。把药量加倍。', '昨天到家了。记录下来。',
])
@pytest.mark.asyncio
async def test_unbound_home_arrivals_never_dispatch(db, monkeypatch, message):
    assert current_turn_trip_payload(message) is None
    calls, _ = await execute_trip(db, monkeypatch, message)
    assert calls == []


def test_home_arrival_mismatch_does_not_request_medication_details():
    reply = _record_intent_needs_detail_message(
        '到家了。记录下来。', reason_codes=['health_record_target_mismatch'],
    )
    assert '剂量' not in reply and '单位' not in reply
    assert '没有执行记录' in reply
