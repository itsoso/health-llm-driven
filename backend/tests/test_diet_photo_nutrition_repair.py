"""Missing photo nutrition opens an owned original record; never retries a write."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.services.diet_photo_correction import build_correction_proposal

NOW = datetime(2031, 4, 4, 5, tzinfo=timezone.utc)
REQUEST = '最后一张图片 没有计算出热量'


@pytest.fixture
def context(db, auth_user_and_headers):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.daily_health import DietPhotoAsset, DietRecord
    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id)
    db.add(conv)
    db.flush()
    source = AgentMessage(conversation_id=conv.id, role='user', content='记录午餐',
                          image_url='["/synthetic/owned.jpg"]', created_at=(NOW-timedelta(minutes=5)).replace(tzinfo=None))
    db.add(source)
    db.flush()
    target = DietRecord(user_id=user.id, record_date=NOW.date()-timedelta(days=1),
                        meal_type='lunch', food_items='鸡肉 100克 + 米饭 1碗',
                        protein=3.1415926, updated_at=NOW)
    db.add(target)
    db.flush()
    asset = DietPhotoAsset(id='nutrition-repair', user_id=user.id, diet_record_id=target.id,
        origin_message_id=source.id, ordinal=0, storage_key='/synthetic/owned.jpg',
        content_sha256='a'*64, media_type='image/jpeg', origin='chat',
        classification='food', intent_decision='auto_record', lifecycle='attached', created_at=NOW)
    current = AgentMessage(conversation_id=conv.id, role='user', content=REQUEST, created_at=NOW.replace(tzinfo=None))
    db.add_all([asset, current])
    db.commit()
    return user, conv, source, current, target, asset


def proposal(db, context, text=REQUEST):
    return build_correction_proposal(db, context[0].id, context[1].id,
                                    context[3].id, text, NOW, 'Asia/Shanghai')


def test_opens_bound_record_preserving_revision_date_precision_and_no_write(db, context):
    from app.models.daily_health import DietRecord
    db.add(DietRecord(user_id=context[0].id, record_date=NOW.date(),
                      meal_type='lunch', food_items='另一餐', calories=900))
    db.commit()
    result = proposal(db, context)
    assert result['status'] == 'waiting_for_user'
    card = result['cards'][0]
    seed = card['data']['adjust_record']
    assert seed['record_id'] == context[4].id
    assert seed['proposed_food_items'] == context[4].food_items
    assert seed['protein'] == 3.1415926
    assert seed['updated_at'] == context[4].updated_at.isoformat()
    assert str(context[4].record_date) in card['data']['title']
    assert context[4].calories is None
    assert db.query(DietRecord).count() == 2
    assert '尚未修改' in result['reply']


@pytest.mark.parametrize('damage', ['deleted', 'pending', 'expired', 'future', 'newer_unbound',
    'multiple', 'other_owner', 'other_conversation', 'changed_input', 'no_food',
    'multi_image_one_asset', 'wrong_ordinal', 'empty_image_list', 'malformed_images'])
def test_ambiguous_or_unowned_sources_only_clarify(db, context, damage):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.daily_health import DietPhotoAsset
    user, conv, source, current, target, asset = context
    if damage == 'deleted': asset.deleted_at = NOW
    elif damage == 'pending': asset.lifecycle = 'pending'
    elif damage == 'expired': source.created_at = (NOW-timedelta(days=2)).replace(tzinfo=None)
    elif damage == 'future': source.created_at = (NOW+timedelta(days=1)).replace(tzinfo=None)
    elif damage == 'no_food': target.food_items = ''
    elif damage == 'multi_image_one_asset': source.image_url = '["/synthetic/first.jpg", "/synthetic/last.jpg"]'
    elif damage == 'wrong_ordinal': asset.ordinal = 1
    elif damage == 'empty_image_list': source.image_url = '[]'
    elif damage == 'malformed_images': source.image_url = 'not-json'
    elif damage == 'changed_input': current.content = '取消'
    elif damage == 'other_owner':
        from app.models.user import User
        other = User(name='Synthetic', email='nutrition-other@example.invalid')
        db.add(other); db.flush()
        target.user_id = other.id
    elif damage == 'other_conversation':
        other = AgentConversation(user_id=user.id)
        db.add(other); db.flush()
        source.conversation_id = other.id
    elif damage == 'multiple':
        db.add(DietPhotoAsset(id='ambiguous', user_id=user.id, origin_message_id=source.id,
            ordinal=1, storage_key='/synthetic/second.jpg', content_sha256='b'*64,
            media_type='image/jpeg', origin='chat', classification='food',
            intent_decision='auto_record', lifecycle='attached', diet_record_id=target.id))
    else:
        # Never skip a newer unbound image to reach an older saved meal.
        current.image_url = '["/synthetic/newer.jpg"]'
        db.flush()
        newer = AgentMessage(conversation_id=conv.id, role='user', content=REQUEST, created_at=NOW.replace(tzinfo=None))
        db.add(newer); db.flush()
        context = (user, conv, source, newer, target, asset)
    db.commit()
    answer = proposal(db, context)
    assert answer['cards'] == []
    assert answer['status'] == 'waiting_for_user'
    assert '饮食页' in answer['reply']
    assert target.calories is None


@pytest.mark.parametrize('text', ['不要'+REQUEST, '朋友说'+REQUEST, '假如'+REQUEST,
    REQUEST+'，删除晚餐', '最后一张妈妈的图片没有计算出热量', '“'+REQUEST+'”'])
def test_non_authorizing_input_does_not_query(text):
    class NoReads:
        def query(self, *_):
            pytest.fail('non-authorizing text must not read records')
    assert build_correction_proposal(NoReads(), 1, 1, 1, text, NOW, 'Asia/Shanghai') is None


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [None, 'panel'])
async def test_stream_no_model_no_write_and_clear_confirmation(db, context, monkeypatch, mode):
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, '_agent_kernel_reference_now', lambda: NOW)
    async def no_model(*_args, **_kwargs):
        pytest.fail('missing nutrition must resolve before model or panel dispatch')
    monkeypatch.setattr(executor, '_call_llm_stream', no_model)
    class PanelProvider:
        async def chat(self, **kwargs):
            pytest.fail('panel provider must not run')
    monkeypatch.setattr('app.services.llm.factory.create_provider_for_model_id',
                        lambda *a, **k: PanelProvider())
    kwargs = {'extra_context': json.dumps({'multi_model': mode == 'panel'})}
    events = [event async for event in executor.run_stream(user_id=context[0].id,
        conversation_id=context[1].id, message=REQUEST, channel='typed', **kwargs)]
    done = next(event['data'] for event in events if event.get('event') == 'done')
    assert done['llm_rounds'] == 0 and done['write_receipts'] == []
    assert done['turn_outcome']['status'] == 'waiting_for_user'
    assert done['turn_outcome']['retryable'] is False
    assert done['cards'][0]['data']['adjust_record']['record_id'] == context[4].id


def test_confirm_recalculates_original_once_and_keeps_photo_date(db, context, client,
                                                               auth_user_and_headers, monkeypatch):
    from app.services.ai.food_recognition import food_recognition_service
    from app.models.daily_health import DietRecord
    seed = proposal(db, context)['cards'][0]['data']['adjust_record']
    calls = []
    def estimate(text):
        calls.append(text)
        return {'success': True, 'foods': [{'name': '合成餐', 'quantity': '1份',
            'calories': 450, 'protein': 20, 'carbs': 60, 'fat': 14, 'fiber': 1, 'confidence': .9}],
            'total_calories': 450, 'total_protein': 20, 'total_carbs': 60,
            'total_fat': 14, 'total_fiber': 1}
    monkeypatch.setattr(food_recognition_service, 'estimate_nutrition_from_text', estimate)
    payload = {'food_items': seed['proposed_food_items'], 'meal_type': seed['meal_type'],
               'expected_updated_at': seed['updated_at']}
    url = f"/api/v1/diet/records/{seed['record_id']}/recalculate-nutrition"
    headers = {**auth_user_and_headers[1], 'Idempotency-Key': 'synthetic-nutrition-repair'}
    first = client.post(url, json=payload, headers=headers)
    assert first.status_code == 200, first.text
    assert client.post(url, json=payload, headers=headers).status_code == 200
    assert len(calls) == 1
    assert client.post(url, json=payload, headers={**headers,
        'Idempotency-Key': 'synthetic-stale-repair'}).status_code == 409
    db.refresh(context[4])
    assert context[4].calories == 450
    assert context[4].record_date == NOW.date()-timedelta(days=1)
    assert context[5].diet_record_id == context[4].id
    assert db.query(DietRecord).count() == 1
