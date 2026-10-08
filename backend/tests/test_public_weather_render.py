from datetime import datetime, timezone, timedelta
from copy import deepcopy
import pytest

from app.services import agent_public_task as public

NOW = datetime(2026, 10, 8, 23, 30, tzinfo=timezone(timedelta(hours=8)))
MESSAGE = '杭州明天天气温度怎么样？空气质量。'

def data():
    return [
        {'available': True, 'source': 'qweather', 'forecasts': [
            {'date': '2026-10-10', 'temp_min': 17, 'temp_max': 25, 'weather': '晴'},
            {'date': '2026-10-09', 'temp_min': 18.125, 'temp_max': 23.456, 'weather': '多云'},
        ]},
        {'air_quality': {'available': True, 'aqi': 52, 'aqi_description': '良', 'source': 'qweather-v1'},
         'observation_time_status': 'unavailable'},
    ]

def render(message=MESSAGE, results=None):
    return public.render_public_weather(message, public.public_weather_queries(message), results or data(), reference_now=NOW)

@pytest.mark.parametrize('message,day,temps', [(MESSAGE, '2026-10-09', '18.12～23.46'),
    (MESSAGE.replace('明天', '后天'), '2026-10-10', '17～25')])
def test_target_date_not_array_position(message, day, temps):
    answer = render(message)
    assert day in answer and temps in answer and 'AQI 52' in answer and '良' in answer
    assert '无法确认观测时点' in answer and '当前空气质量' not in answer
    assert '暂无' in answer and '空气质量预报' in answer

@pytest.mark.parametrize('value', [0, 52.126, '52.126'])
def test_aqi_numeric_values(value):
    results = data(); results[1]['air_quality']['aqi'] = value
    assert ('AQI 0' if value == 0 else 'AQI 52.13') in render(results=results)

@pytest.mark.parametrize('value', [True, False, float('inf'), float('nan'), 'NaN', None])
def test_invalid_aqi_fails_closed(value):
    results = data(); results[1]['air_quality']['aqi'] = value
    with pytest.raises(ValueError): render(results=results)

@pytest.mark.parametrize('value', ['2026-10-08', '2026-10-08T09:12+08:00'])
def test_observation_time_preserves_precision(value):
    results = data(); results[1]['air_quality']['update_time'] = value
    answer = render(results=results)
    assert value in answer and '无法确认观测时点' not in answer
    assert '当前空气质量' not in answer

def test_missing_target_and_invalid_temperature_fail():
    results = data(); results[0]['forecasts'] = results[0]['forecasts'][:1]
    with pytest.raises(ValueError): render(results=results)
    results = data(); results[0]['forecasts'][1]['temp_min'] = True
    with pytest.raises(ValueError): render(results=results)

def test_only_facts_render_without_changing_payload():
    results = data(); results[1]['air_quality']['exercise_advice'] = 'HEALTH_SENTINEL'
    original = deepcopy(results)
    assert 'HEALTH_SENTINEL' not in render(results=results)
    assert results == original


def test_generic_forecast_lists_source_dates_without_default_city():
    answer = public.render_public_weather('天气预报', public.public_weather_queries('天气预报'), data()[:1], reference_now=NOW)
    assert '2026-10-09' in answer and '2026-10-10' in answer
    assert answer.index('2026-10-09') < answer.index('2026-10-10')
    assert '杭州' not in answer

@pytest.mark.parametrize('value', ['opaque-tag', '2026-02-30', '', None])
def test_invalid_observation_time_never_claims_current(value):
    results = data(); results[1]['air_quality']['update_time'] = value
    answer = render(results=results)
    assert '无法确认观测时点' in answer
    assert 'AQI 52' in answer
    assert '当前空气质量' not in answer


def test_source_numeric_level_is_preserved():
    results = data(); results[1]['air_quality'].pop('aqi_description')
    results[1]['air_quality']['aqi_level'] = 2
    assert '来源等级 2' in render(results=results)

@pytest.mark.parametrize('damage', ['duplicate', 'absent_temperature', 'bool', 'inf', 'negative_aqi'])
def test_malformed_facts_fail_closed(damage):
    results = data()
    if damage == 'duplicate': results[0]['forecasts'].append(results[0]['forecasts'][1])
    if damage == 'absent_temperature': results[0]['forecasts'][1].pop('temp_max')
    if damage == 'bool': results[0]['forecasts'][1]['temp_max'] = False
    if damage == 'inf': results[0]['forecasts'][1]['temp_max'] = float('inf')
    if damage == 'negative_aqi': results[1]['air_quality']['aqi'] = -1
    with pytest.raises(ValueError): render(results=results)
