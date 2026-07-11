"""CI pytest shard runner contract tests."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest


def test_build_pytest_command_keeps_the_shard_in_one_process():
    from scripts.run_ci_pytest_shard import build_pytest_command

    command = build_pytest_command(
        ["tests/test_alpha.py", "tests/test_beta.py"],
        ["-q", "--no-cov"],
    )

    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_alpha.py",
        "tests/test_beta.py",
        "-q",
        "--no-cov",
    ]


def test_run_shard_retries_timeout_in_a_fresh_process():
    from scripts.run_ci_pytest_shard import run_shard

    calls: list[tuple[list[str], int]] = []

    def fake_attempt(command: list[str], timeout_seconds: int) -> int:
        calls.append((command, timeout_seconds))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, timeout_seconds)
        return 0

    return_code = run_shard(
        ["tests/test_alpha.py"],
        ["-q"],
        timeout_seconds=600,
        max_attempts=2,
        attempt_runner=fake_attempt,
    )

    assert return_code == 0
    assert len(calls) == 2
    assert calls[0][0] == calls[1][0]


def test_run_shard_does_not_retry_assertion_failure():
    from scripts.run_ci_pytest_shard import run_shard

    calls = 0

    def fake_attempt(_command: list[str], _timeout_seconds: int) -> int:
        nonlocal calls
        calls += 1
        return 7

    return_code = run_shard(
        ["tests/test_alpha.py"],
        ["-q"],
        timeout_seconds=600,
        max_attempts=2,
        attempt_runner=fake_attempt,
    )

    assert return_code == 7
    assert calls == 1


def test_run_shard_returns_timeout_code_after_final_timeout():
    from scripts.run_ci_pytest_shard import TIMEOUT_EXIT_CODE, run_shard

    def always_timeout(command: list[str], timeout_seconds: int) -> int:
        raise subprocess.TimeoutExpired(command, timeout_seconds)

    return_code = run_shard(
        ["tests/test_alpha.py"],
        ["-q"],
        timeout_seconds=600,
        max_attempts=2,
        attempt_runner=always_timeout,
    )

    assert return_code == TIMEOUT_EXIT_CODE


def test_run_attempt_terminates_a_hung_process_group():
    from scripts.run_ci_pytest_shard import run_attempt

    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    started_at = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        run_attempt(command, timeout_seconds=1)

    assert time.monotonic() - started_at < 5
