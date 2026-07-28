"""Versioned cache helpers for derived Safety Guardian reports."""

from app.utils.redis_cache import RedisCache


SAFETY_CACHE_PREFIX = "safety:v3"


def safety_report_cache_key(
    user_id: int,
    *,
    severity_min: int,
    limit: int,
    dedup_by_rule: bool,
) -> str:
    return (
        f"{SAFETY_CACHE_PREFIX}:{user_id}:"
        f"s{severity_min}:l{limit}:d{int(dedup_by_rule)}"
    )


def invalidate_safety_report_cache(user_id: int) -> int:
    """Drop every parameterized Safety report derived from a user's Twin."""

    return RedisCache.clear_pattern(f"{SAFETY_CACHE_PREFIX}:{user_id}:*")
