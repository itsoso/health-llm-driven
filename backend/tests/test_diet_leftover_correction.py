"""Leftovers are an absolute edit proposal, never another consumed meal."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import hashlib

import pytest

NOW = datetime(2031, 4, 4, 4, tzinfo=timezone.utc)
REQUEST = '午饭剩余部分 通过剩余部分 修正记录的午餐'


def test_leftover_instruction_is_not_a_food_description():
    from app.services.agent_executor import _parse_explicit_diet_correction
    assert _parse_explicit_diet_correction(REQUEST, reference_now=NOW) is None


@pytest.fixture
def context(db, auth_user_and_headers):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.daily_health import DietPhotoAsset, DietRecord
    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id)
    db.add(conv)
    db.flush()
    source = AgentMessage(conversation_id=conv.id, role='user', content='记录午餐',
                          image_url=f'["/api/v1/upload/files/chat/{user.id}/synthetic.jpg"]')
    db.add(source)
    db.flush()
    target = DietRecord(user_id=user.id, record_date=NOW.date(), meal_type='lunch',
                        food_items='米饭 1碗 + 鸡肉 100克', calories=450,
                        updated_at=NOW)
    db.add(target)
    db.flush()
    asset = DietPhotoAsset(id='leftover-original', user_id=user.id, diet_record_id=target.id,
        origin_message_id=source.id, ordinal=0, storage_key='/synthetic/owned.jpg',
        content_sha256=hashlib.sha256(b'synthetic').hexdigest(), media_type='image/jpeg', origin='chat',
        classification='food', intent_decision='auto_record', lifecycle='attached',
        recognition_snapshot={'recognition_version': 'contextual_meal_photo_v1',
          'foods': [{'name':'米饭', 'quantity':'1碗'}, {'name':'鸡肉', 'quantity':'100克'}]})
    db.add(asset)
    current = AgentMessage(conversation_id=conv.id, role='user', content=REQUEST,
                           image_url='["/synthetic/leftover.jpg"]')
    db.add(current)
    db.commit()
    return user, conv, source, current, target, asset


async def run_proposal(db, context, monkeypatch, *, text=REQUEST, result=None):
    from app.services import diet_leftover_correction as subject
    user, conv, _, current, _, _ = context
    current.content = text
    db.commit()
    monkeypatch.setattr(subject, 'read_owned_chat_image_data_uri', lambda *_: 'data:image/jpeg;base64,c3ludGhldGlj')
    vision = AsyncMock(return_value=result or {'comparable':True, 'full_plate_visible':True,
        'items':[{'index':0,'remaining_fraction':.5,'confidence':.9},
                 {'index':1,'remaining_fraction':.25,'confidence':.9}]})
    monkeypatch.setattr(subject, 'estimate_leftovers', vision)
    answer = await subject.build_leftover_proposal(db, user.id, conv.id, current.id, text,
        [{'base64':'c3ludGhldGlj','type':'jpeg'}], NOW, 'Asia/Shanghai')
    return answer, vision


@pytest.mark.asyncio
async def test_proposal_subtracts_per_item_without_any_diet_write(db, context, monkeypatch):
    from app.models.daily_health import DietRecord, DietPhotoAsset
    answer, vision = await run_proposal(db, context, monkeypatch)
    assert answer['status'] == 'waiting_for_user'
    seed=answer['cards'][0]['data']['adjust_record']
    assert seed['record_id'] == context[4].id
    assert seed['proposed_food_items'] == '米饭 约0.5碗 + 鸡肉 约75克'
    assert seed['updated_at'] and seed['food_items'] == context[4].food_items
    assert context[4].calories == 450
    assert db.query(DietRecord).filter_by(user_id=context[0].id).count() == 1
    assert db.query(DietPhotoAsset).filter_by(user_id=context[0].id).count() == 1
    assert vision.await_count == 1 and '尚未修改' in answer['reply']


@pytest.mark.asyncio
async def test_retry_uses_original_baseline_not_current_consumed_amount(db, context, monkeypatch):
    first, _ = await run_proposal(db, context, monkeypatch)
    context[4].food_items = first['cards'][0]['data']['adjust_record']['proposed_food_items']
    db.commit()
    second, _ = await run_proposal(db, context, monkeypatch)
    assert second['cards'][0]['data']['adjust_record']['proposed_food_items'] == context[4].food_items


@pytest.mark.parametrize('text', ['不要'+REQUEST, '朋友说'+REQUEST, '假如'+REQUEST,
    REQUEST+'，删掉晚餐', REQUEST.replace('午餐','昨天午餐'), '剩菜照片',
    '根据剩菜照片修改妈妈的午餐'])
@pytest.mark.asyncio
async def test_non_authorizing_text_never_reads_records(text):
    from app.services.diet_leftover_correction import build_leftover_proposal
    class NoReads:
        def query(self, *_):
            pytest.fail('unresolved request cannot read health records')
    result=await build_leftover_proposal(NoReads(),1,1,1,text,[{'base64':'synthetic'}],NOW,'Asia/Shanghai')
    assert not result['cards']


@pytest.mark.parametrize('damage', ['other_owner','other_day','multiple','missing_baseline','partial_baseline','missing_source','cancelled_source'])
@pytest.mark.asyncio
async def test_unbound_or_ambiguous_baselines_never_reach_model(db, context, monkeypatch, damage):
    from app.models.daily_health import DietRecord
    from datetime import timedelta
    if damage=='other_owner':
        from app.models.user import User
        other = User(name='Synthetic other', email='leftover-other@example.invalid')
        db.add(other)
        db.flush()
        context[4].user_id = other.id
    elif damage=='other_day': context[4].record_date -= timedelta(days=1)
    elif damage=='multiple': db.add(DietRecord(user_id=context[0].id,record_date=NOW.date(),meal_type='lunch',food_items='第二份'))
    elif damage=='missing_baseline': context[5].recognition_snapshot = None
    elif damage=='partial_baseline': context[5].recognition_snapshot = {**context[5].recognition_snapshot,'consumed_fraction':.5}
    elif damage=='missing_source': context[2].image_url = None
    else: context[3].content = 'different'
    if damage=='cancelled_source':
        # Exercise exact persisted input check without run_proposal rewriting it.
        from app.services.diet_leftover_correction import build_leftover_proposal
        db.commit()
        result=await build_leftover_proposal(db,context[0].id,context[1].id,context[3].id,REQUEST,
            [{'base64':'synthetic'}],NOW,'Asia/Shanghai')
        assert not result['cards']
    else:
        answer, vision=await run_proposal(db,context,monkeypatch)
        assert vision.await_count==0
        assert answer['status']=='waiting_for_user'


@pytest.mark.asyncio
async def test_stream_short_circuits_generic_capture_and_returns_no_saved_receipt(db,context,monkeypatch):
    from app.services.agent_executor import AgentExecutor
    from app.services import diet_leftover_correction as subject
    monkeypatch.setattr(subject, 'read_owned_chat_image_data_uri', lambda *_:'data:image/jpeg;base64,c3ludGhldGlj')
    monkeypatch.setattr(subject, 'estimate_leftovers', AsyncMock(return_value={
        'comparable':True,'full_plate_visible':True,'items':[
            {'index':0,'remaining_fraction':.5,'confidence':.9},
            {'index':1,'remaining_fraction':.25,'confidence':.9}]}))
    executor=AgentExecutor(db)
    monkeypatch.setattr(executor,'_agent_kernel_reference_now',lambda:NOW)
    monkeypatch.setattr(executor,'_upload_chat_image',lambda *_a,**_k:'/synthetic/leftover.jpg')
    async def no_capture(*_a,**_k):
        pytest.fail('leftovers must not enter normal food recognition/capture')
    monkeypatch.setattr(executor,'_analyze_image_with_vision',no_capture)
    monkeypatch.setattr(executor,'_call_llm_stream',no_capture)
    monkeypatch.setattr(executor,'_should_preprocess_attached_images',lambda *_:True)
    events=[event async for event in executor.run_stream(user_id=context[0].id,
        conversation_id=context[1].id,message=REQUEST,images=[{'base64':'c3ludGhldGlj','type':'jpeg'}],channel='typed')]
    done=next(event['data'] for event in events if event.get('event')=='done')
    assert done['write_receipts']==[]
    assert done['turn_outcome']['status']=='waiting_for_user'
    assert done['record_intent_no_tool'] is False
    assert done['cards'][0]['data']['adjust_record']['record_id']==context[4].id


@pytest.mark.asyncio
async def test_confirmation_updates_same_record_once_and_stale_replay_conflicts(db,client,context,auth_user_and_headers,monkeypatch):
    from app.services.ai.food_recognition import food_recognition_service
    from app.models.daily_health import DietRecord
    answer,_=await run_proposal(db,context,monkeypatch)
    seed=answer['cards'][0]['data']['adjust_record']
    calls=[]
    def estimate(text):
        calls.append(text)
        return {'success':True,'foods':[{'name':'合成米饭','quantity':'0.5碗',
            'calories':100,'protein':2,'carbs':22,'fat':1,'fiber':1,'confidence':.9}],
            'total_calories':100,'total_protein':2,'total_carbs':22,'total_fat':1,'total_fiber':1}
    monkeypatch.setattr(food_recognition_service,'estimate_nutrition_from_text',estimate)
    payload={'food_items':seed['proposed_food_items'],'meal_type':seed['meal_type'],
             'expected_updated_at':seed['updated_at']}
    url=f"/api/v1/diet/records/{seed['record_id']}/recalculate-nutrition"
    headers={**auth_user_and_headers[1],'Idempotency-Key':'synthetic-leftover-confirm'}
    first=client.post(url,json=payload,headers=headers)
    assert first.status_code==200,first.text
    repeated=client.post(url,json=payload,headers=headers)
    assert repeated.status_code==200 and len(calls)==1
    stale=client.post(url,json=payload,headers={**headers,'Idempotency-Key':'synthetic-leftover-stale'})
    assert stale.status_code==409 and len(calls)==1
    db.refresh(context[4])
    assert context[4].food_items==seed['proposed_food_items']
    assert context[4].calories==100
    assert db.query(DietRecord).filter_by(user_id=context[0].id).count()==1
    assert context[5].diet_record_id==context[4].id
    assert context[5].recognition_snapshot['foods'][0]['quantity']=='1碗'


@pytest.mark.parametrize('damage',['unknown','too_much','all_left','mismatch','low_confidence'])
@pytest.mark.asyncio
async def test_unusable_estimates_do_not_fake_consumption(db,context,monkeypatch,damage):
    result={'comparable':True,'full_plate_visible':True,'items':[
        {'index':0,'remaining_fraction':.5,'confidence':.9},
        {'index':1,'remaining_fraction':.25,'confidence':.9}]}
    if damage=='unknown': result['items'][0]['remaining_fraction']=None
    elif damage=='too_much': result['items'][0]['remaining_fraction']=1.2
    elif damage=='all_left':
        for item in result['items']: item['remaining_fraction']=1
    elif damage=='mismatch': result['comparable']=False
    else: result['items'][0]['confidence']=.1
    answer,_=await run_proposal(db,context,monkeypatch,result=result)
    assert 'proposed_food_items' not in answer['cards'][0]['data']['adjust_record']
    assert context[4].calories==450 and '尚未修改' in answer['reply']


@pytest.mark.asyncio
async def test_photo_digest_must_match_original_asset(db,context,monkeypatch):
    context[5].content_sha256='0'*64
    answer,vision=await run_proposal(db,context,monkeypatch)
    assert vision.await_count==0
    assert 'proposed_food_items' not in answer['cards'][0]['data']['adjust_record']


def test_generic_capture_cannot_save_leftovers_even_if_called_directly():
    from app.services.agent_executor import AgentExecutor
    from unittest.mock import MagicMock
    executor=AgentExecutor(MagicMock())
    executor._current_user_id=1
    executor._current_turn_source_message_id=1
    result={'success':True,'foods':[{'name':'米饭','quantity':'半碗','confidence':.99}]}
    assert executor._capture_contextual_meal_photos(REQUEST,result,image_indexes=[0]) is None
    assert result['contextual_capture_write_blocked_reason']=='leftover_confirmation_required'
    executor.db.add.assert_not_called()


@pytest.mark.parametrize('text',['餐后血糖记录怎么看','餐后服药照片','餐后散步记录'])
def test_after_meal_alone_does_not_hijack_other_domains(text):
    from app.services.diet_leftover_correction import is_leftover_context
    assert not is_leftover_context(text)
