# -*- coding: utf-8 -*-
"""DataConnection / ConsentGrant / ProvenanceRecord governance contracts."""

from datetime import datetime, timezone

from tests.conftest import create_authenticated_user


def test_create_connection_with_policy_and_list_status(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/data-connections/me",
        headers=headers,
        json={
            "provider": "garmin",
            "provider_type": "wearable",
            "display_name": "Garmin",
            "scopes": ["sleep", "activity", "hrv"],
            "token_status": "valid",
            "metadata": {"source_priority": 80},
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "garmin"
    assert body["provider_type"] == "wearable"
    assert body["connection_status"] == "active"
    assert body["token_status"] == "valid"
    assert body["scopes"] == ["sleep", "activity", "hrv"]
    assert body["policy"]["degraded_behavior"] == "read_only"
    assert body["policy"]["data_minimization"] == "scoped_fields_only"

    list_resp = client.get("/api/v1/data-connections/me", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["connections"][0]["provider"] == "garmin"


def test_connection_consent_grant_and_revoke(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    connection = client.post(
        "/api/v1/data-connections/me",
        headers=headers,
        json={
            "provider": "fhir_bundle",
            "provider_type": "fhir_bundle",
            "display_name": "FHIR Bundle import",
            "scopes": ["labs.read", "conditions.read"],
            "token_status": "not_required",
        },
    ).json()

    grant_resp = client.post(
        f"/api/v1/data-connections/{connection['id']}/consents",
        headers=headers,
        json={
            "grantee_type": "external_agent",
            "grantee_id": "openclaw",
            "scopes": ["labs.read"],
            "purpose": "reviewed health analysis",
        },
    )

    assert grant_resp.status_code == 200
    grant = grant_resp.json()
    assert grant["status"] == "active"
    assert grant["scopes"] == ["labs.read"]

    revoke_resp = client.post(f"/api/v1/data-connections/{connection['id']}/revoke", headers=headers)

    assert revoke_resp.status_code == 200
    revoked = revoke_resp.json()
    assert revoked["connection_status"] == "revoked"
    assert revoked["token_status"] == "revoked"
    assert revoked["active_consents"] == []


def test_data_connections_are_user_scoped(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other_user, _ = create_authenticated_user(db)

    from app.services.data_connections import upsert_data_connection

    upsert_data_connection(
        db,
        user_id=other_user.id,
        provider="oura",
        provider_type="wearable",
        display_name="Oura",
        scopes=["sleep"],
        token_status="valid",
    )

    resp = client.get("/api/v1/data-connections/me", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["connections"] == []


def test_provenance_record_serialization_and_degraded_behavior(db):
    from app.services.data_connections import (
        create_provenance_record,
        record_sync_result,
        serialize_provenance_record,
        upsert_data_connection,
    )

    user, _ = create_authenticated_user(db)
    connection = upsert_data_connection(
        db,
        user_id=user.id,
        provider="lab_pdf",
        provider_type="report",
        display_name="Lab PDF",
        scopes=["labs.read"],
        token_status="not_required",
    )

    record = create_provenance_record(
        db,
        user_id=user.id,
        connection_id=connection.id,
        source_kind="report",
        source_id="report-123",
        object_type="BiomarkerObservation",
        object_id="ldl-2026-06-27",
        observed_at=datetime(2026, 6, 26, 8, 30, tzinfo=timezone.utc),
        transformed_by="medical_report_ocr_v1",
        confidence="medium",
        privacy_classification="L3",
        user_correction={"status": "none"},
    )
    serialized = serialize_provenance_record(record)

    assert serialized["source_kind"] == "report"
    assert serialized["confidence"] == "medium"
    assert serialized["privacy_classification"] == "L3"
    assert serialized["observed_at"] == "2026-06-26T08:30:00+00:00"

    degraded = record_sync_result(
        db,
        user_id=user.id,
        connection_id=connection.id,
        success=False,
        error_message="token expired",
        is_auth_error=True,
    )

    assert degraded.connection_status == "degraded"
    assert degraded.token_status == "expired"
    assert degraded.sync_error == "token expired"
