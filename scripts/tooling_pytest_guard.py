#!/usr/bin/env python3
"""Fail a tooling pytest session that observes application runtime activity."""

from __future__ import annotations

import importlib.machinery
import os
import sys
import threading
from pathlib import Path
from types import CodeType

import pytest


FORBIDDEN_MODULE_PREFIXES = ("app", "main", "backend.app", "backend.main")
FORBIDDEN_FIXTURES = frozenset({"auth_user_and_headers", "client", "db"})
BACKEND_APP_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"
_PROCESS_AUDIT_DISPATCHER_ATTR = "_reva_tooling_pytest_audit_dispatcher_v2"
_AUDIT_DISPATCHER_VERSION = 2
_AUDIT_DISPATCHER_VERIFY_EVENT = "reva.tooling_pytest_guard.verify"
_AUDIT_EVENTS = frozenset({"compile", "exec", "import"})
_REGISTRATION_STATES = frozenset(
    {"unregistered", "installing", "installed", "failed"}
)
_RLOCK_TYPE = type(threading.RLock())
_PATH_OUTSIDE = 0
_PATH_INSIDE = 1
_PATH_UNKNOWN = 2

if "_AUDIT_LISTENER_TOKEN" not in globals():
    _AUDIT_LISTENER_TOKEN = object()
if "_active_observed_modules" not in globals():
    _active_observed_modules: dict[object, set[str]] = {}
if "_SESSION_STATE_LOCK" not in globals():
    _SESSION_STATE_LOCK = threading.RLock()


class _ForbiddenImportObserver:
    def _record(self, module_name: str) -> None:
        _record_forbidden_module(module_name)

    def find_spec(self, fullname, _path=None, _target=None):
        if isinstance(fullname, str) and is_forbidden_module_name(fullname):
            state = _process_audit_dispatcher_state()
            with state["lock"]:
                observers = tuple(state["import_observers"].values())
            for observer in observers:
                observer._record(fullname)
        return None


if "_IMPORT_ATTEMPT_OBSERVER" not in globals():
    _IMPORT_ATTEMPT_OBSERVER = _ForbiddenImportObserver()


def is_forbidden_module_name(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_MODULE_PREFIXES
    )


def _record_forbidden_module(module_name: str) -> None:
    with _SESSION_STATE_LOCK:
        for observed_modules in tuple(_active_observed_modules.values()):
            observed_modules.add(module_name)


def _is_lexically_within(path: Path, root: Path) -> bool:
    try:
        path_parts = path.parts
        root_parts = root.parts
    except (AttributeError, TypeError):
        return False
    return path_parts[: len(root_parts)] == root_parts


def _classify_backend_app_source(
    path: object, root: Path = BACKEND_APP_ROOT
) -> int:
    if isinstance(path, str) and path.startswith("<") and path.endswith(">"):
        return _PATH_OUTSIDE
    try:
        source = Path(path)
        absolute_source = Path(os.path.abspath(source))
    except (OSError, TypeError, ValueError):
        return _PATH_UNKNOWN

    identity_unavailable = False
    source_candidates = [absolute_source]
    try:
        resolved_source = source.resolve()
    except (OSError, RuntimeError):
        identity_unavailable = True
    else:
        if resolved_source != absolute_source:
            source_candidates.append(resolved_source)

    if any(
        _is_lexically_within(candidate, root)
        for candidate in source_candidates
    ):
        return _PATH_INSIDE

    root_depth = len(root.parts)
    for candidate in source_candidates:
        try:
            candidate.stat()
        except OSError:
            identity_unavailable = True
        if len(candidate.parts) >= root_depth:
            peer = Path(*candidate.parts[:root_depth])
            try:
                if os.path.samefile(peer, root):
                    return _PATH_INSIDE
            except OSError:
                identity_unavailable = True

    if not identity_unavailable:
        return _PATH_OUTSIDE
    return _PATH_UNKNOWN


def _is_backend_app_source(
    path: object, root: Path = BACKEND_APP_ROOT
) -> bool:
    return _classify_backend_app_source(path, root) == _PATH_INSIDE


def _loader_module_name(frame) -> str:
    module_name = getattr(frame.f_locals.get("module"), "__name__", "")
    return module_name if isinstance(module_name, str) else ""


def _source_loader_context(
    _code: CodeType | None = None,
) -> tuple[bool, str, object | None]:
    frame = sys._getframe(1)
    for _ in range(16):
        if frame is None:
            break
        if frame.f_code.co_name != "exec_module":
            frame = frame.f_back
            continue
        frame_locals = frame.f_locals
        loader = frame_locals.get("self")
        if "module" in frame_locals and isinstance(
            loader, importlib.machinery.SourceFileLoader
        ):
            return (
                True,
                _loader_module_name(frame),
                getattr(loader, "path", None),
            )
        frame = frame.f_back
    return False, "", None


def _record_loader_source(
    module_name: str,
    loader_path: object | None,
    observed_path: object | None,
) -> None:
    if is_forbidden_module_name(module_name):
        _record_forbidden_module(module_name)
        return
    loader_identity = _classify_backend_app_source(loader_path)
    if loader_identity != _PATH_OUTSIDE:
        _record_forbidden_module(
            module_name or str(loader_path or observed_path or "unknown-source")
        )
        return
    try:
        same_observed_path = os.fspath(loader_path) == os.fspath(observed_path)
    except TypeError:
        same_observed_path = loader_path is observed_path
    if (
        not same_observed_path
        and _classify_backend_app_source(observed_path) == _PATH_INSIDE
    ):
        _record_forbidden_module(module_name or str(observed_path))


def _handle_audit_event(event: str, args: tuple[object, ...]) -> None:
    if event == "import":
        module_name = args[0] if args else ""
        if isinstance(module_name, str) and is_forbidden_module_name(module_name):
            _record_forbidden_module(module_name)
        return
    if event == "compile":
        source_path = args[1] if len(args) > 1 else None
        confirmed, module_name, loader_path = _source_loader_context()
        if confirmed:
            _record_loader_source(module_name, loader_path, source_path)
        return
    if event != "exec" or not args or not isinstance(args[0], CodeType):
        return

    code = args[0]
    confirmed, module_name, loader_path = _source_loader_context(code)
    if confirmed:
        _record_loader_source(module_name, loader_path, code.co_filename)
    elif _is_backend_app_source(code.co_filename):
        _record_forbidden_module(module_name or str(code.co_filename))


def _audit_listener(event: str, args: tuple[object, ...]) -> None:
    if not _active_observed_modules:
        return
    try:
        _handle_audit_event(event, args)
    except Exception as error:
        # An observer failure must fail the session, not the import in progress.
        error_type = type(error)
        _record_forbidden_module(
            f"audit-hook-error:{error_type.__module__}.{error_type.__qualname__}"
        )


def _process_audit_dispatcher_state() -> dict[str, object]:
    candidate = {
        "version": _AUDIT_DISPATCHER_VERSION,
        "dispatcher": None,
        "listeners": {},
        "listener_snapshot": (),
        "import_observers": {},
        "lock": threading.RLock(),
        "registration_state": "unregistered",
    }
    state = sys.__dict__.setdefault(_PROCESS_AUDIT_DISPATCHER_ATTR, candidate)
    if (
        not isinstance(state, dict)
        or state.get("version") != _AUDIT_DISPATCHER_VERSION
        or not isinstance(state.get("listeners"), dict)
        or not isinstance(state.get("lock"), _RLOCK_TYPE)
        or state.get("registration_state") not in _REGISTRATION_STATES
    ):
        raise RuntimeError("incompatible tooling pytest audit dispatcher state")

    if "listener_snapshot" not in state or "import_observers" not in state:
        lock = state["lock"]
        with lock:
            state.setdefault(
                "listener_snapshot", tuple(state["listeners"].values())
            )
            state.setdefault("import_observers", {})
    if (
        not isinstance(state.get("listener_snapshot"), tuple)
        or not isinstance(state.get("import_observers"), dict)
    ):
        raise RuntimeError("incompatible tooling pytest audit dispatcher state")
    return state


def _validate_audit_dispatcher_state_locked(
    state: dict[str, object],
) -> tuple[str, object]:
    dispatcher = state.get("dispatcher")
    registration_state = state["registration_state"]
    if (
        registration_state == "unregistered"
        and dispatcher is not None
        or registration_state in {"installing", "installed"}
        and not callable(dispatcher)
    ):
        raise RuntimeError("incompatible tooling pytest audit dispatcher state")
    return registration_state, dispatcher


def _refresh_listener_snapshot(state: dict[str, object]) -> None:
    state["listener_snapshot"] = tuple(state["listeners"].values())


def _fail_registration(
    state: dict[str, object], message: str, error: BaseException | None = None
) -> None:
    state["registration_state"] = "failed"
    state["registration_error"] = message
    if error is None:
        raise RuntimeError(message)
    raise RuntimeError(message) from error


def _verify_audit_dispatcher(
    state: dict[str, object], dispatcher: object
) -> None:
    nonce = object()
    receipt: dict[str, object] = {}
    try:
        sys.audit(_AUDIT_DISPATCHER_VERIFY_EVENT, state, nonce, receipt)
    except BaseException as error:
        _fail_registration(
            state,
            "tooling pytest audit dispatcher registration was denied "
            "or could not be verified",
            error,
        )
    if (
        receipt.get("nonce") is not nonce
        or receipt.get("dispatcher") is not dispatcher
    ):
        _fail_registration(
            state,
            "tooling pytest audit dispatcher registration was denied "
            "or could not be verified",
        )


def _register_audit_listener() -> None:
    state = _process_audit_dispatcher_state()
    lock = state["lock"]
    with lock:
        registration_state, dispatcher = _validate_audit_dispatcher_state_locked(
            state
        )
        if registration_state == "failed":
            raise RuntimeError(str(state.get("registration_error")))
        if registration_state == "installing":
            _fail_registration(
                state,
                "tooling pytest audit dispatcher registration re-entered "
                "during installation",
            )
        if registration_state == "unregistered":

            def dispatch(event, args):
                if event == _AUDIT_DISPATCHER_VERIFY_EVENT:
                    if (
                        len(args) == 3
                        and args[0] is state
                        and isinstance(args[2], dict)
                    ):
                        args[2]["nonce"] = args[1]
                        args[2]["dispatcher"] = dispatch
                    return
                listeners = state["listener_snapshot"]
                if not listeners:
                    return
                if event not in _AUDIT_EVENTS:
                    return
                for listener in listeners:
                    listener(event, args)

            state["dispatcher"] = dispatch
            state["registration_state"] = "installing"
            try:
                sys.addaudithook(dispatch)
            except BaseException as error:
                _fail_registration(
                    state,
                    "tooling pytest audit dispatcher registration was denied",
                    error,
                )
        dispatcher = state["dispatcher"]
        if not callable(dispatcher):
            _fail_registration(
                state, "tooling pytest audit dispatcher state is incompatible"
            )
        _verify_audit_dispatcher(state, dispatcher)
        state["registration_state"] = "installed"
        state["listeners"][_AUDIT_LISTENER_TOKEN] = _audit_listener
        _refresh_listener_snapshot(state)


def _unregister_audit_listener() -> None:
    state = getattr(sys, _PROCESS_AUDIT_DISPATCHER_ATTR, None)
    if isinstance(state, dict):
        listeners = state.get("listeners")
        lock = state.get("lock")
        if isinstance(listeners, dict) and isinstance(lock, _RLOCK_TYPE):
            with lock:
                listeners.pop(_AUDIT_LISTENER_TOKEN, None)
                _refresh_listener_snapshot(state)


def _install_import_attempt_observer() -> None:
    state = _process_audit_dispatcher_state()
    with state["lock"]:
        state["import_observers"][_AUDIT_LISTENER_TOKEN] = (
            _IMPORT_ATTEMPT_OBSERVER
        )
        if not any(item is _IMPORT_ATTEMPT_OBSERVER for item in sys.meta_path):
            sys.meta_path.insert(0, _IMPORT_ATTEMPT_OBSERVER)


def _import_attempt_observer_is_intact() -> bool:
    state = _process_audit_dispatcher_state()
    with state["lock"]:
        registered = state["import_observers"]
        if registered.get(_AUDIT_LISTENER_TOKEN) is not _IMPORT_ATTEMPT_OBSERVER:
            return False
        observers = tuple(registered.values())
        if len({id(observer) for observer in observers}) != len(observers):
            return False
        if not sys.meta_path or not any(
            sys.meta_path[0] is observer for observer in observers
        ):
            return False
        return all(
            sum(item is observer for item in sys.meta_path) == 1
            for observer in observers
        )


def _remove_import_attempt_observer() -> None:
    state = getattr(sys, _PROCESS_AUDIT_DISPATCHER_ATTR, None)
    lock = state.get("lock") if isinstance(state, dict) else None
    if isinstance(lock, _RLOCK_TYPE):
        with lock:
            import_observers = state.get("import_observers")
            if isinstance(import_observers, dict):
                import_observers.pop(_AUDIT_LISTENER_TOKEN, None)
            sys.meta_path[:] = [
                item for item in sys.meta_path if item is not _IMPORT_ATTEMPT_OBSERVER
            ]
        return
    sys.meta_path[:] = [
        item for item in sys.meta_path if item is not _IMPORT_ATTEMPT_OBSERVER
    ]


def _observe_current_modules() -> None:
    for module_name in tuple(sys.modules):
        if is_forbidden_module_name(module_name):
            _record_forbidden_module(module_name)


def loaded_forbidden_module_names(config: object) -> tuple[str, ...]:
    try:
        observer_is_intact = _import_attempt_observer_is_intact()
    except Exception as error:
        error_type = type(error)
        _record_forbidden_module(
            "import-observer-error:"
            f"{error_type.__module__}.{error_type.__qualname__}"
        )
    else:
        if not observer_is_intact:
            _record_forbidden_module("import-observer-error:integrity")
    _observe_current_modules()
    with _SESSION_STATE_LOCK:
        return tuple(sorted(_active_observed_modules.get(config, ())))


def pytest_sessionstart(session) -> None:
    config = session.config
    with _SESSION_STATE_LOCK:
        _active_observed_modules[config] = set()
        try:
            config.add_cleanup(lambda: _finish_config(config))
            _register_audit_listener()
            _install_import_attempt_observer()
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
    with _SESSION_STATE_LOCK:
        _active_observed_modules.pop(config, None)
        if not _active_observed_modules:
            _remove_import_attempt_observer()
            _unregister_audit_listener()
