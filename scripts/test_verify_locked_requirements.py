import importlib.metadata
import subprocess
import sys
from pathlib import Path


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
