import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SCRIPT = ROOT / "backend/scripts/rollback_release.sh"
REQUIRED_ARTIFACT_NAMES = (
    "backup_db.sh",
    "verify_backup_restore.sh",
    "archive_backup_offsite.sh",
    "rollback_release.sh",
    "activate_health_evidence_runtime.sh",
    "verify_locked_requirements.py",
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
import stat
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
stage_dir = Path(__file__).resolve().parent
token_path = release_lock_dir / "token"
stage_path = release_lock_dir / "stage"
if stat.S_IMODE(release_lock_dir.stat().st_mode) != 0o700:
    fail("fake runtime transaction observed invalid release lock mode")
if stat.S_IMODE(token_path.stat().st_mode) != 0o600:
    fail("fake runtime transaction observed invalid token mode")
if stat.S_IMODE(stage_path.stat().st_mode) != 0o600:
    fail("fake runtime transaction observed invalid stage pointer mode")
if token_path.stat().st_nlink != 1:
    fail("fake runtime transaction observed hard-linked token")
if stage_path.stat().st_nlink != 1:
    fail("fake runtime transaction observed hard-linked stage pointer")
if os.environ.get("FAKE_LOCK_OWNER", "root:root") != "root:root":
    fail("fake runtime transaction observed invalid release lock owner")
if os.environ.get("FAKE_TOKEN_OWNER", "root:root") != "root:root":
    fail("fake runtime transaction observed invalid token owner")
if os.environ.get("FAKE_LOCK_STAGE_OWNER", "root:root") != "root:root":
    fail("fake runtime transaction observed invalid stage pointer owner")
if token_path.read_text(encoding="utf-8") != release_lock_token + "\\n":
    fail("fake runtime transaction observed a lost release lock")
if stage_path.read_text(encoding="utf-8") != str(stage_dir) + "\\n":
    fail("fake runtime transaction observed a mismatched release stage")

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


@pytest.fixture(autouse=True)
def _isolate_release_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "REMOTE_RELEASE_STATE_DIR",
        str(tmp_path / "release-state"),
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
    assert 'sha256sum --strict -c "$STAGED_HASH_MANIFEST"' in script
    assert 'cmp -s "$REMOTE_RELEASE_LOCK_DIR/token"' in script
    assert 'cmp -s "$REMOTE_RELEASE_LOCK_DIR/stage"' in script
    assert '<(printf \'%s\\n\' "$REMOTE_RELEASE_LOCK_TOKEN")' in script
    assert '<(printf \'%s\\n\' "$SCRIPT_DIR")' in script
    assert '"root:root:700"' in script
    assert '"root:root:400"' in script
    assert "shopt -s nullglob dotglob" in script
    assert script.count('/usr/bin/python3 -I "$RUNTIME_STATE_RUNNER"') == 4
    assert '/usr/bin/python3 "$RUNTIME_STATE_RUNNER"' not in script
    assert "backend/data/system_kb_v2_seed/review_manifest.json" not in script
    for artifact_name in REQUIRED_ARTIFACT_NAMES:
        assert artifact_name in script

    services_touched = script.index("SERVICES_TOUCHED=1")
    writers_inactive = script.index("force_services_inactive", services_touched)
    restore = script.index(
        '/usr/bin/python3 -I "$RUNTIME_STATE_RUNNER"',
        writers_inactive,
    )
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


def test_rollback_restores_service_readable_env_metadata():
    script = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    select_start = script.index("select_release_env_for_runtime_result() {")
    select_end = script.index("revoke_health_evidence_authorization() {", select_start)
    select_body = script[select_start:select_end]

    assert 'chown root:health-app "$target_tmp"' in select_body
    assert 'chmod 0640 "$target_tmp"' in select_body
    assert 'mv -fT -- "$target_tmp" "$target_env"' in select_body
    assert '"root:health-app:640"' in select_body
    assert 'chmod 0600 "$target_tmp"' not in select_body


def test_rollback_rewrites_verified_dependency_marker_before_service_start():
    script = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    install = script.index(
        "backend/venv/bin/pip install --require-hashes -r backend/requirements.lock"
    )
    uninstall = script.index(
        "backend/venv/bin/python -m pip uninstall --yes chromadb chroma-hnswlib",
        install,
    )
    exact = script.index('"$LOCKED_REQUIREMENTS_VERIFIER"', uninstall)
    sanitize = script.index("--sanitize-forbidden-packages", exact)
    pip_check = script.index("backend/venv/bin/python -m pip check", exact)
    marker = script.index("requirements-lock.sha256", pip_check)
    start = script.index('systemctl start "$BACKEND_SOCKET"', marker)

    assert install < uninstall < exact < sanitize < pip_check < marker < start
    assert "root:root:700" in script[install:start]
    assert "root:root:600" in script[install:start]
    assert "mv -fT --" in script[install:start]
    quarantine = script.index('"$KB_QUARANTINE"', marker)
    kb_invalidate = script.index("system-kb-input.sha256", quarantine)
    assert marker < quarantine < kb_invalidate < start


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
    (repo / "backend/requirements.lock").write_text(
        "chromadb==0.6.3\nchroma-hnswlib==0.7.6\n",
        encoding="utf-8",
    )
    (repo / "backend/scripts").mkdir(parents=True)
    (repo / "backend/scripts/verify_locked_requirements.py").write_text(
        "# Legacy target verifier intentionally permits its own Chroma lock.\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text("backend/.env\n", encoding="utf-8")
    (repo / "backend/.env").write_text(
        "DATABASE_URL=sqlite:///:memory:\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        'touch "$FAKE_ENV_EXECUTED"\n',
        encoding="utf-8",
    )
    _write_executable(
        repo / "backend/venv/bin/pip",
        """#!/bin/sh
if [ -n "${FAKE_DEPENDENCY_EVENT_LOG:-}" ]; then
  if grep -q '^chromadb==' backend/requirements.lock; then
    printf 'chroma-packages-installed\n' > "$FAKE_INSTALLED_DEPENDENCY_STATE"
    printf 'pip-install-old-lock\n' >> "$FAKE_DEPENDENCY_EVENT_LOG"
  else
    rm -f "$FAKE_INSTALLED_DEPENDENCY_STATE"
    printf 'pip-install-candidate-lock\n' >> "$FAKE_DEPENDENCY_EVENT_LOG"
  fi
fi
exit 0
""",
    )
    _write_executable(
        repo / "backend/venv/bin/python",
        """#!/bin/sh
case "$1" in
  *verify_locked_requirements.py)
    if [ -n "${FAKE_DEPENDENCY_EVENT_LOG:-}" ]; then
      test "$2" = "--sanitize-forbidden-packages"
      test "$3" = "backend/requirements.lock"
      test ! -f "$FAKE_INSTALLED_DEPENDENCY_STATE"
      printf 'candidate-sanitized-lock-verifier\n' >> "$FAKE_DEPENDENCY_EVENT_LOG"
    fi
    exit 0
    ;;
  -m)
    test "$2" = "pip"
    if [ "$3" = "uninstall" ]; then
      test "$4" = "--yes"
      test "$5" = "chromadb"
      test "$6" = "chroma-hnswlib"
      if [ -n "${FAKE_INSTALLED_DEPENDENCY_STATE:-}" ]; then
        rm -f "$FAKE_INSTALLED_DEPENDENCY_STATE"
      fi
      if [ -n "${FAKE_DEPENDENCY_EVENT_LOG:-}" ]; then
        printf 'chroma-packages-uninstalled\n' >> "$FAKE_DEPENDENCY_EVENT_LOG"
      fi
      exit 0
    fi
    test "$3" = "check"
    exit 0
    ;;
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
    (repo / "backend/requirements.lock").write_text(
        "safe-package==1.0.0\n",
        encoding="utf-8",
    )
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
    subprocess.run(
        ["git", "add", "release.txt", "backend/requirements.lock"],
        cwd=repo,
        check=True,
    )
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
    stage_name: str = "staged-release",
) -> Path:
    stage = tmp_path / stage_name
    stage.mkdir(mode=0o700)
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
    (stage / "staged.sha256").chmod(0o400)
    return stage / "rollback_release.sh"


def _release_lock_args(
    tmp_path: Path,
    *,
    stage: Path | None = None,
) -> tuple[str, str]:
    lock_dir = tmp_path / "remote-release.lock"
    lock_dir.mkdir(mode=0o700)
    token = "test-release-owner"
    (lock_dir / "token").write_text(token + "\n", encoding="utf-8")
    (lock_dir / "token").chmod(0o600)
    (lock_dir / "stage").write_text(
        str(stage or (tmp_path / "staged-release")) + "\n",
        encoding="utf-8",
    )
    (lock_dir / "stage").chmod(0o600)
    return str(lock_dir), token


def _fake_commands(tmp_path: Path, *, healthy: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_owner = tmp_path / "fake-env-owner"
    fake_owner.write_text("root:root\n", encoding="utf-8")
    _write_executable(
        bin_dir / "chown",
        f"""#!/bin/sh
set -eu
test "$1" = "root:health-app"
test -f "$2"
if [ "${{FAKE_CHOWN_NO_EFFECT:-0}}" != "1" ]; then
  printf '%s\n' "$1" > "{fake_owner}"
fi
""",
    )
    _write_executable(
        bin_dir / "stat",
        f"""#!/bin/sh
set -eu
test "$1" = "-c"
test -e "$3" || test -L "$3"
if [ "$2" = "%h" ]; then
  if links=$(/usr/bin/stat -c '%h' "$3" 2>/dev/null); then
    :
  else
    links=$(/usr/bin/stat -f '%l' "$3")
  fi
  printf '%s\n' "$links"
  exit 0
fi
test "$2" = "%U:%G:%a"
if mode=$(/usr/bin/stat -c '%a' "$3" 2>/dev/null); then
  :
else
  mode=$(/usr/bin/stat -f '%Lp' "$3")
fi
case "$3" in
  */release-state|*/release-state/*)
    owner="root:root"
    ;;
  */remote-release.lock)
    owner="${{FAKE_LOCK_OWNER:-root:root}}"
    ;;
  */remote-release.lock/token)
    owner="${{FAKE_TOKEN_OWNER:-root:root}}"
    ;;
  */remote-release.lock/stage)
    owner="${{FAKE_LOCK_STAGE_OWNER:-root:root}}"
    ;;
  */staged-release|*/staged-release-*)
    owner="${{FAKE_STAGE_OWNER:-root:root}}"
    ;;
  */staged-release/staged.sha256|*/staged-release-*/staged.sha256)
    owner="${{FAKE_MANIFEST_OWNER:-root:root}}"
    ;;
  *)
    owner="$(cat "{fake_owner}")"
    ;;
esac
printf '%s:%s\n' "$owner" "$mode"
""",
    )
    _write_executable(
        bin_dir / "mv",
        """#!/bin/sh
set -eu
test "$1" = "-fT"
test "$2" = "--"
if [ "${FAKE_MV_FAIL:-0}" = "1" ]; then
  exit 89
fi
/bin/mv -f "$3" "$4"
""",
    )
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
set -eu
test "$1" = "-f"
test -e "$2"
count=0
if [ -n "${FAKE_SYNC_COUNT:-}" ] && [ -f "$FAKE_SYNC_COUNT" ]; then
  count=$(cat "$FAKE_SYNC_COUNT")
fi
count=$((count + 1))
if [ -n "${FAKE_SYNC_COUNT:-}" ]; then
  printf '%s\n' "$count" > "$FAKE_SYNC_COUNT"
fi
if [ "${FAKE_SYNC_FAIL:-0}" = "1" ] ||
   [ "${FAKE_SYNC_FAIL_ON_CALL:-0}" = "$count" ]; then
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
    for scenario in (
        "missing-hash",
        "missing-manifest",
        "tampered-quarantine",
        "extra-python-module",
        "stage-mismatch",
        "wrong-stage-mode",
        "wrong-manifest-mode",
        "wrong-stage-owner",
        "wrong-manifest-owner",
    ):
        case_path = tmp_path / scenario
        case_path.mkdir()
        repo, known_good, _ = _make_release_repo(case_path)
        rollback_runner = _stage_rollback_runner(case_path, repo)
        stage = rollback_runner.parent
        fake_stage_owner = "root:root"
        fake_manifest_owner = "root:root"
        if scenario == "missing-hash":
            (stage / "staged.sha256").unlink()
        elif scenario == "missing-manifest":
            (stage / "review_manifest.json").unlink()
        elif scenario == "tampered-quarantine":
            with (stage / "quarantine_runtime_only_kb.py").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write("\n# tampered\n")
        elif scenario == "extra-python-module":
            (stage / "hashlib.py").write_text(
                "raise RuntimeError('stage import shadow executed')\n",
                encoding="utf-8",
            )
        elif scenario == "wrong-stage-mode":
            stage.chmod(0o755)
        elif scenario == "wrong-manifest-mode":
            (stage / "staged.sha256").chmod(0o600)
        elif scenario == "wrong-stage-owner":
            fake_stage_owner = "root:health-app"
        elif scenario == "wrong-manifest-owner":
            fake_manifest_owner = "root:health-app"

        bin_dir = _fake_commands(case_path, healthy=True)
        service_state = case_path / "service-state"
        service_state.write_text("active\n", encoding="utf-8")
        event_log = case_path / "rollback-events"
        lock_args = _release_lock_args(
            case_path,
            stage=(
                case_path / "different-sealed-stage"
                if scenario == "stage-mismatch"
                else stage
            ),
        )
        env = {
            **os.environ,
            **_process_proof_env(case_path),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "ROLLBACK_HEALTH_ATTEMPTS": "1",
            "FAKE_SERVICE_STATE": str(service_state),
            "FAKE_SCHEMA_PROBE_LOG": str(case_path / "schema-probe"),
            "FAKE_STOP_COUNT": str(case_path / "stop-count"),
            "FAKE_ROLLBACK_EVENT_LOG": str(event_log),
            "FAKE_STAGE_OWNER": fake_stage_owner,
            "FAKE_MANIFEST_OWNER": fake_manifest_owner,
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


@pytest.mark.parametrize(
    "scenario",
    (
        "lock-mode",
        "token-mode",
        "stage-pointer-mode",
        "lock-owner",
        "token-owner",
        "stage-pointer-owner",
        "token-missing-newline",
        "token-extra-newline",
        "stage-pointer-missing-newline",
        "stage-pointer-extra-newline",
        "token-hardlink",
        "stage-pointer-hardlink",
    ),
)
def test_release_rollback_rejects_unsafe_lock_metadata_before_stopping_services(
    tmp_path: Path,
    scenario: str,
):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    service_state = tmp_path / "service-state"
    service_state.write_text("active\n", encoding="utf-8")
    event_log = tmp_path / "rollback-events"
    lock_args = _release_lock_args(tmp_path, stage=rollback_runner.parent)
    lock_dir = Path(lock_args[0])
    if scenario == "lock-mode":
        lock_dir.chmod(0o755)
    elif scenario == "token-mode":
        (lock_dir / "token").chmod(0o644)
    elif scenario == "stage-pointer-mode":
        (lock_dir / "stage").chmod(0o644)
    elif scenario == "token-missing-newline":
        (lock_dir / "token").write_text(lock_args[1], encoding="utf-8")
    elif scenario == "token-extra-newline":
        (lock_dir / "token").write_text(lock_args[1] + "\n\n", encoding="utf-8")
    elif scenario == "stage-pointer-missing-newline":
        (lock_dir / "stage").write_text(
            str(rollback_runner.parent),
            encoding="utf-8",
        )
    elif scenario == "stage-pointer-extra-newline":
        (lock_dir / "stage").write_text(
            str(rollback_runner.parent) + "\n\n",
            encoding="utf-8",
        )
    elif scenario == "token-hardlink":
        os.link(lock_dir / "token", tmp_path / "token-hardlink")
    elif scenario == "stage-pointer-hardlink":
        os.link(lock_dir / "stage", tmp_path / "stage-hardlink")
    env = {
        **os.environ,
        **_process_proof_env(tmp_path),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ROLLBACK_HEALTH_ATTEMPTS": "1",
        "FAKE_SERVICE_STATE": str(service_state),
        "FAKE_SCHEMA_PROBE_LOG": str(tmp_path / "schema-probe"),
        "FAKE_STOP_COUNT": str(tmp_path / "stop-count"),
        "FAKE_ROLLBACK_EVENT_LOG": str(event_log),
        "FAKE_LOCK_OWNER": (
            "root:health-app" if scenario == "lock-owner" else "root:root"
        ),
        "FAKE_TOKEN_OWNER": (
            "root:health-app" if scenario == "token-owner" else "root:root"
        ),
        "FAKE_LOCK_STAGE_OWNER": (
            "root:health-app"
            if scenario == "stage-pointer-owner"
            else "root:root"
        ),
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
    assert service_state.read_text(encoding="utf-8").strip() == "active"
    assert not (tmp_path / "stop-count").exists()
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
    sync_events = sync_log.read_text(encoding="utf-8").splitlines()
    assert sync_events[:3] == [
        str(durable_dir),
        str(repo / "backend/.env.rollback-release.tmp"),
        str(repo / "backend"),
    ]
    assert Path(sync_events[3]).parent == tmp_path / "release-state"
    assert Path(sync_events[3]).name.startswith(".requirements-lock.rollback.")
    assert sync_events[4] == str(tmp_path / "release-state")
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
    assert stat.S_IMODE((repo / "backend/.env").stat().st_mode) == 0o640
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


def test_release_rollback_sanitizes_legacy_chroma_from_old_lock_before_start(
    tmp_path: Path,
):
    repo, known_good, _ = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    service_state = tmp_path / "service-state"
    service_state.write_text("active\n", encoding="utf-8")
    event_log = tmp_path / "rollback-events"
    dependency_state = tmp_path / "installed-dependency-state"
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
        "FAKE_DEPENDENCY_EVENT_LOG": str(event_log),
        "FAKE_INSTALLED_DEPENDENCY_STATE": str(dependency_state),
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
    assert (repo / "backend/requirements.lock").read_text(
        encoding="utf-8"
    ) == "chromadb==0.6.3\nchroma-hnswlib==0.7.6\n"
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert "pip-install-old-lock" in events
    assert "chroma-packages-uninstalled" in events
    assert "candidate-sanitized-lock-verifier" in events
    assert events.index("pip-install-old-lock") < events.index(
        "chroma-packages-uninstalled"
    ) < events.index("candidate-sanitized-lock-verifier") < events.index(
        "service-start"
    )
    assert not dependency_state.exists()
    assert "ROLLBACK_OK" in result.stdout
    assert service_state.read_text(encoding="utf-8").strip() == "active"
    assert (
        tmp_path / "release-state" / "requirements-lock.sha256"
    ).is_file()


def test_release_rollback_candidate_floor_commits_then_finalizes(
    tmp_path: Path,
):
    repo, _, candidate = _make_release_repo(tmp_path)
    rollback_runner = _stage_rollback_runner(tmp_path, repo)
    bin_dir = _fake_commands(tmp_path, healthy=True)
    (repo / "backend/.env").chmod(0o640)
    (tmp_path / "fake-env-owner").write_text(
        "root:health-app\n",
        encoding="utf-8",
    )
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
    sync_fail_on_call: int = 0,
    initial_owner: str | None = None,
    initial_mode: int | None = None,
    chown_no_effect: bool = False,
    target_env_kind: str = "file",
    fail_mv: bool = False,
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
    if initial_mode is None:
        initial_mode = 0o640 if runtime_result == "candidate-retained" else 0o600
    live_env.chmod(initial_mode)
    redirected_env_dir = tmp_path / "redirected-env-dir"
    if target_env_kind == "directory":
        live_env.unlink()
        live_env.mkdir()
        redirected_env_dir = live_env
    elif target_env_kind == "symlink-directory":
        live_env.unlink()
        redirected_env_dir.mkdir()
        live_env.symlink_to(redirected_env_dir, target_is_directory=True)
    elif target_env_kind == "symlink-regular":
        live_env.unlink()
        redirected_env_dir.write_text(candidate_env, encoding="utf-8")
        live_env.symlink_to(redirected_env_dir)
    elif target_env_kind != "file":
        raise ValueError(f"unknown target_env_kind: {target_env_kind}")
    expected_env = tmp_path / "expected-env-at-start"
    if expected_env_at_start is not None:
        expected_env.write_text(expected_env_at_start, encoding="utf-8")

    bin_dir = _fake_commands(tmp_path, healthy=True)
    fake_owner = tmp_path / "fake-env-owner"
    fake_owner.write_text(
        (initial_owner or (
            "root:health-app"
            if runtime_result == "candidate-retained"
            else "root:root"
        ))
        + "\n",
        encoding="utf-8",
    )
    service_state = tmp_path / "service-state"
    service_state.write_text("active\n", encoding="utf-8")
    event_log = tmp_path / "rollback-events"
    lock_args = _release_lock_args(tmp_path)
    release_state_dir = tmp_path / "release-state"
    system_kb_marker = release_state_dir / "system-kb-input.sha256"
    if not release_state_dir.exists():
        release_state_dir.mkdir(mode=0o700)
        system_kb_marker.write_text("stale-after-quarantine\n", encoding="utf-8")
        system_kb_marker.chmod(0o600)
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
        "FAKE_SYNC_FAIL_ON_CALL": str(sync_fail_on_call),
        "FAKE_SYNC_COUNT": str(tmp_path / "sync-count"),
        "FAKE_CHOWN_NO_EFFECT": "1" if chown_no_effect else "0",
        "FAKE_MV_FAIL": "1" if fail_mv else "0",
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
        "fake_owner": fake_owner,
        "redirected_env_dir": redirected_env_dir,
        "requirements_marker": tmp_path
        / "release-state"
        / "requirements-lock.sha256",
        "system_kb_marker": system_kb_marker,
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
    expected_lock_digest = hashlib.sha256(
        (paths["live_env"].parent / "requirements.lock").read_bytes()
    ).hexdigest()
    assert paths["requirements_marker"].read_text(encoding="utf-8") == (
        expected_lock_digest + "\n"
    )
    assert not paths["system_kb_marker"].exists()
    assert restored_lines.count(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false"
    ) == 1
    assert stat.S_IMODE(paths["live_env"].stat().st_mode) == 0o640
    assert paths["fake_owner"].read_text(encoding="utf-8").strip() == (
        "root:health-app"
    )


def test_release_rollback_rejects_symlinked_dependency_state_before_restart(
    tmp_path: Path,
):
    attacker = tmp_path / "attacker-state"
    attacker.mkdir()
    state_dir = tmp_path / "release-state"
    state_dir.symlink_to(attacker, target_is_directory=True)

    result, paths = _run_rollback_with_env_snapshots(
        tmp_path,
        runtime_result="restored",
        rollback_env="CONFIG_REVISION=old\n",
        candidate_env=(
            "CONFIG_REVISION=candidate\n"
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        ),
    )

    assert result.returncode != 0
    assert paths["service_state"].read_text(encoding="utf-8").strip() == "inactive"
    assert list(attacker.iterdir()) == []


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
    assert stat.S_IMODE(paths["live_env"].stat().st_mode) == 0o640
    assert paths["fake_owner"].read_text(encoding="utf-8").strip() == (
        "root:health-app"
    )


def test_release_rollback_restored_branch_rejects_ineffective_chown(
    tmp_path: Path,
):
    result, paths = _run_rollback_with_env_snapshots(
        tmp_path,
        runtime_result="restored",
        rollback_env="HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        candidate_env="HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
        initial_owner="root:root",
        chown_no_effect=True,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert paths["fake_owner"].read_text(encoding="utf-8").strip() == "root:root"
    assert paths["service_state"].read_text(encoding="utf-8").strip() == "inactive"


def test_release_rollback_candidate_retained_rejects_wrong_env_metadata(
    tmp_path: Path,
):
    for label, owner, mode in (
        ("wrong-owner", "root:root", 0o640),
        ("wrong-mode", "root:health-app", 0o600),
    ):
        case_path = tmp_path / label
        case_path.mkdir()
        result, paths = _run_rollback_with_env_snapshots(
            case_path,
            runtime_result="candidate-retained",
            rollback_env="HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
            candidate_env="HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
            initial_owner=owner,
            initial_mode=mode,
        )

        assert result.returncode != 0, label
        assert "ROLLBACK_OK" not in result.stdout
        assert paths["service_state"].read_text(
            encoding="utf-8"
        ).strip() == "inactive"


def test_release_rollback_rejects_nonregular_env_destination_without_write(
    tmp_path: Path,
):
    for target_kind in ("directory", "symlink-directory", "symlink-regular"):
        case_path = tmp_path / target_kind
        case_path.mkdir()
        result, paths = _run_rollback_with_env_snapshots(
            case_path,
            runtime_result="restored",
            rollback_env=(
                "SECRET_SENTINEL=must-not-move\n"
                "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
            ),
            candidate_env="HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n",
            target_env_kind=target_kind,
        )

        assert result.returncode != 0, target_kind
        assert "ROLLBACK_OK" not in result.stdout
        assert paths["service_state"].read_text(
            encoding="utf-8"
        ).strip() == "inactive"
        if target_kind == "symlink-regular":
            assert paths["redirected_env_dir"].read_text(
                encoding="utf-8"
            ) == "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        else:
            assert list(paths["redirected_env_dir"].glob("*")) == []


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


def test_release_rollback_post_rename_directory_sync_failure_stays_inactive(
    tmp_path: Path,
):
    rollback_env = (
        "CONFIG_REVISION=old\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    )
    result, paths = _run_rollback_with_env_snapshots(
        tmp_path,
        runtime_result="restored",
        rollback_env=rollback_env,
        candidate_env=(
            "CONFIG_REVISION=candidate\n"
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        ),
        sync_fail_on_call=2,
    )

    assert result.returncode != 0
    assert "ROLLBACK_OK" not in result.stdout
    assert paths["live_env"].read_text(encoding="utf-8") == rollback_env
    assert paths["service_state"].read_text(encoding="utf-8").strip() == "inactive"
    if paths["event_log"].exists():
        assert "service-start" not in paths["event_log"].read_text(
            encoding="utf-8"
        )


def test_release_rollback_env_rename_failure_never_claims_success(
    tmp_path: Path,
):
    candidate_env = (
        "CONFIG_REVISION=candidate\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    )
    result, paths = _run_rollback_with_env_snapshots(
        tmp_path,
        runtime_result="restored",
        rollback_env=(
            "CONFIG_REVISION=old\n"
            "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        ),
        candidate_env=candidate_env,
        fail_mv=True,
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
