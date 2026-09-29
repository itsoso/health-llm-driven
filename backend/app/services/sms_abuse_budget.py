"""Atomic, shared, privacy-preserving admission before paid SMS delivery."""
import hashlib
import hmac
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)


class SmsQuotaExceeded(ValueError):
    pass


class SmsQuotaUnavailable(RuntimeError):
    pass


_RESERVE = """
for i, key in ipairs(KEYS) do
    if tonumber(redis.call('GET', key) or '0') >= tonumber(ARGV[2*i-1]) then
        return 0
    end
end
for i, key in ipairs(KEYS) do
    local used = redis.call('INCR', key)
    if used == 1 then redis.call('EXPIRE', key, ARGV[2*i]) end
end
return 1
"""


def reserve_sms_delivery(phone: str, request_ip: str | None) -> None:
    def digest(value: str) -> str:
        return hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()

    phone_key = digest(phone)
    ip_key = digest(request_ip or "unknown")
    buckets = [
        ("auth:sms:global:day", settings.auth_sms_global_daily_limit, 86400),
        (f"auth:sms:phone:{phone_key}:day", settings.auth_sms_phone_daily_limit, 86400),
        (f"auth:sms:ip:{ip_key}:hour", settings.auth_sms_ip_hourly_limit, 3600),
    ]
    if settings.auth_phone_code_resend_seconds > 0:
        buckets.append((f"auth:sms:phone:{phone_key}:cooldown", 1,
                        settings.auth_phone_code_resend_seconds))
    try:
        with redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2) as client:
            result = client.eval(_RESERVE, len(buckets),
                                 *(key for key, _, _ in buckets),
                                 *(value for _, cap, ttl in buckets for value in (cap, ttl)))
    except redis.RedisError:
        logger.error("SMS quota storage unavailable; delivery denied")
        raise SmsQuotaUnavailable("短信服务暂时不可用，请稍后重试") from None
    if result == 0:
        raise SmsQuotaExceeded("验证码发送额度已达上限，请稍后再试")
    if result != 1:
        logger.error("SMS quota storage returned an invalid acknowledgement")
        raise SmsQuotaUnavailable("短信服务暂时不可用，请稍后重试")
