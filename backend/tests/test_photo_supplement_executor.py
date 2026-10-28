"""Real stream contract; recognition and media bytes are synthetic stubs."""
from uuid import uuid4
import pytest
from app.models.agent_conversation import AgentMessage
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.write_intent import WriteIntent
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock,
    owned_data as owned_data, script_executor,
)

MESSAGE = '记录四种补剂 NAC 2粒 其他各1粒'
NAMES = ['NAC', '鱼油', '维生素D3+K2', '槲皮素']

@pytest.fixture
def photo_setup(db, monkeypatch, owned_data):
    from app.services import photo_supplement_recognition as recognition
    from app.services import photo_supplement_intake as intake
    db.add_all([SupplementDefinition(user_id=owned_data.id, name=n, is_active=True) for n in NAMES]); db.commit()
    from app.config import settings
    monkeypatch.setattr(settings, 'llm_vision_base_url', 'https://synthetic.invalid/v1')
    monkeypatch.setattr(settings, 'llm_vision_api_key', 'synthetic-test-key')
    monkeypatch.setattr('app.services.ai_consent.require_ai_consent', lambda *a, **k: None)
    trace = script_executor(db, monkeypatch, [])
    monkeypatch.setattr(trace.executor, '_upload_chat_image', lambda *a, **k: '/uploads/chat/synthetic.jpg')
    monkeypatch.setattr(trace.executor, '_should_preprocess_attached_images', lambda *a: True)
    monkeypatch.setattr(intake, 'read_owned_chat_image_data_uri', lambda *a: 'data:image/jpeg;base64,YWJj')
    monkeypatch.setattr(recognition, 'is_photo_supplement_request', lambda text: text == MESSAGE)
    async def recognize(*a, **k): return [{'name': n} for n in NAMES]
    monkeypatch.setattr(recognition, 'recognize_photo_supplements', recognize)
    return trace

async def consume(trace, user_id, **kwargs):
    return [e async for e in trace.executor.run_stream(user_id, MESSAGE,
        images=[{'base64': 'YWJj', 'type': 'jpeg'}], channel='typed', client_turn_id=str(uuid4()), **kwargs)]

@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['circuit_paused', 'circuit_unavailable'])
async def test_runtime_block_cannot_create_confirmable_photo_intent(db, monkeypatch, owned_data, photo_setup, reason):
    from app.services import photo_supplement_recognition as recognition
    calls = []
    async def recognize(*args, **kwargs):
        calls.append(True)
        return [{'name': name} for name in NAMES]
    monkeypatch.setattr(recognition, 'recognize_photo_supplements', recognize)
    events = await consume(photo_setup, owned_data.id, runtime_write_block_reason=reason)
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert not done['cards']
    assert not calls
    assert db.query(WriteIntent).count() == 0
    assert db.query(SupplementRecord).count() == 0

@pytest.mark.asyncio
async def test_real_stream_presents_same_turn_card_without_health_write(db, monkeypatch, owned_data, photo_setup):
    events = await consume(photo_setup, owned_data.id)
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert done['mode'] == 'photo_supplement_intake'
    assert saved.meta['client_turn_finalized'] is True
    assert saved.meta['completion_status'] == 'complete'
    assert len(saved.meta['cards'][0]['data']['items']) == 4
    wi = db.query(WriteIntent).filter_by(kind='photo_supplement_intake').one()
    source = db.get(AgentMessage, wi.target_id)
    assert source.client_turn_id == saved.client_turn_id
    assert not done['write_receipts'] and db.query(SupplementRecord).count() == 0
    assert not photo_setup.calls and not photo_setup.dispatches

@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['recognition', 'unknown'])
async def test_failed_photo_resolution_never_falls_into_generic_write(db, monkeypatch, owned_data, photo_setup, failure):
    from app.services import photo_supplement_recognition as recognition
    async def fail(*a, **k):
        if failure == 'recognition': raise ValueError('synthetic recognition failure')
        return [{'name': n} for n in ['NAC', '鱼油', '维生素D3+K2', '不同产品']]
    monkeypatch.setattr(recognition, 'recognize_photo_supplements', fail)
    events = await consume(photo_setup, owned_data.id)
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert done['mode'] == 'photo_supplement_intake'
    assert not done['cards'] and not done['write_receipts']
    assert '核对' in db.get(AgentMessage, done['message_id']).content
    assert not photo_setup.calls and not photo_setup.dispatches
    assert db.query(SupplementRecord).count() == 0

@pytest.mark.asyncio
async def test_read_only_scope_does_not_propose_or_recognize(db, monkeypatch, owned_data, photo_setup):
    from app.services import photo_supplement_recognition as recognition
    async def forbidden(*a, **k): raise AssertionError('read-only must not recognize an intake proposal')
    monkeypatch.setattr(recognition, 'recognize_photo_supplements', forbidden)
    events = await consume(photo_setup, owned_data.id, read_only_tools=True)
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert done['mode'] == 'photo_supplement_intake'
    assert not done['cards'] and db.query(WriteIntent).count() == 0
    assert not photo_setup.calls

@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['consent', 'config', 'preprocess'])
async def test_external_recognition_respects_fail_closed_boundaries(db, monkeypatch, owned_data, photo_setup, boundary):
    from app.services import photo_supplement_recognition as recognition
    from fastapi import HTTPException
    from app.config import settings
    async def forbidden(*a, **k): raise AssertionError('recognition must not be invoked')
    monkeypatch.setattr(recognition, 'recognize_photo_supplements', forbidden)
    if boundary == 'consent':
        def denied(*args, **kwargs):
            assert args[0] == owned_data.id
            assert kwargs['destination'] == 'https://synthetic.invalid/v1'
            raise HTTPException(403, detail={'code': 'ai_consent_required'})
        monkeypatch.setattr('app.services.ai_consent.require_ai_consent', denied)
    if boundary == 'config': monkeypatch.setattr(settings, 'llm_vision_api_key', '')
    if boundary == 'preprocess': monkeypatch.setattr(photo_setup.executor, '_should_preprocess_attached_images', lambda *a: False)
    events = await consume(photo_setup, owned_data.id)
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert done['completion_status'] == 'error'
    assert not done['cards'] and db.query(WriteIntent).count() == 0
    assert not photo_setup.calls

@pytest.mark.asyncio
async def test_proposal_and_card_do_not_commit_executor_dirty_state(db, monkeypatch, owned_data, photo_setup):
    from app.services import photo_supplement_recognition as recognition
    unrelated = SupplementDefinition(user_id=owned_data.id, name='Unrelated pending work')
    async def recognize(*a, **k):
        db.add(unrelated)
        return [{'name': n} for n in NAMES]
    monkeypatch.setattr(recognition, 'recognize_photo_supplements', recognize)
    events = await consume(photo_setup, owned_data.id)
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert done['cards']
    assert unrelated in db.new and unrelated.id is None
    db.rollback()
    assert db.query(SupplementDefinition).filter_by(name=unrelated.name).count() == 0

@pytest.mark.asyncio
async def test_real_preprocess_policy_admits_closed_photo_intake_for_multimodal_model(db, monkeypatch, owned_data, photo_setup):
    from app.services.agent_executor import AgentExecutor
    executor = photo_setup.executor
    monkeypatch.setattr(executor, '_should_preprocess_attached_images', AgentExecutor._should_preprocess_attached_images.__get__(executor))
    monkeypatch.setattr(executor, '_should_send_raw_images_to_primary_model', lambda *a: True)
    events = await consume(photo_setup, owned_data.id)
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    assert done['cards'] and done['pending_write_intent_kinds'] == ['photo_supplement_intake']
    assert not photo_setup.calls and not done['write_receipts']

@pytest.mark.asyncio
async def test_stream_card_confirm_and_reload_preserve_terminal_receipts(db, monkeypatch, owned_data, photo_setup):
    from types import SimpleNamespace
    from app.api.write_intents import confirm_write_intent
    events = await consume(photo_setup, owned_data.id)
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    intent_id = done['cards'][0]['data']['write_intent_id']
    result = await confirm_write_intent(intent_id, current_user=SimpleNamespace(id=owned_data.id), db=db)
    assert result['status'] == 'executed'
    assert len(result['write_receipts']) == 4
    db.expire_all()
    saved = db.get(AgentMessage, done['message_id'])
    card = saved.meta['cards'][0]
    assert card['data']['decision_status'] == 'executed'
    assert card['actions'] == []
    assert saved.meta['write_receipts'] == result['write_receipts']
    assert sorted(row.actual_dosage for row in db.query(SupplementRecord).all()) == ['1粒', '1粒', '1粒', '2粒']


@pytest.mark.asyncio
async def test_incomplete_probiotic_photo_waits_for_details_without_model_or_write(db, monkeypatch, owned_data, photo_setup):
    from app.services import photo_supplement_recognition as recognition
    async def forbidden(*args, **kwargs):
        raise AssertionError('missing intake facts must not invoke recognition')
    monkeypatch.setattr(recognition, 'recognize_photo_supplements', forbidden)
    events = [event async for event in photo_setup.executor.run_stream(
        owned_data.id, '记录益生菌补剂', images=[{'base64': 'YWJj', 'type': 'jpeg'}],
        channel='typed', client_turn_id=str(uuid4()),
    )]
    done = next(event['data'] for event in reversed(events) if event['event'] == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert done['turn_outcome']['status'] == 'waiting_for_user'
    assert done['input_clarification_reason'] == 'supplement_photo_details_required'
    assert '补剂清单' in saved.content and '已经服用' in saved.content
    assert '尚未写入' in saved.content
    assert not done['write_receipts'] and not done['cards']
    assert not photo_setup.calls and not photo_setup.dispatches
    assert db.query(WriteIntent).count() == 0
    assert db.query(SupplementRecord).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('with_image', [False, True])
async def test_photo_reference_waits_for_user_instead_of_generic_record_failure(
    db, monkeypatch, owned_data, photo_setup, with_image,
):
    from app.services import photo_supplement_recognition as recognition
    async def forbidden(*args, **kwargs):
        raise AssertionError('incomplete photo reference must not call vision')
    monkeypatch.setattr(recognition, 'recognize_photo_supplements', forbidden)
    monkeypatch.setattr(photo_setup.executor, '_analyze_image_with_vision', forbidden)
    events = [event async for event in photo_setup.executor.run_stream(
        owned_data.id, '记录以上图片补剂',
        images=[{'base64': 'YWJj', 'type': 'jpeg'}] if with_image else None,
        channel='typed', client_turn_id=str(uuid4()),
    )]
    done = next(event['data'] for event in reversed(events) if event['event'] == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert done['turn_outcome']['status'] == 'waiting_for_user'
    assert done['turn_outcome']['retryable'] is False
    assert done['input_clarification_reason'] == 'supplement_photo_details_required'
    assert saved.meta['turn_outcome'] == done['turn_outcome']
    assert '补剂清单' in saved.content and '已经服用' in saved.content
    assert '实际数量' in saved.content and '尚未写入' in saved.content
    assert not done['cards'] and not done['write_receipts']
    assert not photo_setup.calls and not photo_setup.dispatches
    assert db.query(WriteIntent).count() == 0
    assert db.query(SupplementRecord).count() == 0


@pytest.mark.asyncio
async def test_meal_photo_then_supplement_reference_is_durable_and_replay_safe(
    db, monkeypatch, owned_data, photo_setup,
):
    from app.models.agent_conversation import AgentConversation
    conversation = AgentConversation(user_id=owned_data.id, title='Synthetic photo follow-up')
    db.add(conversation)
    db.flush()
    previous = AgentMessage(
        conversation_id=conversation.id, role='user', content='记录这餐',
        image_url='/uploads/chat/synthetic.jpg',
    )
    previous_reply = AgentMessage(
        conversation_id=conversation.id, role='assistant',
        content='照片未能确认食物，本轮未保存。历史中的产品规格和数量不能作为新服用事实。',
        meta={'client_turn_finalized': True, 'write_receipts': []},
    )
    db.add_all([previous, previous_reply])
    db.commit()
    previous_content = previous.content
    turn_id = str(uuid4())
    results = []
    for _ in range(2):
        events = [event async for event in photo_setup.executor.run_stream(
            owned_data.id, '记录以上图片补剂', conversation_id=conversation.id,
            channel='typed', client_turn_id=turn_id,
        )]
        results.append(next(event['data'] for event in reversed(events) if event['event'] == 'done'))
    assert all(result['turn_outcome']['status'] == 'waiting_for_user' for result in results)
    assert all(not result['write_receipts'] for result in results)
    assert results[0]['message_id'] == results[1]['message_id']
    stored_turn_id = f'{owned_data.id}:{turn_id}'
    assert db.query(AgentMessage).filter_by(client_turn_id=stored_turn_id, role='user').count() == 1
    assert db.query(AgentMessage).filter_by(client_turn_id=stored_turn_id, role='assistant').count() == 1
    db.refresh(previous)
    assert previous.content == previous_content
    assert previous.image_url == '/uploads/chat/synthetic.jpg'
    assert db.query(WriteIntent).count() == 0
    assert db.query(SupplementRecord).count() == 0
    assert not photo_setup.calls and not photo_setup.dispatches
