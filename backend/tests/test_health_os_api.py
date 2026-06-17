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
    # LDL 4.5(高,留出超 RCV 又不达标的空间), UA 460(高)
    _ingest(db, user.id, [("低密度脂蛋白", 4.5, "mmol/L"), ("尿酸", 460, "µmol/L")], datetime.date(2026, 3, 1))

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

    # 复查 (改善后): LDL 4.5→3.3 = -26.7% 超 RCV~23% 且仍 >目标3.0 → improving;UA 370 ≤380 → met
    _ingest(db, user.id, [("低密度脂蛋白", 3.3, "mmol/L"), ("尿酸", 370, "µmol/L")], datetime.date(2026, 6, 1))
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


def _seed_indicator(db, user_id, name, value, d, unit="mmol/L"):
    """直接写 medical_indicators(模拟 OCR/手录已入库但尚未归一到 biomarker)。"""
    from sqlalchemy import text
    db.execute(text(
        "INSERT INTO medical_indicators (user_id, name, value, unit, record_date) "
        "VALUES (:u, :n, :v, :unit, :d)"
    ), {"u": user_id, "n": name, "v": value, "unit": unit, "d": d})
    db.commit()


def test_recheck_syncs_ocr_indicators_before_recompute(client, db, auth_user_and_headers):
    """复查前必须把 medical_indicators(OCR 路径)归一进 biomarker,否则复查只看旧值。

    回归(Phase 0「第一刀」): record_recheck 只读 biomarker_observations。用户传完新化验
    (只进 medical_indicators)点复查,若端点不先 sync,latest_value 仍是基线 → 显示「没变化」
    (假装成功型坑)。
    """
    from app.models.biomarker_observation import BiomarkerObservation
    from app.services.biomarker_sync import sync_indicators_to_biomarkers

    user, headers = auth_user_and_headers
    # 基线: 甘油三酯 2.5(走 sync 路径,proven 映射 → lipid_tg),起周期前归一
    _seed_indicator(db, user.id, "甘油三酯", 2.5, datetime.date(2026, 3, 1))
    sync_indicators_to_biomarkers(db, user.id)

    r = client.post("/api/v1/intervention-cycles", headers=headers, json={"days": 90})
    assert r.status_code == 200, r.text
    cid = r.json()["cycle"]["id"]
    assert "lipid_tg" in {o["metric_code"] for o in r.json()["cycle"]["outcomes"]}

    # 中途上传新化验 甘油三酯 1.6 —— 只进 medical_indicators,尚未归一到 biomarker
    _seed_indicator(db, user.id, "甘油三酯", 1.6, datetime.date(2026, 6, 1))
    before = db.query(BiomarkerObservation).filter_by(user_id=user.id, code="lipid_tg").count()
    assert before == 1  # 只有基线那条,新化验还没同步

    rr = client.post(f"/api/v1/intervention-cycles/{cid}/recheck", headers=headers)
    assert rr.status_code == 200, rr.text

    # 新化验已被复查端点同步进 biomarker(否则用户永远看旧值)
    after = db.query(BiomarkerObservation).filter_by(user_id=user.id, code="lipid_tg").count()
    assert after == 2, "复查未把 OCR 化验同步进 biomarker"

    # 且复查裁决用的是新值 1.6(若没 sync,latest_value 会停在基线 2.5)
    outs = {o["metric_code"]: o for o in rr.json()["cycle"]["outcomes"]}
    assert outs["lipid_tg"]["baseline_value"] == 2.5
    assert outs["lipid_tg"]["latest_value"] == 1.6
