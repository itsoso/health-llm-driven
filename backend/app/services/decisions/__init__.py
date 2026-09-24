"""Typed decisions; new non-SystemOne backends implement DecisionProvider."""

from .config import DecisionError, configured_decision
from .systemone import (
    DecisionProvider,
    DecisionRequest,
    DecisionResult,
    SystemOneProvider,
)


def provider_from_settings() -> DecisionProvider:
    return SystemOneProvider(configured_decision())


__all__ = [
    "DecisionError",
    "DecisionProvider",
    "DecisionRequest",
    "DecisionResult",
    "SystemOneProvider",
    "provider_from_settings",
]
