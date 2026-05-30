"""client_events_stats: starter CTR + cold-start percentile aggregation (#4a)."""
from datetime import timedelta


def _seed(db, user_id, name, meta):
    from app.models.client_event import ClientEvent
    db.add(ClientEvent(user_id=user_id, event_name=name, meta=meta))


def test_client_events_stats_computes_starter_ctr_and_cold_start(db):
    from app.models.user import User
    from app.services.observability_service import client_events_stats, utc_now

    user = User(username="obs", email="obs@test.com", hashed_password="x", name="o")
    db.add(user)
    db.commit()
    db.refresh(user)

    # 2 chip sets shown: keys [readiness, aqi] then [readiness, water]
    _seed(db, user.id, "starter_chips_shown", {"keys": ["readiness", "aqi"], "source": "chat"})
    _seed(db, user.id, "starter_chips_shown", {"keys": ["readiness", "water"], "source": "chat"})
    # clicks: readiness x2, aqi x0, water x1
    _seed(db, user.id, "starter_chip_clicked", {"key": "readiness", "priority": 80, "position": 0})
    _seed(db, user.id, "starter_chip_clicked", {"key": "readiness", "priority": 80, "position": 0})
    _seed(db, user.id, "starter_chip_clicked", {"key": "water", "priority": 50, "position": 1})
    # cold start timings
    for ms in (800, 1200, 1600, 5000):
        _seed(db, user.id, "home_cold_start_perf", {"emitted_at_ms": ms, "incomplete": ms >= 5000})
    db.commit()

    stats = client_events_stats(db, utc_now() - timedelta(days=7), user_id=None)

    ctr = stats["starter_ctr"]
    # readiness: 2 impressions, 2 clicks → 100%
    assert ctr["readiness"] == {"impressions": 2, "clicks": 2, "ctr_pct": 100.0}
    # aqi: 1 impression, 0 clicks → 0% (a "dead-ish" generator candidate)
    assert ctr["aqi"]["impressions"] == 1 and ctr["aqi"]["clicks"] == 0 and ctr["aqi"]["ctr_pct"] == 0.0
    # water: 1 impression, 1 click → 100%
    assert ctr["water"] == {"impressions": 1, "clicks": 1, "ctr_pct": 100.0}

    cold = stats["home_cold_start_ms"]
    assert cold["n"] == 4
    assert cold["incomplete"] == 1
    assert cold["p50"] is not None and cold["p95"] is not None
    assert cold["p50"] <= cold["p95"]

    assert stats["by_event"]["starter_chip_clicked"] == 3


def test_client_events_weekly_digest_task_runs(db, monkeypatch):
    """The scheduled digest task computes + logs without error and flags dead generators."""
    from app.models.user import User
    from app.tasks import observability_digest

    user = User(username="obs2", email="obs2@test.com", hashed_password="x", name="o2")
    db.add(user)
    db.commit()
    db.refresh(user)

    # a clearly-dead generator: 25 impressions, 0 clicks
    from app.models.client_event import ClientEvent
    for _ in range(25):
        db.add(ClientEvent(user_id=user.id, event_name="starter_chips_shown", meta={"keys": ["deadgen"]}))
    db.commit()

    # the task opens its own `with SessionLocal() as db:` — feed it the test session
    # via a context manager that does NOT close it (test owns the lifecycle).
    import contextlib

    @contextlib.contextmanager
    def _fake_session():
        yield db

    monkeypatch.setattr(observability_digest, "SessionLocal", _fake_session)

    result = observability_digest.client_events_weekly_digest(days=7)
    assert "deadgen" in result["dead_starter_keys"]
    assert result["starter_ctr"]["deadgen"]["clicks"] == 0
