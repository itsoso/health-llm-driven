from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


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


def test_central_checker_runs_all_gates_in_order(monkeypatch) -> None:
    checker = _load_checker()
    events: list[object] = []

    monkeypatch.setattr(checker, "validate_artifact", lambda: events.append("validate"))

    def fake_run(argv, *, cwd, check):
        events.append(tuple(argv))
        assert cwd == checker.ROOT
        assert check is False
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert checker.main() == 0
    assert events == [
        "validate",
        (sys.executable, "scripts/dump_system_map.py", "--check"),
        (sys.executable, "mobile/scripts/dump_nav_graph.py", "--check"),
        (sys.executable, "scripts/check_doc_drift.py"),
    ]


def test_central_checker_propagates_first_failed_gate(monkeypatch) -> None:
    checker = _load_checker()
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(checker, "validate_artifact", lambda: None)

    def fake_run(argv, *, cwd, check):
        calls.append(tuple(argv))
        return SimpleNamespace(returncode=7 if len(calls) == 2 else 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert checker.main() == 7
    assert len(calls) == 2
