#!/usr/bin/env python3
"""Fail a tooling pytest session that loads the application runtime."""

from __future__ import annotations

import builtins
import importlib
import importlib.machinery
import sys
from pathlib import Path

import pytest


FORBIDDEN_MODULE_PREFIXES = ("app", "main", "backend.app", "backend.main")
FORBIDDEN_FIXTURES = frozenset({"auth_user_and_headers", "client", "db"})
BACKEND_APP_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"
_ORIGINAL_IMPORT = builtins.__import__
_ORIGINAL_IMPORT_MODULE = importlib.import_module
_ORIGINAL_SOURCE_EXEC_MODULE = importlib.machinery.SourceFileLoader.exec_module
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


def _is_backend_app_source(path: object) -> bool:
    try:
        return Path(path).resolve().is_relative_to(BACKEND_APP_ROOT)
    except (OSError, TypeError):
        return False


def _tracking_source_exec_module(loader, module) -> None:
    module_name = getattr(module, "__name__", "")
    source_path = getattr(loader, "path", None)
    if is_forbidden_module_name(module_name) or _is_backend_app_source(source_path):
        _observed_forbidden_modules.add(module_name or str(source_path))
    _ORIGINAL_SOURCE_EXEC_MODULE(loader, module)


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
    importlib.machinery.SourceFileLoader.exec_module = _tracking_source_exec_module


def _restore_import_functions() -> None:
    if builtins.__import__ is _tracking_import:
        builtins.__import__ = _ORIGINAL_IMPORT
    if importlib.import_module is _tracking_import_module:
        importlib.import_module = _ORIGINAL_IMPORT_MODULE
    if importlib.machinery.SourceFileLoader.exec_module is _tracking_source_exec_module:
        importlib.machinery.SourceFileLoader.exec_module = _ORIGINAL_SOURCE_EXEC_MODULE


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


def pytest_unconfigure() -> None:
    _restore_import_functions()
