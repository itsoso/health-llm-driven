"""Minimal FHIR Bundle ingestion into governed biomarker observations."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.biomarkers.normalize import normalize_observation
from app.models.biomarker_observation import BiomarkerObservation
from app.models.user import User
from app.services.data_connections import (
    create_provenance_record,
    serialize_data_connection,
    upsert_data_connection,
)


def import_fhir_bundle_observations(
    db: Session,
    *,
    user: User,
    provider: str,
    display_name: str,
    bundle: dict[str, Any],
    source_ref: str | None = None,
) -> dict[str, Any]:
    if bundle.get("resourceType") != "Bundle":
        raise ValueError("FHIR import requires resourceType=Bundle")

    connection = upsert_data_connection(
        db,
        user_id=user.id,
        provider=provider,
        provider_type="fhir_bundle",
        display_name=display_name,
        scopes=["labs.read", "conditions.read"],
        token_status="not_required",
        source_ref=source_ref,
        metadata={"resource_type": "Bundle", "importer": "fhir_bundle_observation_v1"},
    )

    scanned = 0
    recognized = 0
    skipped = 0
    written: list[BiomarkerObservation] = []
    for entry in bundle.get("entry") or []:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        if resource.get("resourceType") != "Observation":
            continue
        scanned += 1
        observation = _observation_from_fhir(db, user=user, connection_id=connection.id, resource=resource)
        if observation is None:
            skipped += 1
            continue
        recognized += 1
        written.append(observation)

    return {
        "scanned": scanned,
        "recognized": recognized,
        "written": len(written),
        "skipped": skipped,
        "connection": serialize_data_connection(db, connection),
        "observations": [_serialize_observation(observation) for observation in written],
        "boundary": "FHIR Bundle 导入只做结构化归一和来源追踪,不生成诊断或治疗建议。",
    }


def _observation_from_fhir(
    db: Session,
    *,
    user: User,
    connection_id: int,
    resource: dict[str, Any],
) -> BiomarkerObservation | None:
    code = resource.get("code") if isinstance(resource.get("code"), dict) else {}
    name = code.get("text") or _first_coding_value(code, "display") or _first_coding_value(code, "code")
    value_quantity = resource.get("valueQuantity") if isinstance(resource.get("valueQuantity"), dict) else {}
    value = value_quantity.get("value")
    unit = value_quantity.get("unit") or value_quantity.get("code")
    observed_at = _parse_datetime(resource.get("effectiveDateTime") or resource.get("issued"))
    norm = normalize_observation(name, value, unit, sex=_norm_sex(user.gender), age=_age(user.birth_date))
    if norm is None or observed_at is None:
        return None

    existing = (
        db.query(BiomarkerObservation)
        .filter(
            BiomarkerObservation.user_id == user.id,
            BiomarkerObservation.code == norm.code,
            BiomarkerObservation.observed_at == observed_at,
            BiomarkerObservation.source == "fhir_bundle",
        )
        .first()
    )
    target = existing or BiomarkerObservation(user_id=user.id)
    target.code = norm.code
    target.domain = norm.domain
    target.value = norm.value
    target.unit = norm.unit
    target.normalized_value = norm.normalized_value
    target.normalized_unit = norm.normalized_unit
    target.ref_low = norm.ref_low
    target.ref_high = norm.ref_high
    target.flag = norm.flag
    target.abnormal = norm.abnormal
    target.is_risk = norm.is_risk
    target.confidence = norm.confidence
    target.observed_at = observed_at
    target.source = "fhir_bundle"
    if existing is None:
        db.add(target)
    db.flush()

    create_provenance_record(
        db,
        user_id=user.id,
        connection_id=connection_id,
        source_kind="fhir_bundle",
        source_id=f"Observation/{resource.get('id') or target.code}",
        object_type="BiomarkerObservation",
        object_id=str(target.id),
        observed_at=observed_at,
        transformed_by="fhir_bundle_observation_v1",
        confidence=target.confidence or "unknown",
        privacy_classification="L3",
        metadata={
            "resource_status": resource.get("status"),
            "code": code,
        },
    )
    db.refresh(target)
    return target


def _first_coding_value(code: dict[str, Any], key: str) -> str | None:
    coding = code.get("coding")
    if not isinstance(coding, list):
        return None
    for item in coding:
        if isinstance(item, dict) and item.get(key):
            return str(item[key])
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _norm_sex(gender: str | None) -> str | None:
    if not gender:
        return None
    normalized = gender.strip().lower()
    if normalized in {"male", "m", "男"}:
        return "male"
    if normalized in {"female", "f", "女"}:
        return "female"
    return None


def _age(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _serialize_observation(observation: BiomarkerObservation) -> dict[str, Any]:
    return {
        "id": observation.id,
        "code": observation.code,
        "domain": observation.domain,
        "value": observation.value,
        "unit": observation.unit,
        "normalized_value": observation.normalized_value,
        "normalized_unit": observation.normalized_unit,
        "flag": observation.flag,
        "abnormal": observation.abnormal,
        "is_risk": observation.is_risk,
        "confidence": observation.confidence,
        "observed_at": observation.observed_at.isoformat() if observation.observed_at else None,
        "source": observation.source,
    }
