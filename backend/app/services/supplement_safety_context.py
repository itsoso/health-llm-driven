"""Build supplement safety context from reviewed profile and lab timelines."""

from __future__ import annotations

from datetime import date, timedelta
import logging
import re
from typing import Any, Iterable

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.family_health import MedicalIndicator
from app.services.supplement_evidence import SupplementSafetyContext

logger = logging.getLogger(__name__)

DEFAULT_LAB_LOOKBACK_DAYS = 540
MAX_LAB_SCAN_ROWS = 300


LAB_MATCHERS: dict[str, dict[str, tuple[str, ...]]] = {
    "egfr": {
        "aliases": ("egfr", "估算肾小球滤过率", "肾小球滤过率", "gfr"),
        "excludes": ("egfr-l858r", "l858r"),
    },
    "ferritin": {
        "aliases": ("ferritin", "铁蛋白"),
        "excludes": ("转铁蛋白", "transferrin"),
    },
    "vitamin_d": {
        "aliases": (
            "25(oh)d",
            "25-oh-d",
            "25-oh",
            "25ohd",
            "25羟维生素d",
            "25-羟维生素d",
            "维生素d",
            "vitamin d",
            "vitamind",
        ),
        "excludes": (),
    },
    "triglycerides": {
        "aliases": ("甘油三酯", "三酰甘油", "triglycerides", "trig", "tg"),
        "excludes": (),
    },
    "ldl": {
        "aliases": ("低密度脂蛋白", "低密度脂蛋白胆固醇", "ldl", "ldl-c", "ldlc"),
        "excludes": (),
    },
    "calcium": {
        "aliases": ("血钙", "serum calcium", "calcium"),
        "excludes": ("钙化", "冠脉钙", "calcium score"),
    },
    "hemoglobin": {
        "aliases": ("血红蛋白", "hemoglobin", "hgb", "hb"),
        "excludes": ("糖化血红蛋白", "hba1c", "hba1", "血红蛋白a2"),
    },
}


def build_supplement_safety_context(
    db: Session,
    user_id: int,
    profile: Any | None,
    target_date: date | None = None,
) -> SupplementSafetyContext:
    warnings: list[str] = []
    labs: dict[str, float] = {}
    try:
        labs = fetch_supplement_safety_labs(db, user_id, target_date=target_date)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[supplement_safety_context] lab fetch failed user_id=%s error=%s",
            user_id,
            type(exc).__name__,
        )
        warnings.append("lab_fetch_failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("[supplement_safety_context] rollback after lab fetch failure failed", exc_info=True)
    return SupplementSafetyContext.from_profile(profile, labs=labs, data_warnings=tuple(warnings))


def fetch_supplement_safety_labs(
    db: Session,
    user_id: int,
    *,
    target_date: date | None = None,
    lookback_days: int = DEFAULT_LAB_LOOKBACK_DAYS,
) -> dict[str, float]:
    end_date = target_date or date.today()
    start_date = end_date - timedelta(days=lookback_days)
    rows = (
        db.query(MedicalIndicator)
        .filter(
            MedicalIndicator.user_id == user_id,
            MedicalIndicator.value.isnot(None),
            MedicalIndicator.record_date >= start_date,
            MedicalIndicator.record_date <= end_date,
        )
        .order_by(desc(MedicalIndicator.record_date), desc(MedicalIndicator.id))
        .limit(MAX_LAB_SCAN_ROWS)
        .all()
    )
    return extract_supplement_safety_labs_from_indicators(rows)


def extract_supplement_safety_labs_from_indicators(rows: Iterable[Any]) -> dict[str, float]:
    labs: dict[str, float] = {}
    for row in sorted(rows, key=_indicator_sort_key, reverse=True):
        metric = _resolve_lab_metric(row)
        if not metric or metric in labs:
            continue
        value = _as_float(getattr(row, "value", None))
        if value is None:
            continue
        labs[metric] = value
    return labs


def _resolve_lab_metric(row: Any) -> str | None:
    fields = _indicator_fields(row)
    for metric, spec in LAB_MATCHERS.items():
        excludes = spec.get("excludes", ())
        if _has_alias(fields, excludes):
            continue
        if _has_alias(fields, spec.get("aliases", ())):
            return metric
    return None


def _indicator_fields(row: Any) -> tuple[str, ...]:
    return tuple(
        str(getattr(row, attr, "") or "")
        for attr in ("item_code", "name_en", "name", "category")
        if str(getattr(row, attr, "") or "").strip()
    )


def _has_alias(fields: tuple[str, ...], aliases: Iterable[str]) -> bool:
    for alias in aliases:
        if not _field_has_alias(fields, alias):
            continue
        return True
    return False


def _field_has_alias(fields: tuple[str, ...], alias: str) -> bool:
    normalized_alias = _normalize_lab_text(alias)
    compact_alias = _compact_lab_text(alias)
    if not normalized_alias:
        return False
    for field in fields:
        normalized_field = _normalize_lab_text(field)
        compact_field = _compact_lab_text(field)
        if not normalized_field:
            continue
        if _is_short_english_alias(normalized_alias):
            if (
                normalized_field == normalized_alias
                or normalized_field.startswith(f"{normalized_alias}-")
                or normalized_field.startswith(f"{normalized_alias}_")
                or normalized_field.startswith(f"{normalized_alias}/")
            ):
                return True
            continue
        if normalized_alias in normalized_field or compact_alias in compact_field:
            return True
    return False


def _is_short_english_alias(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{1,4}", value))


def _indicator_sort_key(row: Any) -> tuple[date, int]:
    record_date = getattr(row, "record_date", None)
    if not isinstance(record_date, date):
        record_date = date.min
    row_id = getattr(row, "id", None)
    return record_date, int(row_id or 0)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_lab_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower()).replace("µ", "μ")


def _compact_lab_text(value: str) -> str:
    return re.sub(r"[\s\-_()（）/]+", "", _normalize_lab_text(value))
