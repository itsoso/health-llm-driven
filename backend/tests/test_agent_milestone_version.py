"""Versioned render telemetry: old and new success timing cannot be merged."""
import pytest
from pydantic import ValidationError
from app.api.client_events import EventIn


def event(**extra):
    return EventIn(event_name='agent_turn_milestone', meta={
        'phase': 'first_key_content', 'duration_ms': 500,
        'action_type': 'generic', 'has_image': False, **extra,
    })


def test_render_metric_v2_is_preserved():
    assert event(metric_version=2).meta['metric_version'] == 2


def test_legacy_render_metric_remains_distinguishable():
    assert 'metric_version' not in event().meta


@pytest.mark.parametrize('value', [True, '2', 2.0, None, 0, 3])
def test_metric_version_is_strict(value):
    with pytest.raises(ValidationError):
        event(metric_version=value)


def test_aggregate_never_mixes_metric_versions():
    from app.services.observability_service import _agent_turn_milestone_stats
    rows = [('agent_turn_milestone', event().meta),
            ('agent_turn_milestone', {**event(metric_version=2).meta, 'duration_ms': 9000})]
    legacy = _agent_turn_milestone_stats(rows)
    assert legacy['by_phase']['first_key_content']['n'] == 1
    current = _agent_turn_milestone_stats(rows, metric_version=2)
    assert current['by_phase']['first_key_content']['p50'] == 9000
    assert current['by_phase']['first_key_content']['n'] == 1


def test_client_turn_correlation_id_is_preserved_without_content():
    assert event(metric_version=2, client_turn_id='turn-12-1789100000000').meta['client_turn_id'] == 'turn-12-1789100000000'


@pytest.mark.parametrize('value', ['patient-name', 'turn-1-secret', 12, '', 'turn-1-1789100000000\n'])
def test_client_turn_correlation_rejects_free_text(value):
    with pytest.raises(ValidationError):
        event(metric_version=2, client_turn_id=value)
