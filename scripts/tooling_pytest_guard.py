#!/usr/bin/env python3
"""Fail a tooling pytest session that loads the application runtime."""

from __future__ import annotations

import builtins
import importlib
import sys

import pytest


FORBIDDEN_MODULE_PREFIXES = ("app", "main", "backend.app", "backend.main")
FORBIDDEN_FIXTURES = frozenset({"auth_user_and_headers", "client", "db"})
_ORIGINAL_IMPORT = builtins.__import__
_ORIGINAL_IMPORT_MODULE = importlib.import_module
_observed_forbidden_modules: set[str] = set()


def is_forbidden_module_name(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_MODULE_PREFIXES
    )


def _record_loaded_module(module_name: str) -> None:
    if is_forbidden_module_name(module_name) and module_name in sys.modules:
        _observed_forbidden_modules.add(module_name)


def _absolute_import_name(
    name: str, globals_: dict | None, level: int
) -> str:
    if level == 0:
        return name
    package = globals_.get("__package__") if globals_ else None
    if not package:
        return name
    return importlib.util.resolve_name(f"{'.' * level}{name}", package)


def _tracking_import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    absolute_name = _absolute_import_name(name, globals, level)
    _record_loaded_module(absolute_name)
    for imported_name in fromlist or ():
        if imported_name != "*":
            _record_loaded_module(f"{absolute_name}.{imported_name}")
    _record_loaded_module(getattr(module, "__name__", ""))
    return module


def _tracking_import_module(name: str, package: str | None = None):
    module = _ORIGINAL_IMPORT_MODULE(name, package)
    _record_loaded_module(module.__name__)
    return module


def _observe_current_modules() -> None:
    _observed_forbidden_modules.update(
        name for name in sys.modules if is_forbidden_module_name(name)
    )


def loaded_forbidden_module_names() -> tuple[str, ...]:
    _observe_current_modules()
    return tuple(sorted(_observed_forbidden_modules))


def pytest_sessionstart() -> None:
    _observed_forbidden_modules.clear()
    _observe_current_modules()
    builtins.__import__ = _tracking_import
    importlib.import_module = _tracking_import_module


def _restore_import_functions() -> None:
    if builtins.__import__ is _tracking_import:
        builtins.__import__ = _ORIGINAL_IMPORT
    if importlib.import_module is _tracking_import_module:
        importlib.import_module = _ORIGINAL_IMPORT_MODULE


def pytest_sessionfinish(session) -> None:
    forbidden = loaded_forbidden_module_names()
    _restore_import_functions()
    if not forbidden:
        return
    if session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal is not None:
        terminal.write_sep("=", "tooling pytest guard")
        terminal.write_line(
            f"application runtime modules loaded: {', '.join(forbidden)}"
        )
