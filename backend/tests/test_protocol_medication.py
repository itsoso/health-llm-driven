"""协议层 × 用药打通:完成用药协议 → 写真实 MedicationLog(坐实双轨同源)。

钉:① from-medication 建协议(不可默认完成)② 协议轨完成 → 建 1 条 MedicationLog(status=taken)
③ 重复完成不重复写(每天一条)④ 手工轨也写 MedicationLog ⑤ 不存在的药 400。
"""
from datetime import date


def _make_med(db, user_id, name="雷贝拉唑", dosage="10mg"):
    from app.models.medication import Medication
    m = Medication(user_id=user_id, name=name, dosage=dosage, is_active=True, times_per_day=1)
    db.add(m); db.commit(); db.refresh(m)
    return m


def test_from_medication_creates_protocol(client, auth_user_and_headers, db):
    user, h = auth_user_and_headers
    med = _make_med(db, user.id)
    r = client.post(f"/api/v1/protocols/from-medication/{med.id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["domain"] == "medication"
    assert body["source_model"] == "medication_logs" and body["source_id"] == med.id
    assert body["can_default_complete"] is False   # R12:用药禁止默认完成


def test_complete_writes_medication_log_once(client, auth_user_and_headers, db):
    from app.models.medication import MedicationLog
    user, h = auth_user_and_headers
    med = _make_med(db, user.id)
    pid = client.post(f"/api/v1/protocols/from-medication/{med.id}", headers=h).json()["id"]
    # 协议轨完成 → 写 MedicationLog
    c = client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "protocol"})
    assert c.status_code == 200 and c.json()["status"] == "completed"
    logs = db.query(MedicationLog).filter(MedicationLog.medication_id == med.id).all()
    assert len(logs) == 1 and logs[0].status == "taken"
    # 重复完成(改手工轨)→ 不重复写,仍 1 条
    client.post(f"/api/v1/protocols/{pid}/complete", headers=h, json={"track": "manual"})
    assert db.query(MedicationLog).filter(MedicationLog.medication_id == med.id).count() == 1


def test_manual_track_also_writes_log(client, auth_user_and_headers, db):
    from app.models.medication import MedicationLog
    user, h = auth_user_and_headers
    med = _make_med(db, user.id, name="阿莫西林", dosage="1000mg")
    pid = client.post(f"/api/v1/protocols/from-medication/{med.id}", headers=h).json()["id"]
    c = client.post(f"/api/v1/protocols/{pid}/complete", headers=h,
                    json={"track": "manual", "value": {"actual_dosage": "1粒"}})
    assert c.status_code == 200
    logs = db.query(MedicationLog).filter(MedicationLog.medication_id == med.id).all()
    assert len(logs) == 1 and logs[0].status == "taken"


def test_from_nonexistent_medication_400(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/protocols/from-medication/999999", headers=h)
    assert r.status_code == 400
