"""Exercise explicit backup opt-in without contacting production."""

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_SHA = "a" * 40
CANDIDATE_SHA = "b" * 40


@pytest.mark.parametrize(
    (
        "diff_rc",
        "ancestor_rc",
        "receipt_rc",
        "stage_rc",
        "backup_rc",
        "expected_rc",
        "expected_calls",
        "expected_mode",
    ),
    [
        (0, 0, 0, 0, 0, 0, ["stage", "receipt", "backup"], "skip"),
        (0, 0, 1, 0, 0, 0, ["stage", "receipt", "backup"], "upload"),
        (1, 0, 0, 0, 0, 0, ["stage", "backup"], "upload"),
        (2, 0, 0, 0, 0, 0, ["stage", "backup"], "upload"),
        (0, 1, 0, 0, 0, 0, ["stage", "backup"], "upload"),
        (0, 0, 0, 7, 0, 1, ["stage"], None),
        (0, 0, 0, 0, 8, 1, ["stage", "receipt", "backup"], "skip"),
    ],
)
def test_deploy_backup_policy(
    tmp_path,
    diff_rc,
    ancestor_rc,
    receipt_rc,
    stage_rc,
    backup_rc,
    expected_rc,
    expected_calls,
    expected_mode,
):
    script = (ROOT / "deploy.sh").read_text(encoding="utf-8")
    body = script[script.index("backup_database() {") : script.index("# 记录当前 commit")]
    calls = tmp_path / "calls"
    backup_command = tmp_path / "backup-command"
    harness = f"""
print_step() {{ :; }}
print_success() {{ :; }}
print_warning() {{ :; }}
print_error() {{ :; }}
SERVER=fake-server
REMOTE_PATH=/opt/health-app
REMOTE_BACKUP_RUNNER=/tmp/stage/backup_db.sh
REMOTE_VERIFY_RECENT_OFFSITE=/tmp/stage/verify_recent_offsite_backup.sh
DEPLOY_EXPECTED_SHA={CANDIDATE_SHA}
stage_backup_preflight_scripts() {{ echo stage >> "$CALLS"; return {stage_rc}; }}
git() {{
    if [ "$1" = cat-file ]; then return 0; fi
    if [ "$1" = merge-base ]; then return {ancestor_rc}; fi
    if [ "$1" = diff ]; then return {diff_rc}; fi
    return 99
}}
ssh() {{
    case "$*" in
        *"git rev-parse HEAD"*) printf '%s\n' {PRODUCTION_SHA} ;;
        *verify_recent_offsite_backup.sh*) echo receipt >> "$CALLS"; return {receipt_rc} ;;
        *BACKUP_OFFSITE_MODE=*) echo backup >> "$CALLS"; printf '%s\n' "$*" > "$BACKUP_COMMAND"; return {backup_rc} ;;
        *) return 98 ;;
    esac
}}
{body}
backup_database
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        env={
            **os.environ,
            "CALLS": str(calls),
            "BACKUP_COMMAND": str(backup_command),
            "DEPLOY_DATABASE_BACKUP": "1",
        },
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == expected_rc, (result.stdout, result.stderr)
    assert (calls.read_text().splitlines() if calls.exists() else []) == expected_calls
    if expected_mode is None:
        assert not backup_command.exists()
    else:
        assert f"BACKUP_OFFSITE_MODE='{expected_mode}'" in backup_command.read_text()


@pytest.mark.parametrize("setting", [None, "0"])
@pytest.mark.parametrize("delegated", ["0", "1"])
@pytest.mark.parametrize("stage_rc", [0, 7])
def test_default_deploy_stages_tools_without_database_or_offsite_access(
    tmp_path, setting, delegated, stage_rc
):
    script = (ROOT / "deploy.sh").read_text(encoding="utf-8")
    body = script[script.index("backup_database() {") : script.index("# 记录当前 commit")]
    calls = tmp_path / "calls"
    harness = f"""
print_step() {{ :; }}
print_success() {{ :; }}
print_warning() {{ :; }}
print_error() {{ :; }}
_REMOTE_RELEASE_LOCK_DELEGATED={delegated}
stage_backup_preflight_scripts() {{ echo stage >> "$CALLS"; return {stage_rc}; }}
ssh() {{ echo unexpected_remote_access >> "$CALLS"; return 98; }}
git() {{ echo unexpected_git_access >> "$CALLS"; return 99; }}
{body}
backup_database
rc=$?
printf '%s:%s:%s' "$rc" "$_REMOTE_RELEASE_LOCK_DELEGATED" "${{_REMOTE_RELEASE_LOCK_ABANDONED:-0}}"
exit "$rc"
"""
    env = {**os.environ, "CALLS": str(calls)}
    env.pop("DEPLOY_DATABASE_BACKUP", None)
    if setting is not None:
        env["DEPLOY_DATABASE_BACKUP"] = setting
    result = subprocess.run(
        ["bash", "-c", harness], env=env, capture_output=True, text=True, timeout=5
    )
    assert result.returncode == (1 if stage_rc else 0)
    assert calls.read_text().splitlines() == ["stage"]
    assert result.stdout == ("1:1:1" if stage_rc else f"0:{delegated}:0")


@pytest.mark.parametrize("setting", ["yes", "2", "", "false"])
def test_invalid_backup_setting_fails_before_staging(tmp_path, setting):
    script = (ROOT / "deploy.sh").read_text(encoding="utf-8")
    body = script[script.index("backup_database() {") : script.index("# 记录当前 commit")]
    calls = tmp_path / "calls"
    harness = f"""
print_step() {{ :; }}
print_error() {{ :; }}
stage_backup_preflight_scripts() {{ echo stage >> "$CALLS"; return 7; }}
{body}
backup_database
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        env={**os.environ, "CALLS": str(calls), "DEPLOY_DATABASE_BACKUP": setting},
        capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 1
    assert not calls.exists()
