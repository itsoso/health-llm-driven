# -*- coding: utf-8 -*-
"""因果记忆的证据地板回归测试。"""
from datetime import date, timedelta

from app.services.causal_memory import notes_from_impact


def _impact(
    before,
    after,
    *,
    baseline=None,
    samples=None,
    noise=None,
    title="补充维D",
    window=30,
):
    """构造带按指标样本数的 event-impact 合约。"""
    metrics = set(before) | set(after) | set(baseline or {})
    default_counts = {metric: 20 for metric in metrics}
    sample_counts = samples or {
        "before": default_counts,
        "after": default_counts,
        "baseline": default_counts,
    }
    return {
        "title": title,
        "window_days": window,
        "before": before,
        "after": after,
        "baseline": baseline or {},
        "noise": noise or {},
        "metric_samples": sample_counts,
    }


def test_net_effect_note_direction():
    notes = notes_from_impact(_impact(
        before={"hrv": 40, "rhr": 60},
        after={"hrv": 52, "rhr": 70},
        baseline={"hrv": 40, "rhr": 60},
        noise={"hrv": 3.0, "rhr": 2.0},
    ))

    by_metric = {note["metric"]: note for note in notes}
    assert by_metric["hrv"]["direction"] == "改善"
    assert by_metric["rhr"]["direction"] == "走低"
    assert "相关非因果" in by_metric["hrv"]["text"]
    assert by_metric["hrv"]["evidence_tier"] == "observational"


def test_missing_metric_samples_fails_closed():
    impact = {
        "title": "补充维D",
        "window_days": 30,
        "before": {"hrv": 40, "samples": 30},
        "after": {"hrv": 60, "samples": 30},
        "baseline": {"hrv": 40},
        "noise": {"hrv": 1.0},
    }

    assert notes_from_impact(impact) == []


def test_missing_matched_baseline_fails_closed():
    assert notes_from_impact(_impact(
        before={"hrv": 40},
        after={"hrv": 60},
        baseline={},
        noise={"hrv": 1.0},
    )) == []


def test_metric_specific_sample_floor_not_window_row_count():
    samples = {
        "before": {"hrv": 1, "rhr": 20},
        "after": {"hrv": 1, "rhr": 20},
        "baseline": {"hrv": 1, "rhr": 20},
    }
    impact = _impact(
        before={"hrv": 40, "rhr": 60, "samples": 20},
        after={"hrv": 60, "rhr": 70, "samples": 20},
        baseline={"hrv": 40, "rhr": 60},
        samples=samples,
        noise={"hrv": 1.0, "rhr": 2.0},
    )

    assert {note["metric"] for note in notes_from_impact(impact)} == {"rhr"}


def test_control_window_removes_pre_existing_trend():
    notes = notes_from_impact(_impact(
        before={"hrv": 50},
        after={"hrv": 60},
        baseline={"hrv": 40},
        noise={"hrv": 2.0},
    ))

    assert notes == []


def test_noise_band_suppresses_change_within_variability():
    notes = notes_from_impact(_impact(
        before={"hrv": 50},
        after={"hrv": 56},
        baseline={"hrv": 50},
        noise={"hrv": 12.0},
    ))

    assert notes == []


def test_clinician_gated_metric_never_attributed(monkeypatch):
    from app.services import causal_memory

    monkeypatch.setitem(causal_memory._METRIC_META, "ldl", ("LDL", False))
    notes = notes_from_impact(_impact(
        before={"hrv": 50, "ldl": 120},
        after={"hrv": 62, "ldl": 100},
        baseline={"hrv": 50, "ldl": 120},
        noise={"hrv": 3.0, "ldl": 2.0},
    ))

    assert {note["metric"] for note in notes} == {"hrv"}


def test_derive_empty_when_no_events(db):
    from app.services.causal_memory import derive_causal_notes

    out = derive_causal_notes(db, user_id=99999)

    assert out["notes"] == []
    assert out["evidence_tier"] == "observational"


def test_causal_notes_endpoint_runs_real_authenticated_flow(db, client):
    from app.models.daily_health import GarminData
    from app.models.medical_exam import MedicalExam
    from app.models.user import User
    from app.services.auth import auth_service

    user = User(
        username="causal-notes-user",
        email="causal-notes@example.com",
        hashed_password="not-used-in-test",
        name="因果测试用户",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    token = auth_service.create_access_token({"sub": str(user.id)})
    event_date = date.today() - timedelta(days=35)
    exam = MedicalExam(user_id=user.id, exam_date=event_date, exam_type="comprehensive")
    db.add(exam)

    for offset, hrv in [
        *[(day, 50.0) for day in range(-60, -55)],
        *[(day, 50.0) for day in range(-5, 0)],
        *[(day, 65.0) for day in range(0, 5)],
    ]:
        db.add(GarminData(user_id=user.id, record_date=event_date + timedelta(days=offset), hrv=hrv))
    db.commit()

    response = client.get(
        "/api/v1/personal-outcome/me/causal-notes",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_tier"] == "observational"
    assert any(note["metric"] == "hrv" for note in payload["notes"])
    assert all("相关非因果" in note["text"] for note in payload["notes"])


def test_endpoint_requires_auth(client):
    response = client.get("/api/v1/personal-outcome/me/causal-notes")

    assert response.status_code in (401, 403)
