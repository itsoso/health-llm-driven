from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_checker():
    path = ROOT / "scripts" / "check_system_map.py"
    assert path.exists(), "scripts/check_system_map.py must be the central gate"
    spec = importlib.util.spec_from_file_location("check_system_map", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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

    def fake_popen(argv, *, cwd, stdout, stderr, text):
        events.append(("mobile-start", tuple(argv)))
        assert cwd == checker.ROOT
        assert stdout is subprocess.PIPE
        assert stderr is subprocess.PIPE
        assert text is True
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

        def __init__(self) -> None:
            self.communicate_calls = 0

        def communicate(self) -> tuple[str, str]:
            self.communicate_calls += 1
            events.append("mobile-communicate")
            if self.communicate_calls == 1:
                raise RuntimeError("mobile communicate failed")
            self.returncode = -9
            return "mobile reaped\n", ""

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
    assert "mobile reaped" in output.out
    assert events[-5:] == [
        "mobile-start",
        "doc-drift",
        "mobile-communicate",
        "mobile-kill",
        "mobile-communicate",
    ]


def test_doc_drift_cancellation_reaps_mobile_before_propagating(monkeypatch) -> None:
    checker = _load_checker()
    events: list[object] = []
    _configure_successful_canonical(monkeypatch, checker, events)

    def fake_popen(*_args, **_kwargs):
        events.append("mobile-start")
        return _FakeMobileProcess(events)

    def cancel_doc_drift(*, fresh_map: dict | None = None) -> int:
        events.append("doc-drift")
        raise KeyboardInterrupt

    monkeypatch.setattr(checker.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(checker, "check_doc_drift", cancel_doc_drift, raising=False)

    with pytest.raises(KeyboardInterrupt):
        checker.main()

    assert events[-3:] == ["mobile-start", "doc-drift", "mobile-communicate"]
