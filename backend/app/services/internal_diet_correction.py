"""Authenticate same-process deterministic diet portion updates.

The public diet API must not trust client-controlled payload fields as proof
that nutrient values were calculated by the Agent. The Agent signs the exact
owner, record, update payload and authoritative read baseline with the backend
secret. The API checks the baseline again while holding the update row lock.
"""

import hashlib
import hmac
import json
import re
from typing import Any, Mapping

from app.config import settings


INTERNAL_DIET_PORTION_SIGNATURE_HEADER = (
    "X-Reva-Internal-Diet-Portion-Signature"
)

# Only stable fields actually returned by the owned-record API. Signed photo
# URLs and display strings are deliberately excluded. updated_at complements
# the value snapshot: timestamp precision alone cannot protect same-tick edits.
_BASELINE_FIELDS = (
    "record_date", "meal_type", "meal_time", "food_items", "food_id", "source",
    "calories", "protein", "carbs", "fat", "fiber", "alcohol_units", "notes", "ai_recognized",
    "ai_confidence", "health_tips", "created_at", "updated_at",
)
_NUMERIC_FIELDS = frozenset((
    "calories", "protein", "carbs", "fat", "fiber", "alcohol_units",
    "ai_recognized", "ai_confidence",
))
_SIGNATURE_RE = re.compile(r"v2:([0-9a-f]{64}):([0-9a-f]{64})")


def _normalized_values(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: float(value) if key in _NUMERIC_FIELDS and isinstance(value, (int, float)) else value
        for key, value in data.items()
    }


def diet_portion_baseline_fingerprint(baseline_record: Mapping[str, Any]) -> str:
    """Hash the JSON-mode owned-record response, never model-supplied context."""
    canonical = json.dumps(
        _normalized_values({key: baseline_record.get(key) for key in _BASELINE_FIELDS}),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def diet_portion_update_fingerprint(
    record_id: Any,
    data: Mapping[str, Any],
) -> str:
    canonical = json.dumps(
        {"record_id": str(record_id), "data": _normalized_values(data)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_internal_diet_portion_signature(
    user_id: Any,
    record_id: Any,
    data: Mapping[str, Any],
    *,
    baseline_record: Mapping[str, Any],
) -> str:
    baseline_hash = diet_portion_baseline_fingerprint(baseline_record)
    digest = _signature_digest(user_id, record_id, data, baseline_hash)
    return f"v2:{baseline_hash}:{digest}" if digest else ""


def _signature_digest(user_id, record_id, data, baseline_hash: str) -> str:
    secret = str(settings.secret_key or "")
    if not secret:
        return ""
    fingerprint = diet_portion_update_fingerprint(record_id, data)
    message = f"diet-portion:v2:{user_id}:{fingerprint}:{baseline_hash}".encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def verify_internal_diet_portion_signature(
    signature: str | None,
    user_id: Any,
    record_id: Any,
    data: Mapping[str, Any],
) -> bool:
    parsed = _SIGNATURE_RE.fullmatch(signature or "")
    if parsed is None:
        return False
    expected = _signature_digest(user_id, record_id, data, parsed.group(1))
    return bool(
        expected and hmac.compare_digest(parsed.group(2), expected)
    )


def diet_portion_baseline_matches(
    signature: str, baseline_record: Mapping[str, Any],
) -> bool:
    """Call only after authenticating the signature and locking the owned row."""
    parsed = _SIGNATURE_RE.fullmatch(signature or "")
    return bool(parsed and hmac.compare_digest(
        parsed.group(1), diet_portion_baseline_fingerprint(baseline_record),
    ))
