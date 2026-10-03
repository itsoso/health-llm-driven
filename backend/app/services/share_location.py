"""Authenticated callers only. Fixed AMap HTTPS APIs, transient results only."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac
import json
import logging
import math
import time
import unicodedata

import httpx
from fastapi import HTTPException

from app.config import settings
from app.schemas.share_location import LocationItem, LocationResults
from app.utils.redis_cache import get_redis_client
from app.utils.number_format import format_display_number
from app.utils.share_location_privacy import install_location_log_filters, private_provider_io

logger = logging.getLogger("app.audit.share_location")
BASE_URL = "https://restapi.amap.com"
PATHS = frozenset({"/v3/assistant/coordinate/convert", "/v3/geocode/regeo", "/v3/place/text"})
MAX_RESPONSE_BYTES = 262144
_deadline = ContextVar("share_location_deadline", default=None)
RATE_SCRIPT = """
local minute = redis.call('INCR', KEYS[1])
if minute == 1 then redis.call('EXPIRE', KEYS[1], 60) end
local day = redis.call('INCR', KEYS[2])
if day == 1 then redis.call('EXPIRE', KEYS[2], 86400) end
if minute > 20 or day > 300 then return 0 end
return 1
"""


def _subject(user_id):
    return hmac.new(settings.secret_key.encode(), f"share-location:{user_id}".encode(), hashlib.sha256).hexdigest()[:24]


def admit(user_id):
    if not settings.amap_web_service_key or not settings.amap_web_service_key.get_secret_value().strip():
        raise HTTPException(503, "地点查询暂未配置，请手动填写")
    tag = _subject(user_id)
    try:
        redis = get_redis_client()
        if redis is None:
            raise RuntimeError("rate-limit unavailable")
        allowed = redis.eval(RATE_SCRIPT, 2, f"share-location:minute:{tag}", f"share-location:day:{tag}")
    except Exception:
        raise HTTPException(503, "地点查询暂不可用，请手动填写") from None
    if allowed != 1:
        raise HTTPException(429, "地点查询过于频繁，请稍后重试", headers={"Retry-After": "60"})


@contextmanager
def audited_lookup(user_id, action):
    started = time.monotonic()
    status = "failed"
    error_type = "none"
    token = _deadline.set(started + 10)
    try:
        admit(user_id)
        yield
        status = "ok"
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        _deadline.reset(token)
        logger.info("share_location action=%s subject=%s status=%s error_type=%s duration_ms=%d", action, _subject(user_id), status, error_type, int((time.monotonic() - started) * 1000))


def _strip_trace_headers(request):
    # Sentry instruments Client.send before HTTPX request hooks. Never propagate
    # local tracing / account context to the location provider.
    for header in ("sentry-trace", "baggage", "traceparent", "tracestate"):
        request.headers.pop(header, None)


def _request(path, params):
    if path not in PATHS:
        raise RuntimeError("unsupported provider operation")
    install_location_log_filters()
    deadline = _deadline.get() or time.monotonic() + 6
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("provider budget exhausted")
    with private_provider_io(), httpx.Client(timeout=httpx.Timeout(min(3, remaining), connect=min(2, remaining)), follow_redirects=False, trust_env=False, event_hooks={"request": [_strip_trace_headers]}) as client:
        with client.stream("GET", BASE_URL + path, params={**params, "key": settings.amap_web_service_key.get_secret_value(), "output": "JSON"}) as response:
            if response.status_code != 200:
                raise RuntimeError("provider unavailable")
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if time.monotonic() > deadline or len(data) > MAX_RESPONSE_BYTES:
                    raise RuntimeError("provider response too large")
            if time.monotonic() > deadline:
                raise TimeoutError("provider budget exhausted")
            result = json.loads(data)
            if not isinstance(result, dict) or result.get("status") != "1":
                raise RuntimeError("provider rejected request")
            return result


def _text(value, limit):
    if not isinstance(value, str):
        return ""
    return " ".join("".join(c for c in value if not unicodedata.category(c).startswith("C")).split())[:limit]


def _items(pois):
    if not isinstance(pois, list):
        raise ValueError("invalid provider items")
    items = []
    restaurant_ids = set()
    for poi in pois[:100]:
        if not isinstance(poi, dict):
            continue
        item_id, name = _text(poi.get("id"), 100), _text(poi.get("name"), 120)
        if not item_id or not name or item_id in {item.id for item in items}:
            continue
        raw_distance = poi.get("distance")
        try:
            distance = float(raw_distance) if not isinstance(raw_distance, bool) else None
        except (ValueError, TypeError):
            distance = None
        if distance is not None and (not math.isfinite(distance) or distance < 0):
            distance = None
        address = "".join(_text(poi.get(key), 80) for key in ("pname", "cityname", "adname")) + _text(poi.get("address"), 240)
        items.append(LocationItem(id=item_id, name=name, address=address[:240], label=name[:40], distance_m=format_display_number(distance)))
        # Eligibility uses original precision, never the rounded display value.
        if distance is not None and distance <= 100 and (_text(poi.get("typecode"), 20).startswith("05") or _text(poi.get("type"), 120).startswith("餐饮服务")):
            restaurant_ids.add(item_id)
    return items, restaurant_ids


def nearby(payload):
    converted = _request("/v3/assistant/coordinate/convert", {"locations": f"{payload.longitude:.6f},{payload.latitude:.6f}", "coordsys": "gps"})
    raw = converted.get("locations")
    if not isinstance(raw, str) or len(raw) > 50:
        raise ValueError("invalid converted location")
    lon, lat = map(float, raw.split(","))
    if not math.isfinite(lon) or not math.isfinite(lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError("invalid converted location")
    result = _request("/v3/geocode/regeo", {"location": f"{round(lon, 6)},{round(lat, 6)}", "extensions": "all", "radius": "1000", "poitype": "050000", "homeorcorp": "0"})
    items, restaurant_ids = _items(result["regeocode"]["pois"])
    items.sort(key=lambda item: item.distance_m if item.distance_m is not None else math.inf)
    items = items[:10]
    suggested = next((i.id for i in items if i.id in restaurant_ids), None) if payload.accuracy_m <= 50 else None
    return LocationResults(items=items, suggested_id=suggested)


def search(payload):
    params = {"keywords": payload.keyword, "offset": "10", "page": "1", "extensions": "base"}
    if payload.city:
        params.update(city=payload.city, citylimit="true")
    items, _ = _items(_request("/v3/place/text", params)["pois"])
    return LocationResults(items=items[:10])
