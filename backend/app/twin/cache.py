"""
Twin 缓存层 —— 简单版。

MVP 设计：单 key 60 秒 TTL（见 TWIN_CACHE_TTL_SECONDS，同步后希望尽快看到新数据），
命中率优先于精细度。下一阶段 (Phase 0.5) 再做分层 TTL：
  - physiological 短 TTL   (Garmin 高频更新)
  - labs/genetic  24 h     (很少变)
  - environment   1 h      (天气/AQI)
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


TWIN_CACHE_TTL_SECONDS = 60  # 1 min（用户同步 Garmin 后希望立即看到最新数据）
_KEY_PREFIX = "twin:v2:"


def _key(user_id: int) -> str:
    return f"{_KEY_PREFIX}{user_id}"


def _json_default(o: Any) -> Any:
    """datetime / date / Pydantic 对象的 JSON 序列化兜底。"""
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    if hasattr(o, "dict"):
        return o.dict()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def get_cached_twin(user_id: int) -> Optional[Dict[str, Any]]:
    """命中返回 dict；未命中或 Redis 不可用返回 None。"""
    try:
        from app.utils.redis_cache import get_redis_client

        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(_key(user_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"[twin.cache] get 失败: {e}")
        return None


def set_cached_twin(user_id: int, twin_json: Dict[str, Any], ttl: int = TWIN_CACHE_TTL_SECONDS) -> bool:
    """写缓存；失败不报错。"""
    try:
        from app.utils.redis_cache import get_redis_client

        client = get_redis_client()
        if client is None:
            return False
        client.setex(_key(user_id), ttl, json.dumps(twin_json, default=_json_default))
        return True
    except Exception as e:
        logger.warning(f"[twin.cache] set 失败: {e}")
        return False


def invalidate_twin(user_id: int) -> None:
    """用户数据变化后清除 Twin 及所有由 Twin 派生的安全报告。"""
    try:
        from app.utils.redis_cache import get_redis_client

        client = get_redis_client()
        if client is not None:
            client.delete(_key(user_id))
    except Exception as e:
        logger.warning(f"[twin.cache] invalidate 失败: {e}")

    try:
        from app.agents.safety_guardian.cache import invalidate_safety_report_cache

        invalidate_safety_report_cache(user_id)
    except Exception as e:
        logger.warning(f"[twin.cache] safety invalidate 失败: {e}")

    # rank7: this is the write choke every mutation route must call to keep the twin
    # fresh — active writes (exams / labs / genetics / CGM / meds / symptoms / agent
    # writes) AND passive syncs (device/healthkit/garmin/cgm ingest, daily_health /
    # weight / blood_pressure / medication / supplement writers), all wired in the
    # same rank7 change. So it is also where pre-generated starter answers must be
    # dropped fail-closed: ANY write since generation → discard pregen → tap falls
    # through to a live turn (a pre-generated medical answer must NEVER serve on
    # changed data). invalidate_pregen is a no-op when the flag is off (touches Redis
    # zero times); lazy + guarded so it can never break twin invalidation.
    try:
        from app.services.starter_pregen import invalidate_pregen

        invalidate_pregen(user_id)
    except Exception:  # noqa: BLE001 — pregen invalidation is best-effort
        pass
