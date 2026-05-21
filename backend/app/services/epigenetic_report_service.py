"""Service helpers for experimental epigenetic reports."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.epigenetic_report import EpigeneticReport

EPIGENETIC_CLAIM_BOUNDARY = (
    "表观遗传商业报告属于实验性健康趋势参考，只能用于长期干预方向和复测计划，"
    "不替代医生诊断、处方或治疗。"
)


def epigenetic_report_summary(report: EpigeneticReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "user_id": report.user_id,
        "vendor": report.vendor,
        "sample_date": report.sample_date.isoformat() if report.sample_date else None,
        "clock_type": report.clock_type,
        "biological_age": report.biological_age,
        "pace_of_aging": report.pace_of_aging,
        "raw_summary": report.raw_summary or {},
        "evidence_tier": "experimental",
        "confidence": "low",
        "claim_boundary": EPIGENETIC_CLAIM_BOUNDARY,
    }


def list_epigenetic_reports(db: Session, user_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        db.query(EpigeneticReport)
        .filter(EpigeneticReport.user_id == user_id)
        .order_by(desc(EpigeneticReport.sample_date), desc(EpigeneticReport.id))
        .limit(limit)
        .all()
    )
    return [epigenetic_report_summary(row) for row in rows]
