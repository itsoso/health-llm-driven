"""Personal Health Trajectory Agent snapshot tests."""

from datetime import date


def test_trajectory_me_combines_baseline_anchors_realtime_and_actions(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    from app.models.blood_pressure import BloodPressureRecord
    from app.models.genetic_data import GeneticProfile, GeneticVariant
    from app.models.waist import WaistRecord
    from app.models.weight import WeightRecord

    profile = GeneticProfile(
        user_id=user.id,
        test_provider="test",
        test_date=date.today(),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.add_all([
        GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            category="disease_risk",
            gene_name="FTO",
            genotype="AA",
            result_label="肥胖倾向",
            risk_level="high",
            variant_nature="risk",
        ),
        GeneticVariant(
            user_id=user.id,
            profile_id=profile.id,
            category="recovery",
            gene_name="IL6",
            genotype="GG",
            result_label="炎症恢复敏感",
            risk_level="medium",
            variant_nature="risk",
        ),
    ])
    db.add(WeightRecord(user_id=user.id, record_date=date.today(), weight=82.0, bmi=27.2))
    db.add(WaistRecord(user_id=user.id, record_date=date.today(), waist_cm=92.0))
    db.add(BloodPressureRecord(
        user_id=user.id,
        record_date=date.today(),
        systolic=138,
        diastolic=88,
    ))
    db.commit()

    resp = client.get("/api/v1/trajectory/me", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["focus_domains"] == ["metabolic_health", "recovery_capacity", "aging_pace"]
    assert body["congenital_baseline"]["has_genetic_profile"] is True
    assert body["congenital_baseline"]["high_risk_count"] == 1
    assert body["epigenetic_feedback"]["status"] == "missing"
    assert any(gap["code"] == "methylation_report_missing" for gap in body["data_gaps"])
    assert body["clinical_anchors"]["waist_cm"] == 92.0
    assert body["clinical_anchors"]["blood_pressure"] == "138/88"
    assert "training_readiness_score" in body["realtime_state"]
    assert any(r["domain"] == "metabolic_health" and r["level"] == "attention" for r in body["trajectory_risks"])
    assert any(r["domain"] == "recovery_capacity" and r["level"] == "attention" for r in body["trajectory_risks"])
    assert all(r["evidence_tier"] for r in body["trajectory_risks"])
    assert all(r["confidence"] in {"high", "medium", "low"} for r in body["trajectory_risks"])
    assert all("不替代医生诊断" in r["claim_boundary"] for r in body["trajectory_risks"])
    assert all(r["state_variable"] for r in body["trajectory_risks"])
    assert all(r["horizon"] for r in body["trajectory_risks"])
    assert all(isinstance(r["modifiable_levers"], list) for r in body["trajectory_risks"])
    assert all(r["verification_window_days"] >= 0 for r in body["trajectory_risks"])
    assert all(r["verification_signal"] for r in body["trajectory_risks"])
    metabolic = next(r for r in body["trajectory_risks"] if r["domain"] == "metabolic_health")
    assert metabolic["evidence_tier"] == "clinical_guideline"
    assert metabolic["confidence"] == "high"
    assert metabolic["state_variable"] == "waist_cm"
    assert "movement" in metabolic["modifiable_levers"]
    assert body["epigenetic_feedback"]["evidence_tier"] == "experimental"
    assert "短期干预成效" in body["epigenetic_feedback"]["claim_boundary"]
    assert any(a["domain"] == "measurement" for a in body["next_actions"])


def test_trajectory_me_returns_missing_data_gaps_for_new_user(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.get("/api/v1/trajectory/me", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    gap_codes = {gap["code"] for gap in body["data_gaps"]}
    assert "genetic_profile_missing" in gap_codes
    assert "methylation_report_missing" in gap_codes
    assert "clinical_anchor_missing" in gap_codes
    assert body["trajectory_risks"][0]["level"] == "unknown"
    assert all(r["confidence"] == "low" for r in body["trajectory_risks"])
    assert all(r["claim_boundary"] for r in body["trajectory_risks"])


def test_trajectory_me_uses_latest_epigenetic_report_as_experimental_feedback(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    from app.models.epigenetic_report import EpigeneticReport

    user.birth_date = date(1990, 1, 1)
    db.add(user)
    db.add_all([
        EpigeneticReport(
            user_id=user.id,
            vendor="TruDiagnostic",
            sample_date=date(2026, 1, 5),
            clock_type="DunedinPACE",
            biological_age=38.4,
            pace_of_aging=1.01,
            confidence="medium",
            raw_summary={"note": "older report"},
        ),
        EpigeneticReport(
            user_id=user.id,
            vendor="TruDiagnostic",
            sample_date=date(2026, 5, 1),
            clock_type="DunedinPACE",
            biological_age=41.2,
            pace_of_aging=1.11,
            confidence="medium",
            raw_summary={"pace_percentile": 72},
        ),
    ])
    db.commit()

    resp = client.get("/api/v1/trajectory/me", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    epigenetic = body["epigenetic_feedback"]
    assert epigenetic["has_methylation_report"] is True
    assert epigenetic["status"] == "present"
    assert epigenetic["latest_test_date"] == "2026-05-01"
    assert epigenetic["vendor"] == "TruDiagnostic"
    assert epigenetic["clock_type"] == "DunedinPACE"
    assert epigenetic["biological_age"] == 41.2
    assert epigenetic["pace_of_aging"] == 1.11
    assert epigenetic["biological_age_delta_years"] == 4.9
    assert epigenetic["evidence_tier"] == "experimental"
    assert epigenetic["confidence"] == "low"
    assert "短期干预成效" in epigenetic["claim_boundary"]

    gap_codes = {gap["code"] for gap in body["data_gaps"]}
    assert "methylation_report_missing" not in gap_codes
    aging_risk = next(risk for risk in body["trajectory_risks"] if risk["domain"] == "aging_pace")
    assert aging_risk["level"] == "attention"
    assert "epigenetic_pace_elevated" in aging_risk["signals"]
    assert aging_risk["confidence"] == "low"
