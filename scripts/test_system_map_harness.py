from __future__ import annotations

import importlib
import importlib.util
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SYSTEM_MAP_ENTRYPOINTS = (
    "check_system_map",
    "check_doc_drift",
    "dump_system_map",
    "system_map_context",
)


def _import_helper_key() -> str:
    digest = 14695981039346656037
    for byte in os.fsencode(str(ROOT)):
        digest = ((digest ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return f"_reva_system_map_imports_{digest:016x}"


def _load_entrypoint(entrypoint: str):
    path = ROOT / "scripts" / f"{entrypoint}.py"
    assert path.exists()
    spec = importlib.util.spec_from_file_location(
        f"_system_map_entrypoint_probe_{entrypoint}",
        path,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
    return module


def _load_checker():
    return _load_entrypoint("check_system_map")


def test_local_harness_is_pinned_and_uses_its_venv() -> None:
    requirements = ROOT / "scripts" / "system-map-requirements.txt"
    wrapper = ROOT / "scripts" / "system-map-check.sh"

    assert requirements.read_text(encoding="utf-8") == "jsonschema==4.23.0\n"
    source = wrapper.read_text(encoding="utf-8")
    assert "command -v python3.12" in source
    assert '"$PYTHON_BIN" -m venv "$VENV_DIR"' in source
    assert '"$VENV_PYTHON" -m pip install' in source
    assert 'exec "$VENV_PYTHON" "$ROOT/scripts/check_system_map.py"' in source
    assert "python3 scripts/check_system_map.py" not in source
    assert ".venv/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("entrypoint", SYSTEM_MAP_ENTRYPOINTS)
@pytest.mark.parametrize("caller_has_scripts_path", (False, True))
def test_system_map_entrypoint_import_preserves_caller_sys_path(
    entrypoint: str,
    caller_has_scripts_path: bool,
) -> None:
    scripts_path = str(ROOT / "scripts")
    original_sys_path = sys.path.copy()
    sys.path[:] = [entry for entry in sys.path if entry != scripts_path]
    if caller_has_scripts_path:
        sys.path.insert(1, scripts_path)
    caller_sys_path = sys.path.copy()
    try:
        _load_entrypoint(entrypoint)

        assert sys.path == caller_sys_path
    finally:
        sys.path[:] = original_sys_path


def test_checker_import_prefers_repo_scripts_over_shadow_modules(tmp_path) -> None:
    scripts_path = str(ROOT / "scripts")
    shadow_dir = tmp_path / "shadow"
    shadow_dir.mkdir()
    (shadow_dir / "check_doc_drift.py").write_text(
        "def main(*, fresh_map=None):\n    return 99\n",
        encoding="utf-8",
    )
    module_names = (
        "check_doc_drift",
        "dump_system_map",
        "system_map_context",
        "system_map_contract",
    )
    saved_modules = {name: sys.modules.get(name) for name in module_names}
    original_sys_path = sys.path.copy()
    sys.path[:] = [
        str(shadow_dir),
        scripts_path,
        *(entry for entry in sys.path if entry != scripts_path),
    ]
    caller_sys_path = sys.path.copy()
    for name in module_names:
        sys.modules.pop(name, None)
    try:
        checker = _load_checker()

        assert Path(checker.check_doc_drift.__code__.co_filename).resolve() == (
            ROOT / "scripts" / "check_doc_drift.py"
        )
        assert sys.path == caller_sys_path
    finally:
        sys.path[:] = original_sys_path
        for name in module_names:
            sys.modules.pop(name, None)
            if saved_modules[name] is not None:
                sys.modules[name] = saved_modules[name]


@pytest.mark.parametrize("entrypoint", SYSTEM_MAP_ENTRYPOINTS)
def test_entrypoint_ignores_preloaded_scripts_import_helper(
    monkeypatch,
    entrypoint: str,
) -> None:
    shadow_package = types.ModuleType("scripts")
    shadow_package.__path__ = []
    shadow_helper = types.ModuleType("scripts.system_map_imports")

    def poison_loader(*_args, **_kwargs):
        raise AssertionError("preloaded scripts.system_map_imports was trusted")

    shadow_helper.load_repo_module = poison_loader
    monkeypatch.setitem(sys.modules, "scripts", shadow_package)
    monkeypatch.setitem(sys.modules, "scripts.system_map_imports", shadow_helper)

    entry_module = _load_entrypoint(entrypoint)
    helper_module = sys.modules[entry_module.load_repo_module.__module__]

    assert os.path.samefile(
        helper_module.__file__,
        ROOT / "scripts" / "system_map_imports.py",
    )


@pytest.mark.parametrize("entrypoint", SYSTEM_MAP_ENTRYPOINTS)
def test_entrypoint_rejects_preloaded_private_import_helper(
    monkeypatch,
    tmp_path,
    entrypoint: str,
) -> None:
    shadow_path = tmp_path / "system_map_imports.py"
    shadow_path.write_text("# noncanonical helper\n", encoding="utf-8")
    shadow_helper = types.ModuleType(_import_helper_key())
    shadow_helper.__file__ = str(shadow_path)
    shadow_helper.load_repo_module = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, _import_helper_key(), shadow_helper)

    with pytest.raises(ImportError, match="system_map_imports.py"):
        _load_entrypoint(entrypoint)


def test_entrypoints_share_one_helper_during_concurrent_bootstrap(
    monkeypatch,
) -> None:
    helper_path = (ROOT / "scripts" / "system_map_imports.py").resolve()
    helper_key = _import_helper_key()
    monkeypatch.delitem(sys.modules, helper_key, raising=False)
    shadow_package = types.ModuleType("scripts")
    shadow_package.__path__ = []
    shadow_helper = types.ModuleType("scripts.system_map_imports")
    shadow_helper.load_repo_module = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("preloaded scripts.system_map_imports was trusted")
    )
    monkeypatch.setitem(sys.modules, "scripts", shadow_package)
    monkeypatch.setitem(sys.modules, "scripts.system_map_imports", shadow_helper)

    real_spec_from_file_location = importlib.util.spec_from_file_location
    helper_started = threading.Event()
    helper_release = threading.Event()
    second_finished = threading.Event()
    helper_exec_calls = 0

    class SlowHelperLoader:
        def __init__(self, delegate) -> None:
            self.delegate = delegate

        def create_module(self, spec):
            return self.delegate.create_module(spec)

        def exec_module(self, module) -> None:
            nonlocal helper_exec_calls
            helper_exec_calls += 1
            helper_started.set()
            if not helper_release.wait(timeout=2):
                raise RuntimeError("helper release timed out")
            self.delegate.exec_module(module)

    def slow_helper_spec(name, location, *args, **kwargs):
        spec = real_spec_from_file_location(name, location, *args, **kwargs)
        if Path(location).resolve() == helper_path:
            assert spec is not None and spec.loader is not None
            spec.loader = SlowHelperLoader(spec.loader)
        return spec

    monkeypatch.setattr(importlib.util, "spec_from_file_location", slow_helper_spec)
    modules: dict[str, types.ModuleType] = {}
    errors: dict[str, BaseException] = {}

    def load(name: str) -> None:
        try:
            modules[name] = _load_entrypoint(name)
        except BaseException as error:
            errors[name] = error

    first = threading.Thread(target=load, args=("check_doc_drift",))

    def load_second() -> None:
        try:
            load("system_map_context")
        finally:
            second_finished.set()

    second = threading.Thread(target=load_second)
    try:
        first.start()
        assert helper_started.wait(timeout=1)
        second.start()
        assert not second_finished.wait(timeout=0.1)
        helper_release.set()
        first.join(timeout=2)
        second.join(timeout=2)

        assert not first.is_alive()
        assert not second.is_alive()
        assert errors == {}
        assert helper_exec_calls == 1
        assert (
            modules["check_doc_drift"].load_repo_module
            is modules["system_map_context"].load_repo_module
        )
    finally:
        helper_release.set()
        first.join(timeout=2)
        if second.ident is not None:
            second.join(timeout=2)


def test_failed_helper_bootstrap_removes_private_cache_entry(monkeypatch) -> None:
    helper_path = (ROOT / "scripts" / "system_map_imports.py").resolve()
    helper_key = _import_helper_key()
    monkeypatch.delitem(sys.modules, helper_key, raising=False)
    real_spec_from_file_location = importlib.util.spec_from_file_location

    class FailingHelperLoader:
        def __init__(self, delegate) -> None:
            self.delegate = delegate

        def create_module(self, spec):
            return self.delegate.create_module(spec)

        def exec_module(self, _module) -> None:
            raise RuntimeError("helper bootstrap failed")

    def failing_helper_spec(name, location, *args, **kwargs):
        spec = real_spec_from_file_location(name, location, *args, **kwargs)
        if Path(location).resolve() == helper_path:
            assert spec is not None and spec.loader is not None
            spec.loader = FailingHelperLoader(spec.loader)
        return spec

    monkeypatch.setattr(importlib.util, "spec_from_file_location", failing_helper_spec)

    with pytest.raises(RuntimeError, match="helper bootstrap failed"):
        _load_entrypoint("check_doc_drift")

    assert helper_key not in sys.modules
    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        real_spec_from_file_location,
    )
    entry_module = _load_entrypoint("check_doc_drift")
    assert os.path.samefile(
        sys.modules[entry_module.load_repo_module.__module__].__file__,
        helper_path,
    )


@pytest.mark.parametrize(
    "module_name",
    (
        "check_doc_drift",
        "dump_system_map",
        "system_map_context",
        "system_map_contract",
    ),
)
def test_checker_rejects_preloaded_noncanonical_system_map_modules(
    monkeypatch,
    tmp_path,
    module_name: str,
) -> None:
    shadow_path = tmp_path / f"{module_name}.py"
    shadow_path.write_text("# stale module from another checkout\n", encoding="utf-8")
    shadow = types.ModuleType(module_name)
    shadow.__file__ = str(shadow_path)
    shadow.main = lambda **_kwargs: 0
    shadow.build_map = lambda: {"counts": {}}
    shadow.check_artifacts = lambda _graph: (True, "")
    shadow.SystemMapContextError = ValueError
    shadow.render_agent_context = lambda _graph: ""
    shadow.SystemMapContractError = ValueError
    shadow.validate_system_map = lambda _graph: None
    monkeypatch.setitem(sys.modules, module_name, shadow)

    with pytest.raises(ImportError, match=module_name):
        _load_checker()


@pytest.mark.parametrize("repo_loader_first", (True, False))
def test_repo_module_loader_waits_for_concurrent_standard_import(
    monkeypatch,
    tmp_path,
    repo_loader_first: bool,
) -> None:
    from scripts import system_map_imports

    module_name = f"_slow_system_map_probe_{repo_loader_first}"
    support_name = f"{module_name}_support"
    support = types.ModuleType(support_name)
    support.started = threading.Event()
    support.release = threading.Event()
    monkeypatch.setitem(sys.modules, support_name, support)
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / f"{module_name}.py").write_text(
        f"from {support_name} import release, started\n"
        "started.set()\n"
        "if not release.wait(timeout=2):\n"
        "    raise RuntimeError('probe release timed out')\n"
        "READY = True\n",
        encoding="utf-8",
    )
    results: dict[str, types.ModuleType] = {}
    errors: dict[str, BaseException] = {}
    second_started = threading.Event()
    second_finished = threading.Event()

    def repo_load() -> None:
        try:
            results["repo"] = system_map_imports.load_repo_module(
                module_name,
                tmp_path,
            )
        except BaseException as error:
            errors["repo"] = error

    def standard_load() -> None:
        try:
            results["standard"] = importlib.import_module(module_name)
        except BaseException as error:
            errors["standard"] = error

    first_target = repo_load if repo_loader_first else standard_load
    second_target = standard_load if repo_loader_first else repo_load
    first = threading.Thread(target=first_target)

    def run_second() -> None:
        try:
            second_started.set()
            second_target()
        finally:
            second_finished.set()

    second = threading.Thread(target=run_second)
    try:
        first.start()
        assert support.started.wait(timeout=1)
        second.start()
        assert second_started.wait(timeout=1)
        assert not second_finished.wait(timeout=0.1)

        support.release.set()
        first.join(timeout=1)
        second.join(timeout=1)

        assert not first.is_alive()
        assert not second.is_alive()
        assert errors == {}
        assert results["repo"] is results["standard"]
        assert results["repo"].READY is True
    finally:
        support.release.set()
        first.join(timeout=1)
        second.join(timeout=1)
        sys.modules.pop(module_name, None)


def test_repo_module_loader_interrupt_releases_standard_import_waiter(
    monkeypatch,
    tmp_path,
) -> None:
    from scripts import system_map_imports

    module_name = "_interrupted_system_map_probe"
    support_name = f"{module_name}_support"
    support = types.ModuleType(support_name)
    support.started = threading.Event()
    support.release = threading.Event()
    support.attempts = 0
    support.specs = []
    monkeypatch.setitem(sys.modules, support_name, support)
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / f"{module_name}.py").write_text(
        f"import {support_name} as support\n"
        "support.attempts += 1\n"
        "support.specs.append(__spec__)\n"
        "if support.attempts == 1:\n"
        "    support.started.set()\n"
        "    if not support.release.wait(timeout=2):\n"
        "        raise RuntimeError('probe release timed out')\n"
        "    raise KeyboardInterrupt('probe interrupted')\n"
        "READY = True\n",
        encoding="utf-8",
    )
    results: dict[str, types.ModuleType] = {}
    errors: dict[str, BaseException] = {}
    standard_finished = threading.Event()

    def repo_load() -> None:
        try:
            results["repo"] = system_map_imports.load_repo_module(
                module_name,
                tmp_path,
            )
        except BaseException as error:
            errors["repo"] = error

    def standard_load() -> None:
        try:
            results["standard"] = importlib.import_module(module_name)
        except BaseException as error:
            errors["standard"] = error
        finally:
            standard_finished.set()

    repo_thread = threading.Thread(target=repo_load)
    standard_thread = threading.Thread(target=standard_load)
    try:
        repo_thread.start()
        assert support.started.wait(timeout=1)
        partial_module = sys.modules[module_name]
        partial_spec = partial_module.__spec__
        assert partial_spec is not None
        assert partial_spec._initializing is True

        standard_thread.start()
        assert not standard_finished.wait(timeout=0.1)
        support.release.set()
        repo_thread.join(timeout=2)
        standard_thread.join(timeout=2)

        assert not repo_thread.is_alive()
        assert not standard_thread.is_alive()
        assert isinstance(errors.pop("repo"), KeyboardInterrupt)
        assert errors == {}
        assert support.attempts == 2
        assert partial_spec._initializing is False
        assert sys.modules[module_name] is results["standard"]
        assert sys.modules[module_name] is not partial_module
        assert results["standard"].READY is True
    finally:
        support.release.set()
        repo_thread.join(timeout=2)
        if standard_thread.ident is not None:
            standard_thread.join(timeout=2)
        sys.modules.pop(module_name, None)


class _FakeMobileProcess:
    def __init__(
        self,
        events: list[object],
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.events = events
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def communicate(self) -> tuple[str, str]:
        self.events.append("mobile-communicate")
        return self.stdout, self.stderr


def _configure_successful_canonical(monkeypatch, checker, events: list[object]) -> dict:
    fresh_map = {"counts": {}}

    def validate_artifact() -> None:
        events.append("validate")

    def build_map() -> dict:
        events.append("build")
        return fresh_map

    def check_artifacts(graph: dict) -> tuple[bool, str]:
        events.append(("check", id(graph)))
        return True, ""

    monkeypatch.setattr(checker, "validate_artifact", validate_artifact)
    monkeypatch.setattr(checker, "build_map", build_map, raising=False)
    monkeypatch.setattr(checker, "check_artifacts", check_artifacts, raising=False)
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("central gate must not use subprocess.run"),
    )
    return fresh_map


def test_central_checker_reuses_one_graph_and_overlaps_mobile_with_doc_drift(
    monkeypatch,
) -> None:
    checker = _load_checker()
    events: list[object] = []
    fresh_map = _configure_successful_canonical(monkeypatch, checker, events)

    def fake_popen(argv, *, cwd, stdout, stderr, text, start_new_session):
        events.append(("mobile-start", tuple(argv)))
        assert cwd == checker.ROOT
        assert stdout is subprocess.PIPE
        assert stderr is subprocess.PIPE
        assert text is True
        assert start_new_session is True
        return _FakeMobileProcess(events)

    def fake_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append(("doc-drift", id(fresh_map)))
        return 0

    monkeypatch.setattr(checker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(checker, "check_doc_drift", fake_doc_drift, raising=False)

    assert checker.main() == 0
    assert events == [
        "validate",
        "build",
        ("check", id(fresh_map)),
        (
            "mobile-start",
            (sys.executable, "mobile/scripts/dump_nav_graph.py", "--check"),
        ),
        ("doc-drift", id(fresh_map)),
        "mobile-communicate",
    ]


@pytest.mark.parametrize(
    "failure_stage",
    ("schema", "build", "check-return", "check-raise"),
)
def test_canonical_failure_does_not_start_parallel_gates(
    monkeypatch,
    failure_stage: str,
) -> None:
    checker = _load_checker()
    events: list[str] = []
    fresh_map = {"counts": {}}

    def validate_artifact() -> None:
        events.append("validate")
        if failure_stage == "schema":
            raise OSError("schema unavailable")

    def build_map() -> dict:
        events.append("build")
        if failure_stage == "build":
            raise RuntimeError("build failed")
        return fresh_map

    def check_artifacts(_graph: dict) -> tuple[bool, str]:
        events.append("check")
        if failure_stage == "check-return":
            return False, "stale artifact"
        if failure_stage == "check-raise":
            raise RuntimeError("artifact check failed")
        return True, ""

    def forbidden_parallel(*_args, **_kwargs):
        pytest.fail("parallel gates must not start after canonical failure")

    monkeypatch.setattr(checker, "validate_artifact", validate_artifact)
    monkeypatch.setattr(checker, "build_map", build_map, raising=False)
    monkeypatch.setattr(checker, "check_artifacts", check_artifacts, raising=False)
    monkeypatch.setattr(checker, "check_doc_drift", forbidden_parallel, raising=False)
    monkeypatch.setattr(checker.subprocess, "Popen", forbidden_parallel)
    monkeypatch.setattr(checker.subprocess, "run", forbidden_parallel)

    assert checker.main() == 1
    expected_events = {
        "schema": ["validate"],
        "build": ["validate", "build"],
        "check-return": ["validate", "build", "check"],
        "check-raise": ["validate", "build", "check"],
    }
    assert events == expected_events[failure_stage]


def test_parallel_failures_replay_both_outputs_in_gate_order(
    monkeypatch,
    capsys,
) -> None:
    checker = _load_checker()
    events: list[object] = []
    _configure_successful_canonical(monkeypatch, checker, events)

    def fake_popen(*_args, **_kwargs):
        events.append("mobile-start")
        return _FakeMobileProcess(
            events,
            returncode=7,
            stdout="mobile stdout\n",
            stderr="mobile stderr\n",
        )

    def fake_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append("doc-drift")
        print("doc stdout")
        print("doc stderr", file=sys.stderr)
        return 9

    monkeypatch.setattr(checker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(checker, "check_doc_drift", fake_doc_drift, raising=False)

    assert checker.main() == 7

    output = capsys.readouterr()
    assert output.out.index("→ system-map") < output.out.index("→ mobile-nav")
    assert output.out.index("→ mobile-nav") < output.out.index("mobile stdout")
    assert output.out.index("mobile stdout") < output.out.index("→ doc-drift")
    assert output.out.index("→ doc-drift") < output.out.index("doc stdout")
    assert output.err.index("mobile stderr") < output.err.index("doc stderr")
    assert "❌ mobile-nav failed with exit code 7" in output.err
    assert "❌ doc-drift failed with exit code 9" in output.err
    assert events[-3:] == ["mobile-start", "doc-drift", "mobile-communicate"]


def test_combined_stream_replay_preserves_gate_order_in_a_real_subprocess() -> None:
    script = "\n".join(
        (
            "from scripts import check_system_map as checker",
            "checker.build_map = lambda: {'counts': {}}",
            "checker.check_artifacts = lambda _graph: (True, '')",
            "assert checker._build_and_check_canonical() is not None",
            "checker._replay_gate(",
            "    'mobile-nav', 'mobile stdout\\n', 'mobile stderr\\n', 7",
            ")",
            "checker._replay_gate(",
            "    'doc-drift', 'doc stdout\\n', 'doc stderr\\n', 9",
            ")",
        )
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout
    ordered_markers = (
        "→ system-map",
        "→ mobile-nav",
        "mobile stdout",
        "mobile stderr",
        "❌ mobile-nav failed with exit code 7",
        "→ doc-drift",
        "doc stdout",
        "doc stderr",
        "❌ doc-drift failed with exit code 9",
    )
    positions = [completed.stdout.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions), completed.stdout


def test_mobile_start_error_still_completes_doc_drift(monkeypatch, capsys) -> None:
    checker = _load_checker()
    events: list[object] = []
    _configure_successful_canonical(monkeypatch, checker, events)

    def failing_popen(*_args, **_kwargs):
        events.append("mobile-start")
        raise OSError("mobile spawn failed")

    def fake_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append("doc-drift")
        print("doc completed")
        return 0

    monkeypatch.setattr(checker.subprocess, "Popen", failing_popen)
    monkeypatch.setattr(checker, "check_doc_drift", fake_doc_drift, raising=False)

    assert checker.main() == 1

    output = capsys.readouterr()
    assert "mobile spawn failed" in output.err
    assert "doc completed" in output.out
    assert events[-2:] == ["mobile-start", "doc-drift"]


def test_doc_drift_error_still_reaps_mobile_process(monkeypatch, capsys) -> None:
    checker = _load_checker()
    events: list[object] = []
    _configure_successful_canonical(monkeypatch, checker, events)

    def fake_popen(*_args, **_kwargs):
        events.append("mobile-start")
        return _FakeMobileProcess(events, stdout="mobile completed\n")

    def failing_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append("doc-drift")
        raise RuntimeError("doc scan crashed")

    monkeypatch.setattr(checker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(checker, "check_doc_drift", failing_doc_drift, raising=False)

    assert checker.main() == 1

    output = capsys.readouterr()
    assert "mobile completed" in output.out
    assert "doc scan crashed" in output.err
    assert events[-3:] == ["mobile-start", "doc-drift", "mobile-communicate"]


def test_mobile_communicate_error_kills_and_reaps_process(monkeypatch, capsys) -> None:
    checker = _load_checker()
    events: list[object] = []
    _configure_successful_canonical(monkeypatch, checker, events)

    class FailingCommunicateProcess:
        returncode = None

        def communicate(self) -> tuple[str, str]:
            events.append("mobile-communicate")
            raise RuntimeError("mobile communicate failed")

        def wait(self, *, timeout=None) -> int:
            events.append(("mobile-wait", timeout))
            self.returncode = -9
            return self.returncode

        def kill(self) -> None:
            events.append("mobile-kill")

    def fake_popen(*_args, **_kwargs):
        events.append("mobile-start")
        return FailingCommunicateProcess()

    def fake_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append("doc-drift")
        return 0

    monkeypatch.setattr(checker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(checker, "check_doc_drift", fake_doc_drift, raising=False)

    assert checker.main() == 1

    output = capsys.readouterr()
    assert "mobile communicate failed" in output.err
    assert events[-4:] == [
        "doc-drift",
        "mobile-communicate",
        "mobile-kill",
        ("mobile-wait", checker.MOBILE_REAP_TIMEOUT_SECONDS),
    ]


def test_doc_drift_cancellation_reaps_mobile_before_propagating(monkeypatch) -> None:
    checker = _load_checker()
    events: list[object] = []
    _configure_successful_canonical(monkeypatch, checker, events)
    cancellation = KeyboardInterrupt("doc cancellation")

    class CancellableMobileProcess(_FakeMobileProcess):
        def kill(self) -> None:
            events.append("mobile-kill")
            self.returncode = -9

    def fake_popen(*_args, **_kwargs):
        events.append("mobile-start")
        return CancellableMobileProcess(events)

    def cancel_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append("doc-drift")
        raise cancellation

    monkeypatch.setattr(checker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(checker, "check_doc_drift", cancel_doc_drift, raising=False)

    with pytest.raises(KeyboardInterrupt) as caught:
        checker.main()

    assert caught.value is cancellation
    assert events[-3:] == [
        "mobile-start",
        "doc-drift",
        "mobile-kill",
    ]


def test_mobile_communicate_cancellation_kills_and_reaps_before_propagating(
    monkeypatch,
) -> None:
    checker = _load_checker()
    events: list[object] = []
    _configure_successful_canonical(monkeypatch, checker, events)
    cancellation = KeyboardInterrupt("mobile cancellation")

    class CancelledCommunicateProcess:
        returncode = None

        def __init__(self) -> None:
            self.communicate_calls = 0

        def communicate(self) -> tuple[str, str]:
            self.communicate_calls += 1
            events.append("mobile-communicate")
            if self.communicate_calls == 1:
                raise cancellation
            self.returncode = -9
            return "", ""

        def kill(self) -> None:
            events.append("mobile-kill")

    def fake_popen(*_args, **_kwargs):
        events.append("mobile-start")
        return CancelledCommunicateProcess()

    def fake_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append("doc-drift")
        return 0

    monkeypatch.setattr(checker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(checker, "check_doc_drift", fake_doc_drift, raising=False)

    with pytest.raises(KeyboardInterrupt) as caught:
        checker.main()

    assert caught.value is cancellation
    assert events[-4:] == [
        "mobile-start",
        "doc-drift",
        "mobile-communicate",
        "mobile-kill",
    ]


@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_mobile_cancellation_kills_descendant_group_without_unbounded_drain(
    tmp_path,
) -> None:
    checker = _load_checker()
    process, descendant_pid, watchdog = _start_descendant_probe(tmp_path)
    cancellation = KeyboardInterrupt("mobile cancellation")

    class CancelFirstCommunicate:
        pid = process.pid
        stdout = process.stdout
        stderr = process.stderr

        @property
        def returncode(self):
            return process.returncode

        def communicate(self):
            calls = getattr(self, "calls", 0) + 1
            self.calls = calls
            if calls == 1:
                raise cancellation
            return process.communicate()

        def kill(self) -> None:
            process.kill()

        def wait(self, *, timeout=None):
            return process.wait(timeout=timeout)

    started = time.monotonic()
    try:
        with pytest.raises(KeyboardInterrupt) as caught:
            checker._communicate_mobile(CancelFirstCommunicate())
        elapsed = time.monotonic() - started

        assert caught.value is cancellation
        assert elapsed < 3.0
        assert process.returncode is not None
        _assert_process_stopped(descendant_pid)
    finally:
        _finish_descendant_probe(process, descendant_pid, watchdog)


@pytest.mark.skipif(os.name != "posix", reason="process groups require POSIX")
def test_cleanup_retries_interrupted_process_group_kill(
    monkeypatch,
    tmp_path,
) -> None:
    checker = _load_checker()
    process, descendant_pid, watchdog = _start_descendant_probe(tmp_path)
    cancellation = KeyboardInterrupt("process-group kill interrupted")
    real_killpg = checker.os.killpg
    killpg_calls = 0

    def interrupt_first_killpg(pid: int, sig: int) -> None:
        nonlocal killpg_calls
        killpg_calls += 1
        if killpg_calls == 1:
            raise cancellation
        real_killpg(pid, sig)

    class FailedCommunicate:
        pid = process.pid
        stdout = process.stdout
        stderr = process.stderr

        @property
        def returncode(self):
            return process.returncode

        def communicate(self):
            raise RuntimeError("initial communicate failure")

        def kill(self) -> None:
            process.kill()

        def wait(self, *, timeout=None):
            return process.wait(timeout=timeout)

    monkeypatch.setattr(checker.os, "killpg", interrupt_first_killpg)
    try:
        with pytest.raises(KeyboardInterrupt) as caught:
            checker._communicate_mobile(FailedCommunicate())

        assert caught.value is cancellation
        assert killpg_calls >= 2
        assert "initial communicate failure" in "\n".join(
            getattr(caught.value, "__notes__", ())
        )
        assert process.returncode is not None
        _assert_process_stopped(descendant_pid)
    finally:
        monkeypatch.setattr(checker.os, "killpg", real_killpg)
        _finish_descendant_probe(process, descendant_pid, watchdog)


def _start_descendant_probe(tmp_path):
    child_script = tmp_path / "mobile_with_descendant.py"
    child_script.write_text(
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "descendant = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(60)'])\n"
        "print(descendant.pid, flush=True)\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, str(child_script)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    watchdog = threading.Timer(3.0, _kill_probe_group, args=(process, None))
    watchdog.start()
    try:
        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            ready = selector.select(timeout=1)
            assert ready, "mobile probe did not report its descendant PID"
            descendant_pid = int(process.stdout.readline().strip())
        finally:
            selector.close()
    except BaseException:
        watchdog.cancel()
        _finish_descendant_probe(process, None, watchdog)
        raise
    return process, descendant_pid, watchdog


def _kill_probe_group(process, descendant_pid: int | None) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (PermissionError, ProcessLookupError):
        for pid in (process.pid, descendant_pid):
            if pid is None:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except (PermissionError, ProcessLookupError):
                pass


def _assert_process_stopped(pid: int) -> None:
    deadline = time.monotonic() + 1.0
    while True:
        probe = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=0.5,
        )
        state = probe.stdout.strip()
        if not state or state.startswith("Z"):
            return
        if time.monotonic() >= deadline:
            pytest.fail(f"mobile descendant still running; pid={pid} state={state}")
        time.sleep(0.01)


def _finish_descendant_probe(process, descendant_pid, watchdog) -> None:
    watchdog.cancel()
    _kill_probe_group(process, descendant_pid)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


@pytest.mark.parametrize(
    "interrupt_stage",
    ("kill", "stdout-close", "stderr-close", "wait"),
)
def test_recovery_keyboard_interrupt_keeps_cleaning_and_becomes_primary(
    interrupt_stage: str,
) -> None:
    checker = _load_checker()
    events: list[object] = []
    cancellation = KeyboardInterrupt(f"cleanup interrupted at {interrupt_stage}")

    class Pipe:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            events.append(f"{self.name}-close")
            if (
                interrupt_stage == f"{self.name}-close"
                and events.count(f"{self.name}-close") == 1
            ):
                raise cancellation

    class RecoveryProcess:
        returncode = None
        stdout = Pipe("stdout")
        stderr = Pipe("stderr")

        def communicate(self):
            events.append("mobile-communicate")
            raise RuntimeError("initial communicate failure")

        def kill(self) -> None:
            events.append("mobile-kill")
            if interrupt_stage == "kill" and events.count("mobile-kill") == 1:
                raise cancellation

        def wait(self, *, timeout=None):
            events.append(("mobile-wait", timeout))
            if (
                interrupt_stage == "wait"
                and events.count(("mobile-wait", timeout)) == 1
            ):
                raise cancellation
            self.returncode = -9
            return self.returncode

    with pytest.raises(KeyboardInterrupt) as caught:
        checker._communicate_mobile(RecoveryProcess())

    assert caught.value is cancellation
    expected_events = [
        "mobile-communicate",
        "mobile-kill",
        "stdout-close",
        "stderr-close",
        ("mobile-wait", checker.MOBILE_REAP_TIMEOUT_SECONDS),
    ]
    retry_event = {
        "kill": "mobile-kill",
        "stdout-close": "stdout-close",
        "stderr-close": "stderr-close",
        "wait": ("mobile-wait", checker.MOBILE_REAP_TIMEOUT_SECONDS),
    }[interrupt_stage]
    expected_events.insert(expected_events.index(retry_event) + 1, retry_event)
    assert events == expected_events
    assert "initial communicate failure" in "\n".join(
        getattr(caught.value, "__notes__", ())
    )


def test_doc_cancellation_keeps_original_exception_when_cleanup_fails(
    monkeypatch,
) -> None:
    checker = _load_checker()
    events: list[object] = []
    _configure_successful_canonical(monkeypatch, checker, events)
    cancellation = KeyboardInterrupt("original cancellation")

    class FailingPipe:
        def __init__(self, name: str, *, fail: bool = False) -> None:
            self.name = name
            self.fail = fail

        def close(self) -> None:
            events.append(f"mobile-{self.name}-close")
            if self.fail:
                raise RuntimeError(f"cleanup {self.name} close failed")

    class CleanupFailureProcess:
        returncode = None
        stdout = FailingPipe("stdout", fail=True)
        stderr = FailingPipe("stderr")

        def kill(self) -> None:
            events.append("mobile-kill")

        def wait(self, *, timeout=None) -> int:
            events.append(("mobile-wait", timeout))
            raise RuntimeError("cleanup wait failed")

    def fake_popen(*_args, **_kwargs):
        events.append("mobile-start")
        return CleanupFailureProcess()

    def cancel_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append("doc-drift")
        raise cancellation

    monkeypatch.setattr(checker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(checker, "check_doc_drift", cancel_doc_drift, raising=False)

    with pytest.raises(KeyboardInterrupt) as caught:
        checker.main()

    assert caught.value is cancellation
    cleanup_notes = "\n".join(getattr(caught.value, "__notes__", ()))
    assert "cleanup stdout close failed" in cleanup_notes
    assert "cleanup wait failed" in cleanup_notes
    assert events[-6:] == [
        "mobile-start",
        "doc-drift",
        "mobile-kill",
        "mobile-stdout-close",
        "mobile-stderr-close",
        ("mobile-wait", checker.MOBILE_REAP_TIMEOUT_SECONDS),
    ]
