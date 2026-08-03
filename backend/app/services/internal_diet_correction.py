"""Authenticate same-process deterministic diet portion updates.

The public diet API must not trust client-controlled payload fields as proof
that nutrient values were calculated by the Agent. The Agent signs the exact
owner, record and update payload with the backend secret and sends the result
only as an internal request header.
"""

import hashlib
import hmac
import json
from typing import Any, Mapping

from app.config import settings


INTERNAL_DIET_PORTION_SIGNATURE_HEADER = (
    "X-Reva-Internal-Diet-Portion-Signature"
)


def diet_portion_update_fingerprint(
    record_id: Any,
    data: Mapping[str, Any],
) -> str:
    canonical = json.dumps(
        {"record_id": str(record_id), "data": dict(data)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_internal_diet_portion_signature(
    user_id: Any,
    record_id: Any,
    data: Mapping[str, Any],
) -> str:
    secret = str(settings.secret_key or "")
    if not secret:
        return ""
    fingerprint = diet_portion_update_fingerprint(record_id, data)
    message = f"diet-portion:v1:{user_id}:{fingerprint}".encode("utf-8")
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
    expected = build_internal_diet_portion_signature(
        user_id,
        record_id,
        data,
    )
    return bool(
        signature
        and expected
        and hmac.compare_digest(str(signature), expected)
    )
