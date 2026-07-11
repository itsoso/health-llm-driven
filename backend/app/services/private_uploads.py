"""Owner-scoped signed URLs for privacy-sensitive uploaded files."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from urllib.parse import urlencode, urlsplit

from app.config import settings


PRIVATE_UPLOAD_URL_TTL_SECONDS = 5 * 60
PRIVATE_UPLOAD_CATEGORIES = frozenset({"chat", "diet", "medical", "other"})


def _normalized_category(category: str) -> str:
    normalized = str(category or "").strip().lower()
    if normalized not in PRIVATE_UPLOAD_CATEGORIES:
        raise ValueError("unsupported_private_upload_category")
    return normalized


def _private_upload_signature(
    category: str,
    owner_id: int,
    filename: str,
    expires: int,
    legacy: bool,
) -> str:
    namespace = "legacy" if legacy else "private"
    payload = (
        f"{namespace}:{_normalized_category(category)}:{int(owner_id)}:"
        f"{os.path.basename(filename)}:{int(expires)}"
    ).encode()
    return hmac.new(settings.secret_key.encode(), payload, hashlib.sha256).hexdigest()


def build_signed_private_upload_url(
    category: str,
    owner_id: int,
    filename: str,
    *,
    expires: int | None = None,
    legacy: bool = False,
) -> str:
    normalized_category = _normalized_category(category)
    safe_filename = os.path.basename(filename)
    expiry = int(expires or (time.time() + PRIVATE_UPLOAD_URL_TTL_SECONDS))
    signature = _private_upload_signature(
        normalized_category,
        owner_id,
        safe_filename,
        expiry,
        legacy,
    )
    if legacy:
        path = f"/api/v1/upload/files/{normalized_category}/{safe_filename}"
        query = {
            "owner_id": int(owner_id),
            "expires": expiry,
            "signature": signature,
        }
    else:
        path = (
            f"/api/v1/upload/files/{normalized_category}/"
            f"{int(owner_id)}/{safe_filename}"
        )
        query = {"expires": expiry, "signature": signature}
    return f"{path}?{urlencode(query)}"


def verify_signed_private_upload_url(
    category: str,
    owner_id: int,
    filename: str,
    expires: int | None,
    signature: str | None,
    *,
    legacy: bool = False,
) -> bool:
    if not expires or not signature or int(expires) < int(time.time()):
        return False
    try:
        expected = _private_upload_signature(
            category,
            owner_id,
            filename,
            int(expires),
            legacy,
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, str(signature))


def refresh_private_upload_url(
    raw_url: str | None,
    category: str,
    owner_id: int,
) -> str | None:
    """Return a fresh capability URL for canonical or legacy private paths."""
    if not raw_url:
        return raw_url
    normalized_category = _normalized_category(category)
    path = urlsplit(str(raw_url)).path
    private_match = re.search(
        rf"/api/v\d+/upload/files/{re.escape(normalized_category)}/(\d+)/([^/]+)$",
        path,
    )
    legacy_match = re.search(
        rf"/api/v\d+/upload/files/{re.escape(normalized_category)}/([^/]+)$",
        path,
    )
    if private_match and int(private_match.group(1)) == int(owner_id):
        return build_signed_private_upload_url(
            normalized_category,
            owner_id,
            private_match.group(2),
        )
    if legacy_match:
        return build_signed_private_upload_url(
            normalized_category,
            owner_id,
            legacy_match.group(1),
            legacy=True,
        )
    return str(raw_url)
