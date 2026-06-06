# -*- coding: utf-8 -*-
"""DNAm 时钟报告摄入(抗衰 Phase2 W3)回归。

钉:service 写入→latest_epigenetic_state 读出(experimental + claim_boundary);
API 上传/列表带认证;evidence_tier 不被夸大成 validated。
"""
from datetime import date


def test_service_roundtrip_create_then_latest(db):
    from app.services.epigenetic_report_service import (
        create_epigenetic_report,
        latest_epigenetic_state,
    )

    create_epigenetic_report(
        db, user_id=1,
        vendor="TruDiagnostic", clock_type="DunedinPACE",
        sample_date=date(2026, 3, 1), biological_age=44.0, pace_of_aging=0.92,
    )
    state = latest_epigenetic_state(db, 1)
    assert state.has_methylation_report is True
    assert state.biological_age == 44.0
    assert state.pace_of_aging == 0.92
    assert state.evidence_tier == "experimental"   # 不夸大
    assert state.claim_boundary                      # 边界非空


def test_latest_state_empty_when_none(db):
    from app.services.epigenetic_report_service import latest_epigenetic_state
    state = latest_epigenetic_state(db, 999)
    assert state.has_methylation_report is False


def test_api_upload_and_list(client, auth_user_and_headers):
    user, headers = auth_user_and_headers
    body = {
        "vendor": "TruDiagnostic", "clock_type": "GrimAge",
        "sample_date": "2026-05-01", "biological_age": 46.5, "pace_of_aging": 1.02,
    }
    r = client.post("/api/v1/epigenetic-reports/me", json=body, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["vendor"] == "TruDiagnostic"
    assert data["biological_age"] == 46.5
    assert data["evidence_tier"] == "experimental"
    assert data["claim_boundary"]

    r2 = client.get("/api/v1/epigenetic-reports/me", headers=headers)
    assert r2.status_code == 200
    reports = r2.json()["reports"]
    assert len(reports) == 1 and reports[0]["clock_type"] == "GrimAge"


def test_api_requires_auth(client):
    r = client.post("/api/v1/epigenetic-reports/me", json={
        "vendor": "X", "clock_type": "Y", "sample_date": "2026-01-01",
    })
    assert r.status_code in (401, 403)
