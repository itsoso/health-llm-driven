#!/usr/bin/env python3
"""Fail a tooling pytest session that observes application runtime activity."""

from __future__ import annotations

import importlib.machinery
import os
import sys
from pathlib import Path
from types import CodeType

import pytest


FORBIDDEN_MODULE_PREFIXES = ("app", "main", "backend.app", "backend.main")
FORBIDDEN_FIXTURES = frozenset({"auth_user_and_headers", "client", "db"})
BACKEND_APP_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"
_PROCESS_AUDIT_DISPATCHER_ATTR = "_reva_tooling_pytest_audit_dispatcher_v1"
_AUDIT_DISPATCHER_VERSION = 1
_AUDIT_DISPATCHER_VERIFY_EVENT = "reva.tooling_pytest_guard.verify"
_AUDIT_LISTENER_TOKEN = object()
_active_observed_modules: dict[object, set[str]] = {}


def is_forbidden_module_name(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_MODULE_PREFIXES
    )


def _record_forbidden_module(module_name: str) -> None:
    for observed_modules in tuple(_active_observed_modules.values()):
        observed_modules.add(module_name)


def _is_lexically_within(path: Path, root: Path) -> bool:
    try:
        path_parts = tuple(part.casefold() for part in path.parts)
        root_parts = tuple(part.casefold() for part in root.parts)
    except (AttributeError, TypeError):
        return False
    return path_parts[: len(root_parts)] == root_parts


def _is_backend_app_source(
    path: object, root: Path = BACKEND_APP_ROOT
) -> bool:
    if isinstance(path, str) and path.startswith("<") and path.endswith(">"):
        return False
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
                if os.path.samefile(ancestor, root):
                    return True
            except OSError:
                identity_unavailable = True

    if not identity_unavailable:
        return False
    return any(
        _is_lexically_within(candidate, root)
        for candidate in source_candidates
    )


def _source_loader_context(code: CodeType) -> tuple[str, object | None]:
    frame = sys._getframe(1)
    for _ in range(16):
        if frame is None:
            break
        loader = frame.f_locals.get("self")
        if (
            frame.f_locals.get("code") is code
            and isinstance(loader, importlib.machinery.SourceFileLoader)
        ):
            module = frame.f_locals.get("module")
            module_name = getattr(module, "__name__", "")
            return (
                module_name if isinstance(module_name, str) else "",
                getattr(loader, "path", None),
            )
        frame = frame.f_back
    return "", None


def _handle_audit_event(event: str, args: tuple[object, ...]) -> None:
    if event == "import":
        module_name = args[0] if args else ""
        if isinstance(module_name, str) and is_forbidden_module_name(module_name):
            _record_forbidden_module(module_name)
        return
    if event != "exec" or not args or not isinstance(args[0], CodeType):
        return

    code = args[0]
    module_name, loader_path = _source_loader_context(code)
    if is_forbidden_module_name(module_name):
        _record_forbidden_module(module_name)
    source_paths = (code.co_filename, loader_path)
    if any(
        path is not None and _is_backend_app_source(path)
        for path in source_paths
    ):
        _record_forbidden_module(module_name or str(code.co_filename))


def _audit_listener(event: str, args: tuple[object, ...]) -> None:
    if not _active_observed_modules:
        return
    try:
        _handle_audit_event(event, args)
    except BaseException as error:  # noqa: BLE001
        # An observer failure must fail the session, not the import in progress.
        error_type = type(error)
        _record_forbidden_module(
            f"audit-hook-error:{error_type.__module__}.{error_type.__qualname__}"
        )


def _process_audit_dispatcher_state() -> dict[str, object]:
    state = getattr(sys, _PROCESS_AUDIT_DISPATCHER_ATTR, None)
    if state is None:
        state = {
            "version": _AUDIT_DISPATCHER_VERSION,
            "dispatcher": None,
            "listeners": {},
        }
        setattr(sys, _PROCESS_AUDIT_DISPATCHER_ATTR, state)
    if (
        not isinstance(state, dict)
        or state.get("version") != _AUDIT_DISPATCHER_VERSION
        or not isinstance(state.get("listeners"), dict)
    ):
        raise RuntimeError("incompatible tooling pytest audit dispatcher state")
    return state


def _register_audit_listener() -> None:
    state = _process_audit_dispatcher_state()
    registration_error = state.get("registration_error")
    if registration_error is not None:
        raise RuntimeError(str(registration_error))
    listeners = state["listeners"]
    if state["dispatcher"] is None:
        def dispatch(event, args):
            if event == _AUDIT_DISPATCHER_VERIFY_EVENT:
                if args and args[0] is state:
                    state["verified"] = True
                return
            if event != "import" and event != "exec":
                return
            for listener in tuple(state["listeners"].values()):
                listener(event, args)

        state["dispatcher"] = dispatch
        state["verified"] = False
        try:
            sys.addaudithook(dispatch)
            sys.audit(_AUDIT_DISPATCHER_VERIFY_EVENT, state)
        except BaseException as error:
            message = (
                "tooling pytest audit dispatcher registration was denied "
                "or could not be verified"
            )
            state["registration_error"] = message
            raise RuntimeError(message) from error
        if not state.pop("verified", False):
            message = "tooling pytest audit dispatcher registration was denied"
            state["registration_error"] = message
            raise RuntimeError(message)
    listeners[_AUDIT_LISTENER_TOKEN] = _audit_listener


def _unregister_audit_listener() -> None:
    state = getattr(sys, _PROCESS_AUDIT_DISPATCHER_ATTR, None)
    if isinstance(state, dict):
        listeners = state.get("listeners")
        if isinstance(listeners, dict):
            listeners.pop(_AUDIT_LISTENER_TOKEN, None)


def _observe_current_modules() -> None:
    for module_name in sys.modules:
        if is_forbidden_module_name(module_name):
            _record_forbidden_module(module_name)


def loaded_forbidden_module_names(config: object) -> tuple[str, ...]:
    _observe_current_modules()
    return tuple(sorted(_active_observed_modules.get(config, ())))


def pytest_sessionstart(session) -> None:
    config = session.config
    _active_observed_modules[config] = set()
    try:
        config.add_cleanup(lambda: _finish_config(config))
        _register_audit_listener()
    except BaseException:
        _finish_config(config)
        raise
    _observe_current_modules()


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
            f"application runtime imports or source execution observed: "
            f"{', '.join(forbidden)}"
        )


def _finish_config(config: object) -> None:
    _active_observed_modules.pop(config, None)
    if not _active_observed_modules:
        _unregister_audit_listener()
