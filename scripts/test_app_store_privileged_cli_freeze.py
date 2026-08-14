import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("script_name", "privileged_flag", "expected_message"),
    (
        (
            "check_app_store_release_pack.py",
            "--final-submit",
            "final-submit is frozen",
        ),
        (
            "check_ios_app_store_submission.py",
            "--require-asc-credentials",
            "credential validation is frozen",
        ),
    ),
)
def test_privileged_app_store_cli_freezes_before_imports_credentials_paths_or_network(
    tmp_path: Path,
    script_name: str,
    privileged_flag: str,
    expected_message: str,
) -> None:
    isolated = tmp_path / "scripts"
    isolated.mkdir()
    script = isolated / script_name
    shutil.copyfile(ROOT / "scripts" / script_name, script)
    marker = tmp_path / "import-or-tool-called"
    (isolated / "argparse.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported')\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("curl", "git", "ssh", "eas", "xcrun"):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
    secret = "review-password-must-not-leak"

    completed = subprocess.run(
        [sys.executable, str(script), privileged_flag],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(fake_bin),
            "HOME": str(tmp_path / "poison-home"),
            "APP_STORE_REVIEW_DEMO_PASSWORD": secret,
            "ASC_API_KEY_PATH": str(tmp_path / "must-not-read.p8"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert expected_message in completed.stderr
    assert secret not in completed.stdout + completed.stderr
    assert str(tmp_path / "must-not-read.p8") not in completed.stdout + completed.stderr
    assert not marker.exists()
