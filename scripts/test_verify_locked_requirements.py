import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "backend" / "scripts" / "verify_locked_requirements.py"


def _run(lock: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(lock)],
        text=True,
        capture_output=True,
        check=False,
    )


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "locked_requirements_verifier", VERIFIER
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _distribution(name: str, version: str) -> SimpleNamespace:
    return SimpleNamespace(metadata={"Name": name}, version=version)


def test_locked_requirement_verifier_accepts_exact_installed_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    lock = tmp_path / "requirements.lock"
    lock.write_text("demo-pkg==1.2.3\n", encoding="utf-8")
    distributions = [
        _distribution("Demo_Pkg", "1.2.3"),
        _distribution("pip", "25.0"),
        _distribution("wheel", "0.45.1"),
    ]
    monkeypatch.setattr(
        verifier.importlib.metadata, "distributions", lambda: distributions
    )

    errors = verifier.verify_lock(lock)

    assert errors == []


def test_locked_requirement_verifier_rejects_unlocked_installed_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    lock = tmp_path / "requirements.lock"
    lock.write_text("demo-pkg==1.2.3\n", encoding="utf-8")
    distributions = [
        _distribution("demo-pkg", "1.2.3"),
        _distribution("unexpected-addon", "9.9.9"),
    ]
    monkeypatch.setattr(
        verifier.importlib.metadata, "distributions", lambda: distributions
    )

    errors = verifier.verify_lock(lock)

    assert "unexpected-addon: installed=9.9.9; not present in lock" in errors


def test_locked_requirement_verifier_rejects_duplicate_canonical_lock_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "Demo_Pkg==1.2.3\n"
        "demo-pkg==1.2.3\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        verifier.importlib.metadata,
        "distributions",
        lambda: [_distribution("demo-pkg", "1.2.3")],
    )

    errors = verifier.verify_lock(lock)

    assert "line 2: duplicate lock requirement: demo-pkg" in errors


def test_locked_requirement_verifier_rejects_duplicate_installed_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    lock = tmp_path / "requirements.lock"
    lock.write_text("demo-pkg==1.2.3\n", encoding="utf-8")
    monkeypatch.setattr(
        verifier.importlib.metadata,
        "distributions",
        lambda: [
            _distribution("Demo_Pkg", "1.2.3"),
            _distribution("demo-pkg", "1.2.3"),
        ],
    )

    errors = verifier.verify_lock(lock)

    assert "demo-pkg: multiple installed distributions (1.2.3, 1.2.3)" in errors


def test_locked_requirement_verifier_rejects_missing_locked_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    lock = tmp_path / "requirements.lock"
    lock.write_text("demo-pkg==1.2.3\n", encoding="utf-8")
    monkeypatch.setattr(
        verifier.importlib.metadata,
        "distributions",
        lambda: [_distribution("pip", "25.0")],
    )

    errors = verifier.verify_lock(lock)

    assert "demo-pkg: missing; expected=1.2.3" in errors


def test_locked_requirement_verifier_rejects_distribution_without_name_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verifier = _load_verifier()
    lock = tmp_path / "requirements.lock"
    lock.write_text("demo-pkg==1.2.3\n", encoding="utf-8")
    monkeypatch.setattr(
        verifier.importlib.metadata,
        "distributions",
        lambda: [
            _distribution("demo-pkg", "1.2.3"),
            SimpleNamespace(metadata={}, version="9.9.9"),
        ],
    )

    errors = verifier.verify_lock(lock)

    assert "installed distribution has no Name metadata" in errors


def test_locked_requirement_verifier_rejects_mismatch_and_unpinned_input(
    tmp_path: Path,
) -> None:
    mismatch = tmp_path / "mismatch.lock"
    mismatch.write_text("pip==0.0.1\n", encoding="utf-8")
    unpinned = tmp_path / "unpinned.lock"
    unpinned.write_text("pip>=1\n", encoding="utf-8")

    mismatch_result = _run(mismatch)
    unpinned_result = _run(unpinned)

    assert mismatch_result.returncode != 0
    assert "installed=" in mismatch_result.stderr
    assert unpinned_result.returncode != 0
    assert "unsupported lock requirement" in unpinned_result.stderr
