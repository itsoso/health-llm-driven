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


def test_client_events_stats_computes_diet_capture_latency_and_failures(db):
    from app.models.user import User
    from app.services.observability_service import client_events_stats, utc_now

    user = User(username="diet-obs", email="diet-obs@test.com", hashed_password="x", name="d")
    db.add(user)
    db.commit()
    db.refresh(user)
    for index, duration in enumerate((1200, 2400, 6200, 9100), start=1):
        _seed(db, user.id, "diet_photo_recognition_terminal", {
            "phase": "completed", "duration_ms": duration,
            "client_prepare_ms": index * 100,
            "payload_bytes": index * 100 * 1024,
            "food_count": 2, "table_calibrated_count": 1,
        })
    _seed(db, user.id, "diet_photo_recognition_terminal", {
        "phase": "failed", "duration_ms": 290000, "error_code": "vision_timeout",
        "food_count": 0, "table_calibrated_count": 0,
    })
    _seed(db, user.id, "diet_photo_recognition_terminal", {
        "phase": "cancelled", "duration_ms": 280000,
        "food_count": 0, "table_calibrated_count": 0,
    })
    _seed(db, user.id, "diet_photo_confirmation_terminal", {
        "phase": "completed", "duration_ms": 420, "verified": True,
        "corrected": True,
    })
    _seed(db, user.id, "diet_share_terminal", {
        "phase": "completed", "duration_ms": 900, "has_photo": True,
        "share_target": "wechat",
    })
    _seed(db, user.id, "diet_share_terminal", {
        "phase": "completed", "duration_ms": 1200, "has_photo": True,
        "share_target": "xiaohongshu",
    })
    _seed(db, user.id, "diet_share_terminal", {
        "phase": "completed", "duration_ms": 600, "has_photo": False,
        "share_target": "generic",
    })
    _seed(db, user.id, "diet_share_terminal", {
        "phase": "failed", "duration_ms": 800, "has_photo": True,
        "share_target": "wechat",
    })
    db.commit()

    stats = client_events_stats(db, utc_now() - timedelta(days=7), user_id=None)

    recognition = stats["diet_capture_ms"]["recognition"]
    assert recognition == {
        "n": 4,
        "attempts": 6,
        "p50": 4300,
        "p95": 8665,
        "failures": 1,
        "cancelled": 1,
        "client_prepare_p50": 250,
        "client_prepare_p95": 385,
        "payload_kb_p50": 250,
        "payload_kb_p95": 385,
    }
    assert stats["diet_capture_ms"]["confirmation"] == {
        "n": 1, "attempts": 1, "p50": 420, "p95": 420,
        "failures": 0, "cancelled": 0,
        "corrected": 1, "correction_rate_pct": 100.0,
    }
    assert stats["diet_capture_ms"]["share"]["by_target"] == {
        "generic": {"attempts": 1, "completed": 1, "with_photo": 0, "failures": 0},
        "wechat": {"attempts": 2, "completed": 1, "with_photo": 1, "failures": 1},
        "xiaohongshu": {"attempts": 1, "completed": 1, "with_photo": 1, "failures": 0},
    }


def test_client_events_stats_aggregates_chat_attachment_pipeline(db):
    from app.models.user import User
    from app.services.observability_service import client_events_stats, utc_now

    user = User(
        username="attachment-obs",
        email="attachment-obs@test.com",
        hashed_password="x",
        name="attachment",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _seed(db, user.id, "chat_attachment_terminal", {
        "phase": "accepted",
        "stage": "server_accept",
        "image_count": 2,
        "duration_bucket": "3_10s",
        "payload_bucket": "1_4mb",
    })
    _seed(db, user.id, "chat_attachment_terminal", {
        "phase": "failed",
        "stage": "local_prepare",
        "image_count": 1,
        "duration_bucket": "lt_1s",
        "payload_bucket": "unknown",
        "error_code": "draft_hydration_failed",
    })
    _seed(db, user.id, "chat_attachment_terminal", {
        "phase": "failed",
        "stage": "server_accept",
        "image_count": 3,
        "duration_bucket": "10_30s",
        "payload_bucket": "gte_4mb",
        "error_code": "server_not_accepted",
    })
    db.commit()

    pipeline = client_events_stats(
        db,
        utc_now() - timedelta(days=7),
        user_id=None,
    )["chat_attachment_pipeline"]

    assert pipeline == {
        "attempts": 3,
        "accepted": 1,
        "failures": 2,
        "acceptance_rate_pct": 33.3,
        "image_count_total": 6,
        "failures_by_stage": {
            "local_prepare": 1,
            "server_accept": 1,
        },
        "duration_buckets": {
            "lt_1s": 1,
            "3_10s": 1,
            "10_30s": 1,
        },
        "payload_buckets": {
            "unknown": 1,
            "1_4mb": 1,
            "gte_4mb": 1,
        },
    }


def test_app_update_release_health_observes_until_minimum_sample():
    from app.services.observability_service import app_update_release_health

    result = app_update_release_health(
        launches=19,
        emergency_launches=19,
        terminal_attempts=2,
        terminal_failures=2,
    )

    assert result["status"] == "observe"
    assert result["sample_sufficient"] is False
    assert result["emergency_rate_pct"] == 100.0
    assert result["terminal_failure_rate_pct"] == 100.0
    assert result["reasons"] == ["发布启动样本不足 20，继续观察"]


def test_app_update_release_health_marks_stable_sample_healthy():
    from app.services.observability_service import app_update_release_health

    result = app_update_release_health(
        launches=20,
        emergency_launches=0,
        terminal_attempts=20,
        terminal_failures=1,
    )

    assert result["status"] == "healthy"
    assert result["sample_sufficient"] is True
    assert result["emergency_rate_pct"] == 0.0
    assert result["terminal_failure_rate_pct"] == 5.0
    assert result["reasons"] == ["发布启动与更新终态均在阈值内"]


def test_app_update_release_health_pauses_on_emergency_or_terminal_failures():
    from app.services.observability_service import app_update_release_health

    emergency_result = app_update_release_health(
        launches=20,
        emergency_launches=1,
        terminal_attempts=20,
        terminal_failures=0,
    )
    failure_result = app_update_release_health(
        launches=20,
        emergency_launches=0,
        terminal_attempts=20,
        terminal_failures=2,
    )

    assert emergency_result["status"] == "pause_rollout"
    assert emergency_result["reasons"] == ["紧急启动率 5.0% 达到暂停阈值 5.0%"]
    assert failure_result["status"] == "pause_rollout"
    assert failure_result["reasons"] == ["更新失败率 10.0% 达到暂停阈值 10.0%"]


def test_app_update_release_health_keeps_missing_terminal_denominator_null():
    from app.services.observability_service import app_update_release_health

    result = app_update_release_health(
        launches=20,
        emergency_launches=0,
        terminal_attempts=0,
        terminal_failures=0,
    )

    assert result["status"] == "healthy"
    assert result["terminal_failure_rate_pct"] is None
    assert result["reasons"] == ["发布启动与更新终态均在阈值内"]


def test_app_update_release_health_excludes_non_outcome_terminal_phases(db):
    from app.models.user import User
    from app.services.observability_service import client_events_stats, utc_now

    user = User(
        username="release-health",
        email="release-health@test.com",
        hashed_password="x",
        name="release-health",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    for _ in range(20):
        _seed(db, user.id, "app_update_launch", {"launch_source": "ota"})
    _seed(db, user.id, "app_update_terminal", {"phase": "current"})
    for _ in range(18):
        _seed(db, user.id, "app_update_terminal", {"phase": "ready"})
    for _ in range(2):
        _seed(db, user.id, "app_update_terminal", {"phase": "failed"})
    db.commit()

    health = client_events_stats(db, utc_now() - timedelta(days=7), user_id=None)[
        "app_update"
    ]["release_health"]

    assert health["terminal_attempts"] == 20
    assert health["terminal_failures"] == 2
    assert health["terminal_failure_rate_pct"] == 10.0
    assert health["status"] == "pause_rollout"
