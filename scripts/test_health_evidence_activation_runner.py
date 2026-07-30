import hashlib
import os
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ACTIVATION_RUNNER = (
    ROOT / "backend/scripts/activate_health_evidence_runtime.sh"
)
SUCCESS_TEMPLATE = (
    "HEALTH_EVIDENCE_ACTIVATION_OK commit={sha} flag=true "
    "health=passed auth_probe=passed score=passed "
    "contract=enabled services=active"
)
ROLLBACK_TEMPLATE = (
    "HEALTH_EVIDENCE_ACTIVATION_ROLLED_BACK commit={sha} flag=false "
    "health=passed contract=staged services=active"
)
BLOCKED_TEMPLATE = (
    "HEALTH_EVIDENCE_ACTIVATION_BLOCKED commit={sha} flag=unknown "
    "services=inactive containment=passed manual_intervention=required"
)
DEADMAN_NOOP_TEMPLATE = (
    "HEALTH_EVIDENCE_DEADMAN_NOOP commit={sha} authorization=verified"
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_release_repo(tmp_path: Path) -> tuple[Path, str]:
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
    (repo / ".gitignore").write_text("backend/.env\n", encoding="utf-8")
    (repo / "backend/venv/bin").mkdir(parents=True)
    (repo / "backend/scripts").mkdir(parents=True)
    (repo / "backend/scripts/system_health_score.py").write_text(
        "# score probe fixture\n", encoding="utf-8"
    )
    (repo / "backend/scripts/verify_runtime_only_kb_contract.py").write_text(
        "# contract probe fixture\n", encoding="utf-8"
    )
    _write_executable(
        repo / "backend/venv/bin/python",
        """#!/bin/bash
set -euo pipefail
flag="${HEALTH_EVIDENCE_RUNTIME_ENABLED:-$(awk -F= '/^HEALTH_EVIDENCE_RUNTIME_ENABLED=/{print $2}' "$FAKE_REPO/backend/.env")}"
case "$1" in
  *system_health_score.py)
    printf 'python:score:flag=%s\n' "$flag" >> "$FAKE_ACTIVATION_EVENT_LOG"
    printf '{"pass": true, "total_score": 60, "threshold": 35, "max_possible": 60, "critical_failures": []}\n'
    ;;
  *verify_runtime_only_kb_contract.py)
    phase=
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "--phase" ]; then phase="$2"; break; fi
      shift
    done
    printf 'python:contract:%s:flag=%s\n' "$phase" "$flag" >> "$FAKE_ACTIVATION_EVENT_LOG"
    if [ "$phase" = "enabled" ]; then
      if [ -n "${FAKE_ENABLED_READY_FILE:-}" ]; then
        : > "$FAKE_ENABLED_READY_FILE"
        /bin/sleep "${FAKE_ENABLED_PAUSE_SECONDS:-0}"
      fi
      test "$flag" = "true"
      test "${FAKE_FAIL_ENABLED_CONTRACT:-0}" != "1"
    else
      test "$phase" = "staged"
      test "$flag" = "false"
      test "${FAKE_FAIL_STAGED_CONTRACT:-0}" != "1"
    fi
    ;;
  *) exit 91 ;;
esac
""",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "release fixture"], cwd=repo, check=True
    )
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    return repo, sha


def _fake_commands(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "systemctl",
        """#!/bin/bash
set -euo pipefail
normalize_unit() {
  case "$1" in
    *.service) printf '%s' "${1%.service}" ;;
    *) printf '%s' "$1" ;;
  esac
}
state_file() {
  local unit
  unit="$(normalize_unit "$1")"
  printf '%s/%s.state' "$FAKE_SERVICE_STATE_DIR" "$unit"
}
main_pid() {
  case "$(normalize_unit "$1")" in
    health-backend) printf '2101' ;;
    celery-worker) printf '2201' ;;
    celery-beat) printf '2301' ;;
    *) printf '0' ;;
  esac
}
control_group() {
  printf '/system.slice/%s.service' "$(normalize_unit "$1")"
}
write_process_environment() {
  local unit="$1"
  local normalized
  local flag
  local dropin
  local runtime_env
  local cgroup
  local pid
  local child_pid
  normalized="$(normalize_unit "$unit")"
  case "$normalized" in
    health-backend|celery-worker|celery-beat) ;;
    *) return 0 ;;
  esac
  flag="$(
    awk -F= '
      $1 == "HEALTH_EVIDENCE_RUNTIME_ENABLED" { value=$2 }
      END { print value }
    ' "$FAKE_REPO/backend/.env"
  )"
  persistent_dropin="$FAKE_SYSTEMD_PERSISTENT_DIR/$normalized.service.d/80-reva-health-evidence-runtime.conf"
  if [ -e "$persistent_dropin" ]; then
    test "$(grep -c '^EnvironmentFile=-' "$persistent_dropin")" -eq 1
    persistent_env="$(awk -F= '/^EnvironmentFile=-/{print $2}' "$persistent_dropin")"
    persistent_env="${persistent_env#-}"
    test "$persistent_env" = "$FAKE_DURABLE_ENABLED_ENV"
    if [ -e "$persistent_env" ]; then
      flag="$(
        awk -F= '
          $1 == "HEALTH_EVIDENCE_RUNTIME_ENABLED" { value=$2 }
          END { print value }
        ' "$persistent_env"
      )"
    fi
  fi
  dropin="$FAKE_SYSTEMD_RUNTIME_DIR/$normalized.service.d/90-reva-health-evidence-activation.conf"
  if [ -e "$dropin" ]; then
    test "$(grep -c '^EnvironmentFile=' "$dropin")" -eq 1
    test "$(grep -c '^Environment=' "$dropin" || true)" -eq 0
    runtime_env="$(awk -F= '/^EnvironmentFile=/{print $2}' "$dropin")"
    test "$runtime_env" = "$FAKE_RUNTIME_ENABLED_ENV"
    flag="$(
      awk -F= '
        $1 == "HEALTH_EVIDENCE_RUNTIME_ENABLED" { value=$2 }
        END { print value }
      ' "$runtime_env"
    )"
  fi
  if [ "${FAKE_FORCE_PROCESS_FLAG_FOR_UNIT:-}" = "$normalized" ]; then
    flag="${FAKE_FORCE_PROCESS_FLAG_VALUE:-false}"
  fi
  cgroup="$(control_group "$unit")"
  mkdir -p "$FAKE_CGROUP_ROOT$cgroup"
  pid="$(main_pid "$unit")"
  child_pid=$((pid + 1))
  printf '%s\n%s\n' "$pid" "$child_pid" > "$FAKE_CGROUP_ROOT$cgroup/cgroup.procs"
  for process_id in "$pid" "$child_pid"; do
    mkdir -p "$FAKE_PROC_ROOT/$process_id"
    printf 'PATH=/usr/bin\\0HEALTH_EVIDENCE_RUNTIME_ENABLED=%s\\0' "$flag" \
      > "$FAKE_PROC_ROOT/$process_id/environ"
  done
}
case "$1" in
  restart)
    unit="$2"
    printf 'restart:%s\n' "$unit" >> "$FAKE_ACTIVATION_EVENT_LOG"
    printf 'active\n' > "$(state_file "$unit")"
    write_process_environment "$unit"
    if [ "${FAKE_REMOVE_LEASE_AFTER_UNIT:-}" = "$unit" ]; then
      rm -f "$FAKE_RELEASE_LOCK_TOKEN_FILE"
    fi
    ;;
  stop)
    shift
    for unit in "$@"; do
      printf 'stop:%s\n' "$unit" >> "$FAKE_ACTIVATION_EVENT_LOG"
      printf 'inactive\n' > "$(state_file "$unit")"
    done
    ;;
  kill)
    unit="${@: -1}"
    printf 'kill:%s\n' "$unit" >> "$FAKE_ACTIVATION_EVENT_LOG"
    printf 'inactive\n' > "$(state_file "$unit")"
    ;;
  reset-failed)
    unit="$2"
    printf 'reset-failed:%s\n' "$unit" >> "$FAKE_ACTIVATION_EVENT_LOG"
    ;;
  show)
    unit="$2"
    property=
    for arg in "$@"; do
      case "$arg" in
        --property=*) property="${arg#--property=}" ;;
      esac
    done
    case "$property" in
      ActiveState) cat "$(state_file "$unit")" ;;
      SubState)
        if [ "$(cat "$(state_file "$unit")")" != "active" ]; then
          printf 'dead\n'
        elif [ "$(normalize_unit "$unit")" = "health-backend.socket" ]; then
          printf 'listening\n'
        else
          printf 'running\n'
        fi
        ;;
      Result) printf 'success\n' ;;
      NRestarts)
        cat "$FAKE_SERVICE_METRICS_DIR/$(normalize_unit "$unit").restarts"
        ;;
      ActiveEnterTimestampMonotonic)
        cat "$FAKE_SERVICE_METRICS_DIR/$(normalize_unit "$unit").entered"
        ;;
      MainPID) main_pid "$unit"; printf '\n' ;;
      ControlGroup) control_group "$unit"; printf '\n' ;;
      *) exit 93 ;;
    esac
    ;;
  daemon-reload) exit 0 ;;
  *) exit 92 ;;
esac
""",
    )
    _write_executable(
        bin_dir / "curl",
        """#!/bin/bash
set -euo pipefail
args="$*"
case "$args" in
  *auth/me*)
    printf 'curl:auth\n' >> "$FAKE_ACTIVATION_EVENT_LOG"
    printf '401'
    ;;
  *)
    printf 'curl:health\n' >> "$FAKE_ACTIVATION_EVENT_LOG"
    test "${FAKE_HEALTH_FAIL:-0}" != "1"
    ;;
esac
""",
    )
    _write_executable(
        bin_dir / "install",
        """#!/bin/bash
set -euo pipefail
test "$1" = "-o"
test "$2" = "root"
test "$3" = "-g"
test "$4" = "health-app"
test "$5" = "-m"
test "$6" = "0640"
test "$7" = "--"
source="${@: -2:1}"
target="${@: -1}"
printf 'install:%s\n' "$(basename "$source")" >> "$FAKE_ACTIVATION_EVENT_LOG"
cp "$source" "$target"
chmod 0640 "$target"
""",
    )
    _write_executable(
        bin_dir / "stat",
        """#!/bin/bash
set -euo pipefail
target="${@: -1}"
if [ "$target" = "$FAKE_REPO" ]; then
  printf '%s\n' "${FAKE_REPO_STAT:-root:root:700}"
elif [ -d "$target" ]; then
  case "$target" in
    *systemd-runtime*) printf 'root:root:755\n' ;;
    *systemd-persistent*) printf 'root:root:755\n' ;;
    *runtime-state*) printf 'root:root:700\n' ;;
    *durable-state*) printf 'root:root:700\n' ;;
    *) printf 'root:root:700\n' ;;
  esac
else
  case "$target" in
    "$FAKE_REPO"/backend/.env) printf 'root:health-app:640\n' ;;
    */.git/config) printf '%s\n' "${FAKE_GIT_CONFIG_STAT:-root:root:600}" ;;
    "$FAKE_REPO"/.git/*) printf 'root:root:600\n' ;;
    "$FAKE_REPO"/*) printf 'root:root:600\n' ;;
    *runtime-state/enabled.env) printf 'root:root:400\n' ;;
    *durable-state/enabled.env) printf 'root:root:400\n' ;;
    *health-evidence-activation.conf) printf 'root:root:600\n' ;;
    *health-evidence-runtime.conf) printf 'root:root:644\n' ;;
    *) printf 'root:health-app:640\n' ;;
  esac
fi
""",
    )
    _write_executable(
        bin_dir / "id",
        """#!/bin/bash
set -euo pipefail
if [ "$#" -eq 1 ] && [ "$1" = "-u" ]; then
  printf '0\n'
else
  exec /usr/bin/id "$@"
fi
""",
    )
    _write_executable(bin_dir / "chown", "#!/bin/sh\nexit 0\n")
    _write_executable(
        bin_dir / "sleep",
        """#!/bin/bash
set -euo pipefail
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
        """#!/bin/bash
set -euo pipefail
test "$1" = "-f"
test -e "$2"
printf '%s\n' "$2" >> "$FAKE_SYNC_LOG"
pause_match=0
if [ -n "${FAKE_SYNC_PAUSE_MATCH:-}" ]; then
  if [ "${FAKE_SYNC_PAUSE_EXACT:-0}" = "1" ] &&
    [ "$2" = "$FAKE_SYNC_PAUSE_MATCH" ]; then
    pause_match=1
  elif [ "${FAKE_SYNC_PAUSE_EXACT:-0}" != "1" ] &&
    [[ "$2" == *"$FAKE_SYNC_PAUSE_MATCH"* ]]; then
    pause_match=1
  fi
fi
if [ "$pause_match" = "1" ]; then
  : > "$FAKE_SYNC_READY_FILE"
  /bin/sleep "${FAKE_SYNC_PAUSE_SECONDS:-30}"
fi
""",
    )
    return bin_dir


def _write_stage_manifest(stage: Path) -> None:
    lines = []
    for artifact in sorted(stage.iterdir()):
        if artifact.name == "staged.sha256":
            continue
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        lines.append(f"{digest}  {artifact.name}")
    (stage / "staged.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _stage_runner(tmp_path: Path) -> tuple[Path, Path, Path]:
    stage = tmp_path / "activation-stage"
    stage.mkdir()
    runner = stage / ACTIVATION_RUNNER.name
    shutil.copy2(ACTIVATION_RUNNER, runner)
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
    candidate = stage / "candidate.env"
    guard = stage / "guard.env"
    candidate.write_text(
        "DEPLOYMENT_FIXTURE=candidate\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n"
        "SECRET_VALUE=candidate-secret\n",
        encoding="utf-8",
    )
    guard.write_text(
        "DEPLOYMENT_FIXTURE=guard\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        "SECRET_VALUE=guard-secret\n",
        encoding="utf-8",
    )
    _write_stage_manifest(stage)
    return runner, candidate, guard


def _release_lock(tmp_path: Path) -> tuple[Path, str]:
    lock_dir = tmp_path / "release.lock"
    lock_dir.mkdir()
    token = "activation-owner-token"
    (lock_dir / "token").write_text(token + "\n", encoding="utf-8")
    return lock_dir, token


def _runner_env(
    tmp_path: Path, repo: Path, bin_dir: Path
) -> tuple[dict[str, str], Path]:
    event_log = tmp_path / "activation.events"
    state_dir = tmp_path / "service-state"
    state_dir.mkdir()
    systemd_runtime_dir = tmp_path / "systemd-runtime"
    systemd_runtime_dir.mkdir()
    systemd_persistent_dir = tmp_path / "systemd-persistent"
    systemd_persistent_dir.mkdir()
    runtime_state_dir = tmp_path / "runtime-state"
    durable_state_dir = tmp_path / "durable-state"
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    cgroup_root = tmp_path / "cgroup"
    cgroup_root.mkdir()
    service_metrics_dir = tmp_path / "service-metrics"
    service_metrics_dir.mkdir()
    for unit in ("health-backend", "celery-worker", "celery-beat"):
        (service_metrics_dir / f"{unit}.restarts").write_text(
            "0\n", encoding="utf-8"
        )
        (service_metrics_dir / f"{unit}.entered").write_text(
            "1000\n", encoding="utf-8"
        )
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        (state_dir / f"{unit}.state").write_text(
            "active\n", encoding="utf-8"
        )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_ACTIVATION_EVENT_LOG": str(event_log),
        "FAKE_SERVICE_STATE_DIR": str(state_dir),
        "FAKE_REPO": str(repo),
        "FAKE_SYSTEMD_RUNTIME_DIR": str(systemd_runtime_dir),
        "FAKE_SYSTEMD_PERSISTENT_DIR": str(systemd_persistent_dir),
        "FAKE_RUNTIME_ENABLED_ENV": str(runtime_state_dir / "enabled.env"),
        "FAKE_DURABLE_ENABLED_ENV": str(durable_state_dir / "enabled.env"),
        "FAKE_PROC_ROOT": str(proc_root),
        "FAKE_CGROUP_ROOT": str(cgroup_root),
        "FAKE_SERVICE_METRICS_DIR": str(service_metrics_dir),
        "FAKE_STABILITY_BUMP_MARKER": str(
            tmp_path / "stability-restart-bumped"
        ),
        "FAKE_SYNC_LOG": str(tmp_path / "sync.events"),
        "HEALTH_EVIDENCE_ACTIVATION_ATTEMPTS": "1",
        "HEALTH_EVIDENCE_ACTIVATION_SYSTEMD_RUNTIME_DIR": str(
            systemd_runtime_dir
        ),
        "HEALTH_EVIDENCE_ACTIVATION_SYSTEMD_PERSISTENT_DIR": str(
            systemd_persistent_dir
        ),
        "HEALTH_EVIDENCE_ACTIVATION_RUNTIME_STATE_DIR": str(
            runtime_state_dir
        ),
        "HEALTH_EVIDENCE_ACTIVATION_DURABLE_STATE_DIR": str(
            durable_state_dir
        ),
        "HEALTH_EVIDENCE_ACTIVATION_PROC_ROOT": str(proc_root),
        "HEALTH_EVIDENCE_ACTIVATION_CGROUP_ROOT": str(cgroup_root),
    }
    target_env = repo / "backend/.env"
    persistent_flag = "false"
    if target_env.exists():
        persistent_flag = next(
            line.split("=", 1)[1]
            for line in target_env.read_text(encoding="utf-8").splitlines()
            if line.startswith("HEALTH_EVIDENCE_RUNTIME_ENABLED=")
        )
    for unit, pid in (
        ("health-backend", 2101),
        ("celery-worker", 2201),
        ("celery-beat", 2301),
    ):
        cgroup_dir = cgroup_root / "system.slice" / f"{unit}.service"
        cgroup_dir.mkdir(parents=True)
        (cgroup_dir / "cgroup.procs").write_text(
            f"{pid}\n{pid + 1}\n", encoding="utf-8"
        )
        for process_id in (pid, pid + 1):
            process_dir = proc_root / str(process_id)
            process_dir.mkdir()
            (process_dir / "environ").write_bytes(
                b"PATH=/usr/bin\0"
                + (
                    "HEALTH_EVIDENCE_RUNTIME_ENABLED="
                    f"{persistent_flag}\0"
                ).encode()
            )
    return env, event_log


def _seed_authorized_runtime(
    env: dict[str, str],
    bin_dir: Path,
    guard: Path,
    sha: str,
    event_log: Path,
) -> None:
    durable_dir = Path(
        env["HEALTH_EVIDENCE_ACTIVATION_DURABLE_STATE_DIR"]
    )
    durable_dir.mkdir()
    durable_enabled = durable_dir / "enabled.env"
    durable_enabled.write_text(
        f"# commit={sha}\n"
        f"# guard_sha256={hashlib.sha256(guard.read_bytes()).hexdigest()}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    persistent_dir = Path(
        env["HEALTH_EVIDENCE_ACTIVATION_SYSTEMD_PERSISTENT_DIR"]
    )
    for unit in (
        "health-backend.service",
        "celery-worker.service",
        "celery-beat.service",
    ):
        unit_dir = persistent_dir / f"{unit}.d"
        unit_dir.mkdir()
        (unit_dir / "80-reva-health-evidence-runtime.conf").write_text(
            "[Service]\n"
            f"EnvironmentFile=-{durable_enabled}\n",
            encoding="utf-8",
        )
        subprocess.run(
            [str(bin_dir / "systemctl"), "restart", unit.removesuffix(".service")],
            check=True,
            env=env,
        )
    event_log.write_text("", encoding="utf-8")


def _simulate_reboot(
    env: dict[str, str], bin_dir: Path, event_log: Path
) -> None:
    runtime_systemd = Path(
        env["HEALTH_EVIDENCE_ACTIVATION_SYSTEMD_RUNTIME_DIR"]
    )
    shutil.rmtree(runtime_systemd, ignore_errors=True)
    runtime_systemd.mkdir()
    shutil.rmtree(
        Path(env["HEALTH_EVIDENCE_ACTIVATION_RUNTIME_STATE_DIR"]),
        ignore_errors=True,
    )
    for unit in ("health-backend", "celery-worker", "celery-beat"):
        subprocess.run(
            [str(bin_dir / "systemctl"), "restart", unit],
            check=True,
            env=env,
        )
    event_log.write_text("", encoding="utf-8")


def _assert_fake_process_flags(env: dict[str, str], expected: str) -> None:
    proc_root = Path(env["HEALTH_EVIDENCE_ACTIVATION_PROC_ROOT"])
    for pid in (2101, 2102, 2201, 2202, 2301, 2302):
        entries = (proc_root / str(pid) / "environ").read_bytes().split(
            b"\0"
        )
        assert (
            f"HEALTH_EVIDENCE_RUNTIME_ENABLED={expected}".encode()
            in entries
        )


def test_terminal_runner_state_is_durable_and_adopted_without_rewrite(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    state_dir = tmp_path / "activation-state"
    state_dir.mkdir(mode=0o700)
    marker = state_dir / "success"
    unit_name = f"health-evidence-activation-{sha[:12]}-4242.service"
    intent = state_dir / "launch-intent"
    intent.write_text(
        f"commit={sha}\n"
        f"unit={unit_name}\n"
        "lease_sha256="
        f"{hashlib.sha256(token.encode()).hexdigest()}\n",
        encoding="utf-8",
    )
    intent.chmod(0o400)
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)

    activated = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    recovered = subprocess.run(
        [
            str(runner),
            "--recover-if-unverified",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert activated.returncode == 0, (activated.stdout, activated.stderr)
    assert recovered.returncode == 0, (recovered.stdout, recovered.stderr)
    assert marker.read_text(encoding="utf-8").strip() == (
        SUCCESS_TEMPLATE.format(sha=sha)
    )
    outcome = state_dir / "success.outcome"
    assert outcome.read_text(encoding="utf-8").strip() == (
        DEADMAN_NOOP_TEMPLATE.format(sha=sha)
    )
    for terminal_file in (intent, marker, outcome):
        assert stat.S_IMODE(terminal_file.stat().st_mode) == 0o400

    sync_events = Path(env["FAKE_SYNC_LOG"]).read_text(
        encoding="utf-8"
    ).splitlines()
    assert str(marker) in sync_events
    assert str(outcome) in sync_events
    assert str(state_dir) in sync_events

    before = {
        path.name: (
            path.stat().st_ino,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in (*stage_files(runner.parent), *state_dir.iterdir())
    }
    deploy_env = tmp_path / "deploy.env"
    deploy_env.write_text(
        "DEPLOY_SERVER=fake-server\n"
        f"DEPLOY_PATH={repo}\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    deploy_script = ROOT / "deploy.sh"
    harness = f"""
source {deploy_script!s}
set +e
DEPLOY_EXPECTED_SHA={sha}
_REMOTE_RELEASE_LOCK_ACQUIRED=1
_REMOTE_RELEASE_LOCK_ADOPTED=1
_REMOTE_RELEASE_LOCK_ABANDONED=1
_REMOTE_RELEASE_LOCK_DELEGATED=0
REMOTE_RELEASE_LOCK_TOKEN={token}
require_health_evidence_flag_value() {{ return 0; }}
verify_deployed_revision() {{ return 0; }}
stage_health_evidence_activation_artifacts() {{
    test "$(cat "$ADOPT_STATE_DIR/launch-intent")" = \
        "$(printf '%s\\n' \
            'commit={sha}' \
            'unit={unit_name}' \
            'lease_sha256={hashlib.sha256(token.encode()).hexdigest()}')"
}}
prove_health_evidence_activation_state() {{
    test "$1" = enabled
    test "$(cat "$ADOPT_STATE_DIR/success")" = "$4"
    test "$(cat "$ADOPT_STATE_DIR/success.outcome")" = "$3"
}}
verify_runtime_only_kb_contract() {{ exit 91; }}
verify_systemd_activation_capability() {{ exit 92; }}
run_health_evidence_activation_unit() {{ exit 93; }}
prove_health_evidence_activation_not_launched() {{ exit 94; }}
activate_health_evidence_runtime
rc=$?
printf 'rc=%s delegated=%s abandoned=%s\\n' \
    "$rc" \
    "$_REMOTE_RELEASE_LOCK_DELEGATED" \
    "$_REMOTE_RELEASE_LOCK_ABANDONED"
"""
    adopted = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "DEPLOY_ENV_FILE": str(deploy_env),
            "ADOPT_STATE_DIR": str(state_dir),
        },
        check=False,
    )

    assert adopted.returncode == 0, (adopted.stdout, adopted.stderr)
    assert "rc=0 delegated=0 abandoned=0" in adopted.stdout
    after = {
        path.name: (
            path.stat().st_ino,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in (*stage_files(runner.parent), *state_dir.iterdir())
    }
    assert after == before


def stage_files(stage: Path) -> tuple[Path, ...]:
    return tuple(sorted(stage.iterdir(), key=lambda path: path.name))


def test_activation_revision_proof_never_executes_repo_fsmonitor(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    fsmonitor_marker = tmp_path / "fsmonitor-executed"
    fsmonitor_hook = tmp_path / "malicious-fsmonitor.sh"
    _write_executable(
        fsmonitor_hook,
        "#!/bin/sh\n"
        f": > {fsmonitor_marker!s}\n"
        "printf '\\n'\n",
    )
    subprocess.run(
        ["git", "config", "core.fsmonitor", str(fsmonitor_hook)],
        cwd=repo,
        check=True,
    )
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.strip() == SUCCESS_TEMPLATE.format(sha=sha)
    assert not fsmonitor_marker.exists()


def test_activation_revision_proof_never_executes_repo_clean_filter(
    tmp_path: Path,
):
    repo, _ = _make_release_repo(tmp_path)
    (repo / ".gitattributes").write_text(
        "payload.txt filter=evil\n", encoding="utf-8"
    )
    (repo / "payload.txt").write_text("canonical\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitattributes", "payload.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "add filter fixture"], cwd=repo, check=True
    )
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    filter_marker = tmp_path / "clean-filter-executed"
    clean_filter = tmp_path / "malicious-clean-filter.sh"
    _write_executable(
        clean_filter,
        "#!/bin/sh\n"
        f": > {filter_marker!s}\n"
        "cat >/dev/null\n"
        "printf 'canonical\\n'\n",
    )
    subprocess.run(
        ["git", "config", "filter.evil.clean", str(clean_filter)],
        cwd=repo,
        check=True,
    )
    # Keep the same byte length as the committed content so Git must hash the
    # worktree file instead of rejecting it from stat data alone.
    (repo / "payload.txt").write_text("tampered!\n", encoding="utf-8")
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 70, (result.stdout, result.stderr)
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert not filter_marker.exists()
    assert not marker.exists()


def test_activation_revision_proof_ignores_repo_core_worktree(tmp_path: Path):
    repo, sha = _make_release_repo(tmp_path)
    alternate = tmp_path / "alternate-worktree"
    subprocess.run(
        ["git", "clone", "-q", str(repo), str(alternate)], check=True
    )
    subprocess.run(
        ["git", "config", "core.worktree", str(alternate)],
        cwd=repo,
        check=True,
    )
    (repo / ".gitignore").write_text(
        "backend/.env\nunexpected-dirty-entry\n", encoding="utf-8"
    )
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 70, (result.stdout, result.stderr)
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert not marker.exists()


@pytest.mark.parametrize(
    "index_flag",
    ["--assume-unchanged", "--skip-worktree"],
)
def test_activation_revision_proof_rebuilds_index_from_expected_tree(
    tmp_path: Path,
    index_flag: str,
):
    repo, sha = _make_release_repo(tmp_path)
    subprocess.run(
        ["git", "update-index", index_flag, ".gitignore"],
        cwd=repo,
        check=True,
    )
    (repo / ".gitignore").write_text(
        "backend/.env\nhidden-runtime-tamper\n", encoding="utf-8"
    )
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 70, (result.stdout, result.stderr)
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert not marker.exists()


def test_activation_blocks_group_writable_git_config(tmp_path: Path):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)
    env["FAKE_GIT_CONFIG_STAT"] = "root:root:666"

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 70, (result.stdout, result.stderr)
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert not marker.exists()
    state_dir = Path(env["FAKE_SERVICE_STATE_DIR"])
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (state_dir / f"{unit}.state").read_text(
            encoding="utf-8"
        ).strip() == "inactive"


def test_activation_blocks_non_root_owned_release_repo(tmp_path: Path):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)
    env["FAKE_REPO_STAT"] = "UNKNOWN:staff:755"

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 70, (result.stdout, result.stderr)
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert not marker.exists()
    state_dir = Path(env["FAKE_SERVICE_STATE_DIR"])
    for unit in (
        "health-backend.socket",
        "health-backend",
        "celery-worker",
        "celery-beat",
    ):
        assert (state_dir / f"{unit}.state").read_text(
            encoding="utf-8"
        ).strip() == "inactive"


def test_activation_proves_ephemeral_canary_before_persisting_candidate(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    sentinel = SUCCESS_TEMPLATE.format(sha=sha)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == sentinel
    assert marker.read_text(encoding="utf-8").strip() == sentinel
    assert Path(f"{marker}.outcome").read_text(encoding="utf-8").strip() == (
        sentinel
    )
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "restart:health-backend.socket",
        "restart:health-backend",
        "restart:celery-worker",
        "restart:celery-beat",
        "curl:health",
        "curl:auth",
        "python:score:flag=true",
        "python:contract:enabled:flag=true",
        "restart:health-backend.socket",
        "restart:health-backend",
        "restart:celery-worker",
        "restart:celery-beat",
        "curl:health",
        "curl:auth",
        "python:score:flag=true",
        "python:contract:enabled:flag=true",
    ]
    assert not any(
        Path(env["HEALTH_EVIDENCE_ACTIVATION_SYSTEMD_RUNTIME_DIR"]).rglob(
            "*health-evidence-activation.conf"
        )
    )
    assert not Path(
        env["HEALTH_EVIDENCE_ACTIVATION_RUNTIME_STATE_DIR"]
    ).exists()
    durable_enabled = (
        Path(env["HEALTH_EVIDENCE_ACTIVATION_DURABLE_STATE_DIR"])
        / "enabled.env"
    )
    assert durable_enabled.read_text(encoding="utf-8").splitlines() == [
        f"# commit={sha}",
        f"# guard_sha256={hashlib.sha256(guard.read_bytes()).hexdigest()}",
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true",
    ]
    for unit in (
        "health-backend.service",
        "celery-worker.service",
        "celery-beat.service",
    ):
        persistent_dropin = (
            Path(
                env[
                    "HEALTH_EVIDENCE_ACTIVATION_SYSTEMD_PERSISTENT_DIR"
                ]
            )
            / f"{unit}.d"
            / "80-reva-health-evidence-runtime.conf"
        )
        assert persistent_dropin.read_text(encoding="utf-8") == (
            "[Service]\n"
            f"EnvironmentFile=-{durable_enabled}\n"
        )
    sync_targets = (tmp_path / "sync.events").read_text(
        encoding="utf-8"
    ).splitlines()
    assert any(".enabled-commit." in target for target in sync_targets)
    assert str(durable_enabled.parent) in sync_targets


def test_activation_restart_during_stability_window_recovers_to_guard(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)
    env["FAKE_BUMP_RESTART_ON_STABILITY"] = "1"

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == ROLLBACK_TEMPLATE.format(sha=sha)
    assert not marker.exists()
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    assert Path(env["FAKE_STABILITY_BUMP_MARKER"]).exists()
    _assert_fake_process_flags(env, "false")


def test_reboot_before_durable_commit_returns_to_false(tmp_path: Path):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)
    ready_file = tmp_path / "durable-temp.ready"
    env["FAKE_SYNC_PAUSE_MATCH"] = ".enabled-commit."
    env["FAKE_SYNC_READY_FILE"] = str(ready_file)
    env["FAKE_SYNC_PAUSE_SECONDS"] = "30"

    process = subprocess.Popen(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    deadline = time.monotonic() + 45
    while not ready_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert ready_file.exists()
    process.kill()
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)

    durable_enabled = (
        Path(env["HEALTH_EVIDENCE_ACTIVATION_DURABLE_STATE_DIR"])
        / "enabled.env"
    )
    assert not durable_enabled.exists()
    assert not marker.exists()
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    _simulate_reboot(env, bin_dir, event_log)
    _assert_fake_process_flags(env, "false")


def test_reboot_after_durable_commit_stays_true_without_outcome(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)
    durable_dir = Path(
        env["HEALTH_EVIDENCE_ACTIVATION_DURABLE_STATE_DIR"]
    )
    ready_file = tmp_path / "durable-commit.ready"
    env["FAKE_SYNC_PAUSE_MATCH"] = str(durable_dir)
    env["FAKE_SYNC_PAUSE_EXACT"] = "1"
    env["FAKE_SYNC_READY_FILE"] = str(ready_file)
    env["FAKE_SYNC_PAUSE_SECONDS"] = "30"

    process = subprocess.Popen(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    deadline = time.monotonic() + 45
    while not ready_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert ready_file.exists()
    process.kill()
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)

    durable_enabled = durable_dir / "enabled.env"
    assert durable_enabled.exists()
    assert not marker.exists()
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    _simulate_reboot(env, bin_dir, event_log)
    _assert_fake_process_flags(env, "true")

    result = subprocess.run(
        [
            str(runner),
            "--recover-if-unverified",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"HEALTH_EVIDENCE_DEADMAN_NOOP commit={sha} "
        "authorization=verified"
    )
    assert marker.read_text(encoding="utf-8").strip() == (
        SUCCESS_TEMPLATE.format(sha=sha)
    )
    _assert_fake_process_flags(env, "true")


def test_false_real_service_environment_recovers_before_enabled_probes(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)
    env["FAKE_FORCE_PROCESS_FLAG_FOR_UNIT"] = "health-backend"
    env["FAKE_FORCE_PROCESS_FLAG_VALUE"] = "false"

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == ROLLBACK_TEMPLATE.format(
        sha=sha
    ), (result.stderr, event_log.read_text(encoding="utf-8"))
    assert not marker.exists()
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert "python:contract:enabled:flag=true" not in events
    assert events == [
        "restart:health-backend.socket",
        "restart:health-backend",
        "restart:celery-worker",
        "restart:celery-beat",
        "install:guard.env",
        "restart:health-backend.socket",
        "restart:health-backend",
        "restart:celery-worker",
        "restart:celery-beat",
        "curl:health",
        "python:contract:staged:flag=false",
    ]


def test_enabled_contract_failure_installs_guard_and_reverifies_staged(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)
    env["FAKE_FAIL_ENABLED_CONTRACT"] = "1"

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == ROLLBACK_TEMPLATE.format(
        sha=sha
    ), (result.stderr, event_log.read_text(encoding="utf-8"))
    assert SUCCESS_TEMPLATE.format(sha=sha) not in result.stdout
    assert not marker.exists()
    assert Path(f"{marker}.outcome").read_text(encoding="utf-8").strip() == (
        ROLLBACK_TEMPLATE.format(sha=sha)
    )
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "restart:health-backend.socket",
        "restart:health-backend",
        "restart:celery-worker",
        "restart:celery-beat",
        "curl:health",
        "curl:auth",
        "python:score:flag=true",
        "python:contract:enabled:flag=true",
        "install:guard.env",
        "restart:health-backend.socket",
        "restart:health-backend",
        "restart:celery-worker",
        "restart:celery-beat",
        "curl:health",
        "python:contract:staged:flag=false",
    ]
    assert "install:candidate.env" not in event_log.read_text(encoding="utf-8")


def test_failed_guard_reverification_contains_every_unit_socket_first(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)
    env["FAKE_FAIL_ENABLED_CONTRACT"] = "1"
    env["FAKE_FAIL_STAGED_CONTRACT"] = "1"

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert not marker.exists()
    events = event_log.read_text(encoding="utf-8").splitlines()
    containment_start = events.index("stop:health-backend.socket")
    assert events[containment_start : containment_start + 4] == [
        "stop:health-backend.socket",
        "stop:health-backend",
        "stop:celery-worker",
        "stop:celery-beat",
    ]
    assert events[containment_start + 4 :] == [
        "kill:health-backend.socket",
        "reset-failed:health-backend.socket",
        "kill:health-backend",
        "reset-failed:health-backend",
        "kill:celery-worker",
        "reset-failed:celery-worker",
        "kill:celery-beat",
        "reset-failed:celery-beat",
    ]


def test_deadman_without_marker_forces_guard_and_staged_verification(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(candidate.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--recover-if-unverified",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"HEALTH_EVIDENCE_DEADMAN_RECOVERED commit={sha} flag=false "
        "health=passed contract=staged services=active"
    )
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "install:guard.env",
        "restart:health-backend.socket",
        "restart:health-backend",
        "restart:celery-worker",
        "restart:celery-beat",
        "curl:health",
        "python:contract:staged:flag=false",
    ]


def test_deadman_with_exact_success_marker_is_a_noop(tmp_path: Path):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    marker.write_text(
        SUCCESS_TEMPLATE.format(sha=sha) + "\n", encoding="utf-8"
    )
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)
    _seed_authorized_runtime(env, bin_dir, guard, sha, event_log)

    result = subprocess.run(
        [
            str(runner),
            "--recover-if-unverified",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"HEALTH_EVIDENCE_DEADMAN_NOOP commit={sha} "
        "authorization=verified"
    )
    assert Path(f"{marker}.outcome").read_text(encoding="utf-8").strip() == (
        f"HEALTH_EVIDENCE_DEADMAN_NOOP commit={sha} "
        "authorization=verified"
    )
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "curl:health",
        "curl:auth",
        "python:score:flag=true",
        "python:contract:enabled:flag=true",
    ]


def test_deadman_never_trusts_marker_when_target_is_not_exact_candidate(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    marker.write_text(
        SUCCESS_TEMPLATE.format(sha=sha) + "\n", encoding="utf-8"
    )
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--recover-if-unverified",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "HEALTH_EVIDENCE_DEADMAN_RECOVERED" in result.stdout
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    assert event_log.read_text(encoding="utf-8").splitlines() == [
        "install:guard.env",
        "restart:health-backend.socket",
        "restart:health-backend",
        "restart:celery-worker",
        "restart:celery-beat",
        "curl:health",
        "python:contract:staged:flag=false",
    ]


def test_stage_manifest_must_hash_the_running_script_and_every_artifact(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    manifest = runner.parent / "staged.sha256"
    manifest.write_text(
        "".join(
            line
            for line in manifest.read_text(encoding="utf-8").splitlines(
                keepends=True
            )
            if not line.endswith(f"  {runner.name}\n")
        ),
        encoding="utf-8",
    )
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--recover-if-unverified",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert events[:4] == [
        "stop:health-backend.socket",
        "stop:health-backend",
        "stop:celery-worker",
        "stop:celery-beat",
    ]
    assert not any(event.startswith("install:") for event in events)


def test_extra_symlink_in_immutable_stage_fails_before_true_install(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (runner.parent / "unexpected-link").symlink_to(guard)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert "install:candidate.env" not in event_log.read_text(encoding="utf-8")


def test_noncanonical_or_duplicate_candidate_flag_recovers_to_guard(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    candidate.write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=TRUE\n"
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    _write_stage_manifest(runner.parent)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == ROLLBACK_TEMPLATE.format(sha=sha)
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
    assert event_log.read_text(encoding="utf-8").splitlines()[0] == (
        "install:guard.env"
    )


def test_export_alias_cannot_override_canonical_guard_flag(tmp_path: Path):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    guard.write_text(
        "HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
        "export HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n",
        encoding="utf-8",
    )
    _write_stage_manifest(runner.parent)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert not marker.exists()
    assert event_log.read_text(encoding="utf-8").splitlines()[:4] == [
        "stop:health-backend.socket",
        "stop:health-backend",
        "stop:celery-worker",
        "stop:celery-beat",
    ]


def test_lost_release_lease_never_reaches_enabled_and_contains(
    tmp_path: Path,
):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, event_log = _runner_env(tmp_path, repo, bin_dir)
    env["FAKE_REMOVE_LEASE_AFTER_UNIT"] = "health-backend.socket"
    env["FAKE_RELEASE_LOCK_TOKEN_FILE"] = str(lock_dir / "token")

    result = subprocess.run(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout.strip() == BLOCKED_TEMPLATE.format(sha=sha)
    assert not marker.exists()
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert "python:contract:enabled:flag=true" not in events
    assert "stop:health-backend.socket" in events


def test_term_before_enabled_proof_runs_exit_guard(tmp_path: Path):
    repo, sha = _make_release_repo(tmp_path)
    runner, candidate, guard = _stage_runner(tmp_path)
    (repo / "backend/.env").write_bytes(guard.read_bytes())
    lock_dir, token = _release_lock(tmp_path)
    marker = tmp_path / "activation.success"
    bin_dir = _fake_commands(tmp_path)
    env, _ = _runner_env(tmp_path, repo, bin_dir)
    ready_file = tmp_path / "enabled.ready"
    env["FAKE_ENABLED_READY_FILE"] = str(ready_file)
    env["FAKE_ENABLED_PAUSE_SECONDS"] = "2"

    process = subprocess.Popen(
        [
            str(runner),
            "--activate",
            str(repo),
            sha,
            str(candidate),
            str(guard),
            str(marker),
            str(lock_dir),
            token,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    deadline = time.monotonic() + 30
    while not ready_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not ready_file.exists():
        process.terminate()
        stdout, stderr = process.communicate(timeout=10)
        pytest.fail(
            "activation runner did not reach enabled proof pause: "
            f"returncode={process.returncode}, stdout={stdout!r}, "
            f"stderr={stderr!r}"
        )
    process.send_signal(signal.SIGTERM)
    try:
        # Guard recovery deliberately proves two service-stability windows
        # before it reports a safe rollback. Keep the test deadline above
        # that production contract, and always reap the child on failure.
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
        pytest.fail(
            "activation runner did not finish TERM recovery within 30s: "
            f"returncode={process.returncode}, stdout={stdout!r}, "
            f"stderr={stderr!r}"
        )

    assert process.returncode != 0, stderr
    assert stdout.strip() == ROLLBACK_TEMPLATE.format(sha=sha)
    assert not marker.exists()
    assert (repo / "backend/.env").read_bytes() == guard.read_bytes()
