#!/usr/bin/env python3
"""Run a pytest shard with a process deadline and one timeout retry."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import os
import signal
import subprocess
import sys


DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_MAX_ATTEMPTS = 2
TIMEOUT_EXIT_CODE = 124


def build_pytest_command(
    path_inputs: Sequence[str],
    pytest_args: Sequence[str],
) -> list[str]:
    return [sys.executable, "-m", "pytest", *path_inputs, *pytest_args]


def _terminate_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait()


def run_attempt(command: list[str], timeout_seconds: int) -> int:
    process = subprocess.Popen(command, start_new_session=True)
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        raise subprocess.TimeoutExpired(command, timeout_seconds) from exc


def run_shard(
    path_inputs: Sequence[str],
    pytest_args: Sequence[str],
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    attempt_runner: Callable[[list[str], int], int] = run_attempt,
) -> int:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    command = build_pytest_command(path_inputs, pytest_args)
    for attempt in range(1, max_attempts + 1):
        print(
            f"[ci-shard] attempt {attempt}/{max_attempts}, "
            f"deadline={timeout_seconds}s",
            flush=True,
        )
        try:
            return_code = attempt_runner(command, timeout_seconds)
        except subprocess.TimeoutExpired:
            print(
                f"[ci-shard] attempt {attempt} exceeded {timeout_seconds}s",
                file=sys.stderr,
                flush=True,
            )
            if attempt == max_attempts:
                return TIMEOUT_EXIT_CODE
            print("[ci-shard] retrying in a fresh process", flush=True)
            continue

        # Assertion and collection failures are deterministic signals. Do not
        # hide them behind a retry; only process-level timeouts get one retry.
        return return_code

    return TIMEOUT_EXIT_CODE


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--" not in arguments:
        print("usage: run_ci_pytest_shard.py <paths...> -- <pytest args...>", file=sys.stderr)
        return 2

    separator = arguments.index("--")
    path_inputs = arguments[:separator]
    pytest_args = arguments[separator + 1 :]
    if not path_inputs:
        print("at least one pytest path is required", file=sys.stderr)
        return 2

    return run_shard(path_inputs, pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
