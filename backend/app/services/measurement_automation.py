"""Device-first measurement automation capability map."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEDUPLICATION_KEY = "user_id + metric + source + timestamp_bucket + value"


_CAPABILITY_MAP: dict[str, dict[str, Any]] = {
    "weight": {
        "metric": "weight",
        "label": "体重",
        "fallback_ui": "manual_one_screen",
        "dedupe_key": DEDUPLICATION_KEY,
        "automation_path": [
            {
                "method": "system_health_store",
                "source": "apple_health",
                "platform": "ios",
                "confidence": "imported",
                "status": "native_required",
            },
            {
                "method": "system_health_store",
                "source": "health_connect",
                "platform": "android",
                "confidence": "imported",
                "status": "native_required",
            },
            {
                "method": "vendor_cloud",
                "source": "withings",
                "platform": "cloud",
                "confidence": "imported",
                "status": "optional_oauth",
            },
            {
                "method": "manual",
                "source": "manual",
                "platform": "all",
                "confidence": "user_confirmed",
                "status": "available",
            },
        ],
    },
    "waist_cm": {
        "metric": "waist_cm",
        "label": "腰围",
        "fallback_ui": "manual_one_screen",
        "dedupe_key": DEDUPLICATION_KEY,
        "automation_path": [
            {
                "method": "system_health_store",
                "source": "apple_health",
                "platform": "ios",
                "confidence": "imported",
                "status": "native_required",
            },
            {
                "method": "system_health_store",
                "source": "health_connect",
                "platform": "android",
                "confidence": "imported",
                "status": "native_required",
            },
            {
                "method": "device",
                "source": "renpho_smart_tape",
                "platform": "ios",
                "confidence": "sensor_direct",
                "status": "via_apple_health",
            },
            {
                "method": "manual",
                "source": "manual",
                "platform": "all",
                "confidence": "user_confirmed",
                "status": "available",
            },
        ],
    },
    "blood_pressure": {
        "metric": "blood_pressure",
        "label": "血压",
        "fallback_ui": "manual_one_screen",
        "dedupe_key": DEDUPLICATION_KEY,
        "automation_path": [
            {
                "method": "system_health_store",
                "source": "apple_health",
                "platform": "ios",
                "confidence": "imported",
                "status": "native_required",
            },
            {
                "method": "system_health_store",
                "source": "health_connect",
                "platform": "android",
                "confidence": "imported",
                "status": "native_required",
            },
            {
                "method": "vendor_cloud",
                "source": "withings",
                "platform": "cloud",
                "confidence": "imported",
                "status": "optional_oauth",
            },
            {
                "method": "manual",
                "source": "manual",
                "platform": "all",
                "confidence": "user_confirmed",
                "status": "available",
            },
        ],
    },
    "cgm": {
        "metric": "cgm",
        "label": "连续血糖",
        "fallback_ui": "manual_one_screen",
        "dedupe_key": DEDUPLICATION_KEY,
        "automation_path": [
            {
                "method": "device",
                "source": "cgm_device",
                "platform": "all",
                "confidence": "sensor_direct",
                "status": "medical_device_required",
            },
            {
                "method": "system_health_store",
                "source": "apple_health",
                "platform": "ios",
                "confidence": "imported",
                "status": "native_required",
            },
            {
                "method": "vendor_cloud",
                "source": "manufacturer_cloud",
                "platform": "cloud",
                "confidence": "imported",
                "status": "future_oauth",
            },
            {
                "method": "manual",
                "source": "manual",
                "platform": "all",
                "confidence": "user_confirmed",
                "status": "available",
            },
        ],
    },
}


def get_measurement_capability_map() -> dict[str, dict[str, Any]]:
    """Return supported measurement automation paths, keeping callers isolated."""
    return deepcopy(_CAPABILITY_MAP)


def measurement_plan_for(metric: str) -> dict[str, Any]:
    """Return the automation plan for one metric."""
    try:
        return deepcopy(_CAPABILITY_MAP[metric])
    except KeyError as exc:
        raise ValueError(f"Unsupported measurement metric: {metric}") from exc
