#!/usr/bin/env python3
"""Fail a tooling pytest session that loads the application runtime."""

from __future__ import annotations

import builtins
import importlib
import importlib.machinery
import os
import sys
from pathlib import Path

import pytest


FORBIDDEN_MODULE_PREFIXES = ("app", "main", "backend.app", "backend.main")
FORBIDDEN_FIXTURES = frozenset({"auth_user_and_headers", "client", "db"})
BACKEND_APP_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"
_delegated_import = builtins.__import__
_delegated_import_module = importlib.import_module
_delegated_source_exec_module = importlib.machinery.SourceFileLoader.exec_module
_active_observed_modules: dict[object, set[str]] = {}


def is_forbidden_module_name(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_MODULE_PREFIXES
    )


def _record_forbidden_module(module_name: str) -> None:
    for observed_modules in tuple(_active_observed_modules.values()):
        observed_modules.add(module_name)


def _record_loaded_module(module_name: str) -> None:
    if is_forbidden_module_name(module_name) and module_name in sys.modules:
        _record_forbidden_module(module_name)


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
    module = _delegated_import(name, globals, locals, fromlist, level)
    absolute_name = _absolute_import_name(name, globals, level)
    _record_loaded_module(absolute_name)
    for imported_name in fromlist or ():
        if imported_name != "*":
            _record_loaded_module(f"{absolute_name}.{imported_name}")
    _record_loaded_module(getattr(module, "__name__", ""))
    return module


def _tracking_import_module(name: str, package: str | None = None):
    module = _delegated_import_module(name, package)
    _record_loaded_module(module.__name__)
    return module


def _is_lexically_within(path: Path, root: Path) -> bool:
    try:
        path_parts = tuple(part.casefold() for part in path.parts)
        root_parts = tuple(part.casefold() for part in root.parts)
    except (AttributeError, TypeError):
        return False
    return path_parts[: len(root_parts)] == root_parts


def _is_backend_app_source(path: object) -> bool:
    try:
        source = Path(path)
        absolute_source = Path(os.path.abspath(source))
    except (OSError, TypeError, ValueError):
        return False

    identity_unavailable = False
    source_candidates = [absolute_source]
    try:
        resolved_source = source.resolve()
    except (OSError, RuntimeError):
        identity_unavailable = True
    else:
        if resolved_source != absolute_source:
            source_candidates.append(resolved_source)

    for candidate in source_candidates:
        for ancestor in (candidate, *candidate.parents):
            try:
                if os.path.samefile(ancestor, BACKEND_APP_ROOT):
                    return True
            except OSError:
                identity_unavailable = True

    if not identity_unavailable:
        return False
    return any(
        _is_lexically_within(candidate, BACKEND_APP_ROOT)
        for candidate in source_candidates
    )


def _tracking_source_exec_module(loader, module) -> None:
    module_name = getattr(module, "__name__", "")
    source_path = getattr(loader, "path", None)
    if is_forbidden_module_name(module_name) or _is_backend_app_source(source_path):
        _record_forbidden_module(module_name or str(source_path))
    _delegated_source_exec_module(loader, module)


def _observe_current_modules() -> None:
    for module_name in sys.modules:
        if is_forbidden_module_name(module_name):
            _record_forbidden_module(module_name)


def loaded_forbidden_module_names(config: object) -> tuple[str, ...]:
    _observe_current_modules()
    return tuple(sorted(_active_observed_modules.get(config, ())))


def pytest_sessionstart(session) -> None:
    install_hooks = not _active_observed_modules
    _active_observed_modules[session.config] = set()
    if install_hooks:
        global _delegated_import
        global _delegated_import_module
        global _delegated_source_exec_module
        _delegated_import = builtins.__import__
        _delegated_import_module = importlib.import_module
        _delegated_source_exec_module = (
            importlib.machinery.SourceFileLoader.exec_module
        )
        builtins.__import__ = _tracking_import
        importlib.import_module = _tracking_import_module
        importlib.machinery.SourceFileLoader.exec_module = _tracking_source_exec_module
    _observe_current_modules()


def _restore_import_functions() -> None:
    if builtins.__import__ is _tracking_import:
        builtins.__import__ = _delegated_import
    if importlib.import_module is _tracking_import_module:
        importlib.import_module = _delegated_import_module
    if importlib.machinery.SourceFileLoader.exec_module is _tracking_source_exec_module:
        importlib.machinery.SourceFileLoader.exec_module = (
            _delegated_source_exec_module
        )


def pytest_sessionfinish(session) -> None:
    forbidden = loaded_forbidden_module_names(session.config)
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


def _finish_config(config: object) -> None:
    _active_observed_modules.pop(config, None)
    if not _active_observed_modules:
        _restore_import_functions()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_unconfigure(config):
    try:
        yield
    finally:
        _finish_config(config)
