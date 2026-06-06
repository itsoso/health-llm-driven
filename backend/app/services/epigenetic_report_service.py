"""Service helpers for experimental epigenetic reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.epigenetic_report import EpigeneticReport
from app.models.user import User
from app.twin.schema import EpigeneticState

EPIGENETIC_CLAIM_BOUNDARY = (
    "表观遗传商业报告属于实验性健康趋势参考，只能用于长期干预方向和复测计划，"
    "不能证明个体短期干预成效或真实衰老速度改变，不替代医生诊断、处方或治疗。"
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


def create_epigenetic_report(
    db: Session,
    user_id: int,
    *,
    vendor: str,
    clock_type: str,
    sample_date: date,
    biological_age: float | None = None,
    pace_of_aging: float | None = None,
    raw_summary: dict[str, Any] | None = None,
) -> EpigeneticReport:
    """落库一份第三方 DNAm 时钟报告(W3 摄入侧)。

    不自建时钟,只接第三方结果(vendor + clock_type + 生物年龄/衰老速率)。
    evidence_tier 固定 experimental(由 latest_epigenetic_state 输出时带 claim_boundary)。
    落库后使该用户 Twin 缓存失效,下次 build_twin 即纳入。
    """
    report = EpigeneticReport(
        user_id=user_id,
        vendor=vendor.strip(),
        clock_type=clock_type.strip(),
        sample_date=sample_date,
        biological_age=biological_age,
        pace_of_aging=pace_of_aging,
        confidence="low",
        raw_summary=raw_summary or {},
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    # Twin 缓存失效 → 新报告下次构建即生效(失败不影响落库)
    try:
        from app.twin.cache import invalidate_twin

        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001
        pass
    return report


def list_epigenetic_reports(db: Session, user_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        db.query(EpigeneticReport)
        .filter(EpigeneticReport.user_id == user_id)
        .order_by(desc(EpigeneticReport.sample_date), desc(EpigeneticReport.id))
        .limit(limit)
        .all()
    )
    return [epigenetic_report_summary(row) for row in rows]


def latest_epigenetic_state(db: Session, user_id: int) -> EpigeneticState:
    """Return latest methylation report as a Twin-safe experimental state."""

    latest_reports = list_epigenetic_reports(db, user_id, limit=1)
    if not latest_reports:
        return EpigeneticState()

    latest_report = latest_reports[0]
    user_birth_date = db.query(User.birth_date).filter(User.id == user_id).scalar()
    sample_date = _parse_date(latest_report.get("sample_date"))
    biological_age = latest_report.get("biological_age")
    chronological_age = _chronological_age_years(user_birth_date, sample_date)
    biological_age_delta = (
        round(float(biological_age) - chronological_age, 1)
        if biological_age is not None and chronological_age is not None
        else None
    )

    return EpigeneticState(
        has_methylation_report=True,
        status="present",
        latest_test_date=latest_report.get("sample_date"),
        vendor=latest_report.get("vendor"),
        clock_type=latest_report.get("clock_type"),
        biological_age=biological_age,
        biological_age_delta_years=biological_age_delta,
        pace_of_aging=latest_report.get("pace_of_aging"),
        raw_summary=latest_report.get("raw_summary") or {},
        evidence_tier="experimental",
        confidence="low",
        claim_boundary=(
            latest_report.get("claim_boundary")
            or "甲基化时钟只作为长期代理指标和研究性反馈, "
            "不能证明个体短期干预成效或真实衰老速度改变。"
        ),
    )


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _chronological_age_years(birth_date: date | None, measured_date: date | None) -> float | None:
    if birth_date is None or measured_date is None:
        return None
    return (measured_date - birth_date).days / 365.25
