"""Exercise backup opt-in without contacting production or creating backups."""
import os
import subprocess
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize(("enabled", "stage_rc", "backup_rc", "expected_rc", "expected_calls"), [
    (None, 0, 0, 0, ["stage"]),
    ("0", 0, 0, 0, ["stage"]),
    ("1", 0, 0, 0, ["stage", "backup"]),
    (None, 7, 0, 1, ["stage"]),
    ("1", 0, 8, 1, ["stage", "backup"]),
    ("invalid", 0, 0, 1, []),
])
def test_deploy_backup_policy(tmp_path, enabled, stage_rc, backup_rc, expected_rc, expected_calls):
    script = (ROOT / "deploy.sh").read_text()
    body = script[script.index("backup_database() {"):script.index("# 记录当前 commit")]
    calls = tmp_path / "calls"
    env = {k: v for k, v in os.environ.items() if k != "DEPLOY_DATABASE_BACKUP"}
    env["CALLS"] = str(calls)
    if enabled is not None:
        env["DEPLOY_DATABASE_BACKUP"] = enabled
    harness = f"""
print_step() {{ :; }}
print_success() {{ :; }}
print_warning() {{ :; }}
print_error() {{ :; }}
stage_backup_preflight_scripts() {{ echo stage >> "$CALLS"; return {stage_rc}; }}
ssh() {{ echo backup >> "$CALLS"; return {backup_rc}; }}
{body}
backup_database
"""
    result = subprocess.run(["bash", "-c", harness], env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == expected_rc, result.stderr
    assert (calls.read_text().splitlines() if calls.exists() else []) == expected_calls
