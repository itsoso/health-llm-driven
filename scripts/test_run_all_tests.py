from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUN_ALL_TESTS = ROOT / "scripts" / "run-all-tests.sh"


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _init_fixture_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "validation@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Validation Test"],
        cwd=repo,
        check=True,
    )
    for relative in (
        "backend/tests/.keep",
        "backend/requirements.lock",
        "frontend/package-lock.json",
        "mobile/package-lock.json",
    ):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    runner = tmp_path / "fake_check.py"
    runner.write_text(
        """#!/usr/bin/env python3
import fcntl
import json
import os
import pathlib
import sys
import time

label = sys.argv[1]
state_path = pathlib.Path(os.environ["FAKE_CHECK_STATE"])
state_path.parent.mkdir(parents=True, exist_ok=True)
with state_path.open("a+", encoding="utf-8") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    handle.seek(0)
    raw = handle.read().strip()
    state = json.loads(raw) if raw else {"current": 0, "maximum": 0, "labels": [], "pids": []}
    state["current"] += 1
    state["maximum"] = max(state["maximum"], state["current"])
    state["labels"].append(label)
    state["pids"].append(os.getpid())
    handle.seek(0)
    handle.truncate()
    json.dump(state, handle)
    handle.flush()
    fcntl.flock(handle, fcntl.LOCK_UN)

print(f"running {label}", flush=True)
time.sleep(float(os.environ.get("FAKE_CHECK_SLEEP", "0.05")))

with state_path.open("r+", encoding="utf-8") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    state = json.load(handle)
    state["current"] -= 1
    handle.seek(0)
    handle.truncate()
    json.dump(state, handle)
    handle.flush()
    fcntl.flock(handle, fcntl.LOCK_UN)

raise SystemExit(7 if label == os.environ.get("FAKE_CHECK_FAIL") else 0)
""",
        encoding="utf-8",
    )
    runner.chmod(0o755)

    def wrapper(label: str) -> str:
        return f"#!/bin/sh\nexec {sys.executable!s} {runner!s} {label}\n"

    _write_executable(repo / "backend/venv/bin/python", wrapper("backend-pytest"))
    _write_executable(repo / "frontend/node_modules/.bin/tsc", wrapper("frontend-tsc"))
    _write_executable(repo / "mobile/node_modules/.bin/jest", wrapper("mobile-jest"))
    _write_executable(repo / "mobile/node_modules/.bin/tsc", wrapper("mobile-tsc"))
    npm = fake_bin / "npm"
    _write_executable(
        npm,
        f"""#!/bin/sh
if [ "${{1:-}}" = "--version" ]; then
  echo 10.8.0
  exit 0
fi
case "$PWD:$*" in
  */frontend:*"run test"*) label=frontend-vitest ;;
  */frontend:*"run lint"*) label=frontend-lint ;;
  */mobile:*"run lint"*) label=mobile-lint ;;
  */mobile:*"run design:check"*) label=mobile-design ;;
  */mobile:*"run check:settings-routes"*) label=mobile-settings-routes ;;
  *) echo "unexpected npm invocation: $PWD:$*" >&2; exit 91 ;;
esac
exec {sys.executable!s} {runner!s} "$label"
""",
    )
    _write_executable(fake_bin / "node", "#!/bin/sh\necho v22.0.0\n")
    _write_executable(fake_bin / "swift", "#!/bin/sh\necho 'Swift version 6.0'\n")

    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    state_path = tmp_path / "check-state.json"
    log_root = tmp_path / "logs"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "REVA_VALIDATION_ROOT": str(repo),
        "REVA_VALIDATION_ALLOW_ROOT_OVERRIDE_FOR_TESTS": "1",
        "REVA_VALIDATION_LOG_DIR": str(log_root),
        "FAKE_CHECK_STATE": str(state_path),
        "FAKE_CHECK_SLEEP": "0.05",
    }
    return repo, env


def _run(profile: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUN_ALL_TESTS), profile],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_all_profile_runs_checks_in_parallel_with_private_logs(tmp_path: Path) -> None:
    _, env = _init_fixture_repo(tmp_path)
    env["FAKE_CHECK_SLEEP"] = "0.2"

    result = _run("all", env)

    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads(Path(env["FAKE_CHECK_STATE"]).read_text(encoding="utf-8"))
    assert 2 <= state["maximum"] <= 4
    assert {
        "backend-pytest",
        "frontend-vitest",
        "frontend-tsc",
        "frontend-lint",
        "mobile-jest",
        "mobile-tsc",
        "mobile-lint",
        "mobile-design",
        "mobile-settings-routes",
    }.issubset(state["labels"])
    logs = list(Path(env["REVA_VALIDATION_LOG_DIR"]).rglob("*.log"))
    assert len(logs) >= 10
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in logs)


def test_frontend_lint_failure_is_blocking_and_uses_real_exit_code(tmp_path: Path) -> None:
    _, env = _init_fixture_repo(tmp_path)
    env["FAKE_CHECK_FAIL"] = "frontend-lint"

    result = _run("--frontend", env)

    assert result.returncode == 1
    assert "frontend:lint" in result.stdout
    assert "exit 7" in result.stdout


def test_successful_checks_emit_one_summary_line_each(tmp_path: Path) -> None:
    _, env = _init_fixture_repo(tmp_path)

    result = _run("--backend", env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("Backend pytest (") == 1
    assert result.stdout.count("Git whitespace check (") == 1


def test_mobile_profile_includes_lint_design_and_settings_route_checks(tmp_path: Path) -> None:
    _, env = _init_fixture_repo(tmp_path)

    result = _run("--mobile", env)

    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads(Path(env["FAKE_CHECK_STATE"]).read_text(encoding="utf-8"))
    assert {
        "mobile-jest",
        "mobile-tsc",
        "mobile-lint",
        "mobile-design",
        "mobile-settings-routes",
    }.issubset(state["labels"])


def test_validation_root_override_is_rejected_without_explicit_test_mode(
    tmp_path: Path,
) -> None:
    _, env = _init_fixture_repo(tmp_path)
    env.pop("REVA_VALIDATION_ALLOW_ROOT_OVERRIDE_FOR_TESTS")
    env["CI"] = "true"

    result = _run("--mobile", env)

    assert result.returncode == 2
    assert "REVA_VALIDATION_ROOT" in result.stderr
    assert "explicit test mode" in result.stderr


def test_explicit_test_root_must_still_equal_its_git_toplevel(tmp_path: Path) -> None:
    repo, env = _init_fixture_repo(tmp_path)
    nested = repo / "nested"
    nested.mkdir()
    env["REVA_VALIDATION_ROOT"] = str(nested)

    result = _run("--mobile", env)

    assert result.returncode == 2
    assert "must equal Git toplevel" in result.stderr


@pytest.mark.parametrize(
    ("sent_signal", "expected_exit"),
    [(signal.SIGINT, 130), (signal.SIGTERM, 143)],
)
def test_interrupt_reaps_every_running_child(
    tmp_path: Path, sent_signal: signal.Signals, expected_exit: int
) -> None:
    _, env = _init_fixture_repo(tmp_path)
    env["FAKE_CHECK_SLEEP"] = "30"
    process = subprocess.Popen(
        ["bash", str(RUN_ALL_TESTS), "--quick"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    state_path = Path(env["FAKE_CHECK_STATE"])
    deadline = time.monotonic() + 5
    pids: list[int] = []
    while time.monotonic() < deadline:
        if state_path.exists():
            try:
                pids = json.loads(state_path.read_text(encoding="utf-8"))["pids"]
            except (json.JSONDecodeError, KeyError):
                pass
            if len(pids) >= 4:
                break
        time.sleep(0.02)
    assert len(pids) >= 4

    process.send_signal(sent_signal)
    stdout, stderr = process.communicate(timeout=8)

    assert process.returncode == expected_exit, stdout + stderr
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_validation_scripts_never_pipe_running_tests_to_tail() -> None:
    run_all_source = RUN_ALL_TESTS.read_text(encoding="utf-8")
    validate_source = (ROOT / "scripts/validate.py").read_text(encoding="utf-8")

    assert "| tail" not in run_all_source
    assert "| tail" not in validate_source
