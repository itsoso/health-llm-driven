"""Server-owned decision configuration and recipient identity."""

from dataclasses import dataclass
import logging
from urllib.parse import urlsplit

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class DecisionError(RuntimeError):
    """Safe error code only; never includes payloads, credentials or responses."""


@dataclass(frozen=True)
class DecisionConfig:
    provider: str
    endpoint: str
    model: str
    local: bool
    recipient_name: str


def configured_decision() -> DecisionConfig:
    provider = settings.decision_provider
    defaults = {
        "jev": ("https://api.typesafe.ai/v1", "jev-1.13.0"),
        "laya": ("http://127.0.0.1:8092/v1", "multilingual"),
        "systemone": ("", ""),
    }
    if provider not in defaults:
        raise DecisionError("configuration")
    base, model = defaults[provider]
    base = (settings.decision_base_url or base).rstrip("/")
    model = settings.decision_model or model
    endpoint = base if base.endswith("/systemone") else base + "/systemone"
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        raise DecisionError("configuration") from None
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or not model
        or len(model) > 128
        or any(c.isspace() for c in model)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "?" in base
        or "#" in base
        or parsed.scheme not in {"http", "https"}
        or (not local and parsed.scheme != "https")
        or (port is not None and port < 1)
    ):
        raise DecisionError("configuration")
    try:
        endpoint = str(httpx.URL(endpoint))
    except httpx.InvalidURL:
        raise DecisionError("configuration") from None
    official = endpoint == "https://api.typesafe.ai/v1/systemone"
    name = settings.decision_recipient_name or (
        "TypeSafe AI（Jev 决策服务）" if official else ""
    )
    if not local and (not name.strip() or len(name) > 160):
        raise DecisionError("configuration")
    return DecisionConfig(provider, endpoint, model, local, name)


def decision_disclosure() -> dict | None:
    if settings.decision_mode == "off":
        return None
    try:
        cfg = configured_decision()
    except DecisionError:
        # Invalid optional configuration must not break existing consent flows.
        # The decision factory independently rejects this config before any I/O.
        logger.warning("decision_configuration_invalid; decision recipient disabled")
        return None
    if cfg.local:
        return None
    return {
        "id": "decision-service",
        "name": cfg.recipient_name,
        "purpose": f"处理本次对话文本，判断回答复杂度和所需能力。接收地址：{cfg.endpoint}",
    }
