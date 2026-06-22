"""赛后复盘 (post-session exercise review) endpoint tests — R4 observational.

The review endpoint builds the user's twin + runs MovementCoach. ``build_twin``
opens its OWN SessionLocal (it ignores the request ``db``), so in tests it would
hit the real DB. We therefore monkeypatch the review's ``_movement_context``
seam to inject deterministic training context / imperative phrases — tests never
depend on a live DB or wearable data.
"""
from datetime import datetime, timezone

import app.services.rokid_pushup_review as review_svc
from tests.conftest import create_authenticated_user


def _create_session(client, headers, target_reps: int = 20) -> dict:
    res = client.post(
        "/api/v1/devices/rokid/pushup-sessions",
        json={"target_reps": target_reps},
        headers=headers,
    )
    assert res.status_code == 201
    return res.json()


def _ingest(client, session: dict, *, reps: int, quality: float, phase: str = "up"):
    res = client.post(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/events",
        headers={"X-Reva-Rokid-Session-Token": session["ingest_token"]},
        json={
            "event_type": "rep",
            "phase": phase,
            "reps": reps,
            "quality_score": quality,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert res.status_code == 201
    return res.json()


def test_review_happy_path_returns_quality_and_sanitized_observations(
    client, auth_user_and_headers, monkeypatch
):
    _, headers = auth_user_and_headers
    session = _create_session(client, headers)
    _ingest(client, session, reps=6, quality=80)
    _ingest(client, session, reps=12, quality=76)

    # Inject a clean, observational MovementCoach context — no live twin/DB.
    monkeypatch.setattr(
        review_svc,
        "_movement_context",
        lambda db, user_id: (
            {
                "acwr": 1.1,
                "training_status": "optimal",
                "readiness_zone": "moderate",
                "today_intensity": "moderate",
            },
            "训练 负荷最佳区（ACWR 1.10）· 今日建议 moderate",
        ),
    )

    res = client.get(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/review",
        headers=headers,
    )

    assert res.status_code == 200
    body = res.json()
    assert body["session_id"] == session["id"]

    # session_quality: max rep count, avg of quality scores, total events
    assert body["session_quality"]["reps"] == 12
    assert body["session_quality"]["avg_quality_score"] == 78.0
    assert body["session_quality"]["event_count"] == 2

    # training_context surfaced from MovementCoach
    assert body["training_context"]["acwr"] == 1.1
    assert body["training_context"]["training_status"] == "optimal"

    # observational wording, no guidance violations
    assert any("本组完成 12 个" in o for o in body["observations"])
    assert any("ACWR" in o for o in body["observations"])
    assert body["guidance_sanitized"] is False
    assert body["guidance_alerts"] == []

    # teaching link points at the existing exercise-guide pushup entry
    assert body["teaching_links"]
    link = body["teaching_links"][0]
    assert link["key"] == "pushup"
    assert link["url"] == "/fitness/exercise-guide/pushup"

    assert "相关非因果" in body["disclaimer"]


def test_review_user_isolation_returns_404_cross_user(
    client, db, auth_user_and_headers
):
    _, owner_headers = auth_user_and_headers
    session = _create_session(client, owner_headers)

    _, other_token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    res = client.get(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/review",
        headers=other_headers,
    )
    assert res.status_code == 404


def test_review_missing_session_returns_404(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    res = client.get(
        "/api/v1/devices/rokid/pushup-sessions/999999/review",
        headers=headers,
    )
    assert res.status_code == 404


def test_review_degrades_gracefully_without_training_data(
    client, auth_user_and_headers, monkeypatch
):
    _, headers = auth_user_and_headers
    session = _create_session(client, headers)
    _ingest(client, session, reps=8, quality=70)

    # No usable training-load data → MovementCoach yields nothing.
    monkeypatch.setattr(
        review_svc, "_movement_context", lambda db, user_id: (None, None)
    )

    res = client.get(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/review",
        headers=headers,
    )

    assert res.status_code == 200
    body = res.json()
    # quality still computed
    assert body["session_quality"]["reps"] == 8
    assert body["session_quality"]["avg_quality_score"] == 70.0
    # neutral degradation observation, not a fake success / not a 500
    assert body["training_context"] is None
    assert any("暂无足够训练负荷数据" in o for o in body["observations"])
    assert body["guidance_alerts"] == []


def test_review_sanitizes_and_alerts_imperative_movement_phrase(
    client, auth_user_and_headers, monkeypatch
):
    _, headers = auth_user_and_headers
    session = _create_session(client, headers)
    _ingest(client, session, reps=10, quality=72)

    # MovementCoach summary leaks an imperative training command.
    imperative = "你必须做满 3 组,并立刻放慢动作。"
    monkeypatch.setattr(
        review_svc,
        "_movement_context",
        lambda db, user_id: (
            {
                "acwr": 1.6,
                "training_status": "overload",
                "readiness_zone": "light",
                "today_intensity": "low",
            },
            imperative,
        ),
    )

    res = client.get(
        f"/api/v1/devices/rokid/pushup-sessions/{session['id']}/review",
        headers=headers,
    )

    assert res.status_code == 200
    body = res.json()

    # The imperative phrase must NOT survive verbatim in any observation.
    assert all("必须做满 3 组" not in o for o in body["observations"])
    assert all("立刻放慢" not in o for o in body["observations"])
    # It was flagged + softened.
    assert body["guidance_sanitized"] is True
    assert body["guidance_violations"]
    # And surfaced as an auditable movement-imperative alert.
    assert body["guidance_alerts"]
    rule_ids = {a["rule_id"] for a in body["guidance_alerts"]}
    assert "guidance_red_lines.movement_imperative_red_line" in rule_ids


def test_compute_session_quality_handles_missing_scores():
    """Pure aggregation: no quality scores → avg None, reps from max, count kept."""
    from app.models.rokid_pushup import RokidPushupEvent

    events = [
        RokidPushupEvent(event_type="rep", reps=3, quality_score=None),
        RokidPushupEvent(event_type="rep", reps=7, quality_score=None),
        RokidPushupEvent(event_type="pose", reps=None, quality_score=None),
    ]
    quality = review_svc.compute_session_quality(events)
    assert quality["reps"] == 7
    assert quality["avg_quality_score"] is None
    assert quality["event_count"] == 3
