"""Do not send ephemeral precise-location lookups to logs or Sentry.

Sentry hooks are installed for both events and transactions before export. They
drop this narrow request surface, including stack locals/body and child spans.
Other request telemetry remains unchanged. Never log upstream exception objects.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import logging

_provider_io = ContextVar("share_location_provider_io", default=False)


@contextmanager
def private_provider_io():
    token = _provider_io.set(True)
    try:
        yield
    finally:
        _provider_io.reset(token)


class _PrivateLocationFilter(logging.Filter):
    def filter(self, record):
        # httpcore's DEBUG headers/body can contain both URL and provider data.
        if _provider_io.get():
            return False
        return "restapi.amap.com" not in record.getMessage()


def install_location_log_filters():
    for name in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy", "sentry_sdk.errors"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, _PrivateLocationFilter) for f in logger.filters):
            logger.addFilter(_PrivateLocationFilter())


def _contains_location(value):
    if isinstance(value, str):
        return "/share-location/" in value or "restapi.amap.com" in value or "app.api.share_location" in value
    if isinstance(value, dict):
        return any(_contains_location(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_location(v) for v in value)
    return False


def protect_location_event(event, hint):
    """before_send / before_send_transaction; payloads never reach exporter."""
    if _provider_io.get() or _contains_location(event):
        return None
    return event
