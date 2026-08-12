import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "deploy.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o100)


def _write_root_owned_stat_shim(path: Path) -> None:
    """Write the GNU-stat subset used by remote release-state harnesses."""
    _write_executable(
        path,
        """#!/usr/bin/env python3
import os
import sys

if len(sys.argv) != 4 or sys.argv[1] != "-c":
    raise SystemExit(64)

metadata = os.stat(sys.argv[3])
if sys.argv[2] == "%h":
    print(metadata.st_nlink)
elif sys.argv[2] == "%U:%G:%a":
    print(f"root:root:{metadata.st_mode & 0o7777:o}")
else:
    raise SystemExit(64)
""",
    )


def test_backend_deploy_checks_health_before_skills_manifest():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    health_check = script.index("if ! verify_deployment; then")
    manifest_check = script.index("wait_for_agent_skills_manifest", health_check)

    assert health_check < manifest_check


def test_backend_dependency_cache_is_lock_addressed_and_fail_closed():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("remote_dependency_sync_command() {")
    end = script.index("compute_release_input_digests() {", start)
    body = script[start:end]

    assert "requirements-lock.sha256" in body
    assert "REQUIREMENTS_LOCK_SHA" in body
    assert "pip install --require-hashes -r requirements.lock" in body
    assert "scripts/verify_locked_requirements.py requirements.lock" in body
    assert "python -m pip check" in body
    assert "root:root:700" in body
    assert "root:root:600" in body
    assert 'test ! -L "\\${requirements_marker}"' in body
    assert "stat -c '%h'" in body
    assert "dependency lock unchanged; verified install reused" in body
    install = body.index("pip install --require-hashes")
    verified = body.index("python -m pip check", install)
    marker_replace = body.index('mv -fT -- "\\${requirements_marker_tmp}"')
    assert install < verified < marker_replace
    assert "|| true" not in body


def test_release_state_markers_are_verified_and_written_atomically():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    decide_start = script.index("determine_system_kb_activation_need() {")
    decide_end = script.index("record_system_kb_input_digest() {", decide_start)
    decide = script[decide_start:decide_end]
    record_start = decide_end
    record_end = script.index("# 部署后端", record_start)
    record = script[record_start:record_end]

    for body in (decide, record):
        assert "root:root:700" in body
        assert "root:root:600" in body
        assert "stat -c '%h'" in body
        assert "test ! -L" in body
    assert "mktemp" in record
    assert "mv -fT --" in record


def test_dependency_marker_never_skips_an_unverified_or_symlinked_environment(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    install_log = tmp_path / "installs"
    verifier_count = tmp_path / "verifier-count"
    state_dir = tmp_path / "release-state"
    digest = "a" * 64
    _write_root_owned_stat_shim(fake_bin / "stat")
    _write_executable(fake_bin / "sync", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "mv",
        """#!/bin/sh
set -eu
test "$1" = "-fT"
test "$2" = "--"
/bin/mv -f "$3" "$4"
""",
    )
    _write_executable(
        fake_bin / "pip",
        """#!/bin/sh
set -eu
printf 'install\n' >> "$FAKE_INSTALL_LOG"
""",
    )
    _write_executable(
        fake_bin / "python",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-m" ]]; then
  test "$2" = "pip"
  test "$3" = "check"
  exit 0
fi
count=0
[[ -f "$FAKE_VERIFIER_COUNT" ]] && count=$(cat "$FAKE_VERIFIER_COUNT")
count=$((count + 1))
printf '%s\n' "$count" > "$FAKE_VERIFIER_COUNT"
if [[ "${FAKE_VERIFIER_FAIL_AT:-0}" == "$count" ]]; then
  exit 1
fi
test "$1" = "scripts/verify_locked_requirements.py"
test "$2" = "requirements.lock"
""",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_RELEASE_STATE_DIR={state_dir!s}
REQUIREMENTS_LOCK_SHA={digest}
dependency_command="$(remote_dependency_sync_command)"
PATH="$FAKE_BIN:$PATH" bash -c "$dependency_command"
test "$(cat '{state_dir!s}/requirements-lock.sha256')" = '{digest}'
test "$(awk 'END {{ print NR + 0 }}' "$FAKE_INSTALL_LOG")" = 1
PATH="$FAKE_BIN:$PATH" bash -c "$dependency_command"
test "$(awk 'END {{ print NR + 0 }}' "$FAKE_INSTALL_LOG")" = 1
FAKE_VERIFIER_FAIL_AT=3 PATH="$FAKE_BIN:$PATH" bash -c "$dependency_command"
test "$(awk 'END {{ print NR + 0 }}' "$FAKE_INSTALL_LOG")" = 2
rm -f '{state_dir!s}/requirements-lock.sha256'
ln -s '{tmp_path!s}/attacker-marker' '{state_dir!s}/requirements-lock.sha256'
if PATH="$FAKE_BIN:$PATH" bash -c "$dependency_command"; then exit 91; fi
test "$(awk 'END {{ print NR + 0 }}' "$FAKE_INSTALL_LOG")" = 2
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FAKE_BIN": str(fake_bin),
            "FAKE_INSTALL_LOG": str(install_log),
            "FAKE_VERIFIER_COUNT": str(verifier_count),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_system_kb_marker_executes_missing_match_and_symlink_paths(tmp_path: Path):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state_dir = tmp_path / "release-state"
    digest = "b" * 64
    _write_root_owned_stat_shim(fake_bin / "stat")
    _write_executable(fake_bin / "sync", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "mv",
        """#!/bin/sh
set -eu
test "$1" = "-fT"
test "$2" = "--"
/bin/mv -f "$3" "$4"
""",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_RELEASE_STATE_DIR={state_dir!s}
SYSTEM_KB_INPUT_SHA={digest}
ssh() {{ shift; PATH="$FAKE_BIN:$PATH" "$@"; }}
determine_system_kb_activation_need
test "$SYSTEM_KB_ACTIVATION_REQUIRED" = 1
record_system_kb_input_digest
determine_system_kb_activation_need
test "$SYSTEM_KB_ACTIVATION_REQUIRED" = 0
rm -f '{state_dir!s}/system-kb-input.sha256'
ln -s '{tmp_path!s}/attacker-marker' '{state_dir!s}/system-kb-input.sha256'
if determine_system_kb_activation_need; then exit 91; fi
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FAKE_BIN": str(fake_bin),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_system_kb_cache_only_skips_mutation_and_keeps_post_gates():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_end = script.index("render_backend_env_file() {", deploy_start)
    deploy_body = script[deploy_start:deploy_end]

    backup = deploy_body.index("backup_database")
    decide = deploy_body.index("determine_system_kb_activation_need")
    mutation = deploy_body.index("python scripts/seed_food_nutrition.py")
    final_contract = deploy_body.rindex('verify_runtime_only_kb_contract "staged"')
    record = deploy_body.index("record_system_kb_input_digest", final_contract)
    finalize = deploy_body.index(
        "finalize_runtime_state_transaction_after_all_gates", record
    )

    assert backup < decide < mutation < final_contract < record < finalize
    assert "SYSTEM_KB_ACTIVATION_REQUIRED" in deploy_body
    assert "System KB inputs unchanged; mutation skipped" in deploy_body
    assert "system-kb-input.sha256" in script
    assert "verify_deployment" in deploy_body
    assert "verify_deployed_revision" in deploy_body


def test_skills_manifest_check_uses_condition_wait_not_fixed_three_retries():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "wait_for_agent_skills_manifest" in script
    assert "for attempt in $(seq 1 12)" in script


def test_skills_manifest_check_does_not_embed_auth_token():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "Authorization: Bearer" not in script


def test_remote_sync_does_not_stash_untracked_runtime_files():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "git stash push -u" not in script
    assert "git stash push -m auto-deploy-stash" in script
    assert "auto-deploy-stash >/dev/null 2>&1 || true" not in script


def test_remote_sync_normalizes_only_git_metadata_and_tracked_paths():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("remote_repository_trust_normalization_command() {")
    end = script.index("remote_git_sync_command() {", start)
    body = script[start:end]

    assert "chown root:root ." in body
    assert "chown -R root:root .git" in body
    assert "chmod -R go-w .git" in body
    assert "git ls-files --stage -z" in body
    assert 'chown -h root:root -- "$tracked_path"' in body
    assert 'chmod 0644 -- "$tracked_path"' in body
    assert 'chmod 0755 -- "$tracked_path"' in body
    assert "chown -R root:root .\n" not in body


def test_repository_trust_normalization_never_targets_ignored_runtime_data(
    tmp_path: Path,
):
    repo = tmp_path / "release"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repo,
        check=True,
    )
    (repo / "src").mkdir()
    (repo / "src/app.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "backend/.env\nuploads/\ntmp/\nnode_modules/\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    for ignored in (
        repo / "backend/.env",
        repo / "uploads/private.bin",
        repo / "tmp/runtime.sock",
        repo / "node_modules/pkg/index.js",
    ):
        ignored.parent.mkdir(parents=True, exist_ok=True)
        ignored.write_text("runtime\n", encoding="utf-8")

    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=root@example.test\n"
        f"DEPLOY_PATH={repo!s}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = (
        f"source {DEPLOY_SCRIPT!s}\n"
        "remote_repository_trust_normalization_command\n"
    )
    generated = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )
    assert generated.returncode == 0, generated.stderr

    event_log = tmp_path / "ownership-targets.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("chown", "chmod"):
        _write_executable(
            fake_bin / command,
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            f"printf '{command}' >> \"$TARGET_EVENT_LOG\"\n"
            "for arg in \"$@\"; do "
            "printf '|%s' \"$arg\" >> \"$TARGET_EVENT_LOG\"; done\n"
            "printf '\\n' >> \"$TARGET_EVENT_LOG\"\n",
        )
    _write_executable(
        fake_bin / "stat",
        "#!/bin/sh\nprintf 'root:root\\n'\n",
    )
    result = subprocess.run(
        ["bash", "-c", generated.stdout],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "TARGET_EVENT_LOG": str(event_log),
        },
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    targets = event_log.read_text(encoding="utf-8")
    assert "|.git\n" in targets
    assert "|src/app.py\n" in targets
    assert "|src\n" in targets
    for ignored in (
        "backend/.env",
        "uploads",
        "tmp",
        "node_modules",
    ):
        assert ignored not in targets


def test_repository_trust_normalization_makes_tracked_seeds_readable_not_writable(
    tmp_path: Path,
):
    repo = tmp_path / "release"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=repo,
        check=True,
    )
    data_dir = repo / "backend/data"
    data_dir.mkdir(parents=True)
    seed = data_dir / "gene_knowledge.json"
    seed.write_text("{}\n", encoding="utf-8")
    executable = repo / "backend/scripts/probe.sh"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    (repo / ".gitignore").write_text(
        "*.db\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    schedule = data_dir / "celerybeat-schedule.db"
    schedule.write_text("runtime\n", encoding="utf-8")
    data_dir.chmod(0o700)
    seed.chmod(0o600)
    executable.chmod(0o700)
    schedule.chmod(0o600)

    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=root@example.test\n"
        f"DEPLOY_PATH={repo!s}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = (
        f"source {DEPLOY_SCRIPT!s}\n"
        "remote_repository_trust_normalization_command\n"
    )
    generated = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )
    assert generated.returncode == 0, generated.stderr

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ownership_log = tmp_path / "ownership.log"
    _write_executable(
        fake_bin / "chown",
        """#!/bin/sh
set -eu
printf 'chown' >> "$OWNERSHIP_LOG"
for argument in "$@"; do
  printf '|%s' "$argument" >> "$OWNERSHIP_LOG"
done
printf '\n' >> "$OWNERSHIP_LOG"
""",
    )
    _write_executable(fake_bin / "stat", "#!/bin/sh\nprintf 'root:root\\n'\n")
    _write_executable(
        fake_bin / "chmod",
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "args=()\n"
        "for arg in \"$@\"; do\n"
        "  [ \"$arg\" = \"--\" ] || args+=(\"$arg\")\n"
        "done\n"
        "exec /bin/chmod \"${args[@]}\"\n",
    )
    result = subprocess.run(
        ["bash", "-c", generated.stdout],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "OWNERSHIP_LOG": str(ownership_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    ownership_calls = ownership_log.read_text(encoding="utf-8").splitlines()
    for tracked_path in (
        ".gitignore",
        "backend/data/gene_knowledge.json",
        "backend/scripts/probe.sh",
    ):
        assert f"chown|root:root|--|{tracked_path}" in ownership_calls
    for tracked_parent in (
        "backend",
        "backend/data",
        "backend/scripts",
    ):
        assert f"chown|root:root|--|{tracked_parent}" in ownership_calls
    assert all("celerybeat-schedule.db" not in call for call in ownership_calls)
    assert data_dir.stat().st_mode & 0o777 == 0o755
    assert seed.stat().st_mode & 0o777 == 0o644
    assert executable.stat().st_mode & 0o777 == 0o755
    assert schedule.stat().st_mode & 0o777 == 0o600


def test_backend_wraps_runtime_state_in_verified_release_transaction():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    stage_start = script.index("stage_backup_preflight_scripts() {")
    stage_end = script.index(
        "remote_repository_trust_normalization_command() {", stage_start
    )
    stage_body = script[stage_start:stage_end]
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    assert "backend/scripts/runtime_state_release_transaction.py" in stage_body
    for name in (
        "health-backend-runtime-state.conf",
        "celery-worker-runtime-state.conf",
        "celery-beat-runtime-state.conf",
    ):
        assert name in stage_body
    assert "remote_celery_beat_state_migration_command" not in script
    assert "cleanup_legacy_celery_beat_state" not in script

    status = deploy_body.index(
        "inspect_runtime_state_transaction_before_deploy"
    )
    preflight = deploy_body.index(
        "run_runtime_state_transaction \\\n            preflight"
    )
    stop = deploy_body.index("systemctl stop health-backend.socket")
    prepare = deploy_body.index(
        "prepare '$ROLLBACK_CANDIDATE_COMMIT' '$DEPLOY_EXPECTED_SHA'"
    )
    checkout = deploy_body.index("$remote_git_sync")
    install = deploy_body.index(
        "install '$ROLLBACK_CANDIDATE_COMMIT' '$DEPLOY_EXPECTED_SHA'"
    )
    restart = deploy_body.index("systemctl restart celery-worker celery-beat")
    stable_proof = deploy_body.index(
        "prove_health_evidence_runtime_process_flag false", restart
    )
    guard_contract = deploy_body.index(
        'verify_runtime_only_kb_contract "guard"',
        stable_proof,
    )
    commit = deploy_body.index(
        "commit_runtime_state_transaction_after_guard",
        guard_contract,
    )
    floor = deploy_body.index(
        'ROLLBACK_COMMIT="$DEPLOY_EXPECTED_SHA"',
        commit,
    )
    skills = deploy_body.index("wait_for_agent_skills_manifest", floor)
    finalize = deploy_body.index(
        "finalize_runtime_state_transaction_after_all_gates",
        skills,
    )
    assert (
        status
        < preflight
        < stop
        < prepare
        < checkout
        < install
        < restart
        < stable_proof
        < guard_contract
        < commit
        < floor
        < skills
        < finalize
    )


def test_backend_reprobes_stability_process_revision_and_kb_after_skills():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_body = script[script.index("deploy_backend() {") :]
    skills = deploy_body.rindex("wait_for_agent_skills_manifest")
    finalize = deploy_body.index(
        "finalize_runtime_state_transaction_after_all_gates",
        skills,
    )
    terminal_gate_body = deploy_body[skills:finalize]

    for probe in (
        "prove_health_evidence_runtime_process_flag false",
        "verify_deployment",
        "verify_deployed_revision",
        'verify_runtime_only_kb_contract "staged"',
    ):
        assert probe in terminal_gate_body


def test_deactivation_proof_requires_services_stable_across_restart_window():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_deactivated_state() {")
    end = script.index(
        "prove_health_evidence_runtime_process_flag() {", start
    )
    body = script[start:end]

    assert "SERVICE_STABILITY_SECONDS=7" in body
    assert "--property=SubState" in body
    assert "--property=Result" in body
    assert "--property=NRestarts" in body
    assert 'sleep "$SERVICE_STABILITY_SECONDS"' in body
    assert (
        'test "$main_pid" = "${stable_main_pid[$process_index]}"'
        in body
    )
    assert (
        '"${stable_restart_count[$process_index]}"'
        in body
    )
    assert body.count("verify_process_environment_false") >= 2


@pytest.mark.parametrize(
    "failure_mode",
    ("beat-restart", "socket-substate-flip"),
)
def test_deactivation_proof_rejects_restart_of_only_celery_beat(
    tmp_path: Path,
    failure_mode: str,
):
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    proof = script.split(
        "<<'REMOTE_DEACTIVATION_PROOF'\n", 1
    )[1].split("\nREMOTE_DEACTIVATION_PROOF", 1)[0]
    proof_script = tmp_path / "deactivation-proof.sh"
    proof_script.write_text(proof, encoding="utf-8")

    repo = tmp_path / "release"
    (repo / "backend").mkdir(parents=True)
    (repo / "backend" / ".env").write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    release_lock = tmp_path / "release.lock"
    release_lock.mkdir()
    (release_lock / "token").write_text("proof-owner\n", encoding="utf-8")
    runtime_state = tmp_path / "runtime-state"
    systemd_runtime = tmp_path / "systemd-runtime"
    systemd_runtime.mkdir()
    durable_state = tmp_path / "durable-state"
    cgroup_root = tmp_path / "cgroup"
    proc_root = tmp_path / "proc"
    cgroup_root.mkdir()
    proc_root.mkdir()
    unit_pids = {
        "health-backend": 4101,
        "celery-worker": 4201,
        "celery-beat": 4301,
    }
    for unit, pid in unit_pids.items():
        cgroup = cgroup_root / "system.slice" / f"{unit}.service"
        cgroup.mkdir(parents=True)
        (cgroup / "cgroup.procs").write_text(f"{pid}\n", encoding="utf-8")
        process = proc_root / str(pid)
        process.mkdir()
        (process / "environ").write_bytes(
            b"PATH=/usr/bin\0"
            b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0"
        )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    restart_marker = tmp_path / "restart-window.elapsed"
    _write_executable(
        fake_bin / "sleep",
        """#!/bin/sh
set -eu
: > "$FAKE_RESTART_MARKER"
""",
    )
    _write_executable(
        fake_bin / "systemctl",
        """#!/bin/bash
set -euo pipefail
test "$1" = "show"
unit="$2"
name="${unit%.service}"
case "$name" in
  health-backend) pid=4101 ;;
  celery-worker) pid=4201 ;;
  celery-beat) pid=4301 ;;
  health-backend.socket) pid=0 ;;
  *) exit 91 ;;
esac
case "$*" in
  *--property=ActiveState*) printf 'active\n' ;;
  *--property=SubState*)
    if [ "$name" = "health-backend.socket" ]; then
      if [ "${FAKE_SOCKET_FLIP_AFTER_SLEEP:-0}" = "1" ] &&
         [ -e "$FAKE_RESTART_MARKER" ]; then
        printf 'listening\n'
      else
        printf 'running\n'
      fi
    else
      printf 'running\n'
    fi
    ;;
  *--property=Result*) printf 'success\n' ;;
  *--property=MainPID*) printf '%s\n' "$pid" ;;
  *--property=NRestarts*)
    if [ "${FAKE_BEAT_RESTART_AFTER_SLEEP:-0}" = "1" ] &&
       [ "$name" = "celery-beat" ] &&
       [ -e "$FAKE_RESTART_MARKER" ]; then
      printf '1\n'
    else
      printf '0\n'
    fi
    ;;
  *--property=ActiveEnterTimestampMonotonic*)
    if [ "${FAKE_BEAT_RESTART_AFTER_SLEEP:-0}" = "1" ] &&
       [ "$name" = "celery-beat" ] &&
       [ -e "$FAKE_RESTART_MARKER" ]; then
      printf '200\n'
    else
      printf '100\n'
    fi
    ;;
  *--property=ControlGroup*)
    printf '/system.slice/%s.service\n' "$name"
    ;;
  *) exit 92 ;;
esac
""",
    )
    result = subprocess.run(
        [
            "bash",
            str(proof_script),
            str(repo),
            str(durable_state),
            str(release_lock),
            "proof-owner",
            "-",
            str(runtime_state),
            str(systemd_runtime),
            str(cgroup_root),
            str(proc_root),
        ],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_RESTART_MARKER": str(restart_marker),
            "FAKE_BEAT_RESTART_AFTER_SLEEP": (
                "1" if failure_mode == "beat-restart" else "0"
            ),
            "FAKE_SOCKET_FLIP_AFTER_SLEEP": (
                "1" if failure_mode == "socket-substate-flip" else "0"
            ),
        },
    )

    assert result.returncode != 0, (result.stdout, result.stderr)
    assert restart_marker.exists()


def test_socket_ready_state_is_portable_but_stable_across_proofs():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = deploy.index("prove_health_evidence_deactivated_state() {")
    deploy_end = deploy.index(
        "prove_health_evidence_runtime_process_flag() {", deploy_start
    )
    activation = (
        ROOT
        / "backend"
        / "scripts"
        / "activate_health_evidence_runtime.sh"
    ).read_text(encoding="utf-8")
    rollback = (
        ROOT / "backend" / "scripts" / "rollback_release.sh"
    ).read_text(encoding="utf-8")

    for body in (deploy[deploy_start:deploy_end], activation, rollback):
        assert "listening|running" in body
        assert 'stable_socket_sub_state="$sub_state"' in body
        assert '"$sub_state" = "$stable_socket_sub_state"' in body
        assert "*) return 1 ;;" in body


def test_activation_and_rollback_proofs_reject_restart_windows():
    activation = (
        ROOT
        / "backend"
        / "scripts"
        / "activate_health_evidence_runtime.sh"
    ).read_text(encoding="utf-8")
    rollback = (
        ROOT / "backend" / "scripts" / "rollback_release.sh"
    ).read_text(encoding="utf-8")

    for body in (activation, rollback):
        assert "SERVICE_STABILITY_SECONDS=7" in body
        assert "--property=NRestarts" in body
        assert "--property=SubState" in body
        assert "--property=Result" in body
        assert 'sleep "$SERVICE_STABILITY_SECONDS"' in body


def test_backup_and_health_score_failures_block_deploy():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    backup_start = script.index("backup_database() {")
    backup_end = script.index("# 记录当前 commit", backup_start)
    backup_body = script[backup_start:backup_end]
    verify_start = script.index("verify_deployment() {")
    verify_end = script.index("wait_for_agent_skills_manifest()", verify_start)
    verify_body = script[verify_start:verify_end]

    assert "print_warning \"数据库备份失败" not in backup_body
    assert "return 1" in backup_body
    assert "健康度检查跳过" not in verify_body
    assert "健康度脚本无有效输出" in verify_body


def test_health_score_failure_reports_critical_gate_detail():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    verify_start = script.index("verify_deployment() {")
    verify_end = script.index("wait_for_agent_skills_manifest()", verify_start)
    verify_body = script[verify_start:verify_end]

    assert "critical_failures" in verify_body
    assert "agent_runtime_circuit" in verify_body
    assert "健康度硬闸" in verify_body


def test_deploy_health_gate_proves_garmin_worker_affinity():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    verify_start = script.index("verify_deployment() {")
    verify_end = script.index("wait_for_agent_skills_manifest()", verify_start)
    verify_body = script[verify_start:verify_end]

    assert "systemctl show health-backend --property=ExecStart --value" in verify_body
    assert '[[ "$BACKEND_EXEC_START" != *"--workers 1"* ]]' in verify_body
    assert "Garmin MFA 单 worker 约束未生效" in verify_body


def test_backend_proves_rollback_schema_before_live_env_mutation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    backup = deploy_body.index("backup_database")
    rollback_point = deploy_body.index("save_rollback_point")
    rollback_probe = deploy_body.index(
        "verify_rollback_point_schema_compatibility"
    )
    sync_env = deploy_body.index("sync_env")

    assert backup < rollback_point < rollback_probe < sync_env


def test_backend_runs_bundle_and_runtime_preflight_before_live_mutation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    rollback_probe = deploy_body.index(
        "verify_rollback_point_schema_compatibility"
    )
    bundle = deploy_body.index("upload_deploy_bundle", rollback_probe)
    preflight = deploy_body.index(
        "run_runtime_state_transaction \\\n            preflight",
        bundle,
    )
    sync_env = deploy_body.index("sync_env", preflight)
    preserve = deploy_body.index(
        "_REMOTE_RELEASE_LOCK_ABANDONED=1",
        sync_env,
    )
    deactivate = deploy_body.index(
        "deactivate_health_evidence_runtime_before_mutation",
        preserve,
    )

    assert (
        rollback_probe
        < bundle
        < preflight
        < sync_env
        < preserve
        < deactivate
    )


def test_adopted_release_lock_is_preserved_before_transaction_inspection(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "ssh.events"
    adopted_stage = (
        f"/tmp/health-app-backup-preflight-{os.getpid()}-"
        f"{tmp_path.stat().st_ino}"
    )
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REVA_RELEASE_LOCK_ADOPT=1
REVA_RELEASE_LOCK_TOKEN=owner
ssh() {{
    printf 'ssh\\n' >> "$ADOPT_EVENT_LOG"
    printf '%s\\n' \
      'REMOTE_RELEASE_LOCK_ADOPTED stage={adopted_stage}'
}}
acquire_remote_release_lock deploy:backend
test "$_REMOTE_RELEASE_LOCK_ADOPTED" -eq 1
test "$_REMOTE_RELEASE_LOCK_ABANDONED" -eq 1
cleanup_remote_release_artifacts
test "$(wc -l < "$ADOPT_EVENT_LOG")" -eq 1
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "ADOPT_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_rollback_sha_is_recorded_only_after_schema_probe_success():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    save_start = script.index("save_rollback_point() {")
    save_end = script.index(
        "verify_rollback_point_schema_compatibility() {",
        save_start,
    )
    save_body = script[save_start:save_end]
    verify_start = save_end
    verify_end = script.index("# 回滚到上一个版本", verify_start)
    verify_body = script[verify_start:verify_end]

    assert 'ROLLBACK_CANDIDATE_COMMIT="$rollback_commit"' in save_body
    assert 'ROLLBACK_COMMIT="$rollback_commit"' not in save_body
    assert "sha256sum --strict -c staged.sha256" in verify_body
    assert "source .env" not in verify_body
    assert "env -u MIGRATION_DATABASE_URL" in verify_body
    assert "ROLLBACK_POINT_SCHEMA_OK commit=" in verify_body
    probe_success = verify_body.index(
        'if [[ "$probe_output" != *"ROLLBACK_SCHEMA_PROBE_OK tables="* ||'
    )
    record = verify_body.index(
        'ROLLBACK_COMMIT="$ROLLBACK_CANDIDATE_COMMIT"'
    )
    assert probe_success < record


def test_guard_probes_full_schema_before_starting_any_backend_writer():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]
    guard_end = deploy_body.index("CODE_EXIT=$?")
    guard_body = deploy_body[:guard_end]

    stop_socket = guard_body.index("systemctl stop health-backend.socket")
    stop_backend = guard_body.index("systemctl stop health-backend &&")
    stop_celery = guard_body.index(
        "systemctl stop celery-worker celery-beat"
    )
    checkout = guard_body.index("$remote_git_sync")
    dependency_sync = guard_body.index("$remote_dependency_sync")
    migration = guard_body.index("python scripts/apply_managed_migrations.py")
    lease_before_migration = guard_body.index(
        "test -r '$REMOTE_RELEASE_LOCK_DIR/token'",
        dependency_sync,
    )
    stage_recheck = guard_body.index(
        "sha256sum --strict -c staged.sha256",
        migration,
    )
    schema_probe = guard_body.index(
        "verify_runtime_schema_compatibility.py"
    )
    lease_after_probe = guard_body.index(
        "test -r '$REMOTE_RELEASE_LOCK_DIR/token'",
        schema_probe,
    )
    restart_socket = guard_body.index(
        "systemctl restart health-backend.socket"
    )
    restart_backend = guard_body.index("systemctl restart health-backend &&")
    restart_celery = guard_body.index(
        "systemctl restart celery-worker celery-beat"
    )

    assert (
        stop_socket
        < stop_backend
        < stop_celery
        < checkout
        < dependency_sync
        < lease_before_migration
        < migration
        < stage_recheck
        < schema_probe
        < lease_after_probe
        < restart_socket
        < restart_backend
        < restart_celery
    )


def test_guard_lost_lease_after_pip_never_runs_migration_or_restarts_writers(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    remote_repo = tmp_path / "remote"
    backend = remote_repo / "backend"
    fake_bin = tmp_path / "bin"
    lease_dir = tmp_path / "release-lock"
    stage_dir = tmp_path / "stage"
    event_log = tmp_path / "events"
    migration_marker = tmp_path / "migration-ran"
    fake_migration_env = tmp_path / "migration.env"
    backend.mkdir(parents=True)
    fake_bin.mkdir()
    lease_dir.mkdir()
    stage_dir.mkdir()
    (backend / "venv" / "bin").mkdir(parents=True)
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={remote_repo}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    (backend / ".env").write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    (backend / "venv" / "bin" / "activate").write_text(
        ":\n",
        encoding="utf-8",
    )
    fake_migration_env.write_text(
        "MIGRATION_DATABASE_URL=postgresql://migration-role@example/health\n",
        encoding="utf-8",
    )
    (lease_dir / "token").write_text("lease-token\n", encoding="utf-8")
    (stage_dir / "staged.sha256").write_text(
        "stage evidence remains\n",
        encoding="utf-8",
    )
    runtime_helper = stage_dir / "runtime_state_release_transaction.py"
    runtime_helper.write_text(
        "import sys\n"
        "print('RUNTIME_STATE_TRANSACTION_OK command=' + sys.argv[1])\n",
        encoding="utf-8",
    )
    _write_executable(
        fake_bin / "systemctl",
        """#!/usr/bin/env bash
printf 'systemctl:%s\\n' "$*" >> "$FAKE_EVENT_LOG"
if [ "$1" = "show" ]; then
    printf 'inactive\\n'
fi
""",
    )
    _write_executable(
        fake_bin / "pip",
        """#!/usr/bin/env bash
printf 'pip:%s\\n' "$*" >> "$FAKE_EVENT_LOG"
rm -f "$FAKE_LEASE_DIR/token"
""",
    )
    _write_executable(
        fake_bin / "python",
        """#!/usr/bin/env bash
printf 'python:%s\\n' "$*" >> "$FAKE_EVENT_LOG"
if [ "$1" = "scripts/apply_managed_migrations.py" ]; then
    : > "$FAKE_MIGRATION_MARKER"
fi
""",
    )
    _write_root_owned_stat_shim(fake_bin / "stat")
    _write_executable(fake_bin / "sync", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "mv",
        """#!/bin/sh
set -eu
test "$1" = "-fT"
test "$2" = "--"
/bin/mv -f "$3" "$4"
""",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA={'2' * 40}
REQUIREMENTS_LOCK_SHA={'3' * 64}
SYSTEM_KB_INPUT_SHA={'4' * 64}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_DIR={lease_dir!s}
REMOTE_RELEASE_STATE_DIR={(tmp_path / 'release-state')!s}
REMOTE_RELEASE_LOCK_TOKEN=lease-token
REMOTE_BACKUP_PREFLIGHT_DIR={stage_dir!s}
REMOTE_RUNTIME_STATE_RUNNER={runtime_helper!s}
validate_runtime_only_kb_staging() {{ :; }}
assert_remote_release_lock_if_acquired() {{ :; }}
assert_remote_release_lock() {{ :; }}
backup_database() {{ :; }}
determine_system_kb_activation_need() {{ SYSTEM_KB_ACTIVATION_REQUIRED=0; }}
save_rollback_point() {{ ROLLBACK_CANDIDATE_COMMIT={'1' * 40}; }}
verify_rollback_point_schema_compatibility() {{
    ROLLBACK_COMMIT="$ROLLBACK_CANDIDATE_COMMIT"
}}
sync_env() {{ :; }}
    deactivate_health_evidence_runtime_before_mutation() {{ :; }}
    upload_deploy_bundle() {{ :; }}
    run_runtime_state_transaction() {{ :; }}
    remote_git_sync_command() {{ printf ':'; }}
    ssh() {{
    shift
    local command="$*"
    command="${{command//\\/etc\\/health-app\\/migration.env/$FAKE_MIGRATION_ENV}}"
    PATH="$FAKE_BIN:$PATH" bash -c "$command"
}}
if (deploy_backend); then exit 91; fi
test -d "$REMOTE_RELEASE_LOCK_DIR"
test -d "$REMOTE_BACKUP_PREFLIGHT_DIR"
test -f "$REMOTE_BACKUP_PREFLIGHT_DIR/staged.sha256"
test ! -e "$FAKE_MIGRATION_MARKER"
test ! -e "$REMOTE_RELEASE_LOCK_DIR/token"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FAKE_BIN": str(fake_bin),
            "FAKE_EVENT_LOG": str(event_log),
            "FAKE_LEASE_DIR": str(lease_dir),
            "FAKE_MIGRATION_ENV": str(fake_migration_env),
            "FAKE_MIGRATION_MARKER": str(migration_marker),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not migration_marker.exists()
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert any(event.startswith("pip:") for event in events)
    assert not any(
        event.startswith("python:")
        and (
            "scripts/apply_managed_migrations.py" in event
            or "verify_runtime_schema_compatibility.py" in event
        )
        for event in events
    )
    assert not any("restart" in event for event in events)
    assert {
        event.removeprefix("systemctl:")
        for event in events
        if event.startswith("systemctl:stop ")
    } >= {
        "stop health-backend.socket",
        "stop health-backend",
        "stop celery-worker celery-beat",
    }


def test_unknown_guard_transaction_failure_never_starts_concurrent_rollback():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]
    failure_start = deploy_body.index("if [ $CODE_EXIT -ne 0 ]; then")
    failure_end = deploy_body.index(
        "if ! prove_health_evidence_runtime_process_flag false",
        failure_start,
    )
    failure_body = deploy_body[failure_start:failure_end]

    assert "rollback_deploy" not in failure_body
    assert "_REMOTE_RELEASE_LOCK_DELEGATED=0" not in failure_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in failure_body
    assert "transaction terminal" in failure_body


def test_runtime_state_commit_disconnect_preserves_lease_without_rollback(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=owner
DEPLOY_EXPECTED_SHA={'a' * 40}
assert_remote_release_lock() {{ :; }}
run_runtime_state_transaction() {{
    printf 'commit-rpc\\n' >> "$COMMIT_EVENT_LOG"
    return 255
}}
rollback_deploy() {{
    printf 'rollback\\n' >> "$COMMIT_EVENT_LOG"
}}
commit_runtime_state_transaction_after_guard
commit_rc=$?
printf 'rc=%s delegated=%s abandoned=%s\\n' \
    "$commit_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$COMMIT_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "COMMIT_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "commit-rpc",
        "rc=1 delegated=1 abandoned=1",
    ]


def test_runtime_state_finalize_disconnect_preserves_lease_without_rollback(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=owner
DEPLOY_EXPECTED_SHA={'a' * 40}
assert_remote_release_lock() {{ :; }}
run_runtime_state_transaction() {{
    printf 'finalize-rpc\\n' >> "$FINALIZE_EVENT_LOG"
    return 255
}}
rollback_deploy() {{
    printf 'rollback\\n' >> "$FINALIZE_EVENT_LOG"
}}
finalize_runtime_state_transaction_after_all_gates
finalize_rc=$?
printf 'rc=%s delegated=%s abandoned=%s\\n' \
    "$finalize_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$FINALIZE_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FINALIZE_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "finalize-rpc",
        "rc=1 delegated=1 abandoned=1",
    ]


def test_runtime_state_status_adopts_journal_authoritative_release(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    old_sha = "a" * 40
    candidate_sha = "b" * 40
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA={candidate_sha}
run_runtime_state_transaction() {{
    printf '%s\\n' \
      'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=PREPARED old_sha={old_sha} candidate_sha={candidate_sha} gate_armed=true gate_released=false release_target=none next_action=install state_source=journal'
}}
ssh() {{
    case "$*" in
      *"rev-parse HEAD"*) printf '%s\\n' '{old_sha}' ;;
      *) return 0 ;;
    esac
}}
inspect_runtime_state_transaction_before_deploy
test "$RUNTIME_STATE_RESUME_PHASE" = PREPARED
test "$RUNTIME_STATE_RESUME_TARGET" = none
test "$ROLLBACK_CANDIDATE_COMMIT" = {old_sha}
test "$ROLLBACK_COMMIT" = {old_sha}
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_runtime_state_status_rejects_other_candidate_and_preserves_lease(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA={'b' * 40}
run_runtime_state_transaction() {{
    printf '%s\\n' \
      'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=INSTALLED old_sha={'a' * 40} candidate_sha={'c' * 40} gate_armed=true gate_released=false release_target=none next_action=candidate-guard state_source=journal'
}}
set +e
inspect_runtime_state_transaction_before_deploy
inspect_rc=$?
test "$inspect_rc" -ne 0
test "$_REMOTE_RELEASE_LOCK_ABANDONED" -eq 1
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


@pytest.mark.parametrize(
    ("phase", "remote_head", "env_proof_ok"),
    (
        ("INSTALLED", "c" * 40, True),
        ("PREPARED", "a" * 40, False),
    ),
)
def test_runtime_state_resume_proof_failure_preserves_stage_and_lease(
    tmp_path: Path,
    phase: str,
    remote_head: str,
    env_proof_ok: bool,
):
    env_file = tmp_path / "deploy.env"
    stage = tmp_path / "release-stage"
    lock_dir = tmp_path / "release-lock"
    stage.mkdir()
    lock_dir.mkdir()
    (stage / "backend.env.rollback").write_text("rollback")
    (lock_dir / "token").write_text("owner")
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    old_sha = "a" * 40
    candidate_sha = "b" * 40
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
DEPLOY_EXPECTED_SHA={candidate_sha}
REMOTE_BACKUP_PREFLIGHT_DIR={stage!s}
REMOTE_RELEASE_LOCK_DIR={lock_dir!s}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=owner
run_runtime_state_transaction() {{
    printf '%s\\n' \
      'RUNTIME_STATE_TRANSACTION_OK command=status result=phase={phase} old_sha={old_sha} candidate_sha={candidate_sha} gate_armed=true gate_released=false release_target=none next_action=install state_source=journal'
}}
ssh() {{
    case "$*" in
      *"rev-parse HEAD"*) printf '%s\\n' '{remote_head}' ;;
      *) [ '{1 if env_proof_ok else 0}' = 1 ] ;;
    esac
}}
inspect_runtime_state_transaction_before_deploy
inspect_rc=$?
set -e
test "$inspect_rc" -ne 0
test "$_REMOTE_RELEASE_LOCK_ABANDONED" -eq 1
cleanup_remote_release_artifacts
test -d "$REMOTE_BACKUP_PREFLIGHT_DIR"
test -f "$REMOTE_BACKUP_PREFLIGHT_DIR/backend.env.rollback"
test -d "$REMOTE_RELEASE_LOCK_DIR"
test -f "$REMOTE_RELEASE_LOCK_DIR/token"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


def test_committed_journal_resumes_post_commit_gates_before_finalize(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    old_sha = "a" * 40
    candidate_sha = "b" * 40
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA={candidate_sha}
run_runtime_state_transaction() {{
    printf '%s\\n' "$1" >> "$STATUS_EVENT_LOG"
    test "$1" = status
    printf '%s\\n' \
      'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=COMMITTED old_sha={old_sha} candidate_sha={candidate_sha} gate_armed=false gate_released=true release_target=candidate next_action=finalize state_source=journal'
}}
ssh() {{
    case "$*" in
      *"rev-parse HEAD"*) printf '%s\\n' '{candidate_sha}' ;;
      *) return 0 ;;
    esac
}}
inspect_runtime_state_transaction_before_deploy
test "$RUNTIME_STATE_RESUME_PHASE" = COMMITTED
test "$RUNTIME_STATE_ALREADY_FINALIZED" -eq 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "STATUS_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == ["status"]


def test_terminal_marker_cleanup_is_idempotent_before_read_only_post_gates(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    old_sha = "a" * 40
    candidate_sha = "b" * 40
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA={candidate_sha}
assert_remote_release_lock() {{ :; }}
run_runtime_state_transaction() {{
    printf '%s\\n' "$1" >> "$STATUS_EVENT_LOG"
    if [ "$1" = status ]; then
        printf '%s\\n' \
          'RUNTIME_STATE_TRANSACTION_OK command=status result=phase=COMMITTED old_sha={old_sha} candidate_sha={candidate_sha} gate_armed=false gate_released=true release_target=candidate next_action=finalize state_source=terminal'
    else
        test "$1" = finalize
        test "$2" = {candidate_sha}
        printf '%s\\n' \
          'RUNTIME_STATE_TRANSACTION_OK command=finalize result=finalized'
    fi
}}
ssh() {{
    case "$*" in
      *"rev-parse HEAD"*) printf '%s\\n' '{candidate_sha}' ;;
      *) return 0 ;;
    esac
}}
inspect_runtime_state_transaction_before_deploy
test "$RUNTIME_STATE_ALREADY_FINALIZED" -eq 1
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "STATUS_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "status",
        "finalize",
    ]


def test_remote_release_lock_rejects_shell_metacharacters_before_ssh(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    ssh_marker = tmp_path / "ssh-called"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_RELEASE_LOCK_DIR="/tmp/release-lock';touch /tmp/injected"
ssh() {{ : > "$SSH_MARKER"; }}
set +e
acquire_remote_release_lock test
lock_rc=$?
test "$lock_rc" -eq 70
test ! -e "$SSH_MARKER"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "SSH_MARKER": str(ssh_marker),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not ssh_marker.exists()


@pytest.mark.parametrize(
    (
        "runtime_dir",
        "upload_dir",
        "skills_cache_dir",
        "dedao_dir",
        "legacy_enabled",
        "allowed",
    ),
    (
        (
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase/workspace",
            "false",
            True,
        ),
        (
            "/opt/health-app/backend/data",
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase/workspace",
            "false",
            False,
        ),
        (
            "/var/lib/health-app/runtime",
            "/opt/health-app/backend/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase/workspace",
            "false",
            False,
        ),
        (
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/uploads",
            "/opt/health-app/.health-skills-cache",
            "/var/lib/health-app/dedao-kbase/workspace",
            "false",
            False,
        ),
        (
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase-review",
            "false",
            False,
        ),
        (
            "/var/lib/health-app/runtime",
            "/var/lib/health-app/uploads",
            "/var/cache/health-app/skills-hub",
            "/var/lib/health-app/dedao-kbase/workspace",
            "true",
            False,
        ),
    ),
)
def test_env_guard_requires_canonical_external_runtime_paths(
    tmp_path: Path,
    runtime_dir: str,
    upload_dir: str,
    skills_cache_dir: str,
    dedao_dir: str,
    legacy_enabled: str,
    allowed: bool,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "APP_ENV=production\n"
        "DEBUG=False\n"
        f"HEALTH_RUNTIME_DATA_DIR={runtime_dir}\n"
        f"HEALTH_UPLOAD_DIR={upload_dir}\n"
        f"HEALTH_SKILLS_CACHE_DIR={skills_cache_dir}\n"
        f"DEDAO_KBASE_REVIEW_ARTIFACT_DIR={dedao_dir}\n"
        f"LEGACY_KNOWLEDGE_RUNTIME_ENABLED={legacy_enabled}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
scp() {{ return 1; }}
validate_env_sync_safety
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert (result.returncode == 0) is allowed, (
        result.stdout,
        result.stderr,
    )


def test_plain_ssh_write_failures_preserve_server_lease_for_reconciliation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    for function_name, next_marker in (
        ("backup_database() {", "# 记录当前 commit"),
        ("backup_remote_env() {", "upload_backend_env_file() {"),
        ("restart_frontend_service() {", "# 推送代码到 GitHub"),
        ("deploy_frontend() {", "validate_runtime_only_kb_staging() {"),
    ):
        start = script.index(function_name)
        end = script.index(next_marker, start)
        body = script[start:end]
        assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in body


def test_release_cleanup_abandons_server_lease_on_hup_int_and_term():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("install_release_cleanup_traps() {")
    end = script.index("acquire_remote_release_lock() {", start)
    body = script[start:end]

    assert "abandon_remote_release_lock 129" in body
    assert "abandon_remote_release_lock 130" in body
    assert "abandon_remote_release_lock 143" in body


def test_env_sync_uses_external_backup_root_and_mode_0600():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'REMOTE_BACKUP_ROOT="${HEALTH_BACKUP_ROOT:-/var/backups/health-app}"' in script
    assert 'ENV_BACKUP_DIR="$REMOTE_BACKUP_ROOT/env"' in script
    assert 'cp -p .env "$ENV_BACKUP_DIR/.env.${BACKUP_TS}"' in script
    assert 'install -o root -g health-app -m 0640' in script


def test_env_sync_stages_candidate_and_only_deactivation_atomically_installs_live_env():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    upload_start = script.index("upload_backend_env_file() {")
    upload_end = script.index("validate_env_sync_safety() {", upload_start)
    upload_body = script[upload_start:upload_end]
    transaction_start = script.index(
        "run_health_evidence_deactivation_transaction() {"
    )
    transaction_end = script.index(
        "prove_health_evidence_deactivated_state() {",
        transaction_start,
    )
    transaction_body = script[transaction_start:transaction_end]
    execution_body = transaction_body[
        transaction_body.index("mutation_started=1") :
    ]

    assert "REMOTE_BACKEND_ENV_CANDIDATE" in upload_body
    assert "sha256sum -c" in upload_body
    assert 'scp "$temp_env" "$SERVER:$REMOTE_PATH/backend/.env"' not in upload_body
    assert 'mv -fT "$candidate_install_tmp" "$target_env"' in transaction_body
    helper_start = transaction_body.index("install_candidate_env() {")
    helper_end = transaction_body.index(
        "remove_runtime_authorization() {", helper_start
    )
    helper_body = transaction_body[helper_start:helper_end]
    install = helper_body.index(
        'install -o root -g health-app -m 0640'
    )
    sync_tmp = helper_body.index('sync -f "$candidate_install_tmp"')
    rename = helper_body.index(
        'mv -fT "$candidate_install_tmp" "$target_env"'
    )
    sync_parent = helper_body.index('sync -f "$target_env_dir"')
    assert install < sync_tmp < rename < sync_parent
    assert "install_candidate_env" in execution_body


def test_deploy_accepts_main_or_detached_exact_origin_main_only():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'CURRENT_BRANCH="$(git branch --show-current)"' in script
    assert '[[ -n "$CURRENT_BRANCH" && "$CURRENT_BRANCH" != "main" ]]' in script
    assert 'if [[ "$CURRENT_BRANCH" == "main" ]]' in script
    assert "git push origin HEAD:main" in script
    assert 'git rev-parse refs/remotes/origin/main' in script
    assert "git ls-remote origin refs/heads/main" in script
    assert "git push kuaishou HEAD:main" in script


def test_remote_checkout_and_post_deploy_revision_match_expected_sha():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "DEPLOY_EXPECTED_SHA" in script
    assert "verify_deployed_revision" in script
    assert "git rev-parse HEAD" in script
    assert "远端部署版本不匹配" in script


def test_automatic_rollback_uses_verified_release_runner_and_propagates_failure():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    rollback_start = script.index("rollback_deploy() {")
    rollback_end = script.index("# 部署后验证", rollback_start)
    rollback_body = script[rollback_start:rollback_end]

    assert "if ! rollback_output=$(ssh" in rollback_body
    assert "return 1" in rollback_body
    assert "git checkout $ROLLBACK_COMMIT -- ." not in rollback_body
    assert "kb_quarantine=passed" in rollback_body
    assert "REMOTE_ROLLBACK_RUNNER" in rollback_body
    assert "$REMOTE_PATH/backend/scripts/rollback_release.sh" not in rollback_body
    assert "rollback_output=" in rollback_body
    assert "ROLLBACK_OK commit=$ROLLBACK_COMMIT kb_quarantine=passed" in rollback_body


@pytest.mark.parametrize(
    ("runtime_state_marker", "accepted"),
    (
        ("runtime_state=restored", True),
        ("runtime_state=candidate-retained", True),
        ("", False),
        ("runtime_state=unknown", False),
        ("runtime_state=restored-extra", False),
    ),
)
def test_automatic_rollback_accepts_only_terminal_runtime_state_values(
    tmp_path: Path,
    runtime_state_marker: str,
    accepted: bool,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    rollback_commit = "a" * 40
    marker = (
        f"ROLLBACK_OK commit={rollback_commit} "
        "kb_quarantine=passed schema_probe=passed auth_probe=passed "
        "services=active process_flag=false"
    )
    if runtime_state_marker:
        marker += f" {runtime_state_marker}"
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
ROLLBACK_COMMIT={rollback_commit}
ssh() {{ printf '%s\\n' "$FAKE_ROLLBACK_OUTPUT"; }}
rollback_deploy
rollback_rc=$?
printf 'ROLLBACK_RESULT rc=%s delegated=%s abandoned=%s\\n' \
    "$rollback_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED"
exit 0
"""

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FAKE_ROLLBACK_OUTPUT": marker,
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    expected = (
        "ROLLBACK_RESULT rc=0 delegated=0 abandoned=0"
        if accepted
        else "ROLLBACK_RESULT rc=1 delegated=1 abandoned=1"
    )
    assert expected in result.stdout


def test_release_preflight_stages_rollback_code_and_failed_release_manifest():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    stage_start = script.index("stage_backup_preflight_scripts() {")
    stage_end = script.index("remote_git_sync_command()", stage_start)
    stage_body = script[stage_start:stage_end]

    assert "rollback_release.sh" in stage_body
    assert "verify_locked_requirements.py" in stage_body
    assert "verify_runtime_schema_compatibility.py" in stage_body
    assert "quarantine_runtime_only_kb.py" in stage_body
    assert "review_manifest.json" in stage_body
    assert "shasum -a 256" in stage_body
    assert "sha256sum" in stage_body
    assert "git cat-file -e" in stage_body
    assert "git show" in stage_body
    assert "staged.sha256" in stage_body


def test_release_env_snapshots_are_sealed_into_verified_stage_before_deactivation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    seal_start = script.index("seal_release_env_snapshots() {")
    seal_end = script.index("require_canonical_env_assignment() {", seal_start)
    seal_body = script[seal_start:seal_end]
    sync_start = script.index("sync_env() {")
    sync_end = script.index("# 去激活事务", sync_start)
    sync_body = script[sync_start:sync_end]
    deploy_body = script[script.index("deploy_backend() {") :]

    for snapshot in ("backend.env.rollback", "backend.env.candidate"):
        assert snapshot in seal_body
    assert "sha256sum --strict -c staged.sha256" in seal_body
    assert '" = "15"' in seal_body
    assert sync_body.index("upload_backend_env_file") < sync_body.index(
        "seal_release_env_snapshots"
    )
    assert deploy_body.index("sync_env") < deploy_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )


def test_deploy_does_not_claim_services_are_blocked_when_rollback_fails():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "服务保持阻断状态" not in script
    assert "无法证明服务已停止" in script


def test_all_mode_captures_old_backend_sha_before_frontend_checkout(tmp_path):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "deploy.events"
    old_sha = "1" * 40
    new_sha = "2" * 40
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_HEAD={old_sha}
acquire_release_lock() {{ :; }}
acquire_remote_release_lock() {{
    _REMOTE_RELEASE_LOCK_ACQUIRED=1
    _REMOTE_RELEASE_LOCK_DELEGATED=0
    _REMOTE_RELEASE_LOCK_ABANDONED=0
}}
install_release_cleanup_traps() {{ :; }}
assert_remote_release_lock() {{ :; }}
confirm_ota_drift() {{ :; }}
push_code() {{
    DEPLOY_EXPECTED_SHA={new_sha}
    printf 'push\\n' >> "$DEPLOY_EVENT_LOG"
}}
ssh() {{ printf '%s\\n' "$REMOTE_HEAD"; }}
deploy_frontend() {{
    REMOTE_HEAD={new_sha}
    printf 'frontend-checkout:%s\\n' "$REMOTE_HEAD" >> "$DEPLOY_EVENT_LOG"
}}
deploy_backend() {{
    save_rollback_point
    verify_rollback_point_schema_compatibility
    printf 'backend-floor:%s\\n' "$ROLLBACK_COMMIT" >> "$DEPLOY_EVENT_LOG"
    REMOTE_HEAD={new_sha}
}}
verify_rollback_point_schema_compatibility() {{
    ROLLBACK_COMMIT="$ROLLBACK_CANDIDATE_COMMIT"
}}
check_status() {{ printf 'status\\n' >> "$DEPLOY_EVENT_LOG"; }}
main --all --yes
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "DEPLOY_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "push",
        f"backend-floor:{old_sha}",
        f"frontend-checkout:{new_sha}",
        "status",
    ]


def test_frontend_build_refuses_revision_mismatch_before_npm_or_pm2(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "frontend.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
assert_remote_release_lock_if_acquired() {{ :; }}
verify_deployed_revision() {{ return 1; }}
ssh() {{ printf 'ssh:%s\\n' "$*" >> "$FRONTEND_EVENT_LOG"; }}
if deploy_frontend; then exit 91; fi
test ! -e "$FRONTEND_EVENT_LOG"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FRONTEND_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not event_log.exists()


def test_frontend_build_same_sha_does_not_mutate_runtime_or_backend_services(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    event_log = tmp_path / "frontend.events"
    durable = tmp_path / "enabled.env"
    durable_bytes = (
        b"# commit=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        b"# guard_sha256=" + b"b" * 64 + b"\n"
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
    )
    durable.write_bytes(durable_bytes)
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
assert_remote_release_lock_if_acquired() {{ :; }}
verify_deployed_revision() {{
    printf 'revision\\n' >> "$FRONTEND_EVENT_LOG"
}}
ssh() {{
    printf 'ssh:%s\\n' "$*" >> "$FRONTEND_EVENT_LOG"
    case "$*" in
      *systemctl*|*health-backend*|*celery*) return 92 ;;
    esac
}}
deploy_frontend
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "FRONTEND_EVENT_LOG": str(event_log),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert durable.read_bytes() == durable_bytes
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert events[0] == "revision"
    assert events[-1] == "revision"
    assert len([event for event in events if event.startswith("ssh:")]) == 1
    assert all("systemctl" not in event for event in events)
    assert all("health-backend" not in event for event in events)
    assert all("celery" not in event for event in events)


def test_env_candidate_upload_interruption_never_touches_live_env(
    tmp_path: Path,
):
    repo = tmp_path / "release"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    live_env = backend / ".env"
    live_bytes = (
        b"SECRET_VALUE=production-secret\n"
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
    )
    live_env.write_bytes(live_bytes)
    stage = tmp_path / "stage"
    stage.mkdir(mode=0o700)
    release_lock = tmp_path / "release.lock"
    release_lock.mkdir()
    token = "env-stage-owner"
    (release_lock / "token").write_text(token + "\n", encoding="utf-8")
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={repo}\n"
        "SECRET_VALUE=new-secret\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "scp",
        """#!/bin/bash
set -euo pipefail
source="$1"
destination="${2#*:}"
if [ "${FAKE_SCP_INTERRUPT:-0}" = "1" ]; then
  /usr/bin/head -c 8 "$source" > "$destination"
  exit 74
fi
/bin/cp "$source" "$destination"
""",
    )
    _write_executable(
        bin_dir / "install",
        """#!/bin/bash
set -euo pipefail
source="${@: -2:1}"
target="${@: -1}"
/bin/cp "$source" "$target"
chmod 0400 "$target"
""",
    )
    _write_executable(
        bin_dir / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
if [ -d "$target" ]; then
  printf 'root:root:700\n'
else
  printf 'root:root:400\n'
fi
""",
    )
    _write_executable(
        bin_dir / "sync",
        "#!/bin/bash\nset -euo pipefail\ntest \"$1\" = -f\ntest -e \"$2\"\n",
    )
    _write_executable(
        bin_dir / "mv",
        "#!/bin/bash\nset -euo pipefail\ntest \"$1\" = -fT\n/bin/mv \"$2\" \"$3\"\n",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_BACKUP_PREFLIGHT_DIR={stage}
REMOTE_BACKEND_ENV_CANDIDATE={stage / "backend.env.candidate"}
REMOTE_RELEASE_LOCK_DIR={release_lock}
REMOTE_RELEASE_LOCK_TOKEN={token}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
ssh() {{ shift; "$@"; }}
upload_backend_env_file "$ENV_FILE"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DEPLOY_ENV_FILE": str(deploy_env),
            "FAKE_SCP_INTERRUPT": "1",
        },
    )

    assert result.returncode != 0
    assert live_env.read_bytes() == live_bytes
    assert not (stage / "backend.env.candidate").exists()


def test_backend_deploy_establishes_guard_floor_before_system_kb_activation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    restart = deploy_body.index("systemctl restart health-backend")
    first_health = deploy_body.index("if ! verify_deployment; then")
    first_revision = deploy_body.index("verify_deployed_revision", first_health)
    guard_contract = deploy_body.index(
        'verify_runtime_only_kb_contract "guard"',
        first_health,
    )
    guard_floor = deploy_body.index("ROLLBACK_COMMIT=\"$DEPLOY_EXPECTED_SHA\"")
    phase0_seed = deploy_body.index("python scripts/seed_system_kb_phase0.py")
    v2_import = deploy_body.index("python scripts/import_system_kb_v2_artifacts.py")
    second_health = deploy_body.index(
        "if ! verify_deployment; then",
        first_health + 1,
    )

    staged_contract = deploy_body.index(
        'verify_runtime_only_kb_contract "staged"',
        second_health,
    )

    assert (
        restart
        < first_health
        < first_revision
        < guard_contract
        < guard_floor
        < phase0_seed
        < v2_import
        < second_health
        < staged_contract
    )


def test_backend_deploy_requires_runtime_only_feature_flag_off_during_guard_rollout():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    validator_start = script.index("validate_runtime_only_kb_staging() {")
    validator_end = script.index("deploy_backend() {", validator_start)
    validator_body = script[validator_start:validator_end]
    deploy_body = script[validator_end:]

    assert "review_manifest.json" in validator_body
    assert "generic_serving_allowed" in validator_body
    assert "HEALTH_EVIDENCE_RUNTIME_ENABLED" in validator_body
    assert "false" in validator_body
    assert 'pack.get("serving_allowed") is True' not in validator_body
    assert deploy_body.index("validate_runtime_only_kb_staging") < deploy_body.index(
        "sync_env"
    )


def test_backend_revokes_durable_runtime_before_checkout_or_kb_mutation():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_start = script.index("deploy_backend() {")
    deploy_body = script[deploy_start:]

    sync_guard = deploy_body.index("sync_env")
    revoke = deploy_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )
    checkout = deploy_body.index("$remote_git_sync")
    migration = deploy_body.index("python scripts/apply_managed_migrations.py")
    kb_import = deploy_body.index(
        "python scripts/import_system_kb_v2_artifacts.py"
    )

    assert sync_guard < revoke < checkout < migration < kb_import

    deactivation_start = script.index(
        "run_health_evidence_deactivation_transaction() {"
    )
    deactivation_end = script.index(
        "prove_health_evidence_deactivated_state() {", deactivation_start
    )
    deactivation = script[deactivation_start:deactivation_end]
    execution = deactivation[deactivation.index("mutation_started=1") :]
    assert "enabled.env" in deactivation
    assert "sync -f" in deactivation
    assert "HEALTH_EVIDENCE_RUNTIME_ENABLED=false" in deactivation
    assert "cgroup.procs" in deactivation
    assert "health-backend.socket" in deactivation
    assert 'systemctl stop "$unit"' in deactivation
    assert 'systemctl start "$unit"' in deactivation
    assert (
        "stop_and_prove_services_inactive() {"
        in deactivation
    )
    assert "verify_services_inactive" in deactivation
    stop = execution.index("stop_and_prove_services_inactive")
    branch_start = execution.index(
        'if [ "$legacy_flag_bootstrap" -eq 1 ]; then'
    )
    branch_else = execution.index("\nelse\n", branch_start)
    branch_end = execution.index(
        "\nfi\nverify_flag_file_false", branch_else
    )
    bootstrap_branch = execution[branch_start:branch_else]
    standard_branch = execution[branch_else:branch_end]
    start = execution.index('systemctl start "$unit"')
    process_false = execution.index("verify_process_environment_false")
    assert stop < branch_start < branch_end < start < process_false
    assert bootstrap_branch.index(
        "install_candidate_env"
    ) < bootstrap_branch.index("remove_runtime_authorization")
    assert standard_branch.index(
        "remove_runtime_authorization"
    ) < standard_branch.index("install_candidate_env")


def test_deactivation_delegates_before_remote_stage_or_live_mutation_and_proves_last_restart():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    sync_start = script.index("sync_env() {")
    sync_end = script.index("# 去激活事务", sync_start)
    sync_body = script[sync_start:sync_end]
    orchestration_start = script.index(
        "deactivate_health_evidence_runtime_before_mutation() {"
    )
    orchestration_end = script.index("# 部署后端", orchestration_start)
    orchestration = script[orchestration_start:orchestration_end]
    deploy_body = script[script.index("deploy_backend() {") :]

    assert sync_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < sync_body.index(
        "upload_backend_env_file"
    )
    assert orchestration.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        orchestration.index("run_health_evidence_deactivation_transaction")
    )
    assert orchestration.index(
        "run_health_evidence_deactivation_transaction"
    ) < orchestration.index("prove_health_evidence_deactivated_state")
    assert orchestration.index("prove_health_evidence_deactivated_state") < (
        orchestration.index("_REMOTE_RELEASE_LOCK_DELEGATED=0")
    )
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in orchestration

    last_backend_restart = deploy_body.index(
        "systemctl restart health-backend"
    )
    assert last_backend_restart < deploy_body.index(
        "prove_health_evidence_runtime_process_flag false",
        last_backend_restart,
    )


def test_guard_kb_and_rollback_never_overlap_unknown_remote_transactions():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_body = script[script.index("deploy_backend() {") :]
    rollback_start = script.index("rollback_deploy() {")
    rollback_end = script.index("# 部署后验证", rollback_start)
    rollback_body = script[rollback_start:rollback_end]
    guard_start = deploy_body.index("# 3. Guard phase")
    kb_start = deploy_body.index("# 5. KB activation phase")
    guard_body = deploy_body[guard_start:kb_start]
    kb_body = deploy_body[kb_start:]

    assert guard_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        guard_body.index("ssh $SERVER")
    )
    assert "远端事务结果不明确" in guard_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in guard_body
    assert kb_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        kb_body.index("ssh $SERVER")
    )
    assert "不与可能仍运行的 importer 并发回滚" in kb_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in kb_body
    assert rollback_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1") < (
        rollback_body.index("ssh")
    )
    assert rollback_body.index("_REMOTE_RELEASE_LOCK_DELEGATED=0") > (
        rollback_body.index("ROLLBACK_OK")
    )


def test_generic_env_and_restart_revoke_durable_runtime_before_restart():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    env_start = main_body.index('"env")')
    env_end = main_body.index('"health-evidence")', env_start)
    env_body = main_body[env_start:env_end]
    restart_start = main_body.index('"restart")', env_end)
    restart_end = main_body.index('"push")', restart_start)
    restart_body = main_body[restart_start:restart_end]

    assert env_body.index("sync_env") < env_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    )
    assert "restart_services" not in env_body
    assert restart_body.index(
        "deactivate_health_evidence_runtime_before_mutation"
    ) < restart_body.index("restart_frontend_service")


def test_frontend_only_never_mutates_backend_checkout_or_runtime_authorization():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    frontend_start = main_body.index('"frontend")')
    frontend_end = main_body.index('"backend")', frontend_start)
    frontend_body = main_body[frontend_start:frontend_end]
    deploy_start = script.index("deploy_frontend() {")
    deploy_end = script.index("validate_runtime_only_kb_staging() {", deploy_start)
    deploy_body = script[deploy_start:deploy_end]

    assert "deactivate_health_evidence_runtime_before_mutation" not in frontend_body
    assert deploy_body.count("verify_deployed_revision") == 2
    assert deploy_body.index("verify_deployed_revision") < deploy_body.index(
        "npm ci"
    )
    assert deploy_body.count(
        "git status --porcelain --untracked-files=all"
    ) == 2
    assert "remote_git_sync" not in deploy_body
    assert "git checkout" not in deploy_body


def test_post_import_staged_contract_failure_uses_quarantine_rollback():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    deploy_body = script[script.index("deploy_backend() {"):]
    contract_call = deploy_body.index(
        'verify_runtime_only_kb_contract "staged"'
    )
    rollback_call = deploy_body.index("rollback_deploy", contract_call)
    exit_call = deploy_body.index("exit 1", rollback_call)

    assert contract_call < rollback_call < exit_call


def test_health_evidence_activation_is_delegated_to_persistent_systemd_transaction():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("activate_health_evidence_runtime() {")
    end = script.index("# 查看服务状态", start)
    body = script[start:end]
    runner_start = script.index("run_health_evidence_activation_unit() {")
    runner_end = script.index(
        "prove_health_evidence_activation_state() {", runner_start
    )
    runner_body = script[runner_start:runner_end]
    proof_start = runner_end
    proof_end = script.index(
        "prove_health_evidence_activation_not_launched() {", proof_start
    )
    proof_body = script[proof_start:proof_end]

    adopted_branch = body.index('if [[ "$adopted" = "1" ]]')
    adopted_stage = body.index(
        "stage_health_evidence_activation_artifacts",
        adopted_branch,
    )
    adopted_enabled_proof = body.index(
        "prove_health_evidence_activation_state",
        adopted_stage,
    )
    adopted_not_launched = body.index(
        "prove_health_evidence_activation_not_launched",
        adopted_enabled_proof,
    )
    precheck = body.index(
        'verify_runtime_only_kb_contract "staged"',
        adopted_not_launched,
    )
    stage_delegated = body.index("_REMOTE_RELEASE_LOCK_DELEGATED=1", precheck)
    capability = body.index(
        "verify_systemd_activation_capability",
        stage_delegated,
    )
    fresh_branch = body.index('if [[ "$adopted" != "1" ]]', capability)
    stage = body.index(
        "stage_health_evidence_activation_artifacts",
        fresh_branch,
    )
    stage_clear = body.index("_REMOTE_RELEASE_LOCK_DELEGATED=0", stage)
    launch_delegated = body.index(
        "_REMOTE_RELEASE_LOCK_DELEGATED=1", stage_clear
    )
    launch = body.index("run_health_evidence_activation_unit")
    deadman = runner_body.index("ExecStopPost")
    recover_mode = runner_body.index("--recover-if-unverified")

    assert (
        adopted_branch
        < adopted_stage
        < adopted_enabled_proof
        < adopted_not_launched
        < precheck
        < stage_delegated
        < capability
        < fresh_branch
        < stage
        < stage_clear
        < launch_delegated
        < launch
    )
    assert deadman >= 0
    assert recover_mode >= 0
    assert "systemd-run" in runner_body
    assert "require_health_evidence_flag_value true" in body
    assert "sync_env" not in body
    assert "upload_backend_env_file" not in body
    assert "restart_health_runtime_services" not in body
    assert 'HEALTH_EVIDENCE_ACTIVATION_OK commit=$expected_sha' in proof_body
    assert "_REMOTE_RELEASE_LOCK_ABANDONED=1" in body


def test_activation_stage_hashes_runner_candidate_guard_and_keeps_marker_outside():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("stage_health_evidence_activation_artifacts() (")
    end = script.index("activate_health_evidence_runtime() {", start)
    body = script[start:end]

    assert "activate_health_evidence_runtime.sh" in body
    assert "candidate.env" in body
    assert "guard.env" in body
    assert "staged.sha256" in body
    assert "sha256sum" in body
    assert "require_health_evidence_flag_value false" in body
    assert "require_health_evidence_flag_value true" in body
    assert "REMOTE_ACTIVATION_SUCCESS_MARKER" in body
    assert "dirname" not in body or "REMOTE_BACKUP_PREFLIGHT_DIR" in body


def test_activation_proof_uses_durable_authorization_and_real_process_flags():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_activation_state() {")
    end = script.index(
        "prove_health_evidence_services_inactive() {", start
    )
    proof = script[start:end]

    assert "REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR" in proof
    assert "guard_sha256" in proof
    assert "cgroup.procs" in proof
    assert "verify_process_environment" in proof
    assert 'HEALTH_EVIDENCE_RUNTIME_ENABLED=true' in proof
    assert 'flag_is_exact "$repo/backend/.env" false' in proof
    assert 'cmp -s "$guard_env" "$repo/backend/.env"' in proof
    assert 'cmp -s "$candidate_env" "$repo/backend/.env"' not in proof
    assert "verify_git_metadata_trust" in proof
    assert "verify_tracked_worktree_trust" in proof
    assert "verify_repo_revision" in proof
    assert "GIT_CONFIG_NOSYSTEM=1" in proof
    assert 'GIT_CONFIG_GLOBAL="$protected_config"' in proof
    assert 'GIT_OBJECT_DIRECTORY="$git_dir/objects"' in proof
    assert "GIT_OPTIONAL_LOCKS=0" in proof
    assert "/usr/bin/git --no-optional-locks --no-replace-objects" in proof
    assert '--git-dir="$proof_git"' in proof
    assert '--work-tree="$repo"' in proof
    assert '-c "safe.directory=$repo"' not in proof
    assert "-c core.fsmonitor=false" in proof
    assert "-c core.hooksPath=/dev/null" in proof


def test_activation_proof_derives_space_bearing_markers_on_remote_side():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_activation_state() {")
    end = script.index(
        "prove_health_evidence_activation_not_launched() {", start
    )
    proof = script[start:end]
    ssh_prefix = 'ssh "$SERVER" bash -s -- \\'
    remote_start = proof.index(ssh_prefix)
    heredoc_start = proof.index("<<'REMOTE_ACTIVATION_PROOF'", remote_start)
    ssh_argv = proof[remote_start + len(ssh_prefix) : heredoc_start]
    argv = [
        line.strip().removesuffix("\\").strip()
        for line in ssh_argv.splitlines()
        if line.strip()
    ]
    remote = proof[heredoc_start:]

    # OpenSSH joins command arguments into one remote shell command. Marker
    # strings contain spaces, so sending them as argv silently shifts every
    # following positional parameter. Pin the exact ordered argv contract,
    # and independently make the remote reject any future extra argument.
    assert argv == [
        '"$phase"',
        '"$unit_name"',
        '"$REMOTE_PATH"',
        '"$DEPLOY_EXPECTED_SHA"',
        '"$REMOTE_BACKUP_PREFLIGHT_DIR/candidate.env"',
        '"$REMOTE_BACKUP_PREFLIGHT_DIR/guard.env"',
        '"$REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR"',
        '"$REMOTE_ACTIVATION_SUCCESS_MARKER"',
        '"${REMOTE_ACTIVATION_SUCCESS_MARKER}.outcome"',
        '"$REMOTE_RELEASE_LOCK_DIR"',
        '"$REMOTE_RELEASE_LOCK_TOKEN"',
    ]
    argc_check = remote.index('test "$#" -eq 11')
    first_assignment = remote.index('phase="$1"')
    assert argc_check < first_assignment
    assert 'expected_outcome="${10}"' not in remote
    assert 'expected_success="${11}"' not in remote
    assert 'release_lock="${10}"' in remote
    assert 'release_token="${11}"' in remote
    runner = (
        ROOT / "backend/scripts/activate_health_evidence_runtime.sh"
    ).read_text(encoding="utf-8")
    expected_markers = (
        "HEALTH_EVIDENCE_ACTIVATION_OK commit=$expected_sha flag=true "
        "health=passed auth_probe=passed score=passed contract=enabled "
        "services=active",
        "HEALTH_EVIDENCE_DEADMAN_NOOP commit=$expected_sha "
        "authorization=verified",
        "HEALTH_EVIDENCE_DEADMAN_RECOVERED commit=$expected_sha flag=false "
        "health=passed contract=staged services=active",
    )
    marker_pattern = re.compile(
        r'"(HEALTH_EVIDENCE_(?:ACTIVATION_OK|DEADMAN_'
        r'(?:NOOP|RECOVERED))[^"\n]*)"'
    )
    remote_markers = tuple(marker_pattern.findall(remote))
    runner_markers = tuple(
        marker.replace("$EXPECTED_SHA", "$expected_sha")
        for marker in marker_pattern.findall(runner)
    )
    assert sorted(remote_markers) == sorted(expected_markers)
    assert sorted(runner_markers) == sorted(expected_markers)
    assert sorted(remote_markers) == sorted(runner_markers)

    phase_case = remote[remote.index('case "$phase" in') :]
    enabled_start = phase_case.index("enabled)")
    staged_start = phase_case.index("staged)", enabled_start)
    invalid_start = phase_case.index("*)", staged_start)
    case_end = phase_case.index("esac", invalid_start)
    enabled_body = phase_case[enabled_start:staged_start]
    staged_body = phase_case[staged_start:invalid_start]
    invalid_body = phase_case[invalid_start:case_end]
    assert enabled_body.count("expected_outcome=") == 1
    assert "HEALTH_EVIDENCE_DEADMAN_NOOP" in enabled_body
    assert "HEALTH_EVIDENCE_DEADMAN_RECOVERED" not in enabled_body
    assert staged_body.count("expected_outcome=") == 1
    assert "HEALTH_EVIDENCE_DEADMAN_RECOVERED" in staged_body
    assert "HEALTH_EVIDENCE_DEADMAN_NOOP" not in staged_body
    assert "expected_outcome=" not in invalid_body
    assert "exit 2" in invalid_body


def test_activation_process_flag_awk_executes_on_posix_awk():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    proof_start = script.index("prove_health_evidence_activation_state() {")
    proof_end = script.index(
        "prove_health_evidence_activation_not_launched() {", proof_start
    )
    proof = script[proof_start:proof_end]
    process_start = proof.index("verify_process_environment() {")
    process_end = proof.index("\nverify_repo_revision\n", process_start)
    process_proof = proof[process_start:process_end]
    awk_program_match = re.search(
        r'awk -v expected="\$expected" \'(?P<program>.*?)\n\s*\'',
        process_proof,
        re.DOTALL,
    )

    assert awk_program_match is not None
    result = subprocess.run(
        ["awk", "-v", "expected=true", awk_program_match.group("program")],
        input="HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_activation_proof_marker_checks_are_byte_exact(tmp_path: Path):
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("prove_health_evidence_activation_state() {")
    end = script.index(
        "prove_health_evidence_activation_not_launched() {", start
    )
    proof = script[start:end]
    outcome_check = (
        'cmp -s "$outcome_file" '
        '<(printf \'%s\\n\' "$expected_outcome")'
    )
    success_check = (
        'cmp -s "$success_marker" '
        '<(printf \'%s\\n\' "$expected_success")'
    )

    assert outcome_check in proof
    assert success_check in proof
    assert 'test "$(cat "$outcome_file")" = "$expected_outcome"' not in proof
    assert 'test "$(cat "$success_marker")" = "$expected_success"' not in proof

    harness = (
        "set -euo pipefail\n"
        'outcome_file="$1"\n'
        'success_marker="$2"\n'
        'expected_outcome="$3"\n'
        'expected_success="$4"\n'
        f"{outcome_check}\n"
        f"{success_check}\n"
    )
    expected_outcome = "known outcome"
    expected_success = "known success"
    cases = (
        ("exact", b"known outcome\n", b"known success\n", True),
        ("outcome-missing-lf", b"known outcome", b"known success\n", False),
        ("outcome-extra-lf", b"known outcome\n\n", b"known success\n", False),
        ("success-missing-lf", b"known outcome\n", b"known success", False),
        ("success-extra-lf", b"known outcome\n", b"known success\n\n", False),
    )
    for label, outcome_bytes, success_bytes, should_pass in cases:
        outcome_file = tmp_path / f"{label}.outcome"
        success_file = tmp_path / f"{label}.success"
        outcome_file.write_bytes(outcome_bytes)
        success_file.write_bytes(success_bytes)
        result = subprocess.run(
            [
                "bash",
                "-c",
                harness,
                "--",
                str(outcome_file),
                str(success_file),
                expected_outcome,
                expected_success,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert (result.returncode == 0) is should_pass, (
            label,
            result.stdout,
            result.stderr,
        )


def test_release_preflight_hashes_activation_runner_for_rollback_floor():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    stage_start = script.index("stage_backup_preflight_scripts() {")
    stage_end = script.index("remote_git_sync_command()", stage_start)
    stage_body = script[stage_start:stage_end]
    rollback = (
        ROOT / "backend/scripts/rollback_release.sh"
    ).read_text(encoding="utf-8")

    assert "activate_health_evidence_runtime.sh" in stage_body
    assert "activate_health_evidence_runtime.sh" in rollback


def test_cli_has_dedicated_health_evidence_activation_mode():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "--activate-health-evidence" in script
    assert 'DEPLOY_MODE="health-evidence"' in script
    assert "activate_health_evidence_runtime" in script


def test_cli_has_secret_free_app_store_review_reset_mode():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("reset_app_store_review_demo() {")
    end = script.index("\n# 查看服务状态", start)
    body = script[start:end]

    assert "--reset-app-store-review" in script
    assert 'DEPLOY_MODE="app-store-review-reset"' in script
    assert "verify_deployed_revision" in body
    assert "APP_STORE_REVIEW_DEMO_ACCOUNT" in body
    assert "APP_STORE_REVIEW_DEMO_PASSWORD" in body
    assert "--secret-free" in body
    assert "APP_STORE_REVIEW_RESET_OK" in body
    assert "--rotate-password" not in body


def test_health_evidence_flag_parser_only_accepts_one_canonical_assignment(
    tmp_path,
):
    cases = (
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=false", "false", True),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=true", "true", True),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=1", "false", False),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=yes", "false", False),
        ("HEALTH_EVIDENCE_RUNTIME_ENABLED=on", "false", False),
        ('HEALTH_EVIDENCE_RUNTIME_ENABLED="true"', "false", False),
        ("export HEALTH_EVIDENCE_RUNTIME_ENABLED=true", "false", False),
        (
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=true",
            "false",
            False,
        ),
    )
    for index, (assignments, expected, allowed) in enumerate(cases):
        env_file = tmp_path / f"deploy-{index}.env"
        env_file.write_text(
            "\n".join(
                (
                    "DEPLOY_SERVER=fake-server",
                    "DEPLOY_PATH=/tmp/fake-health-app",
                    assignments,
                )
            )
            + "\n",
            encoding="utf-8",
        )
        harness = f"""
source {DEPLOY_SCRIPT!s}
require_health_evidence_flag_value {expected}
"""
        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        )
        assert (result.returncode == 0) is allowed, (
            assignments,
            result.stdout,
            result.stderr,
        )


def test_generic_env_and_restart_paths_require_canonical_false():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_start = script.index("main() {")
    main_body = script[main_start:]

    env_start = main_body.index('"env")')
    env_end = main_body.index('"health-evidence")', env_start)
    restart_start = main_body.index('"restart")', env_end)
    restart_end = main_body.index('"push")', restart_start)
    assert "require_health_evidence_flag_value false" in main_body[env_start:env_end]
    assert (
        "require_health_evidence_flag_value false"
        in main_body[restart_start:restart_end]
    )


def test_mutating_deploy_modes_acquire_server_release_lease():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    main_body = script[script.index("main() {") :]
    acquire = main_body.index('acquire_remote_release_lock "deploy:${DEPLOY_MODE}"')
    execute = main_body.index("# 执行对应操作")

    assert acquire < execute
    assert (
        '"all"|"frontend"|"backend"|"env"|"health-evidence"|"app-store-review-reset"|"restart"'
        in main_body
    )
    assert "assert_remote_release_lock" in main_body[acquire:execute]
    assert "push" not in main_body[acquire - 100 : acquire]


def test_server_release_lease_rejects_second_owner_and_only_owner_can_release(
    tmp_path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    remote_lock = tmp_path / "remote-release.lock"
    harness = f"""
source {DEPLOY_SCRIPT!s}
ssh() {{ shift; "$@"; }}
REVA_RELEASE_LOCK_TOKEN=owner-one
acquire_remote_release_lock first
first_token="$REMOTE_RELEASE_LOCK_TOKEN"
_REMOTE_RELEASE_LOCK_ACQUIRED=0
REMOTE_RELEASE_LOCK_TOKEN=
REVA_RELEASE_LOCK_TOKEN=owner-two
if acquire_remote_release_lock second; then
    exit 91
fi
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=wrong-owner
if release_remote_release_lock; then
    exit 92
fi
test -d "$REMOTE_RELEASE_LOCK_DIR"
REMOTE_RELEASE_LOCK_TOKEN="$first_token"
release_remote_release_lock
test ! -e "$REMOTE_RELEASE_LOCK_DIR"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "REMOTE_RELEASE_LOCK_DIR": str(remote_lock),
        },
    )

    assert result.returncode == 0, (result.stdout, result.stderr)


@pytest.mark.parametrize(
    "mode",
    (
        "all",
        "frontend",
        "backend",
        "env",
        "health-evidence",
        "app-store-review-reset",
        "restart",
    ),
)
def test_each_terminal_release_mode_arms_adopted_stage_cleanup(
    tmp_path: Path,
    mode: str,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
_REMOTE_RELEASE_LOCK_DELEGATED=0
arm_remote_release_cleanup_after_terminal_mode_success {mode}
printf 'delegated=%s abandoned=%s\\n' \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.strip() == "delegated=0 abandoned=0"


def test_terminal_release_mode_preserves_adopted_stage_while_delegated(
    tmp_path: Path,
):
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
_REMOTE_RELEASE_LOCK_DELEGATED=1
arm_remote_release_cleanup_after_terminal_mode_success backend
rc=$?
printf 'rc=%s delegated=%s abandoned=%s\\n' \
    "$rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED"
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "rc=73 delegated=1 abandoned=1" in result.stdout


def test_adopted_terminal_activation_proof_removes_stage_state_and_lease(
    tmp_path: Path,
):
    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-"
        f"{tmp_path.stat().st_ino}"
    )
    state_dir = Path(f"{stage}.activation-state")
    for path in (stage, state_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(mode=0o700)
    (stage / "sealed").write_text("immutable\n", encoding="utf-8")
    (state_dir / "success").write_text("terminal\n", encoding="utf-8")
    remote_lock = tmp_path / "release.lock"
    remote_lock.mkdir()
    token = "activation-owner"
    for name, value in (
        ("token", token),
        ("label", "deploy:health-evidence"),
        ("stage", str(stage)),
        ("started_at", "2026-07-30T12:00:00Z"),
    ):
        (remote_lock / name).write_text(value + "\n", encoding="utf-8")
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={tmp_path / 'remote-app'}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
set_remote_backup_preflight_dir {stage}
REMOTE_RELEASE_LOCK_DIR={remote_lock}
REMOTE_RELEASE_LOCK_TOKEN={token}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
ssh() {{
    shift
    if [ "${{1:-}}" = bash ] && [ "${{2:-}}" = -s ]; then
        "$@"
    else
        test "$#" -eq 1
        bash -c "$1"
    fi
}}
require_health_evidence_flag_value() {{ return 0; }}
verify_deployed_revision() {{ return 0; }}
stage_health_evidence_activation_artifacts() {{ return 0; }}
prove_health_evidence_activation_state() {{ test "$1" = enabled; }}
verify_runtime_only_kb_contract() {{ exit 91; }}
verify_systemd_activation_capability() {{ exit 92; }}
run_health_evidence_activation_unit() {{ exit 93; }}
prove_health_evidence_activation_not_launched() {{ exit 94; }}
activate_health_evidence_runtime
test "$_REMOTE_RELEASE_LOCK_ABANDONED" = 0
test "$_REMOTE_RELEASE_LOCK_DELEGATED" = 0
cleanup_remote_release_artifacts
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "DEPLOY_ENV_FILE": str(env_file)},
        )

        assert result.returncode == 0, (result.stdout, result.stderr)
        assert not stage.exists()
        assert not state_dir.exists()
        assert not remote_lock.exists()
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(state_dir, ignore_errors=True)


_ADOPTED_STAGE_ARTIFACTS = (
    ("backup_db.sh", "backend/scripts/backup_db.sh"),
    ("verify_backup_restore.sh", "backend/scripts/verify_backup_restore.sh"),
    ("archive_backup_offsite.sh", "backend/scripts/archive_backup_offsite.sh"),
    ("rollback_release.sh", "backend/scripts/rollback_release.sh"),
    (
        "verify_locked_requirements.py",
        "backend/scripts/verify_locked_requirements.py",
    ),
    (
        "activate_health_evidence_runtime.sh",
        "backend/scripts/activate_health_evidence_runtime.sh",
    ),
    (
        "verify_runtime_schema_compatibility.py",
        "backend/scripts/verify_runtime_schema_compatibility.py",
    ),
    (
        "quarantine_runtime_only_kb.py",
        "backend/scripts/quarantine_runtime_only_kb.py",
    ),
    (
        "runtime_state_release_transaction.py",
        "backend/scripts/runtime_state_release_transaction.py",
    ),
    (
        "review_manifest.json",
        "backend/data/system_kb_v2_seed/review_manifest.json",
    ),
    (
        "health-backend-runtime-state.conf",
        "infra/systemd/dropins/health-backend-runtime-state.conf",
    ),
    (
        "celery-worker-runtime-state.conf",
        "infra/systemd/dropins/celery-worker-runtime-state.conf",
    ),
    (
        "celery-beat-runtime-state.conf",
        "infra/systemd/dropins/celery-beat-runtime-state.conf",
    ),
)


def _write_immutable_adopted_stage(
    stage: Path,
    *,
    source_repo: Path,
    release_sha: str,
    candidate_env: bytes,
) -> None:
    stage.mkdir(mode=0o700)
    for staged_name, repository_path in _ADOPTED_STAGE_ARTIFACTS:
        payload = subprocess.check_output(
            ["git", "show", f"{release_sha}:{repository_path}"],
            cwd=source_repo,
        )
        target = stage / staged_name
        target.write_bytes(payload)
        target.chmod(0o400)
    for name, payload in (
        ("backend.env.rollback", candidate_env),
        ("backend.env.candidate", candidate_env),
    ):
        target = stage / name
        target.write_bytes(payload)
        target.chmod(0o400)

    manifest_lines = []
    for path in sorted(stage.iterdir(), key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {path.name}")
    manifest = stage / "staged.sha256"
    manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    manifest.chmod(0o400)


def _immutable_stage_snapshot(
    stage: Path,
) -> tuple[int, int, dict[str, tuple[int, str, bytes]]]:
    files = {}
    for path in sorted(stage.iterdir(), key=lambda item: item.name):
        payload = path.read_bytes()
        files[path.name] = (
            path.stat().st_ino,
            hashlib.sha256(payload).hexdigest(),
            payload,
        )
    metadata = stage.stat()
    return metadata.st_ino, metadata.st_mtime_ns, files


def _run_adopted_release_stage_harness(
    tmp_path: Path,
    *,
    scenario: str,
) -> dict[str, object]:
    source_repo = tmp_path / "release-source"
    source_repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=source_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=source_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=source_repo,
        check=True,
    )
    for _, repository_path in _ADOPTED_STAGE_ARTIFACTS:
        target = source_repo / repository_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / repository_path).read_bytes())
    subprocess.run(["git", "add", "."], cwd=source_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "release fixture"],
        cwd=source_repo,
        check=True,
    )
    release_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo,
        text=True,
    ).strip()
    old_sha = "1" * 40
    status_candidate_sha = (
        "f" * 40 if scenario == "wrong-sha" else release_sha
    )
    if status_candidate_sha == old_sha:
        old_sha = "2" * 40

    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-"
        f"{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    candidate_env = (
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        b"HEALTH_RUNTIME_DATA_DIR=/var/lib/health-app/runtime\n"
        b"HEALTH_UPLOAD_DIR=/var/lib/health-app/uploads\n"
        b"HEALTH_SKILLS_CACHE_DIR=/var/cache/health-app/skills-hub\n"
        b"DEDAO_KBASE_REVIEW_ARTIFACT_DIR="
        b"/var/lib/health-app/dedao-kbase/workspace\n"
        b"LEGACY_KNOWLEDGE_RUNTIME_ENABLED=false\n"
    )
    _write_immutable_adopted_stage(
        stage,
        source_repo=source_repo,
        release_sha=release_sha,
        candidate_env=candidate_env,
    )
    if scenario == "unsealed-allowed-name":
        unsealed = stage / "candidate.env"
        unsealed.write_bytes(candidate_env)
        unsealed.chmod(0o400)
    stage_before = _immutable_stage_snapshot(stage)

    remote_path = tmp_path / "remote-app"
    (remote_path / "backend").mkdir(parents=True)
    (remote_path / "backend/.env").write_bytes(candidate_env)
    remote_lock = tmp_path / "remote-release.lock"
    remote_lock.mkdir()
    token = "resume-owner"
    label = "deploy:backend"
    (remote_lock / "token").write_text(token + "\n", encoding="utf-8")
    (remote_lock / "label").write_text(label + "\n", encoding="utf-8")
    (remote_lock / "stage").write_text(str(stage) + "\n", encoding="utf-8")
    (remote_lock / "started_at").write_text(
        "2026-07-30T12:00:00Z\n",
        encoding="utf-8",
    )

    attempted_token = "wrong-owner" if scenario == "wrong-token" else token
    attempted_label = (
        "deploy:frontend" if scenario == "wrong-label" else label
    )
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={remote_path}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    event_log = tmp_path / "adoption.events"
    proof_file = tmp_path / "adoption.proof"
    mkdir_log = tmp_path / "mkdir.events"
    scp_log = tmp_path / "scp.events"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
case "$target" in
  "$FAKE_ADOPTED_STAGE") printf 'root:root:700\n' ;;
  "$FAKE_ADOPTED_STAGE/staged.sha256"|\
"$FAKE_ADOPTED_STAGE/backend.env.candidate"|\
staged.sha256|backend.env.candidate)
    printf 'root:root:400\n'
    ;;
  *) exit 97 ;;
esac
""",
    )
    _write_executable(
        fake_bin / "mkdir",
        """#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FAKE_MKDIR_LOG"
exec /bin/mkdir "$@"
""",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_RELEASE_LOCK_DIR="$FAKE_REMOTE_LOCK"
REVA_RELEASE_LOCK_ADOPT=1
REVA_RELEASE_LOCK_TOKEN="$ATTEMPTED_TOKEN"
DEPLOY_EXPECTED_SHA="$EXPECTED_RELEASE_SHA"
ssh() {{
    shift
    if [ "${{1:-}}" = bash ] && [ "${{2:-}}" = -s ]; then
        "$@"
        return
    fi
    if [ "$#" -eq 1 ]; then
        case "$1" in
          *"rev-parse HEAD"*) printf '%s\\n' "$FAKE_REMOTE_HEAD" ;;
          *) bash -c "$1" ;;
        esac
        return
    fi
    "$@"
}}
scp() {{
    printf '%s\\n' "$*" >> "$FAKE_SCP_LOG"
    return 99
}}
run_runtime_state_transaction() {{
    test "$1" = status
    printf '%s\\n' \
      "RUNTIME_STATE_TRANSACTION_OK command=status result=phase=PREPARED old_sha=$STATUS_OLD_SHA candidate_sha=$STATUS_CANDIDATE_SHA gate_armed=true gate_released=false release_target=none next_action=install state_source=journal"
}}

printf 'acquire\\n' >> "$ADOPTION_EVENT_LOG"
if acquire_remote_release_lock "$ATTEMPTED_LABEL"; then
    :
else
    acquire_rc=$?
    printf 'acquire-failed:%s\\n' "$acquire_rc" >> "$ADOPTION_EVENT_LOG"
    exit 81
fi
test "$REMOTE_BACKUP_PREFLIGHT_DIR" = "$FAKE_ADOPTED_STAGE"
test "$REMOTE_RUNTIME_STATE_RUNNER" = \
    "$FAKE_ADOPTED_STAGE/runtime_state_release_transaction.py"
printf 'stage\\n' >> "$ADOPTION_EVENT_LOG"
if stage_backup_preflight_scripts; then
    :
else
    stage_rc=$?
    printf 'stage-failed:%s\\n' "$stage_rc" >> "$ADOPTION_EVENT_LOG"
    exit 82
fi
printf 'inspect\\n' >> "$ADOPTION_EVENT_LOG"
if inspect_runtime_state_transaction_before_deploy; then
    :
else
    inspect_rc=$?
    printf 'inspect-failed:%s\\n' "$inspect_rc" >> "$ADOPTION_EVENT_LOG"
    exit 83
fi
printf 'stage=%s adopted=%s phase=%s candidate=%s\\n' \
    "$REMOTE_BACKUP_PREFLIGHT_DIR" \
    "$_REMOTE_RELEASE_LOCK_ADOPTED" \
    "$RUNTIME_STATE_RESUME_PHASE" \
    "$STATUS_CANDIDATE_SHA" \
    > "$ADOPTION_PROOF_FILE"
printf 'complete\\n' >> "$ADOPTION_EVENT_LOG"
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=source_repo,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "DEPLOY_ENV_FILE": str(env_file),
                "FAKE_REMOTE_LOCK": str(remote_lock),
                "FAKE_ADOPTED_STAGE": str(stage),
                "FAKE_REMOTE_HEAD": old_sha,
                "FAKE_MKDIR_LOG": str(mkdir_log),
                "FAKE_SCP_LOG": str(scp_log),
                "ADOPTION_EVENT_LOG": str(event_log),
                "ADOPTION_PROOF_FILE": str(proof_file),
                "ATTEMPTED_TOKEN": attempted_token,
                "ATTEMPTED_LABEL": attempted_label,
                "EXPECTED_RELEASE_SHA": release_sha,
                "STATUS_OLD_SHA": old_sha,
                "STATUS_CANDIDATE_SHA": status_candidate_sha,
            },
        )
        stage_after = _immutable_stage_snapshot(stage)
        return {
            "result": result,
            "stage": str(stage),
            "stage_before": stage_before,
            "stage_after": stage_after,
            "events": (
                event_log.read_text(encoding="utf-8").splitlines()
                if event_log.exists()
                else []
            ),
            "proof": (
                proof_file.read_text(encoding="utf-8")
                if proof_file.exists()
                else ""
            ),
            "mkdir_calls": (
                mkdir_log.read_text(encoding="utf-8").splitlines()
                if mkdir_log.exists()
                else []
            ),
            "scp_calls": (
                scp_log.read_text(encoding="utf-8").splitlines()
                if scp_log.exists()
                else []
            ),
        }
    finally:
        shutil.rmtree(stage)


def test_existing_remote_release_is_adopted_without_mutating_immutable_stage(
    tmp_path: Path,
):
    outcome = _run_adopted_release_stage_harness(
        tmp_path,
        scenario="valid",
    )
    result = outcome["result"]

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert outcome["events"] == ["acquire", "stage", "inspect", "complete"]
    assert (
        f"stage={outcome['stage']} adopted=1 phase=PREPARED"
        in outcome["proof"]
    )
    assert outcome["stage_after"] == outcome["stage_before"]
    assert outcome["scp_calls"] == []
    assert all(outcome["stage"] not in call for call in outcome["mkdir_calls"])


@pytest.mark.parametrize(
    ("scenario", "expected_returncode", "expected_events"),
    (
        ("wrong-token", 81, ("acquire", "acquire-failed:73")),
        ("wrong-label", 81, ("acquire", "acquire-failed:73")),
        (
            "wrong-sha",
            83,
            ("acquire", "stage", "inspect", "inspect-failed:1"),
        ),
        (
            "unsealed-allowed-name",
            82,
            ("acquire", "stage", "stage-failed:1"),
        ),
    ),
)
def test_existing_remote_release_adoption_fails_closed_on_identity_mismatch(
    tmp_path: Path,
    scenario: str,
    expected_returncode: int,
    expected_events: tuple[str, ...],
):
    outcome = _run_adopted_release_stage_harness(
        tmp_path,
        scenario=scenario,
    )
    result = outcome["result"]

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == expected_returncode, (
        result.stdout,
        result.stderr,
    )
    assert outcome["events"] == list(expected_events)
    assert outcome["proof"] == ""
    assert outcome["stage_after"] == outcome["stage_before"]
    assert outcome["scp_calls"] == []
    assert all(outcome["stage"] not in call for call in outcome["mkdir_calls"])


def _run_adopted_activation_stage_harness(
    tmp_path: Path,
    *,
    terminal: bool,
) -> dict[str, object]:
    source_repo = tmp_path / "activation-release-source"
    source_repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=source_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "release@example.test"],
        cwd=source_repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Release Test"],
        cwd=source_repo,
        check=True,
    )
    for _, repository_path in _ADOPTED_STAGE_ARTIFACTS:
        target = source_repo / repository_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / repository_path).read_bytes())
    subprocess.run(["git", "add", "."], cwd=source_repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "activation release fixture"],
        cwd=source_repo,
        check=True,
    )
    release_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo,
        text=True,
    ).strip()

    stage = Path("/tmp") / (
        f"health-app-backup-preflight-{os.getpid()}-"
        f"{tmp_path.stat().st_ino}"
    )
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    for staged_name, repository_path in _ADOPTED_STAGE_ARTIFACTS:
        payload = subprocess.check_output(
            ["git", "show", f"{release_sha}:{repository_path}"],
            cwd=source_repo,
        )
        target = stage / staged_name
        target.write_bytes(payload)
        target.chmod(0o400)

    candidate = (
        b"APP_ENV=production\n"
        b"DEBUG=False\n"
        b"HEALTH_RUNTIME_DATA_DIR=/var/lib/health-app/runtime\n"
        b"HEALTH_UPLOAD_DIR=/var/lib/health-app/uploads\n"
        b"HEALTH_SKILLS_CACHE_DIR=/var/cache/health-app/skills-hub\n"
        b"DEDAO_KBASE_REVIEW_ARTIFACT_DIR="
        b"/var/lib/health-app/dedao-kbase/workspace\n"
        b"LEGACY_KNOWLEDGE_RUNTIME_ENABLED=false\n"
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
    )
    guard = candidate.replace(
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true",
        b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false",
    )
    for name, payload in (("candidate.env", candidate), ("guard.env", guard)):
        target = stage / name
        target.write_bytes(payload)
        target.chmod(0o400)
    manifest_lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(stage.iterdir(), key=lambda item: item.name)
    ]
    manifest = stage / "staged.sha256"
    manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    manifest.chmod(0o400)

    state_dir = Path(f"{stage}.activation-state")
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(mode=0o700)
    if terminal:
        terminal_payloads = {
            "launch-intent": (
                f"commit={release_sha}\n"
                "unit=health-evidence-activation-"
                f"{release_sha[:12]}-4242.service\n"
                "lease_sha256="
                f"{hashlib.sha256(b'activation-owner').hexdigest()}\n"
            ),
            "success": "terminal-success\n",
            "success.outcome": "terminal-outcome\n",
        }
        for name, payload in terminal_payloads.items():
            target = state_dir / name
            target.write_text(payload, encoding="utf-8")
            target.chmod(0o400)

    remote_path = tmp_path / "remote-app"
    (remote_path / "backend").mkdir(parents=True)
    (remote_path / "backend/.env").write_bytes(guard)
    remote_lock = tmp_path / "activation-release.lock"
    remote_lock.mkdir()
    (remote_lock / "token").write_text(
        "activation-owner\n", encoding="utf-8"
    )
    env_file = tmp_path / "activation.env"
    env_file.write_bytes(
        b"DEPLOY_SERVER=fake-server\n"
        + f"DEPLOY_PATH={remote_path}\n".encode()
        + candidate
    )
    scp_log = tmp_path / "activation.scp"
    mkdir_log = tmp_path / "activation.mkdir"
    fake_bin = tmp_path / "activation-bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "stat",
        """#!/bin/bash
set -euo pipefail
format="$2"
target="${@: -1}"
case "$format" in
  %U:%G:%a)
    if [ -d "$target" ]; then
      printf 'root:root:700\n'
    else
      printf 'root:root:400\n'
    fi
    ;;
  %h) printf '1\n' ;;
  *) exit 97 ;;
esac
""",
    )
    _write_executable(
        fake_bin / "mkdir",
        """#!/bin/bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_ACTIVATION_MKDIR_LOG"
exec /bin/mkdir "$@"
""",
    )
    stage_before = _immutable_stage_snapshot(stage)
    state_before = _immutable_stage_snapshot(state_dir)
    harness = f"""
source {DEPLOY_SCRIPT!s}
set_remote_backup_preflight_dir "$FAKE_ACTIVATION_STAGE"
DEPLOY_EXPECTED_SHA="$FAKE_ACTIVATION_SHA"
REMOTE_RELEASE_LOCK_DIR="$FAKE_ACTIVATION_LOCK"
REMOTE_RELEASE_LOCK_TOKEN=activation-owner
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
validate_env_sync_safety() {{ return 0; }}
validate_langbridge_env() {{ return 0; }}
ssh() {{
    shift
    if [ "${{1:-}}" = bash ] && [ "${{2:-}}" = -s ]; then
        "$@"
        return
    fi
    test "$#" -eq 1
    bash -c "$1"
}}
scp() {{
    if [ "${{1:-}}" = -q ]; then shift; fi
    test "$#" -eq 2
    source_path="$1"
    target_path="$2"
    case "$source_path" in
      fake-server:*)
        printf 'download:%s\\n' "${{source_path#fake-server:}}" \
            >> "$FAKE_ACTIVATION_SCP_LOG"
        cp "${{source_path#fake-server:}}" "$target_path"
        ;;
      *)
        printf 'upload:%s\\n' "$source_path" \
            >> "$FAKE_ACTIVATION_SCP_LOG"
        return 99
        ;;
    esac
}}
stage_health_evidence_activation_artifacts
"""
    try:
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=source_repo,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "DEPLOY_ENV_FILE": str(env_file),
                "FAKE_ACTIVATION_STAGE": str(stage),
                "FAKE_ACTIVATION_SHA": release_sha,
                "FAKE_ACTIVATION_LOCK": str(remote_lock),
                "FAKE_ACTIVATION_SCP_LOG": str(scp_log),
                "FAKE_ACTIVATION_MKDIR_LOG": str(mkdir_log),
            },
        )
        return {
            "result": result,
            "stage_before": stage_before,
            "stage_after": _immutable_stage_snapshot(stage),
            "state_before": state_before,
            "state_after": _immutable_stage_snapshot(state_dir),
            "scp": (
                scp_log.read_text(encoding="utf-8").splitlines()
                if scp_log.exists()
                else []
            ),
            "mkdir": (
                mkdir_log.read_text(encoding="utf-8").splitlines()
                if mkdir_log.exists()
                else []
            ),
        }
    finally:
        shutil.rmtree(stage)
        shutil.rmtree(state_dir)


@pytest.mark.parametrize("terminal", (False, True))
def test_adopted_activation_stage_is_read_only_for_empty_and_terminal_state(
    tmp_path: Path,
    terminal: bool,
):
    outcome = _run_adopted_activation_stage_harness(
        tmp_path,
        terminal=terminal,
    )
    result = outcome["result"]

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert outcome["stage_after"] == outcome["stage_before"]
    assert outcome["state_after"] == outcome["state_before"]
    assert outcome["mkdir"] == []
    assert len(outcome["scp"]) == 2
    assert all(call.startswith("download:") for call in outcome["scp"])


def _run_deactivation_orchestrator_harness(
    tmp_path: Path,
    *,
    transaction_ok: bool,
    proof_ok: bool,
    inactive_ok: bool,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / "deploy-deactivation.env"
    event_log = tmp_path / "deactivation.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=test-owner
assert_remote_release_lock() {{ :; }}
run_health_evidence_deactivation_transaction() {{
    printf 'run:delegated=%s\\n' "$_REMOTE_RELEASE_LOCK_DELEGATED" \
        >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_TRANSACTION_OK" = "1" ]
}}
prove_health_evidence_deactivated_state() {{
    printf 'prove\\n' >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_PROOF_OK" = "1" ]
}}
prove_health_evidence_services_inactive() {{
    printf 'inactive-proof\\n' >> "$DEACTIVATION_EVENT_LOG"
    [ "$DEACTIVATION_INACTIVE_OK" = "1" ]
}}
deactivate_health_evidence_runtime_before_mutation
deactivation_rc=$?
printf 'final:rc=%s:delegated=%s:abandoned=%s\\n' \
    "$deactivation_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$DEACTIVATION_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "DEACTIVATION_EVENT_LOG": str(event_log),
            "DEACTIVATION_TRANSACTION_OK": "1" if transaction_ok else "0",
            "DEACTIVATION_PROOF_OK": "1" if proof_ok else "0",
            "DEACTIVATION_INACTIVE_OK": "1" if inactive_ok else "0",
        },
    )
    return result, event_log.read_text(encoding="utf-8").splitlines()


def test_deactivation_orchestrator_clears_delegation_only_after_exact_proof(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=True,
        proof_ok=True,
        inactive_ok=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_deactivation_orchestrator_rejects_lost_ssh_even_if_state_proof_passes(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=False,
        proof_ok=True,
        inactive_ok=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "inactive-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def test_deactivation_orchestrator_preserves_lease_and_stage_on_unknown_result(
    tmp_path: Path,
):
    result, events = _run_deactivation_orchestrator_harness(
        tmp_path,
        transaction_ok=False,
        proof_ok=False,
        inactive_ok=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "run:delegated=1",
        "prove",
        "inactive-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def _run_deactivation_transaction_fixture(
    tmp_path: Path,
    *,
    fail_candidate_sync: bool,
    live_flag: str | None = "false",
    authorization_enabled: bool = True,
    process_flag: str | None = "true",
    dirty_auth_artifact: str | None = None,
    dirty_process_unit: str | None = None,
    dirty_process_flag: str = "true",
    dirty_process_child_unit: str | None = None,
    drop_lease_after_candidate_sync: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Path]]:
    repo = tmp_path / "release"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    old_env = backend / ".env"
    old_env_text = "CONFIG_REVISION=old\n"
    if live_flag is not None:
        old_env_text += f"HEALTH_EVIDENCE_RUNTIME_ENABLED={live_flag}\n"
    old_env.write_text(old_env_text, encoding="utf-8")
    stage = tmp_path / "stage"
    stage.mkdir()
    candidate = stage / "backend.env.candidate"
    candidate.write_text(
        "CONFIG_REVISION=new\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    candidate.chmod(0o400)
    candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    durable = tmp_path / "durable"
    runtime_state = tmp_path / "runtime-state"
    systemd_runtime = tmp_path / "systemd-runtime"
    systemd_runtime.mkdir()
    dirty_auth_artifacts = (
        {
            "durable",
            "runtime_state",
            "backend_dropin",
            "worker_dropin",
            "beat_dropin",
        }
        if authorization_enabled
        else ({dirty_auth_artifact} if dirty_auth_artifact else set())
    )
    if "durable" in dirty_auth_artifacts:
        durable.mkdir()
        (durable / "enabled.env").write_text(
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
            encoding="utf-8",
        )
    elif "durable_symlink" in dirty_auth_artifacts:
        durable.mkdir()
        (durable / "enabled.env").symlink_to(
            tmp_path / "missing-durable-authorization"
        )
    if "runtime_state" in dirty_auth_artifacts:
        runtime_state.mkdir()
        (runtime_state / "enabled.env").write_text(
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
            encoding="utf-8",
        )
    elif "runtime_state_symlink" in dirty_auth_artifacts:
        runtime_state.symlink_to(
            tmp_path / "missing-runtime-state",
            target_is_directory=True,
        )
    dirty_dropins = {
        "backend_dropin": "health-backend.service",
        "worker_dropin": "celery-worker.service",
        "beat_dropin": "celery-beat.service",
        "backend_dropin_symlink": "health-backend.service",
        "backend_dropin_dir_symlink": "health-backend.service",
    }
    for artifact, unit in dirty_dropins.items():
        if artifact in dirty_auth_artifacts:
            unit_dir = systemd_runtime / f"{unit}.d"
            if artifact.endswith("_dir_symlink"):
                unit_dir.symlink_to(
                    tmp_path / "missing-runtime-override-dir",
                    target_is_directory=True,
                )
                continue
            unit_dir.mkdir()
            override = (
                unit_dir / "90-reva-health-evidence-activation.conf"
            )
            if artifact.endswith("_symlink"):
                override.symlink_to(tmp_path / "missing-runtime-override")
            else:
                override.write_text(
                    "[Service]\nEnvironmentFile=/tmp/runtime-enabled.env\n",
                    encoding="utf-8",
                )
    release_lock = tmp_path / "release.lock"
    release_lock.mkdir()
    token = "deactivation-owner"
    (release_lock / "token").write_text(token + "\n", encoding="utf-8")
    service_state = tmp_path / "service-state"
    service_state.mkdir()
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    cgroup_root = tmp_path / "cgroup"
    cgroup_root.mkdir()
    unit_pids = {
        "health-backend": 3101,
        "celery-worker": 3201,
        "celery-beat": 3301,
    }
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        (service_state / f"{unit}.state").write_text(
            "active\n", encoding="utf-8"
        )
    for unit, pid in unit_pids.items():
        group = cgroup_root / "system.slice" / f"{unit}.service"
        group.mkdir(parents=True)
        cgroup_pids = [pid]
        if dirty_process_child_unit == unit:
            cgroup_pids.append(pid + 50)
        (group / "cgroup.procs").write_text(
            "".join(f"{process_pid}\n" for process_pid in cgroup_pids),
            encoding="utf-8",
        )
        process = proc_root / str(pid)
        process.mkdir()
        process_env = b"PATH=/usr/bin\0"
        unit_process_flag = process_flag
        if dirty_process_unit == unit:
            unit_process_flag = dirty_process_flag
        if unit_process_flag is not None:
            process_env += (
                "HEALTH_EVIDENCE_RUNTIME_ENABLED="
                f"{unit_process_flag}\0"
            ).encode()
        (process / "environ").write_bytes(process_env)
        if dirty_process_child_unit == unit:
            child_process = proc_root / str(pid + 50)
            child_process.mkdir()
            child_process_env = (
                b"PATH=/usr/bin\0"
                b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\0"
            )
            (child_process / "environ").write_bytes(child_process_env)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    event_log = tmp_path / "deactivation-transaction.events"
    _write_executable(
        bin_dir / "systemctl",
        """#!/bin/bash
set -euo pipefail
normalize() { printf '%s' "${1%.service}"; }
state_file() { printf '%s/%s.state' "$FAKE_STATE_DIR" "$(normalize "$1")"; }
pid_for() {
  case "$(normalize "$1")" in
    health-backend) printf '3101' ;;
    celery-worker) printf '3201' ;;
    celery-beat) printf '3301' ;;
    *) printf '0' ;;
  esac
}
case "$1" in
  stop)
    unit="$2"
    printf 'stop:%s\n' "$unit" >> "$FAKE_EVENT_LOG"
    printf 'inactive\n' > "$(state_file "$unit")"
    ;;
  start)
    unit="$2"
    printf 'start:%s\n' "$unit" >> "$FAKE_EVENT_LOG"
    printf 'active\n' > "$(state_file "$unit")"
    pid="$(pid_for "$unit")"
    if [ "$pid" != "0" ]; then
      printf 'PATH=/usr/bin\\0HEALTH_EVIDENCE_RUNTIME_ENABLED=false\\0' \
        > "$FAKE_PROC_ROOT/$pid/environ"
    fi
    ;;
  show)
    unit="$2"
    case "$*" in
      *--property=ActiveState*) cat "$(state_file "$unit")" ;;
      *--property=MainPID*) pid_for "$unit"; printf '\n' ;;
      *--property=ControlGroup*)
        printf '/system.slice/%s.service\n' "$(normalize "$unit")"
        ;;
      *) exit 93 ;;
    esac
    ;;
  kill)
    unit="${@: -1}"
    printf 'inactive\n' > "$(state_file "$unit")"
    ;;
  daemon-reload) exit 0 ;;
  *) exit 92 ;;
esac
""",
    )
    _write_executable(
        bin_dir / "install",
        """#!/bin/bash
set -euo pipefail
source="${@: -2:1}"
target="${@: -1}"
cp "$source" "$target"
chmod 0640 "$target"
printf 'install:%s\n' "$target" >> "$FAKE_EVENT_LOG"
""",
    )
    _write_executable(
        bin_dir / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
case "$target" in
  *backend.env.candidate) printf 'root:root:400\n' ;;
  */backend/.env|*/backend/.env.reva-release.tmp)
    printf 'root:health-app:640\n'
    ;;
  *) printf 'root:root:700\n' ;;
esac
""",
    )
    _write_executable(
        bin_dir / "sync",
        """#!/bin/bash
set -euo pipefail
test "$1" = "-f"
if [ "${FAKE_FAIL_CANDIDATE_SYNC:-0}" = "1" ] &&
   [[ "$2" == *".env.reva-release.tmp" ]]; then
  exit 88
fi
test -e "$2"
printf 'sync:%s\n' "$2" >> "$FAKE_EVENT_LOG"
if [ "${FAKE_DROP_LEASE_AFTER_CANDIDATE_SYNC:-0}" = "1" ] &&
   [[ "$2" == *".env.reva-release.tmp" ]]; then
  rm -f "$FAKE_RELEASE_TOKEN_FILE"
fi
""",
    )
    _write_executable(
        bin_dir / "mv",
        """#!/bin/bash
set -euo pipefail
test "$1" = "-fT"
/bin/mv "$2" "$3"
""",
    )
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={repo}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
REMOTE_BACKEND_ENV_CANDIDATE={candidate}
REMOTE_BACKEND_ENV_CANDIDATE_SHA={candidate_hash}
REMOTE_HEALTH_EVIDENCE_DURABLE_STATE_DIR={durable}
REMOTE_HEALTH_EVIDENCE_RUNTIME_STATE_DIR={runtime_state}
REMOTE_HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR={systemd_runtime}
REMOTE_HEALTH_EVIDENCE_CGROUP_ROOT={cgroup_root}
REMOTE_HEALTH_EVIDENCE_PROC_ROOT={proc_root}
REMOTE_RELEASE_LOCK_DIR={release_lock}
REMOTE_RELEASE_LOCK_TOKEN={token}
ssh() {{ shift; "$@"; }}
run_health_evidence_deactivation_transaction
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DEPLOY_ENV_FILE": str(deploy_env),
            "FAKE_STATE_DIR": str(service_state),
            "FAKE_PROC_ROOT": str(proc_root),
            "FAKE_EVENT_LOG": str(event_log),
            "FAKE_FAIL_CANDIDATE_SYNC": (
                "1" if fail_candidate_sync else "0"
            ),
            "FAKE_DROP_LEASE_AFTER_CANDIDATE_SYNC": (
                "1" if drop_lease_after_candidate_sync else "0"
            ),
            "FAKE_RELEASE_TOKEN_FILE": str(release_lock / "token"),
        },
    )
    return result, {
        "old_env": old_env,
        "candidate": candidate,
        "durable": durable,
        "runtime_state": runtime_state,
        "service_state": service_state,
        "proc_root": proc_root,
        "event_log": event_log,
    }


def test_deactivation_transaction_atomically_installs_then_proves_false(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert paths["old_env"].read_bytes() == paths["candidate"].read_bytes()
    assert not (paths["durable"] / "enabled.env").exists()
    assert not paths["runtime_state"].exists()
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "active"
    for pid in (3101, 3201, 3301):
        assert b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0" in (
            paths["proc_root"] / str(pid) / "environ"
        ).read_bytes()


def test_deactivation_sync_failure_keeps_old_env_and_contains_services(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=True,
    )

    assert result.returncode != 0
    assert paths["old_env"].read_text(encoding="utf-8").startswith(
        "CONFIG_REVISION=old\n"
    )
    assert not (paths["durable"] / "enabled.env").exists()
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "inactive"
    assert "start:" not in paths["event_log"].read_text(encoding="utf-8")


def test_deactivation_bootstraps_missing_legacy_flag_only_when_unset_everywhere(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert paths["old_env"].read_bytes() == paths["candidate"].read_bytes()
    events = paths["event_log"].read_text(encoding="utf-8").splitlines()
    install_index = next(
        index for index, event in enumerate(events) if event.startswith("install:")
    )
    assert all(
        events.index(f"stop:{unit}") < install_index
        for unit in (
            "health-backend.socket",
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        )
    )
    assert all(
        events.index(f"start:{unit}") > install_index
        for unit in (
            "health-backend.socket",
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        )
    )


def test_deactivation_bootstrap_sync_failure_contains_legacy_services(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=True,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    events = paths["event_log"].read_text(encoding="utf-8")
    assert "start:" not in events
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "inactive"


def test_deactivation_bootstrap_lost_lease_before_rename_keeps_legacy_env(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
        drop_lease_after_candidate_sync=True,
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    events = paths["event_log"].read_text(encoding="utf-8")
    assert "start:" not in events
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (
            paths["service_state"] / f"{unit}.state"
        ).read_text(encoding="utf-8").strip() == "inactive"


@pytest.mark.parametrize(
    "dirty_auth_artifact",
    (
        "durable",
        "runtime_state",
        "backend_dropin",
        "worker_dropin",
        "beat_dropin",
        "durable_symlink",
        "runtime_state_symlink",
        "backend_dropin_symlink",
        "backend_dropin_dir_symlink",
    ),
)
def test_deactivation_rejects_each_legacy_authorization_artifact(
    tmp_path: Path,
    dirty_auth_artifact: str,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
        dirty_auth_artifact=dirty_auth_artifact,
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    if paths["event_log"].exists():
        assert "stop:" not in paths["event_log"].read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("dirty_process_unit", "dirty_process_flag"),
    (
        ("health-backend", "true"),
        ("celery-worker", "true"),
        ("celery-beat", "true"),
        ("health-backend", "false"),
    ),
)
def test_deactivation_rejects_each_legacy_process_assignment(
    tmp_path: Path,
    dirty_process_unit: str,
    dirty_process_flag: str,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
        dirty_process_unit=dirty_process_unit,
        dirty_process_flag=dirty_process_flag,
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    if paths["event_log"].exists():
        assert "stop:" not in paths["event_log"].read_text(encoding="utf-8")


def test_deactivation_rejects_dirty_child_process_in_legacy_cgroup(
    tmp_path: Path,
):
    result, paths = _run_deactivation_transaction_fixture(
        tmp_path,
        fail_candidate_sync=False,
        live_flag=None,
        authorization_enabled=False,
        process_flag=None,
        dirty_process_child_unit="celery-worker",
    )

    assert result.returncode != 0
    assert (
        paths["old_env"].read_text(encoding="utf-8")
        == "CONFIG_REVISION=old\n"
    )
    if paths["event_log"].exists():
        assert "stop:" not in paths["event_log"].read_text(encoding="utf-8")


def _run_activation_orchestrator_harness(
    tmp_path: Path,
    *,
    proof_mode: str,
    adopted: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / f"deploy-{proof_mode}.env"
    event_log = tmp_path / f"activation-{proof_mode}.events"
    env_file.write_text(
        "DEPLOY_SERVER=fake-server\n"
        "DEPLOY_PATH=/tmp/fake-health-app\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    harness = f"""
source {DEPLOY_SCRIPT!s}
set +e
DEPLOY_EXPECTED_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
_REMOTE_RELEASE_LOCK_ACQUIRED=1
REMOTE_RELEASE_LOCK_TOKEN=test-owner
_REMOTE_RELEASE_LOCK_ADOPTED={"1" if adopted else "0"}
_REMOTE_RELEASE_LOCK_ABANDONED={"1" if adopted else "0"}
verify_deployed_revision() {{ printf 'revision\\n' >> "$ACTIVATION_EVENT_LOG"; }}
verify_runtime_only_kb_contract() {{
    printf 'contract:%s\\n' "$1" >> "$ACTIVATION_EVENT_LOG"
}}
verify_systemd_activation_capability() {{
    printf 'systemd-capability\\n' >> "$ACTIVATION_EVENT_LOG"
}}
stage_health_evidence_activation_artifacts() {{
    printf 'stage\\n' >> "$ACTIVATION_EVENT_LOG"
}}
ACTIVATION_LAUNCHED=0
run_health_evidence_activation_unit() {{
    printf 'run:delegated=%s\\n' "$_REMOTE_RELEASE_LOCK_DELEGATED" \
        >> "$ACTIVATION_EVENT_LOG"
    ACTIVATION_LAUNCHED=1
    [ "$ACTIVATION_PROOF_MODE" = "success" ] ||
        [ "$ACTIVATION_PROOF_MODE" = "adopted-not-launched" ]
}}
prove_health_evidence_activation_state() {{
    printf 'prove:%s\\n' "$1" >> "$ACTIVATION_EVENT_LOG"
    case "$ACTIVATION_PROOF_MODE:$1" in
        success:enabled|recovered:staged|adopted-success:enabled|\
adopted-recovered:staged)
            return 0
            ;;
        adopted-not-launched:enabled)
            [ "$ACTIVATION_LAUNCHED" = "1" ]
            ;;
        *) return 1 ;;
    esac
}}
prove_health_evidence_activation_not_launched() {{
    printf 'prove:not-launched\\n' >> "$ACTIVATION_EVENT_LOG"
    [ "$ACTIVATION_PROOF_MODE" = "adopted-not-launched" ]
}}
prove_health_evidence_services_inactive() {{
    printf 'containment-proof\\n' >> "$ACTIVATION_EVENT_LOG"
    return 1
}}
activate_health_evidence_runtime
activation_rc=$?
printf 'final:rc=%s:delegated=%s:abandoned=%s\\n' \
    "$activation_rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED" \
    >> "$ACTIVATION_EVENT_LOG"
exit 0
"""
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(env_file),
            "ACTIVATION_EVENT_LOG": str(event_log),
            "ACTIVATION_PROOF_MODE": proof_mode,
        },
    )
    events = event_log.read_text(encoding="utf-8").splitlines()
    return result, events


def test_activation_orchestrator_releases_delegation_only_after_exact_success(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="success",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_activation_orchestrator_accepts_failure_only_after_exact_guard_proof(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="recovered",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "prove:staged",
        "final:rc=1:delegated=0:abandoned=0",
    ]


def test_activation_orchestrator_preserves_stage_and_lease_on_unknown_result(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="unknown",
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "contract:staged",
        "systemd-capability",
        "stage",
        "run:delegated=1",
        "prove:enabled",
        "prove:staged",
        "containment-proof",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def test_adopted_activation_terminal_success_arms_stage_and_lease_cleanup(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="adopted-success",
        adopted=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "stage",
        "prove:enabled",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_adopted_activation_terminal_recovery_arms_cleanup_and_fails_closed(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="adopted-recovered",
        adopted=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "stage",
        "prove:enabled",
        "prove:staged",
        "final:rc=1:delegated=0:abandoned=0",
    ]


def test_adopted_activation_reuses_sealed_artifacts_only_when_never_launched(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="adopted-not-launched",
        adopted=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "stage",
        "prove:enabled",
        "prove:staged",
        "prove:not-launched",
        "contract:staged",
        "systemd-capability",
        "run:delegated=1",
        "prove:enabled",
        "final:rc=0:delegated=0:abandoned=0",
    ]


def test_adopted_activation_with_launch_intent_but_no_outcome_is_preserved(
    tmp_path: Path,
):
    result, events = _run_activation_orchestrator_harness(
        tmp_path,
        proof_mode="adopted-in-flight",
        adopted=True,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert events == [
        "revision",
        "stage",
        "prove:enabled",
        "prove:staged",
        "prove:not-launched",
        "final:rc=1:delegated=1:abandoned=1",
    ]


def test_activation_persists_launch_intent_before_systemd_rpc():
    script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = script.index("run_health_evidence_activation_unit() {")
    end = script.index("prove_health_evidence_activation_state() {", start)
    body = script[start:end]

    intent = body.index("launch-intent")
    durable_sync = body.index('sync -f "$state_dir"', intent)
    systemd_rpc = body.index("systemd-run", durable_sync)

    assert intent < durable_sync < systemd_rpc
    assert 'test ! -e "$intent_file"' in body
    assert 'rm -f "$success_marker" "$outcome_file"' not in body
