import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SCRIPT = ROOT / "backend/scripts/rollback_release.sh"
STAGED_ARTIFACTS = (
    "backup_db.sh",
    "verify_backup_restore.sh",
    "archive_backup_offsite.sh",
    "rollback_release.sh",
    "activate_health_evidence_runtime.sh",
    "verify_runtime_schema_compatibility.py",
    "quarantine_runtime_only_kb.py",
    "review_manifest.json",
)


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
    assert 'backend/data/system_kb_v2_seed/review_manifest.json' not in script


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
    assert 'ROLLBACK_PROC_ROOT/$pid/environ' in verify_body
    assert final_start < final_proof < success


def _make_release_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "release"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "security@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Security Test"], cwd=repo, check=True)
    (repo / "backend/venv/bin").mkdir(parents=True)
    (repo / "backend/requirements.lock").write_text("", encoding="utf-8")
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
    known_good = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
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
    failed = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    return repo, known_good, failed


def _stage_rollback_runner(tmp_path: Path, repo: Path) -> Path:
    stage = tmp_path / "staged-release"
    stage.mkdir()
    source_dir = ROOT / "backend/scripts"
    for name in STAGED_ARTIFACTS:
        if name == "review_manifest.json":
            source = repo / "backend/data/system_kb_v2_seed/review_manifest.json"
        else:
            source = source_dir / name
        shutil.copy2(source, stage / name)

    lines = []
    for name in STAGED_ARTIFACTS:
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
    printf 'service-start\n' >> "$FAKE_ROLLBACK_EVENT_LOG"
    printf 'active\n' > "$FAKE_SERVICE_STATE"
    ;;
  is-active) test "$(cat "$FAKE_SERVICE_STATE")" = active ;;
  kill) printf 'inactive\n' > "$FAKE_SERVICE_STATE" ;;
  reset-failed) exit 0 ;;
  daemon-reload) exit 0 ;;
  show)
    case "$*" in
      *--property=MainPID*) printf '4242\n' ;;
      *--property=ControlGroup*) printf '/health-test\n' ;;
      *) cat "$FAKE_SERVICE_STATE" ;;
    esac
    ;;
  *) exit 1 ;;
esac
""",
    )
    _write_executable(bin_dir / "sleep", "#!/bin/sh\nexit 0\n")
    _write_executable(
        bin_dir / "sync",
        """#!/bin/sh
test "$1" = "-f"
test -e "$2"
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
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
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
    }

    result = subprocess.run(
        [str(rollback_runner), str(repo), known_good, *lock_args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert "socket-reactivation" not in events
    assert events[:4] == [
        "stop:health-backend.socket",
        "stop:health-backend",
        "stop:celery-worker",
        "stop:celery-beat",
    ]
    assert events.index("kb-quarantine-ran") < events.index("schema-probe-ran")
    assert events.index("schema-probe-ran") < events.index(
        "start:health-backend.socket"
    )
    assert events.index("start:health-backend.socket") < events.index(
        "start:health-backend"
    )


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
        str(durable_dir)
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
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip() == known_good
    assert (repo / "release.txt").read_text(encoding="utf-8") == "known-good"
    assert "ROLLBACK_OK" in result.stdout
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "active"
    assert Path(env["FAKE_SCHEMA_PROBE_LOG"]).read_text(encoding="utf-8").strip() == "schema-probe-ran"
    assert not Path(env["FAKE_ENV_EXECUTED"]).exists()
    assert Path(env["FAKE_ROLLBACK_EVENT_LOG"]).read_text(encoding="utf-8").splitlines() == [
        "kb-quarantine-ran",
        "schema-probe-ran",
        "service-start",
        "service-start",
    ]
    assert "kb_quarantine=passed" in result.stdout


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
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "inactive"


def test_release_rollback_preflight_failure_does_not_stop_running_services(tmp_path: Path):
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
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "active"


def test_release_rollback_forces_services_inactive_when_cleanup_stop_fails(tmp_path: Path):
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
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "inactive"


def test_release_rollback_keeps_services_inactive_when_kb_quarantine_fails(tmp_path: Path):
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
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "inactive"
    assert Path(env["FAKE_ROLLBACK_EVENT_LOG"]).read_text(encoding="utf-8").splitlines() == [
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
        "FAKE_RELEASE_LOCK_TOKEN_TO_REMOVE": str(
            Path(lock_args[0]) / "token"
        ),
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
    assert Path(env["FAKE_SERVICE_STATE"]).read_text(encoding="utf-8").strip() == "inactive"
    assert Path(env["FAKE_ROLLBACK_EVENT_LOG"]).read_text(encoding="utf-8").splitlines() == [
        "kb-quarantine-ran",
    ]
