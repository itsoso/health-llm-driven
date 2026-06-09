"""Personal Health OS API 测试 — biomarkers + 干预周期 (P2)."""
import datetime


def _ingest(db, user_id, items, exam_date):
    from app.models.medical_exam import MedicalExam, MedicalExamItem
    from app.services.biomarker_service import ingest_exam
    exam = MedicalExam(user_id=user_id, exam_date=exam_date, exam_type="comprehensive",
                       patient_gender="男", patient_age=41)
    db.add(exam); db.commit(); db.refresh(exam)
    for n, v, u in items:
        db.add(MedicalExamItem(exam_id=exam.id, item_name=n, value=v, unit=u, source="manual"))
    db.commit(); db.refresh(exam)
    ingest_exam(db, exam)
    return exam


def test_biomarkers_me_and_profile(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _ingest(db, user.id, [("低密度脂蛋白", 3.8, "mmol/L"), ("谷丙转氨酶", 26, "U/L")], datetime.date(2026, 5, 1))

    r = client.get("/api/v1/biomarkers/me", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    codes = {o["code"] for o in data["observations"]}
    assert "lipid_ldl" in codes and "ALT" in codes
    assert data["abnormal_count"] == 1
    assert data["observations"][0]["code"] == "lipid_ldl"  # is_risk 排前
    assert data["observations"][0]["display"] == "低密度脂蛋白胆固醇"

    rp = client.get("/api/v1/biomarkers/me/profile", headers=headers)
    assert rp.status_code == 200, rp.text
    prof = rp.json()
    assert "risk" in prof and "biomarkers" in prof
    assert prof["abnormal_count"] == 1

    rs = client.get("/api/v1/biomarkers/me/lipid_ldl/series", headers=headers)
    assert rs.status_code == 200
    assert len(rs.json()["points"]) == 1


def test_intervention_cycle_api_flow(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _ingest(db, user.id, [("低密度脂蛋白", 3.8, "mmol/L"), ("尿酸", 460, "µmol/L")], datetime.date(2026, 3, 1))

    r = client.post("/api/v1/intervention-cycles", headers=headers, json={"days": 90})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    cycle = body["cycle"]
    cid = cycle["id"]
    codes = {o["metric_code"] for o in cycle["outcomes"]}
    assert "lipid_ldl" in codes and "UA" in codes
    assert cycle["stop_conditions"]

    # 幂等: 已有进行中 → 返回同一周期, created False
    r2 = client.post("/api/v1/intervention-cycles", headers=headers, json={"days": 90})
    assert r2.json()["created"] is False
    assert r2.json()["cycle"]["id"] == cid

    ra = client.get("/api/v1/intervention-cycles/active", headers=headers)
    assert ra.json()["cycle"]["id"] == cid

    # 复查 (改善后)
    _ingest(db, user.id, [("低密度脂蛋白", 3.1, "mmol/L"), ("尿酸", 370, "µmol/L")], datetime.date(2026, 6, 1))
    rr = client.post(f"/api/v1/intervention-cycles/{cid}/recheck", headers=headers)
    assert rr.status_code == 200, rr.text
    outs = {o["metric_code"]: o for o in rr.json()["cycle"]["outcomes"]}
    assert outs["lipid_ldl"]["status"] == "improving"
    assert outs["UA"]["status"] == "met"
    assert rr.json()["cycle"]["latest_snapshot_id"] is not None


def test_get_cycle_404_for_other_user(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    r = client.get("/api/v1/intervention-cycles/99999", headers=headers)
    assert r.status_code == 404
