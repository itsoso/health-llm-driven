"""Desktop client aggregate APIs.

The Swift-native Mac app should launch with one compact request instead of
replaying every mobile screen request one by one.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.action_card import ActionCard
from app.models.blood_pressure import BloodPressureRecord
from app.models.daily_health import DietRecord, GarminData, SupplementIntake, WaterIntake
from app.models.desktop_job import DesktopJob
from app.models.genetic_data import GeneticImportJob, GeneticProfile, GeneticVariant
from app.models.memory_fact import MemoryFact
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.system_knowledge import KBDocument, KBEdge
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.weight import WeightRecord
from app.services.daily_operating_plan import build_daily_operating_plan
from app.services.genetic_risk import clinical_status
from app.services.health_trajectory import build_health_trajectory_snapshot

router = APIRouter(prefix="/desktop", tags=["desktop"])
DEFAULT_DOWN_DEDAO_ROOT = "~/work/personal/down-dedao"
SYSTEM_KB_SEED_MANIFEST = Path(__file__).resolve().parents[2] / "data" / "system_kb_v2_seed" / "manifest.json"

DesktopJobType = Literal[
    "gene_reanalysis",
    "medical_import",
    "system_kb_rebuild",
    "dedao_compile",
    "eval_run",
]


class DesktopJobCreate(BaseModel):
    job_type: DesktopJobType
    source_kind: str | None = Field(None, max_length=50)
    source_name: str | None = Field(None, max_length=500)
    source_hash: str | None = Field(None, max_length=128)
    request_payload: dict[str, Any] = Field(default_factory=dict)


def _action_card_to_dict(card: ActionCard) -> dict[str, Any]:
    return {
        "id": card.id,
        "title": card.title,
        "content": card.content,
        "card_type": card.card_type,
        "source_type": card.source_type,
        "source_id": card.source_id,
        "status": card.status,
        "priority": card.priority,
        "metric_key": card.metric_key,
        "evidence_refs": card.evidence_refs or [],
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "updated_at": card.updated_at.isoformat() if card.updated_at else None,
    }


def _memory_fact_to_dict(fact: MemoryFact) -> dict[str, Any]:
    from app.services.memory_service import (
        effective_memory_confidence,
        effective_memory_predicate,
    )

    return {
        "id": fact.id,
        "tier": fact.tier,
        "subject": fact.subject,
        "predicate": effective_memory_predicate(
            fact.predicate, subject=fact.subject, object_value=fact.object_value, tags=fact.tags or [],
        ),
        "object_value": fact.object_value,
        "object_unit": fact.object_unit,
        "confidence": effective_memory_confidence(
            fact.confidence, predicate=fact.predicate, subject=fact.subject,
            object_value=fact.object_value, tags=fact.tags or [],
        ),
        "effective_confidence": round(effective_memory_confidence(
            fact.effective_confidence, predicate=fact.predicate, subject=fact.subject,
            object_value=fact.object_value, tags=fact.tags or [],
        ), 3),
        "tags": fact.tags or [],
        "is_sensitive": fact.is_sensitive,
        "created_at": fact.created_at.isoformat() if fact.created_at else None,
    }


def _recent_records_summary(db: Session, user_id: int) -> dict[str, Any]:
    today = date.today()
    since_30 = today - timedelta(days=30)
    since_7 = today - timedelta(days=6)
    diet_records = (
        db.query(DietRecord)
        .filter(DietRecord.user_id == user_id, DietRecord.record_date == today)
        .all()
    )
    diet_30d = (
        db.query(DietRecord)
        .filter(
            DietRecord.user_id == user_id,
            DietRecord.record_date >= since_30,
            DietRecord.record_date <= today,
        )
        .all()
    )
    water_records = (
        db.query(WaterIntake)
        .filter(WaterIntake.user_id == user_id, WaterIntake.record_date == today)
        .all()
    )
    water_30d = (
        db.query(WaterIntake)
        .filter(
            WaterIntake.user_id == user_id,
            WaterIntake.record_date >= since_30,
            WaterIntake.record_date <= today,
        )
        .all()
    )
    latest_weight = (
        db.query(WeightRecord)
        .filter(WeightRecord.user_id == user_id)
        .order_by(desc(WeightRecord.record_date), desc(WeightRecord.id))
        .first()
    )
    latest_bp = (
        db.query(BloodPressureRecord)
        .filter(BloodPressureRecord.user_id == user_id)
        .order_by(desc(BloodPressureRecord.record_date), desc(BloodPressureRecord.id))
        .first()
    )
    latest_garmin = (
        db.query(GarminData)
        .filter(GarminData.user_id == user_id)
        .order_by(desc(GarminData.record_date), desc(GarminData.id))
        .first()
    )

    diet_summary = _diet_summary(diet_records, diet_30d, today=today)
    water_summary = _water_summary(water_records, water_30d, today=today)
    supplement_summary = _supplement_summary(db, user_id, today=today)

    return {
        "date": today.isoformat(),
        "range_days": 7,
        "available_ranges": [7, 30],
        "diet": diet_summary,
        "water": water_summary,
        "supplements": supplement_summary,
        "latest_weight": _latest_weight_to_dict(latest_weight),
        "latest_blood_pressure": _latest_blood_pressure_to_dict(latest_bp),
        "latest_garmin": _latest_garmin_to_dict(latest_garmin),
        "recent_records": _recent_records_list(diet_30d, water_30d, latest_weight, latest_bp),
    }


def _date_window(today: date, days: int) -> list[date]:
    start = today - timedelta(days=days - 1)
    return [start + timedelta(days=offset) for offset in range(days)]


def _sum_calories(records: list[DietRecord]) -> float:
    return round(sum(record.calories or 0 for record in records), 1)


def _diet_daily(records: list[DietRecord], *, today: date, days: int) -> list[dict[str, Any]]:
    by_date: dict[date, list[DietRecord]] = {day: [] for day in _date_window(today, days)}
    for record in records:
        if record.record_date in by_date:
            by_date[record.record_date].append(record)
    return [
        {
            "date": day.isoformat(),
            "count": len(rows),
            "calories": _sum_calories(rows),
        }
        for day, rows in by_date.items()
    ]


def _diet_summary(today_records: list[DietRecord], records_30d: list[DietRecord], *, today: date) -> dict[str, Any]:
    since_7 = today - timedelta(days=6)
    records_7d = [record for record in records_30d if record.record_date and record.record_date >= since_7]
    last_7_calories = _sum_calories(records_7d)
    last_30_calories = _sum_calories(records_30d)
    return {
        "today_count": len(today_records),
        "today_calories": _sum_calories(today_records),
        "last_7_count": len(records_7d),
        "last_7_calories": last_7_calories,
        "last_7_avg_calories": round(last_7_calories / 7, 1),
        "last_30_count": len(records_30d),
        "last_30_calories": last_30_calories,
        "last_30_avg_calories": round(last_30_calories / 30, 1),
        "daily_7": _diet_daily(records_7d, today=today, days=7),
        "daily_30": _diet_daily(records_30d, today=today, days=30),
    }


def _water_daily(records: list[WaterIntake], *, today: date, days: int) -> list[dict[str, Any]]:
    by_date: dict[date, list[WaterIntake]] = {day: [] for day in _date_window(today, days)}
    for record in records:
        if record.record_date in by_date:
            by_date[record.record_date].append(record)
    return [
        {
            "date": day.isoformat(),
            "count": len(rows),
            "total_ml": sum(record.amount_ml or 0 for record in rows),
        }
        for day, rows in by_date.items()
    ]


def _water_summary(today_records: list[WaterIntake], records_30d: list[WaterIntake], *, today: date) -> dict[str, Any]:
    since_7 = today - timedelta(days=6)
    records_7d = [record for record in records_30d if record.record_date and record.record_date >= since_7]
    today_total_ml = sum(record.amount_ml or 0 for record in today_records)
    last_7_total_ml = sum(record.amount_ml or 0 for record in records_7d)
    last_30_total_ml = sum(record.amount_ml or 0 for record in records_30d)
    return {
        "today_count": len(today_records),
        "today_total_ml": today_total_ml,
        "last_7_count": len(records_7d),
        "last_7_total_ml": last_7_total_ml,
        "last_7_avg_ml": round(last_7_total_ml / 7, 1),
        "last_30_count": len(records_30d),
        "last_30_total_ml": last_30_total_ml,
        "last_30_avg_ml": round(last_30_total_ml / 30, 1),
        "daily_7": _water_daily(records_7d, today=today, days=7),
        "daily_30": _water_daily(records_30d, today=today, days=30),
    }


def _supplement_summary(db: Session, user_id: int, *, today: date) -> dict[str, Any]:
    since_30 = today - timedelta(days=30)
    since_7 = today - timedelta(days=6)
    active_defs = (
        db.query(SupplementDefinition)
        .filter(
            SupplementDefinition.user_id == user_id,
            SupplementDefinition.is_active == True,  # noqa: E712
        )
        .all()
    )
    definition_names = {definition.id: definition.name for definition in active_defs}
    records_30d = (
        db.query(SupplementRecord)
        .filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.record_date >= since_30,
            SupplementRecord.record_date <= today,
            SupplementRecord.taken == True,  # noqa: E712
        )
        .all()
    )
    intake_30d = (
        db.query(SupplementIntake)
        .filter(
            SupplementIntake.user_id == user_id,
            SupplementIntake.record_date >= since_30,
            SupplementIntake.record_date <= today,
        )
        .all()
    )
    records_7d = [record for record in records_30d if record.record_date and record.record_date >= since_7]
    intake_7d = [record for record in intake_30d if record.record_date and record.record_date >= since_7]
    active_count = len(active_defs)

    def daily(days: int, supplement_records: list[SupplementRecord], intake_records: list[SupplementIntake]) -> list[dict[str, Any]]:
        by_date = {day: 0 for day in _date_window(today, days)}
        for record in supplement_records:
            if record.record_date in by_date:
                by_date[record.record_date] += 1
        for record in intake_records:
            if record.record_date in by_date:
                by_date[record.record_date] += 1
        return [{"date": day.isoformat(), "count": count} for day, count in by_date.items()]

    name_counter: Counter[str] = Counter()
    for record in records_30d:
        name_counter[definition_names.get(record.supplement_id, "补剂")] += 1
    for record in intake_30d:
        name_counter[record.supplement_name or "补剂"] += 1

    count_7 = len(records_7d) + len(intake_7d)
    count_30 = len(records_30d) + len(intake_30d)
    adherence_7_pct = (
        round((len(records_7d) / (active_count * 7)) * 100, 1)
        if active_count
        else None
    )
    adherence_30_pct = (
        round((len(records_30d) / (active_count * 30)) * 100, 1)
        if active_count
        else None
    )
    return {
        "active_count": active_count,
        "today_count": sum(item["count"] for item in daily(1, records_7d, intake_7d)),
        "last_7_count": count_7,
        "last_7_avg_per_day": round(count_7 / 7, 1),
        "last_30_count": count_30,
        "last_30_avg_per_day": round(count_30 / 30, 1),
        "adherence_7_pct": adherence_7_pct,
        "adherence_30_pct": adherence_30_pct,
        "daily_7": daily(7, records_7d, intake_7d),
        "daily_30": daily(30, records_30d, intake_30d),
        "top_items": [
            {"name": name, "count": count}
            for name, count in name_counter.most_common(5)
        ],
    }


def _record_date_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _latest_weight_to_dict(record: WeightRecord | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {
        "id": record.id,
        "type": "weight",
        "title": "体重",
        "value": round(record.weight, 1),
        "unit": "kg",
        "record_date": _record_date_iso(record.record_date),
    }


def _latest_blood_pressure_to_dict(record: BloodPressureRecord | None) -> dict[str, Any] | None:
    if not record:
        return None
    value = f"{record.systolic}/{record.diastolic}"
    return {
        "id": record.id,
        "type": "blood_pressure",
        "title": "血压",
        "value": value,
        "unit": "mmHg",
        "category": record.category,
        "record_date": _record_date_iso(record.record_date),
    }


def _latest_garmin_to_dict(record: GarminData | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {
        "id": record.id,
        "type": "garmin",
        "title": "Garmin",
        "record_date": _record_date_iso(record.record_date),
        "steps": record.steps,
        "sleep_score": record.sleep_score,
        "spo2_avg": record.spo2_avg,
        "resting_heart_rate": record.resting_heart_rate,
        "hrv": record.hrv,
        "training_readiness_score": record.training_readiness_score,
    }


def _recent_records_list(
    diet_records: list[DietRecord],
    water_records: list[WaterIntake],
    latest_weight: WeightRecord | None,
    latest_bp: BloodPressureRecord | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(
        {
            "id": record.id,
            "type": "diet",
            "title": record.food_items or record.food_name or "饮食记录",
            "value": f"{round(record.calories or 0)} kcal" if record.calories is not None else None,
            "record_date": _record_date_iso(record.record_date),
        }
        for record in diet_records
    )
    rows.extend(
        {
            "id": record.id,
            "type": "water",
            "title": "饮水",
            "value": f"{record.amount_ml or 0} ml",
            "record_date": _record_date_iso(record.record_date),
        }
        for record in water_records
    )
    if latest_weight:
        rows.append(_latest_weight_to_dict(latest_weight))
    if latest_bp:
        rows.append(_latest_blood_pressure_to_dict(latest_bp))

    rows = [row for row in rows if row]
    rows.sort(key=lambda row: (row.get("record_date") or "", row.get("id") or 0), reverse=True)
    return rows[:8]


def _empty_genomic_summary() -> dict[str, Any]:
    return {
        "profile_id": None,
        "provider": None,
        "test_date": None,
        "report_id": None,
        "profile_count": 0,
        "total_variant_count": 0,
        "record_count": 0,
        "high_risk_count": 0,
        "medium_risk_count": 0,
        "low_risk_count": 0,
        "info_count": 0,
        "actionable_count": 0,
        "category_count": 0,
        "profile_summaries": [],
        "top_categories": [],
        "top_findings": [],
        "latest_import": None,
    }


def _variant_to_finding(variant: GeneticVariant) -> dict[str, Any]:
    return {
        "id": variant.id,
        "rsid": variant.rsid,
        "category": variant.category,
        "gene_name": variant.gene_name,
        "variant_name": variant.variant_name,
        "genotype": variant.genotype,
        "result_label": variant.result_label,
        "risk_level": variant.risk_level,
        "evidence_level": variant.evidence_level,
        "clinical_status": clinical_status(
            variant.category,
            variant.evidence_level,
            variant.health_implications,
        ),
        "description": variant.description,
        "variant_nature": variant.variant_nature,
    }


def _coverage_pct(
    matched_count: int | None,
    raw_record_count: int | None,
    known_total: int | None = None,
) -> float | None:
    denominator = known_total or raw_record_count
    if not denominator:
        return None
    return round(((matched_count or 0) / denominator) * 100, 1)


def _import_to_summary(import_job: GeneticImportJob | None) -> dict[str, Any] | None:
    if not import_job:
        return None
    return {
        "status": import_job.status,
        "source_type": import_job.source_type,
        "raw_record_count": import_job.raw_record_count,
        "known_total": import_job.known_total,
        "matched_count": import_job.matched_count,
        "duplicate_count": import_job.duplicate_count,
        "unknown_count": import_job.unknown_count,
        "unmapped_count": import_job.unmapped_count,
        "missing_count": import_job.missing_count,
        "coverage_pct": _coverage_pct(
            import_job.matched_count,
            import_job.raw_record_count,
            import_job.known_total,
        ),
        "coverage_summary": import_job.coverage_summary or {},
        "finished_at": import_job.finished_at.isoformat() if import_job.finished_at else None,
        "raw_file_hash": import_job.raw_file_hash,
    }


def _genomic_summary(db: Session, user_id: int) -> dict[str, Any]:
    from app.services.genetic_report import _resolve_active_profile

    profile = _resolve_active_profile(db, user_id)
    if not profile:
        return _empty_genomic_summary()

    profiles = (
        db.query(GeneticProfile)
        .filter(GeneticProfile.user_id == user_id)
        .order_by(desc(GeneticProfile.test_date), desc(GeneticProfile.created_at), desc(GeneticProfile.id))
        .all()
    )
    variant_count_rows = (
        db.query(GeneticVariant.profile_id, func.count(GeneticVariant.id))
        .filter(GeneticVariant.user_id == user_id)
        .group_by(GeneticVariant.profile_id)
        .all()
    )
    variant_counts = {profile_id: int(count) for profile_id, count in variant_count_rows}
    latest_import_rows = (
        db.query(GeneticImportJob)
        .filter(GeneticImportJob.user_id == user_id)
        .order_by(desc(GeneticImportJob.finished_at), desc(GeneticImportJob.created_at), desc(GeneticImportJob.id))
        .all()
    )
    latest_imports_by_profile: dict[int, GeneticImportJob] = {}
    for import_job in latest_import_rows:
        latest_imports_by_profile.setdefault(import_job.profile_id, import_job)
    profile_summaries = [
        {
            "profile_id": item.id,
            "provider": item.test_provider,
            "test_date": item.test_date.isoformat() if item.test_date else None,
            "report_id": item.report_id,
            "record_count": variant_counts.get(item.id, 0),
            "is_active": item.id == profile.id,
            "latest_import": _import_to_summary(latest_imports_by_profile.get(item.id)),
        }
        for item in profiles
    ]

    variants = (
        db.query(GeneticVariant)
        .filter(GeneticVariant.user_id == user_id, GeneticVariant.profile_id == profile.id)
        .all()
    )
    risk_counts = Counter((variant.risk_level or "info").lower() for variant in variants)
    category_counts: dict[str, dict[str, Any]] = {}
    for variant in variants:
        category = variant.category or "uncategorized"
        bucket = category_counts.setdefault(
            category,
            {"category": category, "count": 0, "high_risk_count": 0, "medium_risk_count": 0},
        )
        bucket["count"] += 1
        risk_level = (variant.risk_level or "info").lower()
        if risk_level == "high":
            bucket["high_risk_count"] += 1
        elif risk_level == "medium":
            bucket["medium_risk_count"] += 1

    risk_rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    top_findings = sorted(
        variants,
        key=lambda variant: (
            risk_rank.get((variant.risk_level or "info").lower(), 9),
            variant.category or "",
            variant.gene_name or "",
            variant.rsid or "",
        ),
    )[:12]
    latest_import = (
        db.query(GeneticImportJob)
        .filter(GeneticImportJob.user_id == user_id, GeneticImportJob.profile_id == profile.id)
        .order_by(desc(GeneticImportJob.finished_at), desc(GeneticImportJob.created_at), desc(GeneticImportJob.id))
        .first()
    )

    return {
        "profile_id": profile.id,
        "provider": profile.test_provider,
        "test_date": profile.test_date.isoformat() if profile.test_date else None,
        "report_id": profile.report_id,
        "profile_count": len(profiles),
        "total_variant_count": sum(variant_counts.values()),
        "record_count": len(variants),
        "high_risk_count": risk_counts.get("high", 0),
        "medium_risk_count": risk_counts.get("medium", 0),
        "low_risk_count": risk_counts.get("low", 0),
        "info_count": risk_counts.get("info", 0),
        "actionable_count": risk_counts.get("high", 0) + risk_counts.get("medium", 0),
        "category_count": len(category_counts),
        "top_categories": sorted(
            category_counts.values(),
            key=lambda item: (-int(item["count"]), str(item["category"])),
        )[:8],
        "profile_summaries": profile_summaries[:8],
        "top_findings": [_variant_to_finding(variant) for variant in top_findings],
        "latest_import": _import_to_summary(latest_import),
    }


def _knowledge_summary(db: Session) -> dict[str, Any]:
    docs = (
        db.query(KBDocument)
        .filter(KBDocument.is_archived == False)  # noqa: E712
        .order_by(asc(KBDocument.doc_id))
        .all()
    )
    doc_type_counts = Counter(doc.doc_type or "unknown" for doc in docs)
    source_counts: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    entity_type_counts: Counter[str] = Counter()
    origin_counts: Counter[str] = Counter()
    for doc in docs:
        for source in doc.sources or []:
            source_counts[str(source)] += 1
        if doc.doc_type == "claim" and doc.evidence_level:
            evidence_counts[str(doc.evidence_level)] += 1
        if doc.entity_type:
            entity_type_counts[str(doc.entity_type)] += 1
        origin = (doc.metadata_json or {}).get("origin")
        if origin:
            origin_counts[str(origin)] += 1

    recent_documents = [
        {
            "doc_id": doc.doc_id,
            "doc_type": doc.doc_type,
            "title": doc.title,
            "summary": doc.summary,
            "evidence_level": doc.evidence_level,
            "confidence": doc.confidence,
            "sources": doc.sources or [],
        }
        for doc in docs[:8]
    ]

    return {
        "document_count": len(docs),
        "claim_count": doc_type_counts.get("claim", 0),
        "entity_count": doc_type_counts.get("entity", 0),
        "article_count": doc_type_counts.get("article", 0),
        "edge_count": db.query(func.count(KBEdge.edge_id)).scalar() or 0,
        "source_total_count": len(source_counts),
        "doc_type_counts": [
            {"level": doc_type, "count": count}
            for doc_type, count in sorted(doc_type_counts.items())
        ],
        "entity_type_counts": [
            {"level": entity_type, "count": count}
            for entity_type, count in entity_type_counts.most_common(8)
        ],
        "evidence_level_counts": [
            {"level": level, "count": count}
            for level, count in sorted(evidence_counts.items())
        ],
        "source_counts": [
            {"source": source, "count": count}
            for source, count in source_counts.most_common(8)
        ],
        "local_source_summary": _knowledge_local_source_summary(origin_counts),
        "recent_documents": recent_documents,
    }


def _knowledge_local_source_summary(origin_counts: Counter[str]) -> dict[str, Any]:
    source_root = Path(os.getenv("DOWN_DEDAO_ROOT", DEFAULT_DOWN_DEDAO_ROOT)).expanduser()
    artifact_root = source_root / "artifacts"
    wiki_root = source_root / "wiki"
    raw_root = source_root / "raw"
    bridge_manifest = _load_down_dedao_bridge_manifest()

    return {
        "source_root": str(source_root),
        "exists": source_root.exists(),
        "wiki_exists": wiki_root.exists(),
        "artifacts_exists": artifact_root.exists(),
        "wiki_markdown_count": _count_files(wiki_root, "*.md"),
        "artifact_json_count": _count_files(artifact_root, "*.json"),
        "raw_source_count": _count_top_level(raw_root),
        "linked_document_count": origin_counts.get("down-dedao-llm-wiki", 0),
        "origin_counts": [
            {"origin": origin, "count": count}
            for origin, count in origin_counts.most_common(8)
        ],
        "bridge_manifest": bridge_manifest,
    }


def _load_down_dedao_bridge_manifest() -> dict[str, Any]:
    if not SYSTEM_KB_SEED_MANIFEST.exists():
        return {}
    try:
        manifest = json.loads(SYSTEM_KB_SEED_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    bridge_manifest = manifest.get("down_dedao_wiki")
    return bridge_manifest if isinstance(bridge_manifest, dict) else {}


def _count_files(root: Path, pattern: str) -> int:
    if not root.exists() or not root.is_dir():
        return 0
    return sum(1 for path in root.rglob(pattern) if path.is_file())


def _count_top_level(root: Path) -> int:
    if not root.exists() or not root.is_dir():
        return 0
    return sum(1 for _ in root.iterdir())


def _active_desktop_jobs(db: Session, user_id: int) -> list[dict[str, Any]]:
    jobs = (
        db.query(DesktopJob)
        .filter(
            DesktopJob.user_id == user_id,
            DesktopJob.status.in_(["queued", "running"]),
        )
        .order_by(desc(DesktopJob.created_at))
        .limit(10)
        .all()
    )
    return [job.to_dict() for job in jobs]


@router.get("/bootstrap")
def get_desktop_bootstrap(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the Mac app's launch context for the current user."""

    profile = (
        db.query(UserProfile)
        .filter(UserProfile.user_id == current_user.id)
        .first()
    )
    action_cards = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == current_user.id,
            ActionCard.status == "active",
            ActionCard.is_visible == True,  # noqa: E712
        )
        .order_by(desc(ActionCard.priority), desc(ActionCard.created_at))
        .limit(20)
        .all()
    )
    memory_facts = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == current_user.id,
            MemoryFact.superseded_at.is_(None),
        )
        .order_by(desc(MemoryFact.last_reinforced_at), desc(MemoryFact.created_at))
        .limit(10)
        .all()
    )

    return {
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
        },
        "model_preference": {
            "llm_model_id": profile.llm_model_id if profile else None,
        },
        "daily_plan": build_daily_operating_plan(db, current_user.id),
        "trajectory": build_health_trajectory_snapshot(db, current_user.id),
        "action_cards": [_action_card_to_dict(card) for card in action_cards],
        "recent_memory": [_memory_fact_to_dict(fact) for fact in memory_facts],
        "recent_records_summary": _recent_records_summary(db, current_user.id),
        "genomic_summary": _genomic_summary(db, current_user.id),
        "knowledge_summary": _knowledge_summary(db),
        "active_jobs": _active_desktop_jobs(db, current_user.id),
    }


@router.post("/import-jobs")
def create_desktop_import_job(
    body: DesktopJobCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a desktop-triggered long-running job.

    P0 stores the job and leaves actual worker wiring to the specific pipeline.
    The job table gives the Mac app a stable status surface immediately.
    """

    job = DesktopJob(
        user_id=current_user.id,
        job_type=body.job_type,
        status="queued",
        progress=0,
        source_kind=body.source_kind,
        source_name=body.source_name,
        source_hash=body.source_hash,
        request_payload=body.request_payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.to_dict()


@router.get("/jobs")
def list_desktop_jobs(
    status: str | None = Query(None, max_length=30),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    q = db.query(DesktopJob).filter(DesktopJob.user_id == current_user.id)
    if status:
        q = q.filter(DesktopJob.status == status)
    rows = q.order_by(desc(DesktopJob.created_at)).limit(limit).all()
    return [row.to_dict() for row in rows]


def _load_desktop_job(db: Session, *, user_id: int, job_id: int) -> DesktopJob:
    job = (
        db.query(DesktopJob)
        .filter(DesktopJob.id == job_id, DesktopJob.user_id == user_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Desktop job 不存在")
    return job


@router.get("/jobs/{job_id}")
def get_desktop_job(
    job_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return _load_desktop_job(db, user_id=current_user.id, job_id=job_id).to_dict()


@router.post("/jobs/{job_id}/retry")
def retry_desktop_job(
    job_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = _load_desktop_job(db, user_id=current_user.id, job_id=job_id)
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="只有 failed job 可以重试")

    retry = DesktopJob(
        user_id=current_user.id,
        job_type=job.job_type,
        status="queued",
        progress=0,
        source_kind=job.source_kind,
        source_name=job.source_name,
        source_hash=job.source_hash,
        request_payload=job.request_payload or {},
        retry_of_job_id=job.id,
    )
    db.add(retry)
    db.commit()
    db.refresh(retry)
    return retry.to_dict()


@router.get("/traces/{conversation_id}")
def get_desktop_conversation_trace(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return a desktop-friendly trace summary for one Agent conversation."""

    conv = (
        db.query(AgentConversation)
        .filter(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation trace 不存在")

    messages = (
        db.query(AgentMessage)
        .filter(AgentMessage.conversation_id == conv.id)
        .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
        .all()
    )
    assistant_messages = [m for m in messages if m.role == "assistant"]
    latest_assistant = assistant_messages[-1] if assistant_messages else None
    meta = dict(latest_assistant.meta or {}) if latest_assistant else {}

    return {
        "conversation": {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
        "assistant_message": {
            "id": latest_assistant.id if latest_assistant else None,
            "model": meta.get("model"),
            "elapsed_ms": meta.get("elapsed_ms"),
            "llm_ms": meta.get("llm_ms"),
            "llm_rounds": meta.get("llm_rounds"),
            "finish_reason": meta.get("finish_reason"),
            "completion_status": meta.get("completion_status"),
        },
        "sources_used": meta.get("sources_used") or [],
        "tool_calls": meta.get("tool_calls") or [],
        "evidence_cards": meta.get("cards") or [],
        "raw_meta": meta,
    }
