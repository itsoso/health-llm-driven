from datetime import date, datetime, timedelta, timezone


def test_update_exercise_record_endpoint(client, auth_user_and_headers):
    _user, headers = auth_user_and_headers

    create_resp = client.post(
        "/api/v1/daily-health/exercise",
        headers=headers,
        json={
            "record_date": str(date.today()),
            "exercise_type": "俯卧撑",
            "reps": 10,
            "sets": 1,
        },
    )
    assert create_resp.status_code == 200
    record_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/v1/daily-health/exercise/{record_id}",
        headers=headers,
        json={"reps": 20, "sets": 2, "notes": "修正重复记录"},
    )

    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["id"] == record_id
    assert body["reps"] == 20
    assert body["sets"] == 2
    assert body["notes"] == "修正重复记录"


def test_update_symptom_endpoint(client, auth_user_and_headers):
    _user, headers = auth_user_and_headers

    create_resp = client.post(
        "/api/v1/symptoms",
        headers=headers,
        json={
            "body_part": "respiratory",
            "description": "鼻塞",
            "severity": 5,
            "triggers": ["dust"],
        },
    )
    assert create_resp.status_code == 201
    symptom_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/v1/symptoms/{symptom_id}",
        headers=headers,
        json={"severity": 2, "notes": "洗鼻后缓解"},
    )

    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["id"] == symptom_id
    assert body["severity"] == 2
    assert body["notes"] == "洗鼻后缓解"


def test_update_medication_log_endpoint(client, auth_user_and_headers):
    _user, headers = auth_user_and_headers

    med_resp = client.post(
        "/api/v1/medication/medications",
        headers=headers,
        json={"name": "异丙托溴铵鼻喷雾剂", "dosage": "每侧2喷"},
    )
    assert med_resp.status_code == 200
    med_id = med_resp.json()["id"]

    log_resp = client.post(
        "/api/v1/medication/logs",
        headers=headers,
        json={"medication_id": med_id, "taken_time": "08:00", "status": "taken"},
    )
    assert log_resp.status_code == 200
    log_id = log_resp.json()["id"]

    update_resp = client.put(
        f"/api/v1/medication/logs/{log_id}",
        headers=headers,
        json={"status": "skipped", "skip_reason": "医生要求暂停", "taken_time": "09:00"},
    )

    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["id"] == log_id
    assert body["status"] == "skipped"
    assert body["skip_reason"] == "医生要求暂停"
    assert body["taken_time"] == "09:00"


def test_update_reminder_endpoint(client, auth_user_and_headers):
    _user, headers = auth_user_and_headers
    remind_at = datetime.now(timezone(timedelta(hours=8))) + timedelta(hours=2)

    create_resp = client.post(
        "/api/v1/reminders/me",
        headers=headers,
        json={
            "title": "吃药",
            "message": "早药",
            "remind_at": remind_at.isoformat(),
            "priority": "normal",
        },
    )
    assert create_resp.status_code == 201
    reminder_id = create_resp.json()["id"]

    next_time = remind_at + timedelta(hours=1)
    update_resp = client.put(
        f"/api/v1/reminders/{reminder_id}",
        headers=headers,
        json={
            "title": "明早复查血压",
            "remind_at": next_time.isoformat(),
            "priority": "high",
        },
    )

    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["id"] == reminder_id
    assert body["title"] == "明早复查血压"
    assert body["priority"] == "high"
