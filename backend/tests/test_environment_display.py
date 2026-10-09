from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from app.api import environment

@pytest.mark.asyncio
async def test_weather_display_rounds_without_changing_raw_readings():
    raw = {'available': True, 'temperature': 1.23456, 'humidity': 0, 'source': 'qweather'}
    with patch.object(environment.weather_service, 'get_current_weather', new_callable=AsyncMock, return_value=raw), patch.object(environment.weather_service, 'get_exercise_advice', return_value={}):
        result = await environment.get_weather('Test city', None, None, SimpleNamespace(id=7), None)
    assert result['weather']['display']['temperature'] == 1.23
    assert result['weather']['temperature'] == 1.23456
    assert result['weather']['display']['humidity'] == 0
    assert 'display' not in raw

@pytest.mark.asyncio
async def test_air_display_preserves_missing_and_source():
    raw = {'available': True, 'aqi': 0, 'pm25': 12.3456, 'pm10': None, 'source': 'qweather'}
    with patch.object(environment.weather_service, 'get_air_quality', new_callable=AsyncMock, return_value=raw):
        result = await environment.get_air_quality('Test city', None, None, SimpleNamespace(id=7), None)
    assert result['display']['aqi'] == 0
    assert result['display']['pm25'] == 12.35
    assert result['display']['pm10'] is None
    assert result['source'] == 'qweather'
    assert result['pm25'] == 12.3456
