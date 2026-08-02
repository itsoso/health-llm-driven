"""Resolve mutable application data outside the production Git checkout."""

from __future__ import annotations

import os
import re
from pathlib import Path


_BACKEND_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_BACKEND_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
_CHECKOUT_ROOT = Path(__file__).resolve().parents[3]
_PRODUCTION_RUNTIME_DATA_DIR = Path("/var/lib/health-app/runtime")
_PRODUCTION_UPLOAD_DIR = Path("/var/lib/health-app/uploads")
_PRODUCTION_SKILLS_HUB_CACHE_DIR = Path(
    "/var/cache/health-app/skills-hub"
)
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")


def is_production() -> bool:
    """Return whether mutable state must use production-safe locations."""

    return os.environ.get("APP_ENV", "development").strip().lower() in {
        "production",
        "prod",
    }


def configured_runtime_path(value: str, variable_name: str) -> Path:
    """Validate an explicit mutable-state path.

    Explicit paths are always absolute. Production additionally guarantees
    that stale configuration cannot redirect a writer back into the trusted
    Git checkout.
    """

    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{variable_name} must be absolute")
    resolved = path.resolve(strict=False)
    if resolved == Path("/"):
        raise ValueError(f"{variable_name} cannot be the filesystem root")
    checkout = _CHECKOUT_ROOT.resolve(strict=False)
    if is_production() and (
        resolved == checkout or checkout in resolved.parents
    ):
        raise ValueError(
            f"{variable_name} must be outside the Git checkout in production"
        )
    return resolved


def runtime_data_dir() -> Path:
    """Return the root for mutable, non-database application state.

    Production must never write indexes or uploaded registries into the trusted
    Git checkout. Development keeps the historical repo-local default unless an
    explicit absolute override is provided.
    """

    configured = os.environ.get("HEALTH_RUNTIME_DATA_DIR", "").strip()
    if configured:
        return configured_runtime_path(
            configured,
            "HEALTH_RUNTIME_DATA_DIR",
        )

    if is_production():
        return _PRODUCTION_RUNTIME_DATA_DIR
    return _BACKEND_DATA_DIR


def upload_dir() -> Path:
    """Return the shared root for user-uploaded application files."""

    configured = os.environ.get("HEALTH_UPLOAD_DIR", "").strip()
    if configured:
        return configured_runtime_path(configured, "HEALTH_UPLOAD_DIR")
    if is_production():
        return _PRODUCTION_UPLOAD_DIR
    return _BACKEND_UPLOAD_DIR


def skills_hub_cache_dir() -> Path:
    """Return the local cache root for remote Skills Hub content."""

    configured = os.environ.get("HEALTH_SKILLS_CACHE_DIR", "").strip()
    if configured:
        return configured_runtime_path(
            configured,
            "HEALTH_SKILLS_CACHE_DIR",
        )
    if is_production():
        return _PRODUCTION_SKILLS_HUB_CACHE_DIR
    return Path.home() / ".health-skills-cache"


def runtime_data_path(name: str) -> Path:
    """Resolve one fixed child without permitting traversal or nested paths."""

    if (
        not name
        or name in {".", ".."}
        or not _SAFE_COMPONENT.fullmatch(name)
    ):
        raise ValueError("runtime data name must be a single safe path component")
    return runtime_data_dir() / name
