from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_doctor():
    spec = importlib.util.spec_from_file_location("harness_environment_doctor", ROOT / "scripts/harness_environment_doctor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_doctor_detects_local_python_when_path_missing(tmp_path, monkeypatch):
    doctor = load_doctor()
    interpreter = tmp_path / ".venv/bin/python3.12"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(doctor, "_python_version", lambda path: "3.12.13" if path == interpreter else None)
    report = doctor.inspect_environment(tmp_path, "base", tmp_path / "uv-cache")
    assert report["python"]["usable"] is True
    assert report["python"]["on_path"] is False
    assert report["python"]["source"] == "project_venv"
    assert report["ready"] is False  # git absent, never silently green


def test_doctor_timeout_and_failure_do_not_expose_output(monkeypatch):
    doctor = load_doctor()
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 5
        assert kwargs["env"] == {"PYTHONNOUSERSITE": "1"}
        raise subprocess.TimeoutExpired(args[0], 5, output="TOKEN=private")
    monkeypatch.setattr(doctor.subprocess, "run", timeout)
    assert doctor._python_version(Path("/python")) is None


def test_doctor_never_uses_wrong_python_or_installs(tmp_path, monkeypatch):
    doctor = load_doctor()
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/bin/" + name)
    monkeypatch.setattr(doctor, "_python_version", lambda path: "3.14.1")
    report = doctor.inspect_environment(tmp_path, "testflight", tmp_path / "cache")
    assert report["ready"] is False
    assert report["python"]["usable"] is False
    assert report["scope"] == "local_tool_availability_only"
    assert set(report["tools"]) >= {"eas", "xcodebuild", "git"}
