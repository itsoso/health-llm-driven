"""Isolated pytest policy for the dormant Health Day shadow subtree."""

from __future__ import annotations

import builtins
import importlib
import socket
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest


_PARENT_CONFTEST = Path(__file__).parents[1] / "tests" / "conftest.py"
_PARENT_AUTOUSE_FIXTURES = frozenset({"_isolate_twin_cache", "_noop_twin_cache"})
_DENIED_MODULE_PREFIXES = (
    "app.database",
    "app.config",
    "app.twin.cache",
    "app.utils.redis_cache",
    "app.services.llm",
    "app.services.notification",
    "redis",
    "openai",
)


def _is_denied_module(name: str) -> bool:
    return any(
        name == prefix or name.startswith(f"{prefix}.")
        for prefix in _DENIED_MODULE_PREFIXES
    )


def _absolute_import_base(
    name: str,
    import_globals: dict[str, object] | None,
    level: int,
) -> str:
    if level == 0:
        return name
    package = import_globals.get("__package__") if import_globals else None
    if not isinstance(package, str) or not package:
        raise RuntimeError("health_day_shadow_relative_import_package_required")
    return resolve_name(f"{'.' * level}{name}", package)


def _import_candidates(base: str, fromlist: object) -> tuple[str, ...]:
    candidates = [base]
    if not fromlist:
        return tuple(candidates)
    if not isinstance(fromlist, (tuple, list)):
        raise RuntimeError("health_day_shadow_import_fromlist_invalid")
    for member in fromlist:
        if not isinstance(member, str):
            raise RuntimeError("health_day_shadow_import_fromlist_invalid")
        if member and member != "*":
            candidates.append(f"{base}.{member}")
    return tuple(candidates)


def _assert_import_candidates_allowed(
    name: str,
    import_globals: dict[str, object] | None,
    fromlist: object,
    level: int,
) -> None:
    absolute_base = _absolute_import_base(name, import_globals, level)
    for candidate in _import_candidates(absolute_base, fromlist):
        if _is_denied_module(candidate):
            raise RuntimeError(f"health_day_shadow_ambient_import_denied:{candidate}")


def _plugin_paths(config: pytest.Config) -> frozenset[Path]:
    return frozenset(
        Path(path).resolve()
        for _name, plugin in config.pluginmanager.list_name_plugin()
        if (path := getattr(plugin, "__file__", None))
    )


def _assert_parent_plugin_is_absent(config: pytest.Config) -> None:
    if _PARENT_CONFTEST.resolve() in _plugin_paths(config):
        raise pytest.UsageError("health_day_shadow_parent_conftest_loaded")


def pytest_sessionstart(session: pytest.Session) -> None:
    _assert_parent_plugin_is_absent(session.config)


@pytest.fixture(autouse=True)
def _health_day_shadow_default_deny(monkeypatch, request):
    """Fail closed on ambient integrations before every Phase 1a test."""

    _assert_parent_plugin_is_absent(request.config)
    fixture_registry = request._fixturemanager._arg2fixturedefs
    loaded_parent_fixtures = _PARENT_AUTOUSE_FIXTURES & fixture_registry.keys()
    if loaded_parent_fixtures:
        names = ",".join(sorted(loaded_parent_fixtures))
        raise RuntimeError(f"health_day_shadow_parent_fixture_loaded:{names}")

    loaded_denied = tuple(name for name in sys.modules if _is_denied_module(name))
    if loaded_denied:
        raise RuntimeError(
            "health_day_shadow_ambient_global_access_loaded:"
            + ",".join(sorted(loaded_denied))
        )

    def deny_network(*_args, **_kwargs):
        raise RuntimeError("health_day_shadow_external_network_denied")

    original_import = builtins.__import__
    original_importlib_import = importlib.__import__
    original_import_module = importlib.import_module

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        _assert_import_candidates_allowed(name, globals, fromlist, level)
        return original_import(name, globals, locals, fromlist, level)

    def guarded_importlib_import(
        name,
        globals=None,
        locals=None,
        fromlist=(),
        level=0,
    ):
        _assert_import_candidates_allowed(name, globals, fromlist, level)
        return original_importlib_import(name, globals, locals, fromlist, level)

    def guarded_import_module(name, package=None):
        absolute_name = resolve_name(name, package) if name.startswith(".") else name
        if _is_denied_module(absolute_name):
            raise RuntimeError(
                f"health_day_shadow_ambient_import_denied:{absolute_name}"
            )
        return original_import_module(name, package)

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(socket.socket, "sendto", deny_network)
    if hasattr(socket.socket, "sendmsg"):
        monkeypatch.setattr(socket.socket, "sendmsg", deny_network)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "__import__", guarded_importlib_import)
    monkeypatch.setattr(importlib, "import_module", guarded_import_module)
    yield
