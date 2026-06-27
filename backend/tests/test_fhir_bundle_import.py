# -*- coding: utf-8 -*-
"""Minimal FHIR Bundle import into BiomarkerObservation with provenance."""

from app.models.biomarker_observation import BiomarkerObservation
from app.models.data_connection import DataConnection, ProvenanceRecord


def test_import_fhir_bundle_observations_to_biomarkers(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-ldl-1",
                    "status": "final",
                    "code": {
                        "coding": [{"system": "http://loinc.org", "code": "13457-7", "display": "LDL-C"}],
                        "text": "低密度脂蛋白胆固醇",
                    },
                    "effectiveDateTime": "2026-06-20T08:30:00+08:00",
                    "valueQuantity": {"value": 4.1, "unit": "mmol/L"},
                },
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "unknown-1",
                    "code": {"text": "未知指标"},
                    "effectiveDateTime": "2026-06-20T08:30:00+08:00",
                    "valueQuantity": {"value": 1, "unit": "x"},
                },
            },
        ],
    }

    resp = client.post(
        "/api/v1/data-connections/fhir-bundles/import",
        headers=headers,
        json={
            "provider": "hospital_fhir",
            "display_name": "Hospital FHIR Bundle",
            "source_ref": "bundle-2026-06",
            "bundle": bundle,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scanned"] == 2
    assert body["recognized"] == 1
    assert body["written"] == 1
    assert body["skipped"] == 1
    assert body["connection"]["provider"] == "hospital_fhir"
    assert body["connection"]["provider_type"] == "fhir_bundle"

    observation = db.query(BiomarkerObservation).filter_by(user_id=user.id, code="lipid_ldl").one()
    assert observation.normalized_value == 4.1
    assert observation.normalized_unit == "mmol/L"
    assert observation.source == "fhir_bundle"
    assert observation.abnormal is True

    provenance = db.query(ProvenanceRecord).filter_by(
        user_id=user.id,
        object_type="BiomarkerObservation",
        object_id=str(observation.id),
    ).one()
    assert provenance.connection_id == body["connection"]["id"]
    assert provenance.source_kind == "fhir_bundle"
    assert provenance.source_id == "Observation/obs-ldl-1"
    assert provenance.transformed_by == "fhir_bundle_observation_v1"
    assert provenance.confidence == observation.confidence
    assert provenance.privacy_classification == "L3"


def test_fhir_bundle_import_requires_auth(client):
    resp = client.post(
        "/api/v1/data-connections/fhir-bundles/import",
        json={"provider": "hospital_fhir", "display_name": "Hospital", "bundle": {"resourceType": "Bundle"}},
    )

    assert resp.status_code in (401, 403)
