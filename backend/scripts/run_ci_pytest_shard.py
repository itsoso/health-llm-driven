#!/usr/bin/env python3
"""Run a pytest shard with a process deadline and one timeout retry."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_MAX_ATTEMPTS = 2
TIMEOUT_EXIT_CODE = 124


def build_pytest_command(
    path_inputs: Sequence[str],
    pytest_args: Sequence[str],
) -> list[str]:
    return [sys.executable, "-m", "pytest", *path_inputs, *pytest_args]


def instrument_pytest_args(
    pytest_args: Sequence[str],
    *,
    junit_path: str | None,
) -> list[str]:
    """Add bounded timing telemetry without overriding explicit caller flags."""
    args = list(pytest_args)
    if not any(arg == "--durations" or arg.startswith("--durations=") for arg in args):
        args.append("--durations=50")
    if not any(arg == "--durations-min" or arg.startswith("--durations-min=") for arg in args):
        args.append("--durations-min=0.01")
    if junit_path and not any(
        arg == "--junitxml" or arg.startswith(("--junitxml=", "--junit-xml="))
        for arg in args
    ):
        args.append(f"--junitxml={junit_path}")
    return args


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
        attempt_started_at = time.monotonic()
        print(
            f"[ci-shard] attempt {attempt}/{max_attempts}, "
            f"deadline={timeout_seconds}s",
            flush=True,
        )
        try:
            return_code = attempt_runner(command, timeout_seconds)
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - attempt_started_at) * 1000)
            print(
                "[ci-shard-timing] "
                + json.dumps(
                    {
                        "attempt": attempt,
                        "duration_ms": elapsed_ms,
                        "outcome": "timeout",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                flush=True,
            )
            print(
                f"[ci-shard] attempt {attempt} exceeded {timeout_seconds}s",
                file=sys.stderr,
                flush=True,
            )
            if attempt == max_attempts:
                return TIMEOUT_EXIT_CODE
            print("[ci-shard] retrying in a fresh process", flush=True)
            continue

        elapsed_ms = int((time.monotonic() - attempt_started_at) * 1000)
        print(
            "[ci-shard-timing] "
            + json.dumps(
                {
                    "attempt": attempt,
                    "duration_ms": elapsed_ms,
                    "outcome": "pass" if return_code == 0 else "failure",
                    "return_code": return_code,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            flush=True,
        )

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

    junit_path = str(os.environ.get("CI_PYTEST_JUNIT_XML", "") or "").strip() or None
    if junit_path:
        Path(junit_path).parent.mkdir(parents=True, exist_ok=True)
    return run_shard(
        path_inputs,
        instrument_pytest_args(pytest_args, junit_path=junit_path),
    )


if __name__ == "__main__":
    raise SystemExit(main())
