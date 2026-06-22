"""Meal monitoring (准视频) backend tests.

Covers: session lifecycle (start/frame/finish/confirm), throttle (429),
R4 draft gate (finish -> needs_confirmation with NO DietRecord until confirm),
user isolation, consent, and the raw-media purge.
"""
import uuid

from app.models.user import User
from app.models.ambient_wearable import MealMonitoringSession, VisualInputEvent
from app.models.daily_health import DietRecord


def _auth(db):
    user = User(
        username=f"meal_{uuid.uuid4().hex[:8]}",
        email=f"meal_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="meal",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.auth import auth_service

    return user, {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


def _recognition(name="牛肉面", calories=620, protein=32, confidence=0.8):
    return {
        "success": True,
        "foods": [
            {
                "name": name,
                "quantity": 1,
                "unit": "碗",
                "calories": calories,
                "protein": protein,
                "carbs": 78,
                "fat": 20,
                "fiber": 4,
                "confidence": confidence,
            }
        ],
        "meal_type": "lunch",
    }


def _start(client, headers, consent=True):
    return client.post(
        "/api/v1/ambient/meal-sessions",
        headers=headers,
        json={"consent": consent, "source": "rokid_glasses", "device_type": "glasses"},
    )


# ─────────────────────── start / consent ───────────────────────


def test_start_meal_session_requires_consent(client, db):
    _, headers = _auth(db)
    resp = _start(client, headers, consent=False)
    assert resp.status_code == 400, resp.text


def test_start_meal_session_with_consent_creates_session(client, db):
    user, headers = _auth(db)
    resp = _start(client, headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "active"
    assert body["frame_count"] == 0
    assert body["consent_at"] is not None
    assert body["raw_media_delete_at"] is not None  # +7d TTL set
    session = db.query(MealMonitoringSession).filter(MealMonitoringSession.user_id == user.id).one()
    assert session.id == body["id"]


# ─────────────────────── frames + throttle ───────────────────────


def test_append_frame_increments_count_and_links_to_session(client, db):
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    resp = client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"recognition_result": _recognition()},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["frame_count"] == 1
    frame = db.query(VisualInputEvent).filter(VisualInputEvent.id == body["frame_event_id"]).one()
    assert frame.target_type == "meal_frame"
    assert frame.target_id == sid
    assert frame.meta["meal_session_id"] == sid
    assert frame.status == "captured"


def test_frame_throttle_returns_429_not_silent_drop(client, db):
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    # 30 frames allowed
    for _ in range(30):
        ok = client.post(
            f"/api/v1/ambient/meal-sessions/{sid}/frames",
            headers=headers,
            json={"recognition_result": _recognition()},
        )
        assert ok.status_code == 201, ok.text
    over = client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"recognition_result": _recognition()},
    )
    assert over.status_code == 429, over.text
    assert "frame limit" in over.json()["detail"]


def test_session_throttle_returns_429_after_daily_limit(client, db):
    user, headers = _auth(db)
    for _ in range(5):
        assert _start(client, headers).status_code == 201
    sixth = _start(client, headers)
    assert sixth.status_code == 429, sixth.text
    assert "session limit" in sixth.json()["detail"]


# ─────────────────────── R4 draft gate ───────────────────────


def test_finish_produces_draft_needs_confirmation_no_diet_record(client, db):
    """R4: finish batch-analyzes into a DRAFT — NO DietRecord written until confirm."""
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    for _ in range(3):
        client.post(
            f"/api/v1/ambient/meal-sessions/{sid}/frames",
            headers=headers,
            json={"recognition_result": _recognition()},
        )

    finish = client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers)
    assert finish.status_code == 200, finish.text
    body = finish.json()
    summary = body["summary"]
    assert summary["status"] == "needs_confirmation"
    assert summary["target"] == "diet_draft"
    # dedup: 3 identical frames -> 1 food, total not multiplied
    assert len(summary["foods"]) == 1
    assert summary["totals"]["calories"] == 620
    assert body["session"]["status"] == "needs_confirmation"
    # R4: nothing written until explicit confirm
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 0


def test_confirm_writes_diet_record_via_existing_gate(client, db):
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"recognition_result": _recognition()},
    )
    client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers)

    confirm = client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/confirm",
        headers=headers,
        json={"confirm": True},
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["session"]["status"] == "confirmed"
    record = db.query(DietRecord).filter(DietRecord.user_id == user.id).one()
    assert body["diet_record_id"] == record.id
    assert record.calories == 620
    assert record.ai_recognized == 1


def test_confirm_false_rejected(client, db):
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"recognition_result": _recognition()},
    )
    client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers)
    resp = client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/confirm",
        headers=headers,
        json={"confirm": False},
    )
    assert resp.status_code == 400, resp.text
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 0


def test_cannot_confirm_before_finish(client, db):
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"recognition_result": _recognition()},
    )
    resp = client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/confirm",
        headers=headers,
        json={"confirm": True},
    )
    assert resp.status_code == 409, resp.text


# ─────────────────────── observational summary ───────────────────────


def test_finish_summary_is_observational_not_imperative(client, db):
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"recognition_result": _recognition()},
    )
    body = client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers).json()
    text = body["summary"]["observational_summary"]
    assert "约" in text  # observational ("这餐约 X kcal")
    # no imperative dietary prescription leaked
    assert "别吃" not in text
    assert "每天吃" not in text
    # the guidance red-line rules ran and found nothing on clean observational text
    assert body["summary"]["guidance_alerts"] == []
    assert body["summary"]["guidance_sanitized"] is False


# ─────────────────────── user isolation ───────────────────────


def test_cross_user_session_access_is_not_found(client, db):
    user_a, headers_a = _auth(db)
    user_b, headers_b = _auth(db)
    sid = _start(client, headers_a).json()["id"]

    # B cannot read A's session
    get_b = client.get(f"/api/v1/ambient/meal-sessions/{sid}", headers=headers_b)
    assert get_b.status_code == 404, get_b.text
    # B cannot add frames to A's session
    frame_b = client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers_b,
        json={"recognition_result": _recognition()},
    )
    assert frame_b.status_code == 404, frame_b.text
    # B cannot finish A's session
    finish_b = client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers_b)
    assert finish_b.status_code == 404, finish_b.text


# ─────────────────────── privacy: raw-media purge ───────────────────────


def test_confirm_purges_raw_media_keeps_analysis(client, db):
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    frame_resp = client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"image_base64": "ZmFrZS1pbWFnZS1ieXRlcw==", "recognition_result": _recognition()},
    )
    frame_id = frame_resp.json()["frame_event_id"]
    client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers)
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/confirm",
        headers=headers,
        json={"confirm": True},
    )
    db.expire_all()
    frame = db.query(VisualInputEvent).filter(VisualInputEvent.id == frame_id).one()
    # raw image gone, analysis notes (recognition_result) retained
    assert frame.image_uri is None
    assert "image_base64" not in (frame.meta or {})
    assert frame.recognition_result is not None


def test_purge_expired_raw_media_hook(client, db):
    from datetime import datetime, timedelta, timezone
    from app.services import meal_monitoring as meal_svc

    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"image_base64": "ZmFrZQ==", "recognition_result": _recognition()},
    )
    # force the TTL into the past
    session = db.query(MealMonitoringSession).filter(MealMonitoringSession.id == sid).one()
    session.raw_media_delete_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    purged = meal_svc.purge_expired_raw_media(db)
    assert purged == 1
    db.expire_all()
    session = db.query(MealMonitoringSession).filter(MealMonitoringSession.id == sid).one()
    assert session.raw_media_deleted_at is not None
    frames = db.query(VisualInputEvent).filter(
        VisualInputEvent.target_type == "meal_frame", VisualInputEvent.target_id == sid
    ).all()
    assert all(f.image_uri is None for f in frames)


# ─────────────────────── celery wiring: task registered + beat scheduled ─────


def test_purge_task_importable_and_registered():
    """The raw-media purge Celery task must be importable and registered, else the
    beat entry below would point at a task that never runs."""
    from app.tasks.maintenance import purge_expired_meal_raw_media  # noqa: F401
    from app.celery_app import celery_app

    assert "app.tasks.maintenance.purge_expired_meal_raw_media" in celery_app.tasks


def test_beat_schedule_has_meal_raw_media_purge():
    """The L3 raw-media TTL has exactly one backstop: the daily beat task. If this
    entry is missing, raw base64 meal photos for finished-but-unconfirmed /
    abandoned sessions linger forever. Assert the schedule wiring stays intact."""
    from celery.schedules import crontab
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("purge-meal-raw-media")
    assert entry is not None
    assert entry["task"] == "app.tasks.maintenance.purge_expired_meal_raw_media"
    # daily, aligned just after the 03:00 data-cleanup task
    assert entry["schedule"] == crontab(hour=3, minute=5)


# ─────────────────────── guidance: rules run over PRE-sanitization text ──────


def test_post_meal_summary_includes_daily_context(db, monkeypatch):
    """council #1 regression: build_twin must receive db (was called build_twin(user_id, ...)
    → user_id landed in the db param → TypeError → swallowed at INFO → the documented
    daily-context lines never shipped). With a twin + FuelStrategist findings, the
    observational daily-context lines must appear in the summary text."""
    import app.services.meal_analysis as meal_analysis

    class _Finding:
        summary = "营养观察"
        findings = [
            {"type": "energy", "remaining_kcal": 300},
            {"type": "protein", "target_g": 120, "today_g": 80},
        ]

    class _Fuel:
        def run(self, twin, ctx):
            return _Finding()

    monkeypatch.setattr("app.twin.builder.build_twin", lambda d, uid, use_cache=True: object())
    monkeypatch.setattr(
        "app.agents.fuel_strategist.strategist.FuelStrategistSpecialist", _Fuel
    )

    out = meal_analysis.post_meal_observational_summary(db, 1, {"calories": 620, "protein": 32})
    assert "今日还剩约 300 kcal 空间" in out["text"]
    assert "今日蛋白还差约 40g" in out["text"]
    # still observational, never imperative
    assert "别吃" not in out["text"] and "必须" not in out["text"]


def test_finish_summary_alerts_on_prescription_even_when_stripped(client, db, monkeypatch):
    """If the post-meal text contains a prescription, the client gets the SANITIZED
    text BUT the guidance red-line rules still fire (run over raw text) so the
    stripped prescription is auditable, not silently swallowed."""
    import app.services.meal_analysis as meal_analysis

    def _prescriptive_summary(db, user_id, totals):
        return {
            "text": "这餐约 620 kcal。建议每天吃 50 克坚果, 别吃米饭。",
            "fuel_summary": "",
            "fuel_findings": [],
        }

    monkeypatch.setattr(
        meal_analysis, "post_meal_observational_summary", _prescriptive_summary
    )

    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"recognition_result": _recognition()},
    )
    body = client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers).json()
    summary = body["summary"]

    # client receives sanitized text (prescription stripped)
    assert "每天吃 50 克" not in summary["observational_summary"]
    assert "别吃米饭" not in summary["observational_summary"]
    assert summary["guidance_sanitized"] is True
    # rules ran over RAW text -> a CRITICAL diet alert is still recorded
    assert len(summary["guidance_alerts"]) >= 1
    assert any(
        a["rule_id"] == "guidance_red_lines.diet_prescription_red_line"
        for a in summary["guidance_alerts"]
    )


# ─────────────────────── abort ───────────────────────


def test_abort_active_session_purges_base64_and_sets_status(client, db):
    """Abort an active (never-confirmed) session -> status aborted + base64 purged."""
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    frame_resp = client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"image_base64": "ZmFrZS1pbWFnZS1ieXRlcw==", "recognition_result": _recognition()},
    )
    frame_id = frame_resp.json()["frame_event_id"]

    abort = client.post(f"/api/v1/ambient/meal-sessions/{sid}/abort", headers=headers)
    assert abort.status_code == 200, abort.text
    assert abort.json()["session"]["status"] == "aborted"

    db.expire_all()
    session = db.query(MealMonitoringSession).filter(MealMonitoringSession.id == sid).one()
    assert session.status == "aborted"
    frame = db.query(VisualInputEvent).filter(VisualInputEvent.id == frame_id).one()
    # raw image gone, analysis notes retained
    assert frame.image_uri is None
    assert "image_base64" not in (frame.meta or {})
    assert frame.recognition_result is not None
    # R4: nothing written
    assert db.query(DietRecord).filter(DietRecord.user_id == user.id).count() == 0


def test_cannot_abort_confirmed_session(client, db):
    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"recognition_result": _recognition()},
    )
    client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers)
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/confirm",
        headers=headers,
        json={"confirm": True},
    )
    resp = client.post(f"/api/v1/ambient/meal-sessions/{sid}/abort", headers=headers)
    assert resp.status_code == 409, resp.text


def test_cross_user_abort_is_not_found(client, db):
    _, headers_a = _auth(db)
    _, headers_b = _auth(db)
    sid = _start(client, headers_a).json()["id"]
    resp = client.post(f"/api/v1/ambient/meal-sessions/{sid}/abort", headers=headers_b)
    assert resp.status_code == 404, resp.text


def test_finish_runs_backend_vision_when_frame_lacks_recognition(client, db, monkeypatch):
    """Frames with an inline image but no recognition_result are run through the
    existing vision provider, and each vision call is audited."""
    import app.services.meal_analysis as meal_analysis

    async def _fake_recognize(image_base64):
        return _recognition(name="米饭", calories=200, protein=4)

    monkeypatch.setattr(meal_analysis, "recognize_frame", _fake_recognize)

    user, headers = _auth(db)
    sid = _start(client, headers).json()["id"]
    client.post(
        f"/api/v1/ambient/meal-sessions/{sid}/frames",
        headers=headers,
        json={"image_base64": "ZmFrZS1pbWc="},  # no recognition_result
    )
    body = client.post(f"/api/v1/ambient/meal-sessions/{sid}/finish", headers=headers).json()
    summary = body["summary"]
    assert summary["vision_calls"] == 1
    assert len(summary["foods"]) == 1
    assert summary["foods"][0]["name"] == "米饭"
