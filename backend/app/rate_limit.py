"""One shared limiter for middleware and all HTTP route quotas."""
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings

# Tests use process-local storage; production never falls back when Redis fails.
_is_production = (settings.app_env or "").strip().lower() == "production"
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url if _is_production else "memory://",
    storage_options={"socket_connect_timeout": 2, "socket_timeout": 2} if _is_production else {},
    default_limits=["200/minute"],
    swallow_errors=False,
    in_memory_fallback_enabled=False,
)
