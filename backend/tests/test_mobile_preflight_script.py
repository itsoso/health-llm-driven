from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mobile_preflight_uses_current_ios_app_target():
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "preflight-eas.sh")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "preflight 全过" in result.stdout
