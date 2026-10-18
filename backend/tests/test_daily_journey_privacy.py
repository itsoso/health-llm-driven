import pytest
from app.utils.share_location_privacy import protect_location_event


@pytest.mark.parametrize('event', [
    {'request': {'url': 'https://example/api/v1/daily-journeys/sessions/id/points', 'data': 'private'}},
    {'exception': {'values': [{'stacktrace': {'frames': [{'module': 'app.services.daily_journey', 'vars': {'payload': 'private'}}]}}]}},
    {'exception': {'values': [{'stacktrace': {'frames': [{'filename': 'app/models/daily_journey.py', 'vars': {'payload': 'private'}}]}}]}},
])
def test_daily_journey_never_reaches_telemetry(event):
    assert protect_location_event(event, {}) is None


def test_unrelated_telemetry_preserved():
    event = {'request': {'url': 'https://example/api/v1/health'}, 'message': 'healthy'}
    assert protect_location_event(event, {}) is event
