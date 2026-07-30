import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SCRIPT = ROOT / "backend/scripts/rollback_release.sh"
REQUIRED_ARTIFACT_NAMES = (
    "backup_db.sh",
    "verify_backup_restore.sh",
    "archive_backup_offsite.sh",
    "rollback_release.sh",
    "activate_health_evidence_runtime.sh",
    "verify_runtime_schema_compatibility.py",
    "quarantine_runtime_only_kb.py",
    "runtime_state_release_transaction.py",
    "review_manifest.json",
    "health-backend-runtime-state.conf",
    "celery-worker-runtime-state.conf",
    "celery-beat-runtime-state.conf",
    "backend.env.rollback",
    "backend.env.candidate",
)
DROPIN_ARTIFACT_SOURCES = {
    name: ROOT / "infra/systemd/dropins" / name
    for name in (
        "health-backend-runtime-state.conf",
        "celery-worker-runtime-state.conf",
        "celery-beat-runtime-state.conf",
    )
}
FAKE_RUNTIME_STATE_RUNNER = """#!/usr/bin/python3
import os
import subprocess
import sys
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


if len(sys.argv) != 5:
    fail("fake runtime transaction received unexpected arguments")

command, release_commit, release_lock_dir_raw, release_lock_token = sys.argv[1:]
if command not in {"restore", "release-gate", "commit", "finalize"}:
    fail("fake runtime transaction received unexpected command")
if len(release_commit) != 40 or any(
    character not in "0123456789abcdef" for character in release_commit
):
    fail("fake runtime transaction received invalid commit")

release_lock_dir = Path(release_lock_dir_raw)
if not release_lock_dir.is_absolute():
    fail("fake runtime restore received a relative release lock")
if (release_lock_dir / "token").read_text(encoding="utf-8").strip() != release_lock_token:
    fail("fake runtime transaction observed a lost release lock")

service_state_dir_raw = os.environ.get("FAKE_SERVICE_STATE_DIR")
service_state_raw = os.environ.get("FAKE_SERVICE_STATE")
expected_state = "inactive" if command == "restore" else "active"
if service_state_dir_raw:
    service_state_dir = Path(service_state_dir_raw)
    for service in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        state = (service_state_dir / f"{service}.state").read_text(
            encoding="utf-8"
        )
        if state.strip() != expected_state:
            fail(
                "fake runtime transaction observed unexpected service state: "
                f"{service} expected={expected_state} actual={state.strip()}"
            )
elif service_state_raw:
    actual_state = Path(service_state_raw).read_text(encoding="utf-8").strip()
    if actual_state != expected_state:
        fail(
            "fake runtime transaction observed unexpected writer state: "
            f"expected={expected_state} actual={actual_state}"
        )
else:
    fail("fake runtime transaction cannot prove service state")

expected_rollback = os.environ.get("FAKE_RUNTIME_EXPECTED_ROLLBACK")
if expected_rollback and release_commit != expected_rollback:
    fail("fake runtime transaction received the wrong target")

repo_raw = os.environ.get("FAKE_RUNTIME_REPO")
expected_head = os.environ.get("FAKE_RUNTIME_EXPECTED_HEAD")
if command == "restore" and (repo_raw or expected_head):
    if not repo_raw or not expected_head:
        fail("fake runtime restore head proof is incomplete")
    current_head = subprocess.check_output(
        ["git", "-C", repo_raw, "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if current_head != expected_head:
        fail("fake runtime restore did not run after checkout")

event_log_raw = os.environ.get("FAKE_ROLLBACK_EVENT_LOG")
if event_log_raw:
    with Path(event_log_raw).open("a", encoding="utf-8") as event_log:
        event_log.write(f"runtime-state-{command}\\n")

if os.environ.get("FAKE_RUNTIME_STATE_FAIL") == "1" or os.environ.get(
    "FAKE_RUNTIME_STATE_FAIL_COMMAND"
) == command:
    fail(f"fake runtime {command} failure")

if command == "restore":
    result = os.environ.get("FAKE_RUNTIME_RESTORE_RESULT", "restored")
elif command == "release-gate":
    result = "RESTORE_FINALIZED"
elif command == "commit":
    result = "COMMITTED"
else:
    result = "finalized"
print(f"RUNTIME_STATE_TRANSACTION_OK command={command} result={result}")
"""


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_rollback_runner_requires_verified_staged_failed_release_artifacts():
    script = ROLLBACK_SCRIPT.read_text(encoding="utf-8")

    assert 'STAGED_REVIEW_MANIFEST="$SCRIPT_DIR/review_manifest.json"' in script
    assert 'test -r "$STAGED_REVIEW_MANIFEST"' in script
    assert 'STAGED_HASH_MANIFEST="$SCRIPT_DIR/staged.sha256"' in script
    assert 'test -r "$STAGED_HASH_MANIFEST"' in script
    assert 'sha256sum -c "$STAGED_HASH_MANIFEST"' in script
    assert "backend/data/system_kb_v2_seed/review_manifest.json" not in script
    for artifact_name in REQUIRED_ARTIFACT_NAMES:
        assert artifact_name in script

    services_touched = script.index("SERVICES_TOUCHED=1")
    writers_inactive = script.index("force_services_inactive", services_touched)
    restore = script.index('/usr/bin/python3 "$RUNTIME_STATE_RUNNER"', writers_inactive)
    checkout = script.index('git checkout -B main "$ROLLBACK_COMMIT"')
    final_start = script.index('systemctl start "$BACKEND_SOCKET"', restore)
    assert writers_inactive < checkout < restore < final_start
    release_gate = script.index('"$RUNTIME_STATE_RUNNER" \\\n', final_start)
    assert final_start < release_gate


def test_rollback_stage_requires_both_backend_env_snapshots():
    script = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    required_start = script.index("REQUIRED_STAGED_ARTIFACTS=(")
    required_end = script.index(")", required_start)
    required_body = script[required_start:required_end]

    assert "backend.env.rollback" in required_body
    assert "backend.env.candidate" in required_body


def test_rollback_proves_every_writer_process_flag_false_after_final_start():
    script = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    verify_start = script.index("verify_process_environment_false() {")
    verify_end = script.index("ROLLBACK_VERIFIED=0", verify_start)
    verify_body = script[verify_start:verify_end]
    final_start = script.index('systemctl start "$BACKEND_SOCKET"')
    final_proof = script.index("verify_process_environment_false", final_start)
    success = script.index('echo "ROLLBACK_OK', final_proof)

    assert "MainPID" in verify_body
    assert "ControlGroup" in verify_body
    assert "cgroup.procs" in verify_body
    assert "ROLLBACK_PROC_ROOT/$pid/environ" in verify_body
    assert final_start < final_proof < success


def _make_release_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "release"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "security@example.test"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Security Test"], cwd=repo, check=True
    )
    (repo / "backend/venv/bin").mkdir(parents=True)
    (repo / "backend/requirements.lock").write_text("", encoding="utf-8")
    (repo / ".gitignore").write_text("backend/.env\n", encoding="utf-8")
    (repo / "backend/.env").write_text(
        "DATABASE_URL=sqlite:///:memory:\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        'touch "$FAKE_ENV_EXECUTED"\n',
        encoding="utf-8",
    )
    _write_executable(repo / "backend/venv/bin/pip", "#!/bin/sh\nexit 0\n")
    _write_executable(
        repo / "backend/venv/bin/python",
        """#!/bin/sh
case "$1" in
  *kb-quarantine*|*quarantine_runtime_only_kb.py)
    printf 'kb-quarantine-ran\n' >> "$FAKE_ROLLBACK_EVENT_LOG"
    if [ "${FAKE_QUARANTINE_FAIL:-0}" = "1" ]; then exit 1; fi
    if [ -n "${FAKE_RELEASE_LOCK_TOKEN_TO_REMOVE:-}" ]; then
      rm -f "$FAKE_RELEASE_LOCK_TOKEN_TO_REMOVE"
    fi
    ;;
  *)
    printf 'schema-probe-ran\n' >> "$FAKE_ROLLBACK_EVENT_LOG"
    printf 'schema-probe-ran\n' > "$FAKE_SCHEMA_PROBE_LOG"
    ;;
esac
exit 0
""",
    )
    (repo / "release.txt").write_text("known-good", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "known good"], cwd=repo, check=True)
    known_good = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    (repo / "release.txt").write_text("failed-release", encoding="utf-8")
    manifest_path = repo / "backend/data/system_kb_v2_seed/review_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """{
  "authority_packs": [{
    "serving_allowed": true,
    "serving_scope": "health_evidence_runtime",
    "generic_serving_allowed": false,
    "claim_ids": ["claim:runtime-only"],
    "entity_ids": [],
    "eval_case_ids": []
  }]
}
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "release.txt"], cwd=repo, check=True)
    subprocess.run(["git", "add", str(manifest_path)], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "failed release"], cwd=repo, check=True)
    failed = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    return repo, known_good, failed


def _stage_rollback_runner(
    tmp_path: Path,
    repo: Path,
    *,
    rollback_env: str | None = None,
    candidate_env: str | None = None,
) -> Path:
    stage = tmp_path / "staged-release"
    stage.mkdir()
    source_dir = ROOT / "backend/scripts"
    live_env = (repo / "backend/.env").read_text(encoding="utf-8")
    for name in REQUIRED_ARTIFACT_NAMES:
        if name == "review_manifest.json":
            source = repo / "backend/data/system_kb_v2_seed/review_manifest.json"
        elif name == "runtime_state_release_transaction.py":
            _write_executable(stage / name, FAKE_RUNTIME_STATE_RUNNER)
            continue
        elif name == "backend.env.rollback":
            (stage / name).write_text(
                rollback_env if rollback_env is not None else live_env,
                encoding="utf-8",
            )
            (stage / name).chmod(0o400)
            continue
        elif name == "backend.env.candidate":
            (stage / name).write_text(
                candidate_env if candidate_env is not None else live_env,
                encoding="utf-8",
            )
            (stage / name).chmod(0o400)
            continue
        elif name in DROPIN_ARTIFACT_SOURCES:
            source = DROPIN_ARTIFACT_SOURCES[name]
        else:
            source = source_dir / name
        shutil.copy2(source, stage / name)

    lines = []
    for name in REQUIRED_ARTIFACT_NAMES:
        digest = hashlib.sha256((stage / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (stage / "staged.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stage / "rollback_release.sh"


def _release_lock_args(tmp_path: Path) -> tuple[str, str]:
    lock_dir = tmp_path / "remote-release.lock"
    lock_dir.mkdir()
    token = "test-release-owner"
    (lock_dir / "token").write_text(token + "\n", encoding="utf-8")
    return str(lock_dir), token


def _fake_commands(tmp_path: Path, *, healthy: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "systemctl",
        """#!/bin/sh
case "$1" in
  stop)
    count=0
    if [ -f "$FAKE_STOP_COUNT" ]; then count=$(cat "$FAKE_STOP_COUNT"); fi
    count=$((count + 1))
    printf '%s\n' "$count" > "$FAKE_STOP_COUNT"
    if [ "${FAKE_STOP_FAIL_ON_CALL:-0}" = "$count" ]; then exit 1; fi
    printf 'inactive\n' > "$FAKE_SERVICE_STATE"
    ;;
  start)
    if [ -n "${FAKE_EXPECT_ENV_AT_START:-}" ]; then
      cmp -s "$FAKE_EXPECT_ENV_AT_START" "$FAKE_LIVE_ENV"
    fi
    printf 'service-start\n' >> "$FAKE_ROLLBACK_EVENT_LOG"
    printf 'active\n' > "$FAKE_SERVICE_STATE"
    ;;
  is-active) test "$(cat "$FAKE_SERVICE_STATE")" = active ;;
  kill) printf 'inactive\n' > "$FAKE_SERVICE_STATE" ;;
  reset-failed) exit 0 ;;
  daemon-reload) exit 0 ;;
  show)
    case "$*" in
      *--property=SubState*)
        case "$2" in
          health-backend.socket) printf 'running\n' ;;
          *) printf 'running\n' ;;
        esac
        ;;
      *--property=Result*) printf 'success\n' ;;
      *--property=NRestarts*)
        if [ -n "${FAKE_SERVICE_METRICS_DIR:-}" ]; then
          unit="${2%.service}"
          cat "$FAKE_SERVICE_METRICS_DIR/$unit.restarts"
        else
          printf '0\n'
        fi
        ;;
      *--property=ActiveEnterTimestampMonotonic*)
        if [ -n "${FAKE_SERVICE_METRICS_DIR:-}" ]; then
          unit="${2%.service}"
          cat "$FAKE_SERVICE_METRICS_DIR/$unit.entered"
        else
          printf '1000\n'
        fi
        ;;
      *--property=MainPID*) printf '4242\n' ;;
      *--property=ControlGroup*) printf '/health-test\n' ;;
      *) cat "$FAKE_SERVICE_STATE" ;;
    esac
    ;;
  *) exit 1 ;;
esac
""",
    )
    _write_executable(
        bin_dir / "sleep",
        """#!/bin/sh
if [ "${FAKE_BUMP_RESTART_ON_STABILITY:-0}" = "1" ] &&
   [ "${1:-}" = "7" ] &&
   [ ! -e "$FAKE_STABILITY_BUMP_MARKER" ]; then
  restart_file="$FAKE_SERVICE_METRICS_DIR/celery-beat.restarts"
  entered_file="$FAKE_SERVICE_METRICS_DIR/celery-beat.entered"
  restart_count="$(cat "$restart_file")"
  enter_timestamp="$(cat "$entered_file")"
  printf '%s\n' "$((restart_count + 1))" > "$restart_file"
  printf '%s\n' "$((enter_timestamp + 1))" \
    > "$entered_file"
  : > "$FAKE_STABILITY_BUMP_MARKER"
fi
exit 0
""",
    )
    _write_executable(
        bin_dir / "sync",
        """#!/bin/sh
test "$1" = "-f"
test -e "$2"
if [ "${FAKE_SYNC_FAIL:-0}" = "1" ]; then
  exit 88
fi
if [ -n "${FAKE_SYNC_LOG:-}" ]; then
  printf '%s\n' "$2" >> "$FAKE_SYNC_LOG"
fi
""",
    )
    health_result = "exit 0" if healthy else "exit 1"
    _write_executable(
        bin_dir / "curl",
        f"""#!/bin/sh
case "$*" in
  *auth/me*) printf '401'; exit 0 ;;
esac
{health_result}
""",
    )
    return bin_dir


def _process_proof_env(tmp_path: Path) -> dict[str, str]:
    cgroup_root = tmp_path / "fake-cgroup"
    process_group = cgroup_root / "health-test"
    process_group.mkdir(parents=True, exist_ok=True)
    (process_group / "cgroup.procs").write_text("4242\n", encoding="utf-8")
    proc_root = tmp_path / "fake-proc"
    process_env = proc_root / "4242"
    process_env.mkdir(parents=True, exist_ok=True)
    (process_env / "environ").write_bytes(
        b"PATH=/usr/bin\0HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0"
    )
    return {
        "ROLLBACK_CGROUP_ROOT": str(cgroup_root),
        "ROLLBACK_PROC_ROOT": str(proc_root),
    }


def _replace_systemctl_with_socket_activation_simulator(
    bin_dir: Path,
) -> None:
    _write_executable(
        bin_dir / "systemctl",
        """#!/bin/sh
state_file() { printf '%s/%s.state' "$FAKE_SERVICE_STATE_DIR" "$1"; }
last_arg=
for arg in "$@"; do last_arg="$arg"; done
case "$1" in
  stop)
    shift
    for service in "$@"; do
      printf 'stop:%s\n' "$service" >> "$FAKE_ROLLBACK_EVENT_LOG"
      printf 'inactive\n' > "$(state_file "$service")"
    done
    ;;
  start)
    shift
    for service in "$@"; do
      printf 'start:%s\n' "$service" >> "$FAKE_ROLLBACK_EVENT_LOG"
      printf 'active\n' > "$(state_file "$service")"
    done
    ;;
  show)
    service="$2"
    case "$*" in
      *--property=SubState*)
        case "$service" in
          health-backend.socket) printf 'listening\n' ;;
          *) printf 'running\n' ;;
        esac
        exit 0
        ;;
      *--property=Result*) printf 'success\n'; exit 0 ;;
      *--property=NRestarts*) printf '0\n'; exit 0 ;;
      *--property=ActiveEnterTimestampMonotonic*)
        printf '1000\n'
        exit 0
        ;;
      *--property=MainPID*) printf '4242\n'; exit 0 ;;
      *--property=ControlGroup*) printf '/health-test\n'; exit 0 ;;
    esac
    if [ "$service" = "health-backend" ] &&
       [ "$(cat "$(state_file health-backend.socket)")" = "active" ] &&
       [ "$(cat "$(state_file health-backend)")" != "active" ]; then
      printf 'socket-reactivation\n' >> "$FAKE_ROLLBACK_EVENT_LOG"
      printf 'active\n' > "$(state_file health-backend)"
    fi
    cat "$(state_file "$service")"
    ;;
  is-active)
    test "$(cat "$(state_file "$last_arg")")" = active
    ;;
  kill)
    printf 'inactive\n' > "$(state_file "$last_arg")"
    ;;
  reset-failed) exit 0 ;;
  daemon-reload) exit 0 ;;
  *) exit 1 ;;
esac
""",
    )


def test_release_rollback_rejects_missing_or_tampered_stage_before_stopping_services(
    tmp_path: Path,
):
    for scenario in ("missing-hash", "missing-manifest", "tampered-quarantine"):
        case_path = tmp_path / scenario
        case_path.mkdir()
        repo, known_good, _ = _make_release_repo(case_path)
        rollback_runner = _stage_rollback_runner(case_path, repo)
        stage = rollback_runner.parent
        if scenario == "missing-hash":
            (stage / "staged.sha256").unlink()
        elif scenario == "missing-manifest":
            (stage / "review_manifest.json").unlink()
        else:
            with (stage / "quarantine_runtime_only_kb.py").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write("\n# tampered\n")

        bin_dir = _fake_commands(case_path, healthy=True)
        service_state = case_path / "service-state"
        service_state.write_text("active\n", encoding="utf-8")
        event_log = case_path / "rollback-events"
        lock_args = _release_lock_args(case_path)
        env = {
            **os.environ,
            **_process_proof_env(case_path),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "ROLLBACK_HEALTH_ATTEMPTS": "1",
            "FAKE_SERVICE_STATE": str(service_state),
            "FAKE_SCHEMA_PROBE_LOG": str(case_path / "schema-probe"),
            "FAKE_STOP_COUNT": str(case_path / "stop-count"),
            "FAKE_ROLLBACK_EVENT_LOG": str(event_log),
        }

        result = subprocess.run(
            [str(rollback_runner), str(repo), known_good, *lock_args],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        assert result.returncode != 0, scenario
        assert "ROLLBACK_OK" not in result.stdout
        assert service_state.read_text(encoding="utf-8").strip() == "active"
        assert not (case_path / "stop-count").exists()
        assert not event_log.exists()


def test_release_rollback_stops_socket_before_checkout_and_only_starts_after_probes(
    tmp_path: Path,
):
    repo, known_good, failed = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    runtime_state_runner = rollback_runner.with_name(
        "runtime_state_release_transaction.py"
    )
    assert runtime_state_runner.stat().st_mode & stat.S_IXUSR
    bin_dir = _fake_commands(tmp_path, healthy=True)
    _replace_systemctl_with_socket_activation_simulator(bin_dir)
    state_dir = tmp_path / "service-states"
    state_dir.mkdir()
    for service in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        (state_dir / f"{service}.state").write_text("active\n", encoding="utf-8")
    event_log = tmp_path / "rollback-events"
    lock_args = _release_lock_args(tmp_path)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "FAKE_SERVICE_STATE_DIR": str(state_dir),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_ROLLBACK_EVENT_LOG": str(event_log),
        "FAKE_RUNTIME_REPO": str(repo),
        "FAKE_RUNTIME_EXPECTED_HEAD": known_good,
        "FAKE_RUNTIME_EXPECTED_ROLLBACK": known_good,
    }

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (
        "RUNTIME_STATE_TRANSACTION_OK command=restore result=restored"
        in result.stdout.splitlines()
    )
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert "socket-reactivation" not in events
    assert events[:5] == [
        "stop:health-backend.socket",
        "stop:health-backend",
        "stop:celery-worker",
        "stop:celery-beat",
        "runtime-state-restore",
    ]
    assert events.index("runtime-state-restore") < events.index("kb-quarantine-ran")
    assert events.index("kb-quarantine-ran") < events.index("schema-probe-ran")
    assert events.index("schema-probe-ran") < events.index(
        "start:health-backend.socket"
    )
    assert events.index("start:health-backend.socket") < events.index(
        "start:health-backend"
    )
    assert events[-1] == "runtime-state-release-gate"


def test_release_rollback_revokes_durable_authorization_before_checkout(
    tmp_path: Path,
):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    durable_dir = tmp_path / "durable-state"
    durable_dir.mkdir()
    durable_enabled = durable_dir / "enabled.env"
    durable_enabled.write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    sync_log = tmp_path / "sync-events"
    service_state = tmp_path / "service-state"
    service_state.write_text("active\n", encoding="utf-8")
    lock_args = _release_lock_args(tmp_path)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "HEALTH_EVIDENCE_DURABLE_STATE_DIR": str(durable_dir),
        "FAKE_SERVICE_STATE": str(service_state),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(tmp_path / "rollback-events"),
        "FAKE_SYNC_LOG": str(sync_log),
    }

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not durable_enabled.exists()
    assert sync_log.read_text(encoding="utf-8").splitlines() == [
        str(durable_dir),
        str(repo / "backend/.env.rollback-release.tmp"),
        str(repo / "backend"),
    ]
    script = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    inactive = script.index("force_services_inactive")
    revoke = script.index("revoke_health_evidence_authorization", inactive)
    checkout = script.index('git checkout -B main "$ROLLBACK_COMMIT"')
    assert inactive < revoke < checkout


def test_release_rollback_moves_head_and_requires_health_check(tmp_path: Path):
    repo, known_good, failed = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "2",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_ENV_EXECUTED": str(tmp_path / "env-executed"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(tmp_path / "rollback-events"),
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")
    lock_args = _release_lock_args(tmp_path)

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert failed != known_good
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()
        == known_good
    )
    assert (repo / "release.txt").read_text(encoding="utf-8") == "known-good"
    assert "ROLLBACK_OK" in result.stdout
    assert (
        Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "active"
    )
    assert (
        Path(env["FAKE_SCHEMA_PROBE_LOG"]).read_text(encoding="utf-8").strip()
        == "schema-probe-ran"
    )
    assert not Path(env["FAKE_ENV_EXECUTED"]).exists()
    assert Path(env["FAKE_ROLLBACK_EVENT_LOG"]).read_text(
        encoding="utf-8"
    ).splitlines() == [
        "runtime-state-restore",
        "kb-quarantine-ran",
        "schema-probe-ran",
        "service-start",
        "service-start",
        "runtime-state-release-gate",
    ]
    assert "kb_quarantine=passed" in result.stdout


def test_release_rollback_candidate_floor_commits_then_finalizes(
    tmp_path: Path,
):
    repo, _, candidate = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    service_state = tmp_path / "service-state"
    service_state.write_text("active\n", encoding="utf-8")
    event_log = tmp_path / "rollback-events"
    lock_args = _release_lock_args(tmp_path)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "FAKE_SERVICE_STATE": str(service_state),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(event_log),
        "FAKE_RUNTIME_RESTORE_RESULT": "candidate-retained",
        "FAKE_RUNTIME_EXPECTED_ROLLBACK": candidate,
        "FAKE_RUNTIME_REPO": str(repo),
        "FAKE_RUNTIME_EXPECTED_HEAD": candidate,
    }

    result = subprocess.run(
        [str(rollback_runner), str(repo), candidate, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "runtime_state=candidate-retained" in result.stdout
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "runtime-state-restore",
        "kb-quarantine-ran",
        "schema-probe-ran",
        "service-start",
        "service-start",
        "runtime-state-commit",
        "runtime-state-finalize",
    ]


def _run_rollback_with_env_snapshots(
    tmp_path: Path,
    *,
    runtime_result: str,
    rollback_env: str,
    candidate_env: str,
    expected_env_at_start: str | None = None,
    fail_sync: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Path]]:
    repo, known_good, candidate = _make_release_repo(tmp_path)
    rollback_commit = known_good if runtime_result == "restored" else candidate
    rollback_runner = _stage_rollback_runner(
        tmp_path,
        repo,
        rollback_env=rollback_env,
        candidate_env=candidate_env,
    )
    live_env = repo / "backend/.env"
    live_env.write_text(candidate_env, encoding="utf-8")
    expected_env = tmp_path / "expected-env-at-start"
    if expected_env_at_start is not None:
        expected_env.write_text(expected_env_at_start, encoding="utf-8")

    bin_dir = _fake_commands(tmp_path, healthy=True)
    service_state = tmp_path / "service-state"
    service_state.write_text("active\n", encoding="utf-8")
    event_log = tmp_path / "rollback-events"
    lock_args = _release_lock_args(tmp_path)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "HEALTH_EVIDENCE_DURABLE_STATE_DIR": str(tmp_path / "durable-state"),
        "HEALTH_EVIDENCE_RUNTIME_STATE_DIR": str(tmp_path / "runtime-state"),
        "HEALTH_EVIDENCE_SYSTEMD_RUNTIME_DIR": str(tmp_path / "systemd-runtime"),
        "FAKE_SERVICE_STATE": str(service_state),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(event_log),
        "FAKE_RUNTIME_RESTORE_RESULT": runtime_result,
        "FAKE_RUNTIME_EXPECTED_ROLLBACK": rollback_commit,
        "FAKE_RUNTIME_REPO": str(repo),
        "FAKE_RUNTIME_EXPECTED_HEAD": rollback_commit,
        "FAKE_LIVE_ENV": str(live_env),
        "FAKE_SYNC_FAIL": "1" if fail_sync else "0",
    }
    if expected_env_at_start is not None:
        env["FAKE_EXPECT_ENV_AT_START"] = str(expected_env)

    result = subprocess.run(
        [str(rollback_runner), str(repo), rollback_commit, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    return result, {
        "live_env": live_env,
        "service_state": service_state,
        "event_log": event_log,
    }


def test_release_rollback_restores_legacy_env_before_starting_old_services(
    tmp_path: Path,
):
    rollback_env = "CONFIG_REVISION=old\n"
    expected_env = (
        rollback_env + "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    )
    candidate_env = (
        "CONFIG_REVISION=candidate\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    )

    result, paths = _run_rollback_with_env_snapshots(
        tmp_path,
        runtime_result="restored",
        rollback_env=rollback_env,
        candidate_env=candidate_env,
        expected_env_at_start=expected_env,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "runtime_state=restored" in result.stdout
    restored_lines = paths["live_env"].read_text(encoding="utf-8").splitlines()
    assert restored_lines == expected_env.splitlines()
    assert restored_lines.count(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false"
    ) == 1


def test_release_rollback_candidate_retained_never_overwrites_candidate_env(
    tmp_path: Path,
):
    rollback_env = (
        "CONFIG_REVISION=old\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    )
    candidate_env = (
        "CONFIG_REVISION=candidate\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    )

    result, paths = _run_rollback_with_env_snapshots(
        tmp_path,
        runtime_result="candidate-retained",
        rollback_env=rollback_env,
        candidate_env=candidate_env,
        expected_env_at_start=candidate_env,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "runtime_state=candidate-retained" in result.stdout
    assert paths["live_env"].read_text(encoding="utf-8") == candidate_env


def test_release_rollback_env_restore_failure_never_claims_success(
    tmp_path: Path,
):
    rollback_env = (
        "CONFIG_REVISION=old\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    )
    candidate_env = (
        "CONFIG_REVISION=candidate\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    )

    result, paths = _run_rollback_with_env_snapshots(
        tmp_path,
        runtime_result="restored",
        rollback_env=rollback_env,
        candidate_env=candidate_env,
        fail_sync=True,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert paths["live_env"].read_text(encoding="utf-8") == candidate_env
    assert paths["service_state"].read_text(encoding="utf-8").strip() == "inactive"
    if paths["event_log"].exists():
        assert "service-start" not in paths["event_log"].read_text(
            encoding="utf-8"
        )


def test_release_gate_failure_contains_all_services(tmp_path: Path):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    service_state = tmp_path / "service-state"
    service_state.write_text("active\n", encoding="utf-8")
    event_log = tmp_path / "rollback-events"
    lock_args = _release_lock_args(tmp_path)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "FAKE_SERVICE_STATE": str(service_state),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(event_log),
        "FAKE_RUNTIME_STATE_FAIL_COMMAND": "release-gate",
    }

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert service_state.read_text(encoding="utf-8").strip() == "inactive"
    assert event_log.read_text(encoding="utf-8").splitlines()[-1] == (
        "runtime-state-release-gate"
    )


def test_release_rollback_restart_window_never_claims_success(
    tmp_path: Path,
):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    service_state = tmp_path / "service-state"
    service_state.write_text("active\n", encoding="utf-8")
    metrics_dir = tmp_path / "service-metrics"
    metrics_dir.mkdir()
    for unit in ("health-backend", "celery-worker", "celery-beat"):
        (metrics_dir / f"{unit}.restarts").write_text("0\n", encoding="utf-8")
        (metrics_dir / f"{unit}.entered").write_text("1000\n", encoding="utf-8")
    event_log = tmp_path / "rollback-events"
    lock_args = _release_lock_args(tmp_path)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "FAKE_SERVICE_STATE": str(service_state),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(event_log),
        "FAKE_BUMP_RESTART_ON_STABILITY": "1",
        "FAKE_SERVICE_METRICS_DIR": str(metrics_dir),
        "FAKE_STABILITY_BUMP_MARKER": str(tmp_path / "restart-bumped"),
    }

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert service_state.read_text(encoding="utf-8").strip() == "inactive"
    assert Path(env["FAKE_STABILITY_BUMP_MARKER"]).exists()


def test_release_rollback_never_claims_success_when_health_check_fails(tmp_path: Path):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=False)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "2",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(tmp_path / "rollback-events"),
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")
    lock_args = _release_lock_args(tmp_path)

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert "健康检查失败" in result.stderr
    assert (
        Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip()
        == "inactive"
    )


def test_release_rollback_preflight_failure_does_not_stop_running_services(
    tmp_path: Path,
):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    (repo / "release.txt").write_text("uncommitted change", encoding="utf-8")
    bin_dir = _fake_commands(tmp_path, healthy=True)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "2",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(tmp_path / "rollback-events"),
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")
    lock_args = _release_lock_args(tmp_path)

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert "工作树存在未提交的 tracked 改动" in result.stderr
    assert (
        Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "active"
    )


def test_release_rollback_forces_services_inactive_when_cleanup_stop_fails(
    tmp_path: Path,
):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=False)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(tmp_path / "rollback-events"),
        "FAKE_STOP_FAIL_ON_CALL": "2",
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")
    lock_args = _release_lock_args(tmp_path)

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert "ROLLBACK_BLOCKED services=inactive" in result.stderr
    assert (
        Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip()
        == "inactive"
    )


def test_release_rollback_keeps_services_inactive_when_kb_quarantine_fails(
    tmp_path: Path,
):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(tmp_path / "rollback-events"),
        "FAKE_QUARANTINE_FAIL": "1",
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")
    lock_args = _release_lock_args(tmp_path)

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert (
        Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip()
        == "inactive"
    )
    assert Path(env["FAKE_ROLLBACK_EVENT_LOG"]).read_text(
        encoding="utf-8"
    ).splitlines() == [
        "runtime-state-restore",
        "kb-quarantine-ran",
    ]


def test_release_rollback_never_starts_services_after_server_lease_is_lost(
    tmp_path: Path,
):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    lock_args = _release_lock_args(tmp_path)
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "FAKE_SERVICE_STATE": str(tmp_path / "service-state"),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(tmp_path / "rollback-events"),
        "FAKE_RELEASE_LOCK_TOKEN_TO_REMOVE": str(Path(lock_args[0]) / "token"),
    }
    Path(env["FAKE_SERVICE_STATE"]).write_text("active\n", encoding="utf-8")

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert (
        Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip()
        == "inactive"
    )
    assert Path(env["FAKE_ROLLBACK_EVENT_LOG"]).read_text(
        encoding="utf-8"
    ).splitlines() == [
        "runtime-state-restore",
        "kb-quarantine-ran",
    ]
