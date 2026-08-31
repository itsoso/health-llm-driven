import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

import backend.scripts.verify_locked_requirements as verifier


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "backend" / "scripts" / "verify_locked_requirements.py"


def _run(lock: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(lock)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_locked_requirement_verifier_accepts_exact_installed_version(
    tmp_path: Path,
) -> None:
    version = importlib.metadata.version("pip")
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        f"pip=={version} \\\n    --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )

    result = _run(lock)

    assert result.returncode == 0, result.stderr
    assert "LOCKED_REQUIREMENTS_OK packages=1" in result.stdout


def test_locked_requirement_verifier_rejects_mismatch_and_unpinned_input(
    tmp_path: Path,
) -> None:
    mismatch = tmp_path / "mismatch.lock"
    mismatch.write_text(
        f"pip==0.0.1 \\\n    --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )
    unpinned = tmp_path / "unpinned.lock"
    unpinned.write_text("pip>=1\n", encoding="utf-8")

    mismatch_result = _run(mismatch)
    unpinned_result = _run(unpinned)

    assert mismatch_result.returncode != 0
    assert "installed=" in mismatch_result.stderr
    assert unpinned_result.returncode != 0
    assert "unsupported lock requirement" in unpinned_result.stderr


@pytest.mark.parametrize(
    ("package_name", "installed_version"),
    (("chromadb", "0.6.3"), ("chroma-hnswlib", "0.7.6")),
)
def test_locked_requirement_verifier_rejects_stale_unpatched_chroma_packages(
    tmp_path: Path,
    monkeypatch,
    package_name: str,
    installed_version: str,
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "pip==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )

    def fake_version(name: str) -> str:
        normalized = name.lower().replace("_", "-")
        if normalized == "pip":
            return "1.0"
        if normalized == package_name:
            return installed_version
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(verifier.importlib.metadata, "version", fake_version)

    assert verifier.verify_lock(lock) == [
        f"{package_name}: forbidden installed package; installed={installed_version}"
    ]


def test_locked_requirement_verifier_can_sanitize_forbidden_entries_from_a_rollback_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "pip==1.0 \\\n"
        "    --hash=sha256:" + "a" * 64 + "\n"
        "chromadb==0.6.3 \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n"
        "chroma-hnswlib==0.7.6 \\\n"
        "    --hash=sha256:" + "c" * 64 + "\n",
        encoding="utf-8",
    )

    installed_forbidden: dict[str, str] = {}

    def fake_version(name: str) -> str:
        normalized = name.lower().replace("_", "-")
        if normalized == "pip":
            return "1.0"
        if normalized in installed_forbidden:
            return installed_forbidden[normalized]
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(verifier.importlib.metadata, "version", fake_version)

    assert verifier.verify_lock(
        lock,
        sanitize_forbidden_packages=True,
    ) == []
    installed_forbidden["chroma-hnswlib"] = "0.7.6"
    assert verifier.verify_lock(
        lock,
        sanitize_forbidden_packages=True,
    ) == [
        "chroma-hnswlib: forbidden installed package; installed=0.7.6"
    ]
