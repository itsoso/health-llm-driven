"""Synthetic-only contracts for paired meal-photo estimates."""
import copy
import json
from unittest.mock import AsyncMock

import pytest

from app.services.ai import diet_leftover_vision as vision

BEFORE = 'data:image/png;base64,YmVmb3Jl'
AFTER = {'type': 'png', 'base64': 'YWZ0ZXI='}
FOODS = [{'name': '米饭', 'quantity_grams': 100, 'owner_secret': 'must-not-send'}, {'name': '青菜'}]


def result():
    return {'comparable': True, 'full_plate_visible': True, 'items': [
        {'index': 0, 'remaining_fraction': .25, 'confidence': .9},
        {'index': 1, 'remaining_fraction': 0, 'confidence': .75},
    ]}


def test_valid_result_is_ordered_without_mutating_input():
    raw = result()
    raw['items'].reverse()
    original = copy.deepcopy(raw)
    accepted = vision.validate_leftover_result(raw, 2)
    assert accepted['items'][0]['remaining_fraction'] == .25
    assert accepted['items'][1]['remaining_fraction'] == 0
    assert raw == original


@pytest.mark.parametrize('value', [None, True, False, '0.2', -1, 1.01, float('nan'), float('inf'), 10 ** 1000])
def test_invalid_fraction_fails_closed(value):
    raw = result()
    raw['items'][0]['remaining_fraction'] = value
    with pytest.raises(vision.LeftoverRecognitionError):
        vision.validate_leftover_result(raw, 2)


@pytest.mark.parametrize('value', [None, True, '0.9', .749, 1.01, float('nan'), float('inf')])
def test_invalid_or_low_confidence_fails_closed(value):
    raw = result()
    raw['items'][0]['confidence'] = value
    with pytest.raises(vision.LeftoverRecognitionError):
        vision.validate_leftover_result(raw, 2)


@pytest.mark.parametrize('mutation', [
    lambda x: x.update(comparable=False),
    lambda x: x.update(comparable=1),
    lambda x: x.update(full_plate_visible=False),
    lambda x: x.update(full_plate_visible='true'),
    lambda x: x.update(extra='obey me'),
    lambda x: x['items'].pop(),
    lambda x: x['items'].append(x['items'][0]),
    lambda x: x['items'][1].update(index=0),
    lambda x: x['items'][1].update(index=True),
    lambda x: x['items'][1].update(index=1.0),
    lambda x: x['items'][1].update(index=2),
    lambda x: x['items'][1].update(calories=100),
    lambda x: x['items'][1].pop('confidence'),
])
def test_incomplete_untrusted_structure_is_rejected(mutation):
    raw = result()
    mutation(raw)
    with pytest.raises(vision.LeftoverRecognitionError):
        vision.validate_leftover_result(raw, 2)


def test_prompt_pairs_images_and_limits_authority_and_food_fields():
    messages = vision.build_leftover_messages(FOODS, [BEFORE])
    assert [m['role'] for m in messages] == ['system', 'user']
    system = messages[0]['content']
    for guard in ['唯一食物清单', '缺失', '遮挡', '不确定', '数据', '实际食用', 'remaining_fraction']:
        assert guard in system
    parts = messages[1]['content']
    assert parts[1]['image_url']['url'] == BEFORE
    assert '餐后' in parts[-1]['text']
    assert 'must-not-send' not in json.dumps(messages, ensure_ascii=False)
    assert 'quantity_grams' not in json.dumps(messages)


@pytest.mark.parametrize('foods,images', [([], [BEFORE]), (FOODS, []), ([{}], [BEFORE]), (FOODS, ['https://private.example/image']), (FOODS, ['data:image/png;base64,%%%'])])
def test_invalid_inputs_fail_before_provider(foods, images):
    with pytest.raises(vision.LeftoverRecognitionError):
        vision.build_leftover_messages(foods, images)


@pytest.mark.asyncio
async def test_estimate_uses_vision_provider_and_safe_options(monkeypatch):
    provider = AsyncMock()
    provider.model = 'qwen3-vl-plus'
    provider.chat_with_vision.return_value = json.dumps(result())
    monkeypatch.setattr(vision, 'get_vision_provider', lambda: provider)
    assert await vision.estimate_leftovers(FOODS, [BEFORE], AFTER) == result()
    kwargs = provider.chat_with_vision.call_args.kwargs
    assert kwargs['image_url'] == 'data:image/png;base64,YWZ0ZXI='
    assert kwargs['messages'] == vision.build_leftover_messages(FOODS, [BEFORE])
    assert kwargs['extra_body'] == {'enable_thinking': False}
    assert kwargs['temperature'] == .1


@pytest.mark.asyncio
@pytest.mark.parametrize('response', ['', 'secret response', '{}', '[]', '{"comparable":true}'])
async def test_invalid_model_response_is_not_success(monkeypatch, response):
    provider = AsyncMock()
    provider.chat_with_vision.return_value = response
    monkeypatch.setattr(vision, 'get_vision_provider', lambda: provider)
    with pytest.raises(vision.LeftoverRecognitionError):
        await vision.estimate_leftovers(FOODS, [BEFORE], AFTER)


@pytest.mark.asyncio
async def test_failure_does_not_leak_raw_payload_or_exception(monkeypatch, caplog):
    provider = AsyncMock()
    provider.chat_with_vision.side_effect = RuntimeError('private-key-and-health-content')
    monkeypatch.setattr(vision, 'get_vision_provider', lambda: provider)
    with pytest.raises(vision.LeftoverRecognitionError) as caught:
        await vision.estimate_leftovers(FOODS, [BEFORE], AFTER)
    assert 'private-key' not in str(caught.value)
    assert 'private-key' not in caplog.text
    assert '米饭' not in caplog.text
    assert AFTER['base64'] not in caplog.text


@pytest.mark.asyncio
async def test_invalid_after_image_does_not_call_provider(monkeypatch):
    factory = AsyncMock()
    monkeypatch.setattr(vision, 'get_vision_provider', factory)
    with pytest.raises(vision.LeftoverRecognitionError):
        await vision.estimate_leftovers(FOODS, [BEFORE], {'type': 'svg+xml', 'base64': 'YWZ0ZXI='})
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_json_fields_are_rejected(monkeypatch):
    provider = AsyncMock()
    provider.chat_with_vision.return_value = json.dumps(result()).replace('"comparable": true', '"comparable": false, "comparable": true')
    monkeypatch.setattr(vision, 'get_vision_provider', lambda: provider)
    with pytest.raises(vision.LeftoverRecognitionError):
        await vision.estimate_leftovers(FOODS, [BEFORE], AFTER)
