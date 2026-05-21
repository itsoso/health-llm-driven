"""Normalize Health Twin signals into a planner-facing personal evidence matrix."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any


Signal = dict[str, Any]


def build_personal_evidence_matrix(twin: Any) -> dict[str, Any]:
    """Build a deterministic evidence matrix from an existing Health Twin object or dict."""

    generated_at = _value(_section(twin, "meta"), "generated_at")
    signals: list[Signal] = []

    _add_genetic_signals(twin, signals)
    _add_lab_signals(twin, signals)
    _add_body_signals(twin, signals)
    _add_wearable_signals(twin, signals)
    _add_behavior_signals(twin, signals)
    _add_data_gap_signals(twin, signals)

    signals.sort(key=lambda signal: (signal["signal_type"], signal["signal_id"]))
    return {
        "user_id": _value(_section(twin, "meta"), "user_id"),
        "generated_at": _to_iso(generated_at) or datetime.now(UTC).isoformat(),
        "signals": signals,
        "summary": _summary(signals),
        "claim_boundary": "个人证据矩阵只用于调整健康建议置信度和数据采集优先级，不替代医生诊断、处方或治疗。",
    }


def derive_personal_matrix_planner_flags(matrix: dict[str, Any]) -> list[str]:
    """Derive deterministic planner guardrails from a personal evidence matrix."""

    signals = _matrix_signals(matrix)
    flags: set[str] = set()

    lab_signals = [signal for signal in signals if signal.get("signal_type") == "lab"]
    gap_ids = {str(signal.get("signal_id")) for signal in signals if signal.get("signal_type") == "data_gap"}
    if "gap.lab_anchor_missing" in gap_ids:
        flags.add("lab_anchor_missing")
    elif not lab_signals or any(signal.get("freshness") == "stale" for signal in lab_signals):
        flags.add("lab_anchor_stale")

    if _has_poor_recovery_signal(signals):
        flags.add("poor_recovery_matrix")

    has_genetic = any(signal.get("signal_type") == "genetic" for signal in signals)
    has_validation_signal = any(
        signal.get("signal_type") in {"lab", "body_measurement", "wearable", "behavior"}
        for signal in signals
    )
    if has_genetic and not has_validation_signal:
        flags.add("genetic_only_policy")

    return sorted(flags)


def compact_personal_evidence_matrix(matrix: dict[str, Any], *, max_signals: int = 8) -> dict[str, Any]:
    """Return a planner-safe compact matrix view for state summaries and prompts."""

    signals = _matrix_signals(matrix)
    priority_signals = sorted(
        signals,
        key=lambda signal: (
            signal.get("signal_type") != "data_gap",
            signal.get("confidence_modifier") != "lower",
            str(signal.get("signal_id") or ""),
        ),
    )[:max_signals]
    return {
        "summary": matrix.get("summary", {}),
        "planner_flags": derive_personal_matrix_planner_flags(matrix),
        "key_signals": [
            {
                "signal_id": signal.get("signal_id"),
                "signal_type": signal.get("signal_type"),
                "freshness": signal.get("freshness"),
                "reliability": signal.get("reliability"),
                "confidence_modifier": signal.get("confidence_modifier"),
                "domains": signal.get("domains", []),
            }
            for signal in priority_signals
        ],
    }


def _add_genetic_signals(twin: Any, signals: list[Signal]) -> None:
    genetic = _section(twin, "genetic")
    if not _value(genetic, "has_profile"):
        return

    buckets = (
        ("drug", "drug_sensitivity", ["medication_safety", "pharmacogenomics"]),
        ("risk", "risk_variants", ["metabolic_health", "disease_risk"]),
        ("nutrition", "nutrition_variants", ["nutrition", "metabolic_health"]),
        ("recovery", "recovery_variants", ["recovery_capacity"]),
        ("exercise", "exercise_variants", ["movement", "recovery_capacity"]),
        ("sleep", "sleep_variants", ["sleep", "recovery_capacity"]),
        ("cognition", "cognition_variants", ["cognition", "emotion"]),
        ("personality", "personality_variants", ["emotion", "behavior"]),
    )
    for bucket_name, field_name, domains in buckets:
        for variant in _list(_value(genetic, field_name)):
            gene_name = str(_value(variant, "gene_name") or _value(variant, "gene") or "unknown").strip()
            if not gene_name:
                continue
            _append_signal(
                signals,
                signal_id=f"genetic.{bucket_name}.{gene_name}",
                signal_type="genetic",
                label=f"{gene_name} genetic signal",
                value={
                    "risk_level": _value(variant, "risk_level"),
                    "result_label": _value(variant, "result_label"),
                    "genotype": _value(variant, "genotype"),
                },
                freshness=_freshness(twin, "genetic", default="long_term"),
                reliability="medium",
                domains=domains,
                confidence_modifier="lower",
                source="genetic_report",
            )


def _add_lab_signals(twin: Any, signals: list[Signal]) -> None:
    labs = _section(twin, "labs")
    lab_specs = (
        ("hba1c", "HbA1c", ["metabolic_health"], "%"),
        ("ldl", "LDL-C", ["cardiovascular", "metabolic_health"], "mmol/L"),
        ("triglycerides", "Triglycerides", ["metabolic_health"], "mmol/L"),
        ("blood_glucose", "Blood glucose", ["metabolic_health"], "mmol/L"),
        ("uric_acid", "Uric acid", ["metabolic_health"], "umol/L"),
        ("egfr", "eGFR", ["medication_safety", "metabolic_health"], "mL/min/1.73m²"),
    )
    for field_name, label, domains, unit in lab_specs:
        value = _value(labs, field_name)
        if value is None:
            continue
        _append_signal(
            signals,
            signal_id=f"lab.{field_name}",
            signal_type="lab",
            label=label,
            value=value,
            unit=unit,
            freshness=_freshness(twin, "labs", default=_freshness_from_date(_value(labs, "last_exam_date"))),
            reliability="high",
            domains=domains,
            confidence_modifier="raise",
            source="clinical_lab",
        )

    systolic = _value(labs, "blood_pressure_systolic")
    diastolic = _value(labs, "blood_pressure_diastolic")
    if systolic is not None and diastolic is not None:
        _append_signal(
            signals,
            signal_id="lab.blood_pressure",
            signal_type="lab",
            label="Blood pressure",
            value={"systolic": systolic, "diastolic": diastolic},
            unit="mmHg",
            freshness=_freshness(twin, "blood_pressure", default=_freshness_from_date(_value(labs, "blood_pressure_date"))),
            reliability="high",
            domains=["cardiovascular", "metabolic_health"],
            confidence_modifier="raise",
            source="blood_pressure_log",
        )


def _add_body_signals(twin: Any, signals: list[Signal]) -> None:
    body = _section(twin, "body_composition")
    body_specs = (
        ("weight_kg", "Weight", ["metabolic_health", "body_composition"], "kg", "weight", "last_weighed"),
        ("waist_cm", "Waist circumference", ["metabolic_health", "body_composition"], "cm", "waist", "last_waist_measured"),
        ("bmi", "BMI", ["metabolic_health", "body_composition"], "kg/m²", "weight", "last_weighed"),
        ("body_fat_pct", "Body fat", ["metabolic_health", "body_composition"], "%", "weight", "last_weighed"),
    )
    for field_name, label, domains, unit, freshness_key, date_field in body_specs:
        value = _value(body, field_name)
        if value is None:
            continue
        _append_signal(
            signals,
            signal_id=f"body.{field_name}",
            signal_type="body_measurement",
            label=label,
            value=value,
            unit=unit,
            freshness=_freshness(twin, freshness_key, default=_freshness_from_date(_value(body, date_field))),
            reliability="medium",
            domains=domains,
            confidence_modifier="raise",
            source="body_measurement",
        )

    central_obesity = _value(body, "central_obesity_flag")
    if central_obesity is not None:
        _append_signal(
            signals,
            signal_id="body.central_obesity_flag",
            signal_type="body_measurement",
            label="Central obesity flag",
            value=central_obesity,
            freshness=_freshness(twin, "waist", default=_freshness_from_date(_value(body, "last_waist_measured"))),
            reliability="medium",
            domains=["metabolic_health", "cardiovascular"],
            confidence_modifier="raise" if central_obesity else "neutral",
            source="body_measurement",
        )


def _add_wearable_signals(twin: Any, signals: list[Signal]) -> None:
    physiological = _section(twin, "physiological")
    wearable_specs = (
        ("sleep_score_latest", "Sleep score", ["sleep", "recovery_capacity"], None),
        ("sleep_duration_h_latest", "Sleep duration", ["sleep", "recovery_capacity"], "h"),
        ("hrv_latest", "HRV", ["recovery_capacity"], "ms"),
        ("training_readiness_score", "Training readiness", ["recovery_capacity", "movement"], None),
        ("resting_hr", "Resting heart rate", ["recovery_capacity", "cardiovascular"], "bpm"),
        ("steps_today", "Steps today", ["movement", "metabolic_health"], "steps"),
    )
    for field_name, label, domains, unit in wearable_specs:
        value = _value(physiological, field_name)
        if value is None:
            continue
        _append_signal(
            signals,
            signal_id=f"wearable.{field_name}",
            signal_type="wearable",
            label=label,
            value=value,
            unit=unit,
            freshness=_freshness(twin, "sleep", default=_freshness_from_date(_value(physiological, "last_updated"))),
            reliability="medium",
            domains=domains,
            confidence_modifier="raise",
            source="wearable",
        )

    hrv_status = _value(physiological, "hrv_status")
    if hrv_status:
        _append_signal(
            signals,
            signal_id="wearable.hrv_status",
            signal_type="wearable",
            label="HRV status",
            value=hrv_status,
            freshness=_freshness(twin, "sleep", default=_freshness_from_date(_value(physiological, "last_updated"))),
            reliability="medium",
            domains=["recovery_capacity"],
            confidence_modifier="raise",
            source="wearable",
        )


def _add_behavior_signals(twin: Any, signals: list[Signal]) -> None:
    behavioral = _section(twin, "behavioral")
    behavior_specs = (
        ("diet_calories_today", "Calories logged today", ["nutrition", "metabolic_health"], "kcal", "diet"),
        ("diet_protein_g_today", "Protein logged today", ["nutrition", "metabolic_health"], "g", "diet"),
        ("meals_logged_today", "Meals logged today", ["nutrition", "behavior"], "count", "diet"),
        ("water_ml_today", "Water logged today", ["hydration", "behavior"], "ml", "diet"),
        ("workouts_this_week", "Workouts this week", ["movement", "recovery_capacity"], "count", "unknown"),
        ("acute_chronic_ratio", "Acute chronic workload ratio", ["movement", "recovery_capacity"], None, "unknown"),
    )
    for field_name, label, domains, unit, freshness_key in behavior_specs:
        value = _value(behavioral, field_name)
        if value is None:
            continue
        if field_name in {"meals_logged_today", "water_ml_today", "workouts_this_week"} and value == 0:
            continue
        _append_signal(
            signals,
            signal_id=f"behavior.{field_name}",
            signal_type="behavior",
            label=label,
            value=value,
            unit=unit,
            freshness=_freshness(twin, freshness_key, default="today" if freshness_key == "diet" else "unknown"),
            reliability="low",
            domains=domains,
            confidence_modifier="neutral",
            source="daily_log",
        )


def _add_data_gap_signals(twin: Any, signals: list[Signal]) -> None:
    genetic = _section(twin, "genetic")
    labs = _section(twin, "labs")
    body = _section(twin, "body_composition")
    physiological = _section(twin, "physiological")
    behavioral = _section(twin, "behavioral")

    if not _value(genetic, "has_profile"):
        _append_gap(signals, "gap.genetic_profile_missing", "Missing genetic profile", ["genetics"])
    if _value(labs, "last_exam_date") is None and not _value(labs, "flagged_abnormal"):
        _append_gap(signals, "gap.lab_anchor_missing", "Missing recent lab anchor", ["metabolic_health"])
    if _value(body, "weight_kg") is None and _value(body, "waist_cm") is None:
        _append_gap(signals, "gap.body_measurement_missing", "Missing body measurements", ["metabolic_health"])
    if _value(physiological, "sleep_score_latest") is None and _value(physiological, "training_readiness_score") is None:
        _append_gap(
            signals,
            "gap.wearable_sleep_recovery_missing",
            "Missing wearable sleep/recovery state",
            ["sleep", "recovery_capacity"],
        )
    if not any(
        _value(behavioral, field_name)
        for field_name in ("diet_calories_today", "diet_protein_g_today", "meals_logged_today", "water_ml_today", "workouts_this_week")
    ):
        _append_gap(
            signals,
            "gap.behavior_log_missing",
            "Missing daily behavior logs",
            ["nutrition", "movement", "behavior"],
        )


def _append_gap(signals: list[Signal], signal_id: str, label: str, domains: list[str]) -> None:
    _append_signal(
        signals,
        signal_id=signal_id,
        signal_type="data_gap",
        label=label,
        value=None,
        freshness="missing",
        reliability="low",
        domains=domains,
        confidence_modifier="lower",
        source="matrix_gap_detector",
    )


def _append_signal(
    signals: list[Signal],
    *,
    signal_id: str,
    signal_type: str,
    label: str,
    value: Any,
    freshness: str,
    reliability: str,
    domains: list[str],
    confidence_modifier: str,
    source: str,
    unit: str | None = None,
) -> None:
    signal: Signal = {
        "signal_id": signal_id,
        "signal_type": signal_type,
        "label": label,
        "value": value,
        "freshness": freshness,
        "reliability": reliability,
        "domains": domains,
        "confidence_modifier": confidence_modifier,
        "source": source,
    }
    if unit:
        signal["unit"] = unit
    signals.append(signal)


def _summary(signals: list[Signal]) -> dict[str, Any]:
    by_signal_type: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    by_confidence_modifier: dict[str, int] = {}
    for signal in signals:
        signal_type = signal["signal_type"]
        by_signal_type[signal_type] = by_signal_type.get(signal_type, 0) + 1
        confidence_modifier = signal["confidence_modifier"]
        by_confidence_modifier[confidence_modifier] = by_confidence_modifier.get(confidence_modifier, 0) + 1
        for domain in signal["domains"]:
            by_domain[domain] = by_domain.get(domain, 0) + 1
    return {
        "signal_count": len(signals),
        "data_gap_count": by_signal_type.get("data_gap", 0),
        "by_signal_type": dict(sorted(by_signal_type.items())),
        "by_domain": dict(sorted(by_domain.items())),
        "by_confidence_modifier": dict(sorted(by_confidence_modifier.items())),
    }


def _section(container: Any, name: str) -> Any:
    if isinstance(container, dict):
        return container.get(name) or {}
    return getattr(container, name, None)


def _value(container: Any, name: str, default: Any = None) -> Any:
    if container is None:
        return default
    if isinstance(container, dict):
        return container.get(name, default)
    return getattr(container, name, default)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _freshness(twin: Any, key: str, *, default: str) -> str:
    freshness = _section(twin, "freshness")
    value = _value(freshness, key)
    if value in {"today", "fresh", "recent", "stale", "long_term", "missing", "unknown"}:
        return value
    return default if default in {"today", "fresh", "recent", "stale", "long_term", "missing", "unknown"} else "unknown"


def _freshness_from_date(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return "unknown"
    age_days = (date.today() - value).days
    if age_days <= 1:
        return "today"
    if age_days <= 30:
        return "fresh"
    if age_days <= 120:
        return "recent"
    return "stale"


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value:
        return str(value)
    return None


def _matrix_signals(matrix: dict[str, Any]) -> list[Signal]:
    signals = matrix.get("signals")
    return signals if isinstance(signals, list) else []


def _has_poor_recovery_signal(signals: list[Signal]) -> bool:
    for signal in signals:
        signal_id = signal.get("signal_id")
        value = signal.get("value")
        if signal_id == "wearable.sleep_score_latest" and isinstance(value, (int, float)) and value < 65:
            return True
        if signal_id == "wearable.training_readiness_score" and isinstance(value, (int, float)) and value < 50:
            return True
        if signal_id == "wearable.hrv_status" and str(value).lower() in {"low", "poor", "偏低", "低"}:
            return True
    return False
