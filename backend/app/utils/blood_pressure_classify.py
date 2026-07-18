"""Blood-pressure classification and severe-reading safety text.

This module is the single deterministic source for record/API classification,
read-path safety escalation, and clients that need a factual status label.
"""
from __future__ import annotations

import json
import re
from typing import Any


SEVERE_READING_SYSTOLIC = 180
SEVERE_READING_DIASTOLIC = 120
SEVERE_READING_CATEGORY = "血压严重升高"
SAFETY_WARNING_MARKER = "\n\n⚠️ 安全提示:"

_CATEGORY_COLORS = {
    SEVERE_READING_CATEGORY: "#FF3B30",
    "高血压2级": "#FF453A",
    "高血压1级": "#FF6723",
    "正常偏高": "#FF9F0A",
    "偏低": "#5AC8FA",
    "正常": "#30D158",
}


def severe_blood_pressure_safety_guidance(
    systolic: int,
    diastolic: int,
) -> dict[str, str] | None:
    """Return deterministic guidance for a severe reading, without diagnosing."""
    if systolic < SEVERE_READING_SYSTOLIC and diastolic < SEVERE_READING_DIASTOLIC:
        return None
    return {
        "severity": "high",
        "title": "血压严重升高，请复测",
        "recheck_instruction": "请静坐至少 1 分钟后复测；若复测仍处于此范围，请尽快联系医疗专业人员。",
        "emergency_instruction": "若同时出现胸痛、气促、背痛、麻木或无力、视力改变或说话困难，请立即拨打急救电话。",
        "action_path": "/blood-pressure",
    }


def classify_blood_pressure(systolic: int, diastolic: int) -> str:
    """Classify by the more severe systolic or diastolic category.

    A single severe reading is deliberately labelled as a severe reading, not
    a hypertensive emergency diagnosis. Emergency triage requires symptoms and
    clinical assessment in addition to the measurement.
    """
    if systolic >= SEVERE_READING_SYSTOLIC or diastolic >= SEVERE_READING_DIASTOLIC:
        return SEVERE_READING_CATEGORY
    if systolic >= 140 or diastolic >= 90:
        return "高血压2级"
    if systolic >= 130 or diastolic >= 80:
        return "高血压1级"
    if systolic >= 120 and diastolic < 80:
        return "正常偏高"
    if systolic < 90 or diastolic < 60:
        return "偏低"
    return "正常"


def blood_pressure_display(systolic: int, diastolic: int) -> dict[str, Any]:
    """Build the authoritative display payload for every record read path."""
    category = classify_blood_pressure(systolic, diastolic)
    return {
        "category": category,
        "category_color": _CATEGORY_COLORS[category],
        "safety_guidance": severe_blood_pressure_safety_guidance(systolic, diastolic),
    }


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        return int(match.group()) if match else None
    return None


def is_severe_blood_pressure_record(record: dict[str, Any]) -> bool:
    """True when a record needs deterministic recheck-and-triage guidance."""
    systolic = _as_int(record.get("systolic"))
    diastolic = _as_int(record.get("diastolic"))
    return (
        (systolic is not None and systolic >= SEVERE_READING_SYSTOLIC)
        or (diastolic is not None and diastolic >= SEVERE_READING_DIASTOLIC)
        or str(record.get("category") or "").strip() == SEVERE_READING_CATEGORY
    )


def _read_records(result: str) -> list[dict[str, Any]] | None:
    """Parse JSON result text, allowing the standard display truncation suffix."""
    text = (result or "").strip()
    if not text or text.startswith("Error"):
        return None
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError:
        starts = [index for index in (text.find("["), text.find("{")) if index >= 0]
        if not starts:
            return None
        try:
            payload, _ = json.JSONDecoder().raw_decode(text[min(starts):])
        except json.JSONDecodeError:
            return None

    records: list[dict[str, Any]] = []

    def collect(value: Any, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(value, dict):
            if "systolic" in value and "diastolic" in value:
                records.append(value)
                return
            for item in value.values():
                collect(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                collect(item, depth + 1)

    collect(payload)
    return records


def append_severe_bp_reading_warning(result: str) -> str:
    """Append factual, symptom-aware safety guidance to severe BP query results."""
    if not result or SAFETY_WARNING_MARKER in result:
        return result
    records = _read_records(result)
    if not records:
        return result

    severe_record = next(
        (record for record in records if is_severe_blood_pressure_record(record)),
        None,
    )
    if severe_record is None:
        return result

    systolic = _as_int(severe_record.get("systolic"))
    diastolic = _as_int(severe_record.get("diastolic"))
    measured_at = str(
        severe_record.get("measured_at") or severe_record.get("record_date") or ""
    ).strip()
    reading = f"{systolic}/{diastolic} mmHg" if systolic is not None and diastolic is not None else "该血压读数"
    date_note = f"（{measured_at}）" if measured_at else ""
    guidance = severe_blood_pressure_safety_guidance(
        systolic or SEVERE_READING_SYSTOLIC,
        diastolic or SEVERE_READING_DIASTOLIC,
    )
    if guidance is None:
        return result

    return (
        f"{result}{SAFETY_WARNING_MARKER} 发现血压严重升高读数 {reading}{date_note}"
        f"（收缩压≥{SEVERE_READING_SYSTOLIC} 或舒张压≥{SEVERE_READING_DIASTOLIC} mmHg）。"
        f"{guidance['recheck_instruction']}{guidance['emergency_instruction']}"
    )
