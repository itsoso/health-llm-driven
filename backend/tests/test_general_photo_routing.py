"""Ordinary chat attachments must not imply a meal or a diet write."""
import json
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.models.daily_health import DietPhotoAsset, DietPhotoDraft, DietRecord
from app.services.agent_executor import AgentExecutor
from tests.test_agent_executor_food_vision import (
    VALID_PNG_BASE64, _food_photo_executor, _food_result, _stream_from,
)


@pytest.mark.parametrize('message', [
    '', '请分析这些图片', '请分析这张图片', '帮我看看', '这是什么？',
    '看看这台设备', '帮我记一下', '这瓶补剂是什么',
    '手腕因为佩戴手表磨破了皮肤怎么办？',
])
async def test_general_vision_does_not_try_food_first(db, monkeypatch, message):
    executor = AgentExecutor(db)
    food = AsyncMock(return_value='fabricated meal')
    monkeypatch.setattr(executor, '_analyze_food_images_with_structured_vision', food)
    monkeypatch.setattr(settings, 'llm_vision_base_url', 'https://vision.example.test')
    monkeypatch.setattr(settings, 'llm_vision_api_key', 'synthetic-key')
    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {'choices': [{'message': {'content': 'Synthetic general image description.'}}]}
    class Client:
        async def post(self, url, **kwargs):
            calls.append(kwargs['json'])
            return Response()
    executor._http_client = Client()
    result = await executor._analyze_image_with_vision(message, [{'base64': 'synthetic'}])
    food.assert_not_awaited()
    assert len(calls) == 1
    assert '普通图片描述' in result
    assert '请识别这张图片中的食物' not in str(calls)


@pytest.mark.parametrize('message', ['', '请分析这些图片', '帮我看看', '看看这台设备'])
def test_false_positive_food_cannot_create_a_record_or_draft(db, tmp_path, monkeypatch, message):
    executor, _ = _food_photo_executor(db, tmp_path, monkeypatch)
    assert executor._capture_contextual_meal_photo(message, _food_result(), image_index=0) is None
    assert db.query(DietRecord).count() == db.query(DietPhotoDraft).count() == db.query(DietPhotoAsset).count() == 0


@pytest.mark.parametrize('raw_primary', [False, True])
@pytest.mark.parametrize('message,stale_meal', [
    ('请分析这些图片', False), ('看看这台设备', True),
    ('手腕因为佩戴手表磨破了皮肤怎么办？', True),
])
async def test_general_upload_stream_keeps_image_and_never_emits_meal_progress(
    db, tmp_path, monkeypatch, raw_primary, message, stale_meal,
):
    from app.models.agent_conversation import AgentMessage
    from app.services.ai.food_recognition import food_recognition_service
    executor, user = _food_photo_executor(db, tmp_path, monkeypatch)
    food = AsyncMock(return_value=_food_result())
    monkeypatch.setattr(food_recognition_service, 'recognize_food_from_base64', food)
    monkeypatch.setattr(executor, '_should_send_raw_images_to_primary_model', lambda _: raw_primary)
    monkeypatch.setattr(settings, 'llm_vision_base_url', '')
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *a, **k: 'SYS')
    monkeypatch.setattr('app.services.agent_executor.get_health_tools', lambda subset=None: [])
    model = AsyncMock(return_value={'content': '请说明希望了解照片中的哪部分。', 'finish_reason': 'stop'})
    monkeypatch.setattr(executor, '_call_llm', model)
    monkeypatch.setattr(executor, '_call_llm_stream', _stream_from(model))
    context = json.dumps({'source': 'mobile_chat_meal_photo', 'intent': 'diet_photo_record',
                          'instruction': 'STALE_MEAL_INSTRUCTION', 'capture_session_id': 'old-meal'}) if stale_meal else None
    events = [e async for e in executor.run_stream(user.id, message,
        images=[{'base64': VALID_PNG_BASE64, 'type': 'png'}], extra_context=context,
        client_turn_id='general-photo', user_auth_token='synthetic-token')]
    food.assert_not_awaited()
    assert not executor._diet_photo_auto_save
    assert not any(str(e.get('stage', '')).startswith('diet_photo') for e in events)
    assert 'STALE_MEAL_INSTRUCTION' not in str(model.call_args_list)
    assert any(e.get('event') == 'request_persisted' and e['data'].get('image_urls') for e in events)
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert not done['write_receipts']
    assert db.get(AgentMessage, done['message_id']).content
    assert db.query(DietRecord).count() == db.query(DietPhotoDraft).count() == db.query(DietPhotoAsset).count() == 0
    send = AsyncMock()
    executor._http_client = type('NoDietHTTP', (), {'post': send, 'put': send})()
    result = await executor._exec_health_record('https://example.test', {},
        {'type': 'diet', 'data': {'food_items': 'hallucinated food'}})
    assert '饮食' in str(result)
    send.assert_not_awaited()


@pytest.mark.parametrize('message', ['记录这餐', '分析这餐', '这张午餐照片多少热量'])
async def test_explicit_meal_keeps_one_structured_call(db, monkeypatch, message):
    executor = AgentExecutor(db)
    food = AsyncMock(return_value='structured meal')
    monkeypatch.setattr(executor, '_analyze_food_images_with_structured_vision', food)
    assert await executor._analyze_image_with_vision(message, [{'base64': 'synthetic'}]) == 'structured meal'
    food.assert_awaited_once()


@pytest.mark.parametrize('message', ['', '请分析这些图片'])
async def test_explicit_meal_entry_keeps_structured_vision(db, monkeypatch, message):
    executor = AgentExecutor(db)
    executor._diet_photo_auto_save = True
    food = AsyncMock(return_value='structured meal')
    monkeypatch.setattr(executor, '_analyze_food_images_with_structured_vision', food)
    assert await executor._analyze_image_with_vision(message, [{'base64': 'synthetic'}]) == 'structured meal'
    food.assert_awaited_once()


@pytest.mark.parametrize('message', ['请分析这些图片', '看看这台设备'])
async def test_explicit_food_recognizer_cannot_bypass_general_photo_boundary(db, monkeypatch, message):
    from app.services.ai.food_recognition import food_recognition_service
    executor = AgentExecutor(db)
    food = AsyncMock(return_value=_food_result())
    monkeypatch.setattr(food_recognition_service, 'recognize_food_from_base64', food)
    assert await executor._analyze_food_images_with_structured_vision(message, [{'base64': 'synthetic'}]) is None
    food.assert_not_awaited()


def test_generic_boundary_does_not_lose_report_or_supplement_preprocessing(db, monkeypatch):
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, '_should_send_raw_images_to_primary_model', lambda _: True)
    for message in ('记录补剂，今天骑行', '帮我分析这份体检报告'):
        assert executor._should_preprocess_attached_images(1, message)
        assert not executor._has_food_photo_purpose(message)
