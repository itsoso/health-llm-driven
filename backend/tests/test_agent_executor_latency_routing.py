from app.services.agent_output_quality import (
    clarification_reply,
    needs_input_clarification,
)


def test_one_character_input_uses_deterministic_clarification_lane():
    assert needs_input_clarification("睡") is True
    assert needs_input_clarification(" ? ") is True
    assert needs_input_clarification("睡眠") is False
    assert "补充" in clarification_reply()


def test_empty_input_is_owned_by_request_validation_not_clarification_lane():
    assert needs_input_clarification("") is False
    assert needs_input_clarification("   ") is False


def test_unbound_resolution_requires_specific_symptom_not_private_query():
    assert needs_input_clarification('现在好了')
    assert needs_input_clarification('现在好了。')
    assert '哪种症状' in clarification_reply('现在好了')
    assert '尚未修改' in clarification_reply('现在好了')
    assert not needs_input_clarification('我的感冒现在好了')
    assert not needs_input_clarification('现在好了没？')


async def test_unbound_resolution_stream_waits_without_model_or_health_tools(
    db, auth_user_and_headers, monkeypatch,
):
    from app.services.agent_executor import AgentExecutor
    from app.models.symptom_entry import SymptomEntry
    user, headers = auth_user_and_headers
    executor = AgentExecutor(db)

    async def forbidden(*args, **kwargs):
        raise AssertionError('Unbound resolution must not invoke model or health tools')

    monkeypatch.setattr(executor, '_call_llm', forbidden)
    monkeypatch.setattr(executor, '_call_llm_stream', forbidden)
    monkeypatch.setattr(executor, '_dispatch_tool_request', forbidden)
    events = [event async for event in executor.run_stream(
        user_id=user.id, message='现在好了',
        user_auth_token=headers['Authorization'].split(' ', 1)[1],
    )]
    rendered = ''.join(event['data'].get('content', '') for event in events if event.get('event') == 'token')
    done = next(event['data'] for event in events if event.get('event') == 'done')
    assert '哪种症状' in rendered
    assert '没有授权' not in rendered
    assert not done.get('write_receipts')
    assert db.query(SymptomEntry).filter_by(user_id=user.id).count() == 0
