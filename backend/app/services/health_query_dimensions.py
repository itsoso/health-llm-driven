"""health_query dimension normalization shared by schema guard and executor."""

from __future__ import annotations

import re
from typing import Any, Dict


HEALTH_QUERY_DIM_ALIASES: Dict[str, str] = {
    # 生活事件时间线(情景记忆账本,2026-07-12)
    "timeline": "events",
    "life_events": "events",
    "life_event": "events",
    "时间线": "events",
    "行程": "events",
    "生活事件": "events",
    "今日行程": "events",
    "lab_results": "medical_exam",
    "lab_result": "medical_exam",
    "lab": "medical_exam",
    "labs": "medical_exam",
    "化验": "medical_exam",
    "化验结果": "medical_exam",
    "化验报告": "medical_exam",
    "exam": "medical_exam",
    "medical": "medical_exam",
    "blood_test": "medical_exam",
    "bloodtest": "medical_exam",
    "checkup": "medical_exam",
    "体检": "medical_exam",
    "medical_records": "medical_exam",
    "medical_record": "medical_exam",
    "medical_report": "medical_exam",
    "imaging": "medical_exam",
    "radiology": "medical_exam",
    "mri": "medical_exam",
    "ct": "medical_exam",
    "xray": "medical_exam",
    "x-ray": "medical_exam",
    "ultrasound": "medical_exam",
    "影像": "medical_exam",
    "影像报告": "medical_exam",
    "检查报告": "medical_exam",
    "核磁": "medical_exam",
    "磁共振": "medical_exam",
    "ct报告": "medical_exam",
    "x光": "medical_exam",
    "b超": "medical_exam",
    "gene": "genetic",
    "genes": "genetic",
    "genetics": "genetic",
    "基因": "genetic",
    "bp": "blood_pressure",
    "血压": "blood_pressure",
    "meds": "medication",
    "medications": "medication",
    "用药": "medication",
    "diet": "diet",
    "food": "diet",
    "foods": "diet",
    "meal": "diet",
    "meals": "diet",
    "calorie": "diet",
    "calories": "diet",
    "nutrition": "diet",
    "饮食": "diet",
    "饮食记录": "diet",
    "吃饭": "diet",
    "吃了什么": "diet",
    "热量": "diet",
    "卡路里": "diet",
    "全天饮食": "diet",
    # 生活事件时间线别名 → 既有 "events" 维度 (读 /episodes/me/life-events)。
    "trip": "events",
    "itinerary": "events",
    "轨迹": "events",
    "时间轴": "events",
    "节点": "events",
}

HEALTH_QUERY_DIM_KEYS = ("dimension", "type", "query_type", "category", "kind")
HEALTH_QUERY_CANONICAL_KEYS = (
    "dimension",
    "days",
    "indicator",
    "keyword",
    "uploaded_days",
    "uploaded_since",
)
ILLNESS_MAX_QUERY_DAYS = 36500


def normalize_health_query_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and project model-generated args to the public query schema."""
    a = dict(args or {})
    if not a.get("dimension"):
        for key in HEALTH_QUERY_DIM_KEYS:
            if key != "dimension" and a.get(key):
                a["dimension"] = a[key]
                break

    dim = a.get("dimension")
    if isinstance(dim, str):
        stripped = dim.strip()
        a["dimension"] = HEALTH_QUERY_DIM_ALIASES.get(stripped.lower(), stripped)

    if not a.get("days"):
        time_range = a.get("time_range") or a.get("range") or a.get("time")
        if time_range is not None:
            match = re.search(r"\d+", str(time_range))
            if match:
                a["days"] = int(match.group())

    if not a.get("keyword"):
        keyword = a.get("keywords") or a.get("query")
        if keyword:
            a["keyword"] = keyword

    if not a.get("uploaded_since") and a.get("created_since"):
        a["uploaded_since"] = a["created_since"]

    if not a.get("uploaded_days"):
        uploaded_range = (
            a.get("created_days")
            or a.get("uploaded_range")
            or a.get("upload_range")
            or a.get("created_range")
        )
        if uploaded_range is not None:
            match = re.search(r"\d+", str(uploaded_range))
            if match:
                a["uploaded_days"] = int(match.group())

    return {key: a[key] for key in HEALTH_QUERY_CANONICAL_KEYS if key in a}
