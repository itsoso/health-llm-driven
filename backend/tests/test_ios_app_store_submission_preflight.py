import os
import subprocess
import sys
from pathlib import Path


def _run_preflight(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/check_ios_app_store_submission.py", *extra],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_ios_app_store_submission_preflight_passes_repo_config():
    root = Path(__file__).resolve().parents[2]

    result = _run_preflight(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "iOS App Store submission preflight passed." in result.stdout
    assert "app_name=阿衡" in result.stdout
    assert "bundle_id=life.executor.health" in result.stdout
    assert "asc_app_id=6763569720" in result.stdout


def test_ios_app_store_submission_preflight_requires_asc_credentials_when_requested():
    root = Path(__file__).resolve().parents[2]
    scrubbed_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ASC_") and not key.startswith("APP_STORE_CONNECT_")
    }

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_ios_app_store_submission.py",
            "--require-asc-credentials",
        ],
        cwd=root,
        env=scrubbed_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert "missing App Store Connect credentials" in result.stderr
