from unittest.mock import MagicMock

import pytest


def test_retention_job_is_registered_hourly():
    from app.celery_app import celery_app
    entry = celery_app.conf.beat_schedule['purge-daily-journeys']
    assert entry['task'] == 'app.tasks.maintenance.purge_expired_daily_journeys'
    assert entry['schedule'].hour == set(range(24))


def test_retention_job_bounds_work_and_propagates_sanitized_failure(monkeypatch):
    from app.tasks import maintenance
    from app.services import daily_journey
    session = MagicMock()
    monkeypatch.setattr(maintenance, 'SessionLocal', lambda: session)
    purge = MagicMock(return_value=100)
    monkeypatch.setattr(daily_journey, 'purge_expired', purge)
    result = maintenance.purge_expired_daily_journeys.run()
    assert result == {'deleted_sessions': 1000, 'batch_limit_reached': True}
    assert purge.call_count == 10
    purge.side_effect = RuntimeError('synthetic-sensitive-coordinate')
    with pytest.raises(RuntimeError, match='daily_journey_retention_failed') as failure:
        maintenance.purge_expired_daily_journeys.run()
    assert 'synthetic-sensitive-coordinate' not in str(failure.value)
    assert failure.value.__context__ is None
